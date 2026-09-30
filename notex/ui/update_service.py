"""Update-Check im Hintergrund und der Hinweis-Dialog. Lädt nie etwas herunter."""
from __future__ import annotations

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from notex import APP_NAME, EXE_FILE, __version__
from notex.core import update_check
from notex.theme.tokens import SPACING


class UpdateWorker(QThread):
    done = Signal(object, str)   # Liste der Releases (oder None), Fehlertext

    def run(self) -> None:
        try:
            self.done.emit(update_check.fetch_releases(__version__), "")
        except Exception as error:  # noqa: BLE001 – offline, Proxy, Rate-Limit: alles nur ein Hinweistext
            self.done.emit(None, str(error) or type(error).__name__)


class UpdateDialog(QDialog):
    skip_requested = Signal(str)

    def __init__(self, parent: QWidget, release: update_check.Release) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update verfügbar")
        self.setMinimumWidth(460)
        title = QLabel(f"{APP_NAME} {release.version_text} ist verfügbar (installiert: {__version__}).")
        title.setWordWrap(True)
        hint = QLabel(f"{APP_NAME} lädt nichts selbst herunter. Auf der Release-Seite liegt die ZIP; beim Update nur "
                      f"{EXE_FILE} und _internal/ ersetzen, data/ und config.json bleiben.")
        hint.setObjectName("SettingsNote")
        hint.setWordWrap(True)
        notes = QPlainTextEdit(release.notes or "Keine Versionshinweise.")
        notes.setReadOnly(True)
        notes.setMaximumHeight(220)
        open_page = QPushButton("Release-Seite öffnen")
        open_page.setObjectName("Primary")
        skip = QPushButton("Diese Version überspringen")
        close = QPushButton("Später")
        buttons = QHBoxLayout()
        buttons.addWidget(skip)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(open_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(title)
        layout.addWidget(notes)
        layout.addWidget(hint)
        layout.addLayout(buttons)
        open_page.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl(release.url)), self.accept()))
        skip.clicked.connect(lambda: (self.skip_requested.emit(release.version_text), self.accept()))
        close.clicked.connect(self.reject)
