"""Bearbeitungsleiste über dem Blatt: gleiche Breite wie das Blatt, oben abgerundet, ein-/ausklappbar.

Aufbau:
  EditorToolbar (QFrame, dunkel)
    ├─ strip   – die Buttons in Gruppen; wird beim Einklappen auf Höhe 0 animiert
    └─ handle  – schmale Zeile mit Chevron, bleibt immer sichtbar

Die Aktionen (QAction) kommen aus dem Hauptfenster, damit Tastenkürzel auch ohne
Leiste funktionieren. Passen nicht alle Gruppen nebeneinander, wandern die hinteren
in ein „…“-Menü – die Leiste bricht nie um.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QMenu, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from notex.theme.fonts import STANDARD, STANDARD_LABEL, available_families
from notex.theme.icons import icon
from notex.theme.theme import style_menu
from notex.theme.tokens import DURATION, SPACING
from notex.ui import anim
from notex.ui.widgets import FadeButton

HANDLE_HEIGHT = 14
GROUP_GAP = 10           # Abstand zwischen Gruppen – statt harter Trennlinien

# Gruppen: (Name, [Aktions-Schlüssel oder "widget:<name>"]); "md:" markiert die Markdown-Gruppe
GROUPS: list[tuple[str, list[str]]] = [
    ("Verlauf", ["undo", "redo"]),
    ("Suchen", ["find", "replace"]),
    ("Textschrift", ["widget:font", "font_smaller", "widget:size", "font_larger"]),
    ("Ansicht", ["zoom_reset", "paper_mode", "line_numbers"]),
    ("Zeilen", ["dup_line", "move_up", "move_down", "sort_lines", "unique_lines", "strip_ws"]),
    ("Text", ["upper", "lower", "title", "datetime"]),
    ("Markdown", ["md_bold", "md_italic", "md_heading", "md_list", "md_checkbox", "md_code", "md_link"]),
    ("Prüfung", ["spell", "grammar"]),
    ("Datei", ["widget:encoding", "widget:eol"]),
]


class ToolButton(FadeButton):
    def __init__(self, action: QAction) -> None:
        super().__init__()
        self.setObjectName("IconButton")
        self.setDefaultAction(action)
        self.setIconSize(QSize(16, 16))
        self.setFixedSize(26, 26)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class MenuButton(QToolButton):
    """Text-Button mit Menü (Encoding, Zeilenende)."""

    def __init__(self, tooltip: str) -> None:
        super().__init__()
        self.setObjectName("ToolbarMenuButton")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip(tooltip)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_ = style_menu(QMenu(self))
        self.setMenu(self.menu_)


class EditorToolbar(QFrame):
    visibility_changed = Signal(bool)

    def __init__(self, actions: dict[str, QAction], tabs, is_markdown: bool) -> None:
        super().__init__()
        self.setObjectName("EditorToolbar")
        self.actions_ = actions
        self.tabs = tabs
        self.is_markdown = is_markdown
        self.expanded = True
        self._anim = None
        self._groups: list[tuple[str, QWidget, list[QAction]]] = []
        self._syncing = False

        self.strip = QWidget()
        self.strip.setObjectName("ToolbarStrip")
        self.strip_layout = QHBoxLayout(self.strip)
        self.strip_layout.setContentsMargins(SPACING.sm, SPACING.xs, SPACING.sm, SPACING.xs)
        self.strip_layout.setSpacing(GROUP_GAP)
        self._build_groups()
        self.overflow = QToolButton()
        self.overflow.setObjectName("IconButton")
        self.overflow.setIcon(icon("ellipsis"))
        self.overflow.setToolTip("Weitere Werkzeuge")
        self.overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.overflow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.overflow_menu = style_menu(QMenu(self.overflow))
        self.overflow.setMenu(self.overflow_menu)
        self.overflow.hide()
        self.strip_layout.addStretch(1)
        self.strip_layout.addWidget(self.overflow)

        self.handle = QToolButton()
        self.handle.setObjectName("ToolbarHandle")
        self.handle.setFixedHeight(HANDLE_HEIGHT)
        self.handle.setIconSize(QSize(12, 12))
        self.handle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.handle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.handle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.handle.clicked.connect(self.toggle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.strip)
        layout.addWidget(self.handle)
        self._update_handle()

    # ---- Aufbau -------------------------------------------------------------------
    def _build_groups(self) -> None:
        for name, keys in GROUPS:
            if name == "Markdown" and not self.is_markdown:
                continue
            group = QWidget()
            group.setObjectName("ToolbarGroup")
            row = QHBoxLayout(group)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            group_actions: list[QAction] = []
            for key in keys:
                if key.startswith("widget:"):
                    widget = self._make_widget(key[7:])
                    if widget is not None:
                        row.addWidget(widget)
                    continue
                action = self.actions_.get(key)
                if action is None:
                    continue
                row.addWidget(ToolButton(action))
                group_actions.append(action)
            self.strip_layout.addWidget(group)
            self._groups.append((name, group, group_actions))

    def _make_widget(self, name: str) -> QWidget | None:
        if name == "font":
            self.font_box = QComboBox()
            self.font_box.setObjectName("ToolbarCombo")
            self.font_box.setToolTip("Textschrift – Ansichts-Einstellung für alle Dateien, ändert nichts an der Datei")
            self.font_box.addItem(STANDARD_LABEL, STANDARD)
            for family in available_families():
                self.font_box.addItem(family, family)
            self.font_box.setMaximumWidth(150)
            self.font_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.font_box.currentIndexChanged.connect(self._font_chosen)
            return self.font_box
        if name == "size":
            self.size_edit = QLineEdit()
            self.size_edit.setObjectName("ToolbarSize")
            self.size_edit.setFixedWidth(40)
            self.size_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.size_edit.setToolTip("Textgröße in px – Ansichts-Einstellung, ändert nichts an der Datei  (Ctrl+Mausrad)")
            self.size_edit.editingFinished.connect(self._size_entered)
            return self.size_edit
        if name == "encoding":
            self.encoding_button = MenuButton("Encoding der Datei beim Speichern")
            for label, value in (("UTF-8", "utf-8"), ("UTF-8 mit BOM", "utf-8-sig"), ("cp1252 (Windows)", "cp1252")):
                self.encoding_button.menu_.addAction(label, lambda v=value: self.tabs.set_encoding(v))
            return self.encoding_button
        if name == "eol":
            self.eol_button = MenuButton("Zeilenende der Datei beim Speichern")
            for label, value in (("LF (Unix)", "\n"), ("CRLF (Windows)", "\r\n")):
                self.eol_button.menu_.addAction(label, lambda v=value: self.tabs.set_eol(v))
            return self.eol_button
        return None

    # ---- Zustand aus dem Editor -------------------------------------------------------
    def sync(self, editor) -> None:
        """Dropdowns und Anzeigen an den aktuellen Editor anpassen."""
        self._syncing = True
        index = self.font_box.findData(editor.font_family or STANDARD)
        self.font_box.setCurrentIndex(index if index >= 0 else 0)
        self.size_edit.setText(str(editor.font_size))
        labels = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8 BOM", "cp1252": "cp1252"}
        self.encoding_button.setText(labels.get(editor.encoding, editor.encoding))
        self.eol_button.setText("CRLF" if editor.eol == "\r\n" else "LF")
        self._syncing = False

    def _font_chosen(self, index: int) -> None:
        if not self._syncing:
            self.tabs.set_text_font(self.font_box.itemData(index) or STANDARD)

    def _size_entered(self) -> None:
        try:
            self.tabs.set_font_size(int(self.size_edit.text().strip()))
        except ValueError:
            pass
        editor = self.tabs.current_editor()
        if editor is not None:
            self.size_edit.setText(str(editor.font_size))

    # ---- Ein-/Ausklappen ------------------------------------------------------------
    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        if expanded == self.expanded and self._anim is None:
            return
        self.expanded = expanded
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        target = self.strip.sizeHint().height() if expanded else 0
        start = self.strip.maximumHeight() if self.strip.maximumHeight() < 10000 else self.strip.height()
        self._update_handle()
        if not animate or anim.duration(DURATION.sidebar) == 0:
            self.strip.setMaximumHeight(16777215 if expanded else 0)
            self.strip.setVisible(expanded)
            self.visibility_changed.emit(expanded)
            return
        self.strip.setVisible(True)
        self.strip.setMaximumHeight(start)

        def step(value: float) -> None:
            self.strip.setMaximumHeight(int(value))

        def done() -> None:
            self._anim = None
            self.strip.setMaximumHeight(16777215 if expanded else 0)
            self.strip.setVisible(expanded)
            self.visibility_changed.emit(expanded)

        self._anim = anim.animate(self, start, target, 180, step, done)

    def toggle(self) -> None:
        self.set_expanded(not self.expanded)

    def _update_handle(self) -> None:
        self.handle.setIcon(icon("chevron-up" if self.expanded else "chevron-down"))
        self.handle.setToolTip(("Leiste einklappen" if self.expanded else "Bearbeitungsleiste ausklappen") + "  Ctrl+Shift+E")

    def retheme(self) -> None:
        self._update_handle()
        self.overflow.setIcon(icon("ellipsis"))

    # ---- Überlauf -------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        """Gruppen von hinten ausblenden, bis alles passt; ausgeblendete Aktionen ins „…“-Menü."""
        margins = self.strip_layout.contentsMargins()
        available = self.width() - margins.left() - margins.right() - self.overflow.sizeHint().width() - GROUP_GAP
        used = 0
        hidden: list[tuple[str, list[QAction]]] = []
        for name, group, group_actions in self._groups:
            width = group.sizeHint().width() + GROUP_GAP
            if used + width <= available and not hidden:
                group.setVisible(True)
                used += width
            else:
                group.setVisible(False)
                hidden.append((name, group_actions))
        self.overflow_menu.clear()
        for name, group_actions in hidden:
            if name == "Textschrift":
                self.overflow_menu.addAction(icon("type"), "Textschrift …", lambda: self.tabs.open_font_settings())
                continue
            if name == "Datei":
                editor = self.tabs.current_editor()
                if editor is not None:
                    encoding = self.overflow_menu.addMenu(icon("file-type"), "Encoding / Zeilenende")
                    for action in self.encoding_button.menu_.actions() + [None] + self.eol_button.menu_.actions():
                        if action is None:
                            encoding.addSeparator()
                        else:
                            encoding.addAction(action)
                continue
            section = self.overflow_menu.addSection(name)
            section.setEnabled(False)
            for action in group_actions:
                self.overflow_menu.addAction(action)
        self.overflow.setVisible(bool(hidden))
