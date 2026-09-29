"""Themes als JSON-Dateien in themes/ im App-Ordner: laden, speichern, umbenennen, löschen, importieren, exportieren."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from notex.core.theme_model import merge_theme

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str) -> str:
    """Theme-Name -> Dateiname ohne Sonderzeichen, die Windows verbietet."""
    cleaned = _UNSAFE.sub("", name).strip().strip(".")
    return cleaned[:60] or "Theme"


class ThemeStore:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def _path(self, name: str) -> Path:
        return self.folder / f"{safe_filename(name)}.json"

    def names(self) -> list[str]:
        if not self.folder.exists():
            return []
        return sorted(path.stem for path in self.folder.glob("*.json"))

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def load(self, name: str) -> dict[str, Any]:
        """Kaputte oder unvollständige Dateien liefern ein ergänztes Theme, nie eine Exception."""
        return self.load_file(self._path(name), fallback_name=name)

    def load_file(self, path: Path, fallback_name: str | None = None) -> dict[str, Any]:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        theme = merge_theme(raw)
        if not isinstance(raw, dict) or not raw.get("name"):
            theme["name"] = fallback_name or Path(path).stem
        return theme

    def is_valid_file(self, path: Path) -> bool:
        """Grobe Prüfung für den Import: JSON-Objekt mit mindestens einem bekannten Abschnitt."""
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(raw, dict) and any(key in raw for key in ("colors", "paper", "font", "shape", "animation"))

    def save(self, theme: dict[str, Any], name: str | None = None) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        theme = merge_theme(theme)
        if name:
            theme["name"] = name.strip()[:60]
        path = self._path(theme["name"])
        path.write_text(json.dumps(theme, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.exists():
            path.unlink()

    def rename(self, old: str, new: str) -> dict[str, Any]:
        theme = self.load(old)
        self.delete(old)
        theme["name"] = new
        self.save(theme)
        return theme

    def duplicate(self, name: str) -> dict[str, Any]:
        theme = self.load(name)
        candidate = f"{theme['name']} Kopie"
        counter = 2
        while self.exists(candidate):
            candidate = f"{theme['name']} Kopie {counter}"
            counter += 1
        theme["name"] = candidate
        self.save(theme)
        return theme

    def import_file(self, source: Path) -> dict[str, Any]:
        theme = self.load_file(source)
        self.save(theme)
        return theme

    def export_file(self, theme: dict[str, Any], target: Path) -> None:
        Path(target).write_text(json.dumps(merge_theme(theme), indent=2, ensure_ascii=False), encoding="utf-8")
