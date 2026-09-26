"""Design-Tokens: die einzige Stelle, an der Farben, Abstände, Radien, Schriftgrößen
und Animationsdauern stehen. UI-Code und QSS greifen nur hierauf zu.

Abstände liegen strikt im 4-px-Raster, Radien sind 6 (Controls) und 8 (Panels/Blatt).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Colors:
    # Grau-Hierarchie, von hinten nach vorn: bg < sidebar < surface < hover < selection
    bg: str = "#121212"          # Fensterhintergrund, "Tisch"
    sidebar: str = "#171717"     # Seitenleiste, Statusleiste
    surface: str = "#1e1e1e"     # Eingabefelder, Menüs, Chips, Toasts
    hover: str = "#262626"       # Hover-Flächen
    selection: str = "#303030"   # Auswahl im Baum, aktiver Tab
    border: str = "#2a2a2a"      # Rahmen, nur wo Flächenkontrast nicht reicht

    text: str = "#d6d6d6"
    text_muted: str = "#8b8b8b"  # Pfade, Metadaten, Zeilennummern in dunklen Flächen
    text_faint: str = "#5a5a5a"  # Platzhalter, inaktive Chevrons

    # Genau ein Akzent: Fokus-Ring, aktiver Tab-Strich, Suchtreffer
    accent: str = "#7a8a9e"
    accent_soft: str = "rgba(122, 138, 158, 0.28)"   # Treffer-Hintergrund in dunklen Listen

    # Das Blatt
    paper: str = "#ffffff"
    paper_text: str = "#1a1a1a"
    paper_muted: str = "#b8b8b8"      # Zeilennummern
    paper_line: str = "#f5f5f5"       # aktuelle Zeile
    paper_selection: str = "#dfe6ee"  # Textauswahl, ruhig, aus dem Akzent abgeleitet
    paper_match: str = "#cbd7e6"      # Suchtreffer im Blatt (Akzent, hell)
    paper_match_current: str = "#aebfd5"

    # Zustände
    danger: str = "#b56b6b"           # nur in Dialogen für "Verwerfen"/"Löschen"


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


@dataclass(frozen=True)
class Radius:
    control: int = 6   # Buttons, Eingabefelder, Chips, Baum-Auswahl
    panel: int = 8     # Blatt, Menüs, Toast, Dialoge


@dataclass(frozen=True)
class FontSize:
    small: int = 12      # sekundär: Statusleiste, Pfade, Zeilennummern der Trefferliste
    ui: int = 13         # Standard-UI
    editor: int = 14     # Editor-Default (Zoom ändert das zur Laufzeit)
    title: int = 22      # Empty State


@dataclass(frozen=True)
class Duration:
    hover: int = 120      # Hover-Übergänge
    sidebar: int = 200    # Seitenleiste ein-/ausklappen
    fade: int = 100       # Tab-Wechsel
    chevron: int = 150    # Ordner-Pfeil drehen
    toast: int = 1500     # Sichtbarkeit des Toasts
    toast_fade: int = 180


@dataclass(frozen=True)
class Layout:
    tree_row_height: int = 28
    tree_indent: int = 16
    tab_height: int = 36
    status_height: int = 24
    scrollbar: int = 8
    paper_padding: int = 48       # Innenabstand des Blatts links (Rand -> Zeilennummern)
    paper_padding_top: int = 40   # Innenabstand oben/unten
    paper_max_columns: int = 90   # Blatt-Modus: maximale Textbreite in Zeichen
    paper_margin: int = 24        # Abstand Blatt <-> Fensterrand
    editor_line_height: int = 150 # Prozent


COLORS = Colors()
SPACING = Spacing()
RADIUS = Radius()
FONT_SIZE = FontSize()
DURATION = Duration()
LAYOUT = Layout()

UI_FONT_FAMILIES = ["Inter", "Segoe UI Variable", "Segoe UI", "Noto Sans", "sans-serif"]
EDITOR_FONT_FAMILIES = ["JetBrains Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]


def flat_tokens() -> dict[str, str]:
    """Alle Tokens als flaches dict für die QSS-Platzhalter (@name)."""
    tokens: dict[str, str] = {}
    for prefix, group in (("", COLORS), ("sp_", SPACING), ("r_", RADIUS), ("fs_", FONT_SIZE), ("ly_", LAYOUT)):
        for name, value in vars(group).items():
            tokens[f"{prefix}{name}"] = str(value)
    tokens["ui_font"] = ", ".join(f'"{f}"' for f in UI_FONT_FAMILIES)
    tokens["editor_font"] = ", ".join(f'"{f}"' for f in EDITOR_FONT_FAMILIES)
    return tokens
