"""Gemeinsame Basis für Datei-Analysen (Strings, Eingebettete Dateien, Entropie): Hintergrund-Thread,
Fortschritt, Abbrechen-Knopf, nicht modal – die Oberfläche bleibt bedienbar, auch bei mehreren GB."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from notex.theme.tokens import SPACING
from notex.ui.viewer_page import human_size


class AnalysisWorker(QThread):
    progress = Signal(int)                 # Promille
    done = Signal(object, str)             # Ergebnis oder None, Fehlertext ("" = ok bzw. abgebrochen)

    def __init__(self, job: Callable) -> None:
        """job(progress, cancelled) -> Ergebnis; progress(done, total), cancelled() -> bool."""
        super().__init__()
        self.job = job
        self.cancel = False

    def run(self) -> None:
        try:
            result = self.job(lambda d, t: self.progress.emit(int(d * 1000 / max(1, t))), lambda: self.cancel)
            self.done.emit(None if self.cancel else result, "")
        except OSError as error:
            self.done.emit(None, str(error))
        except Exception as error:   # noqa: BLE001 – Abbruch-Ausnahmen der Kernmodule und unerwartete Daten
            self.done.emit(None, "" if self.cancel else f"{type(error).__name__}: {error}")


class AnalysisDialog(QDialog):
    """Rahmen: Kopf (Datei, Größe), Inhalt der Unterklasse, Fortschritt + Abbrechen, Status, Schließen."""

    def __init__(self, window, path: Path, title: str) -> None:
        super().__init__(window)
        self.window_ = window
        self.path = Path(path)
        self.setWindowTitle(f"{title} – {self.path.name}")
        self.resize(900, 620)
        try:
            size = human_size(self.path.stat().st_size)
        except OSError:
            size = "?"
        self.head = QLabel(f"{self.path.name}  ·  {size}")
        self.head.setObjectName("SettingsNote")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self.cancel)
        self.status = QLabel()
        self.status.setObjectName("SettingsNote")
        self.body = QVBoxLayout()
        self.footer = QHBoxLayout()
        self.footer.addWidget(self.status, 1)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        self._close_button = close
        run_row = QHBoxLayout()
        run_row.addWidget(self.progress, 1)
        run_row.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.head)
        layout.addLayout(self.body, 1)
        layout.addLayout(run_row)
        layout.addLayout(self.footer)
        self.worker: AnalysisWorker | None = None

    def add_footer_button(self, widget: QWidget) -> None:
        self.footer.addWidget(widget)

    def finish_layout(self) -> None:
        self.footer.addWidget(self._close_button)

    def start(self, job: Callable) -> None:
        self.cancel()
        if self.worker is not None:
            self.worker.wait()
        self.worker = AnalysisWorker(job)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.done.connect(self._on_done)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self.status.setText("Läuft …")
        self.worker.start()

    def cancel(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel = True

    def _on_done(self, result, error: str) -> None:
        worker = self.sender()
        if worker is not self.worker:
            return
        worker.wait()
        self.cancel_button.setEnabled(False)
        if result is None:
            self.status.setText(error or "Abgebrochen")
            return
        self.progress.setValue(1000)
        self.show_result(result)

    def show_result(self, result) -> None:
        raise NotImplementedError

    def jump(self, offset: int, length: int = 1) -> None:
        self.window_.show_in_hex(self.path, offset, length)

    def closeEvent(self, event) -> None:
        self.cancel()
        if self.worker is not None:
            self.worker.wait(3000)
        super().closeEvent(event)
