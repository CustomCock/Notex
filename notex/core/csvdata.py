"""CSV/TSV als Tabelle: Dialekt erkennen, parsen, zurückschreiben im gleichen Stil. Ohne Qt.

- Trennzeichen über csv.Sniffer (Kandidaten , ; Tab |), Fallback über Zählen; .tsv bevorzugt Tab.
- Quoting-Stil wird erkannt und beim Speichern beibehalten: „minimal“ (nur wo nötig) oder „all“ (jedes Feld).
- Kopfzeile: Sniffer.has_header als Vorschlag, in der Oberfläche umschaltbar.
- Sortieren/Filtern verändern nur die Ansicht (Indexlisten), nie die Reihenfolge in der Datei.
- Encoding und Zeilenende verwaltet der Editor (TextFile) – hier wird mit "\\n" gearbeitet.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, replace
from pathlib import Path

from notex.core.fileops import is_encrypted_path

TABLE_SUFFIXES = (".csv", ".tsv")
DELIMITERS = [",", ";", "\t", "|"]
DELIMITER_NAMES = {",": "Komma", ";": "Semikolon", "\t": "Tab", "|": "Senkrechter Strich"}
SAMPLE_CHARS = 64 * 1024


def table_supported(path: Path | str) -> bool:
    """Tabellenansicht für .csv/.tsv – nie für .ntx (deren Inhalt kennt nur der entsperrte Editor)."""
    return str(path).lower().endswith(TABLE_SUFFIXES) and not is_encrypted_path(path)


@dataclass(frozen=True)
class Dialect:
    delimiter: str = ","
    quotechar: str = '"'
    quoting: str = "minimal"     # "minimal" | "all"
    has_header: bool = True
    trailing_newline: bool = True

    def with_(self, **changes) -> "Dialect":
        return replace(self, **changes)


def _count_delimiters(lines: list[str]) -> str:
    best, best_score = ",", -1.0
    for delimiter in DELIMITERS:
        counts = [line.count(delimiter) for line in lines if line.strip()]
        if not counts or max(counts) == 0:
            continue
        consistent = sum(1 for c in counts if c == counts[0]) / len(counts)
        score = consistent * 10 + min(counts[0], 50) / 50
        if score > best_score:
            best, best_score = delimiter, score
    return best


def _quoting_style(text: str, delimiter: str, quotechar: str) -> str:
    """„all“, wenn in den ersten Zeilen jedes Feld in Anführungszeichen steht."""
    lines = [l for l in text.split("\n")[:50] if l.strip()]
    if not lines:
        return "minimal"
    try:
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter, quotechar=quotechar))
    except csv.Error:
        return "minimal"
    raw_fields = []
    for line in lines:
        raw_fields.extend(line.split(delimiter))
    if rows and raw_fields and all(f.strip().startswith(quotechar) for f in raw_fields if f.strip()):
        return "all"
    return "minimal"


def sniff(text: str, name: str = "") -> Dialect:
    sample = text[:SAMPLE_CHARS]
    lines = sample.split("\n")[:200]
    if name.lower().endswith(".tsv") and any("\t" in line for line in lines):
        delimiter = "\t"
    else:
        try:
            delimiter = csv.Sniffer().sniff("\n".join(lines[:100]), delimiters="".join(DELIMITERS)).delimiter
        except csv.Error:
            delimiter = _count_delimiters(lines)
        # Sniffer irrt gern bei wenig Spalten – Zählung ist robuster, wenn sie eindeutig ist
        counted = _count_delimiters(lines)
        if delimiter not in DELIMITERS or (counted != delimiter and _consistent(lines, counted) and not _consistent(lines, delimiter)):
            delimiter = counted
    quotechar = '"' if sample.count('"') >= sample.count("'") else "'"
    try:
        has_header = csv.Sniffer().has_header("\n".join(lines[:50])) if len([l for l in lines if l.strip()]) > 1 else False
    except csv.Error:
        has_header = False
    if not has_header:
        has_header = _looks_like_header(lines, delimiter)
    return Dialect(delimiter, quotechar, _quoting_style(sample, delimiter, quotechar), has_header, text.endswith("\n"))


def _consistent(lines: list[str], delimiter: str) -> bool:
    counts = [line.count(delimiter) for line in lines if line.strip()]
    return bool(counts) and counts[0] > 0 and all(c == counts[0] for c in counts)


def _looks_like_header(lines: list[str], delimiter: str) -> bool:
    """Erste Zeile nur Text, darunter mindestens eine Spalte mit Zahlen → Kopfzeile."""
    rows = [r for r in csv.reader(io.StringIO("\n".join(lines[:20])), delimiter=delimiter) if r]
    if len(rows) < 2:
        return False
    first = rows[0]
    if any(to_number(v) is not None for v in first if v.strip()):
        return False
    for column in range(len(first)):
        values = [r[column] for r in rows[1:] if column < len(r) and r[column].strip()]
        if values and all(to_number(v) is not None for v in values):
            return True
    return False


def parse(text: str, dialect: Dialect) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=dialect.delimiter, quotechar=dialect.quotechar)
    rows = [row for row in reader]
    while rows and rows[-1] == []:
        rows.pop()
    return rows


def serialize(rows: list[list[str]], dialect: Dialect) -> str:
    buffer = io.StringIO()
    quoting = csv.QUOTE_ALL if dialect.quoting == "all" else csv.QUOTE_MINIMAL
    writer = csv.writer(buffer, delimiter=dialect.delimiter, quotechar=dialect.quotechar, quoting=quoting,
                        lineterminator="\n")
    writer.writerows(rows)
    text = buffer.getvalue()
    if not dialect.trailing_newline and text.endswith("\n"):
        text = text[:-1]
    return text


_NUMBER = re.compile(r"^[+-]?(\d{1,3}([.,' ]\d{3})*|\d+)([.,]\d+)?([eE][+-]?\d+)?%?$")


def to_number(value: str) -> float | None:
    """„1234“, „1.234,56“, „1,234.56“, „3,5“, „-2e3“, „12 %“ → Zahl; sonst None."""
    v = value.strip().replace(" ", " ")
    if not v or not _NUMBER.match(v.replace(" %", "%")):
        return None
    v = v.rstrip("%").replace(" ", "").replace("'", "")
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    elif v.count(",") == 1:
        v = v.replace(",", ".")        # „3,5“ – deutsche Schreibweise zuerst
    elif "," in v:
        v = v.replace(",", "")         # „1,234,567“
    elif v.count(".") > 1:
        v = v.replace(".", "")
    try:
        return float(v)
    except ValueError:
        return None


def column_is_numeric(rows: list[list[str]], column: int, sample: int = 500) -> bool:
    values = [r[column] for r in rows[:sample] if column < len(r) and r[column].strip()]
    return bool(values) and sum(1 for v in values if to_number(v) is not None) / len(values) >= 0.9


def sorted_indices(rows: list[list[str]], indices: list[int], column: int, descending: bool = False) -> list[int]:
    """Anzeige-Reihenfolge sortiert nach Spalte – numerisch, wenn die Spalte aus Zahlen besteht."""
    numeric = column_is_numeric([rows[i] for i in indices], column)

    def key(i: int):
        value = rows[i][column] if column < len(rows[i]) else ""
        if numeric:
            number = to_number(value)
            return (0, number) if number is not None else (1, 0.0)
        return (0 if value.strip() else 1, value.casefold())

    return sorted(indices, key=key, reverse=descending)


def filter_indices(rows: list[list[str]], indices: list[int], needle: str) -> list[int]:
    needle = needle.strip().casefold()
    if not needle:
        return list(indices)
    return [i for i in indices if any(needle in cell.casefold() for cell in rows[i])]
