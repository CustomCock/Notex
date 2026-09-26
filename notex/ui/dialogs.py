"""Dialoge im Theme: Nachfragen und Texteingaben mit Lucide-Icon statt Windows-Standardgrafik."""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from notex.theme.icons import pixmap
from notex.theme.tokens import COLORS


def _box(parent: QWidget | None, title: str, text: str, informative: str, icon_name: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    if informative:
        box.setInformativeText(informative)
    dpr = parent.devicePixelRatioF() if parent is not None else 1.0
    box.setIconPixmap(pixmap(icon_name, 28, COLORS.text_muted, dpr))
    return box


def confirm(parent: QWidget | None, title: str, text: str, yes: str = "Ja", no: str = "Abbrechen",
            informative: str = "", danger: bool = False, default_yes: bool = True) -> bool:
    """Ja/Nein-Frage. `danger` färbt den Ja-Button (Löschen, Verwerfen) und macht Nein zum Default."""
    box = _box(parent, title, text, informative, "triangle-alert" if danger else "circle")
    yes_button = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    no_button = box.addButton(no, QMessageBox.ButtonRole.RejectRole)
    if danger:
        yes_button.setObjectName("Danger")
    box.setDefaultButton(no_button if danger else (yes_button if default_yes else no_button))
    box.exec()
    return box.clickedButton() is yes_button


def warn(parent: QWidget | None, title: str, text: str, informative: str = "") -> None:
    box = _box(parent, title, text, informative, "triangle-alert")
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def ask_text(parent: QWidget | None, title: str, label: str, default: str = "") -> str | None:
    """Einzeiliges Eingabefeld; None bei Abbruch oder leerer Eingabe."""
    text, ok = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, default)
    text = text.strip()
    return text if ok and text else None
