"""Laden und Speichern von config.json.

Regeln:
- Fehlt die Datei oder ist sie kaputt -> Defaults, die App darf nie crashen.
- Unbekannte oder falsch typisierte Werte werden ignoriert, der Rest bleibt.
- Gespeichert wird atomar (Temp-Datei + os.replace), wie bei Textdateien auch.
"""
from __future__ import annotations

import copy
import json

from notex.core.theme_model import default_theme
import os
import tempfile
from pathlib import Path
from typing import Any

# Alle Einstellungen mit ihren Standardwerten. Die Typen hier sind gleichzeitig
# die "Schablone": ein Wert aus der Datei wird nur übernommen, wenn sein Typ passt.
DEFAULTS: dict[str, Any] = {
    "window": {
        "x": None,          # None = Qt entscheidet (erster Start)
        "y": None,
        "width": 1200,
        "height": 800,
        "maximized": False,
    },
    "sidebar": {
        "visible": True,
        "width": 280,
    },
    "expanded_folders": [],   # relative Pfade unter data/, z. B. "Projekte/2026"
    "open_tabs": [],          # Pfade der offenen Dateien: relativ zu data/ oder absolut (externe)
    "recent_files": [],       # zuletzt geöffnet, absolute Pfade, neueste zuerst (max. 15)
    "association_extensions": [".txt"],   # Auswahl auf der Einstellungsseite „System“
    "active_tab": 0,
    "font_size": 14,          # Zoomstufe = Schriftgröße des Editors in Pixeln
    "paper_mode": True,       # Blatt zentriert mit maximaler Textbreite (False = volle Breite)
    "toolbar_visible": True,  # Bearbeitungsleiste über dem Blatt ausgeklappt
    "line_numbers": True,
    "theme": default_theme(), # das aktive Theme, komplett (Presets/Dateien sind nur Vorlagen)
    "spellcheck": {
        "enabled": True,
        "language": "de",           # "de" | "en" | "both"
        "extensions": [".txt", ".md"],
    },
    "grammar": {
        "enabled": False,
        "server_url": "http://localhost:8081",
        "allow_public": False,      # öffentliche LanguageTool-API nur nach ausdrücklicher Zustimmung
    },
    "search": {
        "by_name": True,
        "full_text": False,
    },
    "extensions": [".txt", ".md", ".log", ".csv", ".json", ".py", ".ini"],
    # Textschrift je Dateiendung ("" = Standardschrift des Themes). Offene Zuordnung: eigene Endungen erlaubt.
    "font_by_extension": {".py": "JetBrains Mono", ".json": "JetBrains Mono", ".csv": "JetBrains Mono",
                          ".log": "JetBrains Mono", ".ini": "JetBrains Mono"},
    "fulltext_max_mb": 5,     # größere Dateien überspringt die Volltextsuche
}


def _merge(default: Any, loaded: Any) -> Any:
    """Verschmilzt einen geladenen Wert mit dem Default – rekursiv für dicts.

    Typprüfung: bool ist in Python ein int-Subtyp, deshalb wird bool extra
    behandelt, sonst würde `true` als Fenstergröße durchgehen.
    """
    if isinstance(default, dict):
        if not isinstance(loaded, dict):
            return copy.deepcopy(default)
        if default and all(isinstance(v, str) for v in default.values()):
            # Offene Zuordnung (z. B. Dateiendung -> Schrift): beliebige Schlüssel, Werte müssen Strings sein
            result = dict(default)
            result.update({k: v for k, v in loaded.items() if isinstance(k, str) and isinstance(v, str)})
            return result
        result = {}
        for key, default_value in default.items():
            result[key] = _merge(default_value, loaded.get(key, default_value))
        return result

    if default is None:
        # Nur für window.x / window.y: erlaubt sind None oder ganze Zahlen.
        return loaded if (loaded is None or (isinstance(loaded, int) and not isinstance(loaded, bool))) else None

    if isinstance(default, bool):
        return loaded if isinstance(loaded, bool) else default

    if isinstance(default, int):
        return loaded if (isinstance(loaded, int) and not isinstance(loaded, bool)) else default

    if isinstance(default, float):
        return float(loaded) if (isinstance(loaded, (int, float)) and not isinstance(loaded, bool)) else default

    if isinstance(default, list):
        return list(loaded) if isinstance(loaded, list) else copy.deepcopy(default)

    return loaded if isinstance(loaded, type(default)) else default


def default_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULTS)


def load_config(path: Path) -> dict[str, Any]:
    """Liest die Config. Jede Art von Fehler führt zu Defaults, nie zu einer Exception."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_config()
    return _merge(DEFAULTS, raw)


def save_config(path: Path, config: dict[str, Any]) -> None:
    """Schreibt die Config atomar: erst Temp-Datei im selben Ordner, dann umbenennen."""
    path = Path(path)
    text = json.dumps(config, indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        # Aufräumen, damit keine Temp-Leiche liegen bleibt
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
