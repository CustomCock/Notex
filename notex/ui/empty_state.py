"""Leerer Editorbereich: App-Name und die wichtigsten Tastenkürzel, ruhig und zentriert."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

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
        keys_row = QHBoxLayout()   # Tabelle als Ganzes zentrieren
        keys_row.addStretch(1)
        keys_row.addLayout(keys)
        keys_row.addStretch(1)
        column.addLayout(keys_row)

        layout = QVBoxLayout(self)
        layout.addStretch(5)
        layout.addLayout(column)
        layout.addStretch(6)
