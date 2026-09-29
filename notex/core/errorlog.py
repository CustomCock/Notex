"""Unbehandelte Fehler sichtbar machen: kurzer Protokolleintrag + Einzeiler für den Hinweis in der App.

Hintergrund: Der Windows-Build läuft ohne Konsole. Ohne eigenen Exception-Hook verschwindet jede Exception in
einem Qt-Slot lautlos – der Klick „tut nichts". Dieses Modul formatiert und schreibt den Eintrag; der Hook
selbst sitzt in ui/error_hook.py.

Datenschutz (.ntx-Regel): Es werden nur Dateiname:Zeile:Funktion der Aufrufkette und eine gekürzte
Fehlermeldung geschrieben – keine Quelltextzeilen, keine lokalen Variablen, keine Dateiinhalte.
"""
from __future__ import annotations

import time
import traceback
from pathlib import Path

LOG_NAME = "notex-fehler.log"
MAX_BYTES = 256 * 1024           # danach wird die alte Datei zu .1 (eine Generation reicht)
MAX_MESSAGE = 200


def short_message(exc: BaseException) -> str:
    """Einzeiler für den Toast: Typ + gekürzte Meldung."""
    text = " ".join(str(exc).split())
    if len(text) > MAX_MESSAGE:
        text = text[:MAX_MESSAGE - 1] + "…"
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def format_entry(exc_type, exc: BaseException, tb, now: float | None = None) -> str:
    """Protokolleintrag: Zeitstempel, Einzeiler, Aufrufkette als „datei.py:zeile in funktion"."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now if now is not None else time.time()))
    lines = [f"[{stamp}] {short_message(exc)}"]
    for frame in traceback.extract_tb(tb):
        lines.append(f"    {Path(frame.filename).name}:{frame.lineno} in {frame.name}")
    return "\n".join(lines) + "\n"


def append(log_dir: Path, entry: str, max_bytes: int = MAX_BYTES) -> Path | None:
    """Eintrag anhängen (Ordner wird angelegt, große Datei rotiert). Schreibfehler werden geschluckt –
    das Protokoll darf selbst nie einen Fehler auslösen. Gibt den Pfad zurück oder None."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / LOG_NAME
        if path.exists() and path.stat().st_size > max_bytes:
            path.replace(path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return path
    except OSError:
        return None
