"""Hauptfenster: Seitenleiste links, Editor-Tabs rechts, Statusleiste, Menü und Shortcuts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSplitter, QToolButton, QVBoxLayout, QWidget

from textbaum import APP_NAME
from textbaum.core.encoding import read_text_file
from textbaum.ui.editor_tabs import EditorTabs
from textbaum.ui.file_watcher import OpenFileWatcher
from textbaum.ui.find_bar import FindBar
from textbaum.ui.sidebar import Sidebar
from textbaum.ui.status_bar import StatusBar
from textbaum.ui.winapi import apply_dark_titlebar


class MainWindow(QMainWindow):
    def __init__(self, root: Path, config: dict[str, Any], on_save_config) -> None:
        super().__init__()
        self.root = root
        self.config = config
        self._save_config = on_save_config
        self.setWindowTitle(APP_NAME)

        self.sidebar = Sidebar(root, config)
        self.tabs = EditorTabs(root)
        self.tabs.font_size = config["font_size"]
        self.tabs.word_wrap = config["word_wrap"]
        self.find_bar = FindBar(self.tabs.current_editor)
        self.status = StatusBar()
        self.setStatusBar(self.status)
        self.watcher = OpenFileWatcher()

        # Kleiner Button links neben den Tabs, der die Seitenleiste ein-/ausklappt.
        # Er sitzt bewusst außerhalb der Seitenleiste, damit er auch sichtbar ist, wenn sie weg ist.
        self.sidebar_button = QToolButton()
        self.sidebar_button.setObjectName("FlatButton")
        self.sidebar_button.setText("☰")
        self.sidebar_button.setToolTip("Seitenleiste ein-/ausblenden (Ctrl+B)")
        self.sidebar_button.clicked.connect(self.toggle_sidebar)
        self.tabs.setCornerWidget(self.sidebar_button, Qt.Corner.TopLeftCorner)

        # Rechte Seite: Tabs oben, darunter (ausblendbar) die Suchen/Ersetzen-Leiste
        editor_area = QWidget()
        editor_layout = QVBoxLayout(editor_area)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self.tabs, 1)
        editor_layout.addWidget(self.find_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(editor_area)
        self.splitter.setStretchFactor(0, 0)  # Seitenleiste behält ihre Breite
        self.splitter.setStretchFactor(1, 1)  # Editor bekommt den Rest
        self.splitter.setCollapsible(1, False)
        self.setCentralWidget(self.splitter)

        self._connect_signals()
        self._build_menu()
        self._restore_window_state()

    def _connect_signals(self) -> None:
        tree = self.sidebar.tree
        self.sidebar.open_requested.connect(self._open_from_sidebar)
        tree.path_renamed.connect(self._on_path_renamed)
        tree.path_deleted.connect(self.tabs.close_paths_under)

        self.tabs.status_changed.connect(self._update_status)
        self.tabs.currentChanged.connect(lambda _i: self.find_bar.refresh_highlight())
        self.tabs.font_size_changed.connect(lambda size: self.config.__setitem__("font_size", size))
        self.tabs.file_opened.connect(self.watcher.watch)
        self.tabs.file_closed.connect(self.watcher.unwatch)
        self.tabs.file_saved.connect(self.watcher.mark_saved)
        self.watcher.file_changed_externally.connect(self._on_external_change)
        self.watcher.file_removed_externally.connect(self._on_external_remove)

    # ---- Menü & Shortcuts ---------------------------------------------------
    def _action(self, text: str, shortcut, slot, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self.addAction(action)  # damit der Shortcut auch ohne offenes Menü greift
        return action

    def _build_menu(self) -> None:
        tree = self.sidebar.tree
        file_menu = self.menuBar().addMenu("&Datei")
        file_menu.addAction(self._action("Neue Datei", "Ctrl+N", lambda: tree.create_file(tree._folder_for(tree.selected_path()))))
        file_menu.addAction(self._action("Neuer Ordner", "Ctrl+Shift+N", lambda: tree.create_folder(tree._folder_for(tree.selected_path()))))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Speichern", QKeySequence.StandardKey.Save, self.tabs.save_current))
        file_menu.addAction(self._action("Alle speichern", "Ctrl+Shift+S", self.tabs.save_all))
        file_menu.addAction(self._action("Tab schließen", "Ctrl+W", self.tabs.close_current))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Beenden", "Ctrl+Q", self.close))

        edit_menu = self.menuBar().addMenu("&Bearbeiten")
        edit_menu.addAction(self._action("Suchen", QKeySequence.StandardKey.Find, lambda: self.find_bar.open(with_replace=False)))
        edit_menu.addAction(self._action("Ersetzen", "Ctrl+H", lambda: self.find_bar.open(with_replace=True)))

        view_menu = self.menuBar().addMenu("&Ansicht")
        self.sidebar_action = self._action("Seitenleiste", "Ctrl+B", self.toggle_sidebar, checkable=True)
        view_menu.addAction(self.sidebar_action)
        view_menu.addAction(self._action("Suche in Dateien", "Ctrl+Shift+F", self.focus_search))
        view_menu.addSeparator()
        self.wrap_action = self._action("Zeilenumbruch", "Alt+Z", self.toggle_word_wrap, checkable=True)
        self.wrap_action.setChecked(self.config["word_wrap"])
        view_menu.addAction(self.wrap_action)
        view_menu.addSeparator()
        view_menu.addAction(self._action("Vergrößern", QKeySequence.StandardKey.ZoomIn, lambda: self.tabs.zoom(+1)))
        view_menu.addAction(self._action("Verkleinern", QKeySequence.StandardKey.ZoomOut, lambda: self.tabs.zoom(-1)))
        view_menu.addAction(self._action("Zoom zurücksetzen", "Ctrl+0", lambda: self.tabs.set_font_size(11)))
        # Ctrl+Plus liegt je nach Tastatur auf "Ctrl+=" – beides abdecken
        self._action("Vergrößern (Alternative)", "Ctrl+=", lambda: self.tabs.zoom(+1))

    def toggle_word_wrap(self) -> None:
        enabled = not self.tabs.word_wrap
        self.tabs.set_word_wrap(enabled)
        self.wrap_action.setChecked(enabled)
        self.config["word_wrap"] = enabled

    def focus_search(self) -> None:
        if not self.sidebar.isVisible():
            self.set_sidebar_visible(True)
        self.sidebar.focus_search()

    def _open_from_sidebar(self, path: Path, location) -> None:
        """Öffnet eine Datei aus Baum oder Trefferliste; `location` = (Zeile, Spalte, Länge) oder None."""
        if location is None:
            self.tabs.open_file(path)
        else:
            line, column, length = location
            self.tabs.open_file(path, line=line, column=column, length=length)

    # ---- Seitenleiste ---------------------------------------------------------
    def toggle_sidebar(self) -> None:
        self.set_sidebar_visible(not self.sidebar.isVisible())

    def set_sidebar_visible(self, visible: bool) -> None:
        if not visible and self.sidebar.isVisible():
            sizes = self.splitter.sizes()
            if sizes and sizes[0] > 0:
                self.config["sidebar"]["width"] = sizes[0]  # Breite merken, bevor sie auf 0 geht
        self.sidebar.setVisible(visible)
        if visible:
            width = self.config["sidebar"]["width"]
            self.splitter.setSizes([width, max(200, self.width() - width)])
        self.sidebar_action.setChecked(visible)
        self.config["sidebar"]["visible"] = visible

    # ---- Reaktionen auf Baum / Watcher -----------------------------------------
    def _on_path_renamed(self, old: Path, new: Path) -> None:
        self.tabs.rename_open_file(old, new)
        # Watcher auf die neuen Pfade umhängen
        for editor in self.tabs.editors():
            if editor.path == new or new in editor.path.parents:
                self.watcher.watch(editor.path)
        self.watcher.unwatch(old)
        self._update_status()

    def _on_external_change(self, path: Path) -> None:
        editor = self.tabs.editor_for(path)
        if editor is None:
            return
        hint = "\nAchtung: Du hast ungespeicherte Änderungen, die dabei verloren gehen." if editor.is_dirty else ""
        answer = QMessageBox.question(
            self, "Datei extern geändert",
            f"„{self.tabs.relative(path)}“ wurde außerhalb von {APP_NAME} geändert.\nNeu laden?{hint}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                editor.replace_content(read_text_file(path))
            except OSError as error:
                QMessageBox.warning(self, "Neu laden fehlgeschlagen", str(error))
        else:
            editor.document().setModified(True)  # Inhalt weicht jetzt von der Platte ab
        self._update_status()

    def _on_external_remove(self, path: Path) -> None:
        editor = self.tabs.editor_for(path)
        if editor is None:
            return
        editor.document().setModified(True)  # Speichern legt die Datei wieder an
        self.status.showMessage(f"„{self.tabs.relative(path)}“ wurde extern gelöscht oder verschoben.", 8000)
        self._update_status()

    def _update_status(self) -> None:
        editor = self.tabs.current_editor()
        if editor is None:
            self.status.update_for(None, "")
            self.setWindowTitle(APP_NAME)
            return
        relative = self.tabs.relative(editor.path)
        self.status.update_for(editor, relative)
        self.setWindowTitle(f"{'● ' if editor.is_dirty else ''}{relative} – {APP_NAME}")

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
        self.set_sidebar_visible(side["visible"])
        self.sidebar.tree.restore_expanded(self.config["expanded_folders"])

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
        if self.sidebar.isVisible():
            sizes = self.splitter.sizes()
            if sizes and sizes[0] > 0:
                self.config["sidebar"]["width"] = sizes[0]
        self.config["sidebar"]["visible"] = self.sidebar.isVisible()
        self.config["expanded_folders"] = self.sidebar.tree.expanded_folders()
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
        self.sidebar.stop_search()
        self.save_state()
        event.accept()
