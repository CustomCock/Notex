"""Strings-Dialog: Liste mit Offset, Encoding, Kategorie, Text; Filter/Regex/Kategorie; Doppelklick → Hex-Ansicht."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QTableView)

from notex.core import strings as st
from notex.theme.tokens import COLORS
from notex.ui.analysis_dialog import AnalysisDialog

HEADERS = ["Offset", "Encoding", "Art", "Text"]


class StringsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[st.FoundString] = []
        self.categories: list[str | None] = []
        self.visible: list[int] = []

    def load(self, items: list[st.FoundString]) -> None:
        self.beginResetModel()
        self.items = items
        self.categories = [st.classify(item.text) for item in items]
        self.visible = list(range(len(items)))
        self.endResetModel()

    def apply_filter(self, needle: str, regex: bool, category: str) -> str | None:
        """Filtern; gibt eine Fehlermeldung bei ungültiger Regex zurück."""
        pattern = None
        if needle and regex:
            try:
                pattern = re.compile(needle, re.I)
            except re.error as error:
                return f"Ungültige Regex: {error}"
        low = needle.casefold()
        self.beginResetModel()
        self.visible = []
        for index, item in enumerate(self.items):
            kind = self.categories[index]
            if category == "interesting" and kind is None or category not in ("all", "interesting") and kind != category:
                continue
            if needle and not (pattern.search(item.text) if pattern else low in item.text.casefold()):
                continue
            self.visible.append(index)
        self.endResetModel()
        return None

    def item(self, row: int) -> st.FoundString:
        return self.items[self.visible[row]]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.visible)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        position = self.visible[index.row()]
        item, kind = self.items[position], self.categories[position]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (f"0x{item.offset:08X}", st.LABELS[item.encoding], st.CATEGORIES.get(kind, "") if kind else "",
                    item.text if len(item.text) <= 300 else item.text[:299] + "…")[column]
        if role == Qt.ItemDataRole.ToolTipRole and column == 3 and len(item.text) > 80:
            return item.text[:2000]
        if role == Qt.ItemDataRole.ForegroundRole and kind is not None and column in (2, 3):
            return QColor(COLORS.warning if kind == "base64" else COLORS.accent)
        return None


class StringsDialog(AnalysisDialog):
    def __init__(self, window, path: Path, config: dict) -> None:
        super().__init__(window, path, "Strings")
        self.config = config.setdefault("strings", {})
        self.min_len = QSpinBox()
        self.min_len.setRange(2, 64)
        self.min_len.setValue(int(self.config.get("min_len", 4)))
        self.min_len.setPrefix("mind. ")
        self.min_len.setSuffix(" Zeichen")
        self.encodings = {key: QCheckBox(st.LABELS[key]) for key in st.ENCODINGS}
        chosen = self.config.get("encodings", ["ascii", "utf16le"])
        for key, box in self.encodings.items():
            box.setChecked(key in chosen)
        run = QPushButton("Neu suchen")
        run.clicked.connect(self.run)
        options = QHBoxLayout()
        options.addWidget(self.min_len)
        for box in self.encodings.values():
            options.addWidget(box)
        options.addStretch(1)
        options.addWidget(run)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtern …")
        self.filter.setClearButtonEnabled(True)
        self.regex = QCheckBox("Regex")
        self.category = QComboBox()
        self.category.addItem("Alle", "all")
        self.category.addItem("Nur interessante", "interesting")
        for key, label in st.CATEGORIES.items():
            self.category.addItem(label, key)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self._apply_filter)
        self.filter.textChanged.connect(lambda _t: self._filter_timer.start())
        self.regex.toggled.connect(lambda _on: self._filter_timer.start())
        self.category.currentIndexChanged.connect(lambda _i: self._filter_timer.start())
        filters = QHBoxLayout()
        filters.addWidget(self.filter, 1)
        filters.addWidget(self.regex)
        filters.addWidget(self.category)
        self.model = StringsModel()
        self.table = QTableView()
        self.table.setObjectName("AnalysisTable")
        self.table.setModel(self.model)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 90)
        self.table.doubleClicked.connect(self._jump)
        self.table.activated.connect(self._jump)
        hint = QLabel("Doppelklick springt in die Hex-Ansicht.")
        hint.setObjectName("SettingsNote")
        self.body.addLayout(options)
        self.body.addLayout(filters)
        self.body.addWidget(self.table, 1)
        self.body.addWidget(hint)
        export = QPushButton("Als .txt exportieren …")
        export.clicked.connect(self._export)
        self.add_footer_button(export)
        self.finish_layout()
        self.truncated = False
        self.run()

    def run(self) -> None:
        encodings = tuple(key for key, box in self.encodings.items() if box.isChecked()) or ("ascii",)
        self.config["min_len"] = self.min_len.value()
        self.config["encodings"] = list(encodings)
        min_len, path = self.min_len.value(), self.path
        self.start(lambda progress, cancelled: st.extract_file(path, min_len, encodings, progress=progress,
                                                               cancelled=cancelled))

    def show_result(self, result) -> None:
        items, self.truncated = result
        self.model.load(items)
        self._apply_filter()

    def _apply_filter(self) -> None:
        error = self.model.apply_filter(self.filter.text(), self.regex.isChecked(), self.category.currentData())
        self.filter.setProperty("state", "bad" if error else "")
        self.filter.style().unpolish(self.filter)
        self.filter.style().polish(self.filter)
        total = len(self.model.items)
        shown = self.model.rowCount()
        interesting = sum(1 for kind in self.model.categories if kind)
        text = error or (f"{shown:,} von {total:,} Strings".replace(",", ".") + f" · {interesting} interessant")
        if self.truncated:
            text += f" · nach {st.DEFAULT_LIMIT:,} Treffern abgeschnitten".replace(",", ".")
        self.status.setText(text)

    def _jump(self, index) -> None:
        if index.isValid():
            item = self.model.item(index.row())
            self.jump(item.offset, item.length)

    def _export(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self, "Strings exportieren", str(self.path.with_suffix(".strings.txt")),
                                                "Text (*.txt)")
        if target:
            items = [self.model.item(row) for row in range(self.model.rowCount())]
            Path(target).write_text(st.to_text_export(items), encoding="utf-8")
            self.status.setText(f"{len(items)} Strings exportiert → {Path(target).name}")
