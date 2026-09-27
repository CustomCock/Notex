"""Vorlagen für „Neue Datei nach Typ" – ohne Qt, damit Startinhalt und Zeilenenden testbar sind.

Jeder Typ hat eine Endung, ein Icon, einen kurzen Startinhalt und – optional – die Cursor-Position
im Startinhalt (Marker ``§|``). `build_content` normalisiert Zeilenenden und kodiert den Text.
"""
from __future__ import annotations

from dataclasses import dataclass

CURSOR = "§|"     # markiert im Startinhalt, wo der Cursor stehen soll (wird vor dem Schreiben entfernt)

EOLS: dict[str, str] = {"lf": "\n", "crlf": "\r\n"}
EOL_LABELS: list[tuple[str, str]] = [("lf", "LF (Unix/Linux/macOS)"), ("crlf", "CRLF (Windows)")]


@dataclass(frozen=True)
class NewFileType:
    key: str
    label: str
    extension: str
    icon: str
    starter: str = ""
    description: str = ""


TYPES: list[NewFileType] = [
    NewFileType("text", "Textdatei", ".txt", "file-text", "§|", "Leere Textdatei"),
    NewFileType("markdown", "Markdown-Notiz", ".md", "heading", "# §|\n\n", "Notiz mit Überschrift"),
    NewFileType("csv", "CSV-Tabelle", ".csv", "table", "Spalte 1,Spalte 2,Spalte 3\n§|", "Tabelle mit Kopfzeile"),
    NewFileType("json", "JSON-Datei", ".json", "braces", "{\n  \"§|\": \"\"\n}\n", "Leeres JSON-Objekt"),
    NewFileType("yaml", "YAML-Datei", ".yaml", "braces", "§|: \n", "YAML-Schlüssel/Wert"),
    NewFileType("html", "HTML-Seite", ".html", "code",
                "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n  <meta charset=\"utf-8\">\n"
                "  <title>§|</title>\n</head>\n<body>\n\n</body>\n</html>\n", "HTML-Grundgerüst"),
    NewFileType("python", "Python-Skript", ".py", "code", "#!/usr/bin/env python3\n\n§|\n", "Python mit Shebang"),
    NewFileType("shell", "Shell-Skript", ".sh", "code", "#!/usr/bin/env bash\nset -euo pipefail\n\n§|\n",
                "Bash mit sicheren Voreinstellungen"),
    NewFileType("ini", "INI-Konfiguration", ".ini", "settings", "[§|]\n", "INI mit erstem Abschnitt"),
]
BY_KEY = {t.key: t for t in TYPES}


def default_extension(key: str) -> str:
    ftype = BY_KEY.get(key)
    return ftype.extension if ftype else ".txt"


def suggested_name(key: str) -> str:
    """Vorschlag für den Dateinamen im Anlegen-Dialog."""
    return "Neu" + default_extension(key)


def cursor_offset(starter: str) -> int:
    """Zeichen-Offset des Cursors im (bereinigten) Startinhalt; 0, wenn kein Marker."""
    index = starter.find(CURSOR)
    return index if index >= 0 else 0


def clean_starter(starter: str) -> str:
    """Startinhalt ohne Cursor-Marker (mit \n als Zeilenende – für den Editor)."""
    return starter.replace(CURSOR, "")


def build_content(starter: str, eol: str = "lf") -> str:
    """Startinhalt mit gewünschtem Zeilenende (ohne Cursor-Marker)."""
    text = clean_starter(starter)
    newline = EOLS.get(eol, "\n")
    # zuerst auf \n vereinheitlichen, dann auf das Ziel-Zeilenende
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline != "\n":
        text = text.replace("\n", newline)
    return text


def encode_content(starter: str, eol: str = "lf", encoding: str = "utf-8") -> bytes:
    return build_content(starter, eol).encode(encoding)
