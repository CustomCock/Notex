"""Statusleiste: niedrig, klein, gedämpft. Elemente rechts durch Punkte getrennt."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QStatusBar, QToolButton

from notex.core.spell import LANGUAGE_LABELS
from notex.theme.icons import icon
from notex.theme.theme import style_menu
from notex.ui.widgets import IconButton
from PySide6.QtWidgets import QMenu

from notex.ui.editor import Editor

ENCODING_LABELS = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8 BOM", "cp1252": "cp1252"}


LANGUAGE_SHORT = {"de": "DE", "en": "EN", "both": "DE+EN"}


class StatusBar(QStatusBar):
    spell_toggled = Signal()
    grammar_toggled = Signal()
    language_chosen = Signal(object)     # "de" | "en" | "both" | None (= global)

    def __init__(self) -> None:
        super().__init__()
        self.setSizeGripEnabled(False)
        self.spell_button = IconButton("spell-check", "Rechtschreibung  F7", size=14)
        self.spell_button.setCheckable(True)
        self.spell_button.clicked.connect(self.spell_toggled)
        self.grammar_button = IconButton("languages", "Grammatik (LanguageTool)  Shift+F7", size=14)
        self.grammar_button.setCheckable(True)
        self.grammar_button.clicked.connect(self.grammar_toggled)
        self.language_button = QToolButton()
        self.language_button.setObjectName("StatusLanguage")
        self.language_button.setToolTip("Rechtschreib-Sprache für diesen Tab")
        self.language_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.language_menu = style_menu(QMenu(self.language_button))
        for key in ("de", "en", "both"):
            self.language_menu.addAction(LANGUAGE_LABELS[key], lambda k=key: self.language_chosen.emit(k))
        self.language_menu.addSeparator()
        self.language_menu.addAction("Globale Einstellung", lambda: self.language_chosen.emit(None))
        self.language_button.setMenu(self.language_menu)
        self.grammar_state_label = QLabel()
        self.grammar_state_label.setObjectName("StatusDot")
        self.readonly_label = QLabel("Schreibgeschützt")
        self.readonly_label.setObjectName("StatusWarn")
        self.readonly_label.setToolTip("Die Datei kann nicht überschrieben werden – Speichern bietet „Speichern unter …“ an")
        self.path_label = QLabel()
        self.position_label = QLabel()
        self.encoding_label = QLabel()
        self.chars_label = QLabel()
        self.dirty_label = QLabel()
        self._separators: list[QLabel] = []
        self.addWidget(self.path_label, 1)  # stretch=1: nimmt den freien Platz links
        self.addPermanentWidget(self.spell_button)
        self.addPermanentWidget(self.grammar_button)
        self.addPermanentWidget(self.language_button)
        self.addPermanentWidget(self.grammar_state_label)
        self.addPermanentWidget(self.readonly_label)
        for i, label in enumerate((self.position_label, self.encoding_label, self.chars_label, self.dirty_label)):
            if i:
                dot = QLabel("·")
                dot.setObjectName("StatusDot")
                self._separators.append(dot)
                self.addPermanentWidget(dot)
            self.addPermanentWidget(label)
        self.update_for(None, "")

    def set_spell_state(self, spelling: bool, grammar: bool, language: str, per_tab: bool, grammar_note: str = "") -> None:
        self.spell_button.setChecked(spelling)
        self.grammar_button.setChecked(grammar)
        self.language_button.setText(LANGUAGE_SHORT.get(language, "DE") + ("*" if per_tab else ""))
        self.grammar_state_label.setText(grammar_note)
        self.grammar_state_label.setVisible(bool(grammar_note))

    def retheme(self) -> None:
        self.spell_button.setIcon(icon("spell-check"))
        self.grammar_button.setIcon(icon("languages"))

    def update_for(self, editor: Editor | None, relative_path: str) -> None:
        labels = (self.position_label, self.encoding_label, self.chars_label, self.dirty_label)
        for widget in (self.spell_button, self.grammar_button, self.language_button):
            widget.setVisible(editor is not None)
        self.readonly_label.setVisible(editor is not None and getattr(editor, "read_only", False))
        if editor is None:
            self.path_label.setText("")
            for label in labels:
                label.setText("")
            for dot in self._separators:
                dot.setVisible(False)
            return
        for dot in self._separators:
            dot.setVisible(True)
        line, col = editor.cursor_line_col()
        eol = "CRLF" if editor.eol == "\r\n" else "LF"
        self.path_label.setText(relative_path)
        self.position_label.setText(f"Z {line}, S {col}")
        self.encoding_label.setText(f"{ENCODING_LABELS.get(editor.encoding, editor.encoding)} · {eol}")
        # characterCount statt toPlainText: bei 5 MB kostet das Kopieren des Texts sonst 12 ms pro Tastendruck
        self.chars_label.setText(f"{max(0, editor.document().characterCount() - 1)} Zeichen")
        self.dirty_label.setText("Ungespeichert" if editor.is_dirty else "Gespeichert")
