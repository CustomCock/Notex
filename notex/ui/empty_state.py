"""Leerer Editorbereich: App-Name und die wichtigsten Tastenkürzel, ruhig und zentriert."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from notex.core.recent import shorten_path
from notex.theme.icons import icon

from notex import APP_NAME
from notex.theme.icons import ICON_DIR
from notex.theme.tokens import SPACING

SHORTCUTS = [
    ("Ctrl+B", "Seitenleiste ein-/ausblenden"),
    ("Ctrl+Shift+F", "In Dateien suchen"),
    ("Ctrl+N", "Neue Datei"),
    ("Ctrl+S", "Speichern"),
]


def _logo(size: int, dpr: float) -> QPixmap:
    renderer = QSvgRenderer(str(ICON_DIR.parent / "notex.svg"))
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pixmap


class EmptyState(QWidget):
    recent_chosen = Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("EmptyState")

        logo = QLabel()
        logo.setPixmap(_logo(48, self.devicePixelRatioF()))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(APP_NAME)
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Wähle links eine Datei oder lege eine neue an.")
        hint.setObjectName("EmptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        keys = QGridLayout()
        keys.setHorizontalSpacing(SPACING.md)
        keys.setVerticalSpacing(SPACING.sm)
        for row, (key, text) in enumerate(SHORTCUTS):
            key_label = QLabel(key)
            key_label.setObjectName("EmptyKey")
            key_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text_label = QLabel(text)
            text_label.setObjectName("EmptyHint")
            keys.addWidget(key_label, row, 0, Qt.AlignmentFlag.AlignRight)
            keys.addWidget(text_label, row, 1, Qt.AlignmentFlag.AlignLeft)

        column = QVBoxLayout()
        column.setSpacing(SPACING.sm)
        column.addWidget(logo)
        column.addSpacing(SPACING.xs)
        column.addWidget(title)
        column.addWidget(hint)
        column.addSpacing(SPACING.xl)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(SPACING.xs)
        self.recent_title = QLabel("Zuletzt geöffnet  ·  Ctrl+R")
        self.recent_title.setObjectName("EmptyHint")
        self.recent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recent_title.hide()
        column.addWidget(self.recent_title)
        recent_row = QHBoxLayout()
        recent_row.addStretch(1)
        recent_row.addLayout(self.recent_box)
        recent_row.addStretch(1)
        column.addLayout(recent_row)
        column.addSpacing(SPACING.lg)
        keys_row = QHBoxLayout()   # Tabelle als Ganzes zentrieren
        keys_row.addStretch(1)
        keys_row.addLayout(keys)
        keys_row.addStretch(1)
        column.addLayout(keys_row)

        self._recent_buttons: list[QToolButton] = []
        layout = QVBoxLayout(self)
        layout.addStretch(5)
        layout.addLayout(column)
        layout.addStretch(6)

    def set_recent(self, entries: list[str]) -> None:
        for button in self._recent_buttons:
            self.recent_box.removeWidget(button)
            button.deleteLater()
        self._recent_buttons = []
        for entry in entries[:5]:
            path = Path(entry)
            button = QToolButton()
            button.setObjectName("RecentButton")
            button.setIcon(icon("file-text"))
            button.setText(f"{path.name}   {shorten_path(path.parent, 44)}")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setToolTip(entry)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, p=path: self.recent_chosen.emit(p))
            self.recent_box.addWidget(button)
            self._recent_buttons.append(button)
        self.recent_title.setVisible(bool(entries))
