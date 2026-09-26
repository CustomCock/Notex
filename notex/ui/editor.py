"""Der Editor im Blatt: QTextEdit mit Zeilennummern, aktueller Zeile und Treffer-Markierung.

Warum QTextEdit statt QPlainTextEdit? Nur das Layout von QTextEdit respektiert die
Zeilenhöhe aus dem Blockformat (1.5-fach). Es layoutet trotzdem lazy, große
Dateien öffnen also weiterhin flott.

Zeilennummern: ein schmales Widget im linken Viewport-Rand (setViewportMargins),
das die sichtbaren Blöcke abläuft und ihre Nummern rechtsbündig zeichnet.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextOption
from PySide6.QtWidgets import QFrame, QTextEdit, QWidget

from notex.core.encoding import TextFile
from notex.theme.fonts import editor_font
from notex.theme.tokens import COLORS, LAYOUT, SPACING

MAX_HIGHLIGHTS = 2000   # mehr Treffer gleichzeitig zu markieren wäre nur langsam
GUTTER_GAP = SPACING.lg  # Abstand Zeilennummer -> Text


class LineNumberArea(QWidget):
    def __init__(self, editor: "Editor") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_line_numbers(event)


class Editor(QTextEdit):
    zoom_requested = Signal(int)   # +1 = größer, -1 = kleiner (Ctrl+Mausrad)

    def __init__(self, path: Path, text_file: TextFile, font_size: int) -> None:
        super().__init__()
        self.path = path
        self.encoding = text_file.encoding
        self.eol = text_file.eol
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        self._font_size = font_size

        self.setObjectName("Editor")
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setAcceptRichText(False)          # eingefügter Text bleibt reiner Text
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.document().setDocumentMargin(SPACING.xs)
        self.setCursorWidth(2)

        self.line_numbers = LineNumberArea(self)
        self.verticalScrollBar().valueChanged.connect(self.line_numbers.update)
        self.document().contentsChanged.connect(self._on_contents_changed)
        self.cursorPositionChanged.connect(self._refresh_extra_selections)

        self.set_font_size(font_size)
        self.load(text_file)

    # ---- Inhalt ---------------------------------------------------------------
    def load(self, text_file: TextFile) -> None:
        self.encoding, self.eol = text_file.encoding, text_file.eol
        self.setPlainText(text_file.text)
        self._apply_line_height()
        self.document().clearUndoRedoStacks()
        self.document().setModified(False)
        self._update_margins()
        self._refresh_extra_selections()

    def _apply_line_height(self) -> None:
        """1.5-fache Zeilenhöhe für alle Blöcke. Neue Zeilen erben das Format beim Tippen."""
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(LAYOUT.editor_line_height, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.mergeBlockFormat(fmt)

    def retheme(self) -> None:
        """Schrift, Zeilenhöhe und Farben aus den aktuellen Tokens übernehmen."""
        self.set_font_size(self._font_size)
        if self.document().firstBlock().blockFormat().lineHeight() != LAYOUT.editor_line_height:
            modified = self.document().isModified()
            self._apply_line_height()
            self.document().setModified(modified)
        self._refresh_extra_selections()
        self.viewport().update()

    def replace_content(self, text_file: TextFile) -> None:
        """Inhalt komplett ersetzen (z. B. nach externer Änderung), Cursor möglichst behalten."""
        position = self.textCursor().position()
        self.load(text_file)
        cursor = self.textCursor()
        cursor.setPosition(min(position, len(text_file.text)))
        self.setTextCursor(cursor)

    @property
    def is_dirty(self) -> bool:
        return self.document().isModified()

    # ---- Darstellung ------------------------------------------------------------
    @property
    def font_size(self) -> int:
        return self._font_size

    def set_font_size(self, pixel_size: int) -> None:
        self._font_size = pixel_size
        self.setFont(editor_font(pixel_size))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._update_margins()

    def set_word_wrap(self, enabled: bool) -> None:
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if enabled else QTextEdit.LineWrapMode.NoWrap)
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap if enabled else QTextOption.WrapMode.NoWrap)

    def char_width(self) -> int:
        return self.fontMetrics().horizontalAdvance("M")

    def cursor_line_col(self) -> tuple[int, int]:
        cursor = self.textCursor()
        return cursor.blockNumber() + 1, cursor.positionInBlock() + 1

    def center_cursor(self) -> None:
        self.ensureCursorVisible()
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() + self.cursorRect().center().y() - self.viewport().height() // 2)

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
        self.center_cursor()
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
            self._refresh_extra_selections()
            return True
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End if backwards else QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        found = self.find(term, flags)
        self._refresh_extra_selections()
        return found

    def replace_current(self, term: str, replacement: str, case_sensitive: bool) -> bool:
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
        """Markiert alle Vorkommen von `term` (bis MAX_HIGHLIGHTS)."""
        self._search_selections = []
        if term:
            flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(COLORS.paper_match))
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
        current_line.format.setBackground(QColor(COLORS.paper_line))
        current_line.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        current_line.cursor = self.textCursor()
        current_line.cursor.clearSelection()
        selections = [current_line, *self._search_selections]
        # Der Treffer unter dem Cursor wird etwas kräftiger markiert
        cursor = self.textCursor()
        if cursor.hasSelection():
            for sel in self._search_selections:
                if sel.cursor.selectionStart() == cursor.selectionStart() and sel.cursor.selectionEnd() == cursor.selectionEnd():
                    current = QTextEdit.ExtraSelection()
                    current.cursor = sel.cursor
                    current.format.setBackground(QColor(COLORS.paper_match_current))
                    selections.append(current)
        self.setExtraSelections(selections)
        self.line_numbers.update()

    def _on_contents_changed(self) -> None:
        self._update_margins()
        self.line_numbers.update()

    # ---- Zeilennummern --------------------------------------------------------
    def gutter_width(self) -> int:
        digits = max(2, len(str(max(1, self.document().blockCount()))))
        return LAYOUT.paper_padding + self.fontMetrics().horizontalAdvance("9") * digits + GUTTER_GAP

    def _update_margins(self) -> None:
        # links: Zeilennummern + Innenabstand, oben/unten/rechts: Innenabstand des Blatts
        self.setViewportMargins(self.gutter_width(), LAYOUT.paper_padding_top, SPACING.xl, LAYOUT.paper_padding_top)
        rect = self.contentsRect()
        self.line_numbers.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(), rect.height()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_margins()

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self.line_numbers)
        painter.setFont(self.font())
        layout = self.document().documentLayout()
        viewport_top = self.viewport().geometry().top() - self.line_numbers.geometry().top()
        scroll = self.verticalScrollBar().value()
        current_block = self.textCursor().blockNumber()
        right = self.gutter_width() - GUTTER_GAP
        height = self.fontMetrics().height()

        # Beim ersten sichtbaren Block anfangen statt alle Blöcke abzulaufen
        block = self.cursorForPosition(QPoint(0, 0)).block()
        while block.isValid():
            rect = layout.blockBoundingRect(block)
            top = int(rect.top()) - scroll + viewport_top
            if top > event.rect().bottom():
                break
            if block.isVisible() and top + rect.height() >= event.rect().top():
                is_current = block.blockNumber() == current_block
                painter.setPen(QColor(COLORS.paper_text if is_current else COLORS.paper_muted))
                painter.drawText(0, top, right, height, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 str(block.blockNumber() + 1))
            block = block.next()

    # ---- Zoom -------------------------------------------------------------
    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_requested.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)
