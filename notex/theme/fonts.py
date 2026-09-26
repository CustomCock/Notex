"""Gebündelte Schriften laden (Inter für die UI, JetBrains Mono für den Editor).

Beide stehen unter der SIL Open Font License, die Lizenztexte liegen in assets/fonts/.
Fehlt eine Datei, greift Qt auf die Fallback-Familien aus tokens.py zurück.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from notex.theme.tokens import EDITOR_FONT_FAMILIES, FONT_SIZE, UI_FONT_FAMILIES

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def load_bundled_fonts() -> list[str]:
    """Registriert alle .ttf aus assets/fonts/. Gibt die geladenen Familiennamen zurück."""
    families: list[str] = []
    for ttf in sorted(FONT_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(ttf))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(set(families))


def ui_font(pixel_size: int = FONT_SIZE.ui, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(UI_FONT_FAMILIES)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def editor_font(pixel_size: int = FONT_SIZE.editor) -> QFont:
    font = QFont()
    font.setFamilies(EDITOR_FONT_FAMILIES)
    font.setPixelSize(pixel_size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    # Kein Zusammenquetschen: Qt darf Buchstaben nicht enger setzen als die Schrift vorgibt
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)
    return font
