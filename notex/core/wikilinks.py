"""Wiki-Links [[Ziel]], [[Ziel|Anzeigetext]], [[Ziel#Überschrift]] – Parsen, Auflösen, Index. Ohne Qt.

Auflösung: Zielname ohne Endung, case-insensitive, über ganz data/. Bei Mehrdeutigkeit gewinnt
der kürzeste relative Pfad; [[ordner/datei]] zielt explizit. Links in Codeblöcken (```) und
Inline-Code (`…`) zählen nicht.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LINK_RE = re.compile(r"\[\[([^\[\]|#\n]+?)(?:#([^\[\]|\n]+?))?(?:\|([^\[\]\n]+?))?\]\]")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
TEXT_SUFFIXES = (".txt", ".md", ".log", ".csv", ".json", ".py", ".ini", ".sh", ".ps1", ".bat", ".yaml", ".yml",
                 ".xml", ".html", ".css", ".js", ".sql")


@dataclass(frozen=True)
class Link:
    target: str            # wie geschrieben, ohne #/| (z. B. "notizen" oder "ordner/notizen")
    heading: str | None
    display: str | None
    line: int              # 1-basiert
    start: int             # Spalte des ersten "["
    end: int               # Spalte hinter dem letzten "]"

    @property
    def text(self) -> str:
        return self.display or self.target


def _mask_line(line: str) -> str:
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def find_links(text: str) -> list[Link]:
    links: list[Link] = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in LINK_RE.finditer(_mask_line(line)):
            target = m.group(1).strip()
            if not target:
                continue
            links.append(Link(target, (m.group(2) or "").strip() or None, (m.group(3) or "").strip() or None,
                              number, m.start(), m.end()))
    return links


def links_in_line(line: str, in_fence: bool = False) -> list[Link]:
    """Für den Highlighter: Links einer einzelnen Zeile (Zeilennummer 0)."""
    if in_fence or FENCE_RE.match(line):
        return []
    return [Link(m.group(1).strip(), (m.group(2) or "").strip() or None, (m.group(3) or "").strip() or None,
                 0, m.start(), m.end()) for m in LINK_RE.finditer(_mask_line(line)) if m.group(1).strip()]


def strip_suffix(path: str) -> str:
    lower = path.lower()
    for suffix in TEXT_SUFFIXES:
        if lower.endswith(suffix):
            return path[: -len(suffix)]
    return path


def resolve(target: str, files: list[str]) -> str | None:
    """Relativen Pfad der Zieldatei finden (files: relative Pfade mit '/'), oder None."""
    wanted = strip_suffix(target.strip().replace("\\", "/")).lower().strip("/")
    if not wanted:
        return None
    candidates = []
    for rel in files:
        stem_path = strip_suffix(rel).lower()
        name = stem_path.rsplit("/", 1)[-1]
        if "/" in wanted:
            if stem_path == wanted or stem_path.endswith("/" + wanted):
                candidates.append(rel)
        elif name == wanted:
            candidates.append(rel)
    if not candidates:
        return None
    candidates.sort(key=lambda r: (len(r), r.lower()))
    return candidates[0]


def link_name(rel: str) -> str:
    """Kürzester eindeutiger Name für einen Link auf `rel`: der Dateiname ohne Endung."""
    return strip_suffix(rel).rsplit("/", 1)[-1]


def headings(text: str) -> list[tuple[int, str]]:
    """Markdown-Überschriften als (Zeile, Text)."""
    result = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            result.append((number, m.group(2)))
    return result


def find_heading_line(text: str, heading: str) -> int | None:
    wanted = heading.strip().lower()
    for line, title in headings(text):
        if title.lower() == wanted or title.lower().startswith(wanted):
            return line
    return None


def unlinked_mentions(text: str, name: str) -> list[tuple[int, int, int]]:
    """Vorkommen des Dateinamens (ganzes Wort, case-insensitive) außerhalb von Links/Code: (Zeile, Start, Ende)."""
    if not name.strip():
        return []
    pattern = re.compile(r"(?<![\w\[])" + re.escape(name) + r"(?![\w\]])", re.IGNORECASE)
    result = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        masked = _mask_line(line)
        masked = LINK_RE.sub(lambda m: " " * len(m.group(0)), masked)
        for m in pattern.finditer(masked):
            result.append((number, m.start(), m.end()))
    return result


def rewrite_links(text: str, files: list[str], old_rel: str, new_rel: str) -> tuple[str, int]:
    """Alle Links, die auf old_rel zeigen, auf new_rel umschreiben (Anzeigetext/Überschrift bleiben).

    Der neue Zielname ist der kurze Dateiname, außer er wäre mehrdeutig – dann der relative Pfad.
    """
    new_name = link_name(new_rel)
    others = [f for f in files if f != old_rel and f != new_rel]
    if resolve(new_name, others) is not None:
        new_name = strip_suffix(new_rel)
    count = 0
    lines = text.split("\n")
    in_fence = False
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        masked = _mask_line(line)
        pieces = []
        last = 0
        for m in LINK_RE.finditer(masked):
            target = m.group(1).strip()
            if resolve(target, files) == old_rel or strip_suffix(target).lower() == strip_suffix(old_rel).lower():
                heading = f"#{m.group(2)}" if m.group(2) else ""
                display = f"|{m.group(3)}" if m.group(3) else ""
                pieces.append(line[last:m.start()])
                pieces.append(f"[[{new_name}{heading}{display}]]")
                last = m.end()
                count += 1
        if count and pieces:
            pieces.append(line[last:])
            lines[i] = "".join(pieces)
    return "\n".join(lines), count


# ---- Index ----------------------------------------------------------------------------
@dataclass
class Backlink:
    source: str          # relative Datei, die den Link enthält
    line: int
    snippet: str


class LinkIndex:
    """Ausgehende Links pro Datei und daraus die Rückwärtsrichtung (Backlinks)."""

    def __init__(self) -> None:
        self.files: list[str] = []
        self.outgoing: dict[str, list[tuple[str, int, str]]] = {}   # rel -> [(target_rel, line, snippet)]
        self.unresolved: dict[str, list[str]] = {}                  # rel -> Ziele ohne Datei

    def set_files(self, files: list[str]) -> None:
        self.files = list(files)

    def update_file(self, rel: str, text: str) -> None:
        lines = text.split("\n")
        outgoing = []
        unresolved = []
        for link in find_links(text):
            target = resolve(link.target, self.files)
            snippet = lines[link.line - 1].strip()[:120]
            if target is None:
                unresolved.append(link.target)
            else:
                outgoing.append((target, link.line, snippet))
        self.outgoing[rel] = outgoing
        self.unresolved[rel] = unresolved

    def remove_file(self, rel: str) -> None:
        self.outgoing.pop(rel, None)
        self.unresolved.pop(rel, None)

    def rename_file(self, old_rel: str, new_rel: str) -> None:
        if old_rel in self.outgoing:
            self.outgoing[new_rel] = self.outgoing.pop(old_rel)
            self.unresolved[new_rel] = self.unresolved.pop(old_rel, [])
        self.files = [new_rel if f == old_rel else f for f in self.files]
        for rel, links in self.outgoing.items():
            self.outgoing[rel] = [(new_rel if t == old_rel else t, line, s) for t, line, s in links]

    def backlinks(self, rel: str) -> list[Backlink]:
        result = []
        for source, links in self.outgoing.items():
            if source == rel:
                continue
            for target, line, snippet in links:
                if target == rel:
                    result.append(Backlink(source, line, snippet))
        result.sort(key=lambda b: (b.source.lower(), b.line))
        return result

    def sources_linking_to(self, rel: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for backlink in self.backlinks(rel):
            counts[backlink.source] = counts.get(backlink.source, 0) + 1
        return counts
