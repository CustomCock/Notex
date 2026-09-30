"""SVG aus dem Mermaid-Renderer (core/mermaid) in ein QImage zeichnen – für Vorschau, PDF-Export und „Als PNG
speichern“. Nutzt Qts eigenen SVG-Renderer (kein Browser, kein Skript)."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def svg_to_image(svg: str, width: float, height: float, scale: float = 1.0, background: str | None = None) -> QImage:
    """SVG in der Größe width×height (logische Pixel) mal `scale` rendern; scale = Pixeldichte für scharfe Bilder."""
    w, h = max(1, round(width * scale)), max(1, round(height * scale))
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background) if background else QColor(0, 0, 0, 0))
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if renderer.isValid():
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        renderer.render(painter, QRectF(0, 0, w, h))
        painter.end()
    image.setDevicePixelRatio(scale)
    return image
