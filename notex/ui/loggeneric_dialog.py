"""Allgemeine Log-Auswertung (beliebige Logs): Übersicht der Stufen, Fehler/Warnungen, häufigste Meldungen,
aktivste Quellen und eine Stunden-Zeitleiste (Fehler vs. Warnungen). Ereignistabelle mit Filter; jede Zeile führt
zur Quelle und kann in die Zeitleiste übernommen werden. Markdown-Report."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QPushButton,
                               QTableWidget, QTableWidgetItem, QWidget)

from notex.core import loggeneric as lg
from notex.theme.tokens import COLORS, FONT_SIZE
from notex.ui.analysis_dialog import AnalysisDialog

HEADERS = ["Zeit", "Stufe", "Quelle", "Meldung"]
LEVEL_COLORS = {"critical": COLORS.danger, "error": COLORS.danger, "warning": COLORS.warning}


class LevelChart(QWidget):
    """Fehler (rot) und Warnungen (gelb) je Stunde – schmale Säulen, eine Achse."""

    def __init__(self) -> None:
        super().__init__()
        self.buckets: list[tuple[datetime, int, int]] = []
        self.setMinimumHeight(120)
        self.setToolTip("Ereignisse je Stunde: rot = Fehler/Kritisch, gelb = Warnungen")

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
        peak = max((e + w) for _h, e, w in self.buckets) or 1
        painter.setPen(QPen(QColor(COLORS.text_faint)))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        n = len(self.buckets)
        slot = rect.width() / n
        bar_w = max(1.0, min(slot * 0.7, 16))
        err_color, warn_color = QColor(COLORS.danger), QColor(COLORS.warning)
        for index, (_hour, errors, warnings) in enumerate(self.buckets):
            x = rect.left() + slot * index + (slot - bar_w) / 2
            eh = rect.height() * errors / peak
            wh = rect.height() * warnings / peak
            painter.fillRect(QRectF(x, rect.bottom() - eh, bar_w / 2, eh), err_color)
            painter.fillRect(QRectF(x + bar_w / 2, rect.bottom() - wh, bar_w / 2, wh), warn_color)
        painter.setPen(QColor(COLORS.text_muted))
        font = painter.font()
        font.setPointSizeF(FONT_SIZE.xs if hasattr(FONT_SIZE, "xs") else 8)
        painter.setFont(font)
        first, last = self.buckets[0][0], self.buckets[-1][0]
        painter.drawText(rect.left(), rect.bottom() + 14, first.strftime("%d.%m %H:%M"))
        painter.drawText(rect.right() - 90, rect.bottom() + 14, last.strftime("%d.%m %H:%M"))


class GenericLogDialog(AnalysisDialog):
    def __init__(self, window, path: Path) -> None:
        super().__init__(window, path, "Log-Auswertung (allgemein)")
        self.events: list[lg.GenericEvent] = []
        self.shown: list[lg.GenericEvent] = []
        self.summary_data: lg.GenericSummary | None = None

        self.summary = QLabel()
        self.summary.setObjectName("SettingsNote")
        self.summary.setWordWrap(True)
        self.chart = LevelChart()

        filters = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItem("Alle Stufen", "")
        self.level.currentIndexChanged.connect(self._refresh)
        self.source = QComboBox()
        self.source.addItem("Alle Quellen", "")
        self.source.currentIndexChanged.connect(self._refresh)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Text in der Meldung …")
        self.search.textChanged.connect(self._refresh)
        filters.addWidget(QLabel("Stufe"))
        filters.addWidget(self.level)
        filters.addWidget(self.source)
        filters.addWidget(self.search, 1)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setObjectName("AnalysisTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 160), (1, 90), (2, 150)):
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
        self.start(lambda progress, cancelled: lg.collect_generic(path_, progress=progress, cancelled=cancelled))

    def show_result(self, result) -> None:
        self.events, truncated = result
        self.summary_data = lg.analyze_generic(self.events)
        self.chart.load(self.summary_data.timeline)
        self.level.blockSignals(True)
        for key in lg.LEVEL_ORDER:
            if self.summary_data.by_level.get(key):
                self.level.addItem(f"{lg.LEVEL_LABELS[key]} ({self.summary_data.by_level[key]})", key)
        self.level.blockSignals(False)
        self.source.blockSignals(True)
        for src, count in self.summary_data.top_sources[:40]:
            self.source.addItem(f"{src} ({count})", src)
        self.source.blockSignals(False)

        s = self.summary_data
        bits = [f"{s.total} Zeilen", f"{s.error_count} Fehler", f"{s.warning_count} Warnungen"]
        if s.first_time and s.last_time:
            bits.append(f"{s.first_time:%Y-%m-%d %H:%M} – {s.last_time:%Y-%m-%d %H:%M}")
        if truncated:
            bits.append(f"nach {lg.MAX_EVENTS} abgeschnitten")
        self.status.setText(" · ".join(bits))
        self._refresh()

    def _refresh(self) -> None:
        level = self.level.currentData()
        source = self.source.currentData()
        needle = self.search.text().lower()
        self.shown = [e for e in self.events
                      if (not level or e.level == level)
                      and (not source or e.source == source)
                      and (not needle or needle in e.message.lower())]
        # sehr große Trefferlisten begrenzen, damit die Tabelle flüssig bleibt
        capped = self.shown[:5000]
        self.table.setRowCount(len(capped))
        for row, event in enumerate(capped):
            when = event.time.strftime("%Y-%m-%d %H:%M:%S") if event.time else "?"
            values = (when, lg.LEVEL_LABELS.get(event.level, event.level), event.source, event.message)
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                color = LEVEL_COLORS.get(event.level)
                if color and column == 1:
                    item.setForeground(QColor(color))
                if column == 3 and text:
                    item.setToolTip(text)
                self.table.setItem(row, column, item)
        extra = f" (erste 5000 von {len(self.shown)})" if len(self.shown) > 5000 else ""
        self.summary.setText(f"{len(self.shown)} von {len(self.events)} Zeilen angezeigt{extra}")

    def _menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        event = self.shown[index.row()]
        menu = QMenu(self)
        menu.addAction("Zur Quelle springen", lambda: self._jump(event))
        menu.addAction("Meldung kopieren", lambda: QGuiApplication.clipboard().setText(event.message))
        if self.window_.registry.get("timeline:add") is not None:
            menu.addAction("Zur Zeitleiste hinzufügen …", lambda: self._to_timeline(event))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _jump(self, event: lg.GenericEvent) -> None:
        if self.path.suffix.lower() == ".gz":
            self.status.setText("Rotierte .gz-Datei – bitte entpackt öffnen, um zur Zeile zu springen")
            return
        self.window_.tabs.open_file(self.path, line=event.line + 1)

    def _to_timeline(self, event: lg.GenericEvent) -> None:
        from notex.core import timeline as tl
        text = event.message or event.raw
        entry = tl.Entry(event.time or datetime.now().astimezone(), self.path.name, text, [f"#{event.level}"])
        self.window_.add_prepared_timeline_entry(entry)

    def _report(self) -> None:
        if self.summary_data is None:
            return
        text = lg.to_markdown(self.summary_data, self.path.name)
        editor = self.window_.tabs.current_editor()
        if editor is not None and not editor.isReadOnly() and not getattr(editor, "locked", False):
            cursor = editor.textCursor()
            editor._grouped(lambda: cursor.insertText(("\n" if cursor.positionInBlock() else "") + text))
            self.status.setText(f"Report in „{editor.path.name}“ eingefügt")
        else:
            QGuiApplication.clipboard().setText(text)
            self.status.setText("Report in die Zwischenablage kopiert (keine beschreibbare Notiz offen)")
