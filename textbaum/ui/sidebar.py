"""Seitenleiste: Suchfeld, Checkboxen und darunter der Baum (bzw. später die Trefferliste)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QStackedWidget, QVBoxLayout, QWidget

from textbaum.ui.file_tree import FileTree


class Sidebar(QWidget):
    def __init__(self, root: Path, extensions: list[str]) -> None:
        super().__init__()
        self.setObjectName("Sidebar")

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Suchen …  (Ctrl+Shift+F)")
        self.search_field.setClearButtonEnabled(True)

        self.by_name = QCheckBox("Dateiname")
        self.full_text = QCheckBox("Volltext")
        checks = QHBoxLayout()
        checks.setContentsMargins(2, 0, 0, 0)
        checks.addWidget(self.by_name)
        checks.addWidget(self.full_text)
        checks.addStretch()

        self.tree = FileTree(root, extensions)
        # Der Stack zeigt entweder den Baum oder (Phase 4) die Suchergebnisse
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tree)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 4, 0)
        layout.setSpacing(6)
        layout.addWidget(self.search_field)
        layout.addLayout(checks)
        layout.addWidget(self.stack, 1)
