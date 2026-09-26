"""Verzeichnisbaum von data/ auf Basis von QFileSystemModel.

QFileSystemModel bringt vieles fertig mit: lazy Laden, Namensfilter, Umbenennen,
Drag & Drop (Verschieben) und einen eigenen Watcher, der den Baum aktuell hält.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QFileSystemModel, QTreeView

from textbaum.theme.icons import FlatIconProvider


class FileTree(QTreeView):
    file_activated = Signal(Path)

    def __init__(self, root: Path, extensions: list[str]) -> None:
        super().__init__()
        self.root = Path(root)

        self.model_ = QFileSystemModel(self)
        self.model_.setIconProvider(FlatIconProvider())
        self.model_.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model_.setNameFilters([f"*{ext}" for ext in extensions])
        self.model_.setNameFilterDisables(False)  # nicht passende Dateien ausblenden statt ausgrauen
        self.model_.setReadOnly(False)            # nötig für Umbenennen und Drag & Drop
        self.model_.setRootPath(str(self.root))

        self.setModel(self.model_)
        self.setRootIndex(self.model_.index(str(self.root)))
        for column in range(1, self.model_.columnCount()):  # nur Namen zeigen
            self.hideColumn(column)
        self.setHeaderHidden(True)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Umbenennen nur per F2/Menü
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setIndentation(14)

        self.clicked.connect(self._on_clicked)

    # ---- Hilfen ------------------------------------------------------------
    def path_at(self, index: QModelIndex) -> Path | None:
        return Path(self.model_.filePath(index)) if index.isValid() else None

    def selected_path(self) -> Path | None:
        return self.path_at(self.currentIndex())

    def index_for(self, path: Path) -> QModelIndex:
        return self.model_.index(str(path))

    def _on_clicked(self, index: QModelIndex) -> None:
        path = self.path_at(index)
        if path is not None and path.is_file():
            self.file_activated.emit(path)

    def keyPressEvent(self, event) -> None:
        # Enter/Return öffnet Dateien bzw. klappt Ordner um
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            path = self.selected_path()
            if path is not None and path.is_file():
                self.file_activated.emit(path)
                return
            if path is not None and path.is_dir():
                self.setExpanded(self.currentIndex(), not self.isExpanded(self.currentIndex()))
                return
        super().keyPressEvent(event)
