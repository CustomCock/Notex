"""Theme-Datenmodell, ohne Qt: Standardwerte, Presets, robustes Zusammenführen, Kontrast.

Ein Theme ist ein verschachteltes dict (JSON-tauglich):
  colors    – alle Farb-Tokens der UI und des Blatts
  paper     – Schatten, Innenabstand, maximale Textbreite
  font      – Schriftfamilien, Größen, Zeilenhöhe
  shape     – Eckenradius, Dichte
  animation – an/aus, Geschwindigkeit

merge_theme() ergänzt fehlende oder ungültige Werte aus dem Standard, damit eine
kaputte Theme-Datei nie zum Absturz führt.
"""
from __future__ import annotations

import copy
import re
from typing import Any

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

DENSITIES = ("kompakt", "normal", "luftig")
DENSITY_FACTORS = {"kompakt": 0.75, "normal": 1.0, "luftig": 1.25}
SPEEDS = ("langsam", "normal", "schnell")
SPEED_FACTORS = {"langsam": 1.6, "normal": 1.0, "schnell": 0.6}

DEFAULT_THEME: dict[str, Any] = {
    "name": "Matt",
    "colors": {
        "bg": "#121212",
        "sidebar": "#171717",
        "surface": "#1e1e1e",
        "hover": "#262626",
        "selection": "#303030",
        "border": "#2a2a2a",
        "text": "#d6d6d6",
        "text_muted": "#8b8b8b",
        "accent": "#7a8a9e",
        "paper": "#ffffff",
        "paper_text": "#1a1a1a",
        "paper_muted": "#b8b8b8",
        "paper_line": "#f5f5f5",
        "paper_selection": "#dfe6ee",
        "paper_match": "#cbd7e6",
        "spell_underline": "#d0665c",
        "grammar_underline": "#5f8fd0",
    },
    "paper": {
        "shadow": True,
        "shadow_strength": 60,      # 0–100
        "padding": 48,              # px, Innenabstand links
        "max_columns": 90,          # Blatt-Modus: maximale Textbreite in Zeichen
    },
    "font": {
        "editor_family": "",        # "" = Standard (SF Pro aus fonts/user/, sonst Inter)
        "ui_size": 13,
        "editor_size": 14,
        "line_height": 1.5,
    },
    "shape": {
        "radius": 6,                # 0–12 px, Controls; Panels bekommen +2
        "density": "normal",
    },
    "animation": {
        "enabled": True,
        "speed": "normal",
    },
}

# Basis-Presets: nur die Abweichungen vom Standard
PRESETS: dict[str, dict[str, Any]] = {
    "Matt": {},
    "Graphit": {
        "colors": {"bg": "#1b1b1b", "sidebar": "#202020", "surface": "#272727", "hover": "#2f2f2f",
                   "selection": "#3a3a3a", "border": "#343434", "text": "#dcdcdc", "text_muted": "#959595",
                   "accent": "#8a98a8"},
    },
    "Mitternacht": {
        "colors": {"bg": "#0a0a0c", "sidebar": "#0e0e11", "surface": "#141418", "hover": "#1b1b21",
                   "selection": "#232330", "border": "#1f1f27", "text": "#d2d4da", "text_muted": "#7f8290",
                   "accent": "#6f8fb8"},
    },
    "Warm": {
        "colors": {"bg": "#161412", "sidebar": "#1b1917", "surface": "#23201d", "hover": "#2b2824",
                   "selection": "#35312c", "border": "#2f2b27", "text": "#dcd6cd", "text_muted": "#948c80",
                   "accent": "#a08f78"},
    },
}

# Blatt-Varianten: nur die Blatt-Farben
PAPER_VARIANTS: dict[str, dict[str, str]] = {
    "Weiß": {"paper": "#ffffff", "paper_text": "#1a1a1a", "paper_muted": "#b8b8b8", "paper_line": "#f5f5f5",
             "paper_selection": "#dfe6ee", "paper_match": "#cbd7e6"},
    "Papier": {"paper": "#faf8f3", "paper_text": "#23201b", "paper_muted": "#bdb7ab", "paper_line": "#f3f0e9",
               "paper_selection": "#e4e0d4", "paper_match": "#dcd4bf"},
    "Sepia": {"paper": "#f4ecd8", "paper_text": "#3b2f22", "paper_muted": "#b9a98d", "paper_line": "#ede4cd",
              "paper_selection": "#e0d3b6", "paper_match": "#d8c69f"},
    "Dunkel": {"paper": "#202023", "paper_text": "#d8d8d8", "paper_muted": "#5c5c62", "paper_line": "#27272b",
               "paper_selection": "#363c4e", "paper_match": "#3e4c66"},
}


def default_theme() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_THEME)


def is_hex_color(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_COLOR.match(value))


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(high, max(low, value))


def merge_theme(raw: Any) -> dict[str, Any]:
    """Gültige Werte aus `raw` übernehmen, alles andere aus dem Standard ergänzen."""
    theme = default_theme()
    if not isinstance(raw, dict):
        return theme
    if isinstance(raw.get("name"), str) and raw["name"].strip():
        theme["name"] = raw["name"].strip()[:60]

    colors = raw.get("colors")
    if isinstance(colors, dict):
        for key in theme["colors"]:
            if is_hex_color(colors.get(key)):
                theme["colors"][key] = colors[key].lower()

    paper = raw.get("paper") if isinstance(raw.get("paper"), dict) else {}
    theme["paper"]["shadow"] = paper.get("shadow") if isinstance(paper.get("shadow"), bool) else theme["paper"]["shadow"]
    theme["paper"]["shadow_strength"] = int(_clamp(paper.get("shadow_strength"), 0, 100, theme["paper"]["shadow_strength"]))
    theme["paper"]["padding"] = int(_clamp(paper.get("padding"), 8, 120, theme["paper"]["padding"]))
    theme["paper"]["max_columns"] = int(_clamp(paper.get("max_columns"), 40, 200, theme["paper"]["max_columns"]))

    font = raw.get("font") if isinstance(raw.get("font"), dict) else {}
    # "ui_family" aus älteren Themes wird bewusst ignoriert: die Oberflächenschrift ist fest
    if isinstance(font.get("editor_family"), str):
        theme["font"]["editor_family"] = font["editor_family"].strip()[:80]
    theme["font"]["ui_size"] = int(_clamp(font.get("ui_size"), 9, 20, theme["font"]["ui_size"]))
    theme["font"]["editor_size"] = int(_clamp(font.get("editor_size"), 8, 40, theme["font"]["editor_size"]))
    theme["font"]["line_height"] = round(_clamp(font.get("line_height"), 1.0, 2.2, theme["font"]["line_height"]), 2)

    shape = raw.get("shape") if isinstance(raw.get("shape"), dict) else {}
    theme["shape"]["radius"] = int(_clamp(shape.get("radius"), 0, 12, theme["shape"]["radius"]))
    if shape.get("density") in DENSITIES:
        theme["shape"]["density"] = shape["density"]

    animation = raw.get("animation") if isinstance(raw.get("animation"), dict) else {}
    if isinstance(animation.get("enabled"), bool):
        theme["animation"]["enabled"] = animation["enabled"]
    if animation.get("speed") in SPEEDS:
        theme["animation"]["speed"] = animation["speed"]
    return theme


def theme_from_preset(preset: str, paper_variant: str | None = None) -> dict[str, Any]:
    """Standard + Preset-Abweichungen (+ optional Blatt-Variante)."""
    theme = default_theme()
    overrides = PRESETS.get(preset, {})
    for section, values in overrides.items():
        theme[section].update(values)
    theme["name"] = preset if preset in PRESETS else theme["name"]
    if paper_variant in PAPER_VARIANTS:
        theme["colors"].update(PAPER_VARIANTS[paper_variant])
    return merge_theme(theme)


def apply_paper_variant(theme: dict[str, Any], variant: str) -> dict[str, Any]:
    result = merge_theme(theme)
    result["colors"].update(PAPER_VARIANTS.get(variant, {}))
    return result


# ---- Kontrast (WCAG 2.x) -------------------------------------------------------
def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(foreground: str, background: str) -> float:
    """Kontrastverhältnis 1.0 (gleich) bis 21.0 (Schwarz auf Weiß). 4.5 ist die WCAG-Grenze für Fließtext."""
    l1, l2 = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(l1, l2), min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


# Welche Farbpaare auf Lesbarkeit geprüft werden: (Vordergrund, Hintergrund)
CONTRAST_PAIRS: list[tuple[str, str]] = [
    ("text", "bg"), ("text", "sidebar"), ("text", "surface"), ("text", "hover"), ("text", "selection"),
    ("text_muted", "bg"), ("text_muted", "sidebar"),
    ("paper_text", "paper"), ("paper_text", "paper_line"), ("paper_text", "paper_selection"),
]
MIN_CONTRAST = 4.5


def contrast_warnings(colors: dict[str, str]) -> dict[str, float]:
    """Für jede Vordergrundfarbe das schlechteste Verhältnis unterhalb der Grenze."""
    warnings: dict[str, float] = {}
    for fg, bg in CONTRAST_PAIRS:
        if fg in colors and bg in colors:
            ratio = contrast_ratio(colors[fg], colors[bg])
            if ratio < MIN_CONTRAST:
                warnings[fg] = min(ratio, warnings.get(fg, 99.0))
    return warnings
