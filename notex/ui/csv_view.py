"""Tabellenansicht für CSV/TSV: QAbstractTableModel über Zeilenlisten, Sortieren/Filtern nur in der Ansicht.

Der Text im Editor bleibt die Quelle der Wahrheit. Beim Umschalten in die Tabelle wird er geparst; Änderungen in
der Tabelle markieren die Datei als geändert und werden beim Speichern bzw. Zurückschalten in den Text
zurückgeschrieben (serialize im erkannten Stil: Trennzeichen, Quoting; Encoding/Zeilenende hält der Editor).
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QTableView, QVBoxLayout, QWidget)

from notex.core import csvdata
from notex.core.csvdata import Dialect
from notex.theme.tokens import SPACING
from notex.ui.widgets import IconButton

ENCODINGS = [("utf-8", "UTF-8"), ("utf-8-sig", "UTF-8 BOM"), ("cp1252", "cp1252"), ("latin-1", "ISO-8859-1"),
             ("utf-16", "UTF-16")]


class CsvModel(QAbstractTableModel):
    edited = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []      # alle Datenzeilen (ohne Kopfzeile, wenn has_header)
        self.header: list[str] = []
        self.has_header = True
        self.order: list[int] = []           # sichtbare Zeilen (sortiert/gefiltert) als Indizes in rows
        self.columns = 0

    def load(self, rows: list[list[str]], has_header: bool) -> None:
        self.beginResetModel()
        self.has_header = has_header and bool(rows)
        self.header = list(rows[0]) if self.has_header else []
        self.rows = [list(r) for r in (rows[1:] if self.has_header else rows)]
        self.columns = max([len(self.header)] + [len(r) for r in self.rows[:100000]] + [0])
        self.order = list(range(len(self.rows)))
        self.endResetModel()

    def all_rows(self) -> list[list[str]]:
        return ([self.header] if self.has_header else []) + self.rows

    # ---- Qt-Modell --------------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.order)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self.columns

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole,
                                               Qt.ItemDataRole.ToolTipRole):
            return None
        row = self.rows[self.order[index.row()]]
        value = row[index.column()] if index.column() < len(row) else ""
        if role == Qt.ItemDataRole.ToolTipRole:
            return value if len(value) > 40 or "\n" in value else None
        return value.replace("\n", " ⏎ ") if role == Qt.ItemDataRole.DisplayRole else value

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        row = self.rows[self.order[index.row()]]
        while len(row) <= index.column():
            row.append("")
        if row[index.column()] == value:
            return False
        row[index.column()] = str(value)
        self.dataChanged.emit(index, index)
        self.edited.emit()
        return True

    def flags(self, index: QModelIndex):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if self.has_header and section < len(self.header) and self.header[section].strip():
                return self.header[section]
            return f"Spalte {section + 1}"
        return str(self.order[section] + 1) if section < len(self.order) else ""

    def clear_cells(self, cells: list[tuple[int, int]]) -> None:
        changed = False
        for view_row, column in cells:
            row = self.rows[self.order[view_row]]
            if column < len(row) and row[column]:
                row[column] = ""
                changed = True
        if changed:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.order) - 1, self.columns - 1))
            self.edited.emit()

    def paste_block(self, view_row: int, column: int, text: str) -> None:
        """Tab-getrennten Block ab (view_row, column) einfügen; fehlende Zeilen/Spalten werden angehängt."""
        lines = text.rstrip("\n").split("\n") if text else []
        if not lines:
            return
        self.beginResetModel()
        for offset, line in enumerate(lines):
            target = view_row + offset
            if target >= len(self.order):
                self.rows.append([""] * self.columns)
                self.order.append(len(self.rows) - 1)
            row = self.rows[self.order[target]]
            for c, value in enumerate(line.split("\t")):
                while len(row) <= column + c:
                    row.append("")
                row[column + c] = value
                self.columns = max(self.columns, column + c + 1)
        self.endResetModel()
        self.edited.emit()

    # ---- Ansicht: sortieren/filtern ------------------------------------------------------------
    def apply_view(self, sort_column: int, descending: bool, needle: str) -> None:
        self.layoutAboutToBeChanged.emit()
        order = csvdata.filter_indices(self.rows, list(range(len(self.rows))), needle)
        if sort_column >= 0:
            order = csvdata.sorted_indices(self.rows, order, sort_column, descending)
        self.order = order
        self.layoutChanged.emit()

    # ---- Struktur ändern ------------------------------------------------------------------------
    def add_row(self, after_view_row: int) -> int:
        position = self.order[after_view_row] + 1 if 0 <= after_view_row < len(self.order) else len(self.rows)
        self.beginResetModel()
        self.rows.insert(position, [""] * self.columns)
        self.order = [i if i < position else i + 1 for i in self.order]
        insert_at = (after_view_row + 1) if 0 <= after_view_row < len(self.order) else len(self.order)
        self.order.insert(insert_at, position)
        self.endResetModel()
        self.edited.emit()
        return insert_at

    def remove_rows(self, view_rows: list[int]) -> None:
        doomed = sorted({self.order[r] for r in view_rows if 0 <= r < len(self.order)}, reverse=True)
        if not doomed:
            return
        self.beginResetModel()
        for index in doomed:
            del self.rows[index]
        gone = set(doomed)
        self.order = [i - sum(1 for d in doomed if d < i) for i in self.order if i not in gone]
        self.endResetModel()
        self.edited.emit()

    def add_column(self, after: int) -> None:
        position = after + 1 if 0 <= after < self.columns else self.columns
        self.beginResetModel()
        for row in self.rows:
            while len(row) < position:
                row.append("")
            row.insert(position, "")
        if self.has_header:
            while len(self.header) < position:
                self.header.append("")
            self.header.insert(position, f"Neu {position + 1}")
        self.columns += 1
        self.endResetModel()
        self.edited.emit()

    def remove_column(self, column: int) -> None:
        if not 0 <= column < self.columns:
            return
        self.beginResetModel()
        for row in self.rows:
            if column < len(row):
                del row[column]
        if self.has_header and column < len(self.header):
            del self.header[column]
        self.columns -= 1
        self.endResetModel()
        self.edited.emit()


class _Table(QTableView):
    """Kopieren/Einfügen als Tab-getrennter Block (wie Tabellenkalkulationen), Entf leert Zellen."""

    def keyPressEvent(self, event) -> None:
        model: CsvModel = self.model()
        if event.matches(QKeySequence.StandardKey.Copy):
            QApplication.clipboard().setText(self._selected_block())
            return
        if event.matches(QKeySequence.StandardKey.Paste) and self.currentIndex().isValid():
            model.paste_block(self.currentIndex().row(), self.currentIndex().column(), QApplication.clipboard().text())
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.state() != QTableView.State.EditingState:
            model.clear_cells([(i.row(), i.column()) for i in self.selectedIndexes()])
            return
        super().keyPressEvent(event)

    def _selected_block(self) -> str:
        indexes = self.selectedIndexes() or ([self.currentIndex()] if self.currentIndex().isValid() else [])
        if not indexes:
            return ""
        rows = sorted({i.row() for i in indexes})
        columns = sorted({i.column() for i in indexes})
        chosen = {(i.row(), i.column()) for i in indexes}
        model = self.model()
        return "\n".join("\t".join(model.data(model.index(r, c), Qt.ItemDataRole.EditRole) if (r, c) in chosen else ""
                                   for c in columns) for r in rows)


class CsvView(QWidget):
    """Werkzeugzeile + Tabelle. `changed` = der Nutzer hat Daten geändert (Datei gilt als ungespeichert)."""
    changed = Signal()
    status_changed = Signal()
    kind = "table"

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DataView")
        self.dialect = Dialect()
        self.encoding = "utf-8"
        self.dirty = False
        self._sort = (-1, False)
        self.model = CsvModel()
        self.model.edited.connect(self._on_edited)
        self.table = _Table()
        self.table.setObjectName("CsvTable")
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(26)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtern (alle Spalten) …")
        self.filter.setClearButtonEnabled(True)
        self.filter.setMinimumWidth(220)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self._apply_view)
        self.filter.textChanged.connect(lambda _t: self._filter_timer.start())
        self.header_box = QCheckBox("Kopfzeile")
        self.header_box.setToolTip("Erste Zeile als Spaltennamen verwenden")
        self.header_box.toggled.connect(self._toggle_header)
        self.delimiter_box = QComboBox()
        for sep, name in csvdata.DELIMITER_NAMES.items():
            self.delimiter_box.addItem(name, sep)
        self.delimiter_box.setToolTip("Trennzeichen (automatisch erkannt)")
        self.delimiter_box.activated.connect(self._change_delimiter)
        self.quoting_box = QComboBox()
        self.quoting_box.addItem("\" nach Bedarf", "minimal")
        self.quoting_box.addItem("\" bei allen Feldern", "all")
        self.quoting_box.setToolTip("Anführungszeichen beim Speichern (automatisch erkannt)")
        self.quoting_box.activated.connect(self._change_quoting)
        self.encoding_box = QComboBox()
        for value, label in ENCODINGS:
            self.encoding_box.addItem(label, value)
        self.encoding_box.setToolTip("Encoding der Datei (automatisch erkannt) – Umstellen liest die Datei neu")
        self.encoding_box.activated.connect(self._change_encoding)
        add_row = IconButton("plus", "Zeile einfügen (unter der Auswahl)")
        del_row = IconButton("minus", "Markierte Zeilen löschen")
        add_col = IconButton("columns-3", "Spalte einfügen (rechts der Auswahl)")
        del_col = IconButton("trash", "Aktuelle Spalte löschen")
        add_row.clicked.connect(self._add_row)
        del_row.clicked.connect(self._remove_rows)
        add_col.clicked.connect(lambda: self.model.add_column(self.table.currentIndex().column()))
        del_col.clicked.connect(self._remove_column)
        self.info = QLabel()
        self.info.setObjectName("DataInfo")

        strip = QFrame()
        strip.setObjectName("DataBar")
        bar = QHBoxLayout(strip)
        bar.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        bar.setSpacing(SPACING.sm)
        bar.addWidget(self.filter, 1)
        bar.addWidget(self.header_box)
        bar.addWidget(self.delimiter_box)
        bar.addWidget(self.quoting_box)
        bar.addWidget(self.encoding_box)
        for button in (add_row, del_row, add_col, del_col):
            bar.addWidget(button)
        bar.addWidget(self.info)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(strip)
        layout.addWidget(self.table, 1)
        self.overridden = False              # Nutzer hat Trennzeichen/Kopfzeile/Quoting selbst gewählt
        self._reparse = None                 # EditorPage: Callable[[Dialect], None]
        self._reencode = None                # EditorPage: Callable[[str], None]

    # ---- Laden / Zurückschreiben -----------------------------------------------------------------
    def load_text(self, text: str, name: str, dialect: Dialect | None = None, encoding: str = "utf-8") -> None:
        self.dialect = dialect.with_(trailing_newline=text.endswith("\n")) if dialect else csvdata.sniff(text, name)
        self.encoding = encoding
        rows = csvdata.parse(text, self.dialect)
        self.model.load(rows, self.dialect.has_header)
        self._sync_controls()
        self._sort = (-1, False)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.blockSignals(False)
        self.dirty = False
        self._resize_columns()
        self._update_info()

    def text(self) -> str:
        return csvdata.serialize(self.model.all_rows(), self.dialect)

    def _sync_controls(self) -> None:
        self.header_box.blockSignals(True)
        self.header_box.setChecked(self.dialect.has_header)
        self.header_box.blockSignals(False)
        index = self.delimiter_box.findData(self.dialect.delimiter)
        self.delimiter_box.setCurrentIndex(max(0, index))
        self.quoting_box.setCurrentIndex(max(0, self.quoting_box.findData(self.dialect.quoting)))
        self.encoding_box.setCurrentIndex(max(0, self.encoding_box.findData(self.encoding)))

    def _resize_columns(self) -> None:
        header = self.table.horizontalHeader()
        for column in range(min(self.model.columns, 40)):
            self.table.resizeColumnToContents(column)
            header.resizeSection(column, min(max(header.sectionSize(column), 60), 320))

    # ---- Aktionen ---------------------------------------------------------------------------------
    def _on_edited(self) -> None:
        self.dirty = True
        self._update_info()
        self.changed.emit()

    def _toggle_header(self, on: bool) -> None:
        rows = self.model.all_rows()
        self.dialect = self.dialect.with_(has_header=on)
        self.overridden = True
        self.model.load(rows, on)
        self._apply_view()
        self._update_info()   # nur Anzeige – die Datei bleibt gleich

    def _change_delimiter(self, _index: int) -> None:
        delimiter = self.delimiter_box.currentData()
        if delimiter == self.dialect.delimiter or self._reparse is None:
            return
        self.overridden = True
        self._reparse(self.dialect.with_(delimiter=delimiter))   # EditorPage liefert den aktuellen Text

    def _change_quoting(self, _index: int) -> None:
        quoting = self.quoting_box.currentData()
        if quoting != self.dialect.quoting:
            self.dialect = self.dialect.with_(quoting=quoting)
            self.overridden = True
            self._on_edited()                 # anderer Stil beim Speichern = Änderung an der Datei

    def _change_encoding(self, _index: int) -> None:
        encoding = self.encoding_box.currentData()
        if encoding != self.encoding and self._reencode is not None:
            self._reencode(encoding)
        self._sync_controls()                 # abgelehnt → Anzeige zurück auf das tatsächliche Encoding

    def _sort_by(self, column: int) -> None:
        current, descending = self._sort
        descending = not descending if current == column else False
        self._sort = (column, descending)
        self.table.horizontalHeader().setSortIndicator(column, Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder)
        self._apply_view()

    def _apply_view(self) -> None:
        self.model.apply_view(self._sort[0], self._sort[1], self.filter.text())
        self._update_info()

    def _add_row(self) -> None:
        view_row = self.model.add_row(self.table.currentIndex().row())
        self.table.setCurrentIndex(self.model.index(view_row, 0))
        self.table.edit(self.model.index(view_row, 0))

    def _remove_rows(self) -> None:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedIndexes()} or {self.table.currentIndex().row()})
        self.model.remove_rows([r for r in rows if r >= 0])

    def _remove_column(self) -> None:
        column = self.table.currentIndex().column()
        if column >= 0:
            self.model.remove_column(column)

    def _update_info(self) -> None:
        shown, total = len(self.model.order), len(self.model.rows)
        rows_text = f"{shown:,} von {total:,} Zeilen".replace(",", ".") if shown != total else f"{total:,} Zeilen".replace(",", ".")
        self.info.setText(f"{rows_text} · {self.model.columns} Spalten")
        self.status_changed.emit()

    def focus_filter(self) -> None:
        self.filter.setFocus()
        self.filter.selectAll()

    def setFocus(self) -> None:          # noqa: N802 – Qt-Name
        self.table.setFocus()

    def position_text(self) -> str:
        index = self.table.currentIndex()
        if not index.isValid():
            return "–"
        return f"Zeile {self.model.order[index.row()] + 1}, Spalte {index.column() + 1}"

    def status_parts(self) -> list[str]:
        name = csvdata.DELIMITER_NAMES.get(self.dialect.delimiter, self.dialect.delimiter)
        quoting = "alle Felder in Anführungszeichen" if self.dialect.quoting == "all" else "Anführungszeichen nach Bedarf"
        return [self.info.text(), f"Trennzeichen: {name}", quoting]
