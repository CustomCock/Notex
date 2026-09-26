"""PDF-Tab (nur lesen): Scrollen, Zoom, Seitensprung, Textsuche, Lesezeichen, Text markieren → Zitat in die Notiz.

Eigene Seitenansicht auf QPdfDocument statt QPdfView, weil QPdfView keine Textauswahl kann. Seiten werden in einem
Hintergrund-Renderer gerastert (QPdfPageRenderer, mehrere Threads) und zwischengespeichert – die Oberfläche wartet
nie auf eine Seite. Es gibt keine Formular-, Link- oder Skript-Interaktion: Notex zeigt nur an und liest Text aus.
Die Datei wird in den Speicher gelesen und sofort geschlossen, damit sie umbenannt/verschoben werden kann.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPolygonF, QShortcut
from PySide6.QtPdf import (QPdfBookmarkModel, QPdfDocument, QPdfDocumentRenderOptions, QPdfPageRenderer,
                           QPdfSearchModel)
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QComboBox, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMenu, QSplitter, QTreeView, QVBoxLayout)

from notex.core import pdfdoc
from notex.core.pdfdoc import PageLayout
from notex.theme.theme import style_menu
from notex.theme.tokens import COLORS, SPACING
from notex.ui.viewer_page import ViewerPage, human_size
from notex.ui.widgets import IconButton

CACHE_IMAGES = 24
ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 6.0, 8.0]
IN_MEMORY_LIMIT = 256 * 1024 * 1024
PAGE_WHITE = "#ffffff"      # PDF-Seiten sind immer weiß gestaltet – unabhängig vom Blatt-Theme


def _alpha(color: str, alpha: int) -> QColor:
    result = QColor(color)
    result.setAlpha(alpha)
    return result


class _PdfCanvas(QAbstractScrollArea):
    page_changed = Signal(int)
    selection_changed = Signal()
    zoom_changed = Signal()
    quote_requested = Signal()

    def __init__(self, document: QPdfDocument) -> None:
        super().__init__()
        self.setObjectName("PdfCanvas")
        self.doc = document
        self.zoom_mode = "width"          # "width" | "page" | "custom"
        self.zoom = 1.0                   # bei "custom": 1.0 = 100 %
        self.layout_: PageLayout | None = None
        self.sizes: list[tuple[float, float]] = []
        self._images: OrderedDict[tuple[int, int], object] = OrderedDict()
        self._pending: dict[int, tuple[int, int]] = {}      # Request-ID → (Seite, Breite)
        self.renderer = QPdfPageRenderer(self)
        self.renderer.setRenderMode(QPdfPageRenderer.RenderMode.MultiThreaded)
        self.renderer.setDocument(document)
        self.renderer.pageRendered.connect(self._on_rendered)
        self.options = QPdfDocumentRenderOptions()
        self.options.setRenderFlags(QPdfDocumentRenderOptions.RenderFlag.Annotations)
        self.selection = None             # QPdfSelection
        self._lines: dict[int, list] = {}
        self.selection_page = -1
        self._drag_start: tuple[int, float, float] | None = None
        self.highlights: list[tuple[int, list]] = []   # (Seite, [QRectF in Punkt]) – Suchtreffer
        self.current_highlight: tuple[int, list] | None = None
        self.current_page = 0
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.verticalScrollBar().valueChanged.connect(self._track_page)

    # ---- Layout -----------------------------------------------------------------------------------
    def reset_document(self) -> None:
        self.sizes = []
        for index in range(self.doc.pageCount()):
            size = self.doc.pagePointSize(index)
            self.sizes.append((max(1.0, size.width()), max(1.0, size.height())))
        self._images.clear()
        self._pending.clear()
        self._lines = {}
        self.selection = None
        self.relayout()

    @property
    def unit(self) -> float:
        """Pixel pro Punkt bei 100 % (Bildschirm-DPI statt 72)."""
        return self.logicalDpiY() / pdfdoc.POINTS_PER_INCH

    def scale(self) -> float:
        width = self.viewport().width()
        if self.zoom_mode == "width" and self.sizes:
            return pdfdoc.fit_width_scale(self.sizes, width)
        if self.zoom_mode == "page" and self.sizes:
            return pdfdoc.fit_page_scale(self.sizes[self.current_page], width, self.viewport().height())
        return self.zoom * self.unit

    def zoom_percent(self) -> int:
        return round(self.scale() / self.unit * 100)

    def relayout(self, keep_page: bool = True) -> None:
        page, offset = self.current_page, 0.0
        if keep_page and self.layout_ is not None and self.layout_.pages:
            rect = self.layout_.pages[min(page, len(self.layout_.pages) - 1)]
            offset = (self.verticalScrollBar().value() - rect.y) / max(1.0, rect.height)
        self.layout_ = PageLayout(self.sizes, self.scale(), self.viewport().width())
        bar = self.verticalScrollBar()
        bar.setRange(0, max(0, int(self.layout_.height - self.viewport().height())))
        bar.setPageStep(self.viewport().height())
        bar.setSingleStep(40)
        hbar = self.horizontalScrollBar()
        hbar.setRange(0, max(0, int(self.layout_.width - self.viewport().width())))
        hbar.setPageStep(self.viewport().width())
        if keep_page and self.layout_.pages:
            rect = self.layout_.pages[min(page, len(self.layout_.pages) - 1)]
            bar.setValue(int(rect.y + offset * rect.height))
        self.viewport().update()
        self.zoom_changed.emit()

    def set_zoom(self, mode: str, zoom: float | None = None) -> None:
        self.zoom_mode = mode
        if zoom is not None:
            self.zoom = max(pdfdoc.MIN_ZOOM, min(pdfdoc.MAX_ZOOM, zoom))
        self.relayout()

    def zoom_step(self, direction: int) -> None:
        current = self.scale() / self.unit
        steps = [z for z in ZOOM_STEPS if (z > current + 0.001 if direction > 0 else z < current - 0.001)]
        if steps:
            self.set_zoom("custom", steps[0] if direction > 0 else steps[-1])

    # ---- Navigation -------------------------------------------------------------------------------
    def _track_page(self, value: int) -> None:
        if self.layout_ is None or not self.layout_.pages:
            return
        page = self.layout_.page_at_y(value + self.viewport().height() / 3)
        if page != self.current_page:
            self.current_page = page
            self.page_changed.emit(page)
        self.viewport().update()

    def go_to(self, page: int, location: QPointF | None = None) -> None:
        if self.layout_ is None or not self.layout_.pages:
            return
        page = max(0, min(page, len(self.layout_.pages) - 1))
        rect = self.layout_.pages[page]
        y = rect.y - pdfdoc.PAGE_GAP / 2
        if location is not None and (location.y() > 0 or location.x() > 0):
            y = rect.y + location.y() * self.layout_.scale - self.viewport().height() / 4
        self.verticalScrollBar().setValue(int(y))
        self.current_page = page
        self.page_changed.emit(page)

    # ---- Rendern ----------------------------------------------------------------------------------
    def _image(self, index: int, width: int):
        key = (index, width)
        image = self._images.get(key)
        if image is not None:
            self._images.move_to_end(key)
            return image
        if key not in self._pending.values():
            dpr = self.devicePixelRatioF()
            w, h = self.sizes[index]
            size = QSize(int(width * dpr), int(width * dpr * h / w))
            request = self.renderer.requestPage(index, size, self.options)
            self._pending[request] = key
        # Ersatz: gleiche Seite in anderer Größe (beim Zoomen), sonst nichts
        for (page, _w), other in reversed(self._images.items()):
            if page == index:
                return other
        return None

    def _on_rendered(self, page: int, _size, image, _options, request: int) -> None:
        key = self._pending.pop(request, None)
        if key is None:
            return
        image.setDevicePixelRatio(self.devicePixelRatioF())
        self._images[key] = image
        while len(self._images) > CACHE_IMAGES:
            self._images.popitem(last=False)
        self.viewport().update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor(COLORS.bg))
        if self.layout_ is None:
            return
        dx, dy = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        scale = self.layout_.scale
        for page in self.layout_.visible(dy, dy + self.viewport().height()):
            target = QRectF(page.x - dx, page.y - dy, page.width, page.height)
            painter.fillRect(target, QColor(PAGE_WHITE))
            image = self._image(page.index, int(page.width))
            if image is not None:
                painter.drawImage(target, image)
            painter.setPen(Qt.PenStyle.NoPen)
            for index, rects in self.highlights:
                if index == page.index:
                    painter.setBrush(_alpha(COLORS.paper_match, 150))
                    for r in rects:
                        painter.drawRect(QRectF(target.x() + r.x() * scale, target.y() + r.y() * scale,
                                                r.width() * scale, r.height() * scale))
            if self.current_highlight is not None and self.current_highlight[0] == page.index:
                painter.setBrush(_alpha(COLORS.warning, 140))
                for r in self.current_highlight[1]:
                    painter.drawRect(QRectF(target.x() + r.x() * scale, target.y() + r.y() * scale,
                                            r.width() * scale, r.height() * scale))
            if self.selection is not None and self.selection_page == page.index:
                painter.setBrush(QColor(COLORS.accent).lighter(130))
                painter.setOpacity(0.35)
                for polygon in self.selection.bounds():
                    painter.drawPolygon(QPolygonF([QPointF(target.x() + p.x() * scale, target.y() + p.y() * scale)
                                                   for p in polygon]))
                painter.setOpacity(1.0)
        painter.end()

    # ---- Auswahl ----------------------------------------------------------------------------------
    def _doc_pos(self, event) -> tuple[float, float]:
        return (event.position().x() + self.horizontalScrollBar().value(),
                event.position().y() + self.verticalScrollBar().value())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.layout_ is not None:
            hit = self.layout_.hit(*self._doc_pos(event))
            self._drag_start = hit
            if self.selection is not None:
                self.selection = None
                self.selection_changed.emit()
                self.viewport().update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None or self.layout_ is None:
            return
        page, sx, sy = self._drag_start
        ex, ey = self.layout_.clamp_hit(page, *self._doc_pos(event))
        self.selection = self._select(page, (sx, sy), (ex, ey))
        self.selection_page = page
        self.viewport().update()

    def _line_boxes(self, page: int) -> list[tuple[float, float, float, float]]:
        """Textzeilen einer Seite (ein PDFium-Aufruf, gecacht) – Ziel für das Einrasten der Auswahl."""
        boxes = self._lines.get(page)
        if boxes is None:
            boxes = []
            for polygon in self.doc.getAllText(page).bounds():
                rect = polygon.boundingRect()
                boxes.append((rect.left(), rect.top(), rect.right(), rect.bottom()))
            self._lines[page] = boxes
        return boxes

    def _select(self, page: int, start: tuple[float, float], end: tuple[float, float]):
        """Auswahl zwischen zwei Punkten; beide rasten auf die nächste Textzeile ein (PDFium trifft sonst nur,
        wenn der Punkt genau auf einem Zeichen liegt)."""
        lines = self._line_boxes(page)
        a, b = pdfdoc.snap_to_lines(lines, *start), pdfdoc.snap_to_lines(lines, *end)
        if a is None or b is None:
            return None
        for nudge in (0.0, 1.5, -1.5, 3.0, -3.0):
            selection = self.doc.getSelection(page, QPointF(a[0] + nudge, a[1]), QPointF(b[0] - nudge, b[1]))
            if selection.isValid() and selection.text():
                return selection
        return None

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_start is not None:
            self._drag_start = None
            self.selection_changed.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Doppelklick markiert die ganze Seite nicht – nur das Wort darunter über eine kleine Auswahl."""
        if self.layout_ is None:
            return
        hit = self.layout_.hit(*self._doc_pos(event))
        if hit is None:
            return
        page, x, y = hit
        selection = self._select(page, (x - 1, y), (x + 1, y))
        if selection is not None:
            self.selection, self.selection_page = selection, page
            self.selection_changed.emit()
            self.viewport().update()

    def selected_text(self) -> str:
        return self.selection.text() if self.selection is not None else ""

    def select_all_on_page(self) -> None:
        if not self.sizes:
            return
        selection = self.doc.getAllText(self.current_page)
        if selection.isValid() and selection.text():
            self.selection, self.selection_page = selection, self.current_page
            self.selection_changed.emit()
            self.viewport().update()

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            if self.selected_text():
                QApplication.clipboard().setText(self.selected_text())
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all_on_page()
            return
        bar = self.verticalScrollBar()
        keys = {Qt.Key.Key_PageDown: bar.pageStep(), Qt.Key.Key_PageUp: -bar.pageStep(), Qt.Key.Key_Space: bar.pageStep(),
                Qt.Key.Key_Down: bar.singleStep(), Qt.Key.Key_Up: -bar.singleStep()}
        if event.key() in keys:
            bar.setValue(bar.value() + keys[event.key()])
            return
        if event.key() == Qt.Key.Key_Home:
            self.go_to(0)
            return
        if event.key() == Qt.Key.Key_End:
            self.go_to(len(self.sizes) - 1)
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_step(1 if event.angleDelta().y() > 0 else -1)
            return
        super().wheelEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.relayout()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        self.viewport().update()

    def _context_menu(self, pos) -> None:
        menu = style_menu(QMenu(self))
        has = bool(self.selected_text())
        copy = menu.addAction("Kopieren", lambda: QApplication.clipboard().setText(self.selected_text()))
        copy.setEnabled(has)
        quote = menu.addAction("Als Zitat in Notiz einfügen", self.quote_requested.emit)
        quote.setEnabled(has)
        menu.addSeparator()
        menu.addAction("Ganze Seite markieren", self.select_all_on_page)
        menu.exec(self.viewport().mapToGlobal(pos))


class PdfPage(ViewerPage):
    kind = "pdf"
    icon_name = "file-type"
    quote_requested = Signal(str)          # fertiges Markdown-Zitat

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.doc = QPdfDocument(self)
        self._buffer: QBuffer | None = None
        self.error = ""
        self.canvas = _PdfCanvas(self.doc)
        self.canvas.page_changed.connect(self._on_page)
        self.canvas.zoom_changed.connect(self._on_zoom)
        self.canvas.selection_changed.connect(self._on_selection)
        self.canvas.quote_requested.connect(self.quote)

        self.bookmarks = QPdfBookmarkModel(self)
        self.bookmarks.setDocument(self.doc)
        self.outline = QTreeView()
        self.outline.setObjectName("PdfOutline")
        self.outline.setModel(self.bookmarks)
        self.outline.setHeaderHidden(True)
        self.outline.clicked.connect(self._bookmark_clicked)
        self.outline.activated.connect(self._bookmark_clicked)

        self.search = QPdfSearchModel(self)
        self.search.setDocument(self.doc)
        self.search_index = -1
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._run_search)
        self.search.modelReset.connect(self._results_changed)
        self.search.rowsInserted.connect(lambda *_a: self._results_changed())

        outline_button = IconButton("bookmark", "Lesezeichen ein/aus")
        outline_button.setCheckable(True)
        outline_button.toggled.connect(self.outline.setVisible)
        self.outline_button = outline_button
        prev_page = IconButton("chevron-up", "Vorige Seite")
        prev_page.clicked.connect(lambda: self.canvas.go_to(self.canvas.current_page - 1))
        next_page = IconButton("chevron-down", "Nächste Seite")
        next_page.clicked.connect(lambda: self.canvas.go_to(self.canvas.current_page + 1))
        self.page_field = QLineEdit()
        self.page_field.setFixedWidth(56)
        self.page_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_field.setToolTip("Seite (Nummer oder Seitenbezeichnung)  Ctrl+G")
        self.page_field.returnPressed.connect(self._jump_page)
        self.page_count = QLabel()
        self.page_count.setObjectName("DataInfo")
        self.zoom_box = QComboBox()
        self.zoom_box.addItem("Seitenbreite", ("width", None))
        self.zoom_box.addItem("Ganze Seite", ("page", None))
        for z in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
            self.zoom_box.addItem(f"{round(z * 100)} %", ("custom", z))
        self.zoom_box.activated.connect(self._zoom_chosen)
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Im PDF suchen …")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(lambda _t: self._search_timer.start())
        self.search_field.returnPressed.connect(lambda: self.next_result(1))
        prev_hit = IconButton("chevron-left", "Vorheriger Treffer  Shift+F3")
        prev_hit.clicked.connect(lambda: self.next_result(-1))
        next_hit = IconButton("chevron-right", "Nächster Treffer  F3")
        next_hit.clicked.connect(lambda: self.next_result(1))
        self.hits_label = QLabel()
        self.hits_label.setObjectName("DataInfo")
        self.quote_button = IconButton("quote", "Markierten Text als Zitat in die Notiz im anderen Teil einfügen")
        self.quote_button.clicked.connect(self.quote)
        self.quote_button.setEnabled(False)

        strip = QFrame()
        strip.setObjectName("DataBar")
        bar = QHBoxLayout(strip)
        bar.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        bar.setSpacing(SPACING.sm)
        for widget in (outline_button, prev_page, next_page, self.page_field, self.page_count, self.zoom_box):
            bar.addWidget(widget)
        bar.addSpacing(SPACING.md)
        bar.addWidget(self.search_field, 1)
        for widget in (prev_hit, next_hit, self.hits_label, self.quote_button):
            bar.addWidget(widget)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("PreviewSplitter")
        self.splitter.addWidget(self.outline)
        self.splitter.addWidget(self.canvas)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([220, 900])
        self.outline.setVisible(False)
        frame = QFrame()
        frame.setObjectName("DataFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        frame_layout.addWidget(strip)
        frame_layout.addWidget(self.splitter, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.md, SPACING.lg, SPACING.lg)
        layout.addWidget(frame)
        for sequence, slot in (("Ctrl+G", self._focus_page), ("F3", lambda: self.next_result(1)),
                               ("Shift+F3", lambda: self.next_result(-1))):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
        self._load()

    # ---- Laden ------------------------------------------------------------------------------------
    def _load(self, password: str = "") -> None:
        self.doc.close()
        if password:
            self.doc.setPassword(password)
        size = self.path.stat().st_size
        if size <= IN_MEMORY_LIMIT:
            data = QByteArray(self.path.read_bytes())      # Datei gleich wieder zu (Windows: umbenennbar)
            self._buffer = QBuffer(self)
            self._buffer.setData(data)
            self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self.doc.load(self._buffer)
        else:
            self.doc.load(str(self.path))
        if self.doc.error() == QPdfDocument.Error.IncorrectPassword:
            text, ok = QInputDialog.getText(self, "Passwortgeschütztes PDF", f"Passwort für „{self.path.name}“:",
                                            QLineEdit.EchoMode.Password)
            if ok and text:
                self._load(text)
                return
            self.error = "Passwortgeschützt – nicht geöffnet"
        elif self.doc.error() != QPdfDocument.Error.None_:
            self.error = f"PDF lässt sich nicht öffnen ({self.doc.error().name})"
        else:
            self.error = ""
        self.canvas.reset_document()
        has_outline = self.bookmarks.rowCount(QModelIndex()) > 0
        self.outline_button.setEnabled(has_outline)
        self.outline_button.setChecked(has_outline)
        self.page_count.setText(f"/ {self.doc.pageCount()}")
        self._on_page(0)
        self.status_changed.emit()

    # ---- Seiten, Zoom, Lesezeichen ------------------------------------------------------------------
    def page_label(self, index: int) -> str:
        label = self.doc.pageLabel(index) if 0 <= index < self.doc.pageCount() else ""
        return label or str(index + 1)

    def _on_page(self, index: int) -> None:
        self.page_field.setText(self.page_label(index))
        self.status_changed.emit()

    def _on_zoom(self) -> None:
        """Auswahlfeld nachziehen (Ctrl+Mausrad, Ctrl+Plus/Minus); freie Stufen als eigener Eintrag am Ende."""
        mode, zoom = self.canvas.zoom_mode, round(self.canvas.zoom, 2)
        index = next((i for i in range(self.zoom_box.count())
                      if self.zoom_box.itemData(i)[0] == mode and (mode != "custom" or self.zoom_box.itemData(i)[1] == zoom)), -1)
        if index < 0:
            if self.zoom_box.itemData(self.zoom_box.count() - 1)[0] == "free":
                self.zoom_box.removeItem(self.zoom_box.count() - 1)
            self.zoom_box.addItem(f"{self.canvas.zoom_percent()} %", ("free", zoom))
            index = self.zoom_box.count() - 1
        self.zoom_box.setCurrentIndex(index)
        self.status_changed.emit()

    def _zoom_chosen(self, index: int) -> None:
        mode, zoom = self.zoom_box.itemData(index)
        self.canvas.set_zoom("custom" if mode == "free" else mode, zoom)

    def _focus_page(self) -> None:
        self.page_field.setFocus()
        self.page_field.selectAll()

    def _jump_page(self) -> None:
        text = self.page_field.text().strip()
        index = self.doc.pageIndexForLabel(text) if text else -1
        if index < 0 and text.isdigit():
            index = int(text) - 1
        if 0 <= index < self.doc.pageCount():
            self.canvas.go_to(index)
            self.canvas.setFocus()
        else:
            self.page_field.setText(self.page_label(self.canvas.current_page))

    def _bookmark_clicked(self, index) -> None:
        page = index.data(int(QPdfBookmarkModel.Role.Page))
        location = index.data(int(QPdfBookmarkModel.Role.Location))
        if isinstance(page, int):
            self.canvas.go_to(page, location if isinstance(location, QPointF) else None)

    def zoom_step(self, direction: int) -> None:
        self.canvas.zoom_step(direction)

    # ---- Suche ------------------------------------------------------------------------------------
    def focus_search(self) -> None:
        self.search_field.setFocus()
        self.search_field.selectAll()

    def _run_search(self) -> None:
        self.search_index = -1
        self.search.setSearchString(self.search_field.text())
        self._results_changed()

    def _results_changed(self) -> None:
        count = self.search.rowCount(QModelIndex()) if self.search_field.text() else 0
        highlights: dict[int, list] = {}
        for i in range(min(count, 2000)):
            link = self.search.resultAtIndex(i)
            highlights.setdefault(link.page(), []).extend(link.rectangles())
        self.canvas.highlights = list(highlights.items())
        if not self.search_field.text():
            self.hits_label.setText("")
        elif 0 <= self.search_index < count:
            self.hits_label.setText(f"{self.search_index + 1} / {count}")
        else:
            self.hits_label.setText(f"{count} Treffer" if count else "Keine Treffer")
        if count and self.search_index < 0:
            self.next_result(1)
        self.canvas.viewport().update()

    def next_result(self, direction: int) -> None:
        count = self.search.rowCount(QModelIndex()) if self.search_field.text() else 0
        if not count:
            return
        self.search_index = (self.search_index + direction) % count
        link = self.search.resultAtIndex(self.search_index)
        self.canvas.current_highlight = (link.page(), link.rectangles())
        self.canvas.go_to(link.page(), link.location())
        self.hits_label.setText(f"{self.search_index + 1} / {count}")
        self.canvas.viewport().update()

    # ---- Zitat ------------------------------------------------------------------------------------
    def _on_selection(self) -> None:
        self.quote_button.setEnabled(bool(self.canvas.selected_text()))
        self.status_changed.emit()

    def quote(self) -> None:
        text = self.canvas.selected_text()
        if not text:
            return
        markdown = pdfdoc.quote_markdown(text, self.path.name, self.page_label(self.canvas.selection_page))
        if markdown:
            self.quote_requested.emit(markdown)

    # ---- ViewerPage -----------------------------------------------------------------------------------
    def status_parts(self) -> list[str]:
        if self.error:
            return [self.error, human_size(self.path.stat().st_size) if self.path.exists() else "", "PDF-Dokument", ""]
        pages = self.doc.pageCount()
        selected = len(self.canvas.selected_text())
        return [f"Seite {self.page_label(self.canvas.current_page)} ({self.canvas.current_page + 1} / {pages})",
                human_size(self.path.stat().st_size) if self.path.exists() else "",
                f"{selected} Zeichen markiert" if selected else "PDF · nur lesen",
                f"{self.canvas.zoom_percent()} %"]

    def reload(self) -> None:
        page = self.canvas.current_page
        self._load()
        self.canvas.go_to(page)

    def retheme(self) -> None:
        self.canvas.viewport().update()

    def shutdown(self) -> None:
        self.doc.close()
