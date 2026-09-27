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
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from notex.core.search import SearchOptions, SearchResult, parse_query
from notex.ui.file_tree import FileTree
from notex.ui.open_files import OpenFilesSection
from notex.ui.places_panel import PlacesPanel
from notex.ui.search_results import SearchResults
from notex.ui.search_worker import SearchWorker
from notex.ui.widgets import Chip, IconButton, SearchField
from notex.theme.icons import icon
from notex.theme.tokens import SPACING

DEBOUNCE_MS = 250


class Sidebar(QWidget):
    open_requested = Signal(Path, object)   # Pfad, (line, column, length) oder None
    settings_requested = Signal()

    def __init__(self, root: Path, config: dict[str, Any]) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.root = root
        self.config = config

        self.search_field = SearchField("Suchen …")
        self.search_field.setToolTip("Suche in Dateien  Ctrl+Shift+F\n\n"
                                     "Mehrere Wörter: alle müssen in der Zeile vorkommen\n"
                                     '"genaue Phrase"  ·  ext:md,txt  ·  path:ordner  ·  -path:archiv')

        self.by_name = Chip("Name", "Dateinamen durchsuchen")
        self.full_text = Chip("Volltext", "Inhalte durchsuchen")
        self.regex = Chip(".*", "Regulärer Ausdruck (Python-Syntax, Groß/Klein egal)")
        self.whole_word = Chip("Wort", "Nur ganze Wörter")
        self.in_values = Chip("§", "Auch in Variablenwerten suchen (Modul Variablen)")
        self.in_values.setChecked(bool(config["search"].get("variable_values", False)))
        self.in_values.setVisible(False)       # nur sichtbar, solange das Modul Variablen an ist
        self.variable_source = None            # Callable[[], VariableService | None] – setzt das Modul
        self.by_name.setChecked(config["search"]["by_name"])
        self.full_text.setChecked(config["search"]["full_text"])
        self.regex.setChecked(bool(config["search"].get("regex", False)))
        self.whole_word.setChecked(bool(config["search"].get("whole_word", False)))
        self.results_info = QLabel()
        self.results_info.setObjectName("ResultsInfo")
        self.results_info.hide()
        checks = QHBoxLayout()
        checks.setContentsMargins(0, 0, 0, 0)
        checks.setSpacing(SPACING.xs)
        checks.addWidget(self.by_name)
        checks.addWidget(self.full_text)
        checks.addWidget(self.regex)
        checks.addWidget(self.whole_word)
        checks.addWidget(self.in_values)
        checks.addStretch()

        self.open_files = OpenFilesSection()
        self.tree = FileTree(root, config["extensions"], show_hidden=bool(config.get("tree_show_hidden", False)))
        self.places = PlacesPanel(root, config)

        # Orte oben, Datei-Baum darunter – über einen Splitter in der Höhe verstellbar
        self.explorer = QSplitter(Qt.Orientation.Vertical)
        self.explorer.setObjectName("ExplorerSplitter")
        self.explorer.setChildrenCollapsible(False)
        self.explorer.setHandleWidth(6)
        self.explorer.addWidget(self.places)
        self.explorer.addWidget(self.tree)
        self.explorer.setStretchFactor(0, 0)
        self.explorer.setStretchFactor(1, 1)
        self.explorer.setSizes([150, 500])

        self.results = SearchResults()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.explorer)
        self.stack.addWidget(self.results)

        # Orte ↔ Baum verbinden
        self.places.place_selected.connect(self._on_place_selected)
        self.tree.root_changed.connect(self.places.set_current_path)
        self.places.set_current_path(root)

        # Fußzeile mit Zahnrad
        self.settings_button = IconButton("settings", "Einstellungen  Ctrl+,")
        self.settings_button.clicked.connect(self.settings_requested)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self.settings_button)
        footer.addStretch(1)
        self._footer = footer

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.xs)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.search_field)
        layout.addLayout(checks)
        layout.addWidget(self.results_info)   # eigene Zeile: bei schmaler Seitenleiste bleiben die Chips lesbar
        layout.addWidget(self.open_files)
        layout.addWidget(self.stack, 1)
        layout.addLayout(footer)
        self._layout = layout
        self._checks = checks

        # Debounce: Timer wird bei jedem Tastendruck neu gestartet, sucht erst bei Ruhe
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._start_search)

        self._generation = 0
        self._placeholder_shown = False   # "Suche …" steht in der Liste und muss beim ersten Treffer weg
        self._workers: list[SearchWorker] = []   # laufende Threads am Leben halten, bis sie fertig sind

        self.search_field.textChanged.connect(self._on_text_changed)
        for chip in (self.by_name, self.full_text, self.regex, self.whole_word, self.in_values):
            chip.toggled.connect(self._on_option_changed)
        self.tree.file_activated.connect(lambda path: self.open_requested.emit(path, None))
        self.results.open_requested.connect(self.open_requested)

        # Schnellzugriff anheften/entfernen und versteckte Dateien schalten (Config wird per Autosave gesichert)
        self.tree.pin_requested.connect(self._pin_folder)
        self.places.pin_removed.connect(self._unpin_folder)
        self.tree.show_hidden_toggled.connect(self._set_show_hidden)

        # Esc leert die Suche – egal ob Feld oder Trefferliste den Fokus hat
        for widget in (self.search_field.input, self.results):
            shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), widget)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self.clear_search)

    # ---- Orte / Schnellzugriff -------------------------------------------------
    def _on_place_selected(self, path: Path) -> None:
        if self.search_field.text().strip():        # aus der Suche zurück zum Baum
            self.clear_search()
        self.tree.set_root(path)
        self.places.set_current_path(path)

    def _pin_folder(self, path: Path) -> None:
        from notex.core import places
        if places.add_pinned(self.config, path):
            self.places.refresh()
            self.places.set_current_path(self.tree.root)

    def _unpin_folder(self, path: Path) -> None:
        from notex.core import places
        if places.remove_pinned(self.config, path):
            self.places.refresh()
            self.places.set_current_path(self.tree.root)

    def _set_show_hidden(self, show: bool) -> None:
        self.config["tree_show_hidden"] = bool(show)
        self.tree.set_hidden(show)

    # ---- Öffentlich -----------------------------------------------------------
    def retheme(self) -> None:
        self._layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.xs)
        self._layout.setSpacing(SPACING.sm)
        self._checks.setSpacing(SPACING.xs)
        self.search_field.retheme()
        self.settings_button.setIcon(icon("settings"))
        self.tree.retheme()
        self.places.retheme()
        self.results.viewport().update()

    def focus_search(self) -> None:
        self.search_field.setFocus()
        self.search_field.selectAll()

    def clear_search(self) -> None:
        self.search_field.clear()   # löst textChanged aus -> Baum wieder sichtbar
        self._set_invalid(False)
        self.tree.setFocus()

    def search_options(self) -> SearchOptions:
        service = self.variable_source() if self.variable_source is not None else None
        use_values = service is not None and self.in_values.isChecked()
        return SearchOptions(
            variable_values=dict(service.values) if use_values else None,
            variable_prefix=service.prefix if service is not None else "§",
            by_name=self.by_name.isChecked(),
            full_text=self.full_text.isChecked(),
            extensions=tuple(self.config["extensions"]),
            max_bytes=int(self.config["fulltext_max_mb"]) * 1024 * 1024,
            regex=self.regex.isChecked(),
            whole_word=self.whole_word.isChecked(),
        )

    def _set_invalid(self, invalid: bool, reason: str = "") -> None:
        """Roter Rahmen am Suchfeld bei ungültiger Regex oder Timeout."""
        if self.search_field.property("invalid") != invalid:
            self.search_field.setProperty("invalid", invalid)
            self.search_field.style().unpolish(self.search_field)
            self.search_field.style().polish(self.search_field)
        self.search_field.input.setToolTip(reason)

    def stop_search(self) -> None:
        for worker in self._workers:
            worker.stop()

    # ---- Intern ----------------------------------------------------------------
    def _on_text_changed(self, text: str) -> None:
        if text.strip():
            self.stack.setCurrentWidget(self.results)
            self.results_info.show()
            self._debounce.start()
        else:
            self._debounce.stop()
            self.stop_search()
            self.results.clear_results()
            self.results_info.hide()
            self.stack.setCurrentWidget(self.tree)

    def _on_option_changed(self) -> None:
        self.config["search"]["by_name"] = self.by_name.isChecked()
        self.config["search"]["full_text"] = self.full_text.isChecked()
        self.config["search"]["regex"] = self.regex.isChecked()
        self.config["search"]["whole_word"] = self.whole_word.isChecked()
        self.config["search"]["variable_values"] = self.in_values.isChecked()
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
        parsed = parse_query(query, options.regex, options.whole_word)
        if parsed.error:
            self._set_invalid(True, parsed.error)
            self.results.show_message(parsed.error)
            self.results_info.setText("Ungültig")
            return
        self._set_invalid(False)
        if not parsed.needles:
            self.results.show_message("Nur Filter angegeben – dazu noch einen Suchbegriff eingeben.")
            self.results_info.setText("")
            return
        self.results.show_message("Suche …")
        self.results_info.setText("Suche …")
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
        if result.error:
            self._set_invalid(True, result.error)
            self.results.show_message(result.error)
            self.results_info.setText("Timeout" if result.timed_out else "Ungültig")
            return
        hits = len(result.names) + sum(len(f.lines) for f in result.files)
        files = len({m.path for m in result.names} | {f.path for f in result.files})
        self.results_info.setText(f"{hits} Treffer in {files} Dateien" if hits else "Keine Treffer")
        if not hits:
            note = f" ({result.skipped_large} große Dateien übersprungen)" if result.skipped_large else ""
            self.results.show_message("Keine Treffer" + note)
