"""Assistent zum Ausfüllen eines Fragebogens (core/questionnaire): ein Abschnitt pro Seite, Fortschritt,
Zurück/Weiter, Zwischenstand automatisch gemerkt. Am Ende entsteht eine formatierte Markdown-Notiz (Antworten
im Frontmatter, erneut bearbeitbar)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget, QDialog)
from PySide6.QtCore import QDate, QTime

from notex.core import questionnaire as qn
from notex.theme.tokens import SPACING


class QuestionnaireDialog(QDialog):
    completed = Signal(dict)         # Antworten, wenn fertiggestellt

    def __init__(self, window, questionnaire: qn.Questionnaire, answers: dict | None = None) -> None:
        super().__init__(window)
        self.window_ = window
        self.q = questionnaire
        self.answers: dict = dict(answers or {})
        self.setWindowTitle(questionnaire.title or "Fragebogen")
        self.resize(760, 640)
        self._index = 0
        self._widgets: dict[str, callable] = {}
        self._drafts = window.config.setdefault("questionnaire_drafts", {}) if not answers else {}
        if not answers:
            self.answers.update(self._drafts.get(self.q.id, {}))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.md)
        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, len(self.q.sections)))
        layout.addWidget(self.progress)
        self.heading = QLabel()
        self.heading.setObjectName("SettingsSection")
        layout.addWidget(self.heading)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(self.scroll, 1)

        nav = QHBoxLayout()
        self.back = QPushButton("Zurück")
        self.back.clicked.connect(self._prev)
        self.next = QPushButton("Weiter")
        self.next.clicked.connect(self._next)
        nav.addStretch(1)
        nav.addWidget(self.back)
        nav.addWidget(self.next)
        layout.addLayout(nav)
        self._show_section()

    # ---- Seiten ---------------------------------------------------------------------------------
    def _show_section(self) -> None:
        self._collect()
        section = self.q.sections[self._index]
        self.heading.setText(section.title or self.q.title)
        self.progress.setValue(self._index + 1)
        self._widgets = {}
        page = QWidget()
        form = QVBoxLayout(page)
        form.setSpacing(SPACING.md)
        for question in section.questions:
            if not qn.is_visible(question, self.answers):
                continue
            form.addWidget(self._question_widget(question))
        form.addStretch(1)
        self.scroll.setWidget(page)
        self.back.setEnabled(self._index > 0)
        self.next.setText("Fertigstellen" if self._index == len(self.q.sections) - 1 else "Weiter")

    def _question_widget(self, question: qn.Question) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(SPACING.xs)
        label = QLabel(question.label + (" *" if question.required else ""))
        label.setWordWrap(True)
        v.addWidget(label)
        if question.help:
            hint = QLabel(question.help)
            hint.setObjectName("SettingsNote")
            hint.setWordWrap(True)
            v.addWidget(hint)
        value = self.answers.get(question.id)
        self._build_input(question, value, v)
        return box

    def _build_input(self, question: qn.Question, value, layout) -> None:
        qid, qtype = question.id, question.type
        if qtype in ("yesno", "choice"):
            group = QButtonGroup(self)
            row = QHBoxLayout()
            opts = [v for v, _s in question.options] or ["Ja", "Nein"]
            for opt in opts:
                rb = QRadioButton(opt)
                rb.setChecked(str(value) == opt)
                group.addButton(rb)
                row.addWidget(rb)
            row.addStretch(1)
            layout.addLayout(row)
            self._widgets[qid] = lambda g=group: (g.checkedButton().text() if g.checkedButton() else None)
        elif qtype == "multichoice":
            checks = []
            opts = [v for v, _s in question.options]
            chosen = value if isinstance(value, list) else []
            for opt in opts:
                cb = QCheckBox(opt)
                cb.setChecked(opt in chosen)
                checks.append((opt, cb))
                layout.addWidget(cb)
            self._widgets[qid] = lambda cs=checks: [o for o, c in cs if c.isChecked()]
        elif qtype == "number":
            edit = QLineEdit("" if value is None else str(value))
            edit.setPlaceholderText("Zahl")
            layout.addWidget(edit)
            self._widgets[qid] = lambda e=edit: e.text().strip()
        elif qtype == "date":
            edit = QDateEdit()
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setDate(QDate.fromString(value, "yyyy-MM-dd") if value else QDate.currentDate())
            layout.addWidget(edit)
            self._widgets[qid] = lambda e=edit: e.date().toString("yyyy-MM-dd")
        elif qtype == "time":
            edit = QTimeEdit()
            edit.setDisplayFormat("HH:mm")
            edit.setTime(QTime.fromString(value, "HH:mm") if value else QTime(8, 0))
            layout.addWidget(edit)
            self._widgets[qid] = lambda e=edit: e.time().toString("HH:mm")
        elif qtype == "table":
            table = self._table_widget(question, value)
            layout.addWidget(table)
            self._widgets[qid] = lambda t=table, q=question: _read_table(t, q)
        else:   # text / Freitext
            edit = QPlainTextEdit(value or "")
            edit.setFixedHeight(80)
            layout.addWidget(edit)
            if question.chips:
                chips = QHBoxLayout()
                for chip in question.chips:
                    b = QPushButton(chip)
                    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    b.clicked.connect(lambda _c=False, e=edit, t=chip: e.insertPlainText(
                        ("" if not e.toPlainText() or e.toPlainText().endswith(("\n", " ")) else " ") + t))
                    chips.addWidget(b)
                chips.addStretch(1)
                layout.addLayout(chips)
            self._widgets[qid] = lambda e=edit: e.toPlainText().strip()

    def _table_widget(self, question: qn.Question, value) -> QTableWidget:
        cols = question.columns or ["Wert"]
        rows = value if isinstance(value, list) else []
        table = QTableWidget(max(len(rows) + 1, 3), len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.verticalHeader().setVisible(False)
        for r, row in enumerate(rows):
            for c, col in enumerate(cols):
                table.setItem(r, c, QTableWidgetItem(str(row.get(col, "") if isinstance(row, dict) else "")))
        return table

    # ---- Navigation -----------------------------------------------------------------------------
    def _collect(self) -> None:
        for qid, getter in self._widgets.items():
            try:
                self.answers[qid] = getter()
            except Exception:      # noqa: BLE001
                pass
        # Zwischenstand merken (wird nach dem Fertigstellen wieder entfernt)
        self.window_.config.setdefault("questionnaire_drafts", {})[self.q.id] = dict(self.answers)

    def _prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._show_section()

    def _next(self) -> None:
        self._collect()
        section = self.q.sections[self._index]
        missing = [(q.id, q.label) for q in section.questions
                   if q.required and qn.is_visible(q, self.answers)
                   and self.answers.get(q.id) in (None, "", [])]
        if missing:
            from notex.ui import dialogs
            dialogs.warn(self, "Pflichtfelder", "Bitte ausfüllen:\n" + "\n".join(f"• {label}" for _i, label in missing))
            return
        if self._index < len(self.q.sections) - 1:
            self._index += 1
            self._show_section()
        else:
            self._finish()

    def _finish(self) -> None:
        remaining = qn.missing_required(self.q, self.answers)
        if remaining:
            from notex.ui import dialogs
            dialogs.warn(self, "Pflichtfelder", "Es fehlen noch Pflichtangaben:\n"
                         + "\n".join(f"• {label}" for _i, label in remaining))
            return
        self.window_.config.get("questionnaire_drafts", {}).pop(self.q.id, None)
        self.completed.emit(dict(self.answers))
        self.accept()


def _read_table(table: QTableWidget, question: qn.Question) -> list:
    cols = question.columns or ["Wert"]
    rows = []
    for r in range(table.rowCount()):
        row = {}
        empty = True
        for c, col in enumerate(cols):
            item = table.item(r, c)
            text = item.text().strip() if item else ""
            row[col] = text
            empty = empty and not text
        if not empty:
            rows.append(row)
    return rows
