"""Zeitleiste: chronologische Ansicht einer Zeitleisten-Notiz (Filter Quelle/Tag/Text, Anzeige UTC/lokal/wie
gespeichert, Export Markdown/CSV) und der Dialog „Zur Zeitleiste hinzufügen“."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from notex.core import timeline as tl
from notex.theme.tokens import COLORS, SPACING

MODES = [("UTC", "utc"), ("Lokal (Systemzeit)", "local"), ("Wie gespeichert", "original")]
NEW_TIMELINE = "Neue Zeitleiste …"


class TimelineDialog(QDialog):
    """Nicht modal; folgt dem Editor (Änderungen erscheinen nach kurzer Pause), Doppelklick springt zur Zeile."""

    def __init__(self, window, editor) -> None:
        super().__init__(window)
        self.window_ = window
        self.editor = editor
        self.cfg = window.config.setdefault("timeline", {})
        self.setWindowTitle(f"Zeitleiste – {editor.path.name}")
        self.resize(980, 600)
        self.source = QComboBox()
        self.tag = QComboBox()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Beschreibung oder Quelle enthält …")
        self.mode = QComboBox()
        for label, key in MODES:
            self.mode.addItem(label, key)
        self.mode.setCurrentIndex(max(0, [k for _l, k in MODES].index(self.cfg.get("mode", "utc"))))
        filters = QHBoxLayout()
        for label, widget in (("Quelle", self.source), ("Tag", self.tag), ("Suche", self.search), ("Zeit", self.mode)):
            filters.addWidget(QLabel(label))
            filters.addWidget(widget, 2 if widget is self.search else 1)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("AnalysisTable")
        self.table.setHorizontalHeaderLabels(tl.HEADER)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(3, 170)
        self.table.cellDoubleClicked.connect(self._jump)
        self.status = QLabel()
        self.status.setObjectName("SettingsNote")
        buttons = QHBoxLayout()
        buttons.addWidget(self.status, 1)
        for text, slot in (("Neuer Eintrag …", self.add_entry), ("Als Markdown kopieren", self.copy_markdown),
                           ("CSV exportieren …", self.export_csv), ("Schließen", self.close)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        self.entries: list[tl.Entry] = []
        self.shown: list[tl.Entry] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.reload)
        editor.textChanged.connect(self._timer.start)
        for combo in (self.source, self.tag, self.mode):
            combo.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.reload()

    def reload(self) -> None:
        timeline = tl.parse(self.editor.toPlainText())
        self.entries = timeline.entries
        for combo, values, label in ((self.source, timeline.sources, "Alle Quellen"), (self.tag, timeline.tags, "Alle Tags")):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(label, "")
            for value in values:
                combo.addItem(value, value)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            combo.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        mode = self.mode.currentData()
        self.cfg["mode"] = mode
        self.shown = tl.filter_entries(self.entries, self.source.currentData() or "", self.tag.currentData() or "",
                                       self.search.text())
        self.table.setRowCount(len(self.shown))
        for row, entry in enumerate(self.shown):
            for column, text in enumerate((tl.display(entry.time, mode), entry.source, entry.description,
                                           " ".join(entry.tags))):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setToolTip(tl.iso(entry.time))
                elif column == 2 and len(text) > 80:
                    item.setToolTip(text)
                self.table.setItem(row, column, item)
        self.status.setText(f"{len(self.shown)} von {len(self.entries)} Einträgen")
        self.status.setToolTip(f"{tl.display(self.shown[0].time, mode)} – {tl.display(self.shown[-1].time, mode)}"
                               if self.shown else "")

    def _jump(self, row: int, _column: int) -> None:
        entry = self.shown[row]
        self.window_.tabs.open_file(self.editor.path, line=entry.line + 1)

    def add_entry(self) -> None:
        dialog = EntryDialog(self, tl.entry_from_line("", ""), [self.editor.path], self.editor.path)
        if dialog.exec():
            self.window_.add_timeline_entry(self.editor.path, dialog.entry())

    def copy_markdown(self) -> None:
        QGuiApplication.clipboard().setText(tl.to_markdown(self.shown, self.mode.currentData()))
        self.status.setText(f"{len(self.shown)} Einträge als Markdown-Tabelle kopiert")

    def export_csv(self) -> None:
        start = str(self.editor.path.with_suffix(".csv"))
        path, _ = QFileDialog.getSaveFileName(self, "Zeitleiste als CSV", start, "CSV (*.csv)")
        if not path:
            return
        try:
            Path(path).write_text(tl.to_csv(self.shown, self.mode.currentData()), encoding="utf-8", newline="")
        except OSError as error:
            self.status.setText(f"Nicht gespeichert: {error}")
            return
        self.status.setText(f"{len(self.shown)} Einträge nach „{Path(path).name}“ exportiert")

    def closeEvent(self, event) -> None:
        try:
            self.editor.textChanged.disconnect(self._timer.start)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)


class EntryDialog(QDialog):
    """Eintrag bearbeiten (Zeit vorbelegt aus der Zeile), Ziel-Zeitleiste wählen."""

    def __init__(self, parent, entry: tl.Entry, timelines: list[Path], preferred: Path | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zur Zeitleiste hinzufügen")
        self.resize(640, 0)
        self.time = QLineEdit(tl.iso(entry.time))
        self.time.setToolTip("ISO 8601 mit Zeitzone, z. B. 2026-09-26T14:03:11+02:00 oder …Z für UTC")
        self.time_hint = QLabel()
        self.time_hint.setObjectName("SettingsNote")
        self.source = QLineEdit(entry.source)
        self.description = QLineEdit(entry.description)
        self.tags = QLineEdit(" ".join(entry.tags))
        self.tags.setPlaceholderText("#ssh #bruteforce")
        self.target = QComboBox()
        for path in timelines:
            self.target.addItem(path.name, str(path))
            self.target.setItemData(self.target.count() - 1, str(path), 3)      # Tooltip: voller Pfad
        self.target.addItem(NEW_TIMELINE, "")
        if preferred is not None and self.target.findData(str(preferred)) >= 0:
            self.target.setCurrentIndex(self.target.findData(str(preferred)))
        form = QFormLayout()
        form.addRow("Zeit", self.time)
        form.addRow("", self.time_hint)
        form.addRow("Quelle", self.source)
        form.addRow("Beschreibung", self.description)
        form.addRow("Tags", self.tags)
        form.addRow("Zeitleiste", self.target)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Hinzufügen")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self.time.textChanged.connect(self._check_time)
        self._check_time()
        self.description.setFocus()

    def _check_time(self) -> None:
        when = tl.parse_iso(self.time.text())
        ok = when is not None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        self.time_hint.setText(f"= {tl.display(when, 'utc')} · {tl.display(when, 'local')} (lokal)" if ok
                               else "Zeit nicht lesbar")
        self.time_hint.setStyleSheet("" if ok else f"color: {COLORS.danger};")

    def entry(self) -> tl.Entry:
        tags = [t if t.startswith("#") else f"#{t}" for t in self.tags.text().replace(",", " ").split() if t.strip("#")]
        return tl.Entry(tl.parse_iso(self.time.text()), self.source.text().strip(), self.description.text().strip(), tags)

    def target_path(self) -> Path | None:
        data = self.target.currentData()
        return Path(data) if data else None
