"""JSON und YAML: prüfen, formatieren, minimieren, als Baum darstellen. Ohne Qt.

- JSON wird token-basiert neu eingerückt: Zahlen (`1.10`, `1e5`), Escapes (`\\u00e4`) und die Reihenfolge der
  Schlüssel bleiben exakt wie in der Datei – nur Leerraum ändert sich. Geprüft wird vorher mit `json.loads`.
- YAML ausschließlich über `yaml.safe_load(_all)` / `yaml.safe_dump(_all)` (keine Python-Objekte, kein Code).
  Formatieren verwirft Kommentare und Anker → `yaml_has_comments()` für die Warnung vorher.
- Fehler kommen als ParseError mit Zeile/Spalte (1-basiert) und Zeichenposition für die Markierung im Text.
- Verschlüsselte Notizen (.ntx) haben keine Datenansicht; Formatieren im Speicher ist dort unkritisch, wird aber
  über `kind_for` gar nicht erst angeboten (Endung .ntx).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

JSON_SUFFIXES = (".json", ".geojson", ".ipynb", ".webmanifest")   # .jsonc (Kommentare) ist kein JSON
YAML_SUFFIXES = (".yaml", ".yml")
MAX_LIVE_CHARS = 2_000_000       # darüber keine Prüfung beim Tippen (nur auf Befehl)


def kind_for(path: Path | str) -> str | None:
    """"json", "yaml" oder None (auch für .ntx)."""
    name = str(path).lower()
    if name.endswith(JSON_SUFFIXES):
        return "json"
    if name.endswith(YAML_SUFFIXES):
        return "yaml"
    return None


@dataclass(frozen=True)
class ParseError:
    message: str
    line: int          # 1-basiert
    column: int        # 1-basiert
    position: int      # Zeichenindex im Text (für die Markierung)

    def short(self, kind: str) -> str:
        return f"{kind.upper()}-Fehler Z {self.line}, S {self.column}: {self.message}"


def _position(text: str, line: int, column: int) -> int:
    """Zeile/Spalte (1-basiert) → Zeichenindex, geklemmt auf den Text."""
    offset = 0
    for _ in range(line - 1):
        nxt = text.find("\n", offset)
        if nxt < 0:
            return len(text)
        offset = nxt + 1
    return min(len(text), offset + max(0, column - 1))


_JSON_MESSAGES = {
    "Expecting value": "Wert erwartet",
    "Expecting property name enclosed in double quotes": "Schlüssel in doppelten Anführungszeichen erwartet",
    "Expecting ',' delimiter": "Komma erwartet",
    "Expecting ':' delimiter": "Doppelpunkt erwartet",
    "Extra data": "Zusätzliche Daten nach dem Ende",
    "Unterminated string starting at": "Zeichenkette nicht geschlossen",
    "Invalid control character at": "Steuerzeichen in Zeichenkette",
    "Invalid \\escape": "Ungültige Escape-Sequenz",
    "Invalid \\uXXXX escape": "Ungültige \\u-Escape-Sequenz",
    "Illegal trailing comma before end of object": "Komma vor } nicht erlaubt",
    "Illegal trailing comma before end of array": "Komma vor ] nicht erlaubt",
}


def _parse_json(text: str):
    try:
        return json.loads(text), None
    except json.JSONDecodeError as error:
        message = _JSON_MESSAGES.get(error.msg, error.msg)
        return None, ParseError(message, error.lineno, error.colno, error.pos)
    except RecursionError:
        return None, ParseError("Zu tief verschachtelt", 1, 1, 0)


def _parse_yaml(text: str):
    import yaml
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark or error.context_mark
        line, column = (mark.line + 1, mark.column + 1) if mark is not None else (1, 1)
        message = (error.problem or error.context or "ungültiges YAML").strip()
        return None, ParseError(message, line, column, _position(text, line, column))
    except yaml.YAMLError as error:
        return None, ParseError(str(error).strip() or "ungültiges YAML", 1, 1, 0)
    except RecursionError:
        return None, ParseError("Zu tief verschachtelt", 1, 1, 0)
    return (documents[0] if len(documents) == 1 else documents), None


def parse(text: str, kind: str):
    """(Wert, None) oder (None, ParseError). YAML mit mehreren Dokumenten → Liste der Dokumente."""
    return _parse_json(text) if kind == "json" else _parse_yaml(text)


def validate(text: str, kind: str) -> ParseError | None:
    if not text.strip():
        return None if kind == "yaml" else ParseError("Leere Datei", 1, 1, 0)
    return parse(text, kind)[1]


# ---- JSON: token-basiert formatieren ---------------------------------------------------------
_JSON_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[{}\[\]:,]|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|\s+', re.S)


def _json_tokens(text: str) -> list[str]:
    tokens, position = [], 0
    while position < len(text):
        match = _JSON_TOKEN.match(text, position)
        if match is None:      # kann nach erfolgreichem json.loads nicht passieren (außer NaN/Infinity)
            end = position + 1
            while end < len(text) and not text[end].isspace() and text[end] not in "{}[]:,\"":
                end += 1
            tokens.append(text[position:end])
            position = end
            continue
        token = match.group(0)
        if not token.isspace():
            tokens.append(token)
        position = match.end()
    return tokens


def format_json(text: str, indent: int = 2) -> str:
    """Neu einrücken; wirft ValueError bei ungültigem JSON. Leere {} und [] bleiben kompakt."""
    _value, error = _parse_json(text)
    if error is not None:
        raise ValueError(error.short("json"))
    tokens = _json_tokens(text)
    pad = " " * max(0, indent) if indent > 0 else "\t"
    out: list[str] = []
    depth = 0
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in "{[" and i + 1 < len(tokens) and tokens[i + 1] == ("}" if token == "{" else "]"):
            out.append(token + tokens[i + 1])
            i += 2
            continue
        if token in "{[":
            depth += 1
            out.append(token + "\n" + pad * depth)
        elif token in "}]":
            depth -= 1
            out.append("\n" + pad * depth + token)
        elif token == ",":
            out.append(",\n" + pad * depth)
        elif token == ":":
            out.append(": ")
        else:
            out.append(token)
        i += 1
    return "".join(out) + ("\n" if text.endswith("\n") or not text else "")


def minify_json(text: str) -> str:
    _value, error = _parse_json(text)
    if error is not None:
        raise ValueError(error.short("json"))
    return "".join(_json_tokens(text)) + ("\n" if text.endswith("\n") else "")


# ---- YAML ------------------------------------------------------------------------------------
def yaml_has_comments(text: str) -> bool:
    """Gibt es Kommentare (# am Zeilenanfang oder nach Leerraum, nicht in Anführungszeichen)?
    Im Zweifel True – dann wird nur einmal zu viel gewarnt."""
    for line in text.split("\n"):
        quote = ""
        previous = " "
        for char in line:
            if quote:
                if char == quote:
                    quote = ""
            elif char in "\"'" and previous in " \t:,[{-":
                quote = char
            elif char == "#" and previous in " \t":
                return True
            previous = char
    return False


def _yaml_dump(value, indent: int, flow: bool, multi: bool) -> str:
    import yaml
    options = dict(allow_unicode=True, sort_keys=False, indent=max(2, min(indent, 9)),
                   default_flow_style=flow)
    if flow:
        options["width"] = float("inf")
    if multi:
        return yaml.safe_dump_all(value, explicit_start=True, **options)
    return yaml.safe_dump(value, **options)


def _yaml_documents(text: str):
    import yaml
    _value, error = _parse_yaml(text)
    if error is not None:
        raise ValueError(error.short("yaml"))
    return list(yaml.safe_load_all(text))


def format_yaml(text: str, indent: int = 2) -> str:
    documents = _yaml_documents(text)
    if len(documents) == 1:
        return _yaml_dump(documents[0], indent, False, False)
    return _yaml_dump(documents, indent, False, True)


def minify_yaml(text: str) -> str:
    documents = _yaml_documents(text)
    if len(documents) == 1:
        return _yaml_dump(documents[0], 2, True, False)
    return _yaml_dump(documents, 2, True, True)


def format_text(text: str, kind: str, indent: int = 2) -> str:
    return format_json(text, indent) if kind == "json" else format_yaml(text, indent)


def minify_text(text: str, kind: str) -> str:
    return minify_json(text) if kind == "json" else minify_yaml(text)


# ---- Baum ------------------------------------------------------------------------------------
_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def path_string(parts: list) -> str:
    """["users", 3, "name"] → "$.users[3].name"; Schlüssel mit Sonderzeichen → $["a b"]."""
    out = "$"
    for part in parts:
        if isinstance(part, int) and not isinstance(part, bool):
            out += f"[{part}]"
        elif isinstance(part, str) and _IDENTIFIER.match(part):
            out += f".{part}"
        else:
            out += "[" + json.dumps(str(part), ensure_ascii=False) + "]"
    return out


def type_name(value) -> str:
    if isinstance(value, dict):
        return "Objekt"
    if isinstance(value, list):
        return "Liste"
    if isinstance(value, bool):
        return "Wahrheitswert"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return "Zahl"
    if isinstance(value, str):
        return "Text"
    return type(value).__name__      # YAML: Datum, Zeitstempel, Bytes …


def preview(value, limit: int = 80) -> str:
    """Kurzdarstellung für die Wert-Spalte."""
    if isinstance(value, dict):
        return f"{{ {len(value)} }}"
    if isinstance(value, list):
        return f"[ {len(value)} ]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = text.replace("\n", "⏎")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def children(value) -> list[tuple[object, object]]:
    """(Schlüssel/Index, Wert) für Objekte und Listen, sonst leer."""
    if isinstance(value, dict):
        return list(value.items())
    if isinstance(value, list):
        return list(enumerate(value))
    return []
