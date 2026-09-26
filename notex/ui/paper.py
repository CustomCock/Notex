"""Das Blatt: weiße, abgerundete Fläche mit weichem Schatten auf dem dunklen Tisch.

EditorPage ist der Inhalt eines Tabs. Es zentriert das PaperFrame (mit dem Editor)
und zeichnet darunter den Schatten selbst – ein QGraphicsDropShadowEffect würde
den Editor bei jedem Tastendruck komplett neu rastern und blurren.

Blatt-Modus: maximale Textbreite (~90 Zeichen), Blatt zentriert.
Volle Breite: das Blatt füllt den Bereich.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from notex.core.markdown import toggle_task_line
from notex.theme.tokens import LAYOUT, RADIUS, SPACING
from notex.ui.editor import Editor
from notex.ui.preview import MarkdownPreview
from notex.ui.toolbar import EditorToolbar

VIEW_MODES = ("edit", "preview", "split")
PREVIEW_DEBOUNCE_MS = 300

SHADOW_BLUR = 28      # wie weit der Schatten nach außen reicht
SHADOW_OFFSET_Y = 8
QWIDGETSIZE_MAX = 16777215


class PaperFrame(QFrame):
    """Die weiße Fläche. Das QSS malt Hintergrund + Radius, der Editor ist transparent."""

    def __init__(self, editor: Editor) -> None:
        super().__init__()
        self.setObjectName("PaperFrame")
        self.editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(editor)


def _shadow_pixmap(width: int, height: int, dpr: float) -> QPixmap:
    """Weicher Schatten als gestapelte, immer kleinere abgerundete Rechtecke.

    Jede Schicht ist fast durchsichtig; übereinander ergeben sie einen sanften Verlauf
    von außen (kaum sichtbar) nach innen (dunkler). Kein echter Gauß-Blur, sieht aber
    bei 28 Schichten genauso weich aus und kostet beim Malen nichts.
    """
    pixmap = QPixmap(int(width * dpr), int(height * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    layers = SHADOW_BLUR
    for i in range(layers):
        inset = i
        # quadratisch ansteigende Deckkraft: außen sehr schwach, innen deutlicher
        alpha = LAYOUT.paper_shadow_alpha * ((i + 1) / layers) ** 2 / layers * 2
        painter.setBrush(QColor(0, 0, 0, max(1, int(alpha))))
        rect = QRectF(inset, inset + SHADOW_OFFSET_Y, width - 2 * inset, height - 2 * inset)
        painter.drawRoundedRect(rect, RADIUS.panel + (layers - i) * 0.5, RADIUS.panel + (layers - i) * 0.5)
    painter.end()
    return pixmap


class PreviewFrame(QFrame):
    """Zweites Blatt für die Markdown-Vorschau, gleiche Optik wie PaperFrame."""

    def __init__(self, preview: MarkdownPreview) -> None:
        super().__init__()
        self.setObjectName("PaperFrame")
        self.preview = preview
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(preview)


class EditorPage(QWidget):
    link_requested = Signal(str)       # Ziel aus der Vorschau: "rel/pfad#Überschrift" oder Wiki-Name
    view_mode_changed = Signal(str)

    def __init__(self, editor: Editor, paper_mode: bool, toolbar: EditorToolbar | None = None,
                 root: Path | None = None) -> None:
        super().__init__()
        self.setObjectName("EditorPage")
        self.editor = editor
        self.frame = PaperFrame(editor)
        self.toolbar = toolbar
        self.root = root or editor.path.parent
        self.preview: MarkdownPreview | None = None
        self.preview_frame: PreviewFrame | None = None
        self.view_mode = "edit"
        self.sync_scroll = True
        self._shadow: QPixmap | None = None
        self._shadow_key: tuple = ()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._syncing = False

        # Spalte: Bearbeitungsleiste oben, darunter Blatt (+ Vorschau-Blatt daneben) – gleich breit
        self.column = QWidget()
        column_layout = QVBoxLayout(self.column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        if toolbar is not None:
            column_layout.addWidget(toolbar)
            self.frame.setProperty("attached", True)   # oben eckig, weil die Leiste den Radius trägt
            toolbar.visibility_changed.connect(lambda _v: self.update())
        self.body = QSplitter(Qt.Orientation.Horizontal)
        self.body.setObjectName("PreviewSplitter")
        self.body.setHandleWidth(SPACING.sm)
        self.body.setChildrenCollapsible(False)
        self.body.addWidget(self.frame)
        column_layout.addWidget(self.body, 1)

        margin = LAYOUT.paper_margin
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin - SHADOW_OFFSET_Y // 2, margin, margin)
        layout.addStretch(1)
        layout.addWidget(self.column, 0)
        layout.addStretch(1)
        self._layout = layout
        self.set_paper_mode(paper_mode)

    def set_paper_mode(self, enabled: bool) -> None:
        self.paper_mode = enabled
        if enabled:
            # Maximale Textbreite in Zeichen + Zeilennummern + rechter Rand + Scrollbar.
            # Das ist ein Maximum: wird das Fenster schmaler, schrumpft das Blatt mit.
            # Geteilte Ansicht: zwei Blätter nebeneinander, also doppelt so breit.
            text_width = int(LAYOUT.paper_max_columns * self.editor.char_width())
            width = text_width + self.editor.gutter_width() + SPACING.xl + LAYOUT.scrollbar + SPACING.sm
            if self.view_mode == "split":
                width = 2 * width + self.body.handleWidth()
            self.column.setMaximumWidth(width)
        else:
            self.column.setMaximumWidth(QWIDGETSIZE_MAX)
        # Das Blatt bekommt (fast) allen Platz bis zu seiner Maximalbreite, der Rest
        # verteilt sich gleichmäßig auf beide Seiten -> zentriert
        self._layout.setStretch(0, 1)
        self._layout.setStretch(1, 1000)
        self._layout.setStretch(2, 1)
        self.update()

    def retheme(self) -> None:
        self._fit_padding()
        self._shadow = None
        self.editor.retheme()
        if self.preview is not None:
            self.preview.set_fonts(self.editor.font().family(), self.editor.font_size)
            self.preview.retheme()
        self.refresh_width()
        self.update()

    # ---- Markdown-Vorschau ---------------------------------------------------------
    @property
    def supports_preview(self) -> bool:
        return self.editor.path.suffix.lower() in (".md", ".markdown")

    def set_view_mode(self, mode: str) -> None:
        """"edit" (nur Blatt), "preview" (nur Vorschau) oder "split" (beides nebeneinander)."""
        if mode not in VIEW_MODES or not self.supports_preview and mode != "edit":
            mode = "edit"
        if mode != "edit" and self.preview is None:
            self._create_preview()
        self.view_mode = mode
        self.frame.setVisible(mode != "preview")
        if self.preview_frame is not None:
            self.preview_frame.setVisible(mode != "edit")
        if mode != "edit":
            self._preview_timer.stop()
            self._refresh_preview()
            if mode == "split":
                self.body.setSizes([1, 1])
        self.refresh_width()
        (self.preview if mode == "preview" and self.preview is not None else self.editor).setFocus()
        self.view_mode_changed.emit(mode)

    def cycle_view_mode(self) -> str:
        index = VIEW_MODES.index(self.view_mode) if self.view_mode in VIEW_MODES else 0
        self.set_view_mode(VIEW_MODES[(index + 1) % len(VIEW_MODES)])
        return self.view_mode

    def _create_preview(self) -> None:
        self.preview = MarkdownPreview(self.root)
        self.preview_frame = PreviewFrame(self.preview)
        if self.toolbar is not None:
            self.preview_frame.setProperty("attached", True)   # wie das Blatt: oben eckig unter der Leiste
        self.body.addWidget(self.preview_frame)
        self.preview.set_fonts(self.editor.font().family(), self.editor.font_size)
        self.preview.set_padding(self.editor._padding)
        self.preview.open_requested.connect(self.link_requested)
        self.preview.toggle_requested.connect(self._toggle_task)
        self.preview.scrolled.connect(self._on_preview_scrolled)
        self.editor.textChanged.connect(self._schedule_preview)
        self.editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)

    def _schedule_preview(self) -> None:
        if self.view_mode != "edit":
            self._preview_timer.start()

    def _refresh_preview(self) -> None:
        if self.preview is not None and self.view_mode != "edit":
            self.preview.set_source(self.editor.toPlainText(), self.editor.path)

    def _toggle_task(self, line: int) -> None:
        new_text = toggle_task_line(self.editor.toPlainText(), line)
        if new_text is None:
            return
        new_line = new_text.split("\n")[line]
        self.editor._grouped(lambda: self.editor._replace_blocks(line, line, [new_line]))
        self._preview_timer.stop()
        self._refresh_preview()

    def _on_editor_scrolled(self, value: int) -> None:
        if self._syncing or not self.sync_scroll or self.view_mode != "split" or self.preview is None:
            return
        bar = self.editor.verticalScrollBar()
        if bar.maximum():
            self._syncing = True
            self.preview.set_scroll_fraction(value / bar.maximum())
            self._syncing = False

    def _on_preview_scrolled(self, fraction: float) -> None:
        if self._syncing or not self.sync_scroll or self.view_mode != "split":
            return
        bar = self.editor.verticalScrollBar()
        self._syncing = True
        bar.setValue(round(fraction * bar.maximum()))
        self._syncing = False

    def refresh_width(self) -> None:
        """Nach Zoom: die maximale Breite hängt von der Zeichenbreite ab."""
        self.set_paper_mode(self.paper_mode)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_padding()

    def _fit_padding(self) -> None:
        """Bei wenig Platz Innenabstand und Rand herunterskalieren (Minimum 16 px innen, 8 px außen)."""
        width = self.width()
        full, tight = 760, 420      # ab `full` Pixeln volle Abstände, bei `tight` die Minima
        t = min(1.0, max(0.0, (width - tight) / (full - tight)))
        margin = round(SPACING.sm + (LAYOUT.paper_margin - SPACING.sm) * t)
        padding = round(SPACING.lg + (LAYOUT.paper_padding - SPACING.lg) * t)
        self._layout.setContentsMargins(margin, max(SPACING.sm, margin - SHADOW_OFFSET_Y // 2), margin, margin)
        self.editor.set_padding(padding)
        if self.preview is not None:
            self.preview.set_padding(max(SPACING.lg, padding))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        geo: QRect = self.column.geometry()   # Leiste + Blatt werfen einen gemeinsamen Schatten
        if geo.isEmpty() or not LAYOUT.paper_shadow or LAYOUT.paper_shadow_alpha <= 0:
            return
        width, height = geo.width() + 2 * SHADOW_BLUR, geo.height() + 2 * SHADOW_BLUR
        dpr = self.devicePixelRatioF()
        key = (width, height, dpr, LAYOUT.paper_shadow_alpha, RADIUS.panel)
        if self._shadow is None or self._shadow_key != key:
            self._shadow = _shadow_pixmap(width, height, dpr)
            self._shadow_key = key
        painter = QPainter(self)
        painter.drawPixmap(geo.left() - SHADOW_BLUR, geo.top() - SHADOW_BLUR, self._shadow)
