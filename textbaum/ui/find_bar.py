"""Suchen/Ersetzen-Leiste für die aktuelle Datei (Ctrl+F / Ctrl+H), unter den Tabs."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QLineEdit, QPushButton, QWidget

from textbaum.ui.editor import Editor


class FindBar(QWidget):
    def __init__(self, current_editor: Callable[[], Editor | None]) -> None:
        super().__init__()
        self.setObjectName("FindBar")
        self._current_editor = current_editor

        self.find_field = QLineEdit()
        self.find_field.setPlaceholderText("Suchen")
        self.replace_field = QLineEdit()
        self.replace_field.setPlaceholderText("Ersetzen durch")
        self.case_box = QCheckBox("Groß/Klein")
        self.status_label = QLabel()

        self.next_button = QPushButton("Weiter")
        self.prev_button = QPushButton("Zurück")
        self.replace_button = QPushButton("Ersetzen")
        self.replace_all_button = QPushButton("Alle ersetzen")
        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("FlatButton")
        self.close_button.setFixedWidth(28)

        grid = QGridLayout(self)
        grid.setContentsMargins(8, 4, 8, 6)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.addWidget(self.find_field, 0, 0)
        grid.addWidget(self.prev_button, 0, 1)
        grid.addWidget(self.next_button, 0, 2)
        grid.addWidget(self.case_box, 0, 3)
        grid.addWidget(self.status_label, 0, 4)
        grid.addWidget(self.close_button, 0, 5)
        grid.addWidget(self.replace_field, 1, 0)
        grid.addWidget(self.replace_button, 1, 1)
        grid.addWidget(self.replace_all_button, 1, 2)
        grid.setColumnStretch(0, 1)
        self.replace_widgets = (self.replace_field, self.replace_button, self.replace_all_button)

        self.find_field.textChanged.connect(self._on_term_changed)
        self.find_field.returnPressed.connect(self.find_next)
        self.replace_field.returnPressed.connect(self.replace_one)
        self.case_box.toggled.connect(self._on_term_changed)
        self.next_button.clicked.connect(self.find_next)
        self.prev_button.clicked.connect(self.find_previous)
        self.replace_button.clicked.connect(self.replace_one)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.close_button.clicked.connect(self.close_bar)
        # Shift+Enter im Suchfeld = rückwärts. QLineEdit schluckt Enter selbst,
        # deshalb fangen wir das Ereignis vorher per Event-Filter ab.
        self.find_field.installEventFilter(self)
        self.hide()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.find_field and event.type() == QEvent.Type.KeyPress \
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.find_previous()
            return True
        return super().eventFilter(watched, event)

    # ---- Anzeigen / Verstecken ----------------------------------------------
    def open(self, with_replace: bool) -> None:
        for widget in self.replace_widgets:
            widget.setVisible(with_replace)
        editor = self._current_editor()
        if editor is not None:
            # Markierten Text als Suchbegriff übernehmen, falls er einzeilig ist
            selected = editor.textCursor().selectedText()
            if selected and " " not in selected:  # U+2029 = Qt-Absatztrenner
                self.find_field.setText(selected)
        self.show()
        self.find_field.setFocus()
        self.find_field.selectAll()
        self._on_term_changed()

    def close_bar(self) -> None:
        self.hide()
        editor = self._current_editor()
        if editor is not None:
            editor.set_search_highlight("", False)
            editor.setFocus()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_bar()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.find_previous()
            return
        super().keyPressEvent(event)

    # ---- Aktionen ------------------------------------------------------------
    @property
    def term(self) -> str:
        return self.find_field.text()

    @property
    def case_sensitive(self) -> bool:
        return self.case_box.isChecked()

    def refresh_highlight(self) -> None:
        """Nach Tabwechsel: Markierung im neuen Editor setzen."""
        if self.isVisible():
            self._on_term_changed()

    def _on_term_changed(self) -> None:
        editor = self._current_editor()
        if editor is None:
            return
        editor.set_search_highlight(self.term, self.case_sensitive)
        count = len(editor._search_selections)
        self.status_label.setText("" if not self.term else (f"{count} Treffer" if count else "Keine Treffer"))

    def find_next(self) -> None:
        editor = self._current_editor()
        if editor is not None:
            editor.find_next(self.term, self.case_sensitive)

    def find_previous(self) -> None:
        editor = self._current_editor()
        if editor is not None:
            editor.find_next(self.term, self.case_sensitive, backwards=True)

    def replace_one(self) -> None:
        editor = self._current_editor()
        if editor is not None:
            editor.replace_current(self.term, self.replace_field.text(), self.case_sensitive)
            self._on_term_changed()

    def replace_all(self) -> None:
        editor = self._current_editor()
        if editor is not None:
            count = editor.replace_all(self.term, self.replace_field.text(), self.case_sensitive)
            self._on_term_changed()
            self.status_label.setText(f"{count} ersetzt")
