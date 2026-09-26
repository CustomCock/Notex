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
    "recent_commands": [],    # zuletzt benutzte Befehle der Command Palette (IDs)
    "wiki_links": True,       # [[Links]] hervorheben und auflösen
    "backlinks_visible": False,
    "backlinks_position": "bottom",   # "bottom" | "right"
    "active_tab": 0,
    "split": {                # geteilter Editor: zweite Tab-Gruppe
        "enabled": False,
        "open_tabs": [],
        "active_tab": 0,
        "active_group": 0,
        "orientation": "horizontal",   # nebeneinander | "vertical" = untereinander
    },
    "font_size": 14,          # Zoomstufe = Schriftgröße des Editors in Pixeln
    "paper_mode": True,       # Blatt zentriert mit maximaler Textbreite (False = volle Breite)
    "toolbar_visible": True,  # Bearbeitungsleiste über dem Blatt ausgeklappt
    "line_numbers": True,
    "markdown_view": "edit",      # Ansicht beim Öffnen von .md: "edit" | "preview" | "split"
    "preview_sync_scroll": True,  # Vorschau scrollt mit dem Editor (geteilte Ansicht)
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
    "update_check": {         # höchstens einmal täglich GitHub-Releases prüfen, nie etwas herunterladen
        "enabled": True,
        "last_check": 0.0,    # Unix-Zeit der letzten Prüfung
        "skipped": "",        # Version, auf die nicht mehr hingewiesen wird
    },
    "templates": {            # Vorlagen liegen in templates/ neben der App
        "week_folder": "Wochen",            # Ordner in data/ für „Neue Woche“
        "week_name": "KW{{week}} {{year}}",  # Dateiname (ohne .md) mit Platzhaltern
        "week_template": "Woche.md",
    },
    "encryption": {           # verschlüsselte Notizen (.ntx)
        "auto_lock_minutes": 5,   # nach so vielen Minuten ohne Eingabe sperren (0 = nie)
    },
    "history": {              # lokale Versionshistorie in history/ neben der App
        "enabled": True,
        "max_mb": 200,        # Obergrenze für die komprimierten Schnappschüsse
    },
    "search": {
        "by_name": True,
        "full_text": False,
        "regex": False,       # Chip „.*“: regulärer Ausdruck
        "whole_word": False,  # Chip „Wort“: nur ganze Wörter
    },
    "extensions": [".txt", ".md", ".log", ".csv", ".json", ".py", ".ini", ".sh", ".ps1", ".bat", ".yaml", ".yml",
                   ".xml", ".html", ".css", ".js", ".sql", ".ntx"],
    "extensions_version": 3,  # Migration: neue Standard-Endungen werden einmalig ergänzt, eigene bleiben
    "syntax_highlighting": True,
    "syntax_extensions": [".py", ".json", ".ini", ".log", ".sh", ".ps1", ".bat", ".yaml", ".yml", ".xml",
                          ".html", ".css", ".js", ".sql", ".md"],
    # Textschrift je Dateiendung ("" = Standardschrift des Themes). Offene Zuordnung: eigene Endungen erlaubt.
    "font_by_extension": {".py": "JetBrains Mono", ".json": "JetBrains Mono", ".csv": "JetBrains Mono",
                          ".log": "JetBrains Mono", ".ini": "JetBrains Mono", ".sh": "JetBrains Mono",
                          ".ps1": "JetBrains Mono", ".bat": "JetBrains Mono", ".yaml": "JetBrains Mono",
                          ".yml": "JetBrains Mono", ".xml": "JetBrains Mono", ".html": "JetBrains Mono",
                          ".css": "JetBrains Mono", ".js": "JetBrains Mono", ".sql": "JetBrains Mono"},
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


def config_digest(config: dict[str, Any]) -> str:
    """Kurzer Fingerabdruck der Config, um unnötiges Schreiben zu vermeiden."""
    import hashlib
    return hashlib.sha1(json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def default_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULTS)


def load_config(path: Path) -> dict[str, Any]:
    """Liest die Config. Jede Art von Fehler führt zu Defaults, nie zu einer Exception."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_config()
    return migrate(_merge(DEFAULTS, raw), raw)


def migrate(config: dict[str, Any], raw: Any) -> dict[str, Any]:
    """Einmalige Anpassungen alter Configs, ohne eigene Einstellungen zu überschreiben."""
    raw_version = raw.get("extensions_version", 1) if isinstance(raw, dict) else 1
    if isinstance(raw, dict) and "extensions" in raw and (not isinstance(raw_version, int) or raw_version < 2):
        # v1.0: neue Standard-Endungen (Syntax-Highlighting) einmalig ergänzen, Reihenfolge und eigene behalten
        existing = [e for e in config["extensions"]]
        for ext in DEFAULTS["extensions"]:
            if ext not in existing:
                existing.append(ext)
        config["extensions"] = existing
    elif isinstance(raw, dict) and "extensions" in raw and raw_version < 3:
        # v1.3: verschlüsselte Notizen im Baum anzeigen
        if ".ntx" not in config["extensions"]:
            config["extensions"] = list(config["extensions"]) + [".ntx"]
    config["extensions_version"] = DEFAULTS["extensions_version"]
    return config


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
