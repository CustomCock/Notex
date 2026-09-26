"""Erzeugt das App-Icon (textbaum/assets/textbaum.ico + .png) aus einer kleinen Zeichnung.

Aufruf: python tools/make_icon.py
Braucht nur PySide6 – kein Grafikprogramm. Das Icon: ein dunkles Quadrat mit
einem hellen "Baum" aus drei Ebenen (Ordner -> Datei -> Zeilen).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import struct  # noqa: E402

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "textbaum" / "assets"


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1e1e1e"))
    painter.drawRoundedRect(QRectF(0, 0, s, s), s * 0.18, s * 0.18)

    pen = QPen(QColor("#d0d0d0"))
    pen.setWidthF(max(1.0, s * 0.07))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    # Stamm (senkrechte Linie links) und drei Äste nach rechts, wie ein Verzeichnisbaum
    x0, top, bottom = s * 0.28, s * 0.22, s * 0.78
    painter.drawLine(QRectF(x0, top, 0, 0).topLeft(), QRectF(x0, bottom, 0, 0).topLeft())
    for i, y in enumerate((0.36, 0.55, 0.74)):
        length = s * (0.42 - i * 0.08)
        painter.drawLine(QRectF(x0, s * y, 0, 0).topLeft(), QRectF(x0 + length, s * y, 0, 0).topLeft())
    painter.end()
    return image


def draw_close(color: str, size: int = 12) -> QImage:
    """Kleines "x" für den Schließen-Button der Tabs."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    m = size * 0.28
    painter.drawLine(QRectF(m, m, 0, 0).topLeft(), QRectF(size - m, size - m, 0, 0).topLeft())
    painter.drawLine(QRectF(size - m, m, 0, 0).topLeft(), QRectF(m, size - m, 0, 0).topLeft())
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path, images: list[QImage]) -> None:
    """Schreibt eine .ico mit mehreren Größen. Windows (ab Vista) erlaubt PNG-Daten
    in ICO-Einträgen, das hält die Datei klein. Aufbau: 6-Byte-Header,
    16 Byte pro Eintrag, dann die Bilddaten hintereinander."""
    entries, blobs = [], []
    offset = 6 + 16 * len(images)
    for image in images:
        data = png_bytes(image)
        size = image.width()
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<HHH", 0, 1, len(images)))
        handle.write(b"".join(entries))
        handle.write(b"".join(blobs))


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 – QPainter braucht eine laufende GUI-Anwendung
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    draw(256).save(str(OUT_DIR / "textbaum.png"))
    write_ico(OUT_DIR / "textbaum.ico", [draw(size) for size in (16, 24, 32, 48, 64, 128, 256)])
    draw_close("#8a8a8a").save(str(OUT_DIR / "close.png"))
    draw_close("#d0d0d0").save(str(OUT_DIR / "close-hover.png"))
    print("geschrieben:", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
