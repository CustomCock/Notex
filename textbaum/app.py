"""Startet die Anwendung: Config laden, Theme setzen, Hauptfenster zeigen."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from textbaum import APP_NAME
from textbaum.core.config import load_config, save_config
from textbaum.paths import config_path, data_dir
from textbaum.theme.theme import load_stylesheet
from textbaum.ui.main_window import MainWindow


def run() -> int:
    data_dir()  # legt data/ an, falls es fehlt
    config = load_config(config_path())

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")  # neutraler Basis-Stil, auf dem das QSS sauber aufsetzt
    app.setStyleSheet(load_stylesheet())

    window = MainWindow(config, on_save_config=lambda cfg: save_config(config_path(), cfg))
    window.show()
    return app.exec()
