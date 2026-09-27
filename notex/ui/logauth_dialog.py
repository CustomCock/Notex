"""Log-Auswertung: auth.log/secure (auch .gz) und Windows-.evtx auswerten – Dashboard mit Kennzahlen und einer
Zeitleiste (Fehlversuche vs. Erfolge je Stunde, QPainter), Ereignisliste mit Filter; jede Zeile führt zur Quelle,
kann in die Zeitleiste übernommen werden, IPs per RDAP nachschlagen; Markdown-Report."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
                               QPushButton, QTableWidget, QTableWidgetItem, QWidget)

from notex.core import logauth
from notex.theme.tokens import COLORS, FONT_SIZE, SPACING
from notex.ui.analysis_dialog import AnalysisDialog

HEADERS = ["Zeit", "Ereignis", "Benutzer", "IP", "Detail"]


class TimelineChart(QWidget):
    """Fehlversuche (Warnfarbe) und Erfolge (Erfolgsfarbe) je Stunde als schmale Säulen – eine Achse, dezentes Raster."""

    def __init__(self) -> None:
        super().__init__()
        self.buckets: list[tuple[datetime, int, int]] = []
        self.setMinimumHeight(130)
        self.setToolTip("Ereignisse je Stunde: rot = Fehlversuche, grün = Erfolge")

    def load(self, buckets) -> None:
        self.buckets = buckets
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect().adjusted(8, 8, -8, -18)
        painter.fillRect(self.rect(), QColor(COLORS.bg))
        if not self.buckets:
            painter.setPen(QColor(COLORS.text_muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Keine zeitlichen Daten")
            return
        peak = max((f + o) for _h, f, o in self.buckets) or 1
        grid = QPen(QColor(COLORS.text_faint))
        painter.setPen(grid)
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        n = len(self.buckets)
        slot = rect.width() / n
        bar_w = max(1.0, min(slot * 0.7, 16))
        fail_color, ok_color = QColor(COLORS.danger), QColor(COLORS.success)
        for index, (_hour, failed, ok) in enumerate(self.buckets):
            x = rect.left() + slot * index + (slot - bar_w) / 2
            fh = rect.height() * failed / peak
            oh = rect.height() * ok / peak
            painter.fillRect(QRectF(x, rect.bottom() - fh, bar_w / 2, fh), fail_color)
            painter.fillRect(QRectF(x + bar_w / 2, rect.bottom() - oh, bar_w / 2, oh), ok_color)
        painter.setPen(QColor(COLORS.text_muted))
        font = painter.font()
        font.setPointSizeF(FONT_SIZE.xs if hasattr(FONT_SIZE, "xs") else 8)
        painter.setFont(font)
        first, last = self.buckets[0][0], self.buckets[-1][0]
        painter.drawText(rect.left(), rect.bottom() + 14, first.strftime("%d.%m %H:%M"))
        painter.drawText(rect.right() - 90, rect.bottom() + 14, last.strftime("%d.%m %H:%M"))


class LogAuthDialog(AnalysisDialog):
    def __init__(self, window, path: Path) -> None:
        super().__init__(window, path, "Log-Auswertung")
        self.events: list[logauth.LogEvent] = []
        self.shown: list[logauth.LogEvent] = []
        self.dash: logauth.Dashboard | None = None
        self.summary = QLabel()
        self.summary.setObjectName("SettingsNote")
        self.summary.setWordWrap(True)
        self.chart = TimelineChart()
        filters = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItem("Alle Ereignisse", "")
        self.kind.currentIndexChanged.connect(self._refresh)
        self.only_notable = QComboBox()
        self.only_notable.addItem("Alle", "all")
        self.only_notable.addItem("Nur auffällige", "notable")
        self.only_notable.currentIndexChanged.connect(self._refresh)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Benutzer, IP oder Text …")
        self.search.textChanged.connect(self._refresh)
        filters.addWidget(QLabel("Art"))
        filters.addWidget(self.kind)
        filters.addWidget(self.only_notable)
        filters.addWidget(self.search, 1)
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setObjectName("AnalysisTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 150), (1, 220), (2, 140), (3, 130)):
            self.table.setColumnWidth(column, width)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(lambda idx: self._jump(self.shown[idx.row()]) if idx.isValid() else None)
        self.body.addWidget(self.summary)
        self.body.addWidget(self.chart)
        self.body.addLayout(filters)
        self.body.addWidget(self.table, 1)
        report = QPushButton("Report einfügen/kopieren")
        report.clicked.connect(self._report)
        self.add_footer_button(report)
        self.finish_layout()
        path_ = self.path
        self.start(lambda progress, cancelled: logauth.collect(path_, progress=progress, cancelled=cancelled))

    def show_result(self, result) -> None:
        self.events, truncated = result
        self.dash = logauth.analyze(self.events)
        self.chart.load(self.dash.timeline)
        kinds = sorted({e.kind for e in self.events})
        self.kind.blockSignals(True)
        for k in kinds:
            self.kind.addItem(logauth.KIND_LABELS.get(k, k), k)
        self.kind.blockSignals(False)
        d = self.dash
        bits = [f"{d.total} Ereignisse"]
        if d.brute_force:
            bits.append(f"⚠ {len(d.brute_force)} mögliche Brute-Force-IP(s): "
                        + ", ".join(f"{ip} ({n}×)" for ip, n in d.brute_force[:4]))
        if d.success_after_failed:
            bits.append(f"{len(d.success_after_failed)} Erfolg(e) nach Fehlversuchen")
        for label, items in (("neue Benutzer", d.new_users), ("Gruppenänderungen", d.group_changes),
                             ("neue Dienste", d.new_services), ("geleerte Protokolle", d.logs_cleared),
                             ("Kontosperren", d.lockouts)):
            if items:
                bits.append(f"{len(items)} {label}")
        if truncated:
            bits.append(f"nach {logauth.MAX_EVENTS} abgeschnitten")
        self.status.setText(" · ".join(bits))
        self._refresh()

    def _refresh(self) -> None:
        kind = self.kind.currentData()
        notable = self.only_notable.currentData() == "notable"
        needle = self.search.text().lower()
        self.shown = [e for e in self.events
                      if (not kind or e.kind == kind)
                      and (not notable or e.kind in logauth.NOTEWORTHY)
                      and (not needle or needle in e.user.lower() or needle in e.ip.lower()
                           or needle in e.detail.lower())]
        self.table.setRowCount(len(self.shown))
        warn = QColor(COLORS.danger)
        for row, event in enumerate(self.shown):
            when = event.time.strftime("%Y-%m-%d %H:%M:%S") if event.time else "?"
            for column, text in enumerate((when, logauth.KIND_LABELS.get(event.kind, event.kind), event.user,
                                           event.ip, event.detail)):
                item = QTableWidgetItem(text)
                if event.kind in logauth.NOTEWORTHY:
                    item.setForeground(warn)
                if column == 4 and text:
                    item.setToolTip(text)
                self.table.setItem(row, column, item)
        self.summary.setText(f"{len(self.shown)} von {len(self.events)} Ereignissen angezeigt")

    def _menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        event = self.shown[index.row()]
        menu = QMenu(self)
        menu.addAction("Zur Quelle springen", lambda: self._jump(event))
        if event.ip:
            menu.addAction(f"IP {event.ip} kopieren", lambda: QGuiApplication.clipboard().setText(event.ip))
            if self.window_.registry.get("rdap:lookup") is not None:
                menu.addAction(f"RDAP zu {event.ip}", lambda: self.window_.rdap_lookup(event.ip))
        if self.window_.registry.get("timeline:add") is not None:
            menu.addAction("Zur Zeitleiste hinzufügen …", lambda: self._to_timeline(event))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _jump(self, event: logauth.LogEvent) -> None:
        if self.path.suffix.lower() == ".evtx":
            self.status.setText(f"Datensatz {event.line} in {self.path.name} (evtx – kein direkter Sprung)")
            return
        if self.path.suffix == ".gz":
            self.status.setText("Rotierte .gz-Datei – bitte entpackt öffnen, um zur Zeile zu springen")
            return
        self.window_.tabs.open_file(self.path, line=event.line + 1)

    def _to_timeline(self, event: logauth.LogEvent) -> None:
        from notex.core import timeline as tl
        entry = tl.Entry(event.time or datetime.now().astimezone(), self.path.name, event.summary, [f"#{event.kind}"])
        self.window_.add_prepared_timeline_entry(entry)

    def _report(self) -> None:
        if self.dash is None:
            return
        text = logauth.to_markdown(self.dash, self.path.name)
        editor = self.window_.tabs.current_editor()
        if editor is not None and not editor.isReadOnly() and not getattr(editor, "locked", False):
            cursor = editor.textCursor()
            editor._grouped(lambda: cursor.insertText(("\n" if cursor.positionInBlock() else "") + text))
            self.status.setText(f"Report in „{editor.path.name}“ eingefügt")
        else:
            QGuiApplication.clipboard().setText(text)
            self.status.setText("Report in die Zwischenablage kopiert (keine beschreibbare Notiz offen)")
