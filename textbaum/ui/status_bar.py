"""Statusleiste: Pfad relativ zu data/, Zeile/Spalte, Encoding, Zeichen, Gespeichert-Status."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QStatusBar

from textbaum.ui.editor import Editor

ENCODING_LABELS = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8 BOM", "cp1252": "cp1252"}


class StatusBar(QStatusBar):
    def __init__(self) -> None:
        super().__init__()
        self.setSizeGripEnabled(False)
        self.path_label = QLabel()
        self.position_label = QLabel()
        self.encoding_label = QLabel()
        self.chars_label = QLabel()
        self.dirty_label = QLabel()
        self.addWidget(self.path_label, 1)  # stretch=1: nimmt den freien Platz links
        for label in (self.position_label, self.encoding_label, self.chars_label, self.dirty_label):
            self.addPermanentWidget(label)
        self.update_for(None, "")

    def update_for(self, editor: Editor | None, relative_path: str) -> None:
        if editor is None:
            self.path_label.setText("")
            for label in (self.position_label, self.encoding_label, self.chars_label, self.dirty_label):
                label.setText("")
            return
        line, col = editor.cursor_line_col()
        eol = "CRLF" if editor.eol == "\r\n" else "LF"
        self.path_label.setText(relative_path)
        self.position_label.setText(f"Z {line}, S {col}")
        self.encoding_label.setText(f"{ENCODING_LABELS.get(editor.encoding, editor.encoding)}  {eol}")
        self.chars_label.setText(f"{len(editor.toPlainText())} Zeichen")
        self.dirty_label.setText("Ungespeichert" if editor.is_dirty else "Gespeichert")
