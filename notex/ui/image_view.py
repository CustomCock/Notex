"""Bild-Tab: einpassen/100 %, Zoom mit dem Mausrad (zur Mausposition), Verschieben mit gedrückter Maus.

Dunkler, neutraler Hintergrund (unabhängig vom Blatt), damit Farben und Transparenz gut beurteilt werden können.
SVG wird über QSvgRenderer gerastert (scharf auch beim Zoomen bis 800 %).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from notex.theme.tokens import SPACING
from notex.ui.viewer_page import ViewerPage, human_size

MIN_ZOOM, MAX_ZOOM = 0.05, 8.0
BACKDROP = "#1b1b1b"


class _View(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setBackgroundBrush(QBrush(QColor(BACKDROP)))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing)
        self.fit_mode = True

    def zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, factor: float) -> None:
        factor = max(MIN_ZOOM, min(MAX_ZOOM, factor))
        self.resetTransform()
        self.scale(factor, factor)
        self.zoom_changed.emit(factor)

    def wheelEvent(self, event) -> None:
        steps = event.angleDelta().y() / 120
        if steps:
            self.fit_mode = False
            self.set_zoom(self.zoom() * (1.15 ** steps))
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit()

    def fit(self) -> None:
        rect = self.sceneRect()
        if rect.isEmpty():
            return
        self.fit_mode = True
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self.zoom() > 1.0:          # kleine Bilder nicht aufblasen
            self.set_zoom(1.0)
        self.zoom_changed.emit(self.zoom())


class ImagePage(ViewerPage):
    kind = "image"
    icon_name = "image"

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.image_size = (0, 0)
        self.format = ""
        self.error = ""
        self.scene = QGraphicsScene(self)
        self.view = _View()
        self.view.setScene(self.scene)
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.addItem(self.item)
        self.fit_button = QPushButton("Einpassen")
        self.full_button = QPushButton("100 %")
        self.zoom_label = QLabel()
        self.zoom_label.setObjectName("SettingsNote")
        self.fit_button.clicked.connect(self.view.fit)
        self.full_button.clicked.connect(lambda: (setattr(self.view, "fit_mode", False), self.view.set_zoom(1.0)))
        self.view.zoom_changed.connect(lambda z: (self.zoom_label.setText(f"{round(z * 100)} %"), self.status_changed.emit()))
        bar = QHBoxLayout()
        bar.setContentsMargins(SPACING.md, SPACING.xs, SPACING.md, SPACING.xs)
        bar.addWidget(self.fit_button)
        bar.addWidget(self.full_button)
        bar.addWidget(self.zoom_label)
        bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(bar)
        layout.addWidget(self.view, 1)
        self.load()

    def load(self) -> None:
        self.error = ""
        pixmap = QPixmap()
        if self.path.suffix.lower() == ".svg":
            pixmap = self._render_svg()
        else:
            reader = QImageReader(str(self.path))
            reader.setAutoTransform(True)       # EXIF-Drehung von Handyfotos beachten
            self.format = bytes(reader.format()).decode().upper()
            image = reader.read()
            if image.isNull():
                self.error = reader.errorString()
            else:
                pixmap = QPixmap.fromImage(image)
        self.item.setPixmap(pixmap)
        if self.format != "SVG":
            self.image_size = (pixmap.width(), pixmap.height()) if not pixmap.isNull() else (0, 0)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        if pixmap.isNull():
            self.scene.addText(f"Bild kann nicht angezeigt werden: {self.error or 'unbekanntes Format'}").setDefaultTextColor(QColor("#cccccc"))
        self.view.fit()

    def _render_svg(self) -> QPixmap:
        from PySide6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(str(self.path))
        self.format = "SVG"
        if not renderer.isValid():
            self.error = "ungültiges SVG"
            return QPixmap()
        size = renderer.defaultSize()
        if size.isEmpty():
            size = renderer.viewBox().size()
        scale = max(1.0, 1024 / max(1, max(size.width(), size.height())))   # scharf rastern
        pixmap = QPixmap(int(size.width() * scale), int(size.height() * scale))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.image_size = (size.width(), size.height())
        return pixmap

    def status_parts(self) -> list[str]:
        parts = []
        if self.image_size[0]:
            parts.append(f"{self.image_size[0]} × {self.image_size[1]} px")
        try:
            parts.append(human_size(self.path.stat().st_size))
        except OSError:
            pass
        if self.format:
            parts.append(self.format)
        parts.append(f"{round(self.view.zoom() * 100)} %")
        return parts
