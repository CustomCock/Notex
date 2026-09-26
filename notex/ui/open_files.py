"""Seitenleisten-Bereich „Geöffnet“: externe Dateien (außerhalb von data/), einklappbar, verschwindet wenn leer."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu, QToolButton, QVBoxLayout, QWidget

from notex.core.recent import shorten_path
from notex.theme.icons import icon
from notex.theme.theme import style_menu
from notex.theme.tokens import LAYOUT, SPACING

ROLE_PATH = Qt.ItemDataRole.UserRole + 1


class OpenFilesSection(QWidget):
    activated = Signal(Path)
    copy_requested = Signal(Path)
    move_requested = Signal(Path)
    reveal_requested = Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("OpenFiles")
        self.expanded = True
        self.header = QToolButton()
        self.header.setObjectName("SectionHeader")
        self.header.setText("Geöffnet")
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setIconSize(QSize(12, 12))
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.header.clicked.connect(self.toggle)
        self.list = QListWidget()
        self.list.setObjectName("OpenFilesList")
        self.list.setIconSize(QSize(16, 16))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemClicked.connect(lambda item: self.activated.emit(Path(item.data(ROLE_PATH))))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)
        layout.addWidget(self.header)
        layout.addWidget(self.list)
        self._update_icon()
        self.hide()

    def set_files(self, paths: list[Path]) -> None:
        self.list.clear()
        for path in paths:
            item = QListWidgetItem(icon("external-link"), shorten_path(path, 40))
            item.setData(ROLE_PATH, str(path))
            item.setToolTip(str(path))
            self.list.addItem(item)
        rows = len(paths)
        self.list.setFixedHeight(min(rows, 6) * (LAYOUT.tree_row_height - 2) + 6)
        self.setVisible(rows > 0)
        self.header.setText(f"Geöffnet ({rows})")

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.list.setVisible(self.expanded)
        self._update_icon()

    def _update_icon(self) -> None:
        self.header.setIcon(icon("chevron-down" if self.expanded else "chevron-right"))

    def retheme(self) -> None:
        self._update_icon()
        for i in range(self.list.count()):
            self.list.item(i).setIcon(icon("external-link"))

    def _context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        path = Path(item.data(ROLE_PATH))
        menu = style_menu(QMenu(self))
        menu.addAction(icon("copy"), "In data/ kopieren", lambda: self.copy_requested.emit(path))
        menu.addAction(icon("folder-plus"), "In data/ verschieben", lambda: self.move_requested.emit(path))
        menu.addSeparator()
        menu.addAction(icon("external-link"), "Im Explorer anzeigen", lambda: self.reveal_requested.emit(path))
        menu.exec(self.list.viewport().mapToGlobal(pos))
