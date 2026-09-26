"""„Prüfsummen …“: MD5, SHA-1, SHA-256, SHA-512 im Hintergrund, kopierbar, mit „Vergleichen mit …“ (grün/rot)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from notex.core import hashing
from notex.theme.fonts import MONO_FAMILIES
from notex.theme.tokens import SPACING
from notex.ui.viewer_page import human_size
from notex.ui.widgets import IconButton


class _HashThread(QThread):
    progress = Signal(int)
    done = Signal(object, str)          # dict | None, Fehlertext

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.cancel = False

    def run(self) -> None:
        try:
            result = hashing.hash_file(self.path, progress=lambda d, t: self.progress.emit(int(d * 1000 / max(1, t))),
                                       cancelled=lambda: self.cancel)
            self.done.emit(result, "")
        except hashing.Cancelled:
            self.done.emit(None, "")
        except OSError as error:
            self.done.emit(None, str(error))


class HashDialog(QDialog):
    def __init__(self, parent: QWidget, path: Path) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Prüfsummen – {path.name}")
        self.resize(760, 320)
        self.path = path
        self.digests: dict[str, str] = {}
        try:
            size = human_size(path.stat().st_size)
        except OSError:
            size = "?"
        head = QLabel(f"{path.name}  ·  {size}")
        head.setObjectName("SettingsNote")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        mono = QFont()
        mono.setFamilies(MONO_FAMILIES)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING.sm)
        self.fields: dict[str, QLineEdit] = {}
        for row, name in enumerate(hashing.ALGORITHMS):
            field = QLineEdit()
            field.setReadOnly(True)
            field.setFont(mono)
            field.setPlaceholderText("wird berechnet …")
            copy = IconButton("copy", f"{hashing.LABELS[name]} kopieren")
            copy.clicked.connect(lambda _c=False, f=field: QApplication.clipboard().setText(f.text()) if f.text() else None)
            grid.addWidget(QLabel(hashing.LABELS[name]), row, 0)
            grid.addWidget(field, row, 1)
            grid.addWidget(copy, row, 2)
            self.fields[name] = field
        self.compare = QLineEdit()
        self.compare.setPlaceholderText("Vergleichen mit … (erwartete Prüfsumme einfügen)")
        self.compare.setFont(mono)
        self.compare.textChanged.connect(self._compare)
        self.verdict = QLabel()
        self.verdict.setObjectName("HashVerdict")
        note = QLabel("MD5 und SHA-1 taugen nur zum Abgleich mit veröffentlichten Werten, nicht als Sicherheitsnachweis.")
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self._cancel)
        close = QPushButton("Schließen")
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(note, 1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.md)
        layout.addWidget(head)
        layout.addWidget(self.progress)
        layout.addLayout(grid)
        layout.addWidget(self.compare)
        layout.addWidget(self.verdict)
        layout.addStretch(1)
        layout.addLayout(buttons)
        self._thread = _HashThread(path)
        self._thread.progress.connect(self.progress.setValue)
        self._thread.done.connect(self._done)
        self._thread.start()

    def _done(self, result, error: str) -> None:
        self._thread.wait()
        self.cancel_button.setEnabled(False)
        if result is None:
            for field in self.fields.values():
                field.setPlaceholderText(error or "abgebrochen")
            self.verdict.setText(error)
            return
        self.digests = result
        self.progress.setValue(1000)
        for name, value in result.items():
            self.fields[name].setText(value)
        self._compare(self.compare.text())

    def _compare(self, text: str) -> None:
        state = ""
        if not text.strip():
            self.verdict.setText("")
        elif not hashing.normalize_digest(text):
            self.verdict.setText("Das ist keine Prüfsumme (erwartet Hex-Ziffern)")
            state = "bad"
        elif not self.digests:
            expected = hashing.expected_algorithm(text)
            self.verdict.setText(f"Vergleich folgt, sobald die Berechnung fertig ist"
                                 + (f" (sieht aus wie {hashing.LABELS[expected]})" if expected else ""))
        else:
            match = hashing.match_digest(text, self.digests)
            if match:
                self.verdict.setText(f"✓ Stimmt mit {hashing.LABELS[match]} überein")
                state = "ok"
            else:
                expected = hashing.expected_algorithm(text)
                self.verdict.setText("✗ Keine Übereinstimmung"
                                     + (f" – {hashing.LABELS[expected]} der Datei weicht ab" if expected else ""))
                state = "bad"
        for widget in (self.compare, self.verdict):
            widget.setProperty("state", state)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        for name, field in self.fields.items():
            matched = state == "ok" and hashing.match_digest(text, {name: self.digests.get(name, "")}) == name
            field.setProperty("state", "ok" if matched else "")
            field.style().unpolish(field)
            field.style().polish(field)

    def _cancel(self) -> None:
        self._thread.cancel = True

    def done(self, result: int) -> None:       # auch beim Schließen per Esc/Fensterknopf
        self._thread.cancel = True
        self._thread.wait(3000)
        super().done(result)
