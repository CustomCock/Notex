"""Allgemeine Log-Auswertung – für beliebige Logs (App-, Installations-, Dienst-Logs …), nicht nur Anmelde-Logs.

Ohne Qt, gestreamt. Jede Zeile wird in Zeitstempel (über core.timeline.detect_timestamp), Stufe (ERROR/WARN/…),
Quelle/Komponente und Nachricht zerlegt. `analyze_generic` baut daraus eine Übersicht: Stufen-Verteilung, Fehler und
Warnungen, häufigste Meldungen (zu Mustern verdichtet), aktivste Quellen, Zeitspanne und Stunden-Zeitleiste.

Beispiele, die damit funktionieren: setupact.log (Windows-Setup), dpkg/apt, pip, Nginx/Apache, journalctl-Auszüge,
Anwendungs-Logs mit „2024-01-01 12:00:00 ERROR …", MailStore-Server-Logs u. Ä.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from notex.core.timeline import detect_timestamp

MAX_EVENTS = 1_000_000

# Stufen auf einen einheitlichen Schlüssel abbilden (Deutsch und Englisch, gängige Kürzel).
LEVEL_CANON: dict[str, str] = {
    "emerg": "critical", "emergency": "critical", "alert": "critical", "fatal": "critical", "crit": "critical",
    "critical": "critical", "panic": "critical",
    "error": "error", "err": "error", "fail": "error", "failed": "error", "failure": "error", "fehler": "error",
    "severe": "error",
    "warn": "warning", "warning": "warning", "warnung": "warning", "wrn": "warning",
    "notice": "info", "info": "info", "information": "info", "informational": "info", "hinweis": "info",
    "debug": "debug", "dbg": "debug", "trace": "debug", "verbose": "debug", "fine": "debug", "finer": "debug",
}
LEVEL_ORDER = ["critical", "error", "warning", "info", "debug", "other"]
LEVEL_LABELS = {"critical": "Kritisch", "error": "Fehler", "warning": "Warnung", "info": "Info",
                "debug": "Debug/Trace", "other": "Ohne Stufe"}

# Ein Stufen-Wort am Zeilenanfang (nach Zeitstempel), auch in [..] oder mit Doppelpunkt.
_LEVEL_WORDS = "|".join(sorted(LEVEL_CANON, key=len, reverse=True))
_LEVEL_RE = re.compile(r"(?<![A-Za-z])(?P<lvl>" + _LEVEL_WORDS + r")(?![A-Za-z])", re.IGNORECASE)
# Quelle/Komponente: [name] oder name[pid] oder logger.name am Anfang des Rests.
_BRACKET_SRC = re.compile(r"\[(?P<src>[^\]\[]{1,48})\]")
_PROG_SRC = re.compile(r"(?P<src>[\w.\-/]{1,48})\[\d+\]")   # prog[pid], auch nach einem Hostnamen (syslog)
_LEADING_SRC = re.compile(r"^(?P<src>[A-Za-z][\w.\-]{1,40}):\s")
# Für die Nachrichten-Bereinigung: führende Stufe bzw. führende Komponente abtrennen.
_LEAD_LEVEL_RE = re.compile(r"^\s*\[?(?:" + _LEVEL_WORDS + r")\]?\s*[:,\-|)\]]*\s*", re.IGNORECASE)
_LEAD_BRACKET_RE = re.compile(r"^\s*\[[^\]]*\]\s*")
_LEAD_COMPONENT_RE = re.compile(r"^(?P<src>[A-Za-z][\w.\-]{1,20})(?:\s{2,}|:\s+)")

# Verdichtung: Zahlen, Hex, IPs, UUIDs, Pfade, Anführungszeichen → Platzhalter, um ähnliche Meldungen zu gruppieren.
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-fA-F]{16,}\b")
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_WINPATH = re.compile(r"[A-Za-z]:\\[^\s,;]+")
_UNIXPATH = re.compile(r"(?<!\w)/[^\s,;:]{2,}")
_NUM = re.compile(r"\b\d[\d.,:]*\b")
_QUOTED = re.compile(r"([\"'`])(?:(?!\1).){0,120}\1")


@dataclass
class GenericEvent:
    time: datetime | None
    level: str                  # kanonischer Schlüssel (critical/error/warning/info/debug/other)
    source: str
    message: str
    line: int = -1
    raw: str = ""


def detect_level(text: str) -> str:
    """Erste erkannte Stufe in den ersten ~48 Zeichen; „other", wenn keine gefunden."""
    head = text[:48]
    match = _LEVEL_RE.search(head)
    if match:
        return LEVEL_CANON.get(match.group("lvl").lower(), "other")
    return "other"


def detect_source(text: str) -> str:
    """Komponente/Quelle aus dem Zeilenrest (best effort): [name], name[pid] oder „name:"."""
    m = _PROG_SRC.search(text[:80])
    if m and not m.group("src").isdigit():
        return m.group("src")
    m = _BRACKET_SRC.search(text[:80])
    if m and not m.group("src").strip().isdigit():
        return m.group("src").strip()
    m = _LEADING_SRC.match(text)
    if m and detect_level(m.group("src")) == "other":     # nicht die Stufe als Quelle missdeuten
        return m.group("src")
    return ""


def template(message: str, max_len: int = 120) -> str:
    """Meldung zu einem Muster verdichten (Zahlen/Pfade/IDs → Platzhalter), um Häufungen zu erkennen."""
    text = message.strip()
    text = _UUID.sub("<id>", text)
    text = _QUOTED.sub("<q>", text)
    text = _WINPATH.sub("<pfad>", text)
    text = _UNIXPATH.sub("<pfad>", text)
    text = _IP.sub("<ip>", text)
    text = _HEX.sub("<hex>", text)
    text = _NUM.sub("<n>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def parse_line(line: str, number: int = -1, year: int | None = None) -> GenericEvent | None:
    """Eine Log-Zeile zerlegen. Leerzeilen → None."""
    raw = line.rstrip("\n").rstrip("\r")
    stripped = raw.strip()
    if not stripped:
        return None
    ts = detect_timestamp(raw, year=year)
    when = ts[0] if ts else None
    rest = raw
    if ts:
        # Text nach dem Zeitstempel als Nachrichtenbeginn nehmen
        idx = raw.find(ts[1])
        if idx >= 0:
            rest = raw[idx + len(ts[1]):]
    rest = rest.strip(" \t-:,|")
    level = detect_level(rest if ts else raw)
    source = detect_source(rest)
    message = rest
    # Nachricht aufräumen: führende [Quelle], Stufe und kurze Komponente abtrennen, damit die Spalten sauber sind.
    if source and message.lstrip().startswith("["):
        message = _LEAD_BRACKET_RE.sub("", message, count=1)
    m = _LEAD_LEVEL_RE.match(message)
    if m and m.end() < len(message):
        message = message[m.end():]
    if not source:
        cm = _LEAD_COMPONENT_RE.match(message)
        if cm:
            source = cm.group("src")
            message = message[cm.end():]
    return GenericEvent(when, level, source, message.strip(), number, raw)


def _open_text(path: Path):
    import gzip
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def read_generic(path: Path, progress: Callable[[int, int], None] | None = None,
                 cancelled: Callable[[], bool] | None = None, year: int | None = None) -> Iterator[GenericEvent]:
    path = Path(path)
    total = path.stat().st_size or 1
    is_gz = path.suffix.lower() == ".gz"
    with _open_text(path) as handle:
        for number, line in enumerate(handle):
            if cancelled and number % 500 == 0 and cancelled():
                return
            event = parse_line(line, number, year)
            if event is not None:
                yield event
            if progress and number % 2000 == 0:
                if is_gz:
                    progress(number, number + 1)
                else:
                    pos = handle.buffer.tell() if hasattr(handle, "buffer") else number
                    progress(min(pos, total), total)


def collect_generic(path: Path, limit: int = MAX_EVENTS, **kwargs) -> tuple[list[GenericEvent], bool]:
    events: list[GenericEvent] = []
    for event in read_generic(path, **kwargs):
        events.append(event)
        if len(events) >= limit:
            return events, True
    return events, False


@dataclass
class GenericSummary:
    total: int = 0
    with_time: int = 0
    by_level: dict[str, int] = field(default_factory=dict)
    first_time: datetime | None = None
    last_time: datetime | None = None
    errors: list[GenericEvent] = field(default_factory=list)       # kritische + Fehler (Auszug)
    warnings: list[GenericEvent] = field(default_factory=list)
    top_sources: list[tuple[str, int]] = field(default_factory=list)
    top_messages: list[tuple[str, int]] = field(default_factory=list)   # verdichtete Muster
    top_error_messages: list[tuple[str, int]] = field(default_factory=list)
    timeline: list[tuple[datetime, int, int]] = field(default_factory=list)   # (Stunde, Fehler+Kritisch, Warnungen)

    @property
    def error_count(self) -> int:
        return self.by_level.get("critical", 0) + self.by_level.get("error", 0)

    @property
    def warning_count(self) -> int:
        return self.by_level.get("warning", 0)


def analyze_generic(events: list[GenericEvent], sample: int = 200) -> GenericSummary:
    summary = GenericSummary(total=len(events))
    by_level: Counter = Counter()
    sources: Counter = Counter()
    messages: Counter = Counter()
    error_messages: Counter = Counter()
    per_hour_err: Counter = Counter()
    per_hour_warn: Counter = Counter()
    for event in events:
        by_level[event.level] += 1
        if event.source:
            sources[event.source] += 1
        if event.message:
            messages[template(event.message)] += 1
        if event.time:
            summary.with_time += 1
            if summary.first_time is None or event.time < summary.first_time:
                summary.first_time = event.time
            if summary.last_time is None or event.time > summary.last_time:
                summary.last_time = event.time
            hour = event.time.replace(minute=0, second=0, microsecond=0)
        else:
            hour = None
        if event.level in ("critical", "error"):
            if len(summary.errors) < sample:
                summary.errors.append(event)
            if event.message:
                error_messages[template(event.message)] += 1
            if hour:
                per_hour_err[hour] += 1
        elif event.level == "warning":
            if len(summary.warnings) < sample:
                summary.warnings.append(event)
            if hour:
                per_hour_warn[hour] += 1
    summary.by_level = {level: by_level[level] for level in LEVEL_ORDER if by_level.get(level)}
    summary.top_sources = sources.most_common(20)
    summary.top_messages = messages.most_common(20)
    summary.top_error_messages = error_messages.most_common(20)
    hours = sorted(set(per_hour_err) | set(per_hour_warn))
    summary.timeline = [(h, per_hour_err.get(h, 0), per_hour_warn.get(h, 0)) for h in hours]
    return summary


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(summary: GenericSummary, source: str) -> str:
    lines = [f"# Log-Auswertung (allgemein): {_cell(source)}", "",
             f"- Zeilen mit Inhalt: {summary.total}", f"- davon mit Zeitstempel: {summary.with_time}"]
    if summary.first_time and summary.last_time:
        lines.append(f"- Zeitraum: {summary.first_time} – {summary.last_time}")
    lines.append("")
    if summary.by_level:
        lines += ["## Stufen", "", "| Stufe | Anzahl |", "|---|---|"]
        lines += [f"| {LEVEL_LABELS.get(k, k)} | {v} |" for k, v in summary.by_level.items()] + [""]
    if summary.top_error_messages:
        lines += ["## Häufigste Fehler (Muster)", "", "| Anzahl | Muster |", "|---|---|"]
        lines += [f"| {count} | {_cell(pat)} |" for pat, count in summary.top_error_messages[:15]] + [""]
    if summary.errors:
        lines += ["## Fehler (Auszug)", ""]
        lines += [f"- {(e.time or '?')}: {_cell(e.message)[:200]}" for e in summary.errors[:60]] + [""]
    if summary.top_sources:
        lines += ["## Aktivste Quellen", "", "| Quelle | Zeilen |", "|---|---|"]
        lines += [f"| {_cell(src)} | {count} |" for src, count in summary.top_sources[:15]] + [""]
    if summary.top_messages:
        lines += ["## Häufigste Meldungen (Muster)", "", "| Anzahl | Muster |", "|---|---|"]
        lines += [f"| {count} | {_cell(pat)} |" for pat, count in summary.top_messages[:15]] + [""]
    return "\n".join(lines)
