"""Der Editor im Blatt: QTextEdit mit Zeilennummern, aktueller Zeile und Treffer-Markierung.

Warum QTextEdit statt QPlainTextEdit? Nur das Layout von QTextEdit respektiert die
Zeilenhöhe aus dem Blockformat (1.5-fach). Es layoutet trotzdem lazy, große
Dateien öffnen also weiterhin flott.

Zeilennummern: ein schmales Widget im linken Viewport-Rand (setViewportMargins),
das die sichtbaren Blöcke abläuft und ihre Nummern rechtsbündig zeichnet.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextOption
from PySide6.QtWidgets import QFrame, QMenu, QTextEdit, QWidget

from notex.core.encoding import TextFile
from notex.core import text_ops as ops
from notex.core.text_ops import hanging_prefix
from notex.core.spell import SpellChecker, LANGUAGE_LABELS
from notex.theme.icons import icon
from notex.theme.theme import style_menu
from notex.ui.spell_highlighter import Issue, SpellHighlighter
from notex.theme.fonts import STANDARD, text_font, ui_font
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
    files_dropped = Signal(list)   # Dateien aufs Blatt gezogen -> öffnen statt Pfad einfügen
    link_activated = Signal(object)   # LinkSpan bei Ctrl+Klick auf einen Wiki-Link
    completion_requested = Signal(str, str)   # ("file", Präfix) oder ("heading", Ziel) nach "[[" bzw. "#"

    def __init__(self, path: Path, text_file: TextFile, font_size: int, checker: SpellChecker | None = None,
                 share_with: "Editor | None" = None) -> None:
        """`share_with`: zweite Ansicht desselben Dokuments (geteilter Editor) – gleicher Text, gleiches Undo,
        gleicher Highlighter; nur Cursor, Scrollposition und Auswahl sind eigen."""
        super().__init__()
        self.path = path
        self.encoding = text_file.encoding
        self.eol = text_file.eol
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        self._font_size = font_size
        self._font_family = STANDARD   # "" = Standardschrift; Ansichts-Einstellung, ändert nichts an der Datei
        self.language: str | None = None   # Rechtschreib-Sprache nur für diesen Tab (None = global)
        self.read_only = False
        self.shared = share_with is not None
        self.encrypted = str(path).lower().endswith(".ntx")   # verschlüsselte Notiz: Klartext nur im Speicher
        self.key = None          # KeyState, solange entsperrt
        self.locked = self.encrypted
        self.highlighter: SpellHighlighter | None = None
        if share_with is not None:
            self.setDocument(share_with.document())
            self.highlighter = share_with.highlighter
            if self.highlighter is not None:
                self.highlighter.add_view(self)
        elif checker is not None:
            self.highlighter = SpellHighlighter(self.document(), self, checker, markdown=path.suffix.lower() == ".md")

        self.setObjectName("Editor")
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setAcceptRichText(False)          # eingefügter Text bleibt reiner Text
        # Text ist immer vollständig sichtbar: Umbruch an der Blattbreite, notfalls mitten im Wort
        # (lange URLs, Hashes, Pfade), und keine horizontale Scrollbar
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(SPACING.xs)
        self.setCursorWidth(2)
        self._padding = LAYOUT.paper_padding   # aktueller Innenabstand (schrumpft bei schmalem Blatt)
        self._show_numbers = True
        self._indent_pending: set[int] = set()
        self._indent_timer = QTimer(self)
        self._indent_timer.setSingleShot(True)
        self._indent_timer.setInterval(0)
        self._indent_timer.timeout.connect(self._apply_pending_indents)
        self.document().contentsChange.connect(self._on_block_changed)

        self.line_numbers = LineNumberArea(self)
        self.verticalScrollBar().valueChanged.connect(self.line_numbers.update)
        self.document().contentsChanged.connect(self._on_contents_changed)
        self.cursorPositionChanged.connect(self._refresh_extra_selections)

        self._loaded_once = False
        self.set_font_size(font_size)
        self.load(text_file)

    # ---- Inhalt ---------------------------------------------------------------
    def load(self, text_file: TextFile) -> None:
        self.encoding, self.eol = text_file.encoding, text_file.eol
        if self.shared and not self._loaded_once:
            # zweite Ansicht: das Dokument hat schon Inhalt, Formate und Undo-Stack
            self._loaded_once = True
            self._update_margins()
            self._refresh_extra_selections()
            return
        self._loaded_once = True
        self.setPlainText(text_file.text)
        self._apply_line_height()
        self._apply_hanging_indents()
        self._indent_timer.stop()          # das Laden selbst ist keine Tipp-Änderung
        self._indent_pending.clear()
        self.document().clearUndoRedoStacks()
        self.document().setModified(False)
        self._update_margins()
        self._refresh_extra_selections()
        if self.highlighter is not None:
            self.highlighter.mark_loaded()

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
        self._apply_font()

    @property
    def font_family(self) -> str:
        return self._font_family

    def set_text_font(self, family: str) -> None:
        self._font_family = family or STANDARD
        self._apply_font()

    def _apply_font(self) -> None:
        self.setFont(text_font(self._font_family, self._font_size))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._update_margins()
        self.line_numbers.update()
        self.refresh_indents()

    def refresh_indents(self) -> None:
        """Einrückungsbreiten hängen von der Schrift ab: nach Schriftwechsel neu setzen,
        ohne die Datei als geändert zu markieren (bei ungeänderter Datei bleibt auch Undo leer)."""
        if not self.document().blockCount() or not self.document().firstBlock().isValid():
            return
        modified = self.document().isModified()
        self._indent_timer.stop()
        self._indent_pending.clear()
        self._apply_hanging_indents()
        if not modified:
            # Reihenfolge wichtig: erst Undo leeren, dann „unverändert“ setzen – sonst gilt jeder
            # spätere (auch leere) Edit-Block als Änderung
            self.document().clearUndoRedoStacks()
        self.document().setModified(modified)

    def _number_font(self):
        """Zeilennummern in der UI-Schrift mit tabellarischen Ziffern, etwas kleiner als der Text."""
        return ui_font(max(9, self._font_size - 2), tabular=True)

    def char_width(self) -> float:
        """Mittlere Zeichenbreite – bei proportionalen Schriften über einen typischen Satz gemessen."""
        sample = "Franz jagt im komplett verwahrlosten Taxi quer durch Bayern. 0123456789"
        return self.fontMetrics().horizontalAdvance(sample) / len(sample)

    def set_padding(self, padding: int) -> None:
        """Innenabstand des Blatts; schrumpft, wenn das Blatt schmal wird (Minimum 16 px)."""
        padding = max(SPACING.lg, padding)
        if padding != self._padding:
            self._padding = padding
            self._update_margins()

    # ---- Hängende Einrückung ----------------------------------------------------
    def _indent_for(self, text: str) -> int:
        """Breite des Präfixes (Einrückung + Listenmarker) in Pixeln, Tabs als 4 Leerzeichen."""
        prefix = hanging_prefix(text).replace("\t", "    ")
        return self.fontMetrics().horizontalAdvance(prefix) if prefix else 0

    def _set_hanging_indent(self, block, indent: int) -> None:
        fmt = block.blockFormat()
        if round(fmt.leftMargin()) == indent:
            return
        fmt.setLeftMargin(indent)
        fmt.setTextIndent(-indent)
        cursor = QTextCursor(block)
        cursor.setBlockFormat(fmt)

    def _apply_hanging_indents(self) -> None:
        """Beim Laden für alle Blöcke (vor setModified(False), also ohne Dirty-Folgen).
        Nur Blöcke mit Präfix bekommen ein Format – bei 40 000 Zeilen spart das die meiste Zeit."""
        block = self.document().firstBlock()
        while block.isValid():
            text = block.text()
            if text[:1] in (" ", "\t", "-", "*", "+") or text[:1].isdigit():
                self._set_hanging_indent(block, self._indent_for(text))
            block = block.next()

    def _on_block_changed(self, position: int, removed: int, added: int) -> None:
        block = self.document().findBlock(position)
        end = self.document().findBlock(position + max(added, 1))
        while block.isValid():
            self._indent_pending.add(block.blockNumber())
            if block == end or block.blockNumber() >= end.blockNumber():
                break
            block = block.next()
        self._indent_timer.start()

    def _apply_pending_indents(self) -> None:
        """Einrückung der geänderten Blöcke nachziehen."""
        pending, self._indent_pending = self._indent_pending, set()
        for number in pending:
            block = self.document().findBlockByNumber(number)
            if block.isValid():
                self._set_hanging_indent(block, self._indent_for(block.text()))

    def _grouped(self, action) -> None:
        """Führt `action` und die daraus folgende Einrückungs-Korrektur als EINEN Undo-Schritt aus."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            action()
            self._indent_timer.stop()
            self._apply_pending_indents()
        finally:
            cursor.endEditBlock()

    def keyPressEvent(self, event) -> None:
        self._grouped(lambda: super(Editor, self).keyPressEvent(event))
        self._maybe_complete()

    def _maybe_complete(self) -> None:
        """Nach "[[" Dateien vorschlagen, nach "#" innerhalb eines Links die Überschriften des Ziels."""
        cursor = self.textCursor()
        before = cursor.block().text()[: cursor.positionInBlock()]
        start = before.rfind("[[")
        if start < 0 or "]]" in before[start:]:
            return
        inner = before[start + 2:]
        if "#" in inner:
            target, _, prefix = inner.partition("#")
            self.completion_requested.emit("heading", target + "\x00" + prefix)
        elif "|" not in inner:
            self.completion_requested.emit("file", inner)

    def complete_with(self, text: str) -> None:
        """Ersetzt den angefangenen Link-Teil hinter "[[" bzw. "#" durch `text` und schließt mit "]]"."""
        cursor = self.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        before = block_text[:col]
        start = before.rfind("[[")
        if start < 0:
            return
        hash_pos = before.rfind("#", start)
        replace_from = hash_pos + 1 if hash_pos > start else start + 2
        after = block_text[col:]
        closing = "" if after.startswith("]]") else "]]"
        edit = QTextCursor(self.document())
        edit.setPosition(cursor.block().position() + replace_from)
        edit.setPosition(cursor.block().position() + col, QTextCursor.MoveMode.KeepAnchor)
        self._grouped(lambda: edit.insertText(text + closing))
        if closing:
            self.setTextCursor(edit)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier \
                and self.highlighter is not None:
            cursor = self.cursorForPosition(event.position().toPoint())
            span = self.highlighter.link_at(cursor.block(), cursor.positionInBlock())
            if span is not None:
                self.link_activated.emit(span)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        over_link = False
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and self.highlighter is not None:
            cursor = self.cursorForPosition(event.position().toPoint())
            over_link = self.highlighter.link_at(cursor.block(), cursor.positionInBlock()) is not None
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if over_link else Qt.CursorShape.IBeamCursor)

    def insertFromMimeData(self, source) -> None:
        if source.hasUrls() and any(u.isLocalFile() for u in source.urls()):
            self.files_dropped.emit([u.toLocalFile() for u in source.urls() if u.isLocalFile()])
            return
        self._grouped(lambda: super(Editor, self).insertFromMimeData(source))

    def canInsertFromMimeData(self, source) -> bool:
        return source.hasUrls() or super().canInsertFromMimeData(source)

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
        if not self._show_numbers:
            return self._padding
        digits = max(2, len(str(max(1, self.document().blockCount()))))
        from PySide6.QtGui import QFontMetrics
        return self._padding + QFontMetrics(self._number_font()).horizontalAdvance("9") * digits + GUTTER_GAP

    def _update_margins(self) -> None:
        # links: Zeilennummern + Innenabstand, oben/unten/rechts: Innenabstand des Blatts
        top = max(SPACING.md, round(self._padding * 0.85))
        self.setViewportMargins(self.gutter_width(), top, max(SPACING.lg, self._padding // 2), top)
        rect = self.contentsRect()
        self.line_numbers.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(), rect.height()))

    def resizeEvent(self, event) -> None:
        # Lese-Position halten: der Block am oberen Rand bleibt nach dem Reflow oben
        top_block = self.cursorForPosition(QPoint(0, 0)).block()
        old_offset = 0
        if top_block.isValid():
            old_offset = self.verticalScrollBar().value() - int(self.document().documentLayout().blockBoundingRect(top_block).top())
        super().resizeEvent(event)
        self._update_margins()
        if top_block.isValid() and event.oldSize().width() != event.size().width():
            QTimer.singleShot(0, lambda b=top_block, o=old_offset: self._restore_top(b, o))

    def _restore_top(self, block, old_offset: int) -> None:
        if block.isValid():
            top = int(self.document().documentLayout().blockBoundingRect(block).top())
            self.verticalScrollBar().setValue(max(0, top + old_offset))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        # Das globale QSS setzt beim Polishen die UI-Schrift auf jedes Widget – danach unsere Textschrift wieder anlegen
        if event.type() == QEvent.Type.StyleChange:
            self._apply_font()

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self.line_numbers)
        painter.setFont(self._number_font())
        layout = self.document().documentLayout()
        viewport_top = self.viewport().geometry().top() - self.line_numbers.geometry().top()
        scroll = self.verticalScrollBar().value()
        current_block = self.textCursor().blockNumber()
        right = self.gutter_width() - GUTTER_GAP
        height = self.fontMetrics().height()   # Höhe der ersten Textzeile, damit die Nummer mit ihr fluchtet

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

    # ---- Werkzeuge der Bearbeitungsleiste ---------------------------------------
    def set_line_numbers(self, visible: bool) -> None:
        self.line_numbers.setVisible(visible)
        self._show_numbers = visible
        self._update_margins()

    def set_encoding(self, encoding: str) -> None:
        if encoding != self.encoding:
            self.encoding = encoding
            self.document().setModified(True)   # wirkt erst beim Speichern, ist aber eine Änderung

    def set_eol(self, eol: str) -> None:
        if eol != self.eol:
            self.eol = eol
            self.document().setModified(True)

    def _block_range(self) -> tuple[int, int]:
        """Erste und letzte Blocknummer der Auswahl (ohne Auswahl: der Cursor-Block)."""
        cursor = self.textCursor()
        start = self.document().findBlock(cursor.selectionStart()).blockNumber()
        end_pos = cursor.selectionEnd()
        if cursor.hasSelection() and end_pos > cursor.selectionStart():
            end_pos -= 1   # eine Auswahl, die genau am Zeilenanfang endet, gehört nicht zur nächsten Zeile
        end = self.document().findBlock(end_pos).blockNumber()
        return start, end

    def _replace_blocks(self, first: int, last: int, lines: list[str], select: tuple[int, int] | None = None) -> None:
        """Ersetzt die Blöcke first..last durch `lines` und markiert danach select=(erste, letzte) Blöcke."""
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.setPosition(doc.findBlockByNumber(first).position())
        last_block = doc.findBlockByNumber(last)
        cursor.setPosition(last_block.position() + last_block.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("\n".join(lines))
        if select is not None:
            a, b = select
            sel = QTextCursor(doc)
            sel.setPosition(doc.findBlockByNumber(a).position())
            end_block = doc.findBlockByNumber(b)
            sel.setPosition(end_block.position() + end_block.length() - 1, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(sel)

    def apply_line_op(self, func) -> None:
        """Wendet eine Funktion auf die ausgewählten Zeilen an (Liste rein, Liste raus)."""
        first, last = self._block_range()
        lines = [self.document().findBlockByNumber(n).text() for n in range(first, last + 1)]
        new_lines = func(lines)
        if new_lines == lines:
            return
        self._grouped(lambda: self._replace_blocks(first, last, new_lines, (first, first + len(new_lines) - 1)))

    def move_lines(self, direction: int) -> None:
        first, last = self._block_range()
        count = self.document().blockCount()
        if direction < 0 and first == 0 or direction > 0 and last >= count - 1:
            return
        lo, hi = (first - 1, last) if direction < 0 else (first, last + 1)
        lines = [self.document().findBlockByNumber(n).text() for n in range(lo, hi + 1)]
        moved, start, end = ops.move_lines(lines, first - lo, last - lo + 1, direction)
        self._grouped(lambda: self._replace_blocks(lo, hi, moved, (lo + start, lo + end - 1)))

    def apply_text_op(self, func) -> None:
        """Wendet eine Funktion auf die Auswahl an (ohne Auswahl: das Wort unter dem Cursor)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        text = cursor.selectedText().replace("\u2029", "\n")
        new_text = func(text)
        if new_text == text:
            return
        start = cursor.selectionStart()

        def do() -> None:
            cursor.insertText(new_text)
            cursor.setPosition(start)
            cursor.setPosition(start + len(new_text), QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)

        self._grouped(do)

    def insert_text(self, text: str) -> None:
        self._grouped(lambda: self.textCursor().insertText(text))

    # ---- Rechtschreibung -----------------------------------------------------
    def set_spellcheck(self, spelling: bool, grammar: bool) -> None:
        if self.highlighter is not None:
            self.highlighter.set_enabled(spelling, grammar)

    def set_language(self, language: str | None) -> None:
        self.language = language
        if self.highlighter is not None:
            self.highlighter.set_language(language)

    def issues_at_cursor(self, cursor: QTextCursor) -> list[Issue]:
        if self.highlighter is None:
            return []
        return self.highlighter.issues_at(cursor.block(), cursor.positionInBlock())

    context_menu_hook = None   # (editor, menu, term) -> None; setzt das Hauptfenster (Text + Nachschlagen)

    def lookup_term(self) -> str:
        """Suchbegriff: Markierung, sonst das Wort am Cursor – getrimmt, einzeilig, max. 200 Zeichen."""
        from notex.core.lookup import prepare_term
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return prepare_term(cursor.selectedText())

    def term_rect(self) -> QRect:
        """Bildschirm-Rechteck der Markierung bzw. des Worts am Cursor – Anker für die Nachschlage-Karte."""
        cursor = QTextCursor(self.textCursor())
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        start, end = QTextCursor(cursor), QTextCursor(cursor)
        start.setPosition(cursor.selectionStart())
        end.setPosition(cursor.selectionEnd())
        a, b = self.cursorRect(start), self.cursorRect(end)
        if a.top() != b.top():                       # mehrzeilig: ganze Breite der Zeilen
            rect = QRect(self.viewport().rect().left(), a.top(), self.viewport().width(), b.bottom() - a.top())
        else:
            rect = a.united(b)
        clipped = rect.intersected(self.viewport().rect())
        rect = clipped if not clipped.isEmpty() else rect
        return QRect(self.viewport().mapToGlobal(rect.topLeft()), rect.size())

    def build_context_menu(self, pos) -> QMenu:
        """Vorschläge (Rechtschreibung/Grammatik) oben, dann Bearbeiten, Text und Nachschlagen.
        Rechtsklick außerhalb der Markierung setzt den Cursor dorthin – dann gilt das Wort unter dem Mauszeiger."""
        from PySide6.QtGui import QKeySequence
        click = self.cursorForPosition(pos)
        current = self.textCursor()
        inside = current.hasSelection() and current.selectionStart() <= click.position() <= current.selectionEnd()
        if not inside:
            self.setTextCursor(click)
        issues = self.issues_at_cursor(click)
        menu = style_menu(QMenu(self))
        for issue in issues:
            self._add_issue_actions(menu, None, click, issue)
        if issues:
            menu.addSeparator()

        has_selection = self.textCursor().hasSelection()
        writable = not self.isReadOnly()

        def add(icon_name: str, text: str, shortcut, slot, enabled: bool) -> None:
            action = QAction(icon(icon_name), text, menu)
            if shortcut is not None:
                action.setShortcut(QKeySequence(shortcut))
                action.setShortcutVisibleInContextMenu(True)
            action.setEnabled(enabled)
            action.triggered.connect(slot)
            menu.addAction(action)

        add("scissors", "Ausschneiden", QKeySequence.StandardKey.Cut, self.cut, has_selection and writable)
        add("copy", "Kopieren", QKeySequence.StandardKey.Copy, self.copy, has_selection)
        add("clipboard-paste", "Einfügen", QKeySequence.StandardKey.Paste, self.paste, writable and self.canPaste())
        add("trash", "Löschen", QKeySequence.StandardKey.Delete, lambda: self._grouped(lambda: self.textCursor().removeSelectedText()),
            has_selection and writable)
        add("scan-text", "Alles markieren", QKeySequence.StandardKey.SelectAll, self.selectAll, not self.document().isEmpty())
        if self.context_menu_hook is not None:
            self.context_menu_hook(self, menu, self.lookup_term())
        return menu

    def contextMenuEvent(self, event) -> None:
        self.build_context_menu(event.pos()).exec(event.globalPos())

    def _replace_issue(self, cursor: QTextCursor, issue: Issue, replacement: str) -> None:
        block_start = cursor.block().position()
        edit = QTextCursor(self.document())
        edit.setPosition(block_start + issue.start)
        edit.setPosition(block_start + issue.start + issue.length, QTextCursor.MoveMode.KeepAnchor)
        edit.insertText(replacement)

    def _add_issue_actions(self, menu: QMenu, before, cursor: QTextCursor, issue: Issue) -> None:
        checker = self.highlighter.checker if self.highlighter else None
        if issue.kind == "spelling" and checker is not None:
            suggestions = checker.suggestions(issue.word, limit=5, language=self.language)
            if not suggestions:
                action = QAction("Keine Vorschläge", menu)
                action.setEnabled(False)
                menu.insertAction(before, action)
            for suggestion in suggestions:
                action = QAction(suggestion, menu)
                action.triggered.connect(lambda _c=False, s=suggestion: self._replace_issue(cursor, issue, s))
                menu.insertAction(before, action)
            if not self.encrypted:   # user_dictionary.txt ist Klartext auf der Platte – nie aus .ntx-Notizen
                add = QAction(icon("plus"), "Zum Wörterbuch hinzufügen", menu)
                add.triggered.connect(lambda: (checker.add_to_dictionary(issue.word), self.highlighter.reset()))
                menu.insertAction(before, add)
            ignore = QAction("In dieser Sitzung ignorieren", menu)
            ignore.triggered.connect(lambda: (checker.ignore_for_session(issue.word), self.highlighter.reset()))
            menu.insertAction(before, ignore)
        elif issue.kind == "grammar":
            title = QAction(issue.message[:90] + ("…" if len(issue.message) > 90 else ""), menu)
            title.setEnabled(False)
            menu.insertAction(before, title)
            for replacement in issue.replacements[:5]:
                action = QAction(f"→ {replacement}", menu)
                action.triggered.connect(lambda _c=False, r=replacement: self._replace_issue(cursor, issue, r))
                menu.insertAction(before, action)
            if issue.rule:
                rule = QAction(f"Regel: {issue.rule}", menu)
                rule.setEnabled(False)
                menu.insertAction(before, rule)

    # ---- Zoom -------------------------------------------------------------
    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_requested.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)
