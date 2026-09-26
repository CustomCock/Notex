"""Hält den Link-Index (wer verlinkt auf wen) im Hintergrund aktuell.

Erster Aufbau in einem Thread über alle Textdateien in data/; danach inkrementell: beim
Speichern eines Tabs, bei externer Änderung (Watcher), bei Umbenennen/Löschen und wenn
der Dateiindex neue Dateien meldet. Verschlüsselte Inhalte gibt es hier (noch) nicht.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from notex.core.fileops import is_encrypted_path

from notex.core.encoding import decode_bytes
from notex.core.wikilinks import LinkIndex

MAX_BYTES = 2 * 1024 * 1024   # größere Dateien werden für den Link-Index übersprungen


class _Scanner(QThread):
    done = Signal(object)   # LinkIndex

    def __init__(self, root: Path, files: list[str]) -> None:
        super().__init__()
        self.root, self.files = root, list(files)

    def run(self) -> None:
        index = LinkIndex()
        index.set_files(self.files)
        for rel in self.files:
            if is_encrypted_path(rel):   # verschlüsselte Notizen: Inhalt bleibt unbekannt
                continue
            path = self.root / rel
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                text = decode_bytes(path.read_bytes()).text
            except (OSError, UnicodeDecodeError):
                continue
            if "[[" in text:
                index.update_file(rel, text)
        self.done.emit(index)


class LinkIndexService(QObject):
    updated = Signal()

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.index = LinkIndex()
        self._scanner: _Scanner | None = None
        self._pending_files: list[str] | None = None

    def rebuild(self, files: list[str]) -> None:
        if self._scanner is not None and self._scanner.isRunning():
            self._pending_files = files
            return
        self._scanner = _Scanner(self.root, files)
        self._scanner.done.connect(self._on_done)
        self._scanner.start()

    def _on_done(self, index: LinkIndex) -> None:
        self.index = index
        self.updated.emit()
        if self._pending_files is not None:
            files, self._pending_files = self._pending_files, None
            self.rebuild(files)

    def set_files(self, files: list[str]) -> None:
        self.index.set_files(files)

    def update_text(self, rel: str, text: str) -> None:
        if is_encrypted_path(rel):
            return
        self.index.update_file(rel, text)
        self.updated.emit()

    def update_path(self, rel: str) -> None:
        if is_encrypted_path(rel):
            return
        path = self.root / rel
        try:
            text = decode_bytes(path.read_bytes()).text
        except (OSError, UnicodeDecodeError):
            self.index.remove_file(rel)
        else:
            self.index.update_file(rel, text)
        self.updated.emit()

    def remove(self, rel: str) -> None:
        self.index.remove_file(rel)
        self.updated.emit()

    def rename(self, old_rel: str, new_rel: str) -> None:
        self.index.rename_file(old_rel, new_rel)
        self.updated.emit()

    def resolve(self, target: str) -> str | None:
        from notex.core.wikilinks import resolve
        return resolve(target, self.index.files)

    def shutdown(self) -> None:
        if self._scanner is not None and self._scanner.isRunning():
            self._scanner.wait(1000)
