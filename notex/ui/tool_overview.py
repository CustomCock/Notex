"""Werkzeug-Übersicht: Suchfeld und Kacheln nach Kategorie mit Kurzbeschreibung, Shortcut und Modul-Status.
Klick startet das Werkzeug; ist das Modul aus, gibt es einen „Aktivieren"-Knopf."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from notex.core import tools
from notex.core.modules import BY_KEY
from notex.theme.icons import icon
from notex.theme.tokens import SPACING


class ToolCard(QFrame):
    def __init__(self, dialog, tool: tools.Tool, enabled: bool) -> None:
        super().__init__()
        self.setObjectName("ToolCard")
        self.tool = tool
        self.dialog = dialog
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        head = QHBoxLayout()
        badge = QLabel()
        badge.setPixmap(icon(tool.icon).pixmap(18, 18))
        name = QLabel(tool.name)
        name.setObjectName("ToolCardTitle")
        head.addWidget(badge)
        head.addWidget(name, 1)
        if tool.shortcut:
            sc = QLabel(tool.shortcut)
            sc.setObjectName("SettingsNote")
            head.addWidget(sc)
        layout.addLayout(head)
        desc = QLabel(tool.description)
        desc.setObjectName("SettingsNote")
        desc.setWordWrap(True)
        layout.addWidget(desc, 1)
        row = QHBoxLayout()
        module = BY_KEY.get(tool.module)
        status = QLabel("aktiv" if enabled else (f"Modul „{module.name}“ aus" if module else "aktiv"))
        status.setObjectName("SettingsNote")
        row.addWidget(status, 1)
        if enabled:
            start = QPushButton("Starten")
            start.clicked.connect(self._start)
            row.addWidget(start)
        elif module:
            activate = QPushButton("Aktivieren")
            activate.clicked.connect(self._activate)
            row.addWidget(activate)
        layout.addLayout(row)

    def _start(self) -> None:
        self.dialog.window_._run_tool(self.tool.command)
        self.dialog.accept()

    def _activate(self) -> None:
        self.dialog.window_.modules.set_enabled(self.tool.module, True)
        self.dialog.refresh()




class ToolOverviewDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle("Werkzeug-Übersicht")
        self.resize(820, 620)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Werkzeug suchen …")
        self.search.textChanged.connect(self.refresh)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.addWidget(self.search)
        layout.addWidget(self.scroll, 1)
        layout.addLayout(footer)
        self.refresh()

    def refresh(self) -> None:
        needle = self.search.text().lower()
        enabled = self.window_._enabled_modules()
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        any_shown = False
        for key, label in tools.CATEGORIES:
            group = [t for t in tools.TOOLS if t.category == key
                     and (not needle or needle in t.name.lower() or needle in t.description.lower())]
            if not group:
                continue
            any_shown = True
            heading = QLabel(label)
            heading.setObjectName("SettingsSection")
            outer.addWidget(heading)
            grid = QGridLayout()
            grid.setSpacing(SPACING.sm)
            for index, tool in enumerate(group):
                grid.addWidget(ToolCard(self, tool, not tool.module or tool.module in enabled), index // 2, index % 2)
            outer.addLayout(grid)
        if not any_shown:
            outer.addWidget(QLabel("Nichts gefunden."))
        outer.addStretch(1)
        self.scroll.setWidget(container)
