"""Schriften: gebündelte (Inter, JetBrains Mono) plus eigene aus fonts/user/ neben der App.

Schrift-Konzept:
- Die gesamte Oberfläche benutzt EINE Schrift, nicht einstellbar. Reihenfolge:
  SF Pro Text / SF Pro Display (nur wenn der Nutzer sie selbst nach fonts/user/ legt;
  Apple-Lizenz, wird nie mitgeliefert) -> Inter (gebündelt, OFL) -> Segoe UI Variable -> Segoe UI.
- Einstellbar ist allein die Schrift des Textinhalts im Blatt. "" bzw. STANDARD steht für
  dieselbe Reihenfolge wie die Oberfläche. Textdateien haben keine Formatierung: die Schrift
  ist eine Ansichts-Einstellung und ändert nichts an der Datei.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from notex.theme.tokens import FONT_SIZE

BUNDLED_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
STANDARD = ""                       # Kennung für "Standardschrift" im Theme/Dropdown
STANDARD_LABEL = "Standard (SF Pro / Inter)"
SF_FAMILIES = ["SF Pro Text", "SF Pro Display", "SF Pro"]
FALLBACK_FAMILIES = ["Inter", "Segoe UI Variable", "Segoe UI", "Noto Sans", "sans-serif"]
MONO_FAMILIES = ["JetBrains Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]

_loaded: list[str] = []


def user_font_dir() -> Path:
    from notex.paths import app_root
    return app_root() / "fonts" / "user"


def load_fonts() -> list[str]:
    """Registriert alle .ttf/.otf aus assets/fonts/ und fonts/user/. Gibt die Familiennamen zurück."""
    families: list[str] = []
    folders = [BUNDLED_DIR]
    try:
        folders.append(user_font_dir())
    except Exception:  # noqa: BLE001 – ohne App-Root (Tests) nur die gebündelten
        pass
    for folder in folders:
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in (".ttf", ".otf"):
                font_id = QFontDatabase.addApplicationFont(str(path))
                if font_id >= 0:
                    families.extend(QFontDatabase.applicationFontFamilies(font_id))
    _loaded[:] = sorted(set(families))
    return list(_loaded)


def sf_available() -> bool:
    installed = set(QFontDatabase.families())
    return any(family in installed for family in SF_FAMILIES)


def ui_families() -> list[str]:
    """Auflösungsreihenfolge für die Oberfläche (und die Standard-Textschrift)."""
    return [f for f in SF_FAMILIES if f in set(QFontDatabase.families())] + FALLBACK_FAMILIES


def available_families() -> list[str]:
    """Für Dropdowns: gebündelte und eigene zuerst, dann alles Installierte."""
    installed = QFontDatabase.families()
    first = [f for f in _loaded if f in installed]
    return first + [f for f in installed if f not in first]


def _tune(font: QFont, pixel_size: int, tabular: bool = False) -> QFont:
    """Inter näher an SF Pro: tabellarische Ziffern wo sinnvoll, etwas engere Laufweite bei großen Größen."""
    font.setPixelSize(pixel_size)
    if tabular:
        try:
            font.setFeature(QFont.Tag("tnum"), 1)
        except (AttributeError, TypeError):
            pass
    if pixel_size >= 18:
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
    return font


def ui_font(pixel_size: int = FONT_SIZE.ui, weight: QFont.Weight = QFont.Weight.Normal, tabular: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(ui_families())
    font.setWeight(weight)
    return _tune(font, pixel_size, tabular)


def text_font(family: str, pixel_size: int) -> QFont:
    """Schrift für den Textinhalt: eine konkrete Familie oder STANDARD (= wie die Oberfläche)."""
    font = QFont()
    if family and family != STANDARD:
        font.setFamilies([family, *ui_families()])
    else:
        font.setFamilies(ui_families())
    font.setStyleHint(QFont.StyleHint.AnyStyle)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)
    return _tune(font, pixel_size)


def editor_font(pixel_size: int = FONT_SIZE.editor, family: str = STANDARD) -> QFont:
    return text_font(family, pixel_size)
