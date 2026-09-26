"""Über-Dialog: Name, Version, Lizenzen der gebündelten Bestandteile."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from notex import APP_NAME, __version__
from notex.theme.tokens import SPACING
from notex.ui.empty_state import _logo

CREDITS = [
    ("Python + PySide6 (Qt)", "LGPL v3"),
    ("Inter", "SIL Open Font License"),
    ("JetBrains Mono", "SIL Open Font License"),
    ("Lucide Icons", "ISC"),
    ("Hunspell-Wörterbücher de_DE / en_US (LibreOffice)", "GPL v2/v3 · MIT/SCOWL"),
    ("pyenchant / spylls", "LGPL · MPL 2.0"),
    ("LanguageTool (optional, extern)", "LGPL"),
]


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Über {APP_NAME}")
        self.setObjectName("AboutDialog")
        logo = QLabel()
        logo.setPixmap(_logo(56, self.devicePixelRatioF()))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(APP_NAME)
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version = QLabel(f"Version {__version__} · portabel · Windows")
        version.setObjectName("EmptyHint")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        blurb = QLabel("Explorer + Editor für Textdateien. Alles liegt in einem Ordner:\n"
                       "Notex.exe, data/, config.json, themes/, fonts/user/.")
        blurb.setObjectName("EmptyHint")
        blurb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credits = QLabel("\n".join(f"{name} – {license_}" for name, license_ in CREDITS))
        credits.setObjectName("SettingsNote")
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close = QPushButton("Schließen")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxl, SPACING.xl, SPACING.xxl, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(SPACING.sm)
        layout.addWidget(blurb)
        layout.addSpacing(SPACING.md)
        layout.addWidget(credits)
        layout.addSpacing(SPACING.md)
        layout.addLayout(buttons)
