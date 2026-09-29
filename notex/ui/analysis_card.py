"""Kompakte Analyse-Karte: ein Popover neben der Markierung (statt großer Dialoge).

Zeigt erkannte Typen bzw. das Ergebnis einer Kontext-Aktion (Zeitstempel umrechnen, Zahl in Basen, JWT zerlegen,
Netzwerk-Abfrage, Hash-Info …). Aufbau ist inhaltsgetrieben: Kopf, Zeilen (Label/Wert, kopierbar), optionale
Aktionszeile (Knopf + Ergebnis + Ladeindikator) und eine Fußzeile („Als Notiz einfügen"/„Schließen").

Netzabfragen laufen in einem Worker-Thread (nie im UI-Thread), mit Abbruch beim Schließen der Karte.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QThread, QTimer, QRect, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from notex.core import lookup as lk
from notex.theme.tokens import COLORS, DURATION, SPACING
from notex.ui import anim
from notex.ui.widgets import IconButton

CARD_WIDTH = 392
BODY_MAX = 320


class _Worker(QThread):
    done = Signal(int, object, str)          # Generation, Ergebnis, Fehlertext

    def __init__(self, generation: int, job: Callable[[], object]) -> None:
        super().__init__()
        self.generation, self.job = generation, job

    def run(self) -> None:
        try:
            self.done.emit(self.generation, self.job(), "")
        except Exception as error:           # noqa: BLE001 – nie abstürzen, nur in der Karte melden
            self.done.emit(self.generation, None, str(error))


class AnalysisCard(QWidget):
    def __init__(self, window) -> None:
        super().__init__(window, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.window_ = window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._generation = 0
        self._workers: list[_Worker] = []
        self._note_text = ""
        self.anchor = QRect()

        self.card = QFrame(self)
        self.card.setObjectName("LookupCard")            # gleiche Optik wie die Nachschlage-Karte
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(self.card)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(SPACING.lg, SPACING.md, SPACING.lg, SPACING.md)
        root.setSpacing(SPACING.sm)

        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("LookupTitle")
        self.title.setWordWrap(True)
        close = IconButton("x", "Schließen (Esc)")
        close.clicked.connect(self.close)
        head.addWidget(self.title, 1)
        head.addWidget(close)
        root.addLayout(head)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("SettingsNote")
        self.subtitle.setWordWrap(True)
        self.subtitle.hide()
        root.addWidget(self.subtitle)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("LookupScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(SPACING.xs)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll)

        # Aktionszeile (Knopf + Ergebnis)
        self.action_row = QWidget()
        arow = QVBoxLayout(self.action_row)
        arow.setContentsMargins(0, 0, 0, 0)
        arow.setSpacing(SPACING.xs)
        self.action_button = QPushButton()
        self.action_button.clicked.connect(self._on_action)
        self.result = QLabel()
        self.result.setObjectName("SettingsNote")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        arow.addWidget(self.action_button)
        arow.addWidget(self.result)
        self.action_row.hide()
        root.addWidget(self.action_row)

        footer = QHBoxLayout()
        self.insert_button = QPushButton("Als Notiz einfügen")
        self.insert_button.clicked.connect(self._insert_note)
        self.insert_button.hide()
        footer.addWidget(self.insert_button)
        footer.addStretch(1)
        root.addLayout(footer)

        self._action_handler: Callable[[AnalysisCard], None] | None = None
        self._busy_timer = QTimer(self)
        self._busy_timer.timeout.connect(self._tick_busy)
        self._busy_dots = 0

    # ---- Aufbau -----------------------------------------------------------------------------------
    def reset(self, title: str, subtitle: str = "") -> None:
        self._generation += 1
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.action_row.hide()
        self.result.clear()
        self.insert_button.hide()
        self._note_text = ""
        self._action_handler = None

    def add_row(self, label: str, value: str, mono: bool = False, color: str = "") -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.sm)
        key = QLabel(label)
        key.setObjectName("SettingsNote")
        key.setMinimumWidth(96)
        key.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        val = QLabel(value)
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if mono:
            font = val.font()
            font.setFamily("JetBrains Mono")
            val.setFont(font)
        layout.addWidget(key)
        if color:
            swatch = QLabel()
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(f"background:{color}; border:1px solid {COLORS.border}; border-radius:3px;")
            layout.addWidget(swatch)
        layout.addWidget(val, 1)
        self.body_layout.addWidget(row)

    def add_text(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("SettingsNote")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body_layout.addWidget(label)

    def set_note(self, markdown: str) -> None:
        self._note_text = markdown
        self.insert_button.setVisible(bool(markdown))

    def set_action(self, label: str, handler: Callable[["AnalysisCard"], None] | None,
                   enabled: bool = True, disabled_reason: str = "") -> None:
        self.action_button.setText(label)
        self.action_button.setEnabled(enabled)
        self.action_button.setToolTip(disabled_reason if not enabled else "")
        self._action_handler = handler
        self.action_row.show()
        if not enabled and disabled_reason:
            self.result.setText(disabled_reason)

    # ---- Aktion / Async ---------------------------------------------------------------------------
    def _on_action(self) -> None:
        if self._action_handler is not None:
            self._action_handler(self)

    def run_job(self, job: Callable[[], object], on_result: Callable[[object], str]) -> None:
        """Job im Thread ausführen; on_result(result) liefert den Text für die Ergebniszeile."""
        self.set_busy(True)
        generation = self._generation
        worker = _Worker(generation, job)

        def done(gen: int, result: object, error: str) -> None:
            if gen != self._generation:
                return
            self.set_busy(False)
            if error:
                self.set_result(f"Fehler: {error}", error=True)
            else:
                try:
                    self.set_result(on_result(result))
                except Exception as exc:                 # noqa: BLE001
                    self.set_result(f"Fehler: {exc}", error=True)
            if worker in self._workers:
                self._workers.remove(worker)

        worker.done.connect(done)
        self._workers.append(worker)
        worker.start()

    def set_busy(self, busy: bool) -> None:
        self.action_button.setEnabled(not busy)
        if busy:
            self._busy_dots = 0
            self.result.setText("läuft …")
            self._busy_timer.start(300)
        else:
            self._busy_timer.stop()

    def _tick_busy(self) -> None:
        self._busy_dots = (self._busy_dots + 1) % 4
        self.result.setText("läuft " + "." * self._busy_dots)

    def set_result(self, text: str, error: bool = False) -> None:
        self.result.setText(text)
        self.result.setStyleSheet(f"color:{COLORS.danger};" if error else "")
        self.action_button.setEnabled(True)
        self._fit()

    # ---- Notiz einfügen ---------------------------------------------------------------------------
    def _insert_note(self) -> None:
        if self._note_text:
            self.window_.insert_analysis_note(self._note_text)
            self.close()

    # ---- Anzeigen / Platzieren --------------------------------------------------------------------
    def show_near(self, anchor: QRect | None = None) -> None:
        if anchor is None:
            pos = QGuiApplication.instance().overrideCursor()
            from PySide6.QtGui import QCursor
            p = QCursor.pos()
            anchor = QRect(p.x(), p.y(), 1, 1)
        self.anchor = anchor
        self._fit()
        if not self.isVisible():
            self.setWindowOpacity(0.0 if anim.duration(DURATION.fade) else 1.0)
            self.show()
            if anim.duration(DURATION.fade):
                anim.animate(self, 0.0, 1.0, int(DURATION.fade * 1.5), self.setWindowOpacity)
        self.raise_()
        self.activateWindow()

    def _fit(self) -> None:
        self.body.setFixedWidth(CARD_WIDTH - 2 * SPACING.lg - 8)
        hint = self.body.sizeHint().height()
        self.scroll.setFixedHeight(min(BODY_MAX, max(0, hint)))
        self.card.adjustSize()
        height = self.card.sizeHint().height()
        screen = QGuiApplication.screenAt(self.anchor.center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        x, y, h = lk.place_card((self.anchor.x(), self.anchor.y(), self.anchor.width(), self.anchor.height()),
                                (CARD_WIDTH, height),
                                (available.x(), available.y(), available.width(), available.height()))
        self.setGeometry(x, y, CARD_WIDTH, h)

    def closeEvent(self, event) -> None:
        self._generation += 1                # laufende Worker-Ergebnisse verwerfen
        self._busy_timer.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
