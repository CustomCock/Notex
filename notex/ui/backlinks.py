"""Backlinks-Panel: wer verlinkt auf die aktuelle Datei, plus unverlinkte Erwähnungen mit „verlinken“."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QToolButton, QVBoxLayout,
                               QWidget)

from notex.core.wikilinks import Backlink
from notex.theme.icons import icon
from notex.theme.tokens import COLORS, SPACING
from notex.ui.search_results import HtmlDelegate

ROLE_SOURCE = Qt.ItemDataRole.UserRole + 1
ROLE_LINE = Qt.ItemDataRole.UserRole + 2
ROLE_SPAN = Qt.ItemDataRole.UserRole + 3


def _muted(text: str) -> str:
    return f'<span style="color:{COLORS.text_muted}">{html.escape(text)}</span>'


class BacklinksPanel(QWidget):
    open_requested = Signal(Path, int)                  # Datei, Zeile
    link_requested = Signal(Path, int, int, int)        # Datei, Zeile, Start, Ende  (Erwähnung verlinken)
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Backlinks")
        self.title = QLabel("Backlinks")
        self.title.setObjectName("SectionTitle")
        self.close_button = QToolButton()
        self.close_button.setObjectName("IconButton")
        self.close_button.setIcon(icon("x"))
        self.close_button.setToolTip("Backlinks ausblenden  Ctrl+Shift+K")
        self.close_button.clicked.connect(self.closed)
        header = QHBoxLayout()
        header.setContentsMargins(SPACING.md, SPACING.xs, SPACING.xs, 0)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.close_button)

        self.list = QListWidget()
        self.list.setObjectName("BacklinksList")
        self.list.setItemDelegate(HtmlDelegate(self.list))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self._activate)

        self.mentions_title = QLabel("Unverlinkte Erwähnungen")
        self.mentions_title.setObjectName("SectionTitle")
        self.mentions = QListWidget()
        self.mentions.setObjectName("BacklinksList")
        self.mentions.setItemDelegate(HtmlDelegate(self.mentions))
        self.mentions.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.mentions.itemClicked.connect(self._activate)
        self.link_button = QPushButton("Auswahl verlinken")
        self.link_button.clicked.connect(self._link_selected)
        self.link_all_button = QPushButton("Alle verlinken")
        self.link_all_button.clicked.connect(self._link_all)
        mention_buttons = QHBoxLayout()
        mention_buttons.setContentsMargins(SPACING.md, 0, SPACING.md, SPACING.sm)
        mention_buttons.addWidget(self.link_button)
        mention_buttons.addWidget(self.link_all_button)
        mention_buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)
        layout.addLayout(header)
        layout.addWidget(self.list, 2)
        layout.addWidget(self.mentions_title)
        layout.addWidget(self.mentions, 1)
        layout.addLayout(mention_buttons)
        self.mentions_title.setContentsMargins(SPACING.md, 0, 0, 0)
        self.set_data([], [], "")

    def set_data(self, backlinks: list[Backlink], mentions: list[tuple[str, int, int, int, str]], name: str) -> None:
        self.list.clear()
        self.title.setText(f"Backlinks ({len(backlinks)})" if name else "Backlinks")
        for backlink in backlinks:
            item = QListWidgetItem(icon("file-text"), f"{html.escape(backlink.source)}  {_muted(f'{backlink.line}: {backlink.snippet}')}")
            item.setData(ROLE_SOURCE, backlink.source)
            item.setData(ROLE_LINE, backlink.line)
            item.setToolTip(f"{backlink.source} – Zeile {backlink.line}")
            self.list.addItem(item)
        if not backlinks:
            placeholder = QListWidgetItem(_muted("Keine Datei verlinkt hierher." if name else "Keine Datei geöffnet."))
            placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.list.addItem(placeholder)
        self.mentions.clear()
        self.mentions_title.setText(f"Unverlinkte Erwähnungen ({len(mentions)})")
        for source, line, start, end, snippet in mentions:
            item = QListWidgetItem(icon("link"), f"{html.escape(source)}  {_muted(f'{line}: {snippet}')}")
            item.setData(ROLE_SOURCE, source)
            item.setData(ROLE_LINE, line)
            item.setData(ROLE_SPAN, (start, end))
            self.mentions.addItem(item)
        has_mentions = bool(mentions)
        for widget in (self.mentions_title, self.mentions, self.link_button, self.link_all_button):
            widget.setVisible(has_mentions)

    def _activate(self, item: QListWidgetItem) -> None:
        source = item.data(ROLE_SOURCE)
        if source:
            self.open_requested.emit(Path(source), int(item.data(ROLE_LINE)))

    def _link_selected(self) -> None:
        item = self.mentions.currentItem()
        if item is not None:
            start, end = item.data(ROLE_SPAN)
            self.link_requested.emit(Path(item.data(ROLE_SOURCE)), int(item.data(ROLE_LINE)), start, end)

    def _link_all(self) -> None:
        # Von hinten nach vorn, damit sich Positionen innerhalb einer Zeile nicht verschieben
        items = [self.mentions.item(i) for i in range(self.mentions.count())]
        for item in sorted(items, key=lambda it: (it.data(ROLE_SOURCE), -int(it.data(ROLE_LINE)), -it.data(ROLE_SPAN)[0])):
            start, end = item.data(ROLE_SPAN)
            self.link_requested.emit(Path(item.data(ROLE_SOURCE)), int(item.data(ROLE_LINE)), start, end)

    def retheme(self) -> None:
        self.close_button.setIcon(icon("x"))
