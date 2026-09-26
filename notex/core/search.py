"""Suche über data/: Dateinamen und/oder Volltext. Ohne Qt, damit sie testbar ist.

- immer rekursiv, immer case-insensitive
- abbrechbar über ein threading.Event (die UI setzt es bei neuer Eingabe)
- Treffer werden über Callbacks gemeldet, sobald sie gefunden sind, und
  zusätzlich gesammelt zurückgegeben
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from notex.core.encoding import decode_bytes

SNIPPET_BEFORE = 30   # Zeichen Kontext vor dem Treffer
SNIPPET_AFTER = 60    # Zeichen Kontext nach dem Treffer


@dataclass
class NameMatch:
    path: Path
    relative: str       # Pfad relativ zu root, mit "/"
    start: int          # Trefferposition im Dateinamen …
    end: int            # … für die Hervorhebung


@dataclass
class LineMatch:
    line_no: int        # 1-basiert
    column: int         # 0-basiert, Position des Treffers in der vollen Zeile
    length: int         # Länge des Treffers
    snippet: str        # gekürzter Ausschnitt der Zeile
    start: int          # Trefferposition im Snippet …
    end: int            # … für die Hervorhebung


@dataclass
class FileMatch:
    path: Path
    relative: str
    lines: list[LineMatch] = field(default_factory=list)


@dataclass
class SearchOptions:
    by_name: bool = True
    full_text: bool = False
    extensions: tuple[str, ...] = (".txt", ".md")
    max_bytes: int = 5 * 1024 * 1024   # größere Dateien überspringt der Volltext


@dataclass
class SearchResult:
    names: list[NameMatch] = field(default_factory=list)
    files: list[FileMatch] = field(default_factory=list)
    cancelled: bool = False
    skipped_large: int = 0


def iter_files(root: Path, extensions: tuple[str, ...] | list[str]) -> Iterator[Path]:
    """Alle passenden Dateien unter root, Ordner und Dateien alphabetisch, versteckte übersprungen."""
    suffixes = tuple(ext.lower() for ext in extensions)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if name.lower().endswith(suffixes):
                yield Path(dirpath) / name


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _match_name(path: Path, root: Path, needle: str) -> NameMatch | None:
    # lower() statt casefold(): casefold kann die Länge ändern ("ß" -> "ss"),
    # dann stimmen die Positionen für die Hervorhebung nicht mehr.
    pos = path.name.lower().find(needle)
    if pos < 0:
        return None
    return NameMatch(path=path, relative=_relative(path, root), start=pos, end=pos + len(needle))


def _match_lines(text: str, needle: str, cancel: threading.Event | None) -> list[LineMatch]:
    matches: list[LineMatch] = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        if cancel is not None and line_no % 2000 == 0 and cancel.is_set():
            break
        pos = line.lower().find(needle)
        if pos < 0:
            continue
        snippet_start = max(0, pos - SNIPPET_BEFORE)
        snippet_end = min(len(line), pos + len(needle) + SNIPPET_AFTER)
        snippet = line[snippet_start:snippet_end].strip("\r")
        prefix = "…" if snippet_start > 0 else ""
        suffix = "…" if snippet_end < len(line) else ""
        matches.append(LineMatch(
            line_no=line_no,
            column=pos,
            length=len(needle),
            snippet=prefix + snippet + suffix,
            start=len(prefix) + (pos - snippet_start),
            end=len(prefix) + (pos - snippet_start) + len(needle),
        ))
    return matches


def search(
    root: Path,
    query: str,
    options: SearchOptions,
    cancel: threading.Event | None = None,
    on_name: Callable[[NameMatch], None] | None = None,
    on_file: Callable[[FileMatch], None] | None = None,
) -> SearchResult:
    result = SearchResult()
    needle = query.strip().lower()
    if not needle or not (options.by_name or options.full_text):
        return result

    for path in iter_files(root, options.extensions):
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break

        if options.by_name:
            name_match = _match_name(path, root, needle)
            if name_match is not None:
                result.names.append(name_match)
                if on_name:
                    on_name(name_match)

        if options.full_text:
            try:
                if path.stat().st_size > options.max_bytes:
                    result.skipped_large += 1
                    continue
                text = decode_bytes(path.read_bytes()).text
            except (OSError, UnicodeDecodeError):
                continue
            lines = _match_lines(text, needle, cancel)
            if lines:
                file_match = FileMatch(path=path, relative=_relative(path, root), lines=lines)
                result.files.append(file_match)
                if on_file:
                    on_file(file_match)

    return result
