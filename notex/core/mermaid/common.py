"""Gemeinsames für alle Mermaid-Diagrammtypen: Fehler, Ergebnis, Vorverarbeitung, Stil-Werte."""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_ELEMENTS = 400          # Schutz vor riesigen Diagrammen (Layout ist O(n²) an einigen Stellen)


class MermaidError(Exception):
    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line            # 1-basiert, bezogen auf den Mermaid-Block

    def __str__(self) -> str:
        return f"Zeile {self.line}: {self.message}" if self.line else self.message


@dataclass
class Diagram:
    kind: str
    svg: str
    width: float
    height: float
    title: str = ""


@dataclass
class Line:
    no: int          # 1-basiert
    text: str


_DIRECTIVE = re.compile(r"%%\{.*?\}%%", re.DOTALL)


def preprocess(source: str) -> tuple[list[Line], str]:
    """Frontmatter (--- title: … ---) und %%{init}%%-Direktiven entfernen, Kommentare (%%) streichen.
    Liefert die nicht leeren Zeilen (mit Originalnummer) und einen Frontmatter-Titel."""
    title = ""
    text = source.replace("\r\n", "\n").replace("\t", "    ")
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                for fm in lines[1:i]:
                    m = re.match(r"\s*title\s*:\s*(.+)$", fm)
                    if m:
                        title = m.group(1).strip().strip("\"'")
                start = i + 1
                break
    out = []
    for no, raw in enumerate(lines[start:], start + 1):
        raw = _DIRECTIVE.sub("", raw)
        stripped = raw.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        out.append(Line(no, raw.rstrip()))
    return out, title


def unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if text.startswith("`") and text.endswith("`"):          # Markdown-Strings: `**fett**` → Text
        text = text.strip("`").replace("**", "").replace("*", "").replace("_", " ").strip()
    return decode_entities(text)


_ENTITIES = {"quot": '"', "amp": "&", "lt": "<", "gt": ">", "nbsp": " ", "apos": "'", "semi": ";", "colon": ":"}


def decode_entities(text: str) -> str:
    """Mermaid-Entities (#quot; #35; #amp;) in Zeichen umwandeln."""
    def repl(m):
        body = m.group(1)
        if body.isdigit():
            try:
                return chr(int(body))
            except ValueError:
                return m.group(0)
        return _ENTITIES.get(body.lower(), m.group(0))
    return re.sub(r"#(\w+);", repl, text)


_SAFE_VALUE = re.compile(r"^[#\w\s.,%()\-]+$")


def parse_style(text: str) -> dict[str, str]:
    """„fill:#f9f,stroke:#333,stroke-width:4px,color:#fff“ → dict; nur harmlose Werte (keine url(), kein Quoting)."""
    out: dict[str, str] = {}
    for part in text.split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key, value = key.strip().lower(), value.strip().rstrip(";")
        if key in ("fill", "stroke", "color", "stroke-width", "stroke-dasharray", "font-weight") and \
                _SAFE_VALUE.match(value) and "url" not in value.lower():
            out[key] = value
    return out


def px(value: str, default: float) -> float:
    m = re.match(r"\s*([\d.]+)", value or "")
    return float(m.group(1)) if m else default
