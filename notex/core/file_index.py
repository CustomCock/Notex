"""Dateiindex für Quick Open: alle passenden Dateien unter data/, plus Suche mit Fuzzy-Ranking."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from notex.core.fuzzy import Match, match


def scan_files(root: Path, extensions: list[str] | tuple[str, ...]) -> list[str]:
    """Relative Pfade (mit '/') aller Dateien mit passender Endung, versteckte Ordner übersprungen."""
    suffixes = tuple(e.lower() for e in extensions)
    result: list[str] = []
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        for name in sorted(filenames):
            if not name.startswith(".") and name.lower().endswith(suffixes):
                result.append(prefix + name)
    return sorted(result, key=str.lower)


@dataclass
class FileHit:
    relative: str            # Pfad relativ zu data/ oder absoluter Pfad (externe Datei)
    name: str
    match: Match
    external: bool = False
    recent_rank: int = -1


class FileIndex:
    def __init__(self) -> None:
        self.files: list[str] = []
        self.externals: list[str] = []   # absolute Pfade zuletzt geöffneter externer Dateien

    def set_files(self, files: list[str]) -> None:
        self.files = list(files)

    def set_externals(self, paths: list[str]) -> None:
        self.externals = list(paths)

    def search(self, query: str, recent: list[str], limit: int = 30) -> list[FileHit]:
        """Fuzzy über Dateiname (stark) und Pfad (schwach); zuletzt geöffnete Dateien nach vorn."""
        hits: list[FileHit] = []
        for external, entries in ((False, self.files), (True, self.externals)):
            for rel in entries:
                name = rel.rsplit("/", 1)[-1] if not external else Path(rel).name
                best = match(query, name)
                path_match = match(query, rel)
                if best is None and path_match is None:
                    continue
                if best is None or (path_match is not None and path_match.score > best.score + 4):
                    best = path_match
                    chosen_on_name = False
                else:
                    chosen_on_name = True
                rank = recent.index(rel) if rel in recent else -1
                hit = FileHit(rel, name, best, external, rank)
                hit.chosen_on_name = chosen_on_name  # type: ignore[attr-defined]
                hits.append(hit)
        hits.sort(key=lambda h: (-(h.match.score + (6 - h.recent_rank * 0.3 if h.recent_rank >= 0 else 0)), h.relative))
        return hits[:limit]
