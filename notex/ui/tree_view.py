"""Baumansicht für JSON/YAML: Schlüssel | Wert | Typ, Pfad der Auswahl (z. B. $.users[3].name) und „Pfad kopieren“.

Nur Ansicht – bearbeitet wird im Text. Kinder werden erst beim Aufklappen erzeugt, so bleiben auch große Dateien
flüssig. Ist der Text ungültig, zeigt die Ansicht den Fehler mit „Zur Stelle springen“.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from notex.core import structured
from notex.theme.tokens import SPACING
from notex.ui.widgets import IconButton

ROLE_NODE = Qt.ItemDataRole.UserRole + 1     # Index in DataTreeView._nodes – Werte bleiben Python-Objekte
MAX_CHILDREN = 5000        # mehr Kinder pro Knoten → „… weitere“ (Liste mit 1 Mio. Einträgen friert sonst ein)


class DataTreeView(QWidget):
    changed = Signal()                  # nie – der Baum ist nur Ansicht (Schnittstelle wie CsvView)
    status_changed = Signal()
    jump_requested = Signal(int)        # Zeichenposition des Fehlers im Text
    kind = "tree"

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DataView")
        self.dirty = False
        self.overridden = False
        self.dialect = None
        self.format_kind = "json"
        self.error: structured.ParseError | None = None
        self._nodes: list[tuple[list, object]] = []      # (Pfad, Wert) je Baumeintrag
        self.tree = QTreeWidget()
        self.tree.setObjectName("DataTree")
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Schlüssel", "Wert", "Typ"])
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().resizeSection(0, 260)
        self.tree.itemExpanded.connect(self._fill)
        self.tree.currentItemChanged.connect(lambda _c, _p: self._on_current())

        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setPlaceholderText("Pfad der Auswahl")
        self.path_field.setToolTip("Pfad des markierten Knotens (JSONPath-Schreibweise)")
        copy = QPushButton("Pfad kopieren")
        copy.clicked.connect(self.copy_path)
        expand = IconButton("chevrons-up-down", "Alles aufklappen (bis Ebene 3)")
        expand.clicked.connect(lambda: self._expand_levels(3))
        collapse = IconButton("chevrons-down-up", "Alles zuklappen")
        collapse.clicked.connect(self.tree.collapseAll)
        self.info = QLabel()
        self.info.setObjectName("DataInfo")
        strip = QFrame()
        strip.setObjectName("DataBar")
        bar = QHBoxLayout(strip)
        bar.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        bar.setSpacing(SPACING.sm)
        bar.addWidget(self.path_field, 1)
        bar.addWidget(copy)
        bar.addWidget(expand)
        bar.addWidget(collapse)
        bar.addWidget(self.info)

        self.error_label = QLabel()
        self.error_label.setObjectName("DataError")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        jump = QPushButton("Zur Stelle springen")
        jump.clicked.connect(lambda: self.jump_requested.emit(self.error.position) if self.error else None)
        error_page = QWidget()
        error_layout = QVBoxLayout(error_page)
        error_layout.addStretch(1)
        error_layout.addWidget(self.error_label)
        error_layout.addWidget(jump, 0, Qt.AlignmentFlag.AlignHCenter)
        error_layout.addStretch(1)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tree)
        self.stack.addWidget(error_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(strip)
        layout.addWidget(self.stack, 1)
        self._reparse = None
        self._reencode = None

    # ---- Laden ----------------------------------------------------------------------------------
    def load_text(self, text: str, name: str, dialect=None, encoding: str = "utf-8") -> None:
        self.format_kind = structured.kind_for(name) or "json"
        expanded = self._expanded_paths()
        current = self.path_field.text()
        value, self.error = structured.parse(text, self.format_kind) if text.strip() else (None, None)
        self.tree.clear()
        self._nodes = []
        if self.error is not None:
            self.error_label.setText(f"Ungültiges {self.format_kind.upper()} – Zeile {self.error.line}, "
                                     f"Spalte {self.error.column}:\n{self.error.message}")
            self.stack.setCurrentIndex(1)
            self.info.setText("")
            self.status_changed.emit()
            return
        self.stack.setCurrentIndex(0)
        root = self._item(self.tree.invisibleRootItem(), "$", value, [])
        root.setExpanded(True)
        self._restore(expanded, current)
        self.info.setText(f"{structured.type_name(value)} · {structured.preview(value)}")
        self.status_changed.emit()

    def text(self) -> str:              # nie aufgerufen (dirty bleibt False) – Schnittstelle wie CsvView
        return ""

    def _item(self, parent: QTreeWidgetItem, key, value, path: list) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [str(key), structured.preview(value), structured.type_name(value)])
        item.setData(0, ROLE_NODE, len(self._nodes))
        self._nodes.append((path, value))
        item.setToolTip(1, structured.preview(value, 2000))
        if structured.children(value):
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        return item

    def _fill(self, item: QTreeWidgetItem) -> None:
        if item.childCount():
            return
        path, value = self._node(item)
        entries = structured.children(value)
        for key, child in entries[:MAX_CHILDREN]:
            self._item(item, key, child, path + [key])
        if len(entries) > MAX_CHILDREN:
            more = QTreeWidgetItem(item, [f"… {len(entries) - MAX_CHILDREN} weitere", "", ""])
            more.setDisabled(True)
        if not entries:
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)

    def _expand_levels(self, depth: int) -> None:
        def walk(item: QTreeWidgetItem, level: int) -> None:
            if level > depth or item.childIndicatorPolicy() == QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator:
                return
            item.setExpanded(True)
            for i in range(min(item.childCount(), 200)):
                walk(item.child(i), level + 1)
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i), 0)

    def _expanded_paths(self) -> set[str]:
        paths = set()

        def walk(item: QTreeWidgetItem) -> None:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.isExpanded():
                    paths.add(structured.path_string(self._node(child)[0]))
                    walk(child)
        walk(self.tree.invisibleRootItem())
        return paths

    def _restore(self, expanded: set[str], current: str) -> None:
        """Nach dem Neuladen (Text geändert) die aufgeklappten Knoten und die Auswahl behalten."""
        def walk(item: QTreeWidgetItem) -> None:
            for i in range(item.childCount()):
                child = item.child(i)
                path = structured.path_string(self._node(child)[0])
                if path == current:
                    self.tree.setCurrentItem(child)
                if path in expanded:
                    child.setExpanded(True)
                    walk(child)
        walk(self.tree.invisibleRootItem())

    def _node(self, item: QTreeWidgetItem | None) -> tuple[list, object]:
        index = item.data(0, ROLE_NODE) if item is not None else None
        return self._nodes[index] if isinstance(index, int) and 0 <= index < len(self._nodes) else ([], None)

    # ---- Auswahl / Pfad ---------------------------------------------------------------------------
    def _on_current(self) -> None:
        item = self.tree.currentItem()
        enabled = item is not None and item.data(0, ROLE_NODE) is not None
        self.path_field.setText(structured.path_string(self._node(item)[0]) if enabled else "")
        self.status_changed.emit()

    def copy_path(self) -> None:
        if self.path_field.text():
            QApplication.clipboard().setText(self.path_field.text())

    def focus_filter(self) -> None:
        self.tree.setFocus()

    def setFocus(self) -> None:          # noqa: N802 – Qt-Name
        self.tree.setFocus()

    def position_text(self) -> str:
        return self.path_field.text() or "–"

    def status_parts(self) -> list[str]:
        if self.error is not None:
            return [self.error.short(self.format_kind), ""]
        return [self.info.text(), ""]
