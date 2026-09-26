"""„Live verfolgen“: neue Zeilen einer wachsenden Datei lesen, Rotation/Kürzung erkennen, Zeilen filtern. Ohne Qt.

Tailer.poll() liest nur, was seit dem letzten Aufruf dazugekommen ist (höchstens MAX_READ pro Aufruf, der Rest
folgt beim nächsten). Unvollständige letzte Zeilen werden zurückgehalten, bis ihr Zeilenende kommt; Mehrbyte-
Zeichen an der Blockgrenze dekodiert ein inkrementeller Decoder korrekt. Wird die Datei ersetzt (Rotation: andere
Datei-ID) oder kürzer (Kürzung, `> app.log`), liefert poll() reset=True und den Inhalt neu ab Anfang.
Die Datei wird nie verändert – Filter wirken nur auf die Anzeige.
"""
from __future__ import annotations

import codecs
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_READ = 2 * 1024 * 1024          # pro poll()
INITIAL_TAIL = 8 * 1024 * 1024      # beim Start/nach Rotation höchstens die letzten 8 MB

ERROR_RE = re.compile(r"\b(?:ERROR|ERR|FATAL|CRITICAL|CRIT|SEVERE|EMERG(?:ENCY)?|ALERT|PANIC|FAIL(?:ED|URE)?)\b",
                      re.IGNORECASE)
WARN_RE = re.compile(r"\b(?:WARN(?:ING)?|WRN)\b", re.IGNORECASE)


def can_follow(path: Path | str) -> bool:
    """Live verfolgen nur für normale Dateien – nie .ntx (die Ansicht läse sonst Geheimtext als „Log“ und der
    Klartext existiert nur im entsperrten Editor)."""
    from notex.core.fileops import is_encrypted_path
    return not is_encrypted_path(path) and Path(path).is_file()


def classify(line: str) -> str | None:
    """"error", "warn" oder None – nach üblichen Level-Wörtern (ERROR, FATAL, [error], WARN, WARNING …)."""
    if ERROR_RE.search(line):
        return "error"
    if WARN_RE.search(line):
        return "warn"
    return None


@dataclass
class TailResult:
    lines: list[str] = field(default_factory=list)
    reset: bool = False          # Datei rotiert/gekürzt: bisherige Anzeige verwerfen, `lines` ist der neue Anfang
    skipped: int = 0             # beim (Neu-)Start übersprungene Bytes am Anfang (nur die letzten 8 MB gelesen)
    missing: bool = False        # Datei gerade nicht vorhanden (z. B. während der Rotation)
    more: bool = False           # es liegt noch mehr an – bald wieder poll() aufrufen


class Tailer:
    def __init__(self, path: Path | str, encoding: str = "utf-8") -> None:
        from notex.core.fileops import is_encrypted_path
        if is_encrypted_path(path):
            raise ValueError("Verschlüsselte Notizen (.ntx) lassen sich nicht live verfolgen")
        self.path = Path(path)
        self.encoding = "utf-8" if encoding in ("utf-8-sig",) else encoding
        self.position = 0
        self._file_id: tuple[int, int] | None = None
        self._decoder = codecs.getincrementaldecoder(self.encoding)(errors="replace")
        self._partial = ""

    def _identity(self, stat: os.stat_result) -> tuple[int, int]:
        return stat.st_dev, stat.st_ino

    def start(self) -> TailResult:
        """Von vorn (bzw. die letzten 8 MB) lesen und ab dem Ende weiter verfolgen."""
        try:
            stat = self.path.stat()
        except OSError:
            return TailResult(missing=True)
        self._file_id = self._identity(stat)
        self._decoder.reset()
        self._partial = ""
        skipped = max(0, stat.st_size - INITIAL_TAIL)
        self.position = skipped
        result = self._read(stat.st_size, limit=INITIAL_TAIL, flush=False)
        if skipped and result.lines:
            result.lines = result.lines[1:]          # erste Zeile ist vermutlich angeschnitten
        result.skipped = skipped
        result.reset = True
        return result

    def poll(self) -> TailResult:
        try:
            stat = self.path.stat()
        except OSError:
            return TailResult(missing=True)
        if self._file_id is None or self._identity(stat) != self._file_id or stat.st_size < self.position:
            return self.start()                       # rotiert (neue Datei) oder gekürzt
        if stat.st_size == self.position:
            return TailResult()
        return self._read(stat.st_size, limit=MAX_READ, flush=False)

    def _read(self, size: int, limit: int, flush: bool) -> TailResult:
        length = min(size - self.position, limit)
        try:
            with open(self.path, "rb") as handle:
                handle.seek(self.position)
                data = handle.read(length)
        except OSError:
            return TailResult(missing=True)
        self.position += len(data)
        if self.position == len(data) and data.startswith(codecs.BOM_UTF8):
            data = data[len(codecs.BOM_UTF8):]
        text = self._partial + self._decoder.decode(data, final=flush)
        text = text.replace("\r\n", "\n")
        if text.endswith("\r"):                        # \r\n über die Blockgrenze
            text, carry = text[:-1], "\r"
        else:
            carry = ""
        parts = text.replace("\r", "\n").split("\n")
        self._partial = parts.pop() + carry            # angefangene Zeile bis zum nächsten Zeilenende halten
        return TailResult(lines=parts, more=self.position < size)

    @property
    def partial(self) -> str:
        """Angefangene letzte Zeile (noch ohne Zeilenende) – zur Anzeige, nicht verbraucht."""
        return self._partial.rstrip("\r")


# ---- Filter ------------------------------------------------------------------------------------
@dataclass
class LogFilter:
    level: str = "all"            # "all" | "warn" (WARN und schlimmer) | "error"
    text: str = ""
    regex: bool = False
    case_sensitive: bool = False
    error: str | None = None
    _needle: object = None

    def __post_init__(self) -> None:
        self.compile()

    def compile(self) -> None:
        from notex.core.search import _compile
        self.error = None
        self._needle = None
        if not self.text:
            return
        flags = 0 if self.case_sensitive else re.IGNORECASE
        pattern = self.text if self.regex else re.escape(self.text)
        try:
            self._needle = _compile(pattern, flags)
        except Exception as error:  # noqa: BLE001 – re.error und regex.error
            self.error = f"Ungültige Regex: {error}"

    @property
    def active(self) -> bool:
        return self.level != "all" or self._needle is not None

    def matches(self, line: str) -> bool:
        if self.level != "all":
            level = classify(line)
            if level is None or (self.level == "error" and level != "error"):
                return False
        if self._needle is None:
            return True                  # kein Text bzw. ungültige Regex: Textfilter wirkt nicht (Feld zeigt Fehler)
        try:
            from notex.core.search import MATCH_TIMEOUT, _regex
            if _regex is not None:
                return self._needle.search(line, timeout=MATCH_TIMEOUT) is not None
            return self._needle.search(line) is not None
        except TimeoutError:
            return False

    def apply(self, lines: list[str]) -> list[str]:
        if not self.active:
            return list(lines)
        return [line for line in lines if self.matches(line)]
