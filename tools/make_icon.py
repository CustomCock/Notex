"""Rastert das App-Icon aus assets/notex.svg nach notex.png (256 px) und notex.ico (7 Größen).

Aufruf: python tools/make_icon.py   (braucht nur PySide6)
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "notex" / "assets"


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path, images: list[QImage]) -> None:
    """ICO mit PNG-komprimierten Einträgen (ab Windows Vista erlaubt, hält die Datei klein).
    Aufbau: 6-Byte-Header, 16 Byte pro Eintrag, dann die Bilddaten hintereinander."""
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
    renderer = QSvgRenderer(str(ASSETS / "notex.svg"))
    render(renderer, 256).save(str(ASSETS / "notex.png"))
    write_ico(ASSETS / "notex.ico", [render(renderer, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    print("geschrieben:", ASSETS / "notex.png", ASSETS / "notex.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
