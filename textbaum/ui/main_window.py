"""Hauptfenster: Seitenleiste links, Editor-Tabs rechts, Menü und Shortcuts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QMainWindow, QSplitter

from textbaum import APP_NAME
from textbaum.ui.editor_tabs import EditorTabs
from textbaum.ui.sidebar import Sidebar
from textbaum.ui.winapi import apply_dark_titlebar


class MainWindow(QMainWindow):
    def __init__(self, root: Path, config: dict[str, Any], on_save_config) -> None:
        super().__init__()
        self.root = root
        self.config = config
        self._save_config = on_save_config
        self.setWindowTitle(APP_NAME)

        self.sidebar = Sidebar(root, config["extensions"])
        self.tabs = EditorTabs(root)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 0)  # Seitenleiste behält ihre Breite
        self.splitter.setStretchFactor(1, 1)  # Editor bekommt den Rest
        self.splitter.setCollapsible(1, False)
        self.setCentralWidget(self.splitter)

        self.sidebar.tree.file_activated.connect(self.tabs.open_file)
        self.tabs.status_changed.connect(self._update_title)

        self._build_menu()
        self._restore_window_state()

    # ---- Menü & Shortcuts ---------------------------------------------------
    def _action(self, text: str, shortcut: str | QKeySequence.StandardKey | None, slot) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        self.addAction(action)  # damit der Shortcut auch ohne sichtbares Menü greift
        return action

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Datei")
        file_menu.addAction(self._action("Speichern", QKeySequence.StandardKey.Save, self.tabs.save_current))
        file_menu.addAction(self._action("Alle speichern", "Ctrl+Shift+S", self.tabs.save_all))
        file_menu.addAction(self._action("Tab schließen", "Ctrl+W", self.tabs.close_current))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Beenden", "Ctrl+Q", self.close))

    def _update_title(self) -> None:
        editor = self.tabs.current_editor()
        if editor is None:
            self.setWindowTitle(APP_NAME)
            return
        mark = "● " if editor.is_dirty else ""
        self.setWindowTitle(f"{mark}{self.tabs.relative(editor.path)} – {APP_NAME}")

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

        for rel in self.config["open_tabs"]:
            path = self.root / rel
            if path.is_file():
                self.tabs.open_file(path)
        if 0 <= self.config["active_tab"] < self.tabs.count():
            self.tabs.setCurrentIndex(self.config["active_tab"])

    def _collect_window_state(self) -> None:
        win = self.config["window"]
        win["maximized"] = self.isMaximized()
        if not self.isMaximized():
            geo = self.normalGeometry()  # Größe/Position im nicht-maximierten Zustand
            win["x"], win["y"], win["width"], win["height"] = geo.x(), geo.y(), geo.width(), geo.height()
        sizes = self.splitter.sizes()
        if sizes and sizes[0] > 0:
            self.config["sidebar"]["width"] = sizes[0]
        self.config["open_tabs"] = self.tabs.open_paths()
        self.config["active_tab"] = max(0, self.tabs.currentIndex())

    def save_state(self) -> None:
        self._collect_window_state()
        self._save_config(self.config)

    # ---- Qt-Events --------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_dark_titlebar(self)  # das HWND existiert erst, wenn das Fenster sichtbar wird

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.tabs.confirm_close_all():
            event.ignore()
            return
        self.save_state()
        event.accept()
