"""UI-Smoke-Tests mit echtem Hauptfenster (offscreen): Werkzeuge-Menü, Blatt-Leiste und Netzwerk-Werkzeuge
müssen nach Tab-Wechsel, Teilen und Neuöffnen sichtbar reagieren (R1/R3)."""
import os
import struct
import zlib
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402


def _png() -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEX_ROOT", str(tmp_path))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)          # modale Dialoge nie blockieren
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    app = QApplication.instance() or QApplication([])
    from notex.core.config import default_config
    from notex.core.modules import MODULES
    from notex.ui.main_window import MainWindow
    root = tmp_path / "data"
    root.mkdir()
    config = default_config()
    config["modules"] = {m.key: True for m in MODULES}
    window = MainWindow(root, config, on_save_config=lambda c: None)
    window.show()
    app.processEvents()
    window.files = {
        "log": _write(root / "server.log", "2024-01-01 ERROR 10.0.0.5:443 fehlgeschlagen\n"),
        "md": _write(root / "notiz.md", "# Notiz\n\nIP 192.168.1.10\n"),
        "png": root / "bild.png",
    }
    window.files["png"].write_bytes(_png())
    yield window
    for widget in QApplication.topLevelWidgets():
        if widget is not window and widget.isVisible():
            widget.close()
    window.close()
    window.deleteLater()
    app.processEvents()


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def leaves(menu):
    for action in menu.actions():
        if action.menu():
            yield from leaves(action.menu())
        elif not action.isSeparator():
            yield action


def enabled_names(menu) -> list[str]:
    return [a.text().split("\t")[0] for a in leaves(menu) if a.isEnabled()]


def open_tools_menu(win) -> list[str]:
    win.tools_menu.aboutToShow.emit()
    QApplication.processEvents()
    return enabled_names(win.tools_menu)


def open_toolbar_menu(page) -> list[str]:
    page.toolbar.tools_button.menu_.aboutToShow.emit()
    QApplication.processEvents()
    return enabled_names(page.toolbar.tools_button.menu_)


# ---- Geteilte Ansicht: Menüs gehören zum angeklickten Blatt -------------------------------------------------------
def test_split_toolbar_click_targets_its_own_sheet(win):
    win.tabs.open_file(win.files["log"])
    group2 = win.tabs.split(share_current=False)
    win.tabs.open_file(win.files["png"])
    QApplication.processEvents()
    assert win.tabs.active is group2 and win._current_file().name == "bild.png"

    log_page = win.tabs.groups[0].currentWidget()
    # Klick in die Leiste des Log-Blatts (Knöpfe nehmen keinen Fokus an) → dieses Blatt ist gemeint
    QTest.mouseClick(log_page.toolbar.strip, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
    QApplication.processEvents()
    assert win._current_file().name == "server.log"
    names = open_toolbar_menu(log_page)
    assert "Log-Auswertung" in names and "Live verfolgen" in names
    assert "Log-Auswertung" in open_tools_menu(win)


def test_toolbar_menu_activates_own_group_even_without_click(win):
    win.tabs.open_file(win.files["log"])
    win.tabs.split(share_current=False)
    win.tabs.open_file(win.files["png"])
    QApplication.processEvents()
    log_page = win.tabs.groups[0].currentWidget()
    assert "Log-Auswertung" in open_toolbar_menu(log_page)     # z. B. per Tastatur geöffnet
    assert win._current_file().name == "server.log"


# ---- Menüaufbau: kein Leck, kein leeres Menü bei Fehlern ------------------------------------------------------------
def test_tools_menu_rebuild_does_not_leak(win):
    from PySide6.QtWidgets import QMenu
    win.tabs.open_file(win.files["log"])
    open_tools_menu(win)
    QApplication.processEvents()
    before = len(win.tools_menu.findChildren(QMenu))
    for _ in range(30):
        open_tools_menu(win)
    from PySide6.QtCore import QEvent
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)   # deleteLater ausführen
    QApplication.processEvents()
    assert len(win.tools_menu.findChildren(QMenu)) <= before


def test_tools_menu_survives_broken_entry(win, monkeypatch):
    import sys
    from notex.ui import main_window as mw
    real_icon = mw.icon

    def flaky(name, *a, **k):
        if name == "radar":
            raise RuntimeError("Icon kaputt")
        return real_icon(name, *a, **k)
    monkeypatch.setattr(mw, "icon", flaky)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: errors.append(exc[1]))
    win.tabs.open_file(win.files["log"])
    names = open_tools_menu(win)
    assert "Log-Auswertung" in names and "Prüfsummen" in names          # Rest bleibt benutzbar
    texts = [a.text() for a in leaves(win.tools_menu)]
    assert any("Fehler beim Aufbau" in t for t in texts)
    assert errors and "Icon kaputt" in str(errors[0])                    # im Log/Toast gemeldet
