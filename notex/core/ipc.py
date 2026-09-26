"""Nachrichtenformat für die Einzelinstanz: die zweite Instanz schickt der ersten die zu öffnenden Pfade.

Reines Python: Kodierung als JSON-Zeile, damit sie über einen QLocalSocket (oder in Tests
über einen Puffer) sauber gelesen werden kann. Der Servername hängt vom App-Ordner ab, damit
zwei portable Kopien in verschiedenen Ordnern sich nicht in die Quere kommen.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def server_name(app_root: Path | str) -> str:
    digest = hashlib.sha1(str(Path(app_root).resolve()).lower().encode("utf-8")).hexdigest()[:12]
    return f"notex-{digest}"


def encode_open_request(paths: list[str | Path]) -> bytes:
    payload = {"open": [str(Path(p).resolve()) for p in paths]}
    return (json.dumps(payload) + "\n").encode("utf-8")


def decode_open_request(data: bytes) -> list[str]:
    """Liefert die Pfade oder [] bei kaputten Daten – nie eine Exception."""
    try:
        payload = json.loads(data.decode("utf-8").strip())
    except (ValueError, UnicodeDecodeError):
        return []
    paths = payload.get("open") if isinstance(payload, dict) else None
    if not isinstance(paths, list):
        return []
    return [p for p in paths if isinstance(p, str) and p]


def file_arguments(argv: list[str]) -> list[Path]:
    """Existierende Dateien aus den Kommandozeilen-Argumenten (Optionen wie -x werden ignoriert)."""
    result = []
    for arg in argv:
        if arg.startswith("-"):
            continue
        try:
            path = Path(arg).expanduser().resolve()
        except OSError:
            continue
        if path.is_file():
            result.append(path)
    return result
