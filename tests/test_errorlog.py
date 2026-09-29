"""R1: Unbehandelte Fehler dürfen nicht lautlos verschwinden (Windows-Build ohne Konsole)."""
import os
import sys

import pytest

from notex.core import errorlog


def _raise(message: str):
    try:
        raise ValueError(message)
    except ValueError:
        return sys.exc_info()


def test_short_message_type_and_truncation():
    _t, exc, _tb = _raise("x" * 500)
    text = errorlog.short_message(exc)
    assert text.startswith("ValueError: ")
    assert len(text) <= len("ValueError: ") + errorlog.MAX_MESSAGE


def test_entry_has_frames_but_no_source_lines():
    exc_type, exc, tb = _raise("kaputt")
    entry = errorlog.format_entry(exc_type, exc, tb, now=0)
    assert "ValueError: kaputt" in entry
    assert "test_errorlog.py:" in entry and "in _raise" in entry
    assert "raise ValueError(message)" not in entry         # keine Quelltextzeilen/Inhalte


def test_append_creates_dir_and_rotates(tmp_path):
    log_dir = tmp_path / "logs"
    path = errorlog.append(log_dir, "eins\n", max_bytes=10)
    assert path is not None and path.read_text(encoding="utf-8") == "eins\n"
    errorlog.append(log_dir, "x" * 20 + "\n", max_bytes=10)
    errorlog.append(log_dir, "drei\n", max_bytes=10)          # Datei > 10 Bytes → rotiert
    assert (log_dir / (errorlog.LOG_NAME + ".1")).exists()
    assert path.read_text(encoding="utf-8") == "drei\n"


def test_append_never_raises(tmp_path):
    blocker = tmp_path / "logs"
    blocker.write_text("ich bin eine Datei")                  # Ordner kann nicht angelegt werden
    assert errorlog.append(blocker, "x\n") is None


def test_hook_in_slot_logs_and_toasts(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QWidget
    from notex.ui import error_hook

    app = QApplication.instance() or QApplication([])

    class Toast:
        messages = []

        def show_message(self, text, icon_name="check"):
            self.messages.append((text, icon_name))

    window = QWidget()
    window.toast = Toast()
    import threading
    old_hook, old_thread_hook = sys.excepthook, threading.excepthook
    hook = error_hook.install(window, tmp_path / "logs")
    try:
        def slot():
            raise RuntimeError("Slot kaputt")
        QTimer.singleShot(0, slot)
        for _ in range(5):
            app.processEvents()
    finally:
        sys.excepthook, threading.excepthook = old_hook, old_thread_hook
    assert hook.count == 1
    log = (tmp_path / "logs" / errorlog.LOG_NAME).read_text(encoding="utf-8")
    assert "RuntimeError: Slot kaputt" in log
    assert window.toast.messages and "RuntimeError: Slot kaputt" in window.toast.messages[0][0]
    assert window.toast.messages[0][1] == "triangle-alert"
