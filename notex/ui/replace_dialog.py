"""Suchen & Ersetzen über mehrere Dateien (Ctrl+Shift+H) mit Vorschau und Häkchen pro Zeile.

Ablauf: Suchbegriff (Abfragesprache wie in der Seitenleiste, Regex/Ganzes Wort umschaltbar) und
Ersatztext eingeben → ein Thread liest alle passenden Dateien und liefert je Datei die Zeilen
(vorher → nachher) → Häkchen setzen → „Ersetzen“ schreibt nur die angekreuzten Zeilen. Offene, geänderte
Dateien werden aus dem Editor gelesen und dort ersetzt (rückgängig machbar); alles andere wird atomar auf
die Platte geschrieben, mit dem Encoding und Zeilenende der Datei.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from notex.core import search as core_search
from notex.core.encoding import decode_bytes
from notex.core.search import Query, RegexTimeout, ReplaceLine, iter_files, parse_query, replace_query_ok
from notex.theme.tokens import SPACING
from notex.ui.widgets import Chip

DEBOUNCE_MS = 350
ROLE_PATH = Qt.ItemDataRole.UserRole + 1
ROLE_LINE = Qt.ItemDataRole.UserRole + 2


@dataclass
class FilePreview:
    path: Path
    relative: str
    lines: list[ReplaceLine]


class _Scanner(QThread):
    file_ready = Signal(int, object)      # generation, FilePreview
    done = Signal(int, str, int)          # generation, Fehlertext ("" = ok), übersprungene große Dateien

    def __init__(self, generation: int, root: Path, query: Query, replacement: str, extensions: list[str],
                 max_bytes: int, overrides: dict[Path, str]) -> None:
        super().__init__()
        self.generation, self.root, self.query, self.replacement = generation, root, query, replacement
        self.extensions, self.max_bytes, self.overrides = extensions, max_bytes, overrides
        self.cancel = threading.Event()

    def run(self) -> None:
        skipped = 0
        try:
            for path in iter_files(self.root, self.extensions):
                if self.cancel.is_set():
                    return
                relative = path.relative_to(self.root).as_posix()
                if not self.query.allows_path(relative):
                    continue
                text = self.overrides.get(path)
                if text is None:
                    try:
                        if path.stat().st_size > self.max_bytes:
                            skipped += 1
                            continue
                        text = decode_bytes(path.read_bytes()).text
                    except (OSError, UnicodeDecodeError):
                        continue
                lines = core_search.preview_replace(text, self.query, self.replacement)
                if lines:
                    self.file_ready.emit(self.generation, FilePreview(path, relative, lines))
        except RegexTimeout:
            self.done.emit(self.generation, "Regex zu langsam (Timeout) – Muster vereinfachen", skipped)
            return
        except Exception as error:  # noqa: BLE001 – z. B. kaputte Gruppenreferenz im Ersatztext
            self.done.emit(self.generation, f"Ersetzen nicht möglich: {error}", skipped)
            return
        self.done.emit(self.generation, "", skipped)


class ReplaceInFilesDialog(QDialog):
    apply_requested = Signal(object, str, object)   # Query, Ersatztext, {Path: set(Zeilen)} (object: dict mit Path-Schlüsseln lässt Qt nicht kopieren)

    def __init__(self, parent: QWidget, root: Path, config: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ersetzen in Dateien")
        self.setObjectName("ReplaceDialog")
        self.setModal(False)
        self.resize(760, 520)
        self.root, self.config = root, config
        self._generation = 0
        self._workers: list[_Scanner] = []
        self.overrides: dict[Path, str] = {}   # offene, geänderte Dateien: Text aus dem Editor
        self._query: Query | None = None

        self.find_field = QLineEdit()
        self.find_field.setPlaceholderText('Suchen …  (auch ext:md path:ordner -path:archiv "Phrase")')
        self.replace_field = QLineEdit()
        self.replace_field.setPlaceholderText("Ersetzen durch  (Regex: \\1 für Gruppen)")
        self.regex_chip = Chip(".*", "Regulärer Ausdruck")
        self.word_chip = Chip("Wort", "Nur ganze Wörter")
        self.case_chip = Chip("Aa", "Groß-/Kleinschreibung beachten")
        self.info = QLabel()
        self.info.setObjectName("SettingsNote")
        self.info.setWordWrap(True)

        self.tree = QTreeWidget()
        self.tree.setObjectName("ReplaceTree")
        self.tree.setHeaderLabels(["Zeile", "Vorher", "Nachher"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 220)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemChanged.connect(self._on_item_changed)

        self.all_button = QPushButton("Alle")
        self.none_button = QPushButton("Keine")
        self.apply_button = QPushButton("Ersetzen")
        self.apply_button.setObjectName("Primary")
        self.apply_button.setEnabled(False)
        self.close_button = QPushButton("Schließen")

        top = QHBoxLayout()
        top.setSpacing(SPACING.xs)
        top.addWidget(self.find_field, 1)
        for chip in (self.regex_chip, self.word_chip, self.case_chip):
            top.addWidget(chip)
        buttons = QHBoxLayout()
        buttons.addWidget(self.all_button)
        buttons.addWidget(self.none_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        buttons.addWidget(self.apply_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addLayout(top)
        layout.addWidget(self.replace_field)
        layout.addWidget(self.info)
        layout.addWidget(self.tree, 1)
        layout.addLayout(buttons)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self.refresh)
        for signal in (self.find_field.textChanged, self.replace_field.textChanged):
            signal.connect(lambda _t: self._debounce.start())
        for chip in (self.regex_chip, self.word_chip, self.case_chip):
            chip.toggled.connect(lambda _on: self._debounce.start())
        self.all_button.clicked.connect(lambda: self._check_all(True))
        self.none_button.clicked.connect(lambda: self._check_all(False))
        self.apply_button.clicked.connect(self._apply)
        self.close_button.clicked.connect(self.close)

    # ---- Befüllen ------------------------------------------------------------------------------
    def prefill(self, text: str, regex: bool, whole_word: bool) -> None:
        self.find_field.setText(text)
        self.regex_chip.setChecked(regex)
        self.word_chip.setChecked(whole_word)
        self.find_field.setFocus()
        self.find_field.selectAll()

    def _stop(self) -> None:
        for worker in self._workers:
            worker.cancel.set()

    def refresh(self) -> None:
        self._stop()
        self._generation += 1
        self.tree.clear()
        self.apply_button.setEnabled(False)
        self.apply_button.setText("Ersetzen")
        text = self.find_field.text()
        query = parse_query(text, self.regex_chip.isChecked(), self.word_chip.isChecked(), self.case_chip.isChecked())
        self._query = query
        self.find_field.setProperty("invalid", bool(query.error))
        self.find_field.style().unpolish(self.find_field)
        self.find_field.style().polish(self.find_field)
        if not text.strip():
            self.info.setText("Suchbegriff eingeben. Es wird nur ersetzt, was du unten ankreuzt.")
            return
        problem = replace_query_ok(query)
        if problem:
            self.info.setText(problem)
            return
        self.info.setText("Suche …")
        extensions = sorted(set(self.config.get("extensions", [])) | set(query.extensions)) if query.extensions \
            else list(self.config.get("extensions", []))
        worker = _Scanner(self._generation, self.root, query, self.replace_field.text(), extensions,
                          int(self.config.get("fulltext_max_mb", 5)) * 1024 * 1024, dict(self.overrides))
        worker.file_ready.connect(self._on_file)
        worker.done.connect(self._on_done)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _on_file(self, generation: int, preview: FilePreview) -> None:
        if generation != self._generation:
            return
        parent = QTreeWidgetItem([f"{preview.relative}  ({len(preview.lines)})", "", ""])
        parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        parent.setCheckState(0, Qt.CheckState.Checked)
        parent.setData(0, ROLE_PATH, str(preview.path))
        for line in preview.lines:
            child = QTreeWidgetItem([f"Zeile {line.line_no}", line.before.strip(), line.after.strip()])
            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            child.setCheckState(0, Qt.CheckState.Checked)
            child.setData(0, ROLE_PATH, str(preview.path))
            child.setData(0, ROLE_LINE, line.line_no)
            child.setToolTip(1, line.before)
            child.setToolTip(2, line.after)
            parent.addChild(child)
        self.tree.addTopLevelItem(parent)
        parent.setExpanded(True)
        self._update_summary()

    def _on_done(self, generation: int, error: str, skipped: int) -> None:
        if generation != self._generation:
            return
        if error:
            self.info.setText(error)
            self.find_field.setProperty("invalid", True)
            self.find_field.style().unpolish(self.find_field)
            self.find_field.style().polish(self.find_field)
            return
        self._update_summary(done=True, skipped=skipped)

    # ---- Häkchen ------------------------------------------------------------------------------
    def _on_item_changed(self, _item, _column) -> None:
        self._update_summary()

    def _check_all(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, state)

    def selection(self) -> dict[Path, set[int]]:
        result: dict[Path, set[int]] = {}
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    result.setdefault(Path(child.data(0, ROLE_PATH)), set()).add(int(child.data(0, ROLE_LINE)))
        return result

    def _update_summary(self, done: bool = False, skipped: int = 0) -> None:
        chosen = self.selection()
        lines = sum(len(v) for v in chosen.values())
        total = sum(self.tree.topLevelItem(i).childCount() for i in range(self.tree.topLevelItemCount()))
        files = self.tree.topLevelItemCount()
        self.apply_button.setEnabled(lines > 0)
        self.apply_button.setText(f"Ersetzen ({lines} Zeilen in {len(chosen)} Dateien)" if lines else "Ersetzen")
        if done and total == 0:
            self.info.setText("Keine Treffer" + (f" ({skipped} große Dateien übersprungen)" if skipped else ""))
        elif total:
            self.info.setText(f"{total} Zeilen in {files} Dateien gefunden – angekreuzte werden ersetzt"
                              + (f" · {skipped} große Dateien übersprungen" if skipped else ""))

    def _apply(self) -> None:
        if self._query is None or replace_query_ok(self._query):
            return
        chosen = self.selection()
        if not chosen:
            return
        self.apply_requested.emit(self._query, self.replace_field.text(), chosen)
        self.refresh()

    def closeEvent(self, event) -> None:
        self._stop()
        super().closeEvent(event)
