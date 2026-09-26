"""Suche über data/: Dateinamen und/oder Volltext. Ohne Qt, damit sie testbar ist.

- immer rekursiv, Groß-/Kleinschreibung egal (Regex: (?-i) im Muster schaltet das um)
- abbrechbar über ein threading.Event (die UI setzt es bei neuer Eingabe)
- Treffer werden über Callbacks gemeldet, sobald sie gefunden sind, und zusätzlich gesammelt zurückgegeben

Abfragesprache (parse_query):
  wort1 wort2           alle Begriffe müssen in derselben Zeile (bzw. im Dateinamen) vorkommen (AND)
  "genaue phrase"       Phrase mit Leerzeichen
  ext:md ext:txt,log    nur diese Endungen
  path:ordner           nur Pfade, die „ordner“ enthalten;  -path:archiv  schließt aus
  Regex-Modus           der Rest (ohne Filter) ist EIN Muster; „Ganzes Wort“ wickelt (?<!\\w)…(?!\\w) darum

Katastrophales Backtracking: mit dem Modul `regex` bekommt jeder Zeilen-Match ein Timeout; ist es nicht
installiert, fällt die Suche auf `re` zurück (ohne Timeout, dafür bleibt alles andere gleich).
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from notex.core.encoding import decode_bytes

try:   # `regex` kennt ein Timeout pro Aufruf – das einzige Mittel gegen katastrophales Backtracking
    import regex as _regex
    HAS_TIMEOUT = True
except ImportError:  # pragma: no cover – Fallback ohne Timeout
    _regex = None
    HAS_TIMEOUT = False

SNIPPET_BEFORE = 30   # Zeichen Kontext vor dem Treffer
SNIPPET_AFTER = 60    # Zeichen Kontext nach dem Treffer
MATCH_TIMEOUT = 0.25  # Sekunden pro Zeile, bevor ein Regex als „zu langsam“ gilt
MAX_LINE_MATCHES = 200

_FILTER_RE = re.compile(r'(?:(?<=\s)|^)(-?path:|ext:)("[^"]*"|\S+)', re.IGNORECASE)
_TOKEN_RE = re.compile(r'"([^"]*)"|(\S+)')


class RegexTimeout(Exception):
    """Ein Zeilen-Match hat länger als MATCH_TIMEOUT gebraucht (katastrophales Backtracking)."""


@dataclass
class NameMatch:
    path: Path
    relative: str       # Pfad relativ zu root, mit "/"
    start: int          # Trefferposition im Dateinamen …
    end: int            # … für die Hervorhebung
    spans: list[tuple[int, int]] = field(default_factory=list)   # alle Treffer (mehrere Begriffe)


@dataclass
class LineMatch:
    line_no: int        # 1-basiert
    column: int         # 0-basiert, Position des Treffers in der vollen Zeile
    length: int         # Länge des Treffers
    snippet: str        # gekürzter Ausschnitt der Zeile
    start: int          # Trefferposition im Snippet …
    end: int            # … für die Hervorhebung
    spans: list[tuple[int, int]] = field(default_factory=list)   # alle Treffer im Snippet


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
    regex: bool = False
    whole_word: bool = False
    case_sensitive: bool = False


@dataclass
class SearchResult:
    names: list[NameMatch] = field(default_factory=list)
    files: list[FileMatch] = field(default_factory=list)
    cancelled: bool = False
    skipped_large: int = 0
    error: str | None = None       # ungültige Regex oder Timeout – die UI zeigt den Text an
    timed_out: bool = False


# ---- Abfrage --------------------------------------------------------------------------------

@dataclass
class Query:
    needles: list = field(default_factory=list)      # kompilierte Muster, alle müssen treffen (AND)
    terms: list[str] = field(default_factory=list)   # die Begriffe/Phrasen bzw. [Regex-Muster] als Text
    extensions: list[str] = field(default_factory=list)   # aus ext:, mit Punkt, klein
    path_includes: list[str] = field(default_factory=list)
    path_excludes: list[str] = field(default_factory=list)
    regex: bool = False
    error: str | None = None

    @property
    def empty(self) -> bool:
        return not self.needles and not self.extensions and not self.path_includes and not self.path_excludes

    def allows_path(self, relative: str) -> bool:
        low = relative.lower()
        if self.path_includes and not all(p in low for p in self.path_includes):
            return False
        return not any(p in low for p in self.path_excludes)

    def allows_extension(self, suffix: str) -> bool:
        return not self.extensions or suffix.lower() in self.extensions


def _compile(pattern: str, flags: int):
    return (_regex.compile(pattern, flags) if _regex is not None else re.compile(pattern, flags))


def parse_query(text: str, regex: bool = False, whole_word: bool = False, case_sensitive: bool = False) -> Query:
    query = Query(regex=regex)
    rest = text
    for m in _FILTER_RE.finditer(text):
        kind, value = m.group(1).lower(), m.group(2).strip('"').strip()
        if not value:
            continue
        if kind == "ext:":
            for ext in value.split(","):
                ext = ext.strip().lower().lstrip(".")
                if ext:
                    query.extensions.append("." + ext)
        elif kind == "path:":
            query.path_includes.append(value.lower().replace("\\", "/"))
        else:
            query.path_excludes.append(value.lower().replace("\\", "/"))
    rest = _FILTER_RE.sub("", rest).strip()
    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        if rest:
            pattern = f"(?<!\\w)(?:{rest})(?!\\w)" if whole_word else rest
            try:
                query.needles.append(_compile(pattern, flags))
                query.terms.append(rest)
            except (re.error, Exception) as error:   # regex.error ist keine re.error-Unterklasse
                query.error = f"Ungültige Regex: {error}"
        return query
    for m in _TOKEN_RE.finditer(rest):
        term = m.group(1) if m.group(1) is not None else m.group(2)
        if not term:
            continue
        pattern = re.escape(term)
        if whole_word:
            pattern = f"(?<!\\w)(?:{pattern})(?!\\w)"
        query.needles.append(_compile(pattern, flags))
        query.terms.append(term)
    return query


def _finditer(needle, text: str):
    if _regex is not None:
        try:
            return list(needle.finditer(text, timeout=MATCH_TIMEOUT))
        except TimeoutError as error:
            raise RegexTimeout(str(error)) from error
    return list(needle.finditer(text))


def match_spans(query: Query, text: str) -> list[tuple[int, int]] | None:
    """Alle Trefferbereiche, wenn JEDES Muster in `text` vorkommt; sonst None. Kann RegexTimeout werfen."""
    spans: list[tuple[int, int]] = []
    for needle in query.needles:
        found = _finditer(needle, text)
        found = [m for m in found if m.end() > m.start()] or found[:1]
        if not found:
            return None
        spans.extend((m.start(), m.end()) for m in found[:MAX_LINE_MATCHES])
    spans.sort()
    return spans


# ---- Dateien -------------------------------------------------------------------------------

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


def _match_name(path: Path, root: Path, query: Query) -> NameMatch | None:
    if not query.needles:
        return None
    spans = match_spans(query, path.name)
    if spans is None:
        return None
    return NameMatch(path=path, relative=_relative(path, root), start=spans[0][0], end=spans[0][1], spans=spans)


def _line_match(line_no: int, line: str, spans: list[tuple[int, int]]) -> LineMatch:
    first_start, first_end = spans[0]
    snippet_start = max(0, first_start - SNIPPET_BEFORE)
    snippet_end = min(len(line), first_end + SNIPPET_AFTER)
    snippet = line[snippet_start:snippet_end].rstrip("\r")
    prefix = "…" if snippet_start > 0 else ""
    suffix = "…" if snippet_end < len(line) else ""
    shift = len(prefix) - snippet_start
    local = [(s + shift, e + shift) for s, e in spans if s >= snippet_start and e <= snippet_end]
    return LineMatch(
        line_no=line_no, column=first_start, length=first_end - first_start,
        snippet=prefix + snippet + suffix,
        start=first_start + shift, end=first_end + shift, spans=local,
    )


def _match_lines(text: str, query: Query, cancel: threading.Event | None) -> list[LineMatch]:
    matches: list[LineMatch] = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        if cancel is not None and line_no % 2000 == 0 and cancel.is_set():
            break
        spans = match_spans(query, line)
        if spans:
            matches.append(_line_match(line_no, line, spans))
    return matches


def search(
    root: Path,
    query_text: str,
    options: SearchOptions,
    cancel: threading.Event | None = None,
    on_name: Callable[[NameMatch], None] | None = None,
    on_file: Callable[[FileMatch], None] | None = None,
) -> SearchResult:
    result = SearchResult()
    query = parse_query(query_text, options.regex, options.whole_word, options.case_sensitive)
    if query.error:
        result.error = query.error
        return result
    if not query.needles or not (options.by_name or options.full_text):
        return result
    extensions = [e for e in options.extensions if query.allows_extension(e)] if query.extensions else list(options.extensions)
    if query.extensions:   # ext:-Filter darf auch Endungen nennen, die nicht im Baum stehen
        extensions = sorted(set(extensions) | set(query.extensions))

    try:
        for path in iter_files(root, extensions):
            if cancel is not None and cancel.is_set():
                result.cancelled = True
                break
            relative = _relative(path, root)
            if not query.allows_path(relative):
                continue

            if options.by_name:
                name_match = _match_name(path, root, query)
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
                lines = _match_lines(text, query, cancel)
                if lines:
                    file_match = FileMatch(path=path, relative=relative, lines=lines)
                    result.files.append(file_match)
                    if on_file:
                        on_file(file_match)
    except RegexTimeout:
        result.timed_out = True
        result.error = "Regex zu langsam (Timeout) – Muster vereinfachen, z. B. verschachtelte Wiederholungen vermeiden"
    return result


# ---- Ersetzen über Dateien ---------------------------------------------------------------------

@dataclass
class ReplaceLine:
    line_no: int     # 1-basiert
    before: str
    after: str


def replace_query_ok(query: Query) -> str | None:
    """Ersetzen braucht genau ein Muster (ein Begriff, eine Phrase oder eine Regex)."""
    if query.error:
        return query.error
    if len(query.needles) != 1:
        return "Zum Ersetzen genau einen Suchbegriff angeben (oder eine Regex)"
    return None


def _substitute(query: Query, line: str, replacement: str) -> str:
    needle = query.needles[0]
    if query.regex:
        if _regex is not None:
            return needle.sub(replacement, line, timeout=MATCH_TIMEOUT)
        return needle.sub(replacement, line)
    return needle.sub(lambda _m: replacement, line)   # Klartext: Backslashes im Ersatz bleiben Backslashes


def preview_replace(text: str, query: Query, replacement: str) -> list[ReplaceLine]:
    """Alle Zeilen mit Treffer als (vorher, nachher). Wirft RegexTimeout oder re.error (kaputte Gruppenreferenz)."""
    result: list[ReplaceLine] = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        if match_spans(query, line):
            try:
                after = _substitute(query, line, replacement)
            except TimeoutError as error:
                raise RegexTimeout(str(error)) from error
            if after != line:
                result.append(ReplaceLine(line_no, line, after))
    return result


def apply_replace(text: str, query: Query, replacement: str, only_lines: set[int] | None = None) -> tuple[str, int]:
    """Ersetzen in `text`; `only_lines` (1-basiert) beschränkt auf die angekreuzten Zeilen. Gibt (Text, Anzahl Zeilen)."""
    lines = text.split("\n")
    count = 0
    for index, line in enumerate(lines):
        line_no = index + 1
        if only_lines is not None and line_no not in only_lines:
            continue
        if match_spans(query, line):
            after = _substitute(query, line, replacement)
            if after != line:
                lines[index] = after
                count += 1
    return "\n".join(lines), count
