"""Startet die Anwendung: Config laden, Fonts + Theme setzen, Hauptfenster zeigen."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QLibraryInfo, QLocale, QObject, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from notex import APP_NAME
from notex.core.config import load_config, save_config
from notex.paths import config_path, data_dir
from notex.theme.fonts import load_fonts, ui_font
from notex.theme.manager import theme_manager
from notex.theme.theme import load_stylesheet
from notex.ui.main_window import MainWindow
from notex.ui.winapi import apply_dark_titlebar


class _DarkDialogs(QObject):
    """Sorgt dafür, dass auch Dialoge (Nachfragen, Eingaben) eine dunkle Titelleiste bekommen."""

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QDialog):
            apply_dark_titlebar(watched)
        return False


def create_app(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")  # neutraler Basis-Stil, auf dem das QSS sauber aufsetzt
    # Qt-eigene Beschriftungen (OK / Abbrechen in Eingabedialogen) auf Deutsch, falls vorhanden
    translator = QTranslator(app)
    if translator.load(QLocale("de"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    load_fonts()            # Inter + JetBrains Mono aus assets/fonts/, eigene aus fonts/user/
    app.setFont(ui_font())
    app.setStyleSheet(load_stylesheet())
    icon_path = Path(__file__).resolve().parent / "assets" / "notex.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app._dark_dialogs = _DarkDialogs(app)  # Referenz halten, sonst räumt Python den Filter weg
    app.installEventFilter(app._dark_dialogs)
    return app


def create_window() -> MainWindow:
    root = data_dir()  # legt data/ an, falls es fehlt
    config = load_config(config_path())
    config["theme"] = theme_manager().apply(config["theme"])   # Tokens + QSS aus dem gespeicherten Theme
    return MainWindow(root, config, on_save_config=lambda cfg: save_config(config_path(), cfg))


def run() -> int:
    app = create_app(sys.argv)
    window = create_window()
    window.show()
    return app.exec()
