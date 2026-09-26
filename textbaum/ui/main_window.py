"""Hauptfenster: Splitter mit Seitenleiste links und Editorbereich rechts."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QWidget

from textbaum import APP_NAME
from textbaum.ui.winapi import apply_dark_titlebar


class MainWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], on_save_config) -> None:
        super().__init__()
        self.config = config
        self._save_config = on_save_config
        self.setWindowTitle(APP_NAME)

        # Platzhalter, werden in Phase 2/3 durch echte Widgets ersetzt
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.editor_area = QLabel("Noch keine Datei geöffnet")
        self.editor_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.editor_area)
        self.splitter.setStretchFactor(0, 0)  # Seitenleiste behält ihre Breite
        self.splitter.setStretchFactor(1, 1)  # Editor bekommt den Rest
        self.setCentralWidget(self.splitter)

        self._restore_window_state()

    # ---- Zustand ----------------------------------------------------------
    def _restore_window_state(self) -> None:
        win = self.config["window"]
        self.resize(win["width"], win["height"])
        if win["x"] is not None and win["y"] is not None:
            self.move(win["x"], win["y"])
        if win["maximized"]:
            self.showMaximized()

        side = self.config["sidebar"]
        self.splitter.setSizes([side["width"], max(200, win["width"] - side["width"])])

    def _collect_window_state(self) -> None:
        win = self.config["window"]
        win["maximized"] = self.isMaximized()
        if not self.isMaximized():
            # normalGeometry = Größe/Position im nicht-maximierten Zustand
            geo = self.normalGeometry()
            win["x"], win["y"], win["width"], win["height"] = geo.x(), geo.y(), geo.width(), geo.height()
        sizes = self.splitter.sizes()
        if sizes and sizes[0] > 0:
            self.config["sidebar"]["width"] = sizes[0]

    def save_state(self) -> None:
        self._collect_window_state()
        self._save_config(self.config)

    # ---- Qt-Events --------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Das Fenster-Handle (HWND) existiert erst, wenn das Fenster sichtbar wird.
        apply_dark_titlebar(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.save_state()
        event.accept()
