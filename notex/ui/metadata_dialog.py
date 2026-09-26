"""Metadaten-Panel: alle Felder als Tabelle, kopieren, als Markdown in die Notiz einfügen, GPS in OpenStreetMap
(nur auf Klick), „Metadaten entfernen“ als bereinigte Kopie mit Rückfrage und anschließender Prüfung."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QHeaderView, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem

from notex.core import fileops
from notex.core import metadata as md
from notex.theme.tokens import COLORS
from notex.ui.analysis_dialog import AnalysisDialog, AnalysisWorker


def _job(path: Path):
    def run(_progress, _cancelled):
        try:
            return md.read(path)
        except md.MetadataError as error:
            return str(error)
    return run


class MetadataDialog(AnalysisDialog):
    def __init__(self, window, path: Path) -> None:
        super().__init__(window, path, "Metadaten")
        self.report: md.Report | None = None
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("AnalysisTable")
        self.table.setHorizontalHeaderLabels(["Gruppe", "Feld", "Wert"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 220)
        self.table.setWordWrap(False)
        self.body.addWidget(self.table, 1)
        self.copy_button = QPushButton("Kopieren")
        self.copy_button.setToolTip("Markierte Zeilen (oder alle) als Tab-getrennten Text kopieren")
        self.copy_button.clicked.connect(self.copy)
        self.insert_button = QPushButton("Als Markdown einfügen")
        self.insert_button.setToolTip("Tabelle an der Cursorposition der aktuellen Notiz einfügen")
        self.insert_button.clicked.connect(self.insert_markdown)
        self.map_button = QPushButton("In OpenStreetMap öffnen")
        self.map_button.setToolTip("Öffnet den Browser – erst beim Klick geht etwas ins Netz")
        self.map_button.clicked.connect(self.open_map)
        self.strip_button = QPushButton("Metadaten entfernen …")
        self.strip_button.clicked.connect(self.strip)
        self.reveal_button = QPushButton("Kopie anzeigen")
        self.reveal_button.clicked.connect(lambda: fileops.reveal_in_file_manager(self.cleaned))
        for button in (self.copy_button, self.insert_button, self.map_button, self.strip_button, self.reveal_button):
            button.setEnabled(False)
            self.add_footer_button(button)
        self.finish_layout()
        self.cleaned: Path | None = None
        self._strip_worker: AnalysisWorker | None = None
        self.start(_job(self.path))

    def show_result(self, result) -> None:
        if isinstance(result, str):
            self.status.setText(result)
            return
        self.report = result
        self.table.setRowCount(len(result.fields))
        muted = QColor(COLORS.text_muted)
        for row, item in enumerate(result.fields):
            for column, text in enumerate((item.group, item.name, item.value)):
                cell = QTableWidgetItem(text)
                cell.setToolTip(text if len(text) > 60 else "")
                if not item.removable:
                    cell.setForeground(muted)
                    cell.setToolTip("Bleibt beim Entfernen (Formatangabe oder Teil des Inhalts)")
                elif item.group.endswith("GPS"):
                    cell.setForeground(QColor(COLORS.warning))
                self.table.setItem(row, column, cell)
        kind = md.KIND_NAMES.get(result.kind, result.kind)
        count = len(result.removable_fields)
        self.status.setText(f"{kind} · {count} entfernbare Angabe(n)" + (" · mit GPS-Position" if result.gps else "")
                            if result.fields else f"{kind} · keine Metadaten gefunden")
        self.copy_button.setEnabled(bool(result.fields))
        self.insert_button.setEnabled(bool(result.fields))
        self.map_button.setEnabled(result.gps is not None)
        self.strip_button.setEnabled(result.can_strip and bool(result.removes))
        if not result.can_strip:
            self.strip_button.setToolTip("; ".join(result.keeps) or "Für diesen Dateityp nicht unterstützt")

    def copy(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}) or range(self.table.rowCount())
        lines = ["\t".join(self.table.item(r, c).text() for c in range(3)) for r in rows]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.status.setText(f"{len(lines)} Zeile(n) kopiert")

    def insert_markdown(self) -> None:
        editor = self.window_.tabs.current_editor()
        if editor is None or editor.isReadOnly() or getattr(editor, "locked", False):
            self.status.setText("Erst eine beschreibbare Notiz öffnen – dort wird an der Cursorposition eingefügt")
            return
        text = md.to_markdown(self.report, self.path.name)
        cursor = editor.textCursor()
        editor._grouped(lambda: cursor.insertText(("\n" if cursor.positionInBlock() else "") + text))
        self.status.setText(f"In „{editor.path.name}“ eingefügt")

    def open_map(self) -> None:
        if self.report and self.report.gps:
            QDesktopServices.openUrl(QUrl(md.osm_url(*self.report.gps)))

    def strip(self) -> None:
        report = self.report
        if report is None:
            return
        target = md.clean_name(self.path)
        box = QMessageBox(self)
        box.setWindowTitle("Metadaten entfernen")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Bereinigte Kopie „{target.name}“ anlegen? Das Original bleibt unverändert.")
        removes = "\n".join(f"• {r}" for r in report.removes)
        keeps = "\n".join(f"• {k}" for k in report.keeps)
        box.setInformativeText(f"Entfernt wird:\n{removes}\n\nBleibt:\n{keeps}")
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Ok).setText("Kopie anlegen")
        if box.exec() != QMessageBox.StandardButton.Ok:
            return
        path = self.path

        def job(_progress, _cancelled):
            try:
                cleaned = md.strip(path, target)
                return cleaned, md.verify(path, cleaned)
            except (md.MetadataError, OSError) as error:
                return str(error)
        self.strip_button.setEnabled(False)
        self.status.setText("Schreibe bereinigte Kopie …")
        self._strip_worker = AnalysisWorker(job)
        self._strip_worker.done.connect(self._stripped)
        self._strip_worker.start()

    def _stripped(self, result, error: str) -> None:
        self._strip_worker.wait()
        self.strip_button.setEnabled(True)
        if result is None or isinstance(result, str):
            self.status.setText(f"Nicht bereinigt: {result or error}")
            return
        self.cleaned, left = result
        self.reveal_button.setEnabled(True)
        if left:
            names = ", ".join(f"{f.group}/{f.name}" for f in left[:6])
            self.status.setText(f"„{self.cleaned.name}“ angelegt – Prüfung: noch vorhanden: {names}")
            self.status.setStyleSheet(f"color: {COLORS.danger};")
        else:
            self.status.setText(f"„{self.cleaned.name}“ angelegt und geprüft: keine entfernbaren Metadaten mehr")
            self.status.setStyleSheet(f"color: {COLORS.success};")

    def closeEvent(self, event) -> None:
        if self._strip_worker is not None:
            self._strip_worker.wait(10000)
        super().closeEvent(event)
