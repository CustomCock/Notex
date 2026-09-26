"""Farbpalette und Stylesheet.

Alle Farben stehen genau hier. Die QSS-Datei benutzt Platzhalter wie `@bg`,
die beim Laden durch die Werte aus COLORS ersetzt werden. So bleibt das
Styling an einem Ort statt über die Widgets verstreut.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtGui import QFont

COLORS = {
    "bg": "#121212",          # Fensterhintergrund
    "sidebar": "#181818",     # Seitenleiste
    "surface": "#232323",     # Flächen / Hover
    "border": "#2c2c2c",      # Rahmen
    "text": "#d0d0d0",        # Text
    "text_muted": "#8a8a8a",  # gedämpfter Text
    "selection": "#3a3a3a",   # Auswahl
    "accent": "#6b6b6b",      # sehr dezenter Akzent
    # Das "Blatt Papier"
    "paper": "#ffffff",
    "paper_text": "#1a1a1a",
    "paper_muted": "#9a9a9a",     # Zeilennummern
    "paper_line": "#f3f3f3",      # aktuelle Zeile
    "paper_gutter": "#fafafa",    # Hintergrund der Zeilennummern
    "paper_selection": "#cfe3ff", # Textauswahl im Blatt
    "paper_match": "#ffe58a",     # Suchtreffer-Markierung
}

# Bevorzugte Schriften in Reihenfolge; Qt nimmt die erste installierte.
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "monospace"]


def editor_font(point_size: int) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FAMILIES)
    font.setPointSize(point_size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def load_stylesheet() -> str:
    qss = (Path(__file__).parent / "dark.qss").read_text(encoding="utf-8")
    # `@name` -> Farbwert. Unbekannte Namen bleiben stehen, damit man den Tippfehler sieht.
    return re.sub(r"@([a-z_]+)", lambda m: COLORS.get(m.group(1), m.group(0)), qss)
