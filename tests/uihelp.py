"""Gemeinsame Helfer für UI-Tests (offscreen): echtes Hauptfenster, Menüs auslesen, auf Threads warten.

Nur aus UI-Tests importieren – die Qt-freien Tests dürfen ohne PySide6 laufen.
"""
import struct
import time
import zlib
from pathlib import Path

from PySide6.QtWidgets import QApplication

FIXTURE_PCAP = Path(__file__).parent / "fixtures" / "beispiel_traffic.pcap"


def png_bytes() -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


def make_window(tmp_path: Path):
    """Hauptfenster mit allen Modulen an und einigen Beispieldateien in data/."""
    from notex.core.config import default_config
    from notex.core.modules import MODULES
    from notex.ui.main_window import MainWindow
    root = tmp_path / "data"
    root.mkdir()
    config = default_config()
    config["modules"] = {m.key: True for m in MODULES}
    window = MainWindow(root, config, on_save_config=lambda c: None)
    window.show()
    QApplication.processEvents()
    files = {
        "log": root / "server.log",
        "md": root / "notiz.md",
        "png": root / "bild.png",
        "pcap": root / "mitschnitt.pcap",
    }
    files["log"].write_text("2024-01-01 ERROR 10.0.0.5:443 fehlgeschlagen\n", encoding="utf-8")
    files["md"].write_text("# Notiz\n\nIP 192.168.1.10\n", encoding="utf-8")
    files["png"].write_bytes(png_bytes())
    files["pcap"].write_bytes(FIXTURE_PCAP.read_bytes())
    window.files = files
    return window


def close_window(window) -> None:
    for widget in QApplication.topLevelWidgets():
        if widget is not window and widget.isVisible():
            widget.close()
    window.close()
    window.deleteLater()
    QApplication.processEvents()


def wait_for(predicate, timeout: float = 10.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def leaves(menu):
    for action in menu.actions():
        if action.menu():
            yield from leaves(action.menu())
        elif not action.isSeparator():
            yield action


def label(action) -> str:
    return action.text().split("\t")[0]


def enabled_names(menu) -> list[str]:
    return [label(a) for a in leaves(menu) if a.isEnabled()]


def open_tools_menu(window) -> list[str]:
    window.tools_menu.aboutToShow.emit()
    QApplication.processEvents()
    return enabled_names(window.tools_menu)


def open_toolbar_menu(page) -> list[str]:
    page.toolbar.tools_button.menu_.aboutToShow.emit()
    QApplication.processEvents()
    return enabled_names(page.toolbar.tools_button.menu_)


def visible_windows() -> set:
    return {w for w in QApplication.topLevelWidgets() if w.isVisible()}


def capture_toasts(window, monkeypatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(window.toast, "show_message", lambda text, *a, **k: messages.append(text))
    return messages
