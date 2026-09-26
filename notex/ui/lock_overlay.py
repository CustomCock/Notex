"""Sperrbildschirm über einem Tab mit verschlüsselter Notiz (.ntx) und der Passwort-Dialog.

LockOverlay liegt als Kind über der ganzen EditorPage, solange die Notiz gesperrt ist. Der Editor darunter
ist dann leer und schreibgeschützt – der Klartext existiert nur, solange entsperrt ist, und nie auf der Platte.

Modi:
  "unlock"  Passwort eingeben (vorhandene Datei)
  "set"     Passwort festlegen + wiederholen (leere/neue .ntx-Datei)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from notex.theme.icons import pixmap
from notex.theme.tokens import COLORS, SPACING

MIN_RECOMMENDED = 10


def strength_hint(password: str) -> str:
    """Grobe Einschätzung – kein Ersatz für eine echte Bewertung, nur ein Stups."""
    if not password:
        return ""
    classes = sum(any(check(c) for c in password) for check in (str.islower, str.isupper, str.isdigit,
                                                               lambda c: not c.isalnum()))
    if len(password) < 8:
        return "Sehr kurz – leicht zu erraten."
    if len(password) < MIN_RECOMMENDED or classes < 2:
        return "Eher schwach. Länger ist besser als kompliziert, z. B. vier zufällige Wörter."
    return "Ordentlich." if len(password) < 16 else "Stark."


class PasswordFields(QWidget):
    """Ein oder zwei Passwortfelder mit Anzeigen-Schalter und Stärke-Hinweis."""
    submitted = Signal()

    def __init__(self, confirm: bool) -> None:
        super().__init__()
        self.confirm = confirm
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Passwort")
        self.repeat = QLineEdit()
        self.repeat.setEchoMode(QLineEdit.EchoMode.Password)
        self.repeat.setPlaceholderText("Passwort wiederholen")
        self.show_box = QCheckBox("Anzeigen")
        self.hint = QLabel()
        self.hint.setObjectName("SettingsNote")
        self.hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.password)
        layout.addWidget(self.repeat)
        row = QHBoxLayout()
        row.addWidget(self.show_box)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.hint)
        self.repeat.setVisible(confirm)
        self.hint.setVisible(confirm)
        self.show_box.toggled.connect(self._toggle_echo)
        self.password.textChanged.connect(self._update_hint)
        self.password.returnPressed.connect(self._on_return)
        self.repeat.returnPressed.connect(self.submitted)

    def _toggle_echo(self, show: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self.password.setEchoMode(mode)
        self.repeat.setEchoMode(mode)

    def _update_hint(self, text: str) -> None:
        if self.confirm:
            self.hint.setText(strength_hint(text))

    def _on_return(self) -> None:
        if self.confirm and not self.repeat.text():
            self.repeat.setFocus()
        else:
            self.submitted.emit()

    def validate(self) -> str | None:
        """Fehlertext oder None."""
        if not self.password.text():
            return "Bitte ein Passwort eingeben."
        if self.confirm and self.password.text() != self.repeat.text():
            return "Die Passwörter stimmen nicht überein."
        return None

    def clear(self) -> None:
        """Passwort aus den Feldern entfernen (so kurz wie möglich im Speicher halten)."""
        self.password.clear()
        self.repeat.clear()


class LockOverlay(QFrame):
    submitted = Signal(str)     # Passwort

    def __init__(self, parent: QWidget, file_name: str) -> None:
        super().__init__(parent)
        self.setObjectName("LockOverlay")
        self.setAutoFillBackground(True)
        self.mode = "unlock"
        self.card = QFrame()
        self.card.setObjectName("LockCard")
        self.card.setFixedWidth(360)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(file_name)
        self.title.setObjectName("LockTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("SettingsNote")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)
        self.fields_single = PasswordFields(confirm=False)
        self.fields_double = PasswordFields(confirm=True)
        self.error = QLabel()
        self.error.setObjectName("LockError")
        self.error.setWordWrap(True)
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.button = QPushButton()
        self.button.setObjectName("Primary")
        self.info = QLabel()
        self.info.setObjectName("SettingsNote")
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QVBoxLayout(self.card)
        card.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        card.setSpacing(SPACING.sm)
        for widget in (self.icon, self.title, self.subtitle, self.fields_single, self.fields_double, self.error,
                       self.button, self.info):
            card.addWidget(widget)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)

        self.button.clicked.connect(self._submit)
        self.fields_single.submitted.connect(self._submit)
        self.fields_double.submitted.connect(self._submit)
        self.set_mode("unlock")

    def fields(self) -> PasswordFields:
        return self.fields_double if self.mode == "set" else self.fields_single

    def set_mode(self, mode: str, message: str = "", info: str = "") -> None:
        self.mode = mode
        self.fields_single.setVisible(mode != "set")
        self.fields_double.setVisible(mode == "set")
        self.icon.setPixmap(pixmap("lock", 32, COLORS.text_muted, self.devicePixelRatioF()))
        if mode == "set":
            self.subtitle.setText("Neue verschlüsselte Notiz. Lege ein Passwort fest – ohne es kommt niemand an "
                                  "den Inhalt, auch Notex nicht.")
            self.button.setText("Passwort festlegen")
        else:
            self.subtitle.setText("Diese Notiz ist verschlüsselt.")
            self.button.setText("Entsperren")
        self.error.setText(message)
        self.error.setVisible(bool(message))
        self.info.setText(info)
        self.info.setVisible(bool(info))
        self.fields().clear()

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(True)
        self.fields().password.selectAll()
        self.fields().password.setFocus()

    def focus_password(self) -> None:
        self.fields().password.setFocus()

    def _submit(self) -> None:
        problem = self.fields().validate()
        if problem:
            self.show_error(problem)
            return
        password = self.fields().password.text()
        self.fields().clear()
        self.submitted.emit(password)

    def retheme(self) -> None:
        self.icon.setPixmap(pixmap("lock", 32, COLORS.text_muted, self.devicePixelRatioF()))


class PasswordDialog(QDialog):
    """Modal: neues Passwort festlegen (optional mit aktuellem Passwort zur Bestätigung)."""

    def __init__(self, parent: QWidget, title: str, text: str, ask_current: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("PasswordDialog")
        self.setMinimumWidth(420)
        self.current = PasswordFields(confirm=False) if ask_current else None
        self.fields = PasswordFields(confirm=True)
        label = QLabel(text)
        label.setWordWrap(True)
        self.error = QLabel()
        self.error.setObjectName("LockError")
        self.error.setWordWrap(True)
        self.error.hide()
        ok = QPushButton("OK")
        ok.setObjectName("Primary")
        cancel = QPushButton("Abbrechen")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(label)
        if self.current is not None:
            self.current.password.setPlaceholderText("Aktuelles Passwort")
            layout.addWidget(self.current)
            new_label = QLabel("Neues Passwort:")
            layout.addWidget(new_label)
        layout.addWidget(self.fields)
        layout.addWidget(self.error)
        layout.addLayout(buttons)
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        self.fields.submitted.connect(self._accept)
        self.password = ""
        self.current_password = ""
        (self.current or self.fields).password.setFocus()

    def _accept(self) -> None:
        if self.current is not None and not self.current.password.text():
            self._error("Bitte das aktuelle Passwort eingeben.")
            return
        problem = self.fields.validate()
        if problem:
            self._error(problem)
            return
        self.password = self.fields.password.text()
        self.current_password = self.current.password.text() if self.current else ""
        self.fields.clear()
        if self.current:
            self.current.clear()
        self.accept()

    def _error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
