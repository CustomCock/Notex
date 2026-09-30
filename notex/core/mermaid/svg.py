"""SVG-Bausteine für den Mermaid-Renderer – ohne Qt.

Bewusst nur Elemente, die Qts SVG-Renderer (SVG Tiny 1.2) sicher kann: rect, ellipse, line, polygon, polyline,
path (inkl. Bögen), text. Keine <marker> (Pfeilspitzen werden als Polygone gezeichnet), kein CSS, kein
foreignObject, keine externen Verweise – das SVG ist in sich geschlossen und enthält nie Skripte oder Links.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from html import escape

FONT_FAMILY = "Inter, 'Segoe UI', Arial, sans-serif"
FONT_SIZE = 14.0
LINE_HEIGHT = 1.3

# ---- Textbreite schätzen (kein Qt im Kern: Breitentabelle ≈ Inter/Segoe, in em) ----------------------------------------
_NARROW = set("iljI.,:;|!'`()[]{}ſ ")
_SEMI = set("frt-\"*/\\")
_WIDE = set("mwMWÆŒ@%")


def char_width(ch: str) -> float:
    if ch in _NARROW:
        return 0.3
    if ch in _SEMI:
        return 0.4
    if ch in _WIDE:
        return 0.86
    if ch.isupper():
        return 0.67
    if ch.isdigit():
        return 0.57
    if ord(ch) > 0x2E80:          # CJK & Co. – volle Breite
        return 1.0
    return 0.54


def text_width(text: str, size: float = FONT_SIZE, bold: bool = False) -> float:
    width = sum(char_width(c) for c in text) * size
    return width * (1.06 if bold else 1.0)


def split_lines(text: str) -> list[str]:
    """Zeilenumbrüche aus Mermaid-Labels: <br>, <br/>, \\n."""
    import re
    parts = re.split(r"<br\s*/?>|\\n|\n", text, flags=re.IGNORECASE)
    return [p.strip() for p in parts] or [""]


def block_size(text: str, size: float = FONT_SIZE, bold: bool = False) -> tuple[float, float]:
    lines = split_lines(text)
    width = max((text_width(line, size, bold) for line in lines), default=0.0)
    return width, len(lines) * size * LINE_HEIGHT


# ---- Farben ---------------------------------------------------------------------------------------------------------
def _hex(color: str) -> tuple[int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return 128, 128, 128


def mix(a: str, b: str, t: float) -> str:
    """a → b um Anteil t (0 = a, 1 = b)."""
    ra, ga, ba = _hex(a)
    rb, gb, bb = _hex(b)
    return "#{:02x}{:02x}{:02x}".format(round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def luminance(color: str) -> float:
    r, g, b = (v / 255 for v in _hex(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@dataclass
class Theme:
    bg: str = "#ffffff"
    text: str = "#1f2328"
    muted: str = "#6b7280"
    accent: str = "#5f7aa0"
    line: str = "#56606d"
    node_fill: str = "#eef2f8"
    node_stroke: str = "#5f7aa0"
    cluster_fill: str = "#f6f8fb"
    cluster_stroke: str = "#b7c2d2"
    note_fill: str = "#fff8d9"
    note_stroke: str = "#d6c16a"
    danger: str = "#c0504d"
    series: list[str] = field(default_factory=lambda: ["#5f7aa0", "#d08a4c", "#5e9a6b", "#b35f7c", "#8a74b8",
                                                       "#4f9aa6", "#b39a3e", "#7d8a99", "#c46a5c", "#6b8f3e"])
    dark: bool = False


def theme_from_colors(colors: dict[str, str] | None) -> Theme:
    """Schema aus den Vorschau-Farben ableiten (text, muted, accent, bg, border, danger) – hell oder dunkel."""
    colors = colors or {}
    bg = colors.get("bg", "#ffffff")
    text = colors.get("text", "#1f2328")
    accent = colors.get("accent", "#5f7aa0")
    dark = luminance(bg) < 0.4
    theme = Theme(bg=bg, text=text, muted=colors.get("muted", mix(text, bg, 0.45)), accent=accent,
                  line=mix(text, bg, 0.25), node_fill=mix(bg, accent, 0.16 if dark else 0.11), node_stroke=accent,
                  cluster_fill=mix(bg, accent, 0.07 if dark else 0.04), cluster_stroke=mix(accent, bg, 0.45),
                  note_fill=mix(bg, "#e0c050", 0.22 if dark else 0.2), note_stroke=mix("#c9a93a", bg, 0.2),
                  danger=colors.get("danger", "#c0504d"), dark=dark)
    if dark:
        theme.series = [mix(c, "#ffffff", 0.15) for c in theme.series]
    return theme


# ---- Zeichnen -------------------------------------------------------------------------------------------------------
def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v - round(v)) > 1e-6 else str(int(round(v)))


class Svg:
    def __init__(self, theme: Theme) -> None:
        self.theme = theme
        self.parts: list[str] = []

    # Grundformen
    def rect(self, x, y, w, h, fill=None, stroke=None, width=1.2, rx=0.0, dash="", opacity=1.0) -> None:
        self.parts.append(f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" rx="{_f(rx)}" '
                          f'fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{_f(width)}"'
                          + (f' stroke-dasharray="{dash}"' if dash else "")
                          + (f' fill-opacity="{opacity:.2f}"' if opacity < 1 else "") + "/>")

    def ellipse(self, cx, cy, rx, ry, fill=None, stroke=None, width=1.2) -> None:
        self.parts.append(f'<ellipse cx="{_f(cx)}" cy="{_f(cy)}" rx="{_f(rx)}" ry="{_f(ry)}" '
                          f'fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{_f(width)}"/>')

    def line(self, x1, y1, x2, y2, stroke=None, width=1.2, dash="") -> None:
        self.parts.append(f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}" '
                          f'stroke="{stroke or self.theme.line}" stroke-width="{_f(width)}"'
                          + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")

    def polygon(self, points, fill=None, stroke=None, width=1.2) -> None:
        pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in points)
        self.parts.append(f'<polygon points="{pts}" fill="{fill or "none"}" stroke="{stroke or "none"}" '
                          f'stroke-width="{_f(width)}"/>')

    def path(self, d: str, fill=None, stroke=None, width=1.2, dash="") -> None:
        self.parts.append(f'<path d="{d}" fill="{fill or "none"}" stroke="{stroke or "none"}" '
                          f'stroke-width="{_f(width)}"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")

    def text(self, x, y, text, size=FONT_SIZE, anchor="middle", bold=False, italic=False, fill=None,
             family=FONT_FAMILY) -> None:
        self.parts.append(f'<text x="{_f(x)}" y="{_f(y)}" font-family="{escape(family, quote=True)}" '
                          f'font-size="{_f(size)}" text-anchor="{anchor}" fill="{fill or self.theme.text}"'
                          + (' font-weight="bold"' if bold else "") + (' font-style="italic"' if italic else "")
                          + f">{escape(text)}</text>")

    def text_block(self, cx, cy, text, size=FONT_SIZE, anchor="middle", bold=False, italic=False, fill=None) -> None:
        """Mehrzeiligen Text vertikal um cy zentrieren (anchor gilt horizontal an x = cx)."""
        lines = split_lines(text)
        lh = size * LINE_HEIGHT
        top = cy - lh * len(lines) / 2
        for i, line in enumerate(lines):
            self.text(cx, top + lh * i + size * 0.95, line, size, anchor, bold, italic, fill)

    # Pfeilspitzen (als Polygone – QtSvg kennt keine <marker>)
    def arrow_head(self, tip, origin, kind="arrow", color=None, size=9.0) -> None:
        color = color or self.theme.line
        dx, dy = tip[0] - origin[0], tip[1] - origin[1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        bx, by = tip[0] - ux * size, tip[1] - uy * size
        if kind == "arrow":
            self.polygon([tip, (bx + px * size * 0.45, by + py * size * 0.45),
                          (bx - px * size * 0.45, by - py * size * 0.45)], fill=color, stroke=color, width=1)
        elif kind == "open":                       # offene Spitze (Mermaid „-->>“ / Abhängigkeit)
            self.parts.append(f'<polyline points="{_f(bx + px * size * 0.5)},{_f(by + py * size * 0.5)} '
                              f'{_f(tip[0])},{_f(tip[1])} {_f(bx - px * size * 0.5)},{_f(by - py * size * 0.5)}" '
                              f'fill="none" stroke="{color}" stroke-width="1.4"/>')
        elif kind == "triangle":                   # Vererbung: hohles Dreieck
            s = size * 1.35
            bx2, by2 = tip[0] - ux * s, tip[1] - uy * s
            self.polygon([tip, (bx2 + px * s * 0.55, by2 + py * s * 0.55), (bx2 - px * s * 0.55, by2 - py * s * 0.55)],
                         fill=self.theme.bg, stroke=color, width=1.3)
        elif kind in ("diamond", "diamond_open"):  # Komposition (gefüllt) / Aggregation (hohl)
            s = size * 1.25
            mid = (tip[0] - ux * s, tip[1] - uy * s)
            back = (tip[0] - ux * s * 2, tip[1] - uy * s * 2)
            self.polygon([tip, (mid[0] + px * s * 0.5, mid[1] + py * s * 0.5), back,
                          (mid[0] - px * s * 0.5, mid[1] - py * s * 0.5)],
                         fill=color if kind == "diamond" else self.theme.bg, stroke=color, width=1.3)
        elif kind == "circle":
            r = size * 0.42
            self.ellipse(tip[0] - ux * r, tip[1] - uy * r, r, r, fill=self.theme.bg, stroke=color, width=1.4)
        elif kind == "cross":
            s = size * 0.55
            cx, cy = tip[0] - ux * s, tip[1] - uy * s
            for sign in (1, -1):
                self.line(cx - (ux + sign * px) * s, cy - (uy + sign * py) * s,
                          cx + (ux + sign * px) * s, cy + (uy + sign * py) * s, stroke=color, width=1.6)

    def to_string(self, width: float, height: float, background: bool = False) -> str:
        width, height = max(1.0, width), max(1.0, height)
        bg = f'<rect x="0" y="0" width="{_f(width)}" height="{_f(height)}" fill="{self.theme.bg}"/>' if background else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.2" baseProfile="tiny" width="{_f(width)}" '
                f'height="{_f(height)}" viewBox="0 0 {_f(width)} {_f(height)}">' + bg + "".join(self.parts) + "</svg>")


def smooth_path(points: list[tuple[float, float]]) -> str:
    """Weiche Linie durch alle Punkte (Catmull-Rom → kubische Bézier)."""
    if len(points) < 2:
        return ""
    d = f"M{_f(points[0][0])},{_f(points[0][1])}"
    if len(points) == 2:
        return d + f" L{_f(points[1][0])},{_f(points[1][1])}"
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{_f(c1[0])},{_f(c1[1])} {_f(c2[0])},{_f(c2[1])} {_f(p2[0])},{_f(p2[1])}"
    return d
