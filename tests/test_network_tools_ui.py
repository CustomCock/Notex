"""R3: Jedes Netzwerk-Werkzeug reagiert sichtbar und liefert ein Ergebnis – ohne Internet.

Lokales wird echt getestet (TCP gegen einen Listener auf 127.0.0.1, PCAP gegen tests/fixtures), nur öffentliche
Dienste (RDAP, fremdes DNS/Ping) werden durch Fakes ersetzt.
"""
import os
import socket

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from notex.core import rdap, scan  # noqa: E402
from uihelp import label, leaves, open_tools_menu, visible_windows, wait_for  # noqa: E402


@pytest.fixture
def listener():
    """Offener TCP-Port auf 127.0.0.1 (nimmt Verbindungen an, sendet ein Banner)."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    server.settimeout(0.05)
    yield server.getsockname()[1]
    server.close()


def new_windows(before: set) -> list:
    return [w for w in visible_windows() - before]


def by_title(title: str):
    return next((w for w in QApplication.topLevelWidgets() if w.isVisible() and title in w.windowTitle()), None)


# ---- Werkzeuge-Menü: jedes Netzwerk-Werkzeug öffnet ein Fenster ---------------------------------------------------
@pytest.mark.parametrize("name, title", [
    ("Netzwerk-Scanner", "Netzwerk-Scanner"),
    ("Port nachschlagen", "Port nachschlagen"),
    ("IP-Übersicht", "IP-Übersicht"),
    ("RDAP / ASN abfragen", "RDAP / ASN"),
    ("PCAP-Übersicht", "PCAP-Übersicht"),
])
def test_network_tool_from_menu_opens_window(win, name, title):
    win.tabs.open_file(win.files["pcap"])            # PCAP braucht eine .pcap als aktuelle Datei
    QApplication.processEvents()
    open_tools_menu(win)
    action = next(a for a in leaves(win.tools_menu) if label(a) == name)
    assert action.isEnabled(), f"{name} ist ausgegraut"
    before = visible_windows()
    action.trigger()
    QApplication.processEvents()
    assert any(title in w.windowTitle() for w in new_windows(before)), f"{name}: kein Fenster"


# ---- Port-Infos -----------------------------------------------------------------------------------------------------
def test_port_lookup_shows_service(win):
    from notex.ui.ports_dialog import PortDialog
    dialog = PortDialog(win, "3389")
    dialog.show()
    assert dialog.results.count() >= 1
    assert "3389" in dialog.results.item(0).text()
    assert "RDP" in dialog.details.toPlainText() or "Remote" in dialog.details.toPlainText()
    dialog.query.setText("gibt-es-sicher-nicht-xyz")
    assert "Nichts gefunden" in dialog.details.toPlainText()


# ---- IP-Übersicht / Konflikte -----------------------------------------------------------------------------------------
def test_ip_overview_shows_conflict(win):
    root = win.root
    (root / "server-a.md").write_text("fileserver: 10.20.0.5\n", encoding="utf-8")
    (root / "server-b.md").write_text("10.20.0.5 drucker\n", encoding="utf-8")
    win.refresh_ip_index(full=True)
    before = visible_windows()
    win.show_ip_overview()
    dialog = next(w for w in new_windows(before) if "IP-Übersicht" in w.windowTitle())
    assert wait_for(lambda: "1 Konflikt" in dialog.status.text())
    heads = [dialog.tree.topLevelItem(i).text(0) for i in range(dialog.tree.topLevelItemCount())]
    assert any("10.20.0.0/24" in h and "im Konflikt" in h for h in heads)
    dialog.network.setText("10.20.0.0/24")
    assert dialog.copy_button.isEnabled()


# ---- RDAP / ASN (öffentlicher Dienst → Fake-Client) -------------------------------------------------------------------
class FakeRdapClient:
    def __init__(self):
        self.queries = []

    def lookup(self, query):
        self.queries.append(query)
        card = rdap.Card("ip", query, "Beispielnetz", source="https://rdap.example/ip/" + query)
        card.add("Netz", "8.8.8.0/24")
        card.add("ASN", "AS15169")
        return card


def test_rdap_shows_card_from_worker(win):
    client = FakeRdapClient()
    win._rdap_client = client
    before = visible_windows()
    win.rdap_lookup("8.8.8.8")
    dialog = next(w for w in new_windows(before) if "RDAP" in w.windowTitle())
    assert wait_for(lambda: "Quelle:" in dialog.status.text())
    assert client.queries == ["8.8.8.8"]
    assert "Beispielnetz" in dialog.title.text() and dialog.form.rowCount() == 2


def test_rdap_never_queries_private_addresses(win):
    client = FakeRdapClient()
    win._rdap_client = client
    before = visible_windows()
    win.rdap_lookup("192.168.1.1")
    dialog = next(w for w in new_windows(before) if "RDAP" in w.windowTitle())
    assert "nie ab" in dialog.status.text() and client.queries == []


# ---- PCAP-Übersicht (echte Fixture) ----------------------------------------------------------------------------------
def test_pcap_overview_with_fixture(win):
    before = visible_windows()
    win.analyze_pcap(win.files["pcap"])
    dialog = next(w for w in new_windows(before) if "PCAP" in w.windowTitle())
    assert wait_for(lambda: dialog.summary is not None)
    assert "13 Pakete" in dialog.overview.text()
    assert dialog.summary.dns and dialog.summary.dns[0].name == "example.test"


# ---- Geräte-Scanner (echter TCP-Connect auf 127.0.0.1) ----------------------------------------------------------------
def test_device_scanner_finds_local_listener(win, listener, monkeypatch):
    from notex.ui.network_scanner import NetworkScannerDialog
    monkeypatch.setattr(scan, "parse_ports", lambda spec: [listener])
    dialog = NetworkScannerDialog(win)
    dialog.show()
    dialog.target.setText("127.0.0.1")
    dialog.opt_netbios.setChecked(False)
    dialog.opt_ping.setChecked(False)
    dialog._toggle_scan()
    assert dialog.start_button.text() == "Stopp"
    assert wait_for(lambda: dialog.start_button.text() == "Scannen", timeout=20)
    assert "127.0.0.1" in dialog.devices
    assert listener in dialog.devices["127.0.0.1"].ports
    assert "Geräte gefunden" in dialog.status.text()
    dialog.close()


# ---- Port-Scan (ein Ziel) ---------------------------------------------------------------------------------------------
def test_port_scan_dialog_finds_open_port(win, listener):
    from notex.ui.scan_dialog import ScanDialog
    dialog = ScanDialog(win)
    dialog.show()
    dialog.target.setText("127.0.0.1")
    dialog.ports.setText(str(listener))
    dialog.discover.setChecked(False)
    dialog.use_ping.setChecked(False)
    dialog.banner.setChecked(False)
    dialog.start()
    assert wait_for(lambda: dialog.thread is None, timeout=20)
    assert "Fertig: 1 aktive Host(s), 1 offene Ports" in dialog.status.text()
    assert dialog.table.rowCount() == 1
    dialog.close()


# ---- Rechtsklick-Analyse (Q): DNS, Ping, Ports ------------------------------------------------------------------------
def _run_card_action(win):
    card = win.analyze.card()
    assert card.isVisible(), "Analyse-Karte nicht sichtbar"
    card._on_action()
    assert wait_for(lambda: "läuft" not in card.result.text() and card.result.text())
    return card.result.text()


def test_q_dns_lookup_localhost(win):
    win.analyze.dns_lookup("localhost")                 # echte Auflösung, ohne Internet
    assert "127.0.0.1" in _run_card_action(win)


def test_q_dns_error_is_shown(win, monkeypatch):
    from notex.ui import analyze_actions

    def fail(host):
        raise RuntimeError("Name or service not known")
    monkeypatch.setattr(analyze_actions, "_resolve", fail)
    win.analyze.dns_lookup("gibt-es-nicht.invalid")
    assert _run_card_action(win).startswith("Fehler: Name or service not known")


def test_q_ping(win, monkeypatch):
    monkeypatch.setattr(scan, "system_ping", lambda host, timeout=1.0: host == "10.0.0.5")
    win.analyze.ping("10.0.0.5")
    assert _run_card_action(win) == "erreichbar"
    win.analyze.ping("10.0.0.6")
    assert _run_card_action(win) == "keine Antwort"


def test_q_port_check_finds_listener(win, listener, monkeypatch):
    monkeypatch.setattr(scan, "parse_ports", lambda spec: [listener])
    win.analyze.port_check("127.0.0.1")
    assert _run_card_action(win).startswith(f"offen: {listener}/")


def test_q_menu_offers_network_actions_for_ip(win):
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import QMenu
    win.tabs.open_file(win.files["log"])
    editor = win.tabs.current_editor()
    start = editor.toPlainText().index("10.0.0.5")
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + len("10.0.0.5"), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    menu = QMenu()
    win.analyze.menu_provider(editor, menu)
    sub = next(a.menu() for a in menu.actions() if a.menu() and a.text() == "Analysieren")
    names = [a.text() for a in leaves(sub)]
    for expected in ("DNS auflösen (A/AAAA/PTR)", "Ping (Antwortzeit)", "Gängige Ports prüfen", "RDAP / ASN",
                     "In IP-Übersicht öffnen", "Im Netzwerk-Scanner öffnen"):
        assert expected in names
    before = visible_windows()
    next(a for a in leaves(sub) if a.text() == "Ping (Antwortzeit)").trigger()
    QApplication.processEvents()
    assert win.analyze.card().isVisible() and win.analyze.card().title.text() == "Ping"
    win.analyze.card().close()
    next(a for a in leaves(sub) if a.text() == "Im Netzwerk-Scanner öffnen").trigger()
    QApplication.processEvents()
    assert by_title("Netzwerk-Scanner") is not None and by_title("Netzwerk-Scanner") not in before


def test_ip_refresh_during_running_refresh_is_not_lost(win):
    """Regression R3: Ein Abgleich-Wunsch während eines laufenden Abgleichs wurde verworfen."""
    win.refresh_ip_index(full=True)                          # läuft
    (win.root / "spaet.md").write_text("10.30.0.7 kamera\n", encoding="utf-8")
    win.refresh_ip_index(full=True)                          # während des Laufs angefordert
    assert wait_for(lambda: any(a.ip == "10.30.0.7" for a in win._ip_assignments()))
