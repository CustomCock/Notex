"""Führt core.search in einem eigenen Thread aus und meldet Treffer als Qt-Signale."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from textbaum.core.search import SearchOptions, search


class SearchWorker(QThread):
    name_found = Signal(int, object)     # generation, NameMatch
    file_found = Signal(int, object)     # generation, FileMatch
    search_done = Signal(int, object)    # generation, SearchResult

    def __init__(self, generation: int, root: Path, query: str, options: SearchOptions) -> None:
        super().__init__()
        self.generation = generation  # damit späte Signale alter Suchen ignoriert werden können
        self.root = root
        self.query = query
        self.options = options
        self.cancel = threading.Event()

    def run(self) -> None:
        result = search(
            self.root, self.query, self.options, self.cancel,
            on_name=lambda m: self.name_found.emit(self.generation, m),
            on_file=lambda m: self.file_found.emit(self.generation, m),
        )
        self.search_done.emit(self.generation, result)

    def stop(self) -> None:
        self.cancel.set()
