"""ThemeManager: wendet ein Theme live an und sagt allen Bescheid.

Ablauf bei apply(): Tokens setzen -> QSS neu erzeugen und setzen -> Icon-Caches
leeren -> Signal `changed`. Widgets, die Farben oder Icons selbst zeichnen oder
beim Aufbau Abstände übernommen haben, hängen an `changed` und aktualisieren sich.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from notex.theme import icons, tokens
from notex.theme.fonts import ui_font
from notex.theme.theme import load_stylesheet
from notex.ui import anim


class ThemeManager(QObject):
    changed = Signal()

    def apply(self, theme: dict[str, Any]) -> dict[str, Any]:
        theme = tokens.apply_theme(theme)
        anim.set_reduced(not theme["animation"]["enabled"])
        icons.clear_cache()
        app = QApplication.instance()
        if app is not None:
            app.setFont(ui_font())
            app.setStyleSheet(load_stylesheet())
        self.changed.emit()
        return theme

    def current(self) -> dict[str, Any]:
        return tokens.active_theme()


_manager: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager
