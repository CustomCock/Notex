"""R1: Netzwerk-Scanner – Host-Aktionen laufen im Worker-Thread und melden sich immer sichtbar zurück."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from notex.core import netdetect, scan  # noqa: E402
from notex.ui import network_scanner as ns  # noqa: E402


class FakeRegistry:
    def get(self, _command):
        return None


@pytest.fixture
def dialog(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(netdetect, "local_adapters", lambda runner=None: [])
    window = QWidget()
    window.config = {}
    window.registry = FakeRegistry()
    dlg = ns.NetworkScannerDialog(window)
    yield dlg
    dlg.close()
    app.processEvents()


def wait_for(predicate, timeout=5.0):
    app = QApplication.instance()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def device(ip="192.168.1.5"):
    return ns.Device(ip, "", "", "", [], None, True)


def test_ping_runs_in_worker_and_reports(dialog, monkeypatch):
    import threading
    seen = []
    monkeypatch.setattr(scan, "system_ping", lambda ip, timeout=1.0: seen.append(threading.current_thread()) or True)
    dialog._ping(device())
    assert "Ping an 192.168.1.5" in dialog.status.text()          # sofortige Rückmeldung
    assert wait_for(lambda: "erreichbar" in dialog.status.text())
    assert seen and seen[0] is not threading.main_thread()        # nie im UI-Thread


def test_ping_error_is_visible(dialog, monkeypatch):
    def boom(ip, timeout=1.0):
        raise UnicodeDecodeError("charmap", b"\x81", 0, 1, "character maps to <undefined>")
    monkeypatch.setattr(scan, "system_ping", boom)
    dialog._ping(device())
    assert wait_for(lambda: "Fehler" in dialog.status.text())
    assert "UnicodeDecodeError" in dialog.status.text()


def test_failed_scan_resets_button(dialog):
    dialog.start_button.setText("Stopp")
    dialog._on_failed("UnicodeDecodeError: kaputt")
    assert dialog.start_button.text() == "Scannen"
    assert "kaputt" in dialog.status.text()


def test_traceroute_shows_output_window(dialog, monkeypatch):
    monkeypatch.setattr(scan, "traceroute", lambda ip, runner=None: " 1  192.168.1.1  2 ms")
    before = set(QApplication.topLevelWidgets())
    dialog._traceroute(device())
    assert "läuft" in dialog.status.text()
    assert wait_for(lambda: "fertig" in dialog.status.text())
    new = [w for w in QApplication.topLevelWidgets() if w not in before and w.isVisible()]
    assert any("Traceroute zu 192.168.1.5" in w.windowTitle() for w in new)
    for w in new:
        w.close()
