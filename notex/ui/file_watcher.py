"""Beobachtet offene Dateien und meldet externe Änderungen.

Den Baum hält QFileSystemModel selbst aktuell. Hier geht es nur um den Inhalt
der Dateien, die gerade in einem Tab offen sind.

Knackpunkt: Wenn wir selbst speichern, feuert der Watcher auch. Deshalb merken
wir uns pro Datei den Hash des Inhalts, den wir zuletzt geschrieben/gelesen
haben, und melden nur, wenn die Datei davon abweicht.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal


def _digest(path: Path) -> bytes | None:
    from notex.core.fileops import file_signature
    return file_signature(path)


class OpenFileWatcher(QObject):
    file_changed_externally = Signal(Path)
    file_removed_externally = Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self._watcher = QFileSystemWatcher(self)
        self._known: dict[str, bytes | None] = {}
        self._watcher.fileChanged.connect(self._on_file_changed)

    def watch(self, path: Path) -> None:
        key = str(path)
        self._known[key] = _digest(path)
        if key not in self._watcher.files():
            self._watcher.addPath(key)

    def unwatch(self, path: Path) -> None:
        key = str(path)
        self._known.pop(key, None)
        self._watcher.removePath(key)

    def mark_saved(self, path: Path) -> None:
        """Nach eigenem Speichern: neuen Hash merken und Watch erneuern.

        os.replace ersetzt die Datei physisch; auf manchen Systemen (inotify)
        verliert der Watcher dadurch den Pfad, deshalb neu registrieren.
        """
        self.watch(path)

    def _on_file_changed(self, key: str) -> None:
        # Kurz warten: Programme schreiben oft in mehreren Schritten (leeren, dann füllen).
        QTimer.singleShot(150, lambda: self._check(key))

    def _check(self, key: str) -> None:
        if key not in self._known:
            return
        path = Path(key)
        if not path.exists():
            self.file_removed_externally.emit(path)
            return
        if key not in self._watcher.files():
            self._watcher.addPath(key)
        digest = _digest(path)
        if digest != self._known[key]:
            self._known[key] = digest
            self.file_changed_externally.emit(path)
