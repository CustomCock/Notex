"""RDAP-Karte: Abfrage im Hintergrund (nie im UI-Thread), Ergebnis als Feldliste, „Als Markdown einfügen“ und
„Kopieren“. Fehler erscheinen dezent in der Karte, nicht als Meldungsfenster."""
from __future__ import annotations

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from notex.core import rdap
from notex.theme.tokens import COLORS, SPACING


class RdapWorker(QThread):
    done = Signal(object, str)

    def __init__(self, client: rdap.Client, query: str) -> None:
        super().__init__()
        self.client, self.query = client, query

    def run(self) -> None:
        try:
            self.done.emit(self.client.lookup(self.query), "")
        except rdap.RdapError as error:
            self.done.emit(None, str(error))
        except Exception as error:   # noqa: BLE001 – unerwartete Antworten dürfen die App nicht stören
            self.done.emit(None, f"Unerwartete Antwort: {type(error).__name__}: {error}")


class RdapDialog(QDialog):
    def __init__(self, window, client: rdap.Client, query: str, editor=None) -> None:
        super().__init__(window)
        self.window_ = window
        self.client = client
        self.editor = editor
        self.card: rdap.Card | None = None
        self.setWindowTitle("RDAP / ASN")
        self.resize(620, 420)
        self.query = QLineEdit(query)
        self.query.setPlaceholderText("IP, Domain oder AS-Nummer (AS13335)")
        self.query.returnPressed.connect(self.run)
        ask = QPushButton("Abfragen")
        ask.clicked.connect(self.run)
        top = QHBoxLayout()
        top.addWidget(self.query, 1)
        top.addWidget(ask)
        self.title = QLabel()
        self.title.setObjectName("SettingsSection")
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setHorizontalSpacing(SPACING.lg)
        self.status = QLabel()
        self.status.setObjectName("SettingsNote")
        self.status.setWordWrap(True)
        self.insert_button = QPushButton("Als Markdown einfügen")
        self.insert_button.clicked.connect(self.insert)
        self.copy_button = QPushButton("Kopieren")
        self.copy_button.clicked.connect(self.copy)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        for button in (self.insert_button, self.copy_button, close):
            footer.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addLayout(top)
        layout.addWidget(self.title)
        layout.addWidget(self.form_host, 1)
        layout.addWidget(self.status)
        layout.addLayout(footer)
        self.worker: RdapWorker | None = None
        self._set_card(None)
        if query:
            self.run()

    def run(self) -> None:
        text = self.query.text().strip()
        if not text or (self.worker is not None and self.worker.isRunning()):
            return
        try:
            kind, value = rdap.classify(text)
            if kind == "ip" and rdap.local_reason(value):
                self._set_card(None)
                self.status.setText(f"{value} ist {rdap.local_reason(value)} – solche Adressen fragt Notex nie ab.")
                return
        except rdap.RdapError as error:
            self._set_card(None)
            self.status.setText(str(error))
            return
        self.status.setStyleSheet("")
        self.status.setText(f"Frage {text} ab … (IANA-Bootstrap → zuständige Registry" +
                            (", RIPEstat für die ASN)" if kind == "ip" else ")"))
        self.worker = RdapWorker(self.client, text)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _done(self, card, error: str) -> None:
        if self.worker is not None:
            self.worker.wait()
        if card is None:
            self._set_card(None)
            self.status.setText(error)
            self.status.setStyleSheet(f"color: {COLORS.danger};")
            return
        self._set_card(card)
        notes = " · ".join(card.notes[:2])
        self.status.setText(f"Quelle: {card.source}" + (f"\n{notes}" if notes else ""))

    def _set_card(self, card) -> None:
        self.card = card
        while self.form.rowCount():
            self.form.removeRow(0)
        self.title.setText(f"{card.query} – {card.title}" if card and card.title and card.title != card.query
                           else (card.query if card else ""))
        for label, value in (card.fields if card else []):
            field = QLabel(value)
            field.setWordWrap(True)
            field.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.form.addRow(label, field)
        self.insert_button.setEnabled(card is not None)
        self.copy_button.setEnabled(card is not None)

    def copy(self) -> None:
        if self.card:
            QGuiApplication.clipboard().setText(rdap.to_markdown(self.card))
            self.status.setText("Als Markdown kopiert")

    def insert(self) -> None:
        editor = self.editor or self.window_.tabs.current_editor()
        if self.card is None or editor is None or editor.isReadOnly() or getattr(editor, "locked", False):
            self.status.setText("Erst eine beschreibbare Notiz öffnen")
            return
        text = rdap.to_markdown(self.card)
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.EndOfBlock)
        editor._grouped(lambda: cursor.insertText("\n\n" + text))
        self.status.setText(f"In „{editor.path.name}“ eingefügt")

    def closeEvent(self, event) -> None:
        worker = self.worker
        if worker is not None and worker.isRunning():
            # nicht warten (kein UI-Freeze): der Thread läuft am Fenster weiter und räumt sich selbst weg
            worker.done.disconnect(self._done)
            worker.setParent(self.window_)
            worker.finished.connect(worker.deleteLater)
            self.worker = None
        super().closeEvent(event)
