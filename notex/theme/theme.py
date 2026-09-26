"""Stylesheet aus den Tokens erzeugen und kleine Styling-Helfer.

dark.qss enthält Platzhalter wie `@bg`, `@sp_md`, `@r_control`, `@fs_ui`, die hier
durch die Werte aus tokens.py ersetzt werden. So gibt es im QSS keine Magic Numbers.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QMenu, QWidget
from PySide6.QtGui import QColor

from notex.theme.fonts import editor_font  # noqa: F401 – Re-Export für bestehende Importe
from notex.theme.tokens import COLORS, RADIUS, SPACING, flat_tokens

# Lazy + Lookahead: `@fs_uipx` -> Token "fs_ui" + Einheit "px", `@text_muted;` -> "text_muted"
_TOKEN = re.compile(r"@([a-z_]+?)(?=px\b|\b)")


def load_stylesheet() -> str:
    qss = (Path(__file__).parent / "dark.qss").read_text(encoding="utf-8")
    tokens = flat_tokens()
    # Unbekannte Platzhalter bleiben stehen, damit man den Tippfehler im QSS sieht
    return _TOKEN.sub(lambda m: tokens.get(m.group(1), m.group(0)), qss)


def add_shadow(widget: QWidget, blur: int = 24, offset_y: int = 6, alpha: int = 110) -> QGraphicsDropShadowEffect:
    """Weicher Schatten für kleine Widgets (Menüs, Toast). Für große Flächen wie das
    Blatt zeichnen wir den Schatten selbst – ein Effekt würde jeden Tastendruck bremsen."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, offset_y)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return effect


def style_menu(menu: QMenu) -> QMenu:
    """Abgerundetes Menü mit Schatten. Braucht ein transparentes Fenster, sonst
    bleiben hinter den runden Ecken Windows-graue Pixel stehen."""
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    add_shadow(menu, blur=20, offset_y=4, alpha=120)
    return menu


__all__ = ["COLORS", "RADIUS", "SPACING", "add_shadow", "editor_font", "load_stylesheet", "style_menu"]
