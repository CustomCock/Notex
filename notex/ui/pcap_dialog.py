"""PCAP-Übersicht: Protokoll-Hierarchie, Hosts, ARP, ICMP, DNS, TCP-Verbindungen (Doppelklick: Stream folgen),
HTTP, TLS, Dienste, Klartext-Zugangsdaten und Befunde. Tabellen filter-/sortierbar; IPs per RDAP; Markdown-Report."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from notex.core import pcapinfo
from notex.theme.tokens import COLORS, SPACING
from notex.ui.analysis_dialog import AnalysisDialog

_IP = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")


def _item(value) -> QTableWidgetItem:
    if isinstance(value, int):
        cell = QTableWidgetItem()
        cell.setData(Qt.ItemDataRole.DisplayRole, value)
        return cell
    return QTableWidgetItem(str(value))


class Tab(QWidget):
    def __init__(self, window, headers, on_double=None, warn=False) -> None:
        super().__init__()
        self.window_ = window
        self.on_double = on_double
        self.rows: list = []
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtern …")
        self.search.textChanged.connect(self._filter)
        self.table = QTableWidget(0, len(headers))
        self.table.setObjectName("AnalysisTable")
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        if on_double is not None:
            self.table.doubleClicked.connect(lambda idx: on_double(self.rows[idx.row()]) if idx.isValid()
                                             and idx.row() < len(self.rows) else None)
        self._warn = warn
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.table, 1)

    def fill(self, rows: list[list], data: list | None = None) -> None:
        self.rows = data or []
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                cell = _item(value)
                if self._warn:
                    cell.setForeground(QColor(COLORS.danger))
                self.table.setItem(r, c, cell)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def _filter(self, text: str) -> None:
        text = text.lower()
        for r in range(self.table.rowCount()):
            visible = not text or any(text in (self.table.item(r, c).text().lower() if self.table.item(r, c) else "")
                                      for c in range(self.table.columnCount()))
            self.table.setRowHidden(r, not visible)

    def _menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        cell = self.table.item(index.row(), index.column())
        if cell:
            menu.addAction("Zelle kopieren", lambda: QGuiApplication.clipboard().setText(cell.text()))
        ips = {m.group() for c in range(self.table.columnCount())
               for m in [_IP.search(self.table.item(index.row(), c).text() if self.table.item(index.row(), c) else "")]
               if m}
        if self.window_.registry.get("rdap:lookup") is not None:
            for ip in sorted(ips):
                menu.addAction(f"RDAP zu {ip}", lambda i=ip: self.window_.rdap_lookup(i))
        if menu.actions():
            menu.exec(self.table.viewport().mapToGlobal(pos))


class PcapDialog(AnalysisDialog):
    def __init__(self, window, path: Path) -> None:
        super().__init__(window, path, "PCAP-Übersicht")
        self.summary: pcapinfo.Summary | None = None
        self.overview = QLabel()
        self.overview.setObjectName("SettingsNote")
        self.overview.setWordWrap(True)
        self.tabs = QTabWidget()
        self.t_layers = Tab(window, ["Ebene", "Protokoll", "Pakete", "Bytes"])
        self.t_hosts = Tab(window, ["IP", "MAC", "Hersteller", "Typ", "Rolle", "Ges. Pakete", "Ges. Bytes"])
        self.t_arp = Tab(window, ["Vorgang", "Absender-IP", "Absender-MAC", "Ziel-IP", "Ziel-MAC"])
        self.t_icmp = Tab(window, ["Typ", "Von", "Nach", "Detail", "RTT (ms)"])
        self.t_dns = Tab(window, ["Name", "Typ", "Client", "Resolver", "RCODE", "Antworten", "Zeit (ms)"])
        self.t_tcp = Tab(window, ["A", "B", "Status", "Dauer (s)", "A→B", "B→A", "Retrans"], on_double=self._follow)
        self.t_http = Tab(window, ["Methode", "Host", "Pfad", "Status", "Content-Type", "Länge", "Zeit (ms)"])
        self.t_tls = Tab(window, ["Server", "SNI", "Version", "ALPN"])
        self.t_services = Tab(window, ["Adresse", "Dienst"])
        self.t_creds = Tab(window, ["Protokoll", "Server", "Quelle", "Detail"], warn=True)
        self.t_findings = Tab(window, ["", "Befund"])
        for widget, title in ((self.t_layers, "Protokolle"), (self.t_hosts, "Hosts"), (self.t_arp, "ARP"),
                              (self.t_icmp, "ICMP"), (self.t_dns, "DNS"), (self.t_tcp, "TCP"), (self.t_http, "HTTP"),
                              (self.t_tls, "TLS"), (self.t_services, "Dienste"), (self.t_creds, "Zugangsdaten"),
                              (self.t_findings, "Befunde")):
            self.tabs.addTab(widget, title)
        self.body.addWidget(self.overview)
        self.body.addWidget(self.tabs, 1)
        report = QPushButton("Report einfügen/kopieren")
        report.clicked.connect(self._report)
        self.add_footer_button(report)
        self.finish_layout()
        path_ = self.path
        self.start(lambda progress, cancelled: pcapinfo.analyze(path_, progress=progress, cancelled=cancelled))

    def show_result(self, summary: pcapinfo.Summary) -> None:
        self.summary = summary
        self.overview.setText(
            f"{summary.packets} Pakete · {summary.bytes:,} Bytes · {_when(summary.first_ts)} – {_when(summary.last_ts)} "
            f"({summary.duration:.3f} s)".replace(",", ".")
            + (f" · {summary.broken} kaputte Pakete übersprungen" if summary.broken else ""))
        self.t_layers.fill([["  " * l.depth + str(l.depth), "  " * l.depth + l.name, l.packets, l.bytes]
                            for l in summary.layers])
        self.t_hosts.fill([[h.ip, ", ".join(sorted(h.macs)) or "–", _vendor(h), h.addr_type, h.role,
                            h.sent_packets + h.recv_packets, h.sent_bytes + h.recv_bytes]
                           for h in sorted(summary.hosts.values(), key=lambda x: x.ip)])
        self.t_arp.fill([[e.op + (" (gratuitous)" if e.gratuitous else ""), e.sender_ip, e.sender_mac, e.target_ip,
                          e.target_mac or "–"] for e in summary.arp])
        self.t_icmp.fill([[e.kind, e.src, e.dst, e.detail, f"{e.rtt*1000:.1f}" if e.rtt is not None else "–"]
                          for e in summary.icmp])
        self.t_dns.fill([[e.name, e.qtype, e.client, e.server, e.rcode or "–",
                          "; ".join(f"{v} (TTL {t})" for v, t in e.answers) or "–",
                          f"{e.response_time*1000:.1f}" if e.response_time is not None else "–"] for e in summary.dns])
        self.t_tcp.fill([[c.a, c.b, c.state, f"{c.duration:.3f}", c.bytes_ab, c.bytes_ba, c.retransmissions]
                         for c in summary.tcp_list], data=summary.tcp_list)
        self.t_http.fill([[e.method, e.host, e.path, e.status or "–", e.content_type or "–", e.content_length or "–",
                           f"{e.response_time*1000:.1f}" if e.response_time is not None else "–"] for e in summary.http])
        self.t_tls.fill([[t.server, t.sni or "–", t.version or "–", t.alpn or "–"] for t in summary.tls])
        self.t_services.fill([[addr, name] for addr, name in sorted(summary.services.items())])
        self.t_creds.fill([[c.protocol, c.server, c.src, c.detail] for c in summary.credentials])
        self.t_findings.fill([["⚠" if f.severity == "warnung" else "ℹ", f.text] for f in summary.findings])
        self._tab_count(5, len(summary.tcp))
        self._tab_count(9, len(summary.credentials))
        warn = any(f.severity == "warnung" for f in summary.findings)
        self.status.setText(f"{len(summary.hosts)} Hosts · {len(summary.tcp)} TCP-Verbindungen · "
                            f"{len(summary.dns)} DNS · {len(summary.http)} HTTP"
                            + (f" · ⚠ {len(summary.credentials)} Klartext-Zugangsdaten" if summary.credentials else ""))
        if summary.credentials:
            self.tabs.setCurrentWidget(self.t_creds)
        elif warn:
            self.tabs.setCurrentWidget(self.t_findings)

    def _tab_count(self, index: int, count: int) -> None:
        base = self.tabs.tabText(index).split(" (")[0]
        self.tabs.setTabText(index, f"{base} ({count})" if count else base)

    def _follow(self, conn) -> None:
        FollowStreamDialog(self, conn).show()

    def _report(self) -> None:
        if self.summary is None:
            return
        text = pcapinfo.to_markdown(self.summary, self.path.name)
        editor = self.window_.tabs.current_editor()
        if editor is not None and not editor.isReadOnly() and not getattr(editor, "locked", False):
            cursor = editor.textCursor()
            editor._grouped(lambda: cursor.insertText(("\n" if cursor.positionInBlock() else "") + text))
            self.status.setText(f"Report in „{editor.path.name}“ eingefügt")
        else:
            QGuiApplication.clipboard().setText(text)
            self.status.setText("Report in die Zwischenablage kopiert (keine beschreibbare Notiz offen)")


class FollowStreamDialog(QDialog):
    def __init__(self, parent, conn) -> None:
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(f"Stream folgen – {conn.a} ↔ {conn.b}")
        self.resize(760, 560)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setObjectName("CodeView")
        self.mode = QPushButton("Als Hex anzeigen")
        self.mode.setCheckable(True)
        self.mode.toggled.connect(self._render)
        copy = QPushButton("Kopieren")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.view.toPlainText()))
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(self.mode)
        row.addStretch(1)
        row.addWidget(copy)
        row.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.addWidget(self.view, 1)
        layout.addLayout(row)
        self._render()

    def _render(self) -> None:
        data = self.conn.stream()
        if self.mode.isChecked():
            self.view.setPlainText(_hexdump(data))
        else:
            text = data.decode("latin-1", "replace")
            self.view.setPlainText("".join(ch if (ch.isprintable() or ch in "\r\n\t") else "." for ch in text))


def _hexdump(data: bytes, width: int = 16) -> str:
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk).ljust(width * 3 - 1)
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset:08x}  {hexpart}  {ascii_}")
    return "\n".join(lines)


def _vendor(host) -> str:
    macs = [m for m in host.macs if pcapinfo.is_locally_administered(m)]
    if macs and len(macs) == len(host.macs):
        return "(lokal verwaltet)"
    return "–"


def _when(ts) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%H:%M:%S") if ts else "?"
