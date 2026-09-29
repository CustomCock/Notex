"""Vorlage wählen: Suchfeld (Name + Kategorie) und Vorlagen in Abschnitten nach Kategorie, alphabetisch.

Datei-Vorlagen und Fragebögen stehen gemeinsam in der Liste (Fragebögen starten den Assistenten). Die Einordnung
kommt aus core/template_catalog – Dateien werden dafür nie verschoben.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from notex.core import template_catalog as tc
from notex.theme.icons import icon
from notex.theme.tokens import SPACING

ROLE = Qt.ItemDataRole.UserRole


def _icon_name(entry: tc.Entry) -> str:
    if entry.kind == "questionnaire":
        return "clipboard-list"
    if Path(entry.key).suffix.lower() == ".csv" or entry.category == "Tabellen":
        return "table"
    return "file-text"


class TemplatePickerDialog(QDialog):
    def __init__(self, parent, entries: list[tc.Entry], on_open_folder=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Neue Datei aus Vorlage")
        self.resize(560, 620)
        self.entries = entries
        self.chosen: tc.Entry | None = None

        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen: Name oder Kategorie (z. B. „mail termin“, „ausbildung“) …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self._accept_current)

        self.tree = QTreeWidget()
        self.tree.setObjectName("AnalysisTree")
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(SPACING.lg)
        self.tree.itemDoubleClicked.connect(lambda item, _c: self._accept_item(item))
        self.tree.itemActivated.connect(lambda item, _c: self._accept_item(item))
        self.tree.currentItemChanged.connect(lambda *_: self._update_buttons())

        self.hint = QLabel("Eigene Vorlagen: .md/.txt/.csv in den Vorlagen-Ordner legen – ein Unterordner wird "
                           "zur Kategorie. Fragebögen (.yaml) liegen in templates/fragebogen.")
        self.hint.setObjectName("SettingsNote")
        self.hint.setWordWrap(True)

        self.ok_button = QPushButton("Erstellen")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._accept_current)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        footer = QHBoxLayout()
        if on_open_folder is not None:
            folder = QPushButton(icon("folder-open"), "Vorlagen-Ordner")
            folder.clicked.connect(on_open_folder)
            footer.addWidget(folder)
        footer.addStretch(1)
        footer.addWidget(cancel)
        footer.addWidget(self.ok_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.hint)
        layout.addLayout(footer)
        self.refresh()
        self.search.setFocus()

    # ---- Liste ------------------------------------------------------------------------------------
    def refresh(self) -> None:
        self.tree.clear()
        shown = tc.filter_entries(self.entries, self.search.text())
        first = None
        for category, items in tc.grouped(shown):
            head = QTreeWidgetItem([f"{category}  ·  {len(items)}"])
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)                 # Abschnitt: nicht auswählbar
            font = head.font(0)
            font.setBold(True)
            head.setFont(0, font)
            self.tree.addTopLevelItem(head)
            for entry in items:
                label = entry.title + ("  (Fragebogen)" if entry.kind == "questionnaire" else "")
                child = QTreeWidgetItem([label])
                child.setIcon(0, icon(_icon_name(entry)))
                child.setToolTip(0, f"{entry.category} · templates/{entry.key}")
                child.setData(0, ROLE, entry)
                head.addChild(child)
                first = first or child
            head.setExpanded(True)
        if first is None:
            empty = QTreeWidgetItem(["Nichts gefunden." if self.search.text().strip() else
                                     "Keine Vorlagen – Vorlagen-Ordner öffnen und Dateien ablegen."])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tree.addTopLevelItem(empty)
        else:
            self.tree.setCurrentItem(first)
        self._update_buttons()

    def visible_entries(self) -> list[tc.Entry]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            head = self.tree.topLevelItem(i)
            out.extend(head.child(j).data(0, ROLE) for j in range(head.childCount()))
        return out

    def section_titles(self) -> list[str]:
        return [self.tree.topLevelItem(i).text(0).split("  ·  ")[0] for i in range(self.tree.topLevelItemCount())
                if self.tree.topLevelItem(i).childCount()]

    # ---- Auswahl ----------------------------------------------------------------------------------
    def _update_buttons(self) -> None:
        item = self.tree.currentItem()
        self.ok_button.setEnabled(item is not None and item.data(0, ROLE) is not None)

    def _accept_item(self, item) -> None:
        entry = item.data(0, ROLE) if item is not None else None
        if entry is not None:
            self.chosen = entry
            self.accept()

    def _accept_current(self) -> None:
        self._accept_item(self.tree.currentItem())


def choose_template(parent, entries: list[tc.Entry], on_open_folder=None) -> tc.Entry | None:
    dialog = TemplatePickerDialog(parent, entries, on_open_folder)
    return dialog.chosen if dialog.exec() == QDialog.DialogCode.Accepted else None
