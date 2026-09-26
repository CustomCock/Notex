"""Seitenleiste: Suchfeld, Checkboxen und darunter Baum oder Trefferliste.

Ablauf einer Suche:
  Tippen -> Debounce-Timer (250 ms) -> alte Suche abbrechen -> neuer Worker-Thread
  -> Treffer kommen als Signale herein -> Ergebnisliste füllt sich.
Solange das Feld nicht leer ist, zeigt der Stack die Trefferliste statt des Baums.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QStackedWidget, QVBoxLayout, QWidget

from textbaum.core.search import SearchOptions, SearchResult
from textbaum.ui.file_tree import FileTree
from textbaum.ui.search_results import SearchResults
from textbaum.ui.search_worker import SearchWorker

DEBOUNCE_MS = 250


class Sidebar(QWidget):
    open_requested = Signal(Path, object)   # Pfad, (line, column, length) oder None

    def __init__(self, root: Path, config: dict[str, Any]) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.root = root
        self.config = config

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Suchen …  (Ctrl+Shift+F)")
        self.search_field.setClearButtonEnabled(True)

        self.by_name = QCheckBox("Dateiname")
        self.full_text = QCheckBox("Volltext")
        self.by_name.setChecked(config["search"]["by_name"])
        self.full_text.setChecked(config["search"]["full_text"])
        checks = QHBoxLayout()
        checks.setContentsMargins(2, 0, 0, 0)
        checks.addWidget(self.by_name)
        checks.addWidget(self.full_text)
        checks.addStretch()

        self.tree = FileTree(root, config["extensions"])
        self.results = SearchResults()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.results)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 4, 0)
        layout.setSpacing(6)
        layout.addWidget(self.search_field)
        layout.addLayout(checks)
        layout.addWidget(self.stack, 1)

        # Debounce: Timer wird bei jedem Tastendruck neu gestartet, sucht erst bei Ruhe
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._start_search)

        self._generation = 0
        self._placeholder_shown = False   # "Suche …" steht in der Liste und muss beim ersten Treffer weg
        self._workers: list[SearchWorker] = []   # laufende Threads am Leben halten, bis sie fertig sind

        self.search_field.textChanged.connect(self._on_text_changed)
        self.by_name.toggled.connect(self._on_option_changed)
        self.full_text.toggled.connect(self._on_option_changed)
        self.tree.file_activated.connect(lambda path: self.open_requested.emit(path, None))
        self.results.open_requested.connect(self.open_requested)

        # Esc leert die Suche – egal ob Feld oder Trefferliste den Fokus hat
        for widget in (self.search_field, self.results):
            shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), widget)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self.clear_search)

    # ---- Öffentlich -----------------------------------------------------------
    def focus_search(self) -> None:
        self.search_field.setFocus()
        self.search_field.selectAll()

    def clear_search(self) -> None:
        self.search_field.clear()   # löst textChanged aus -> Baum wieder sichtbar
        self.tree.setFocus()

    def search_options(self) -> SearchOptions:
        return SearchOptions(
            by_name=self.by_name.isChecked(),
            full_text=self.full_text.isChecked(),
            extensions=tuple(self.config["extensions"]),
            max_bytes=int(self.config["fulltext_max_mb"]) * 1024 * 1024,
        )

    def stop_search(self) -> None:
        for worker in self._workers:
            worker.stop()

    # ---- Intern ----------------------------------------------------------------
    def _on_text_changed(self, text: str) -> None:
        if text.strip():
            self.stack.setCurrentWidget(self.results)
            self._debounce.start()
        else:
            self._debounce.stop()
            self.stop_search()
            self.results.clear_results()
            self.stack.setCurrentWidget(self.tree)

    def _on_option_changed(self) -> None:
        self.config["search"]["by_name"] = self.by_name.isChecked()
        self.config["search"]["full_text"] = self.full_text.isChecked()
        if self.search_field.text().strip():
            self._debounce.start()

    def _start_search(self) -> None:
        query = self.search_field.text().strip()
        if not query:
            return
        self.stop_search()
        self._generation += 1
        self.results.clear_results()

        options = self.search_options()
        if not (options.by_name or options.full_text):
            self.results.show_message("Keine Suchart gewählt – Dateiname und/oder Volltext ankreuzen.")
            return
        self.results.show_message("Suche …")
        self._placeholder_shown = True

        worker = SearchWorker(self._generation, self.root, query, options)
        worker.name_found.connect(self._on_name_found)
        worker.file_found.connect(self._on_file_found)
        worker.search_done.connect(self._on_search_done)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _is_current(self, generation: int) -> bool:
        return generation == self._generation

    def _both(self) -> bool:
        return self.by_name.isChecked() and self.full_text.isChecked()

    def _first_hit(self) -> None:
        if self._placeholder_shown:
            self.results.clear_results()
            self._placeholder_shown = False

    def _on_name_found(self, generation: int, match) -> None:
        if self._is_current(generation):
            self._first_hit()
            self.results.add_name_match(match, self._both())

    def _on_file_found(self, generation: int, match) -> None:
        if self._is_current(generation):
            self._first_hit()
            self.results.add_file_match(match, self._both())

    def _on_search_done(self, generation: int, result: SearchResult) -> None:
        if not self._is_current(generation) or result.cancelled:
            return
        if not result.names and not result.files:
            note = f" ({result.skipped_large} große Dateien übersprungen)" if result.skipped_large else ""
            self.results.show_message("Keine Treffer" + note)
