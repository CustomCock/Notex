"""„Port nachschlagen“: Suche nach Nummer, Kurzname (rdp, smb) oder IANA-Name; Details mit Hinweis und allen
IANA-Einträgen, „Als Markdown einfügen“. Rein offline."""
from __future__ import annotations

from html import escape

from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QTextBrowser, QVBoxLayout)

from notex.core import ports
from notex.theme.tokens import SPACING


class PortDialog(QDialog):
    def __init__(self, window, term: str = "") -> None:
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle("Port nachschlagen")
        self.resize(760, 480)
        self.query = QLineEdit(term)
        self.query.setPlaceholderText("3389, rdp, microsoft-ds, kerberos …")
        self.results = QListWidget()
        self.results.setFixedWidth(260)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        source = QLabel(f"Quelle: IANA Service Name and Transport Protocol Port Number Registry (Stand "
                        f"{ports.data_version() or '?'}) + eigene Hinweise · offline")
        source.setObjectName("SettingsNote")
        insert = QPushButton("Als Markdown einfügen")
        insert.clicked.connect(self.insert)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        body = QHBoxLayout()
        body.addWidget(self.results)
        body.addWidget(self.details, 1)
        footer = QHBoxLayout()
        footer.addWidget(source, 1)
        footer.addWidget(insert)
        footer.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.addWidget(self.query)
        layout.addLayout(body, 1)
        layout.addLayout(footer)
        self.query.textChanged.connect(self.search)
        self.results.currentRowChanged.connect(self.show_info)
        self.infos: list[ports.PortInfo] = []
        self.search()

    def search(self) -> None:
        self.infos = ports.search(self.query.text())
        self.results.clear()
        for info in self.infos:
            self.results.addItem(QListWidgetItem(info.summary()))
        if self.infos:
            self.results.setCurrentRow(0)
        else:
            self.details.setHtml("<p>Nichts gefunden.</p>" if self.query.text().strip() else "")

    def show_info(self, row: int) -> None:
        if 0 <= row < len(self.infos):
            info = self.infos[row]
            rows = "".join(f"<tr><td>{escape(n or '–')}</td><td>{escape(p)}</td><td>{escape(d)}</td></tr>"
                           for n, p, d in info.iana)
            table = f"<p><b>IANA</b></p><table cellspacing=6>{rows}</table>" if rows else ""
            self.details.setHtml(ports.tooltip_html(ports.PortInfo(info.port, info.name, info.protocols, info.note))
                                 + table)

    def insert(self) -> None:
        row = self.results.currentRow()
        editor = self.window_.tabs.current_editor()
        if not 0 <= row < len(self.infos) or editor is None or editor.isReadOnly() or getattr(editor, "locked", False):
            return
        text = ports.to_markdown(self.infos[row])
        cursor = editor.textCursor()
        editor._grouped(lambda: cursor.insertText(("\n" if cursor.positionInBlock() else "") + text))
