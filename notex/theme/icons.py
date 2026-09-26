"""Kleine, flache Icons, die zur Palette passen – gezeichnet statt aus Dateien geladen.

QFileSystemModel würde sonst die bunten Windows-Icons anzeigen, die im
dunklen Theme fremd wirken.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFileIconProvider

from notex.theme.theme import COLORS


def _pixmap(size: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


@lru_cache(maxsize=None)
def folder_icon(size: int = 16) -> QIcon:
    pixmap, painter = _pixmap(size)
    color = QColor(COLORS["text_muted"])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    s = size
    # Lasche oben links + Korpus
    painter.drawRoundedRect(QRectF(s * 0.1, s * 0.2, s * 0.4, s * 0.2), 1, 1)
    painter.drawRoundedRect(QRectF(s * 0.1, s * 0.3, s * 0.8, s * 0.5), 1.5, 1.5)
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=None)
def file_icon(size: int = 16) -> QIcon:
    pixmap, painter = _pixmap(size)
    color = QColor(COLORS["text_muted"])
    pen = QPen(color)
    pen.setWidthF(1.2)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    s = size
    painter.drawRoundedRect(QRectF(s * 0.2, s * 0.12, s * 0.6, s * 0.76), 1.5, 1.5)
    for y in (0.4, 0.55, 0.7):  # drei "Textzeilen"
        painter.drawLine(QRectF(s * 0.32, s * y, s * 0.36, 0).topLeft(), QRectF(s * 0.68, s * y, 0, 0).topLeft())
    painter.end()
    return QIcon(pixmap)


class FlatIconProvider(QFileIconProvider):
    """Liefert dem QFileSystemModel unsere Icons statt der System-Icons."""

    def icon(self, info_or_type):  # type: ignore[override]
        # Qt ruft die Methode mal mit QFileInfo, mal mit einem IconType-Enum auf.
        if isinstance(info_or_type, QFileIconProvider.IconType):
            if info_or_type in (QFileIconProvider.IconType.Folder, QFileIconProvider.IconType.Drive):
                return folder_icon()
            return file_icon()
        return folder_icon() if info_or_type.isDir() else file_icon()
