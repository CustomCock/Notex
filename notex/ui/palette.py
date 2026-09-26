"""Overlay oben mittig über dem Blatt: Quick Open (Ctrl+P) und Command Palette (Ctrl+Shift+P).

Ein Widget, zwei Modi. Eingabe mit ">" am Anfang wechselt in die Befehle, ":123" springt
zur Zeile, "datei:123" öffnet und springt. Esc schließt, Pfeiltasten wandern, Enter führt aus.
"""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from notex.core.actions import ActionRegistry
from notex.core.file_index import FileIndex
from notex.core.fuzzy import highlight, parse_goto
from notex.core.recent import shorten_path
from notex.theme.icons import icon
from notex.theme.theme import add_shadow
from notex.theme.tokens import COLORS, DURATION, LAYOUT, SPACING
from notex.ui import anim
from notex.ui.search_results import HtmlDelegate
from notex.ui.widgets import SearchField

ROLE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_VALUE = Qt.ItemDataRole.UserRole + 2
ROLE_LINE = Qt.ItemDataRole.UserRole + 3
WIDTH = 640
MAX_ROWS = 12


def _mark(text: str, indices: tuple[int, ...]) -> str:
    escaped = [html.escape(ch) for ch in text]
    marks = set(indices)
    return "".join(f'<span style="color:{COLORS.text}; font-weight:600">{c}</span>' if i in marks else c
                   for i, c in enumerate(escaped))


def _muted(text: str) -> str:
    return f'<span style="color:{COLORS.text_muted}">{html.escape(text)}</span>'


class PaletteOverlay(QFrame):
    open_file = Signal(Path, object)      # Pfad, Zeile oder None
    goto_line = Signal(int)
    run_command = Signal(str)

    def __init__(self, parent: QWidget, registry: ActionRegistry, index: FileIndex) -> None:
        super().__init__(parent)
        self.setObjectName("Palette")
        self.registry = registry
        self.index = index
        self.recent_files: list[str] = []
        self.mode = "files"

        self.field = SearchField("Datei suchen …  (> für Befehle, :Zeile)")
        self.field.input.installEventFilter(self)
        self.field.textChanged.connect(self._refresh)
        self.hint = QLabel()
        self.hint.setObjectName("PaletteHint")
        self.list = QListWidget()
        self.list.setObjectName("PaletteList")
        self.list.setItemDelegate(HtmlDelegate(self.list))
        self.list.setIconSize(QSize(16, 16))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self._activate_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.field)
        layout.addWidget(self.list)
        layout.addWidget(self.hint)
        self.setFixedWidth(WIDTH)
        # Schatten + Fade: beides Effekte, ein Widget kann nur einen tragen -> Schatten auf den Rahmen,
        # Deckkraft über die Fensterdeckkraft simulieren wir mit einem Opacity-Effekt auf dem Ganzen.
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self.hide()

    # ---- Öffnen / Schließen ---------------------------------------------------------
    def open(self, mode: str) -> None:
        self.mode = mode
        self.field.setText(">" if mode == "commands" else "")
        self.field.input.setPlaceholderText("Befehl suchen …" if mode == "commands" else "Datei suchen …  (> für Befehle, :Zeile)")
        self._place()
        self._refresh(self.field.text())
        self._opacity.setOpacity(0.0)
        self.show()
        self.raise_()
        anim.animate(self, 0.0, 1.0, DURATION.fade, self._opacity.setOpacity)
        self.field.setFocus()

    def close_overlay(self) -> None:
        if not self.isVisible():
            return
        anim.animate(self, self._opacity.opacity(), 0.0, DURATION.fade, self._opacity.setOpacity, self.hide)
        parent = self.parentWidget()
        if parent is not None:
            parent.setFocus()

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move((parent.width() - self.width()) // 2, SPACING.xxl + 8)

    def resize_to_parent(self) -> None:
        if self.isVisible():
            self._place()

    # ---- Inhalt ----------------------------------------------------------------------
    def _refresh(self, text: str) -> None:
        self.list.clear()
        if text.startswith(">"):
            self._fill_commands(text[1:].strip())
        else:
            self._fill_files(text)
        if self.list.count():
            self.list.setCurrentRow(0)
        rows = min(MAX_ROWS, max(1, self.list.count()))
        self.list.setFixedHeight(rows * (LAYOUT.tree_row_height - 2) + 8)
        self.adjustSize()

    def _fill_files(self, text: str) -> None:
        query, line = parse_goto(text)
        if not query and line is not None:
            item = QListWidgetItem(icon("corner-down-left"), f"Zur Zeile {line} in der aktuellen Datei")
            item.setData(ROLE_KIND, "goto")
            item.setData(ROLE_LINE, line)
            self.list.addItem(item)
            self.hint.setText("Enter springt")
            return
        for hit in self.index.search(query, self.recent_files):
            if hit.external:
                shown = _mark(hit.name, hit.match.indices) if getattr(hit, "chosen_on_name", True) else html.escape(hit.name)
                label = shown + "  " + _muted(shorten_path(Path(hit.relative).parent, 50))
            else:
                folder = hit.relative.rsplit("/", 1)[0] + "/" if "/" in hit.relative else ""
                if getattr(hit, "chosen_on_name", True):
                    label = _mark(hit.name, hit.match.indices) + "  " + _muted(folder)
                else:
                    label = _mark(hit.relative, hit.match.indices)
            item = QListWidgetItem(icon("external-link" if hit.external else "file-text"), label)
            item.setData(ROLE_KIND, "file")
            item.setData(ROLE_VALUE, hit.relative)
            item.setData(ROLE_LINE, line)
            item.setToolTip(hit.relative)
            self.list.addItem(item)
        count = self.list.count()
        self.hint.setText(f"{count} Dateien · ↑↓ wählen · Enter öffnen · Esc schließen" if count else "Keine Datei gefunden")

    def _fill_commands(self, query: str) -> None:
        for hit in self.registry.search(query):
            command = hit.command
            label = _mark(command.label, hit.match.indices)
            if command.is_checked is not None:
                label = _muted("✓ " if command.is_checked() else "○ ") + label
            if command.shortcut:
                label += "  " + _muted(command.shortcut)
            item = QListWidgetItem(label)
            item.setData(ROLE_KIND, "command")
            item.setData(ROLE_VALUE, command.id)
            self.list.addItem(item)
        count = self.list.count()
        self.hint.setText(f"{count} Befehle · zuletzt benutzte zuerst" if count else "Kein Befehl gefunden")

    # ---- Auswahl -----------------------------------------------------------------------
    def _activate_item(self, item: QListWidgetItem) -> None:
        kind = item.data(ROLE_KIND)
        self.close_overlay()
        if kind == "goto":
            self.goto_line.emit(int(item.data(ROLE_LINE)))
        elif kind == "file":
            self.open_file.emit(Path(item.data(ROLE_VALUE)), item.data(ROLE_LINE))
        elif kind == "command":
            self.run_command.emit(item.data(ROLE_VALUE))

    def eventFilter(self, watched, event) -> bool:
        if watched is self.field.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.close_overlay()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.list.currentItem() is not None:
                    self._activate_item(self.list.currentItem())
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                step = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1, Qt.Key.Key_PageDown: 8, Qt.Key.Key_PageUp: -8}[key]
                row = max(0, min(self.list.count() - 1, self.list.currentRow() + step))
                self.list.setCurrentRow(row)
                return True
        if watched is self.field.input and event.type() == QEvent.Type.FocusOut and self.isVisible():
            # Klick außerhalb schließt das Overlay
            if not self.list.hasFocus():
                self.close_overlay()
        return super().eventFilter(watched, event)
