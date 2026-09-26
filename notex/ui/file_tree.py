"""Verzeichnisbaum von data/ auf Basis von QFileSystemModel.

QFileSystemModel bringt vieles fertig mit: lazy Laden, Namensfilter, Umbenennen
und einen eigenen Watcher, der den Baum aktuell hält, wenn extern Dateien
dazukommen. Drag & Drop machen wir selbst (dropEvent), damit offene Tabs vom
Verschieben erfahren.

Aussehen: Zeilen 28 px hoch, Auswahl/Hover als abgerundete Fläche über die
ganze Zeile (drawRow), Chevrons als Lucide-Icons (drawBranches), Ordner-Icon
wechselt beim Aufklappen.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QPersistentModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDropEvent, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFileSystemModel, QLabel, QMenu, QStyledItemDelegate,
                               QStyleOptionViewItem, QTreeView)

from notex.core import fileops
from notex.theme.icons import LucideIconProvider, icon, pixmap
from notex.theme.theme import style_menu
from notex.theme.tokens import COLORS, DURATION, LAYOUT, RADIUS, SPACING
from notex.ui import anim, dialogs

CHEVRON_SIZE = 14


class TreeDelegate(QStyledItemDelegate):
    """Zeilenhöhe aus den Tokens, Ordner-Icon je nach Zustand."""

    def __init__(self, view: "FileTree") -> None:
        super().__init__(view)
        self.view = view

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), LAYOUT.tree_row_height)

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        if self.view.model_.isDir(index):
            option.icon = icon("folder-open" if self.view.isExpanded(index) else "folder")
        elif fileops.is_encrypted_path(self.view.model_.fileName(index)):
            option.icon = icon("lock")


class FileTree(QTreeView):
    file_activated = Signal(Path)
    path_renamed = Signal(Path, Path)   # alt, neu – auch bei Verschieben
    path_deleted = Signal(Path)

    def __init__(self, root: Path, extensions: list[str]) -> None:
        super().__init__()
        self.root = Path(root)
        self._expanded: set[str] = set()
        self._hover_row = QModelIndex()
        self._hover_prev = QModelIndex()
        self._hover = anim.HoverFade(self, DURATION.hover)
        self._hover.changed.connect(self.viewport().update)
        self._chevrons: dict[QPersistentModelIndex, float] = {}   # laufende Drehwinkel

        self.model_ = QFileSystemModel(self)
        self.model_.setIconProvider(LucideIconProvider())
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
        self.setItemDelegate(TreeDelegate(self))
        self.setHeaderHidden(True)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Umbenennen nur per F2/Menü
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformRowHeights(True)
        self.setIndentation(LAYOUT.tree_indent)
        self.setIconSize(QSize(16, 16))
        self.setMouseTracking(True)
        self.setAnimated(not anim.reduced())   # Auf-/Zuklappen gleitet
        self.setFrameShape(QTreeView.Shape.NoFrame)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # Drag & Drop: Dateien/Ordner innerhalb von data/ verschieben, von außen hineinkopieren
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Hinweis, wenn data/ leer ist
        self.hint = QLabel(
            "Noch keine Dateien.\n\nLege Ordner mit Textdateien in data/ ab\n"
            "oder erstelle per Rechtsklick eine neue Datei.", self.viewport())
        self.hint.setObjectName("TreeHint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.hide()
        self.model_.directoryLoaded.connect(lambda _p: self._update_hint())
        self.model_.rowsInserted.connect(lambda *_: self._update_hint())
        self.model_.rowsRemoved.connect(lambda *_: self._update_hint())

        self.clicked.connect(self._on_clicked)
        self.expanded.connect(self._on_expanded)
        self.collapsed.connect(self._on_collapsed)

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

    def set_extensions(self, extensions: list[str]) -> None:
        self.model_.setNameFilters([f"*{ext}" for ext in extensions])

    def retheme(self) -> None:
        self.setIndentation(LAYOUT.tree_indent)
        self.model_.setIconProvider(LucideIconProvider())   # neue Icon-Farben
        self.scheduleDelayedItemsLayout()                   # Zeilenhöhe neu berechnen
        self.viewport().update()

    def select_path(self, path: Path) -> None:
        index = self.index_for(path)
        if index.isValid():
            self.setCurrentIndex(index)
            self.scrollTo(index)

    def _update_hint(self) -> None:
        empty = self.model_.rowCount(self.rootIndex()) == 0
        self.hint.setVisible(empty)
        if empty:
            self.hint.setGeometry(self.viewport().rect().adjusted(SPACING.lg, SPACING.xxl, -SPACING.lg, -SPACING.xxl))

    # ---- Auf-/Zuklappzustand ------------------------------------------------
    def _on_expanded(self, index: QModelIndex) -> None:
        self._expanded.add(self._relative(self.path_at(index)))
        self._rotate_chevron(index, 90.0)

    def _on_collapsed(self, index: QModelIndex) -> None:
        self._expanded.discard(self._relative(self.path_at(index)))
        self._rotate_chevron(index, 0.0)

    def _rotate_chevron(self, index: QModelIndex, target: float) -> None:
        key = QPersistentModelIndex(index)
        start = self._chevrons.get(key, 90.0 - target)

        def step(value: float) -> None:
            self._chevrons[key] = value
            self.viewport().update()

        def done() -> None:
            self._chevrons.pop(key, None)
            self.viewport().update()

        anim.animate(self, start, target, DURATION.chevron, step, done)

    def expanded_folders(self) -> list[str]:
        return sorted(self._expanded)

    def restore_expanded(self, relative_paths: list[str]) -> None:
        # Sortiert, damit Eltern vor Kindern aufgeklappt werden. index(path) legt
        # die Knoten bei QFileSystemModel bei Bedarf an, auch wenn noch nichts geladen war.
        for rel in sorted(relative_paths):
            path = self.root / rel
            if path.is_dir():
                self.expand(self.index_for(path))

    # ---- Zeichnen ------------------------------------------------------------
    def chevron_angle(self, index: QModelIndex) -> float:
        """0 = zu (Pfeil nach rechts), 90 = offen; während der Drehung ein Zwischenwert."""
        running = self._chevrons.get(QPersistentModelIndex(index))
        if running is not None:
            return running
        return 90.0 if self.isExpanded(index) else 0.0

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex) -> None:
        if not self.model_.hasChildren(index):
            return
        cell = QRect(rect.right() - self.indentation() + 1, rect.top(), self.indentation(), rect.height())
        pm = pixmap("chevron-right", CHEVRON_SIZE, COLORS.text_muted, self.devicePixelRatioF())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(cell.center())
        painter.rotate(self.chevron_angle(index))
        painter.drawPixmap(-CHEVRON_SIZE // 2, -CHEVRON_SIZE // 2, pm)
        painter.restore()

    def row_background(self, index: QModelIndex) -> QColor | None:
        if index in self.selectedIndexes() or index == self.currentIndex():
            return QColor(COLORS.selection)
        alpha = 0.0
        if index == self._hover_row:
            alpha = self._hover.value
        elif index == self._hover_prev:
            alpha = 1.0 - self._hover.value
        if alpha > 0:
            color = QColor(COLORS.hover)
            color.setAlphaF(alpha)
            return color
        return None

    def drawRow(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        color = self.row_background(index)
        if color is not None:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(option.rect.adjusted(0, 1, 0, -1), RADIUS.control, RADIUS.control)
            painter.restore()
        super().drawRow(painter, option, index)

    def mouseMoveEvent(self, event) -> None:
        self._set_hover(self.indexAt(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hover(QModelIndex())
        super().leaveEvent(event)

    def _set_hover(self, index: QModelIndex) -> None:
        if index != self._hover_row:
            self._hover_prev = self._hover_row
            self._hover_row = index
            self._hover.value = 0.0
            self._hover.fade_to(True)   # neue Zeile blendet ein, alte gleichzeitig aus

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_hint()

    # ---- Events -------------------------------------------------------------
    def _on_clicked(self, index: QModelIndex) -> None:
        path = self.path_at(index)
        if path is not None and path.is_file():
            self.file_activated.emit(path)
        elif path is not None and path.is_dir():
            self.setExpanded(index, not self.isExpanded(index))

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
                dialogs.warn(self, "Verschieben", f"„{source.name}“ kann nicht in sich selbst verschoben werden.")
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
                dialogs.warn(self, "Verschieben fehlgeschlagen", str(error))
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
        menu = self.build_context_menu(path)
        menu.exec(self.viewport().mapToGlobal(pos))

    def build_context_menu(self, path: Path | None) -> QMenu:
        menu = style_menu(QMenu(self))
        menu.addAction(icon("file-plus"), "Neue Datei", lambda: self.create_file(self.folder_for(path)))
        menu.addAction(icon("folder-plus"), "Neuer Ordner", lambda: self.create_folder(self.folder_for(path)))
        if path is not None:
            menu.addSeparator()
            menu.addAction(icon("pencil"), "Umbenennen\tF2", self.rename_selected)
            menu.addAction(icon("trash"), "In den Papierkorb\tEntf", self.delete_selected)
        menu.addSeparator()
        menu.addAction(icon("external-link"), "Im Explorer anzeigen", lambda: fileops.reveal_in_file_manager(path or self.root))
        return menu

    def create_file(self, folder: Path) -> None:
        name = dialogs.ask_text(self, "Neue Datei", "Dateiname:", fileops.unique_path(folder, "Neu", ".txt").name)
        if not name:
            return
        try:
            path = fileops.create_file(folder, name)
        except OSError as error:
            dialogs.warn(self, "Neue Datei", str(error))
            return
        self.expand(self.index_for(folder))
        self.select_path(path)
        self.file_activated.emit(path)

    def create_folder(self, folder: Path) -> None:
        name = dialogs.ask_text(self, "Neuer Ordner", "Ordnername:", fileops.unique_path(folder, "Neuer Ordner").name)
        if not name:
            return
        try:
            path = fileops.create_folder(folder, name)
        except OSError as error:
            dialogs.warn(self, "Neuer Ordner", str(error))
            return
        self.expand(self.index_for(folder))
        self.select_path(path)

    def rename_selected(self) -> None:
        index = self.currentIndex()
        if index.isValid():
            self.edit(index)  # Inline-Editor; das Modell benennt um und feuert fileRenamed

    def _on_model_renamed(self, folder: str, old_name: str, new_name: str) -> None:
        old, new = Path(folder) / old_name, Path(folder) / new_name
        if new.is_file() and fileops.is_encrypted_path(old) != fileops.is_encrypted_path(new):
            # Umbenennen ändert den Inhalt nicht: aus Klartext würde eine kaputte .ntx, aus einer .ntx Datenmüll
            try:
                import os
                os.replace(new, old)
            except OSError:
                pass
            dialogs.warn(self, "Umbenennen", "Die Endung .ntx lässt sich nicht per Umbenennen setzen oder entfernen.",
                         informative="Zum Verschlüsseln „Datei → Datei verschlüsseln …“ benutzen; eine verschlüsselte "
                                     "Notiz bleibt eine .ntx-Datei.")
            return
        self.path_renamed.emit(old, new)

    def delete_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        kind = "Ordner" if path.is_dir() else "Datei"
        if not dialogs.confirm(self, "In den Papierkorb", f"{kind} „{path.name}“ in den Papierkorb verschieben?",
                               yes="In den Papierkorb", danger=True):
            return
        try:
            fileops.move_to_trash(path)
        except Exception as error:  # noqa: BLE001 – send2trash wirft eigene Exception-Typen
            dialogs.warn(self, "Löschen fehlgeschlagen", str(error))
            return
        self.path_deleted.emit(path)
