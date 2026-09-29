"""„Live verfolgen“: neue Zeilen erscheinen unten, Autoscroll pausiert beim Hochscrollen, Filter nur für die Anzeige.

Die Ansicht liest die Datei selbst (core.tail) – der Editortext bleibt unberührt, die Datei wird nie geschrieben.
Solange „live“ läuft, ist der Tab nur lesend; beim Beenden lädt der Editor den aktuellen Stand von der Platte.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from notex.core import tail
from notex.core.tail import LogFilter, Tailer
from notex.theme.tokens import COLORS, SPACING
from notex.ui.widgets import IconButton

POLL_MS = 500
MAX_LINES = 200_000          # ältere Zeilen fallen aus der Anzeige (die Datei bleibt vollständig)


class _LevelHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:
        level = tail.classify(text)
        if level is None:
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(COLORS.danger if level == "error" else COLORS.warning))
        self.setFormat(0, len(text), fmt)


class LogView(QWidget):
    changed = Signal()              # nie – nur lesend (Schnittstelle wie CsvView)
    status_changed = Signal()
    stop_requested = Signal()
    kind = "live"

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DataView")
        self.dirty = False
        self.overridden = False
        self.dialect = None
        self.tailer: Tailer | None = None
        self.lines: list[str] = []
        self.shown = 0
        self.last_update = ""
        self.missing = False
        self.filter = LogFilter()
        self._follow = True
        self._reparse = None
        self._reencode = None

        self.text_view = QPlainTextEdit()
        self.text_view.setObjectName("LogText")
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_view.setMaximumBlockCount(MAX_LINES)
        self.text_view.setFrameStyle(QFrame.Shape.NoFrame)
        self.highlighter = _LevelHighlighter(self.text_view.document())
        self.text_view.verticalScrollBar().valueChanged.connect(self._on_scrolled)

        self.level_box = QComboBox()
        self.level_box.addItem("Alle Zeilen", "all")
        self.level_box.addItem("WARN und schlimmer", "warn")
        self.level_box.addItem("Nur ERROR", "error")
        self.level_box.currentIndexChanged.connect(lambda _i: self._filter_timer.start())
        self.filter_field = QLineEdit()
        self.filter_field.setPlaceholderText("Filtern (Text) …")
        self.filter_field.setClearButtonEnabled(True)
        self.filter_field.textChanged.connect(lambda _t: self._filter_timer.start())
        self.regex_box = QCheckBox("Regex")
        self.regex_box.toggled.connect(lambda _on: self._filter_timer.start())
        self.pause_button = QPushButton("Pausiert – Ende anspringen")
        self.pause_button.setObjectName("LogPaused")
        self.pause_button.clicked.connect(self.jump_to_end)
        self.pause_button.setVisible(False)
        self.info = QLabel()
        self.info.setObjectName("DataInfo")
        stop = IconButton("square", "Live verfolgen beenden")
        stop.clicked.connect(self.stop_requested)
        strip = QFrame()
        strip.setObjectName("DataBar")
        bar = QHBoxLayout(strip)
        bar.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        bar.setSpacing(SPACING.sm)
        live = QLabel("● Live")
        live.setObjectName("LiveBadge")
        bar.addWidget(live)
        bar.addWidget(self.level_box)
        bar.addWidget(self.filter_field, 1)
        bar.addWidget(self.regex_box)
        bar.addWidget(self.pause_button)
        bar.addWidget(self.info)
        bar.addWidget(stop)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(strip)
        layout.addWidget(self.text_view, 1)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self._apply_filter)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_MS)
        self._poll_timer.timeout.connect(self.poll)

    # ---- Start/Stopp --------------------------------------------------------------------------------
    def load_text(self, _text: str, name: str, dialect=None, encoding: str = "utf-8", path: Path | None = None) -> None:
        """Start (bzw. Neustart nach Encoding-Wechsel). Der Editortext wird ignoriert – gelesen wird von der Platte."""
        if path is None:
            return
        self.tailer = Tailer(path, encoding)
        self._take(self.tailer.start())
        self._poll_timer.start()

    def stop(self) -> None:
        self._poll_timer.stop()
        self.tailer = None

    def set_font(self, font) -> None:
        self.text_view.setFont(font)

    def poll(self) -> None:
        if self.tailer is None:
            return
        result = self.tailer.poll()
        self._take(result)
        if result.more:
            QTimer.singleShot(0, self.poll)           # großer Nachschub: gleich weiterlesen, ohne zu blockieren

    def _take(self, result: tail.TailResult) -> None:
        if result.missing:
            if not self.missing:
                self.missing = True
                self._update_info()
            return
        self.missing = False
        if result.reset:
            self.lines = []
            self.text_view.clear()
            self.shown = 0
            if result.skipped:
                self.text_view.appendPlainText(f"… {result.skipped:,} Bytes am Anfang ausgelassen (nur die letzten 8 MB)"
                                               .replace(",", "."))
        if not result.lines and not result.reset:
            return
        self.lines.extend(result.lines)
        if len(self.lines) > MAX_LINES:
            del self.lines[:len(self.lines) - MAX_LINES]
        self._append(self.filter.apply(result.lines))
        self.last_update = time.strftime("%H:%M:%S")
        self._update_info()

    def _append(self, lines: list[str]) -> None:
        if not lines:
            return
        bar = self.text_view.verticalScrollBar()
        position = bar.value()
        self.text_view.setUpdatesEnabled(False)
        self.text_view.appendPlainText("\n".join(lines))
        self.text_view.setUpdatesEnabled(True)
        self.shown += len(lines)
        if self._follow:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(position)

    # ---- Autoscroll ----------------------------------------------------------------------------------
    def _on_scrolled(self, value: int) -> None:
        bar = self.text_view.verticalScrollBar()
        at_end = value >= bar.maximum() - 2
        if at_end != self._follow:
            self._follow = at_end
            self.pause_button.setVisible(not at_end)

    def jump_to_end(self) -> None:
        bar = self.text_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._follow = True
        self.pause_button.setVisible(False)

    @property
    def following(self) -> bool:
        return self._follow

    # ---- Filter --------------------------------------------------------------------------------------
    def _apply_filter(self) -> None:
        self.filter = LogFilter(level=self.level_box.currentData(), text=self.filter_field.text(),
                                regex=self.regex_box.isChecked())
        self.filter_field.setProperty("state", "bad" if self.filter.error else "")
        self.filter_field.style().unpolish(self.filter_field)
        self.filter_field.style().polish(self.filter_field)
        self.filter_field.setToolTip(self.filter.error or "")
        self.text_view.clear()
        self.shown = 0
        self._append(self.filter.apply(self.lines))
        if self._follow:
            self.jump_to_end()
        self._update_info()

    def _update_info(self) -> None:
        if self.missing:
            text = "Datei fehlt – wartet auf Neuanlage"
        else:
            total = f"{len(self.lines):,}".replace(",", ".")
            text = f"{self.shown:,} von {total} Zeilen".replace(",", ".") if self.filter.active else f"{total} Zeilen"
            if self.last_update:
                text += f" · {self.last_update}"
        self.info.setText(text)
        self.status_changed.emit()

    # ---- Schnittstelle der Datenansicht ---------------------------------------------------------------
    def text(self) -> str:
        return ""

    def focus_filter(self) -> None:
        self.filter_field.setFocus()
        self.filter_field.selectAll()

    def setFocus(self) -> None:          # noqa: N802 – Qt-Name
        self.text_view.setFocus()

    def position_text(self) -> str:
        return "Live · nur lesen" if self._follow else "Live · pausiert"

    def status_parts(self) -> list[str]:
        return [self.info.text(), ""]
