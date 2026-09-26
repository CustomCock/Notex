"""Kleines Popup unter dem Cursor: Vorschläge für [[Datei]] und [[Datei#Überschrift]]."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from notex.theme.icons import icon
from notex.theme.tokens import LAYOUT

MAX_ROWS = 8


class CompletionPopup(QListWidget):
    chosen = Signal(str)

    def __init__(self, editor) -> None:
        super().__init__(editor)
        self.setObjectName("CompletionPopup")
        self.editor = editor
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIconSize(QSize(14, 14))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.itemClicked.connect(lambda item: self._pick(item))
        editor.installEventFilter(self)
        self.hide()

    def show_items(self, entries: list[tuple[str, str]], icon_name: str) -> None:
        """entries: (einzufügender Text, Anzeigetext)."""
        self.clear()
        for value, label in entries[:40]:
            item = QListWidgetItem(icon(icon_name), label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.addItem(item)
        if not self.count():
            self.hide()
            return
        self.setCurrentRow(0)
        rows = min(MAX_ROWS, self.count())
        self.setFixedSize(360, rows * (LAYOUT.tree_row_height - 4) + 8)
        rect = self.editor.cursorRect()
        self.move(self.editor.viewport().mapToGlobal(rect.bottomLeft()) + QPoint(0, 4))
        self.show()

    def _pick(self, item: QListWidgetItem) -> None:
        self.hide()
        self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))

    def eventFilter(self, watched, event) -> bool:
        if watched is self.editor and self.isVisible() and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab) and self.currentItem():
                self._pick(self.currentItem())
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.setCurrentRow(max(0, min(self.count() - 1, self.currentRow() + (1 if key == Qt.Key.Key_Down else -1))))
                return True
        if watched is self.editor and event.type() in (QEvent.Type.FocusOut, QEvent.Type.Hide):
            self.hide()
        return super().eventFilter(watched, event)
