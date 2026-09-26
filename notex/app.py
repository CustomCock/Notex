"""Startet die Anwendung: Config laden, Theme setzen, Hauptfenster zeigen."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from notex import APP_NAME
from notex.core.config import load_config, save_config
from notex.paths import config_path, data_dir
from notex.theme.theme import load_stylesheet
from notex.ui.main_window import MainWindow


def run() -> int:
    root = data_dir()  # legt data/ an, falls es fehlt
    config = load_config(config_path())

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")  # neutraler Basis-Stil, auf dem das QSS sauber aufsetzt
    app.setStyleSheet(load_stylesheet())
    icon_path = Path(__file__).resolve().parent / "assets" / "notex.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow(root, config, on_save_config=lambda cfg: save_config(config_path(), cfg))
    window.show()
    return app.exec()
