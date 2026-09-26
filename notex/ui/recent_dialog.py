"""Zuletzt geöffnet (Ctrl+R): Liste mit Filterfeld, Enter oder Doppelklick öffnet."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QVBoxLayout

from notex.core.recent import shorten_path
from notex.theme.icons import icon
from notex.theme.tokens import SPACING
from notex.ui.widgets import SearchField

ROLE_PATH = Qt.ItemDataRole.UserRole + 1


class RecentDialog(QDialog):
    def __init__(self, entries: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zuletzt geöffnet")
        self.setObjectName("RecentDialog")
        self.resize(560, 400)
        self.chosen: Path | None = None
        self.entries = entries
        self.filter = SearchField("Filtern …")
        self.filter.textChanged.connect(self._fill)
        self.list = QListWidget()
        self.list.setIconSize(self.list.iconSize())
        self.list.itemActivated.connect(self._pick)
        self.list.itemClicked.connect(self._pick)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.filter)
        layout.addWidget(self.list, 1)
        self._fill("")
        self.filter.input.installEventFilter(self)

    def _fill(self, text: str) -> None:
        self.list.clear()
        needle = text.strip().lower()
        for entry in self.entries:
            if needle and needle not in entry.lower():
                continue
            item = QListWidgetItem(icon("file-text"), f"{Path(entry).name}    {shorten_path(Path(entry).parent, 60)}")
            item.setData(ROLE_PATH, entry)
            item.setToolTip(entry)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _pick(self, item: QListWidgetItem) -> None:
        self.chosen = Path(item.data(ROLE_PATH))
        self.accept()

    def eventFilter(self, watched, event) -> bool:
        # Enter im Filterfeld öffnet den markierten Eintrag, Pfeiltasten wandern durch die Liste
        from PySide6.QtCore import QEvent
        if watched is self.filter.input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.list.currentItem():
                self._pick(self.list.currentItem())
                return True
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if event.key() == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
        return super().eventFilter(watched, event)
