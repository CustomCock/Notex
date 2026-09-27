"""PCAP-Übersicht: Kennzahlen, Protokolle, Top-Verbindungen/-Talker, DNS, HTTP, TLS-SNI und – deutlich markiert –
im Klartext übertragene Zugangsdaten. Tabellen filter- und sortierbar; IPs per RDAP nachschlagen; Markdown-Report."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QLabel, QLineEdit, QMenu, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from notex.core import pcapinfo
from notex.theme.tokens import COLORS
from notex.ui.analysis_dialog import AnalysisDialog


def _num(value: int) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setData(Qt.ItemDataRole.DisplayRole, int(value))     # numerisch sortierbar
    return item


class Tab(QWidget):
    """Eine filterbare, sortierbare Tabelle."""

    def __init__(self, headers: list[str], ip_columns: set[int], window) -> None:
        super().__init__()
        self.window_ = window
        self.ip_columns = ip_columns
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.table, 1)

    def fill(self, rows: list[list], warn_rows: bool = False) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = _num(value) if isinstance(value, int) else QTableWidgetItem(str(value))
                if warn_rows:
                    item.setForeground(QColor(COLORS.danger))
                self.table.setItem(r, c, item)
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
        for column in self.ip_columns:
            item = self.table.item(index.row(), column)
            ip = self._first_ip(item.text()) if item else ""
            if ip and self.window_.registry.get("rdap:lookup") is not None:
                menu.addAction(f"RDAP zu {ip}", lambda i=ip: self.window_.rdap_lookup(i))
        if menu.actions():
            menu.exec(self.table.viewport().mapToGlobal(pos))

    @staticmethod
    def _first_ip(text: str) -> str:
        import re
        match = re.search(r"(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{3,}:[0-9a-fA-F:]*", text)
        return match.group() if match else ""


class PcapDialog(AnalysisDialog):
    def __init__(self, window, path: Path) -> None:
        super().__init__(window, path, "PCAP-Übersicht")
        self.summary: pcapinfo.Summary | None = None
        self.overview = QLabel()
        self.overview.setObjectName("SettingsNote")
        self.overview.setWordWrap(True)
        self.tabs = QTabWidget()
        self.t_proto = Tab(["Protokoll", "Pakete"], set(), window)
        self.t_conv = Tab(["A", "B", "Pakete", "Bytes"], {0, 1}, window)
        self.t_talk = Tab(["IP", "Bytes"], {0}, window)
        self.t_dns = Tab(["Name", "Anzahl", "Antwort"], {2}, window)
        self.t_http = Tab(["Host", "Pfad", "User-Agent"], set(), window)
        self.t_tls = Tab(["SNI", "Anzahl"], set(), window)
        self.t_creds = Tab(["Protokoll", "Server", "Quelle", "Detail"], {1, 2}, window)
        self.tabs.addTab(self.t_proto, "Protokolle")
        self.tabs.addTab(self.t_conv, "Verbindungen")
        self.tabs.addTab(self.t_talk, "Top-Talker")
        self.tabs.addTab(self.t_dns, "DNS")
        self.tabs.addTab(self.t_http, "HTTP")
        self.tabs.addTab(self.t_tls, "TLS-SNI")
        self.creds_index = self.tabs.addTab(self.t_creds, "Zugangsdaten")
        self.body.addWidget(self.overview)
        self.body.addWidget(self.tabs, 1)
        report = QPushButton("Report einfügen/kopieren")
        report.clicked.connect(self._report)
        self.add_footer_button(report)
        self.finish_layout()
        path_ = self.path
        self.start(lambda progress, cancelled: pcapinfo.analyze(path_, progress=progress, cancelled=cancelled))

    def _when(self, ts) -> str:
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "?"

    def show_result(self, summary: pcapinfo.Summary) -> None:
        self.summary = summary
        self.overview.setText(
            f"{summary.packets} Pakete · {summary.bytes:,} Bytes · Zeitraum {self._when(summary.first_ts)} – "
            f"{self._when(summary.last_ts)} ({summary.duration:.1f} s)"
            + (f" · {summary.broken} kaputte Pakete übersprungen" if summary.broken else ""))
        self.t_proto.fill([[p, n] for p, n in summary.protocols.most_common()])
        self.t_conv.fill([[a, b, summary.conversation_packets[(a, b)], byt]
                          for (a, b), byt in summary.conversations.most_common(pcapinfo.MAX_ROWS)])
        self.t_talk.fill([[ip, byt] for ip, byt in summary.talkers.most_common(pcapinfo.MAX_ROWS)])
        self.t_dns.fill([[name, n, summary.dns_answers.get(name, "")]
                         for name, n in summary.dns_queries.most_common(pcapinfo.MAX_ROWS)])
        self.t_http.fill([[h, path, ua] for h, path, ua in summary.http_requests])
        self.t_tls.fill([[sni, n] for sni, n in summary.tls_sni.most_common(pcapinfo.MAX_ROWS)])
        self.t_creds.fill([[c.protocol, c.server, c.src, c.detail] for c in summary.credentials], warn_rows=True)
        label = f"Zugangsdaten ({len(summary.credentials)})" if summary.credentials else "Zugangsdaten"
        self.tabs.setTabText(self.creds_index, label)
        note = ""
        if summary.credentials:
            note = f" · ⚠ {len(summary.credentials)} Klartext-Zugangsdaten gefunden"
            self.tabs.setCurrentIndex(self.creds_index)
        self.status.setText(f"{len(summary.protocols)} Protokolle · {len(summary.dns_queries)} DNS-Namen · "
                            f"{len(summary.tls_sni)} TLS-SNI{note}")

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
