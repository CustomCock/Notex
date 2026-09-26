"""Design-Tokens: die einzige Stelle, an der Farben, Abstände, Radien, Schriftgrößen
und Animationsdauern stehen. UI-Code und QSS greifen nur hierauf zu.

Die Objekte hier sind veränderbar: apply_theme() schreibt ein Theme-dict (siehe
core/theme_model.py) hinein, und weil alle Module dieselben Objekte importieren,
sehen sie die neuen Werte sofort. Abstände liegen im 4-px-Raster (mal Dichte-Faktor),
Radien sind 6 (Controls) und 8 (Panels/Blatt) – oder was das Theme vorgibt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from notex.core.theme_model import DENSITY_FACTORS, SPEED_FACTORS, default_theme, merge_theme


@dataclass
class Colors:
    # Grau-Hierarchie, von hinten nach vorn: bg < sidebar < surface < hover < selection
    bg: str = "#121212"
    sidebar: str = "#171717"
    surface: str = "#1e1e1e"
    hover: str = "#262626"
    selection: str = "#303030"
    border: str = "#2a2a2a"
    text: str = "#d6d6d6"
    text_muted: str = "#8b8b8b"
    text_faint: str = "#5a5a5a"      # abgeleitet: zwischen bg und text_muted
    accent: str = "#7a8a9e"
    accent_soft: str = "rgba(122, 138, 158, 0.28)"   # abgeleitet aus accent
    paper: str = "#ffffff"
    paper_text: str = "#1a1a1a"
    paper_muted: str = "#b8b8b8"
    paper_line: str = "#f5f5f5"
    paper_selection: str = "#dfe6ee"
    paper_match: str = "#cbd7e6"
    paper_match_current: str = "#aebfd5"   # abgeleitet aus paper_match
    spell_underline: str = "#d0665c"
    grammar_underline: str = "#5f8fd0"
    danger: str = "#b56b6b"
    success: str = "#6f9a7a"          # z. B. Prüfsumme stimmt überein (gedämpft wie danger)
    warning: str = "#b39a5c"          # z. B. WARN-Zeilen im Live-Log


@dataclass
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


@dataclass
class Radius:
    control: int = 6
    panel: int = 8


@dataclass
class FontSize:
    small: int = 12
    ui: int = 13
    editor: int = 14
    title: int = 22


@dataclass
class Duration:
    hover: int = 120
    sidebar: int = 200
    fade: int = 100
    chevron: int = 150
    toast: int = 1500
    toast_fade: int = 180


@dataclass
class Layout:
    tree_row_height: int = 28
    tree_indent: int = 16
    tab_height: int = 36
    status_height: int = 24
    scrollbar: int = 8
    paper_padding: int = 48
    paper_padding_top: int = 40
    paper_max_columns: int = 90
    paper_margin: int = 24
    paper_shadow: bool = True
    paper_shadow_alpha: int = 150
    editor_line_height: int = 150   # Prozent


SYNTAX: dict[str, str] = {}   # aktive Syntax-Farben (hell oder dunkel, je nach Blattfarbe)
COLORS = Colors()
SPACING = Spacing()
RADIUS = Radius()
FONT_SIZE = FontSize()
DURATION = Duration()
LAYOUT = Layout()

# Nur für das QSS: konkrete Familien löst fonts.py zur Laufzeit auf (SF Pro aus fonts/user/ zuerst)
UI_FONT_FAMILIES = ["SF Pro Text", "SF Pro Display", "Inter", "Segoe UI Variable", "Segoe UI", "Noto Sans", "sans-serif"]
TEXT_FONT_FAMILY = ""   # aktuelle Textschrift des Blatts ("" = Standard)

_BASE_SPACING = Spacing()
_BASE_DURATION = Duration()
_BASE_LAYOUT = Layout()
_ACTIVE: dict[str, Any] = default_theme()


def _mix(hex_a: str, hex_b: str, t: float) -> str:
    """Linear zwischen zwei Hex-Farben mischen (t=0 -> a, t=1 -> b)."""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


def active_theme() -> dict[str, Any]:
    """Kopie des aktuell angewendeten Themes."""
    return merge_theme(_ACTIVE)


def apply_theme(theme: dict[str, Any]) -> dict[str, Any]:
    """Schreibt ein Theme in die Token-Objekte. Gibt das bereinigte Theme zurück."""
    global _ACTIVE
    theme = merge_theme(theme)
    _ACTIVE = theme

    colors = theme["colors"]
    for key, value in colors.items():
        setattr(COLORS, key, value)
    COLORS.text_faint = _mix(colors["bg"], colors["text_muted"], 0.6)
    COLORS.accent_soft = _rgba(colors["accent"], 0.28)
    COLORS.paper_match_current = _mix(colors["paper_match"], colors["paper_text"], 0.18)
    from notex.core.theme_model import relative_luminance
    SYNTAX.clear()
    SYNTAX.update(theme["syntax"]["dark" if relative_luminance(colors["paper"]) < 0.4 else "light"])

    factor = DENSITY_FACTORS[theme["shape"]["density"]]
    for key, base in vars(_BASE_SPACING).items():
        setattr(SPACING, key, max(2, round(base * factor)))
    RADIUS.control = theme["shape"]["radius"]
    RADIUS.panel = min(12, theme["shape"]["radius"] + 2)

    FONT_SIZE.ui = theme["font"]["ui_size"]
    FONT_SIZE.small = max(9, theme["font"]["ui_size"] - 1)
    FONT_SIZE.editor = theme["font"]["editor_size"]
    global TEXT_FONT_FAMILY
    TEXT_FONT_FAMILY = theme["font"]["editor_family"]

    speed = SPEED_FACTORS[theme["animation"]["speed"]]
    for key, base in vars(_BASE_DURATION).items():
        setattr(DURATION, key, round(base * speed))
    DURATION.toast = _BASE_DURATION.toast   # Sichtbarkeitsdauer des Toasts bleibt

    LAYOUT.tree_row_height = round(_BASE_LAYOUT.tree_row_height * factor)
    LAYOUT.tab_height = round(_BASE_LAYOUT.tab_height * factor)
    LAYOUT.status_height = round(_BASE_LAYOUT.status_height * factor)
    LAYOUT.paper_margin = round(_BASE_LAYOUT.paper_margin * factor)
    LAYOUT.paper_padding = theme["paper"]["padding"]
    LAYOUT.paper_padding_top = max(12, round(theme["paper"]["padding"] * 0.85))
    LAYOUT.paper_max_columns = theme["paper"]["max_columns"]
    LAYOUT.paper_shadow = theme["paper"]["shadow"]
    LAYOUT.paper_shadow_alpha = round(theme["paper"]["shadow_strength"] * 2.5)
    LAYOUT.editor_line_height = round(theme["font"]["line_height"] * 100)
    return theme


def flat_tokens() -> dict[str, str]:
    """Alle Tokens als flaches dict für die QSS-Platzhalter (@name)."""
    tokens: dict[str, str] = {}
    for prefix, group in (("", COLORS), ("sp_", SPACING), ("r_", RADIUS), ("fs_", FONT_SIZE), ("ly_", LAYOUT)):
        for name, value in vars(group).items():
            tokens[f"{prefix}{name}"] = str(value)
    tokens["ui_font"] = ", ".join(f'"{f}"' for f in UI_FONT_FAMILIES)
    text_families = ([TEXT_FONT_FAMILY] if TEXT_FONT_FAMILY else []) + UI_FONT_FAMILIES
    tokens["editor_font"] = ", ".join(f'"{f}"' for f in text_families)
    return tokens


apply_theme(default_theme())
