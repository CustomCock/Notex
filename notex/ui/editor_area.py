"""Editorbereich: eine oder zwei Tab-Gruppen (EditorTabs) nebeneinander bzw. untereinander.

Das Hauptfenster spricht nur mit dem EditorArea. Alles, was „den aktuellen Tab“ betrifft, geht an
die aktive Gruppe (die, in der zuletzt ein Editor Fokus hatte oder ein Tab angeklickt wurde); alles,
was Darstellung oder Einstellungen betrifft, geht an alle Gruppen. Unbekannte Attribute werden an die
aktive Gruppe durchgereicht, damit bestehender Code (tabs.current_editor(), tabs.relative(...)) weiter
funktioniert. Geteilte Attribute (Schriftgröße, Blattmodus …) werden beim Setzen an alle Gruppen
verteilt.

Gleiche Datei in beiden Gruppen: die zweite Ansicht teilt sich QTextDocument, Undo-Stack und
Highlighter mit der ersten (Editor(share_with=…)).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSplitter, QVBoxLayout, QWidget

from notex.core import split_state
from notex.core.split_state import SplitState
from notex.ui.editor import Editor
from notex.ui.editor_tabs import EditorTabs
from notex.ui.paper import EditorPage

SHARED_ATTRS = {"font_size", "paper_mode", "resolve_link", "open_font_settings", "toolbar_visible", "line_numbers",
                "context_menu_hook", "image_hook", "tools_menu_builder"}
FORWARDED_SIGNALS = ("status_changed", "file_saved", "file_opened", "font_size_changed", "text_font_changed",
                     "files_dropped", "link_activated", "completion_requested", "preview_link", "view_mode_changed", "pdf_quote")


class EditorArea(QWidget):
    status_changed = Signal()
    file_saved = Signal(Path)
    file_opened = Signal(Path)
    file_closed = Signal(Path)
    font_size_changed = Signal(int)
    text_font_changed = Signal(str)
    files_dropped = Signal(list)
    link_activated = Signal(object, object)
    completion_requested = Signal(object, str, str)
    preview_link = Signal(object, str)
    view_mode_changed = Signal(str)
    pdf_quote = Signal(object, str)       # PDF-Viewer, Markdown-Zitat
    currentChanged = Signal(int)          # aktiver Tab oder aktive Gruppe hat gewechselt
    split_changed = Signal(bool)          # Teilung an/aus

    def __init__(self, root: Path, config: dict[str, Any]) -> None:
        super().__init__()
        self.root = root
        self.config = config
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("EditorGroups")
        self.splitter.setChildrenCollapsible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
        self.groups: list[EditorTabs] = []
        self._corner: QWidget | None = None
        self.active: EditorTabs | None = None
        self.active = self._add_group(None)
        self._refresh_keys()
        self.set_orientation(config.get("split", {}).get("orientation", "horizontal"))
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

    # ---- Attribute durchreichen ----------------------------------------------------------------
    def __getattr__(self, name: str):
        if name in ("groups", "active", "splitter", "config", "root", "_corner"):
            raise AttributeError(name)
        return getattr(self.active, name)

    def __setattr__(self, name: str, value) -> None:
        if name in SHARED_ATTRS and "groups" in self.__dict__:
            for group in self.groups:
                setattr(group, name, value)
            return
        super().__setattr__(name, value)

    # ---- Gruppen ------------------------------------------------------------------------------
    def _add_group(self, shared: EditorTabs | None) -> EditorTabs:
        group = EditorTabs(self.root, self.config, shared=shared)
        group.area = self
        group.tab_bar.group_key = len(self.groups)
        for name in FORWARDED_SIGNALS:
            getattr(group, name).connect(getattr(self, name))
        group.file_closed.connect(self._on_file_closed)
        group.currentChanged.connect(lambda _i, g=group: self._on_group_current_changed(g))
        group.tab_bar.tabBarClicked.connect(lambda _i, g=group: self.set_active(g))
        group.tabs_emptied.connect(lambda g=group: self._on_group_emptied(g))
        group.tab_drop.connect(self._on_tab_drop)
        self.groups.append(group)
        self.splitter.addWidget(group)
        self._refresh_keys()
        return group

    def _refresh_keys(self) -> None:
        for index, group in enumerate(self.groups):
            group.tab_bar.group_key = index
            group.tab_bar.setProperty("inactive", group is not self.active and len(self.groups) > 1)
            group.tab_bar.style().unpolish(group.tab_bar)
            group.tab_bar.style().polish(group.tab_bar)
        if self._corner is not None and self.groups:
            self.groups[0].setCornerWidget(self._corner, Qt.Corner.TopLeftCorner)
            self._corner.show()

    def set_corner_widget(self, widget: QWidget) -> None:
        self._corner = widget
        self._refresh_keys()

    @property
    def is_split(self) -> bool:
        return len(self.groups) > 1

    def other_group(self, group: EditorTabs | None = None) -> EditorTabs | None:
        group = group or self.active
        others = [g for g in self.groups if g is not group]
        return others[0] if others else None

    def set_active(self, group: EditorTabs) -> None:
        if group is self.active or group not in self.groups:
            return
        self.active = group
        self._refresh_keys()
        self.currentChanged.emit(group.currentIndex())
        self.status_changed.emit()

    def _on_focus_changed(self, _old, new) -> None:
        for group in self.groups:
            if new is not None and group.isAncestorOf(new):
                self.set_active(group)
                return

    def _on_group_current_changed(self, group: EditorTabs) -> None:
        if group is self.active:
            self.currentChanged.emit(group.currentIndex())

    def set_orientation(self, orientation: str) -> None:
        orientation = orientation if orientation in split_state.ORIENTATIONS else "horizontal"
        self.config.setdefault("split", {})["orientation"] = orientation
        self.splitter.setOrientation(Qt.Orientation.Horizontal if orientation == "horizontal" else Qt.Orientation.Vertical)

    def orientation(self) -> str:
        return "horizontal" if self.splitter.orientation() == Qt.Orientation.Horizontal else "vertical"

    def toggle_orientation(self) -> str:
        self.set_orientation("vertical" if self.orientation() == "horizontal" else "horizontal")
        return self.orientation()

    # ---- Teilen / Aufheben ------------------------------------------------------------------
    def split(self, share_current: bool = True) -> EditorTabs:
        """Zweite Gruppe anlegen; standardmäßig mit der aktuellen Datei als zweiter Ansicht."""
        if self.is_split:
            return self.groups[1]
        source = self.active
        group = self._add_group(shared=self.groups[0])
        for index in range(len(self.groups)):
            self.splitter.setStretchFactor(index, 1)
        QTimer.singleShot(0, self._equalize)
        editor = source.current_editor()
        if share_current and editor is not None and not editor.encrypted:
            group.open_file(editor.path, share_from=editor)
        self.set_active(group)
        self.split_changed.emit(True)
        self.status_changed.emit()
        return group

    def _equalize(self) -> None:
        """Beide Gruppen gleich groß – erst nach dem Layout, sonst gewinnt die Gruppe mit mehr Tabs."""
        if not self.is_split:
            return
        total = self.splitter.width() if self.orientation() == "horizontal" else self.splitter.height()
        self.splitter.setSizes([total // 2, total - total // 2])

    def unsplit(self) -> None:
        """Teilung aufheben: Tabs der zweiten Gruppe wandern in die erste (Duplikate schließen)."""
        if not self.is_split:
            return
        first, second = self.groups[0], self.groups[1]
        for page in list(second.pages()):
            self._move_page(second, page, first)
        self._drop_group(second)
        self.set_active(first)
        self.split_changed.emit(False)

    def toggle_split(self) -> bool:
        if self.is_split:
            self.unsplit()
        else:
            self.split()
        return self.is_split

    def _drop_group(self, group: EditorTabs) -> None:
        if group not in self.groups or len(self.groups) == 1:
            return
        self.groups.remove(group)
        if self.active is group:
            self.active = self.groups[0]
        group.setParent(None)
        group.deleteLater()
        self._refresh_keys()
        self.currentChanged.emit(self.active.currentIndex())

    def _on_group_emptied(self, group: EditorTabs) -> None:
        if self.is_split:
            self._drop_group(group)
            self.split_changed.emit(False)
        self.status_changed.emit()

    # ---- Tabs bewegen ----------------------------------------------------------------------
    def _move_page(self, source: EditorTabs, page: EditorPage, target: EditorTabs) -> None:
        """Seite samt Editor in eine andere Gruppe hängen. Zeigt die Zielgruppe die Datei schon,
        wird die Quellseite geschlossen (das Dokument bleibt in der Zielansicht erhalten)."""
        editor = page.editor
        if target.editor_for(editor.path) is not None:
            source.remove_page(page, ask=False)
            target.open_file(editor.path)
            return
        index = source.indexOf(page)
        title, tooltip, icon = source.tabText(index), source.tabToolTip(index), source.tabIcon(index)
        source.removeTab(index)
        source.unwire_page(page)
        target.wire_page(page)
        new_index = target.addTab(page, title)
        target.setTabToolTip(new_index, tooltip)
        target.setTabIcon(new_index, icon)
        target.setCurrentIndex(new_index)
        target._refresh_title(editor)
        source.status_changed.emit()
        if source.count() == 0:
            source.tabs_emptied.emit()

    def move_tab(self, source: EditorTabs, index: int, target: EditorTabs) -> None:
        page = source.widget(index)
        if source is not target and page in source.viewers() and target in self.groups:
            title, tooltip, icon_ = source.tabText(index), source.tabToolTip(index), source.tabIcon(index)
            source.removeTab(index)
            source.unwire_page(page)
            target.wire_page(page)
            new_index = target.addTab(page, icon_, title)
            target.setTabToolTip(new_index, tooltip)
            target.setCurrentIndex(new_index)
            self.set_active(target)
            if source.count() == 0:
                source.tabs_emptied.emit()
            return
        if source is target or not isinstance(page, EditorPage) or target not in self.groups:
            return
        self._move_page(source, page, target)
        self.set_active(target)
        page.editor.setFocus()

    def move_current_to_other_group(self) -> None:
        if not self.is_split:
            self.split(share_current=False)
        target = self.other_group()
        page = self.active.current_page()
        if target is not None and page is not None:
            self.move_tab(self.active, self.active.indexOf(page), target)

    def open_in_other_group(self) -> None:
        """Aktuelle Datei als zweite Ansicht in der anderen Gruppe (gleiches Dokument)."""
        editor = self.active.current_editor()
        if editor is None or editor.encrypted:   # Sperren müsste sonst zwei Ansichten gleichzeitig räumen
            return
        if not self.is_split:
            self.split(share_current=True)
            return
        target = self.other_group()
        target.open_file(editor.path, share_from=editor)
        self.set_active(target)

    def _on_tab_drop(self, group_key: int, index: int, target: EditorTabs, wants_split: bool) -> None:
        if not (0 <= group_key < len(self.groups)):
            return
        source = self.groups[group_key]
        if wants_split and not self.is_split:
            page = source.widget(index)
            if isinstance(page, EditorPage) and source.count() > 1:
                new_group = self.split(share_current=False)
                self.move_tab(source, index, new_group)
            return
        self.move_tab(source, index, target)

    # ---- Dateien über alle Gruppen ----------------------------------------------------------
    def editors(self) -> list[Editor]:
        return [e for g in self.groups for e in g.editors()]

    def pages(self) -> list[EditorPage]:
        return [p for g in self.groups for p in g.pages()]

    def viewers(self) -> list:
        return [v for g in self.groups for v in g.viewers()]

    def current_viewer(self):
        return self.active.current_viewer()

    def editor_for(self, path: Path) -> Editor | None:
        editor = self.active.editor_for(path)
        if editor is None:
            for group in self.groups:
                editor = group.editor_for(path)
                if editor is not None:
                    break
        return editor

    def group_of(self, editor: Editor) -> EditorTabs | None:
        for group in self.groups:
            if group.page_for(editor) is not None:
                return group
        return None

    def views_of(self, path: Path) -> list[Editor]:
        return [e for e in self.editors() if e.path == path]

    def external_files(self) -> list[Path]:
        seen: list[Path] = []
        for editor in self.editors():
            if self.active.is_external(editor.path) and editor.path not in seen:
                seen.append(editor.path)
        return seen

    def count(self) -> int:
        return sum(g.count() for g in self.groups)

    def open_file(self, path: Path, line: int | None = None, column: int = 0, length: int = 0) -> Editor | None:
        """In der aktiven Gruppe öffnen; ist die Datei nur in der anderen Gruppe offen, dorthin wechseln."""
        path = Path(path)
        if self.active.editor_for(path) is None and self.active.viewer_for(path) is None:
            for group in self.groups:
                if group.editor_for(path) is not None or group.viewer_for(path) is not None:
                    self.set_active(group)
                    break
        return self.active.open_file(path, line, column, length)

    def _on_file_closed(self, path: Path) -> None:
        if not self.views_of(path):
            self.file_closed.emit(path)

    def refresh_tab_icon(self, editor: Editor) -> None:
        group = self.group_of(editor)
        if group is not None:
            group.refresh_icon(editor)

    # ---- Für alle Gruppen ---------------------------------------------------------------------
    def _all(self, method: str, *args) -> None:
        for group in self.groups:
            getattr(group, method)(*args)

    def set_font_size(self, size: int) -> None:
        for group in self.groups:
            group.set_font_size(size, local=True)   # jede Gruppe klemmt gleich und meldet font_size_changed

    def zoom(self, direction: int) -> None:
        viewer = self.current_viewer() if self.current_editor() is None else None
        if viewer is not None and hasattr(viewer, "zoom_step"):
            viewer.zoom_step(direction)            # PDF: Ctrl+Plus/Minus zoomt die Seite
            return
        self.set_font_size(self.groups[0].font_size + direction)

    def set_paper_mode(self, enabled: bool) -> None:
        self._all("set_paper_mode", enabled)

    def retheme(self) -> None:
        self._all("retheme")

    def apply_spell_settings(self) -> None:
        self.groups[0].apply_spell_settings()
        for group in self.groups[1:]:
            for editor in group.editors():
                group._apply_spell_to(editor)

    def apply_text_fonts(self) -> None:
        self._all("apply_text_fonts")

    def set_line_numbers(self, visible: bool) -> None:
        self._all("set_line_numbers", visible)

    def relink_all(self) -> None:
        self._all("relink_all")

    def apply_preview_settings(self) -> None:
        self._all("apply_preview_settings")

    def toggle_toolbar(self) -> None:
        self.groups[0]._on_toolbar_toggled(not self.groups[0].toolbar_visible)   # verteilt auf alle Gruppen

    def save_all(self) -> None:
        self._all("save_all")

    def confirm_close_all(self) -> bool:
        """Vor dem Beenden: je geändertem Dokument genau einmal fragen, auch wenn es in beiden Gruppen offen ist."""
        asked: set[int] = set()
        for group in self.groups:
            for editor in group.editors():
                if not editor.is_dirty or id(editor.document()) in asked:
                    continue
                asked.add(id(editor.document()))
                self.set_active(group)
                group.setCurrentWidget(group.page_for(editor))
                if not group._ask_save(editor):
                    return False
        return True

    def close_paths_under(self, path: Path) -> None:
        self._all("close_paths_under", path)

    def rename_open_file(self, old: Path, new: Path) -> None:
        self._all("rename_open_file", old, new)

    def shutdown(self) -> None:
        self.groups[0].shutdown()
        for group in self.groups[1:]:
            for page in group.pages():
                if page.preview is not None:
                    page.preview.shutdown()

    # ---- Zustand --------------------------------------------------------------------------------
    def state(self) -> SplitState:
        return SplitState(
            groups=[g.open_paths() for g in self.groups],
            active_tabs=[max(0, g.currentIndex()) for g in self.groups],
            active_group=self.groups.index(self.active),
            orientation=self.orientation(),
        )

    def restore_state(self, state: SplitState) -> None:
        self.set_orientation(state.orientation)
        for entry in state.groups[0]:
            path = self.groups[0].resolve_saved(entry)
            if path.is_file():
                self.groups[0].open_file(path)
        if state.is_split and state.groups[1]:
            second = self.split(share_current=False)
            for entry in state.groups[1]:
                path = second.resolve_saved(entry)
                if not path.is_file() or (path.suffix.lower() == ".ntx" and self.groups[0].editor_for(path)):
                    continue
                shared = self.groups[0].editor_for(path)
                second.open_file(path, share_from=shared)
            if second.count() == 0:
                self.unsplit()
        for group, index in zip(self.groups, state.active_tabs):
            if 0 <= index < group.count():
                group.setCurrentIndex(index)
        if state.active_group < len(self.groups):
            self.set_active(self.groups[state.active_group])
        self.status_changed.emit()
