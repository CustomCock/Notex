"""Variablen verwalten: Tabelle Name | Wert | Beschreibung, Suche, Bearbeiten, Import/Export (JSON), Präfix."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from notex.core import variables as vb
from notex.core.variables import Variable
from notex.theme.tokens import SPACING
from notex.ui import dialogs

SECRET_HINT = ("Keine Passwörter oder Geheimnisse als Variablen speichern – variables.json liegt unverschlüsselt "
               "neben der App.")


class VariableEditDialog(QDialog):
    def __init__(self, parent: QWidget, variable: Variable | None, existing: list[str], prefix: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Variable bearbeiten" if variable else "Neue Variable")
        self.resize(520, 360)
        self.original = variable.name if variable else None
        self.existing = set(existing) - {self.original}
        self.name = QLineEdit(variable.name if variable else "")
        self.name.setPlaceholderText("z. B. gruss, firma_tel, 23")
        self.value = QPlainTextEdit(variable.value if variable else "")
        self.description = QLineEdit(variable.description if variable else "")
        self.error = QLabel()
        self.error.setObjectName("StatusWarn")
        hint = QLabel(f"Im Text: {prefix}Name. Name aus Buchstaben, Ziffern und Unterstrich. {SECRET_HINT}")
        hint.setObjectName("SettingsNote")
        hint.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Wert", self.value)
        form.addRow("Beschreibung", self.description)
        ok = QPushButton("Speichern")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.error, 1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(buttons)

    def _accept(self) -> None:
        name = self.name.text().strip()
        if not vb.valid_name(name):
            self.error.setText("Name: nur Buchstaben, Ziffern, Unterstrich")
            return
        if name in self.existing:
            self.error.setText(f"„{name}“ gibt es schon")
            return
        self.accept()

    def result_variable(self) -> Variable:
        return Variable(self.name.text().strip(), self.value.toPlainText(), self.description.text().strip())


class VariablesPanel(QWidget):
    """Inhalt der Einstellungsseite „Variablen“ – Änderungen gelten sofort (variables.json wird geschrieben)."""

    def __init__(self, window, service) -> None:
        super().__init__()
        self.window_ = window
        self.service = service
        self.search = QLineEdit()
        self.search.setPlaceholderText("Variablen durchsuchen …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._fill)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Wert", "Beschreibung"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(260)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        buttons = QHBoxLayout()
        for text, slot in (("Hinzufügen …", self._add), ("Bearbeiten …", self._edit), ("Löschen", self._delete),
                           ("Importieren …", self._import), ("Exportieren …", self._export)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.prefix = QLineEdit(service.prefix)
        self.prefix.setMaximumWidth(80)
        self.prefix.setToolTip("Zeichen vor dem Namen, z. B. § oder $ – keine Buchstaben, Ziffern, _ oder \\")
        self.prefix.editingFinished.connect(self._set_prefix)
        self.copy_mode = QComboBox()
        self.copy_mode.addItem("Werte einsetzen", "values")
        self.copy_mode.addItem("Tokens kopieren (§name)", "tokens")
        self.copy_mode.setCurrentIndex(0 if service.copy_values else 1)
        self.copy_mode.currentIndexChanged.connect(
            lambda i: service.config.__setitem__("copy", self.copy_mode.itemData(i)))
        options = QFormLayout()
        options.addRow("Präfix", self.prefix)
        options.addRow("Kopieren (Ctrl+C)", self.copy_mode)
        warning = QLabel(SECRET_HINT)
        warning.setObjectName("SettingsNote")
        warning.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        layout.addLayout(options)
        layout.addWidget(warning)
        self._fill()

    def _fill(self) -> None:
        needle = self.search.text().casefold()
        rows = [v for v in sorted(self.service.variables, key=lambda v: v.name.casefold())
                if not needle or needle in f"{v.name} {v.value} {v.description}".casefold()]
        self.table.setRowCount(len(rows))
        for row, variable in enumerate(rows):
            for column, text in enumerate((self.service.prefix + variable.name, vb.display_value(variable.value, 120),
                                           variable.description)):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, variable.name)
                item.setToolTip(variable.value if column == 1 else text)
                self.table.setItem(row, column, item)
        self.table.resizeColumnToContents(0)

    def _selected(self) -> str | None:
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _add(self) -> None:
        dialog = VariableEditDialog(self, None, [v.name for v in self.service.variables], self.service.prefix)
        if dialog.exec():
            self.service.upsert(dialog.result_variable())
            self._fill()

    def _edit(self) -> None:
        name = self._selected()
        if name is None:
            return
        dialog = VariableEditDialog(self, self.service.get(name), [v.name for v in self.service.variables],
                                    self.service.prefix)
        if dialog.exec():
            self.service.upsert(dialog.result_variable(), old_name=name)
            self._fill()

    def _delete(self) -> None:
        name = self._selected()
        if name is None:
            return
        if dialogs.confirm(self, "Variable löschen", f"„{self.service.prefix}{name}“ löschen?", yes="Löschen",
                           danger=True, informative="In Dateien bleibt das Token stehen und ist dann normaler Text."):
            self.service.delete(name)
            self._fill()

    def _import(self) -> None:
        target, _ = QFileDialog.getOpenFileName(self, "Variablen importieren", "", "JSON (*.json)")
        if not target:
            return
        try:
            imported = vb.parse_variables(json.loads(Path(target).read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            dialogs.warn(self, "Import", str(error))
            return
        merged = {v.name: v for v in self.service.variables}
        merged.update({v.name: v for v in imported})
        self.service.set_all(list(merged.values()))
        self._fill()
        self.window_.toast.show_message(f"{len(imported)} Variable(n) importiert", "variable")

    def _export(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self, "Variablen exportieren", "variablen.json", "JSON (*.json)")
        if target:
            vb.save_variables(Path(target), self.service.variables)

    def _set_prefix(self) -> None:
        value = self.prefix.text().strip()
        if value and not any(c.isalnum() or c in "_\\" for c in value):
            self.service.set_prefix(value)
        self.prefix.setText(self.service.prefix)
        self._fill()
