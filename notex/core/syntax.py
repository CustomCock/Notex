"""Syntax-Highlighting-Logik ohne Qt: Lexer je Endung, Token-Klassen, Zustand über Blockgrenzen, Log-Zeilen.

Pygments lexed eigentlich ganze Dateien. Für den Editor arbeiten wir zeilenweise und
merken uns pro Zeile, ob sie in einem mehrzeiligen String/Kommentar endet. Die nächste
Zeile wird dann mit einem passenden „Eröffner“ davor gelexed, damit der Zustand stimmt.
Das deckt die üblichen Fälle ab (Python-Docstrings, /* */-Kommentare, Markdown-Codeblöcke).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Literal, Name, Number, Operator, String, Token
from pygments.util import ClassNotFound

# Endung -> Pygments-Lexername
LEXERS: dict[str, str] = {
    ".py": "python", ".json": "json", ".ini": "ini", ".sh": "bash", ".ps1": "powershell", ".bat": "batch",
    ".yaml": "yaml", ".yml": "yaml", ".xml": "xml", ".html": "html", ".css": "css", ".js": "javascript",
    ".sql": "sql", ".md": "markdown", ".log": "log", ".yar": "yara", ".yara": "yara",
}
DEFAULT_EXTENSIONS = [".txt", ".md", ".log", ".csv", ".json", ".py", ".ini", ".sh", ".ps1", ".bat", ".yaml", ".yml",
                      ".xml", ".html", ".css", ".js", ".sql"]

# Anzeigeklassen (Theme-Tokens): keyword, string, comment, number, function, operator, tag, attribute, log_*
STYLE_CLASSES = ["keyword", "string", "comment", "number", "function", "operator", "tag", "attribute",
                 "log_error", "log_warn", "log_info", "log_debug", "log_time", "log_ip", "log_path"]

# Zustände über Blockgrenzen: was am Zeilenende offen blieb
STATE_NONE = 0
STATE_TRIPLE_DQ = 1     # Python """ ... """
STATE_TRIPLE_SQ = 2     # Python ''' ... '''
STATE_BLOCK_COMMENT = 3  # /* ... */
STATE_FENCE = 4          # Markdown ``` ...
STATE_FENCE_LANG_BASE = 100   # 100 + Index der Sprache im Fence (siehe FENCE_LANGS)
FENCE_LANGS = ["", "python", "json", "bash", "yaml", "javascript", "html", "css", "sql", "xml", "ini", "powershell", "batch", "yara"]

_OPENERS = {STATE_TRIPLE_DQ: '"""', STATE_TRIPLE_SQ: "'''", STATE_BLOCK_COMMENT: "/*"}
_FENCE_RE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
_C_LIKE = {"javascript", "css", "sql", "java", "c", "cpp", "yara"}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    style: str


def lexer_for_extension(ext: str) -> str | None:
    return LEXERS.get(ext.lower())


@lru_cache(maxsize=32)
def _lexer(name: str):
    try:
        return get_lexer_by_name(name, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None


def style_for(token_type) -> str | None:
    """Pygments-Tokentyp -> Anzeigeklasse (oder None für normalen Text)."""
    if token_type in Comment or token_type in Comment.Preproc:
        return "comment"
    if token_type in String or token_type in Literal.String.Doc:
        return "string"
    if token_type in Number:
        return "number"
    if token_type in Keyword or token_type in Name.Builtin:
        return "keyword"
    if token_type in Name.Function or token_type in Name.Class or token_type in Name.Decorator:
        return "function"
    if token_type in Name.Tag:
        return "tag"
    if token_type in Name.Attribute or token_type in Name.Variable:
        return "attribute"
    if token_type in Operator:
        return "operator"
    if token_type in Token.Generic.Heading or token_type in Token.Generic.Subheading:
        return "keyword"
    if token_type in Token.Generic.Emph or token_type in Token.Generic.Strong:
        return "attribute"
    return None


def _ends_in(text: str, marker: str, opened: bool) -> bool:
    """Bleibt nach `text` ein mit `marker` geöffneter Bereich offen?"""
    count = text.count(marker)
    return (count % 2 == 1) != opened if marker != "/*" else _block_comment_open(text, opened)


def _block_comment_open(text: str, opened: bool) -> bool:
    pos = 0
    state = opened
    while True:
        if state:
            close = text.find("*/", pos)
            if close < 0:
                return True
            state, pos = False, close + 2
        else:
            open_ = text.find("/*", pos)
            if open_ < 0:
                return False
            state, pos = True, open_ + 2


def lex_line(text: str, lexer_name: str | None, prev_state: int = STATE_NONE) -> tuple[list[Span], int]:
    """Spans einer Zeile und der Zustand am Zeilenende."""
    if lexer_name is None:
        return [], STATE_NONE
    if lexer_name == "log":
        return lex_log_line(text), STATE_NONE
    if lexer_name == "markdown":
        return _lex_markdown_line(text, prev_state)
    return _lex_code_line(text, lexer_name, prev_state)


def _lex_code_line(text: str, lexer_name: str, prev_state: int) -> tuple[list[Span], int]:
    lexer = _lexer(lexer_name)
    if lexer is None:
        return [], STATE_NONE
    prefix = _OPENERS.get(prev_state, "")
    spans: list[Span] = []
    pos = 0
    # Viele Lexer-Regeln (z. B. Markdown-Überschriften) brauchen das Zeilenende – deshalb "\n" anhängen
    for token_type, value in lexer.get_tokens(prefix + text + "\n"):
        length = len(value)
        start, end = pos - len(prefix), pos + length - len(prefix)
        pos += length
        if end <= 0:
            continue
        style = style_for(token_type)
        if style is not None:
            spans.append(Span(max(0, start), min(len(text), end), style))
    # Zustand am Zeilenende bestimmen
    state = STATE_NONE
    if lexer_name == "python":
        if _ends_in(text, '"""', prev_state == STATE_TRIPLE_DQ):
            state = STATE_TRIPLE_DQ
        elif _ends_in(text, "'''", prev_state == STATE_TRIPLE_SQ):
            state = STATE_TRIPLE_SQ
    elif lexer_name in _C_LIKE:
        if _block_comment_open(text, prev_state == STATE_BLOCK_COMMENT):
            state = STATE_BLOCK_COMMENT
    return _merge(spans), state


def _lex_markdown_line(text: str, prev_state: int) -> tuple[list[Span], int]:
    """Markdown selbst über Pygments; Codeblöcke mit Sprache über deren Lexer."""
    fence = _FENCE_RE.match(text)
    if prev_state >= STATE_FENCE_LANG_BASE or prev_state == STATE_FENCE:
        if fence:
            return [Span(0, len(text), "comment")], STATE_NONE
        lang = FENCE_LANGS[prev_state - STATE_FENCE_LANG_BASE] if prev_state >= STATE_FENCE_LANG_BASE else ""
        if lang and _lexer(lang) is not None:
            spans, _ = _lex_code_line(text, lang, STATE_NONE)
            return spans, prev_state
        return [Span(0, len(text), "string")], prev_state
    if fence:
        lang = fence.group(2).lower()
        lang = {"py": "python", "js": "javascript", "sh": "bash", "shell": "bash", "yml": "yaml", "ps": "powershell",
                "cmd": "batch"}.get(lang, lang)
        state = STATE_FENCE_LANG_BASE + FENCE_LANGS.index(lang) if lang in FENCE_LANGS else STATE_FENCE
        return [Span(0, len(text), "comment")], state
    spans, _ = _lex_code_line(text, "markdown", STATE_NONE)
    return spans, STATE_NONE


_LOG_PATTERNS = [
    ("log_time", re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b|\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b|\b\d{2}\.\d{2}\.\d{4}\b")),
    ("log_error", re.compile(r"\b(ERROR|FATAL|CRITICAL|SEVERE|ERR|E)\b|\bException\b|\bTraceback\b")),
    ("log_warn", re.compile(r"\b(WARN|WARNING|W)\b")),
    ("log_info", re.compile(r"\b(INFO|NOTICE|I)\b")),
    ("log_debug", re.compile(r"\b(DEBUG|TRACE|VERBOSE|D)\b")),
    ("log_ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b|\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")),
    ("log_path", re.compile(r"(?:[A-Za-z]:\\|/)[^\s\"'<>|:*?]+")),
]


def lex_log_line(text: str) -> list[Span]:
    spans: list[Span] = []
    taken = [False] * len(text)
    for style, pattern in _LOG_PATTERNS:
        for m in pattern.finditer(text):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            spans.append(Span(m.start(), m.end(), style))
    return sorted(spans, key=lambda s: s.start)


def _merge(spans: list[Span]) -> list[Span]:
    """Benachbarte Spans gleicher Klasse zusammenfassen (weniger setFormat-Aufrufe)."""
    merged: list[Span] = []
    for span in spans:
        if merged and merged[-1].style == span.style and merged[-1].end == span.start:
            merged[-1] = Span(merged[-1].start, span.end, span.style)
        else:
            merged.append(span)
    return merged
