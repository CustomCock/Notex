"""Variablen: Textbausteine wie §gruss, die in der Datei als Token stehen und im Editor als Wert erscheinen. Ohne Qt.

Regeln
- Token = Präfix (Standard „§“) + Name aus Buchstaben (auch Umlaute), Ziffern, Unterstrich. Das Token endet am ersten
  anderen Zeichen. Nur wenn dieser ganze Name definiert ist, ist es eine Variable – „§23a“ bei definiertem §23 ist
  normaler Text (Paragraphen!). Dadurch gewinnt bei Überschneidung automatisch der längste Name: „§234“ ist §234,
  nicht §23 + „4“.
- Escape: „\\§23“ ist ein bewusst entferntes Vorkommen – angezeigt als normales „§23“, ohne Backslash und Kennzeichnung.
  Escapes gelten nur für definierte Namen; alles Undefinierte ist ganz normaler Text.
- Keine Rekursion: Variablen in Variablenwerten werden nie aufgelöst.
- Die Datei enthält immer nur Tokens; aufgelöst wird ausschließlich im Speicher (auch bei .ntx).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PREFIX = "§"
ESCAPE = "\\"
DISPLAY_LIMIT = 80
_NAME = re.compile(r"^\w+$")


@dataclass
class Variable:
    name: str
    value: str
    description: str = ""


@dataclass(frozen=True)
class Token:
    start: int          # Index des Präfix – bzw. des Backslash bei einem Escape
    end: int            # exklusiv
    name: str
    escaped: bool = False

    @property
    def length(self) -> int:
        return self.end - self.start


def valid_name(name: str) -> bool:
    return bool(_NAME.match(name or ""))


def _pattern(prefix: str) -> re.Pattern:
    return re.compile(r"(\\)?" + re.escape(prefix) + r"(\w+)")


def find_tokens(text: str, names, prefix: str = DEFAULT_PREFIX) -> list[Token]:
    """Alle Variablen-Tokens und Escapes in `text` (nur definierte Namen)."""
    if not prefix or not names or prefix not in text:
        return []
    tokens = []
    for match in _pattern(prefix).finditer(text):
        name = match.group(2)
        if name not in names:
            continue
        tokens.append(Token(match.start(), match.end(), name, match.group(1) is not None))
    return tokens


def token_at(tokens: list[Token], position: int, inclusive: bool = False) -> Token | None:
    """Token, in dem `position` liegt (echt innen; mit inclusive auch an den Rändern)."""
    for token in tokens:
        if token.start < position < token.end or (inclusive and token.start <= position <= token.end):
            return token
    return None


def display_value(value: str, limit: int = DISPLAY_LIMIT) -> str:
    """Einzeilige Anzeige eines Werts im Lesefluss: Zeilenumbrüche als „⏎“, lange Werte gekürzt."""
    single = value.replace("\r\n", "\n").replace("\n", " ⏎ ")
    return single if len(single) <= limit else single[:limit - 1] + "…"


def resolve(text: str, values: dict[str, str], prefix: str = DEFAULT_PREFIX, single_line: bool = False) -> str:
    """Tokens durch Werte ersetzen, Escapes als normales „§name“ – für Kopieren, Vorschau, Export, Suche."""
    tokens = find_tokens(text, values, prefix)
    if not tokens:
        return text
    out, last = [], 0
    for token in tokens:
        out.append(text[last:token.start])
        if token.escaped:
            out.append(prefix + token.name)
        else:
            value = values[token.name]
            out.append(value.replace("\r\n", " ").replace("\n", " ") if single_line else value)
        last = token.end
    out.append(text[last:])
    return "".join(out)


def resolve_with_line_map(text: str, values: dict[str, str], prefix: str = DEFAULT_PREFIX) -> tuple[str, list[int]]:
    """Wie resolve(), plus Zuordnung Zeile im Ergebnis → Zeile im Original (mehrzeilige Werte verschieben die
    Zeilennummern; die Vorschau braucht das z. B. zum Abhaken von Aufgaben)."""
    out_lines: list[str] = []
    mapping: list[int] = []
    for number, line in enumerate(text.split("\n")):
        resolved = resolve(line, values, prefix).split("\n")
        out_lines.extend(resolved)
        mapping.extend([number] * len(resolved))
    return "\n".join(out_lines), mapping


def escape_token(text: str, token: Token) -> str:
    """Ein Vorkommen „entfernen“: bleibt als Text, gespeichert als \\§name."""
    return text if token.escaped else text[:token.start] + ESCAPE + text[token.start:]


def unescape_token(text: str, token: Token) -> str:
    """„Wieder als Variable verwenden“: Backslash vor dem Präfix entfernen."""
    return text[:token.start] + text[token.start + 1:] if token.escaped else text


def replace_token(text: str, token: Token, values: dict[str, str]) -> str:
    """„Durch Wert ersetzen“: Token dauerhaft durch den aktuellen Wert ersetzen (Escapes bleiben unberührt)."""
    if token.escaped:
        return text
    return text[:token.start] + values[token.name] + text[token.end:]


def replace_all(text: str, values: dict[str, str], prefix: str = DEFAULT_PREFIX, start: int = 0,
                end: int | None = None) -> tuple[str, int]:
    """Alle Tokens im Bereich durch ihre Werte ersetzen. Gibt (neuer Text, Anzahl) zurück."""
    end = len(text) if end is None else end
    tokens = [t for t in find_tokens(text, values, prefix) if not t.escaped and t.start >= start and t.end <= end]
    for token in reversed(tokens):
        text = replace_token(text, token, values)
    return text, len(tokens)


def escape_all(text: str, names, prefix: str = DEFAULT_PREFIX, start: int = 0, end: int | None = None) -> tuple[str, int]:
    """„Variablen in Auswahl entfernen“: alle Tokens im Bereich zu literalem Text (Escape)."""
    end = len(text) if end is None else end
    tokens = [t for t in find_tokens(text, names, prefix) if not t.escaped and t.start < end and t.end > start]
    for token in reversed(tokens):
        text = escape_token(text, token)
    return text, len(tokens)


def completions(typed: str, variables: list[Variable], limit: int = 40) -> list[tuple[str, str]]:
    """Vorschläge nach dem Präfix: (Name, gekürzter Wert) – erst Namen, die mit dem Getippten beginnen, dann enthaltene."""
    typed_low = typed.casefold()
    starts = [v for v in variables if v.name.casefold().startswith(typed_low)]
    contains = [v for v in variables if typed_low and typed_low in v.name.casefold() and v not in starts]
    ordered = sorted(starts, key=lambda v: (len(v.name), v.name.casefold())) + sorted(contains, key=lambda v: v.name.casefold())
    return [(v.name, display_value(v.value, 50)) for v in ordered[:limit]]


def typed_name_before(line: str, column: int, prefix: str = DEFAULT_PREFIX) -> str | None:
    """Angefangener Name direkt vor dem Cursor („… §gr|“ → „gr“), sonst None. Nicht nach einem Escape."""
    before = line[:column]
    match = re.search(re.escape(prefix) + r"(\w*)$", before)
    if match is None:
        return None
    if match.start() > 0 and before[match.start() - 1] == ESCAPE:
        return None
    return match.group(1)


# ---- Speicherung -----------------------------------------------------------------------------------
def parse_variables(data) -> list[Variable]:
    """JSON-Inhalt → Variablen. Akzeptiert {"variables": [{name, value, description}]} und {name: value}.
    Ungültige Namen werden übersprungen, doppelte Namen: der letzte gewinnt."""
    entries = []
    if isinstance(data, dict) and isinstance(data.get("variables"), list):
        for item in data["variables"]:
            if isinstance(item, dict):
                entries.append((item.get("name"), item.get("value", ""), item.get("description", "")))
    elif isinstance(data, dict):
        entries = [(name, value, "") for name, value in data.items()]
    result: dict[str, Variable] = {}
    for name, value, description in entries:
        if isinstance(name, str) and valid_name(name) and isinstance(value, str):
            result[name] = Variable(name, value, description if isinstance(description, str) else "")
    return list(result.values())


def dump_variables(variables: list[Variable]) -> str:
    payload = {"version": 1, "variables": [{"name": v.name, "value": v.value, "description": v.description}
                                           for v in sorted(variables, key=lambda v: v.name.casefold())]}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def load_variables(path: Path) -> list[Variable]:
    try:
        return parse_variables(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def save_variables(path: Path, variables: list[Variable]) -> None:
    """Atomar schreiben (Temp-Datei + os.replace) – ein Absturz hinterlässt nie eine halbe Datei."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".variables-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(dump_variables(variables))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
