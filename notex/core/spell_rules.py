"""Welche Wörter die Rechtschreibprüfung überhaupt anschaut – ohne Qt, damit es testbar ist.

tokenize() zerlegt eine Zeile in Wörter mit Position und lässt alles weg, was kein
Prosa-Wort ist: URLs, E-Mail-Adressen, Dateipfade, Hex/Hashes, Wörter mit Ziffern,
ALLCAPS-Abkürzungen, CamelCase/snake_case, Inline-Code in Backticks.
Markdown-Codeblöcke (```) behandelt der Aufrufer über den Block-Zustand (in_code_fence).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Was im Vorfeld komplett ausgeblendet wird (Reihenfolge: zuerst die "großen" Muster)
_SKIP_SPANS = re.compile(
    r"`[^`]*`"                                   # Inline-Code
    r"|https?://\S+|www\.\S+|ftp://\S+"          # URLs
    r"|[\w.+-]+@[\w-]+\.[\w.-]+"                 # E-Mail
    r"|(?:[A-Za-z]:\\|\\\\|~?/|\./|\.\./)[^\s\"'<>|]+"   # Pfade: C:\..., \\server, /usr/..., ./x, ../x
    r"|(?<![\w/])(?:\w+/)+\w[\w.-]*"             # relative Pfade mit Schrägstrich: a/b/c.txt
    r"|\b(?:0x)?[0-9a-fA-F]{7,}\b"               # Hashes/Hex ab 7 Zeichen
    r"|\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"   # UUID
)
_WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|['’\-](?=[^\W\d_]))*", re.UNICODE)   # Buchstabenwort, innen ' oder -
_HAS_DIGIT = re.compile(r"\d")
_CAMEL = re.compile(r"^[a-zäöüß]+[A-ZÄÖÜ]|^[A-ZÄÖÜ][a-zäöüß]+[A-ZÄÖÜ]")   # notexApp, NotexApp
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


def is_code_fence(line: str) -> bool:
    return bool(_FENCE.match(line))


def should_check(word: str) -> bool:
    """Prosa-Wort? Abkürzungen, CamelCase, snake_case, Ziffern usw. fallen raus."""
    if len(word) < 2:
        return False
    if _HAS_DIGIT.search(word):
        return False
    if word.isupper():                       # ALLCAPS (auch "GPL", "HTTP"); Einzelbuchstabe schon oben raus
        return False
    if "_" in word or _CAMEL.search(word):
        return False
    return True


def tokenize(line: str, markdown: bool = False) -> list[Token]:
    """Alle prüfwürdigen Wörter einer Zeile mit Start-/Endposition.

    `markdown` lässt zusätzlich Zeilen weg, die Bilder/Links-Ziele enthalten könnten? Nein –
    Markdown-spezifisch ist nur der Codeblock-Zustand, den der Aufrufer hält. Der Parameter
    bleibt für künftige Regeln (z. B. Frontmatter) reserviert.
    """
    del markdown
    # Ausgeblendete Bereiche durch Leerzeichen ersetzen, damit die Positionen stimmen
    masked = _SKIP_SPANS.sub(lambda m: " " * len(m.group(0)), line)
    # Wortläufe mit Unterstrich oder Ziffer komplett maskieren (snake_case, _privat, abc123, v2),
    # sonst würde z. B. "abc" aus "abc123" einzeln geprüft
    masked = re.sub(r"\w+", lambda m: " " * len(m.group(0)) if ("_" in m.group(0) or _HAS_DIGIT.search(m.group(0))) else m.group(0), masked)
    tokens: list[Token] = []
    for match in _WORD.finditer(masked):
        word = match.group(0)
        if should_check(word):
            tokens.append(Token(word, match.start(), match.end()))
    return tokens
