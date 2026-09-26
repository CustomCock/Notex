"""Das weiße Blatt: QPlainTextEdit mit Zeilennummern, aktueller Zeile und Treffer-Markierung.

Zeilennummern nach dem klassischen Qt-Muster: ein schmales Widget links im
Viewport-Rand (setViewportMargins), das bei jedem Scrollen neu gezeichnet wird.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from notex.core.encoding import TextFile
from notex.theme.theme import COLORS, editor_font

MAX_HIGHLIGHTS = 2000   # mehr Treffer gleichzeitig zu markieren wäre nur langsam


class LineNumberArea(QWidget):
    def __init__(self, editor: "Editor") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_line_numbers(event)


class Editor(QPlainTextEdit):
    zoom_requested = Signal(int)   # +1 = größer, -1 = kleiner (Ctrl+Mausrad)

    def __init__(self, path: Path, text_file: TextFile, font_size: int) -> None:
        super().__init__()
        self.path = path
        self.encoding = text_file.encoding
        self.eol = text_file.eol
        self._search_selections: list[QTextEdit.ExtraSelection] = []

        self.line_numbers = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margins)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._refresh_extra_selections)

        self.set_font_size(font_size)
        self.document().setDocumentMargin(14)  # Innenabstand wie ein Seitenrand
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.setPlainText(text_file.text)
        self.document().setModified(False)
        self._update_margins()
        self._refresh_extra_selections()

    # ---- Eigenschaften ----------------------------------------------------
    @property
    def is_dirty(self) -> bool:
        return self.document().isModified()

    def set_font_size(self, point_size: int) -> None:
        self.setFont(editor_font(point_size))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._update_margins()

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
            cursor.setPosition(block.position() + column + length, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    # ---- Suchen / Ersetzen --------------------------------------------------
    def find_next(self, term: str, case_sensitive: bool, backwards: bool = False) -> bool:
        """Sucht ab Cursor; am Ende (bzw. Anfang) wird einmal umgebrochen."""
        if not term:
            return False
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if backwards:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.find(term, flags):
            return True
        # Umbrechen: Cursor an den Anfang (bzw. das Ende) setzen und noch einmal
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End if backwards else QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        return self.find(term, flags)

    def replace_current(self, term: str, replacement: str, case_sensitive: bool) -> bool:
        """Ersetzt die aktuelle Auswahl, wenn sie dem Suchbegriff entspricht, und springt weiter."""
        cursor = self.textCursor()
        selected = cursor.selectedText()
        matches = selected == term if case_sensitive else selected.lower() == term.lower()
        if cursor.hasSelection() and matches:
            cursor.insertText(replacement)
        return self.find_next(term, case_sensitive)

    def replace_all(self, term: str, replacement: str, case_sensitive: bool) -> int:
        if not term:
            return 0
        flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)
        document = self.document()
        cursor = QTextCursor(document)
        cursor.beginEditBlock()   # alles als EIN Undo-Schritt
        count = 0
        found = document.find(term, 0, flags)
        while not found.isNull():
            found.insertText(replacement)
            count += 1
            found = document.find(term, found.position(), flags)
        cursor.endEditBlock()
        return count

    def set_search_highlight(self, term: str, case_sensitive: bool) -> None:
        """Markiert alle Vorkommen von `term` gelb (bis MAX_HIGHLIGHTS)."""
        self._search_selections = []
        if term:
            flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(COLORS["paper_match"]))
            found = self.document().find(term, 0, flags)
            while not found.isNull() and len(self._search_selections) < MAX_HIGHLIGHTS:
                selection = QTextEdit.ExtraSelection()
                selection.cursor = found
                selection.format = fmt
                self._search_selections.append(selection)
                found = self.document().find(term, found.position(), flags)
        self._refresh_extra_selections()

    # ---- Aktuelle Zeile + Extra-Selections ----------------------------------
    def _refresh_extra_selections(self) -> None:
        current_line = QTextEdit.ExtraSelection()
        current_line.format.setBackground(QColor(COLORS["paper_line"]))
        current_line.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        current_line.cursor = self.textCursor()
        current_line.cursor.clearSelection()
        # Reihenfolge: erst die Zeile, dann die Treffer darüber
        self.setExtraSelections([current_line, *self._search_selections])
        self.line_numbers.update()

    # ---- Zeilennummern --------------------------------------------------------
    def line_number_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margins(self) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_numbers.scroll(0, dy)
        else:
            self.line_numbers.update(0, rect.y(), self.line_numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margins()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.line_numbers.setGeometry(QRect(rect.left(), rect.top(), self.line_number_width(), rect.height()))

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self.line_numbers)
        painter.fillRect(event.rect(), QColor(COLORS["paper_gutter"]))
        painter.setFont(self.font())
        current_block = self.textCursor().blockNumber()
        width = self.line_numbers.width() - 6
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and top + height >= event.rect().top():
                is_current = block.blockNumber() == current_block
                painter.setPen(QColor(COLORS["paper_text"] if is_current else COLORS["paper_muted"]))
                painter.drawText(0, top, width, height, Qt.AlignmentFlag.AlignRight, str(block.blockNumber() + 1))
            block = block.next()
            top += round(self.blockBoundingRect(block).height())

    # ---- Zoom -------------------------------------------------------------
    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_requested.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)
