"""Orte-Leiste über dem Datei-Baum: Notizen, Schnellzugriff, Dieser PC.

Eine kompakte Navigation (eigenes QTreeWidget). Ein Klick auf einen Eintrag schaltet
den darunterliegenden Datei-Baum auf diesen Ordner um. „Dieser PC" und die Laufwerke
kommen aus `core/places` (plattformabhängig, ohne Qt).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from notex.core import places
from notex.theme.icons import icon
from notex.theme.theme import style_menu
from notex.theme.tokens import LAYOUT

PATH_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1


class PlacesPanel(QTreeWidget):
    place_selected = Signal(Path)     # ein Ort wurde gewählt → Baum umschalten
    pin_removed = Signal(Path)        # ein Schnellzugriff-Eintrag soll weg

    def __init__(self, root: Path, config: dict[str, Any]) -> None:
        super().__init__()
        self.setObjectName("PlacesPanel")
        self.notes_root = Path(root)
        self.config = config
        self.setHeaderHidden(True)
        self.setFrameShape(QTreeWidget.Shape.NoFrame)
        self.setIndentation(LAYOUT.tree_indent)
        self.setUniformRowHeights(True)
        self.setExpandsOnDoubleClick(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemClicked.connect(self._on_clicked)
        self._current_path: Path | None = None
        self.refresh()

    # ---- Aufbau ---------------------------------------------------------------------------
    def _leaf(self, parent, place: places.Place) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [place.label])
        item.setIcon(0, icon(place.icon))
        item.setData(0, PATH_ROLE, str(place.path))
        item.setData(0, KIND_ROLE, place.kind)
        item.setToolTip(0, str(place.path))
        return item

    def _section(self, label: str) -> QTreeWidgetItem:
        head = QTreeWidgetItem(self, [label])
        head.setFlags(Qt.ItemFlag.ItemIsEnabled)   # nicht auswählbar, nur Kopf
        head.setData(0, KIND_ROLE, "section")
        head.setFirstColumnSpanned(True)
        return head

    def refresh(self) -> None:
        expanded = self._expanded_sections()
        self.clear()

        notes = self._leaf(self, places.notes_place(self.notes_root))
        notes.setData(0, KIND_ROLE, "notes")

        quick = self._section("Schnellzugriff")
        pinned = places.pinned_places(self.config)
        for place in pinned:
            self._leaf(quick, place)
        if not pinned:
            hint = QTreeWidgetItem(quick, ["(Ordner per Rechtsklick anheften)"])
            hint.setFlags(Qt.ItemFlag.ItemIsEnabled)
            hint.setData(0, KIND_ROLE, "hint")
            hint.setDisabled(True)

        this_pc = self._section("Dieser PC")
        for place in places.this_pc_places():
            self._leaf(this_pc, place)

        # Abschnitte standardmäßig offen (bzw. wie zuvor)
        quick.setExpanded(expanded.get("Schnellzugriff", True))
        this_pc.setExpanded(expanded.get("Dieser PC", True))
        self._highlight_current()

    def _expanded_sections(self) -> dict[str, bool]:
        state: dict[str, bool] = {}
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, KIND_ROLE) == "section":
                state[item.text(0)] = item.isExpanded()
        return state

    # ---- Auswahl --------------------------------------------------------------------------
    def set_current_path(self, path: Path) -> None:
        self._current_path = Path(path)
        self._highlight_current()

    def _highlight_current(self) -> None:
        if self._current_path is None:
            return
        target = str(self._current_path)
        it = self._iter_items()
        for item in it:
            if item.data(0, PATH_ROLE) == target:
                self.setCurrentItem(item)
                return
        self.clearSelection()
        self.setCurrentItem(None)

    def _iter_items(self):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            yield item
            for c in range(item.childCount()):
                stack.append(item.child(c))

    def _on_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        kind = item.data(0, KIND_ROLE)
        if kind == "section":
            item.setExpanded(not item.isExpanded())
            return
        path = item.data(0, PATH_ROLE)
        if path:
            self.place_selected.emit(Path(path))

    def _context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None or item.data(0, KIND_ROLE) != "pinned":
            return
        menu = style_menu(QMenu(self))
        path = Path(item.data(0, PATH_ROLE))
        menu.addAction(icon("x"), "Vom Schnellzugriff entfernen", lambda: self.pin_removed.emit(path))
        menu.exec(self.viewport().mapToGlobal(pos))

    def retheme(self) -> None:
        self.setIndentation(LAYOUT.tree_indent)
        self.refresh()
