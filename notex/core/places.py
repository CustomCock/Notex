"""Orte für den Explorer-Baum – ohne Qt, damit die Logik testbar bleibt.

Der Baum zeigt drei Abschnitte:
  * **Notizen**       – der Datenordner der App (data/), voll beschreibbar.
  * **Schnellzugriff** – vom Nutzer angeheftete Ordner (in der Config gespeichert).
  * **Dieser PC**      – Laufwerke/Einhängepunkte und der persönliche Ordner.

Ausserhalb des Notiz-Ordners ist Vorsicht geboten: `is_system_path` erkennt
Systemordner (Windows und Linux/macOS), damit die Oberfläche vor dem Anlegen,
Umbenennen oder Löschen dort warnen kann. Nichts hier liest Dateien – es geht nur
um Pfade und ihre Einordnung.
"""
from __future__ import annotations

import os
import string
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Place:
    """Ein Ziel im Explorer. `path` ist der Wurzelordner, auf den der Baum umschaltet."""
    key: str            # stabile Kennung (für Auswahl/Persistenz)
    label: str
    path: Path
    kind: str           # "notes" | "pinned" | "drive" | "home"
    icon: str
    removable: bool = False   # angeheftete Orte lassen sich wieder entfernen


# ---- Notizen ----------------------------------------------------------------------------------

def notes_place(notes_root: Path | str) -> Place:
    root = Path(notes_root)
    return Place("notes", "Notizen", root, "notes", "folder-open")


# ---- Schnellzugriff ---------------------------------------------------------------------------

def quick_access_paths(config: dict) -> list[Path]:
    """Angeheftete Pfade aus der Config (als Path, Reihenfolge erhalten, Duplikate/Leeres raus)."""
    raw = config.get("quick_access", []) if isinstance(config, dict) else []
    out: list[Path] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            continue
        norm = os.path.normpath(entry)
        if norm not in seen:
            seen.add(norm)
            out.append(Path(norm))
    return out


def pinned_places(config: dict) -> list[Place]:
    places = []
    for path in quick_access_paths(config):
        places.append(Place(f"pinned:{path}", path.name or str(path), path, "pinned", "bookmark", removable=True))
    return places


def add_pinned(config: dict, path: Path | str) -> bool:
    """Ordner an den Schnellzugriff anheften. Gibt True zurück, wenn neu hinzugefügt."""
    path = Path(path)
    norm = os.path.normpath(str(path))
    current = [os.path.normpath(str(p)) for p in quick_access_paths(config)]
    if norm in current:
        return False
    config["quick_access"] = current + [norm]
    return True


def remove_pinned(config: dict, path: Path | str) -> bool:
    norm = os.path.normpath(str(path))
    current = [os.path.normpath(str(p)) for p in quick_access_paths(config)]
    if norm not in current:
        return False
    config["quick_access"] = [p for p in current if p != norm]
    return True


def is_pinned(config: dict, path: Path | str) -> bool:
    norm = os.path.normpath(str(path))
    return norm in [os.path.normpath(str(p)) for p in quick_access_paths(config)]


# ---- Dieser PC --------------------------------------------------------------------------------

def home_place() -> Place:
    return Place("home", "Persönlicher Ordner", Path.home(), "home", "folder")


def _windows_drives() -> list[Place]:
    places = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            places.append(Place(f"drive:{letter}", f"{letter}:\\", root, "drive", "hard-drive"))
    return places


def _unix_roots() -> list[Place]:
    places = [Place("drive:/", "Dateisystem (/)", Path("/"), "drive", "hard-drive")]
    # gebräuchliche Einhängepunkte für Wechseldatenträger
    for base in ("/media", "/mnt", "/run/media", "/Volumes"):
        base_path = Path(base)
        if not base_path.is_dir():
            continue
        try:
            entries = sorted(base_path.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                places.append(Place(f"drive:{entry}", entry.name, entry, "drive", "hard-drive"))
    return places


def drive_places() -> list[Place]:
    """Laufwerke bzw. Wurzeln des Dateisystems – plattformabhängig."""
    if sys.platform.startswith("win"):
        return _windows_drives()
    return _unix_roots()


def this_pc_places() -> list[Place]:
    """„Dieser PC": persönlicher Ordner zuerst, dann Laufwerke/Wurzeln."""
    return [home_place()] + drive_places()


# ---- Systemordner-Erkennung -------------------------------------------------------------------

_WIN_SYSTEM_DIRS = ("windows", "program files", "program files (x86)", "programdata", "system volume information",
                    "$recycle.bin", "recovery", "perflogs")
_UNIX_SYSTEM_DIRS = ("/bin", "/sbin", "/usr", "/etc", "/var", "/boot", "/lib", "/lib32", "/lib64", "/libx32",
                     "/sys", "/proc", "/dev", "/run", "/root", "/opt", "/srv", "/System", "/Library",
                     "/private", "/Applications")


def is_system_path(path: Path | str) -> bool:
    """Grobe Einschätzung, ob ein Pfad in einem Systemordner liegt – für Warnungen vor Schreibzugriffen.

    Konservativ: im Zweifel eher „ja", damit die Oberfläche warnt. Dateisystem-Wurzeln selbst gelten als System.
    """
    try:
        path = Path(path)
        norm = path.resolve(strict=False)
    except (OSError, ValueError):
        return True
    parts = norm.parts
    if not parts:
        return True
    # Wurzel selbst (C:\, /) ist immer heikel
    if len(parts) == 1:
        return True
    if sys.platform.startswith("win"):
        # parts[0] ist z. B. "C:\\"; der erste echte Ordner darunter entscheidet
        for segment in parts[1:2]:
            if segment.lower() in _WIN_SYSTEM_DIRS:
                return True
        # AppData ist Nutzerdaten (dort liegen u. a. Temp-Dateien) – bewusst NICHT als Systemordner werten,
        # sonst warnt die App bei ganz normalen Nutzerpfaden.
        return False
    lowered_path = norm.as_posix()
    for sysdir in _UNIX_SYSTEM_DIRS:
        if lowered_path == sysdir or lowered_path.startswith(sysdir + "/"):
            # /usr/... aber nicht der Home-Ordner; /home ist ausdrücklich kein Systemordner
            return True
    return False


def is_within(path: Path | str, root: Path | str) -> bool:
    """True, wenn `path` innerhalb von `root` liegt (oder gleich ist)."""
    try:
        Path(path).resolve(strict=False).relative_to(Path(root).resolve(strict=False))
        return True
    except (ValueError, OSError):
        return False
