"""Variablen-Dienst: hält die Definitionen aus variables.json (neben der App) und meldet Änderungen.

Nur aktiv, solange das Modul „Variablen“ an ist (dann steht er in Editor.variables). Ändert sich ein Wert, zeichnen
alle Editoren und Vorschauen neu – in der Datei steht weiterhin nur das Token.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from notex.core import variables as vb
from notex.core.variables import Token, Variable


class VariableService(QObject):
    changed = Signal()

    def __init__(self, path: Path, config: dict) -> None:
        super().__init__()
        self.path = Path(path)
        self.config = config.setdefault("variables", {})
        self.variables: list[Variable] = vb.load_variables(self.path)
        self.values: dict[str, str] = {}
        self._reindex()

    # ---- Einstellungen ----------------------------------------------------------------------------
    @property
    def prefix(self) -> str:
        prefix = self.config.get("prefix", vb.DEFAULT_PREFIX)
        return prefix if isinstance(prefix, str) and prefix.strip() and not any(c.isalnum() or c in "_\\" for c in prefix) \
            else vb.DEFAULT_PREFIX

    def set_prefix(self, prefix: str) -> None:
        self.config["prefix"] = prefix
        self.changed.emit()

    @property
    def copy_values(self) -> bool:
        return self.config.get("copy", "values") != "tokens"

    # ---- Definitionen --------------------------------------------------------------------------------
    def _reindex(self) -> None:
        self.values = {v.name: v.value for v in self.variables}

    def get(self, name: str) -> Variable | None:
        return next((v for v in self.variables if v.name == name), None)

    def set_all(self, variables: list[Variable]) -> None:
        self.variables = list(variables)
        self._reindex()
        vb.save_variables(self.path, self.variables)
        self.changed.emit()

    def upsert(self, variable: Variable, old_name: str | None = None) -> None:
        items = [v for v in self.variables if v.name not in (variable.name, old_name)]
        self.set_all(items + [variable])

    def delete(self, name: str) -> None:
        self.set_all([v for v in self.variables if v.name != name])

    # ---- Text ------------------------------------------------------------------------------------
    def tokens(self, text: str) -> list[Token]:
        return vb.find_tokens(text, self.values, self.prefix)

    def resolve(self, text: str) -> str:
        return vb.resolve(text, self.values, self.prefix)
