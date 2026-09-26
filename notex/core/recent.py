"""Liste „Zuletzt geöffnet“: maximal 15 Einträge, neueste zuerst, verschwundene Dateien fallen still raus."""
from __future__ import annotations

from pathlib import Path

MAX_RECENT = 15


def add_recent(entries: list[str], path: Path | str, limit: int = MAX_RECENT) -> list[str]:
    """Setzt `path` an den Anfang (ohne Doppelte) und kürzt auf `limit`."""
    text = str(path)
    result = [text] + [e for e in entries if e != text]
    return result[:limit]


def prune_recent(entries: list[str]) -> list[str]:
    """Entfernt Einträge, deren Datei nicht (mehr) existiert, und Duplikate."""
    seen: set[str] = set()
    result = []
    for entry in entries:
        if not isinstance(entry, str) or entry in seen:
            continue
        seen.add(entry)
        try:
            if Path(entry).is_file():
                result.append(entry)
        except OSError:
            continue
    return result


def shorten_path(path: Path | str, max_len: int = 48) -> str:
    """Kürzt lange Pfade für die Anzeige in der Mitte: C:\\Users\\…\\Notizen\\datei.txt."""
    text = str(path)
    if len(text) <= max_len:
        return text
    head, tail = text[: max_len // 3], text[-(max_len - max_len // 3 - 1):]
    return f"{head}…{tail}"
