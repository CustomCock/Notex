"""Globaler Exception-Hook: kein Fehler endet mehr lautlos (Windows-Build hat keine Konsole).

Schreibt einen kurzen Eintrag nach <App-Ordner>/logs/notex-fehler.log (siehe core/errorlog.py) und zeigt
einen dezenten Hinweis im Hauptfenster. Hinweise werden gedrosselt, damit eine Fehlerserie nicht flutet.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from notex.core import errorlog

TOAST_INTERVAL = 3.0             # Sekunden zwischen zwei Fehler-Hinweisen


class ErrorHook(QObject):
    """Aufrufbar als sys.excepthook. Der Hinweis läuft über ein Signal – so landet er auch bei Fehlern aus
    Worker-Threads sicher im UI-Thread."""
    toast_requested = Signal(str)

    def __init__(self, window, log_dir: Path) -> None:
        super().__init__(window)
        self.window = window
        self.log_dir = log_dir
        self.previous = sys.excepthook
        self._last_toast = 0.0
        self._busy = False
        self.count = 0
        self.toast_requested.connect(self._toast)

    def __call__(self, exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt) or self._busy:
            self._chain(exc_type, exc, tb)
            return
        self._busy = True
        try:
            self.count += 1
            errorlog.append(self.log_dir, errorlog.format_entry(exc_type, exc, tb))
            now = time.monotonic()
            if now - self._last_toast >= TOAST_INTERVAL:
                self._last_toast = now
                message = f"Fehler: {errorlog.short_message(exc)} – Details in logs/{errorlog.LOG_NAME}"
                self.toast_requested.emit(message)
        finally:
            self._busy = False
        self._chain(exc_type, exc, tb)

    def _toast(self, message: str) -> None:
        toast = getattr(self.window, "toast", None)
        if toast is not None:
            try:
                toast.show_message(message, "triangle-alert")
            except RuntimeError:          # Fenster bereits zerstört
                pass

    def _chain(self, exc_type, exc, tb) -> None:
        """Weiterreichen (Dev-Modus: Ausgabe auf stderr). Im Build ohne Konsole ist stderr None."""
        if sys.stderr is not None and self.previous is not None and self.previous is not self:
            try:
                self.previous(exc_type, exc, tb)
            except Exception:             # noqa: BLE001 – Hook darf nie selbst werfen
                pass


def install(window, log_dir: Path) -> ErrorHook:
    hook = ErrorHook(window, log_dir)
    sys.excepthook = hook
    threading.excepthook = lambda args: hook(args.exc_type, args.exc_value, args.exc_traceback)
    return hook
