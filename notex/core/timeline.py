"""Zeitleisten-Notizen und Beweismittel-Tabellen. Ohne Qt.

Format (Entscheidung, siehe PROGRESS.md): normale Markdown-Datei mit Frontmatter-Marker und einer Tabelle –
lesbar in jeder Markdown-Ansicht (auch in der Vorschau), diffbar im Verlauf und von Hand editierbar:

    ---
    notex: zeitleiste
    titel: Vorfall Webserver
    ---
    # Zeitleiste: Vorfall Webserver

    | Zeit | Quelle | Beschreibung | Tags |
    |---|---|---|---|
    | 2026-09-26T14:03:11+02:00 | auth.log | Fehlgeschlagener Login root von 203.0.113.5 | #ssh #bruteforce |

Zeiten stehen als ISO 8601 mit Offset in der Datei (eindeutig, sortierbar). Ohne Offset gilt die Systemzeitzone.
Bewusst keine IANA-Namen (Europe/Berlin): Windows-Python hat ohne das Paket tzdata keine Zonendatenbank.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKER = "zeitleiste"
HEADER = ["Zeit", "Quelle", "Beschreibung", "Tags"]
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                           "nov", "dec"])}
MONTHS.update({"mär": 3, "mai": 5, "okt": 10, "dez": 12})


@dataclass
class Entry:
    time: datetime                     # immer mit Zeitzone
    source: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    line: int = -1                     # 0-basierte Zeile in der Datei (-1 = neu)

    def row(self) -> str:
        cells = [iso(self.time), self.source, self.description, " ".join(self.tags)]
        return "| " + " | ".join(escape_cell(c) for c in cells) + " |"


# ---- Zellen und Zeiten --------------------------------------------------------------------------------------------
def escape_cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def split_row(line: str) -> list[str] | None:
    """„| a | b \\| c |“ → ["a", "b | c"]; None, wenn keine Tabellenzeile."""
    text = line.strip()
    if not text.startswith("|"):
        return None
    cells, current, i = [], [], 1
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text) and text[i + 1] in "|\\":
            current.append(text[i + 1])
            i += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        i += 1
    if "".join(current).strip():
        cells.append("".join(current).strip())
    return cells


def local_tz() -> timezone:
    offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    return timezone(offset)


def iso(dt: datetime) -> str:
    text = dt.isoformat(timespec="milliseconds" if dt.microsecond else "seconds")
    return text.replace("+00:00", "Z") if dt.utcoffset() == timedelta(0) else text


def parse_iso(text: str, default_tz=None) -> datetime | None:
    text = text.strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        found = detect_timestamp(text)
        return found[0] if found else None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz or local_tz())
    return dt


def display(dt: datetime, mode: str = "utc") -> str:
    """mode "utc" → 2026-09-26 12:03:11 UTC, "local" → Systemzeit mit Offset, "original" → wie gespeichert."""
    if mode == "utc":
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + " UTC"
    if mode == "local":
        dt = dt.astimezone()
    offset = dt.strftime("%z")
    return dt.strftime("%Y-%m-%d %H:%M:%S") + (f" {offset[:3]}:{offset[3:]}" if offset else "")


# ---- Zeitstempel in beliebigen Zeilen erkennen --------------------------------------------------------------------
_TZ = r"(?P<tz>Z|[+-]\d{2}:?\d{2}|\s?UTC|\s?GMT)?"
PATTERNS = [
    # ISO 8601 / RFC 3339 / RFC 5424, auch mit Leerzeichen statt T
    ("iso", re.compile(r"(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})[T ](?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})"
                       r"(?P<f>[.,]\d{1,9})?" + _TZ)),
    # Apache/nginx: [26/Sep/2026:14:03:11 +0200]
    ("clf", re.compile(r"(?P<d>\d{2})/(?P<mon>[A-Za-z]{3})/(?P<y>\d{4}):(?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})"
                       r"\s(?P<tz>[+-]\d{4})")),
    # Deutsch: 26.09.2026 14:03(:11)
    ("de", re.compile(r"(?<!\d)(?P<d>\d{1,2})\.(?P<mo>\d{1,2})\.(?P<y>\d{4}),?\s+(?P<h>\d{1,2}):(?P<mi>\d{2})"
                      r"(?::(?P<s>\d{2}))?" + _TZ)),
    # US/Windows: 9/26/2026 2:03:11 PM
    ("us", re.compile(r"(?<!\d)(?P<mo>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4}),?\s+(?P<h>\d{1,2}):(?P<mi>\d{2})"
                      r"(?::(?P<s>\d{2}))?\s*(?P<ampm>[AaPp][Mm])?")),
    # syslog (ohne Jahr): Sep 26 14:03:11
    ("syslog", re.compile(r"(?<![\w/])(?P<mon>[A-Z][a-z]{2})\s+(?P<d>\d{1,2})\s+(?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})")),
    # nur Datum
    ("date", re.compile(r"(?<![\d.-])(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})(?![\d:T])")),
    # Unix-Zeit am Zeilenanfang (auch mit Millisekunden), 2001–2100
    ("epoch", re.compile(r"^\s*(?P<epoch>\d{10})(?:[.,](?P<ms>\d{1,6}))?(?!\d)")),
]


def _tzinfo(text: str | None, default):
    if not text:
        return default
    text = text.strip().upper()
    if text in ("Z", "UTC", "GMT"):
        return timezone.utc
    sign = -1 if text[0] == "-" else 1
    digits = text[1:].replace(":", "")
    return timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0)))


def detect_timestamp(line: str, year: int | None = None, default_tz=None) -> tuple[datetime, str] | None:
    """Erster erkannter Zeitstempel einer Zeile → (datetime mit Zone, gefundener Text). Ohne Zone: Systemzeit
    (bzw. default_tz); syslog ohne Jahr: `year` bzw. aktuelles Jahr."""
    default_tz = default_tz or local_tz()
    best = None
    for kind, pattern in PATTERNS:
        match = pattern.search(line)
        if not match or (best is not None and match.start() >= best[0].start()):
            continue
        best = (match, kind)
    if best is None:
        return None
    match, kind = best
    g = match.groupdict()
    try:
        if kind == "epoch":
            value = int(g["epoch"])
            if not 978307200 <= value <= 4102444800:
                return None
            ms = int((g["ms"] or "0").ljust(6, "0")[:6])
            return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=ms), match.group()
        month = int(g["mo"]) if g.get("mo") else MONTHS.get((g.get("mon") or "").lower()[:3])
        if not month:
            return None
        y = int(g["y"]) if g.get("y") else (year or datetime.now().year)
        hour = int(g.get("h") or 0)
        ampm = (g.get("ampm") or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        micro = int((g.get("f") or ".0")[1:].ljust(6, "0")[:6]) if g.get("f") else 0
        dt = datetime(y, month, int(g["d"]), hour, int(g.get("mi") or 0), int(g.get("s") or 0), micro,
                      tzinfo=_tzinfo(g.get("tz"), default_tz))
    except (ValueError, TypeError):
        return None
    return dt, match.group().strip()


# ---- Zeitleisten-Datei --------------------------------------------------------------------------------------------
@dataclass
class Timeline:
    meta: dict[str, str]
    entries: list[Entry]
    header_line: int = -1              # Zeile der Kopfzeile der Tabelle (-1 = keine Tabelle)
    last_row_line: int = -1            # letzte Tabellenzeile

    @property
    def sources(self) -> list[str]:
        return sorted({e.source for e in self.entries if e.source}, key=str.lower)

    @property
    def tags(self) -> list[str]:
        return sorted({t for e in self.entries for t in e.tags}, key=str.lower)


def frontmatter(text: str) -> tuple[dict[str, str], int]:
    """Einfaches Frontmatter (key: value) → (dict, Zeile nach dem schließenden ---) bzw. ({}, 0)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta = {}
    for index, line in enumerate(lines[1:60], start=1):
        if line.strip() == "---":
            return meta, index + 1
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip().strip('"\'')
    return {}, 0


def is_timeline(text: str) -> bool:
    return frontmatter(text[:4000])[0].get("notex", "").lower() == MARKER


def parse(text: str) -> Timeline:
    meta, start = frontmatter(text)
    lines = text.split("\n")
    entries: list[Entry] = []
    header, last = -1, -1
    columns: dict[str, int] = {}
    for index in range(start, len(lines)):
        cells = split_row(lines[index])
        if cells is None:
            if header >= 0 and last >= 0:
                break                               # Tabelle zu Ende
            continue
        if header < 0:
            names = [c.lower() for c in cells]
            if "zeit" in names:
                header, last = index, index
                columns = {name: names.index(name) for name in ("zeit", "quelle", "beschreibung", "tags") if name in names}
            continue
        last = index
        if all(set(c) <= set("-: ") for c in cells):
            continue                                # Trennzeile |---|
        def cell(name: str) -> str:
            pos = columns.get(name)
            return cells[pos] if pos is not None and pos < len(cells) else ""
        when = parse_iso(cell("zeit"))
        if when is None:
            continue
        tags = [t if t.startswith("#") else f"#{t}" for t in re.split(r"[\s,]+", cell("tags")) if t.strip("#")]
        entries.append(Entry(when, cell("quelle"), cell("beschreibung"), tags, index))
    entries.sort(key=lambda e: e.time)
    return Timeline(meta, entries, header, last)


def new_text(title: str) -> str:
    return (f"---\nnotex: {MARKER}\ntitel: {title}\n---\n# Zeitleiste: {title}\n\n"
            "| Zeit | Quelle | Beschreibung | Tags |\n|---|---|---|---|\n")


def add_entry(text: str, entry: Entry) -> tuple[str, int]:
    """Eintrag chronologisch in die Tabelle einfügen (fehlt sie, wird sie angehängt). → (neuer Text, Zeile)."""
    timeline = parse(text)
    lines = text.split("\n")
    if timeline.header_line < 0:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + ["| Zeit | Quelle | Beschreibung | Tags |", "|---|---|---|---|", entry.row(), ""]
        return "\n".join(lines), len(lines) - 2
    position = timeline.last_row_line + 1
    for existing in sorted(timeline.entries, key=lambda e: e.line):
        if existing.time > entry.time:
            position = existing.line
            break
    lines.insert(position, entry.row())
    return "\n".join(lines), position


def filter_entries(entries: list[Entry], source: str = "", tag: str = "", text: str = "") -> list[Entry]:
    needle = text.lower()
    return [e for e in entries
            if (not source or e.source == source) and (not tag or tag in e.tags)
            and (not needle or needle in e.description.lower() or needle in e.source.lower())]


def to_markdown(entries: list[Entry], mode: str = "utc") -> str:
    lines = ["| Zeit | Quelle | Beschreibung | Tags |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(escape_cell(c) for c in (display(e.time, mode), e.source, e.description,
                                                           " ".join(e.tags))) + " |" for e in entries]
    return "\n".join(lines) + "\n"


def to_csv(entries: list[Entry], mode: str = "utc") -> str:
    """CSV (Komma, UTF-8): Zeit ISO 8601 (UTC bzw. lokal mit Offset), Quelle, Beschreibung, Tags."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    for e in entries:
        when = e.time.astimezone(timezone.utc) if mode == "utc" else (e.time.astimezone() if mode == "local" else e.time)
        writer.writerow([iso(when), e.source, e.description, " ".join(e.tags)])
    return out.getvalue()


def entry_from_line(line: str, source: str, year: int | None = None) -> Entry:
    """Vorschlag für „Zur Zeitleiste hinzufügen“: Zeitstempel erkennen, Rest als Beschreibung."""
    found = detect_timestamp(line, year)
    if found is None:
        return Entry(datetime.now().astimezone().replace(microsecond=0), source, line.strip())
    when, matched = found
    rest = line.replace(matched, "", 1).strip(" \t-:|[]")
    return Entry(when, source, re.sub(r"\s{2,}", " ", rest) or line.strip())


def can_take_from(path: Path) -> bool:
    """Aus verschlüsselten Notizen (.ntx) wird nichts in eine (unverschlüsselte) Zeitleiste übernommen."""
    return Path(path).suffix.lower() != ".ntx"


def find_timelines(root: Path, limit: int = 3000) -> list[Path]:
    """Zeitleisten-Notizen im Datenordner (nur .md; liest je Datei höchstens die ersten 4 KB)."""
    found, seen = [], 0
    for path in sorted(Path(root).rglob("*.md")):
        seen += 1
        if seen > limit:
            break
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                if is_timeline(handle.read(4000)):
                    found.append(path)
        except OSError:
            continue
    return found


# ---- Beweismittel (Chain of Custody) ------------------------------------------------------------------------------
def append_row(text: str, heading: str, cells: list[str]) -> tuple[str, int] | None:
    """Zeile an die erste Tabelle unter der Überschrift `heading` („Prüfsummen“, „Übergaben“) anhängen.
    Leere Platzhalterzeilen (nur leere Zellen) werden dabei ersetzt. → (neuer Text, Zeile) oder None."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.lstrip("#").strip().lower() == heading.lower()
                  and l.startswith("#")), None)
    if start is None:
        return None
    first = last = None
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("#"):
            break
        if split_row(lines[index]) is not None:
            first = index if first is None else first
            last = index
        elif first is not None:
            break
    row = "| " + " | ".join(escape_cell(c) for c in cells) + " |"
    if last is None:
        return None
    placeholder = split_row(lines[last])
    if last - first >= 2 and placeholder is not None and not any(placeholder):
        lines[last] = row
        return "\n".join(lines), last
    lines.insert(last + 1, row)
    return "\n".join(lines), last + 1
