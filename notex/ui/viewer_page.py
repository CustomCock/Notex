"""Tabs, die keine Texteditoren sind: Bilder, Hex-Ansicht, PDF.

ViewerPage ist die gemeinsame Basis: sie kennt ihren Pfad, liefert Text für die Statusleiste und kann bei
Umbenennen/Verschieben nachgezogen werden. Viewer schreiben nie in die Datei (alle nur lesend).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{size} B"


class ViewerPage(QWidget):
    kind = "viewer"
    icon_name = "file"
    status_changed = Signal()

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.setObjectName("ViewerPage")
        self.path = Path(path)

    def status_parts(self) -> list[str]:
        """Einträge für die Statusleiste (links nach rechts), z. B. Maße, Größe, Typ."""
        try:
            return [human_size(self.path.stat().st_size)]
        except OSError:
            return []

    def rename(self, new_path: Path) -> None:
        self.path = Path(new_path)

    def retheme(self) -> None:
        pass

    def shutdown(self) -> None:
        pass
