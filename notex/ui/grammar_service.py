"""Grammatikprüfung im Hintergrund: sammelt Absätze, schickt sie gebündelt an LanguageTool.

Ablauf pro Editor:
  Tippen -> 1,5 s Ruhe -> sichtbare Blöcke ohne Ergebnis werden in die Warteschlange gelegt
  -> Worker-Thread fragt den Server (mit Rate-Limit) -> Treffer landen im Highlighter.

Ist der Server nicht erreichbar, schaltet sich die Prüfung still ab, die Statusleiste
zeigt einen Hinweis, und nach einer Minute wird es einmal wieder probiert.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from notex.core.grammar import GrammarClient, GrammarUnavailable, is_public_url
from notex.ui.spell_highlighter import Issue

DEBOUNCE_MS = 1500
RETRY_MS = 60_000
MAX_BLOCKS_PER_ROUND = 12
_finishing: list[GrammarWorker] = []   # gestoppte Worker bis zum Ende am Leben halten


@dataclass
class Job:
    editor_id: int
    block_number: int
    text: str
    language: str


class GrammarWorker(QThread):
    result = Signal(object, int, str, object)   # editor_key, block_number, text, list[GrammarMatch]
    failed = Signal(str)

    def __init__(self, client: GrammarClient) -> None:
        super().__init__()
        self.client = client
        self.jobs: queue.Queue[Job | None] = queue.Queue()
        self._stop = threading.Event()

    def submit(self, job: Job) -> None:
        self.jobs.put(job)

    def stop(self) -> None:
        self._stop.set()
        self.jobs.put(None)

    def run(self) -> None:
        while not self._stop.is_set():
            job = self.jobs.get()
            if job is None or self._stop.is_set():
                break
            try:
                matches = self.client.check(job.text, job.language)
            except GrammarUnavailable as error:
                self.failed.emit(str(error))
                # Rest der Warteschlange verwerfen – der Server ist weg
                while not self.jobs.empty():
                    try:
                        self.jobs.get_nowait()
                    except queue.Empty:
                        break
                continue
            self.result.emit(job.editor_id, job.block_number, job.text, matches)


class GrammarService(QObject):
    state_changed = Signal(str)   # Hinweistext für die Statusleiste ("" = alles gut)

    def __init__(self, config: dict) -> None:
        super().__init__()
        self.config = config
        self.note = ""
        self._worker: GrammarWorker | None = None
        self._editors: dict[int, object] = {}
        self._timers: dict[int, QTimer] = {}
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(RETRY_MS)
        self._retry.timeout.connect(self._recover)

    # ---- Konfiguration ---------------------------------------------------------------
    def _client(self) -> GrammarClient:
        cfg = self.config.get("grammar", {})
        return GrammarClient(cfg.get("server_url", "http://localhost:8081"), cfg.get("allow_public", False))

    def restart(self) -> None:
        """Nach Config-Änderung: Worker mit neuem Client starten, Hinweis zurücksetzen."""
        self.shutdown()
        client = self._client()
        if is_public_url(client.server_url) and not client.allow_public:
            self._set_note("Öffentliche LanguageTool-API nicht freigegeben")
            return
        self._worker = GrammarWorker(client)
        self._worker.result.connect(self._on_result)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self._set_note("")

    def shutdown(self) -> None:
        if self._worker is not None:
            worker = self._worker
            self._worker = None
            worker.stop()
            if not worker.wait(500):
                # hängt noch in einer Anfrage (Timeout bis 8 s): Referenz halten, bis er fertig ist,
                # sonst würde Qt den laufenden Thread beim Aufräumen zerstören
                _finishing.append(worker)
                worker.finished.connect(lambda w=worker: _finishing.remove(w) if w in _finishing else None)

    def _set_note(self, note: str) -> None:
        if note != self.note:
            self.note = note
            self.state_changed.emit(note)

    # ---- Editoren --------------------------------------------------------------------
    def attach(self, editor) -> None:
        if getattr(editor, "encrypted", False):   # verschlüsselte Notizen gehen nie an LanguageTool
            return
        key = id(editor)
        self._editors[key] = editor
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(DEBOUNCE_MS)
        timer.timeout.connect(lambda k=key: self._flush(k))
        self._timers[key] = timer
        editor.document().contentsChange.connect(lambda *_a, k=key: self.schedule(k))
        editor.verticalScrollBar().valueChanged.connect(lambda _v, k=key: self.schedule(k))

    def detach(self, editor) -> None:
        key = id(editor)
        self._editors.pop(key, None)
        timer = self._timers.pop(key, None)
        if timer is not None:
            timer.stop()

    def schedule(self, key: int) -> None:
        timer = self._timers.get(key)
        if timer is not None and self._worker is not None:
            timer.start()

    def schedule_all(self) -> None:
        for key in list(self._timers):
            self.schedule(key)

    def _flush(self, key: int) -> None:
        """Sichtbare Blöcke ohne Grammatik-Ergebnis zur Prüfung einreihen."""
        editor = self._editors.get(key)
        if editor is None or self._worker is None or editor.highlighter is None or getattr(editor, "encrypted", False):
            return
        highlighter = editor.highlighter
        if not highlighter.grammar_enabled:
            return
        language = editor.language or self.config.get("spellcheck", {}).get("language", "de")
        first, last = highlighter.visible_block_range()
        block = editor.document().findBlockByNumber(first)
        submitted = 0
        while block.isValid() and block.blockNumber() <= last and submitted < MAX_BLOCKS_PER_ROUND:
            number = block.blockNumber()
            text = block.text()
            if text.strip() and number not in highlighter._grammar and not highlighter.in_code_fence(block):
                highlighter._grammar[number] = []   # Platzhalter: läuft schon
                self._worker.submit(Job(key, number, text, language))
                submitted += 1
            block = block.next()

    # ---- Ergebnisse --------------------------------------------------------------------
    def _on_result(self, editor_id, block_number: int, text: str, matches) -> None:
        editor = self._editors.get(editor_id)
        if editor is None or editor.highlighter is None:
            return
        block = editor.document().findBlockByNumber(block_number)
        if not block.isValid() or block.text() != text:
            editor.highlighter._grammar.pop(block_number, None)   # inzwischen geändert -> beim nächsten Mal
            return
        issues = []
        for match in matches:
            if "SPELLER" in match.rule or "MORFOLOGIK" in match.rule:
                continue   # Rechtschreibung übernimmt Hunspell, sonst doppelte Wellenlinie
            issues.append(Issue(match.offset, match.length, "grammar", message=match.message,
                                replacements=match.replacements, rule=match.rule))
        editor.highlighter.set_grammar_issues(block_number, issues)

    def _on_failed(self, message: str) -> None:
        self._set_note("LanguageTool nicht erreichbar")
        for editor in self._editors.values():
            if editor.highlighter is not None:
                editor.highlighter._grammar.clear()
        self._retry.start()

    def _recover(self) -> None:
        if self._worker is not None and self._client().ping():
            self._set_note("")
            self.schedule_all()
        elif self._worker is not None:
            self._retry.start()
