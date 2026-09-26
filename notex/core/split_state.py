"""Zustand des geteilten Editors (zwei Tab-Gruppen) für config.json. Ohne Qt.

Gruppe 0 ist immer da, Gruppe 1 nur bei aktiver Teilung. Beim Laden wird bereinigt: doppelte Pfade
innerhalb einer Gruppe fallen weg (derselbe Pfad darf aber in beiden Gruppen stehen – „gleiches
Dokument in beiden“), nicht mehr vorhandene Dateien fallen weg, Indizes werden eingegrenzt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

ORIENTATIONS = ("horizontal", "vertical")   # nebeneinander | untereinander


@dataclass
class SplitState:
    groups: list[list[str]] = field(default_factory=lambda: [[]])   # Pfade je Gruppe (relativ zu data/ oder absolut)
    active_tabs: list[int] = field(default_factory=lambda: [0])       # aktiver Tab je Gruppe
    active_group: int = 0
    orientation: str = "horizontal"

    @property
    def is_split(self) -> bool:
        return len(self.groups) > 1

    def to_config(self) -> dict[str, Any]:
        """Gruppe 0 bleibt in den alten Schlüsseln open_tabs/active_tab (abwärtskompatibel)."""
        second = self.groups[1] if self.is_split else []
        return {
            "open_tabs": list(self.groups[0]),
            "active_tab": self.active_tabs[0] if self.active_tabs else 0,
            "split": {
                "enabled": self.is_split,
                "open_tabs": list(second),
                "active_tab": self.active_tabs[1] if self.is_split and len(self.active_tabs) > 1 else 0,
                "active_group": self.active_group if self.is_split else 0,
                "orientation": self.orientation if self.orientation in ORIENTATIONS else "horizontal",
            },
        }


def _clean(paths: Any, exists: Callable[[str], bool]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for entry in paths if isinstance(paths, list) else []:
        if not isinstance(entry, str) or not entry or entry in seen:
            continue
        if not exists(entry):
            continue
        seen.add(entry)
        result.append(entry)
    return result


def _clamp(value: Any, count: int) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(index, max(0, count - 1)))


def from_config(config: dict[str, Any], exists: Callable[[str], bool]) -> SplitState:
    """Zustand aus config.json lesen und bereinigen. `exists` prüft, ob ein Eintrag noch eine Datei ist."""
    first = _clean(config.get("open_tabs", []), exists)
    split = config.get("split") if isinstance(config.get("split"), dict) else {}
    state = SplitState(groups=[first], active_tabs=[_clamp(config.get("active_tab", 0), len(first))])
    state.orientation = split.get("orientation") if split.get("orientation") in ORIENTATIONS else "horizontal"
    if split.get("enabled"):
        second = _clean(split.get("open_tabs", []), exists)
        if second:   # eine leere zweite Gruppe wird nicht wiederhergestellt
            state.groups.append(second)
            state.active_tabs.append(_clamp(split.get("active_tab", 0), len(second)))
            state.active_group = 1 if split.get("active_group") == 1 else 0
    return state


def move_entry(groups: list[list[str]], source: int, index: int, target: int) -> list[list[str]] | None:
    """Tab von Gruppe `source` an Position `index` ans Ende von Gruppe `target` verschieben.
    Gibt None zurück, wenn nichts zu tun ist (gleiche Gruppe, ungültiger Index, Ziel hat den Pfad schon)."""
    if source == target or not (0 <= source < len(groups)) or not (0 <= target < len(groups)):
        return None
    if not (0 <= index < len(groups[source])):
        return None
    entry = groups[source][index]
    if entry in groups[target]:
        return None
    result = [list(g) for g in groups]
    del result[source][index]
    result[target].append(entry)
    return result


def merge_groups(groups: list[list[str]]) -> list[str]:
    """Teilung aufheben: alle Tabs in eine Gruppe, Reihenfolge Gruppe 0 dann 1, Duplikate nur einmal."""
    result: list[str] = []
    for group in groups:
        for entry in group:
            if entry not in result:
                result.append(entry)
    return result
