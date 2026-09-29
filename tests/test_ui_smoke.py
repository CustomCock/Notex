"""UI-Smoke-Tests mit echtem Hauptfenster (offscreen): Werkzeuge-Menü, Blatt-Leiste und Netzwerk-Werkzeuge
müssen nach Tab-Wechsel, Teilen und Neuöffnen sichtbar reagieren (R1/R3)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from uihelp import capture_toasts as _capture_toasts, leaves, open_toolbar_menu, open_tools_menu  # noqa: E402


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


# ---- Stille Rückgaben zeigen einen Hinweis ------------------------------------------------------------------------
def test_run_tool_with_module_off_shows_toast(win, monkeypatch):
    messages = _capture_toasts(win, monkeypatch)
    win.modules.set_enabled("scanner", False)
    win._run_tool("scan:open")
    assert messages and "ist aus" in messages[-1]


def test_run_tool_unknown_command_shows_toast(win, monkeypatch):
    messages = _capture_toasts(win, monkeypatch)
    win._run_tool("gibt:es-nicht")
    assert messages and "nicht verfügbar" in messages[-1]


def test_ip_overview_without_index_shows_toast(win, monkeypatch):
    messages = _capture_toasts(win, monkeypatch)
    win.ip_index = None
    win.show_ip_overview()
    assert messages and "IP-Konflikte" in messages[-1]
