"""Das weiße Blatt: ein QPlainTextEdit, das weiß, welche Datei es zeigt."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPlainTextEdit

from textbaum.core.encoding import TextFile
from textbaum.theme.theme import editor_font


class Editor(QPlainTextEdit):
    def __init__(self, path: Path, text_file: TextFile, font_size: int) -> None:
        super().__init__()
        self.path = path
        self.encoding = text_file.encoding
        self.eol = text_file.eol

        self.setFont(editor_font(font_size))
        # Etwas Innenabstand, damit der Text nicht am Rand klebt (wie ein Seitenrand).
        self.document().setDocumentMargin(14)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

        self.setPlainText(text_file.text)
        self.document().setModified(False)

    # ---- Eigenschaften ----------------------------------------------------
    @property
    def is_dirty(self) -> bool:
        return self.document().isModified()

    def set_font_size(self, point_size: int) -> None:
        self.setFont(editor_font(point_size))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

    def set_word_wrap(self, enabled: bool) -> None:
        mode = QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap
        self.setLineWrapMode(mode)

    def replace_content(self, text_file: TextFile) -> None:
        """Inhalt komplett ersetzen (z. B. nach externer Änderung), Cursor möglichst behalten."""
        position = self.textCursor().position()
        self.encoding, self.eol = text_file.encoding, text_file.eol
        self.setPlainText(text_file.text)
        cursor = self.textCursor()
        cursor.setPosition(min(position, len(text_file.text)))
        self.setTextCursor(cursor)
        self.document().setModified(False)

    def cursor_line_col(self) -> tuple[int, int]:
        cursor = self.textCursor()
        return cursor.blockNumber() + 1, cursor.positionInBlock() + 1

    def goto_line(self, line: int, column: int = 0, length: int = 0) -> None:
        """Springt zu einer 1-basierten Zeile und markiert optional `length` Zeichen ab `column`."""
        block = self.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cursor = self.textCursor()
        cursor.setPosition(block.position() + column)
        if length > 0:
            cursor.setPosition(block.position() + column + length, cursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
