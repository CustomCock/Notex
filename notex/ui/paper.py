"""Das Blatt: weiße, abgerundete Fläche mit weichem Schatten auf dem dunklen Tisch.

EditorPage ist der Inhalt eines Tabs. Es zentriert das PaperFrame (mit dem Editor)
und zeichnet darunter den Schatten selbst – ein QGraphicsDropShadowEffect würde
den Editor bei jedem Tastendruck komplett neu rastern und blurren.

Blatt-Modus: maximale Textbreite (~90 Zeichen), Blatt zentriert.
Volle Breite: das Blatt füllt den Bereich.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from notex.theme.tokens import LAYOUT, RADIUS, SPACING
from notex.ui.editor import Editor

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


class EditorPage(QWidget):
    def __init__(self, editor: Editor, paper_mode: bool) -> None:
        super().__init__()
        self.setObjectName("EditorPage")
        self.editor = editor
        self.frame = PaperFrame(editor)
        self._shadow: QPixmap | None = None
        self._shadow_key: tuple = ()

        margin = LAYOUT.paper_margin
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin - SHADOW_OFFSET_Y // 2, margin, margin)
        layout.addStretch(1)
        layout.addWidget(self.frame, 0)
        layout.addStretch(1)
        self._layout = layout
        self.set_paper_mode(paper_mode)

    def set_paper_mode(self, enabled: bool) -> None:
        self.paper_mode = enabled
        if enabled:
            # Maximale Textbreite in Zeichen + Zeilennummern + rechter Rand + Scrollbar.
            # Das ist ein Maximum: wird das Fenster schmaler, schrumpft das Blatt mit.
            text_width = int(LAYOUT.paper_max_columns * self.editor.char_width())
            self.frame.setMaximumWidth(text_width + self.editor.gutter_width() + SPACING.xl + LAYOUT.scrollbar + SPACING.sm)
        else:
            self.frame.setMaximumWidth(QWIDGETSIZE_MAX)
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
        self.refresh_width()
        self.update()

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

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        geo: QRect = self.frame.geometry()
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
