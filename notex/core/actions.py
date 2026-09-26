"""Zentrale Aktions-Registry für die Command Palette – ohne Qt.

Jedes Feature meldet seine Befehle hier an (das Hauptfenster übernimmt das für alle
QActions automatisch). Die Palette fragt die Registry, sortiert nach Fuzzy-Score und
bevorzugt zuletzt benutzte Befehle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from notex.core.fuzzy import Match, match

MAX_RECENT = 20


@dataclass
class Command:
    id: str
    title: str
    category: str = ""
    shortcut: str = ""
    callback: Callable[[], None] | None = None
    is_checked: Callable[[], bool] | None = None   # für Toggles: aktueller Zustand
    keywords: str = ""

    @property
    def label(self) -> str:
        return f"{self.category}: {self.title}" if self.category else self.title


@dataclass
class Hit:
    command: Command
    match: Match
    recent_rank: int = -1    # 0 = zuletzt benutzt


class ActionRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self.recent: list[str] = []

    def register(self, command: Command) -> Command:
        self._commands[command.id] = command
        return command

    def add(self, id: str, title: str, callback: Callable[[], None], category: str = "", shortcut: str = "",
            is_checked: Callable[[], bool] | None = None, keywords: str = "") -> Command:
        return self.register(Command(id, title, category, shortcut, callback, is_checked, keywords))

    def remove(self, id: str) -> None:
        self._commands.pop(id, None)

    def get(self, id: str) -> Command | None:
        return self._commands.get(id)

    def all(self) -> list[Command]:
        return sorted(self._commands.values(), key=lambda c: (c.category, c.title))

    def run(self, id: str) -> bool:
        command = self._commands.get(id)
        if command is None or command.callback is None:
            return False
        self.recent = [id] + [r for r in self.recent if r != id]
        self.recent = self.recent[:MAX_RECENT]
        command.callback()
        return True

    def search(self, query: str, limit: int = 40) -> list[Hit]:
        """Fuzzy über 'Kategorie: Titel' + Schlüsselwörter; ohne Anfrage zuletzt benutzte zuerst."""
        hits: list[Hit] = []
        for command in self._commands.values():
            haystack = f"{command.label} {command.keywords}".strip()
            m = match(query, haystack)
            if m is None:
                continue
            rank = self.recent.index(command.id) if command.id in self.recent else -1
            hits.append(Hit(command, m, rank))
        hits.sort(key=lambda h: (-(h.match.score + (8 - h.recent_rank * 0.4 if h.recent_rank >= 0 else 0)), h.command.label))
        return hits[:limit]
