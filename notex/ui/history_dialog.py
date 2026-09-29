"""Versionsverlauf einer Datei (Ctrl+Shift+Y): Liste der Schnappschüsse links, Diff rechts.

Der Diff vergleicht die gewählte Version mit dem aktuellen Text im Editor (inklusive ungespeicherter
Änderungen). „Wiederherstellen“ ersetzt den Editor-Text als EINEN Undo-Schritt und speichert nicht –
man kann es also mit Ctrl+Z zurücknehmen oder erst prüfen und dann speichern.
"""
from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter,
                               QTextEdit, QVBoxLayout, QWidget)

from notex import APP_NAME
from notex.core.history import History, diff_lines, diff_stats, format_age
from notex.theme.fonts import MONO_FAMILIES
from notex.theme.tokens import COLORS, SPACING

ROLE_SHA = Qt.ItemDataRole.UserRole + 1
MAX_DIFF_LINES = 4000


class HistoryDialog(QDialog):
    restore_requested = Signal(str)      # Text der gewählten Version

    def __init__(self, parent: QWidget, history: History, rel: str, current_text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Versionsverlauf – {rel}")
        self.setObjectName("HistoryDialog")
        self.resize(900, 560)
        self.history, self.rel, self.current_text = history, rel, current_text

        self.list = QListWidget()
        self.list.setObjectName("HistoryList")
        self.list.setMinimumWidth(220)
        self.diff = QTextEdit()
        self.diff.setObjectName("HistoryDiff")
        self.diff.setReadOnly(True)
        self.diff.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.summary = QLabel()
        self.summary.setObjectName("SettingsNote")
        self.restore_button = QPushButton("Diese Version wiederherstellen")
        self.restore_button.setObjectName("Primary")
        self.restore_button.setEnabled(False)
        self.restore_button.setToolTip("Ersetzt den Text im Editor (rückgängig machbar mit Ctrl+Z), speichert nicht")
        close = QPushButton("Schließen")

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.summary)
        right_layout.addWidget(self.diff, 1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.list)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 660])
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(self.restore_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(splitter, 1)
        layout.addLayout(buttons)

        self.list.currentItemChanged.connect(lambda item, _prev: self._show(item))
        self.restore_button.clicked.connect(self._restore)
        close.clicked.connect(self.close)
        self._fill()

    def _fill(self) -> None:
        versions = self.history.versions(self.rel)
        now = time.time()
        for version in versions:
            text = format_age(version.timestamp, now)
            detail = time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(version.timestamp))
            label = f"  · {version.label}" if version.label else ""
            item = QListWidgetItem(f"{text}{label}\n{version.size} Zeichen")
            item.setToolTip(detail)
            item.setData(ROLE_SHA, version.sha)
            self.list.addItem(item)
        if not versions:
            self.summary.setText(f"Noch keine Versionen. {APP_NAME} legt bei jedem Speichern einen Schnappschuss an.")
            self.diff.clear()
            return
        self.list.setCurrentRow(1 if len(versions) > 1 and versions[0].sha == _sha(self.current_text) else 0)

    def _show(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        sha = item.data(ROLE_SHA)
        try:
            old = self.history.content(sha)
        except (OSError, ValueError) as error:
            self.summary.setText(f"Version nicht lesbar: {error}")
            self.diff.clear()
            self.restore_button.setEnabled(False)
            return
        self._selected_text = old
        lines = diff_lines(old, self.current_text)
        added, removed = diff_stats(lines)
        if not lines:
            self.summary.setText("Identisch mit dem aktuellen Text.")
            self.diff.setHtml(f'<p style="color:{COLORS.text_muted}">Keine Unterschiede.</p>')
            self.restore_button.setEnabled(False)
            return
        self.summary.setText(f"Gegenüber dem aktuellen Text: +{added} / −{removed} Zeilen  "
                             f"(rot = nur in dieser Version, grün = seitdem hinzugekommen)")
        self.diff.setHtml(render_diff_html(lines))
        self.restore_button.setEnabled(True)

    def _restore(self) -> None:
        text = getattr(self, "_selected_text", None)
        if text is not None:
            self.restore_requested.emit(text)
            self.close()


def _sha(text: str) -> str:
    from notex.core.history import text_sha
    return text_sha(text)


def render_diff_html(lines, limit: int = MAX_DIFF_LINES) -> str:
    red = "rgba(208, 102, 92, 0.22)"
    green = "rgba(110, 170, 110, 0.22)"
    rows: list[str] = []
    for index, line in enumerate(lines):
        if index >= limit:
            rows.append(f'<tr><td colspan="3" style="color:{COLORS.text_muted}">… Diff gekürzt</td></tr>')
            break
        text = html.escape(line.text) or "&nbsp;"
        if line.kind == "@":
            rows.append(f'<tr><td colspan="3" style="color:{COLORS.accent}; padding-top:6px">{text}</td></tr>')
            continue
        bg = red if line.kind == "-" else green if line.kind == "+" else "transparent"
        old_no = "" if line.old_no is None else str(line.old_no)
        new_no = "" if line.new_no is None else str(line.new_no)
        rows.append(f'<tr style="background:{bg}"><td width="40" style="color:{COLORS.text_muted}" align="right">{old_no}</td>'
                    f'<td width="40" style="color:{COLORS.text_muted}" align="right">{new_no}</td>'
                    f'<td style="white-space:pre-wrap; background:{bg}">{line.kind if line.kind != " " else "&nbsp;"} {text}</td></tr>')
    return (f'<table cellspacing="0" cellpadding="1" width="100%" style="font-family:\'{MONO_FAMILIES[0]}\'; '
            f'color:{COLORS.text}">' + "".join(rows) + "</table>")
