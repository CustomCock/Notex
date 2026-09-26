"""Hält den Dateiindex für Quick Open im Hintergrund aktuell.

Scannt data/ in einem Thread (auch tausende Dateien ohne spürbare Verzögerung), stößt sich
selbst neu an, wenn der Baum Änderungen meldet (Watcher des QFileSystemModel, eigene
Dateioperationen) – gebündelt über einen kurzen Timer – und zur Sicherheit alle 60 s.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from notex.core.file_index import FileIndex, scan_files

RESCAN_DEBOUNCE_MS = 400
PERIODIC_MS = 60_000


class _Scanner(QThread):
    done = Signal(list)

    def __init__(self, root: Path, extensions: list[str]) -> None:
        super().__init__()
        self.root, self.extensions = root, list(extensions)

    def run(self) -> None:
        try:
            self.done.emit(scan_files(self.root, self.extensions))
        except OSError:
            self.done.emit([])


class FileIndexService(QObject):
    updated = Signal()

    def __init__(self, root: Path, config: dict) -> None:
        super().__init__()
        self.root = root
        self.config = config
        self.index = FileIndex()
        self._scanner: _Scanner | None = None
        self._dirty = False
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(RESCAN_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._start)
        self._periodic = QTimer(self)
        self._periodic.setInterval(PERIODIC_MS)
        self._periodic.timeout.connect(self.request_rescan)
        self._periodic.start()

    def attach_tree(self, tree) -> None:
        """An die Signale des Baums hängen: alles, was dort auftaucht oder verschwindet, ist ein Rescan."""
        model = tree.model_
        model.rowsInserted.connect(lambda *_: self.request_rescan())
        model.rowsRemoved.connect(lambda *_: self.request_rescan())
        model.fileRenamed.connect(lambda *_: self.request_rescan())
        tree.path_renamed.connect(lambda *_: self.request_rescan())
        tree.path_deleted.connect(lambda *_: self.request_rescan())

    def request_rescan(self) -> None:
        self._debounce.start()

    def _start(self) -> None:
        if self._scanner is not None and self._scanner.isRunning():
            self._dirty = True   # nach dem laufenden Scan gleich noch einmal
            return
        self._scanner = _Scanner(self.root, self.config.get("extensions", []))
        self._scanner.done.connect(self._on_done)
        self._scanner.start()

    def _on_done(self, files: list) -> None:
        self.index.set_files(files)
        self.updated.emit()
        if self._dirty:
            self._dirty = False
            self._start()

    def set_externals(self, paths: list[str]) -> None:
        self.index.set_externals(paths)

    def shutdown(self) -> None:
        self._periodic.stop()
        if self._scanner is not None and self._scanner.isRunning():
            self._scanner.wait(1000)
