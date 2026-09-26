"""Verzeichnisbaum von data/ auf Basis von QFileSystemModel.

QFileSystemModel bringt vieles fertig mit: lazy Laden, Namensfilter, Umbenennen
und einen eigenen Watcher, der den Baum aktuell hält, wenn extern Dateien
dazukommen. Drag & Drop machen wir selbst (dropEvent), damit offene Tabs vom
Verschieben erfahren.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QPoint, Qt, Signal
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QAbstractItemView, QFileSystemModel, QInputDialog, QMenu, QMessageBox, QTreeView

from notex.core import fileops
from notex.theme.icons import FlatIconProvider


class FileTree(QTreeView):
    file_activated = Signal(Path)
    path_renamed = Signal(Path, Path)   # alt, neu – auch bei Verschieben
    path_deleted = Signal(Path)

    def __init__(self, root: Path, extensions: list[str]) -> None:
        super().__init__()
        self.root = Path(root)
        self._expanded: set[str] = set()

        self.model_ = QFileSystemModel(self)
        self.model_.setIconProvider(FlatIconProvider())
        self.model_.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model_.setNameFilters([f"*{ext}" for ext in extensions])
        self.model_.setNameFilterDisables(False)  # nicht passende Dateien ausblenden statt ausgrauen
        self.model_.setReadOnly(False)            # nötig für Umbenennen per F2
        self.model_.setRootPath(str(self.root))
        self.model_.fileRenamed.connect(self._on_model_renamed)

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

        # Drag & Drop: Dateien/Ordner innerhalb von data/ verschieben, von außen hineinkopieren
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.clicked.connect(self._on_clicked)
        self.expanded.connect(lambda index: self._expanded.add(self._relative(self.path_at(index))))
        self.collapsed.connect(lambda index: self._expanded.discard(self._relative(self.path_at(index))))

    # ---- Hilfen ------------------------------------------------------------
    def path_at(self, index: QModelIndex) -> Path | None:
        return Path(self.model_.filePath(index)) if index.isValid() else None

    def selected_path(self) -> Path | None:
        return self.path_at(self.currentIndex())

    def index_for(self, path: Path) -> QModelIndex:
        return self.model_.index(str(path))

    def _relative(self, path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return ""

    def folder_for(self, path: Path | None) -> Path:
        """Zielordner für 'Neu…': der gewählte Ordner, sonst der Ordner der gewählten Datei, sonst root."""
        if path is None:
            return self.root
        return path if path.is_dir() else path.parent

    def select_path(self, path: Path) -> None:
        index = self.index_for(path)
        if index.isValid():
            self.setCurrentIndex(index)
            self.scrollTo(index)

    # ---- Auf-/Zuklappzustand ------------------------------------------------
    def expanded_folders(self) -> list[str]:
        return sorted(self._expanded)

    def restore_expanded(self, relative_paths: list[str]) -> None:
        # Sortiert, damit Eltern vor Kindern aufgeklappt werden. index(path) legt
        # die Knoten bei QFileSystemModel bei Bedarf an, auch wenn noch nichts geladen war.
        for rel in sorted(relative_paths):
            path = self.root / rel
            if path.is_dir():
                self.expand(self.index_for(path))

    # ---- Events -------------------------------------------------------------
    def _on_clicked(self, index: QModelIndex) -> None:
        path = self.path_at(index)
        if path is not None and path.is_file():
            self.file_activated.emit(path)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            path = self.selected_path()
            if path is not None and path.is_file():
                self.file_activated.emit(path)
                return
            if path is not None and path.is_dir():
                self.setExpanded(self.currentIndex(), not self.isExpanded(self.currentIndex()))
                return
        if key == Qt.Key.Key_F2:
            self.rename_selected()
            return
        if key == Qt.Key.Key_Delete:
            self.delete_selected()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        target = self.path_at(index) if index.isValid() else self.root
        if target is None:
            return
        if target.is_file():
            target = target.parent

        for url in event.mimeData().urls():
            source = Path(url.toLocalFile())
            if not source.exists() or source.parent == target or source == target:
                continue
            if fileops.is_within(target, source):
                QMessageBox.warning(self, "Verschieben", f"„{source.name}“ kann nicht in sich selbst verschoben werden.")
                continue
            try:
                if fileops.is_within(source, self.root):
                    new_path = fileops.move_path(source, target)
                    self.path_renamed.emit(source, new_path)
                else:
                    # Von außerhalb (z. B. aus dem Explorer) hineingezogen: kopieren
                    destination = target / source.name
                    if destination.exists():
                        raise FileExistsError(f"Existiert bereits: {destination.name}")
                    if source.is_dir():
                        shutil.copytree(source, destination)
                    else:
                        shutil.copy2(source, destination)
            except (OSError, shutil.Error) as error:
                QMessageBox.warning(self, "Verschieben fehlgeschlagen", str(error))
        # Wir haben verschoben. Als Ergebnis "Copy" melden, sonst würde Qt nach einem
        # "Move" die Quell-Einträge zusätzlich über das Modell löschen lassen.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    # ---- Kontextmenü ---------------------------------------------------------
    def _show_context_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        path = self.path_at(index)
        if index.isValid():
            self.setCurrentIndex(index)
        else:
            self.clearSelection()
            self.setCurrentIndex(QModelIndex())

        menu = QMenu(self)
        menu.addAction("Neue Datei", lambda: self.create_file(self.folder_for(path)))
        menu.addAction("Neuer Ordner", lambda: self.create_folder(self.folder_for(path)))
        if path is not None:
            menu.addSeparator()
            menu.addAction("Umbenennen\tF2", self.rename_selected)
            menu.addAction("In den Papierkorb\tEntf", self.delete_selected)
        menu.addSeparator()
        menu.addAction("Im Explorer anzeigen", lambda: fileops.reveal_in_file_manager(path or self.root))
        menu.exec(self.viewport().mapToGlobal(pos))

    def create_file(self, folder: Path) -> None:
        suggestion = fileops.unique_path(folder, "Neu", ".txt").name
        name, ok = QInputDialog.getText(self, "Neue Datei", "Dateiname:", text=suggestion)
        if not ok or not name.strip():
            return
        try:
            path = fileops.create_file(folder, name.strip())
        except OSError as error:
            QMessageBox.warning(self, "Neue Datei", str(error))
            return
        self.expand(self.index_for(folder))
        self.select_path(path)
        self.file_activated.emit(path)

    def create_folder(self, folder: Path) -> None:
        suggestion = fileops.unique_path(folder, "Neuer Ordner").name
        name, ok = QInputDialog.getText(self, "Neuer Ordner", "Ordnername:", text=suggestion)
        if not ok or not name.strip():
            return
        try:
            path = fileops.create_folder(folder, name.strip())
        except OSError as error:
            QMessageBox.warning(self, "Neuer Ordner", str(error))
            return
        self.expand(self.index_for(folder))
        self.select_path(path)

    def rename_selected(self) -> None:
        index = self.currentIndex()
        if index.isValid():
            self.edit(index)  # Inline-Editor; das Modell benennt um und feuert fileRenamed

    def _on_model_renamed(self, folder: str, old_name: str, new_name: str) -> None:
        self.path_renamed.emit(Path(folder) / old_name, Path(folder) / new_name)

    def delete_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        kind = "Ordner" if path.is_dir() else "Datei"
        answer = QMessageBox.question(
            self, "In den Papierkorb",
            f"{kind} „{path.name}“ in den Papierkorb verschieben?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            fileops.move_to_trash(path)
        except Exception as error:  # noqa: BLE001 – send2trash wirft eigene Exception-Typen
            QMessageBox.warning(self, "Löschen fehlgeschlagen", str(error))
            return
        self.path_deleted.emit(path)
