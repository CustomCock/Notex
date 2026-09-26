"""Lucide-Icons (ISC-Lizenz) als SVG, zur Laufzeit in Theme-Farbe eingefärbt.

Die SVGs benutzen `stroke="currentColor"`. Wir ersetzen das durch die gewünschte
Farbe und rendern per QSvgRenderer – dadurch bleiben die Icons auf jeder
DPI-Skalierung scharf, weil sie erst in der Zielgröße gerastert werden.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFileIconProvider

from notex.theme.tokens import COLORS

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    path = ICON_DIR / f"{name}.svg"
    if not path.exists():
        raise FileNotFoundError(f"Icon fehlt: {path.name}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _renderer(name: str, color: str, stroke_width: str) -> QSvgRenderer:
    svg = _svg_source(name).replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke_width}"')
    renderer = QSvgRenderer(svg.encode("utf-8"))
    renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
    return renderer


class SvgIconEngine(QIconEngine):
    """Rendert das SVG bei Bedarf in der angefragten Pixelgröße."""

    def __init__(self, name: str, color: str, disabled_color: str, stroke_width: str) -> None:
        super().__init__()
        self.name, self.color, self.disabled_color, self.stroke_width = name, color, disabled_color, stroke_width

    def _color_for(self, mode: QIcon.Mode) -> str:
        return self.disabled_color if mode == QIcon.Mode.Disabled else self.color

    def paint(self, painter: QPainter, rect, mode, state) -> None:
        _renderer(self.name, self._color_for(mode), self.stroke_width).render(painter, QRectF(rect))

    def pixmap(self, size: QSize, mode, state) -> QPixmap:
        if size.isEmpty():
            return QPixmap()   # z. B. während die Seitenleiste auf 0 px zufährt
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap

    def scaledPixmap(self, size: QSize, mode, state, scale: float) -> QPixmap:
        # Qt übergibt hier bereits die mit dem Device-Pixel-Ratio multiplizierte Größe
        return self.pixmap(size, mode, state)

    def clone(self) -> QIconEngine:
        return SvgIconEngine(self.name, self.color, self.disabled_color, self.stroke_width)


@lru_cache(maxsize=None)
def _icon(name: str, color: str, disabled: str, stroke_width: str) -> QIcon:
    return QIcon(SvgIconEngine(name, color, disabled, stroke_width))


def icon(name: str, color: str | None = None, stroke_width: str = "1.75") -> QIcon:
    """Ein eingefärbtes Lucide-Icon. Standard: gedämpfte Textfarbe des aktuellen Themes, 1.75 px Strich."""
    return _icon(name, color or COLORS.text_muted, COLORS.text_faint, stroke_width)


icon.cache_clear = _icon.cache_clear  # type: ignore[attr-defined]


def pixmap(name: str, size: int, color: str | None = None, dpr: float = 1.0) -> QPixmap:
    """Fertig gerastertes Icon für eigene paintEvents, DPI-korrekt."""
    pm = icon(name, color).pixmap(QSize(int(size * dpr), int(size * dpr)))
    pm.setDevicePixelRatio(dpr)
    return pm


def clear_cache() -> None:
    """Nach einem Theme-Wechsel: Icons werden beim nächsten Aufruf in den neuen Farben gerendert."""
    icon.cache_clear()
    _renderer.cache_clear()


class LucideIconProvider(QFileIconProvider):
    """Liefert dem QFileSystemModel Ordner-/Datei-Icons aus dem Lucide-Set."""

    def icon(self, info_or_type):  # type: ignore[override]
        if isinstance(info_or_type, QFileIconProvider.IconType):
            is_dir = info_or_type in (QFileIconProvider.IconType.Folder, QFileIconProvider.IconType.Drive)
        else:
            is_dir = info_or_type.isDir()
        return icon("folder" if is_dir else "file-text")
