"""Mermaid-Kreisdiagramm (`pie`): Parser + Zeichnen. Unterstützt title, showData, "Label" : Wert."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from notex.core.mermaid.common import MAX_ELEMENTS, Diagram, Line, MermaidError, unquote
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, text_width


@dataclass
class Pie:
    title: str = ""
    show_data: bool = False
    slices: list[tuple[str, float]] = field(default_factory=list)


def parse(lines: list[Line]) -> Pie:
    pie = Pie()
    head = lines[0].text.strip()
    rest = head[3:].strip()
    if rest.lower().startswith("showdata"):
        pie.show_data = True
        rest = rest[8:].strip()
    if rest.lower().startswith("title"):
        pie.title = unquote(rest[5:].strip())
    for line in lines[1:]:
        s = line.text.strip()
        m = re.match(r"^title\s+(.+)$", s, re.IGNORECASE)
        if m:
            pie.title = unquote(m.group(1))
            continue
        if s.lower() == "showdata":
            pie.show_data = True
            continue
        m = re.match(r'^"([^"]+)"\s*:\s*([-+]?\d+(?:[.,]\d+)?)$', s)
        if m:
            value = float(m.group(2).replace(",", "."))
            if value < 0:
                raise MermaidError("Negative Werte sind in einem Kreisdiagramm nicht möglich", line.no)
            pie.slices.append((m.group(1), value))
            continue
        if re.match(r"^(accTitle|accDescr)\b", s):
            continue
        raise MermaidError(f"Erwartet „\"Name\" : Wert“, gefunden: „{s[:50]}“", line.no)
    if not pie.slices:
        raise MermaidError("Keine Werte im Kreisdiagramm")
    if len(pie.slices) > MAX_ELEMENTS:
        raise MermaidError("Zu viele Werte")
    return pie


def _fmt(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def render(pie: Pie, theme: Theme, title: str = "") -> Diagram:
    t = theme
    title = pie.title or title
    total = sum(v for _, v in pie.slices)
    if total <= 0:
        raise MermaidError("Summe der Werte ist 0")
    r = 130.0
    top = 44.0 if title else 14.0
    cx, cy = 14 + r, top + r
    svg = Svg(t)
    angle = -math.pi / 2
    legend_x = cx + r + 34
    fs = FONT_SIZE * 0.92
    labels = []
    for i, (label, value) in enumerate(pie.slices):
        color = t.series[i % len(t.series)]
        frac = value / total
        sweep = frac * 2 * math.pi
        if frac >= 0.9999:
            svg.ellipse(cx, cy, r, r, color, t.bg, 1.5)
        elif frac > 0:
            x1, y1 = cx + r * math.cos(angle), cy + r * math.sin(angle)
            x2, y2 = cx + r * math.cos(angle + sweep), cy + r * math.sin(angle + sweep)
            large = 1 if sweep > math.pi else 0
            svg.path(f"M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z",
                     color, t.bg, 1.5)
        if frac >= 0.04:                              # Prozent in größere Stücke schreiben
            mid = angle + sweep / 2
            labels.append((cx + r * 0.62 * math.cos(mid), cy + r * 0.62 * math.sin(mid), f"{frac * 100:.0f} %"))
        angle += sweep
    for x, y, text in labels:
        svg.text(x, y + 5, text, FONT_SIZE * 0.9, bold=True, fill="#ffffff")
    lw = 0.0
    for i, (label, value) in enumerate(pie.slices):
        y = top + 12 + i * 24
        svg.rect(legend_x, y - 11, 14, 14, t.series[i % len(t.series)], None, 0, rx=2)
        text = f"{label}  [{_fmt(value)}]" if pie.show_data else label
        svg.text(legend_x + 22, y + 1, text, fs, anchor="start")
        lw = max(lw, text_width(text, fs))
    width = legend_x + 22 + lw + 14
    height = max(cy + r + 14, top + 12 + len(pie.slices) * 24)
    if title:
        svg.text(width / 2, 26, title, FONT_SIZE * 1.15, bold=True)
    return Diagram("pie", svg.to_string(width, height), width, height, title)
