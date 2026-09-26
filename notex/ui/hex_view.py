"""Hex-Ansicht (nur lesen): Offset | 16 Bytes hex | ASCII, synchron markiert, Sprung zu Offset, Suche.

Gezeichnet werden nur die sichtbaren Zeilen; gelesen wird seitenweise über PagedFile – auch mehrere GB öffnen
sofort. Die Suche läuft in einem eigenen Thread mit Fortschritt und Abbruch, die Oberfläche bleibt bedienbar.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from notex.core import filetype, hexdata
from notex.core.hexdata import BYTES_PER_ROW, PagedFile
from notex.theme.fonts import MONO_FAMILIES
from notex.theme.tokens import COLORS, SPACING
from notex.ui.viewer_page import ViewerPage, human_size
from notex.ui.widgets import IconButton

MAX_SCROLL = 1_000_000_000          # Scrollbalken-Schritte; darüber (> 16 GB) wird skaliert
COPY_LIMIT = 4 * 1024 * 1024


class _HexArea(QAbstractScrollArea):
    cursor_changed = Signal()

    def __init__(self, paged: PagedFile) -> None:
        super().__init__()
        self.setObjectName("HexArea")
        self.paged = paged
        self.cursor = 0              # Byte unter dem Cursor
        self.anchor = 0              # anderes Ende der Auswahl
        self.active = "hex"          # zuletzt angeklickte Spalte: "hex" | "ascii"
        self._dragging = False
        font = QFont()
        font.setFamilies(MONO_FAMILIES)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(13)
        self.setFont(font)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._measure()

    # ---- Geometrie ------------------------------------------------------------------------------
    def _measure(self) -> None:
        metrics = QFontMetrics(self.font())
        self.cw = metrics.horizontalAdvance("0")
        self.lh = metrics.height() + 4
        self.ascent = metrics.ascent() + 2
        self.digits = hexdata.offset_digits(self.paged.size)
        pad = SPACING.md
        self.x_hex = pad + (self.digits + 2) * self.cw
        self.x_ascii = self.x_hex + (BYTES_PER_ROW * 3 + 2) * self.cw
        self.content_width = self.x_ascii + BYTES_PER_ROW * self.cw + pad
        self._update_scroll()

    @property
    def rows(self) -> int:
        return max(1, math.ceil(self.paged.size / BYTES_PER_ROW))

    @property
    def visible_rows(self) -> int:
        return max(1, self.viewport().height() // self.lh)

    def _scale(self) -> int:
        return max(1, math.ceil(self.rows / MAX_SCROLL))

    def _update_scroll(self) -> None:
        bar = self.verticalScrollBar()
        scale = self._scale()
        bar.setRange(0, max(0, (self.rows - self.visible_rows + scale - 1) // scale))
        bar.setPageStep(max(1, self.visible_rows // scale))
        bar.setSingleStep(1 if scale == 1 else max(1, 3 // scale))
        hbar = self.horizontalScrollBar()
        hbar.setRange(0, max(0, self.content_width - self.viewport().width()))
        hbar.setPageStep(self.viewport().width())

    def top_row(self) -> int:
        return min(self.verticalScrollBar().value() * self._scale(), max(0, self.rows - 1))

    def _hex_x(self, column: int) -> int:
        return self.x_hex + (column * 3 + (1 if column >= 8 else 0)) * self.cw

    def hit(self, x: int, y: int) -> tuple[int, str] | None:
        """Byte-Offset und Spalte unter einer Viewport-Position."""
        x += self.horizontalScrollBar().value()
        row = self.top_row() + max(0, y) // self.lh
        column, area = None, None
        if self.x_hex - self.cw <= x < self.x_ascii - self.cw:
            area = "hex"
            relative = (x - self.x_hex) / self.cw
            if relative >= 8 * 3:
                relative -= 1
            column = int(max(0, min(BYTES_PER_ROW - 1, relative // 3)))
        elif x >= self.x_ascii - self.cw:
            area = "ascii"
            column = int(max(0, min(BYTES_PER_ROW - 1, (x - self.x_ascii) // self.cw)))
        if column is None:
            return None
        return min(row * BYTES_PER_ROW + column, max(0, self.paged.size - 1)), area

    # ---- Auswahl ------------------------------------------------------------------------------
    def selection(self) -> tuple[int, int]:
        """(Start, Länge) – ohne Ziehen ist das genau ein Byte (der Cursor)."""
        start, end = sorted((self.cursor, self.anchor))
        return start, (end - start + 1) if self.paged.size else 0

    def set_cursor(self, offset: int, extend: bool = False, length: int = 1) -> None:
        if not self.paged.size:
            return
        offset = max(0, min(offset, self.paged.size - 1))
        self.cursor = offset if length <= 1 else min(offset + length - 1, self.paged.size - 1)
        if not extend:
            self.anchor = offset
        self.ensure_visible(offset)
        self.viewport().update()
        self.cursor_changed.emit()

    def ensure_visible(self, offset: int) -> None:
        row = offset // BYTES_PER_ROW
        top = self.top_row()
        scale = self._scale()
        if row < top:
            self.verticalScrollBar().setValue(row // scale)
        elif row >= top + self.visible_rows:
            self.verticalScrollBar().setValue((row - self.visible_rows + 1 + scale - 1) // scale)

    def selected_bytes(self) -> bytes:
        start, length = self.selection()
        return self.paged.read(start, min(length, COPY_LIMIT))

    # ---- Ereignisse ---------------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scroll()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        self.viewport().update()

    def mousePressEvent(self, event) -> None:
        hit = self.hit(int(event.position().x()), int(event.position().y()))
        if hit is not None and event.button() == Qt.MouseButton.LeftButton:
            offset, self.active = hit
            self._dragging = True
            self.set_cursor(offset, extend=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            hit = self.hit(int(event.position().x()), int(event.position().y()))
            if hit is not None:
                self.set_cursor(hit[0], extend=True)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy(as_text=self.active == "ascii")
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.anchor, self.cursor = 0, max(0, self.paged.size - 1)
            self.viewport().update()
            self.cursor_changed.emit()
            return
        key = event.key()
        extend = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        page = self.visible_rows * BYTES_PER_ROW
        moves = {
            Qt.Key.Key_Left: self.cursor - 1, Qt.Key.Key_Right: self.cursor + 1,
            Qt.Key.Key_Up: self.cursor - BYTES_PER_ROW, Qt.Key.Key_Down: self.cursor + BYTES_PER_ROW,
            Qt.Key.Key_PageUp: self.cursor - page, Qt.Key.Key_PageDown: self.cursor + page,
            Qt.Key.Key_Home: 0 if ctrl else self.cursor - self.cursor % BYTES_PER_ROW,
            Qt.Key.Key_End: self.paged.size - 1 if ctrl else self.cursor - self.cursor % BYTES_PER_ROW + BYTES_PER_ROW - 1,
        }
        if key in moves:
            self.set_cursor(moves[key], extend=extend)
            return
        if key == Qt.Key.Key_Tab:
            self.active = "ascii" if self.active == "hex" else "hex"
            self.viewport().update()
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, _next: bool) -> bool:     # Tab wechselt die Spalte statt den Fokus
        return False

    def copy(self, as_text: bool = False) -> None:
        data = self.selected_bytes()
        if not data:
            return
        QApplication.clipboard().setText(hexdata.ascii_line(data) if as_text else hexdata.to_hex_string(data))

    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        painter.setFont(self.font())
        painter.fillRect(self.viewport().rect(), QColor(COLORS.paper))
        dx = -self.horizontalScrollBar().value()
        top = self.top_row()
        start, length = self.selection()
        end = start + length
        muted, text = QColor(COLORS.paper_muted), QColor(COLORS.paper_text)
        selection_bg, cursor_bg = QColor(COLORS.paper_selection), QColor(COLORS.paper_match_current)
        zero = QColor(COLORS.paper_muted)
        data = self.paged.read(top * BYTES_PER_ROW, (self.visible_rows + 1) * BYTES_PER_ROW)
        for index in range(self.visible_rows + 1):
            row = top + index
            chunk = data[index * BYTES_PER_ROW:(index + 1) * BYTES_PER_ROW]
            if not chunk and row * BYTES_PER_ROW >= self.paged.size:
                break
            y = index * self.lh
            base = row * BYTES_PER_ROW
            painter.setPen(muted)
            painter.drawText(SPACING.md + dx, y + self.ascent, hexdata.offset_label(base, self.digits))
            for column, byte in enumerate(chunk):
                offset = base + column
                hx, ax = self._hex_x(column) + dx, self.x_ascii + column * self.cw + dx
                if start <= offset < end and length > 1 or offset == self.cursor:
                    color = cursor_bg if offset == self.cursor else selection_bg
                    painter.fillRect(QRect(hx - self.cw // 2, y, self.cw * 3, self.lh), color)
                    painter.fillRect(QRect(ax, y, self.cw, self.lh), color)
                    if offset == self.cursor:        # aktive Spalte: Rahmen um den Cursor
                        rect = QRect(hx - self.cw // 2, y, self.cw * 3 - 1, self.lh - 1) if self.active == "hex" \
                            else QRect(ax, y, self.cw - 1, self.lh - 1)
                        painter.setPen(QColor(COLORS.accent))
                        painter.drawRect(rect)
                painter.setPen(zero if byte == 0 else text)
                painter.drawText(hx, y + self.ascent, f"{byte:02X}")
                printable = 0x20 <= byte < 0x7F
                painter.setPen(text if printable else muted)
                painter.drawText(ax, y + self.ascent, chr(byte) if printable else "·")
        if not self.paged.size:
            painter.setPen(muted)
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, "Leere Datei")
        painter.end()


class _SearchThread(QThread):
    progress = Signal(int)
    finished_search = Signal(object)        # Offset oder None

    def __init__(self, path: Path, pattern: bytes, start: int, ignore_case: bool) -> None:
        super().__init__()
        self.path, self.pattern, self.start_offset, self.ignore_case = path, pattern, start, ignore_case
        self.cancel = False

    def run(self) -> None:
        try:
            result = hexdata.search_file(self.path, self.pattern, self.start_offset, ignore_case=self.ignore_case,
                                         progress=lambda done, total: self.progress.emit(int(done * 100 / max(1, total))),
                                         cancelled=lambda: self.cancel)
        except OSError:
            result = None
        self.finished_search.emit(None if self.cancel else result)


class HexPage(ViewerPage):
    kind = "hex"
    icon_name = "binary"

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.paged = PagedFile(path)
        self.ftype = filetype.detect_file(self.path)
        self.warning = filetype.mismatch(self.path.name, self.ftype) or ""
        self.area = _HexArea(self.paged)
        self.area.cursor_changed.connect(self.status_changed)
        self._search: _SearchThread | None = None
        self._last_found = -1

        self.goto_field = QLineEdit()
        self.goto_field.setPlaceholderText("Offset (1234 oder 0x4D2)")
        self.goto_field.setToolTip("Gehe zu Offset – dezimal oder hex  Ctrl+G")
        self.goto_field.setFixedWidth(190)
        self.goto_field.returnPressed.connect(self.goto)
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Suchen …")
        self.search_field.returnPressed.connect(self.find_next)
        self.search_mode = QComboBox()
        self.search_mode.addItem("Hex-Bytes", "hex")
        self.search_mode.addItem("Text", "text")
        self.search_mode.addItem("Text (Groß/klein egal)", "text_i")
        self.search_button = QPushButton("Weitersuchen")
        self.search_button.clicked.connect(self.find_next)
        reload_button = IconButton("rotate-ccw", "Neu laden (Datei hat sich geändert)")
        reload_button.clicked.connect(self.reload)
        self.info = QLabel()
        self.info.setObjectName("DataInfo")
        strip = QFrame()
        strip.setObjectName("DataBar")
        bar = QHBoxLayout(strip)
        bar.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        bar.setSpacing(SPACING.sm)
        bar.addWidget(self.goto_field)
        bar.addWidget(self.search_field, 1)
        bar.addWidget(self.search_mode)
        bar.addWidget(self.search_button)
        bar.addWidget(reload_button)
        bar.addWidget(self.info)
        frame = QFrame()
        frame.setObjectName("DataFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        frame_layout.addWidget(strip)
        frame_layout.addWidget(self.area, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.md, SPACING.lg, SPACING.lg)
        layout.addWidget(frame)
        for sequence, slot in (("Ctrl+G", self.focus_goto), ("F3", self.find_next), ("Escape", self.cancel_search)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
        if self.warning:
            self.info.setText("⚠ " + self.warning)

    # ---- Aktionen -------------------------------------------------------------------------------
    def focus_goto(self) -> None:
        self.goto_field.setFocus()
        self.goto_field.selectAll()

    def focus_search(self) -> None:
        self.search_field.setFocus()
        self.search_field.selectAll()

    def goto(self) -> None:
        try:
            offset = hexdata.parse_offset(self.goto_field.text())
        except ValueError as error:
            self.info.setText(str(error))
            return
        if offset >= self.paged.size:
            self.info.setText(f"Offset hinter dem Dateiende ({self.paged.size:,} Bytes)".replace(",", "."))
            return
        self.info.setText("")
        self.area.set_cursor(offset)
        self.area.setFocus()

    def find_next(self) -> None:
        if self._search is not None:
            self.cancel_search()
            return
        text = self.search_field.text()
        mode = self.search_mode.currentData()
        try:
            pattern = hexdata.parse_hex_pattern(text) if mode == "hex" else text.encode("utf-8")
        except ValueError as error:
            self.info.setText(str(error))
            return
        if not pattern:
            return
        start, _length = self.area.selection()
        begin = start + 1 if start == self._last_found else start     # „Weitersuchen“ hinter dem letzten Treffer
        self._search = _SearchThread(self.path, pattern, min(begin, max(0, self.paged.size - 1)), mode == "text_i")
        self._search.progress.connect(lambda p: self.info.setText(f"Suche … {p} %"))
        self._search.finished_search.connect(lambda result, n=len(pattern): self._found(result, n))
        self.search_button.setText("Abbrechen")
        self.info.setText("Suche …")
        self._search.start()

    def _found(self, result, length: int) -> None:
        thread, self._search = self._search, None
        if thread is not None:
            thread.wait()
        self.search_button.setText("Weitersuchen")
        if result is None:
            self.info.setText("Nicht gefunden")
            return
        self._last_found = result
        self.info.setText(f"Gefunden bei 0x{result:X} ({result:,})".replace(",", "."))
        self.area.anchor = result
        self.area.set_cursor(result, extend=True, length=length)
        self.area.anchor = result
        self.area.viewport().update()
        self.area.setFocus()

    def cancel_search(self) -> None:
        if self._search is not None:
            self._search.cancel = True

    def reload(self) -> None:
        try:
            self.paged.refresh()
        except OSError as error:
            self.info.setText(str(error))
            return
        self.ftype = filetype.detect_file(self.path)
        self.warning = filetype.mismatch(self.path.name, self.ftype) or ""
        self.area._measure()
        self.area.viewport().update()
        self.status_changed.emit()

    # ---- ViewerPage ---------------------------------------------------------------------------------
    def status_parts(self) -> list[str]:
        start, length = self.area.selection()
        cursor = self.area.cursor
        position = f"Offset 0x{cursor:X} ({cursor:,})".replace(",", ".") if self.paged.size else "–"
        selection = f"Auswahl {length:,} Bytes".replace(",", ".") if length > 1 else "nur lesen"
        return [position, human_size(self.paged.size), self.ftype.name, selection]

    def rename(self, new_path: Path) -> None:
        super().rename(new_path)
        self.paged.path = Path(new_path)

    def retheme(self) -> None:
        self.area.viewport().update()

    def shutdown(self) -> None:
        if self._search is not None:
            self._search.cancel = True
            self._search.wait(2000)
