"""Eingebettete Dateien: Trefferliste (Offset, Typ, Größe, Info, Vorschau), Extrahieren, Sprung in die Hex-Ansicht.

Extrahierte Dateien landen als Kopie in <Datei>_extrahiert/ neben der Datei – nie überschrieben, nie geöffnet oder
ausgeführt.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QPushButton, QTableView

from notex.core import carve, fileops, hexdata
from notex.theme.tokens import COLORS
from notex.ui.analysis_dialog import AnalysisDialog
from notex.ui.viewer_page import human_size

HEADERS = ["Offset", "Typ", "Größe", "Info", "Erste Bytes"]


class HitsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.hits: list[carve.Hit] = []
        self.previews: list[str] = []

    def load(self, hits: list[carve.Hit], previews: list[str]) -> None:
        self.beginResetModel()
        self.hits, self.previews = hits, previews
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.hits)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        hit = self.hits[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            size = human_size(hit.size) if hit.size is not None else "unbekannt"
            return (f"0x{hit.offset:08X}", hit.name, size, hit.info, self.previews[index.row()])[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 2 and hit.size is None:
            return "Größe aus dem Format nicht ableitbar – extrahiert wird bis zum nächsten Fund bzw. Dateiende"
        if role == Qt.ItemDataRole.ForegroundRole and hit.key == "trailer":
            return QColor(COLORS.warning)
        return None


class EmbeddedDialog(AnalysisDialog):
    def __init__(self, window, path: Path) -> None:
        super().__init__(window, path, "Eingebettete Dateien")
        self.model = HitsModel()
        self.table = QTableView()
        self.table.setObjectName("AnalysisTable")
        self.table.setModel(self.model)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 110), (2, 90), (3, 200), (4, 330)):
            self.table.setColumnWidth(column, width)
        self.table.doubleClicked.connect(self._jump)
        self.table.activated.connect(self._jump)
        hint = QLabel("Doppelklick springt in die Hex-Ansicht. Extrahierte Dateien werden nur gespeichert – nie "
                      "geöffnet oder ausgeführt. Gelb: Daten hinter dem Ende einer Datei (Anhang, Overlay).")
        hint.setObjectName("SettingsNote")
        hint.setWordWrap(True)
        self.body.addWidget(self.table, 1)
        self.body.addWidget(hint)
        extract_selected = QPushButton("Markierte extrahieren")
        extract_selected.clicked.connect(lambda: self._extract(selected_only=True))
        extract_all = QPushButton("Alle extrahieren")
        extract_all.clicked.connect(lambda: self._extract(selected_only=False))
        self.reveal = QPushButton("Zielordner anzeigen")
        self.reveal.setEnabled(False)
        self.reveal.clicked.connect(lambda: fileops.reveal_in_file_manager(self._target_folder()))
        for button in (extract_selected, extract_all, self.reveal):
            self.add_footer_button(button)
        self.finish_layout()
        self.truncated = False
        path_ = self.path
        self.start(lambda progress, cancelled: carve.scan(path_, progress=progress, cancelled=cancelled))

    def show_result(self, result) -> None:
        hits, self.truncated = result
        previews = []
        try:
            with open(self.path, "rb") as handle:
                for hit in hits:
                    handle.seek(hit.offset)
                    previews.append(hexdata.to_hex_string(handle.read(16)))
        except OSError:
            previews = [""] * len(hits)
        self.model.load(hits, previews)
        found = sum(1 for h in hits if h.key != "trailer")
        trailers = len(hits) - found
        text = f"{found} Fund(e)" + (f" · {trailers} × Daten hinter einem Dateiende" if trailers else "")
        if self.truncated:
            text += f" · nach {carve.MAX_HITS} Funden abgeschnitten"
        self.status.setText(text if hits else "Keine eingebetteten Dateien gefunden")

    def _target_folder(self) -> Path:
        return self.path.with_name(f"{self.path.name}_extrahiert")

    def _extract(self, selected_only: bool) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()}) if selected_only \
            else list(range(self.model.rowCount()))
        if not rows:
            self.status.setText("Erst Funde markieren")
            return
        done, errors = [], []
        for row in rows:
            hit = self.model.hits[row]
            try:
                done.append(carve.extract(self.path, hit, self.model.hits))
            except OSError as error:
                errors.append(f"0x{hit.offset:X}: {error}")
        self.reveal.setEnabled(bool(done))
        message = f"{len(done)} Datei(en) nach „{self._target_folder().name}“ extrahiert (nicht geöffnet)"
        self.status.setText(message + (f" · Fehler: {'; '.join(errors)}" if errors else ""))

    def _jump(self, index) -> None:
        if index.isValid():
            hit = self.model.hits[index.row()]
            self.jump(hit.offset, min(hit.size or 16, 1 << 20))
