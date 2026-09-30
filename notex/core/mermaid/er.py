"""Mermaid-ER-Diagramm (`erDiagram`): Parser + Zeichnen (Krähenfuß-Notation).

Unterstützt: ENTITÄT { typ name PK,FK "Kommentar" }, Beziehungen A ||--o{ B : "Text" mit |o || }o }| bzw.
o| || o{ |{ an den Enden, -- (identifizierend) und .. (nicht identifizierend), Alias ENTITÄT["Anzeige"], direction.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from notex.core.mermaid import layout as lay
from notex.core.mermaid.common import MAX_ELEMENTS, Diagram, Line, MermaidError, unquote
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, block_size, smooth_path, text_width

ENT = r"[\wÀ-￿\-]+"
REL_RE = re.compile(r"^(?P<a>" + ENT + r")\s*(?P<l>\|o|\|\||\}o|\}\|)(?P<line>--|\.\.)(?P<r>o\||\|\||o\{|\|\{)\s*"
                    r"(?P<b>" + ENT + r")\s*(?::\s*(?P<label>.*))?$")
CARD = {"|o": "zero_one", "o|": "zero_one", "||": "one", "}o": "zero_many", "o{": "zero_many",
        "}|": "one_many", "|{": "one_many"}


@dataclass
class Attribute:
    type: str
    name: str
    keys: str = ""
    comment: str = ""


@dataclass
class Entity:
    name: str
    label: str
    attributes: list[Attribute] = field(default_factory=list)


@dataclass
class Relationship:
    a: str
    b: str
    card_a: str
    card_b: str
    identifying: bool
    label: str


@dataclass
class ERModel:
    entities: dict[str, Entity] = field(default_factory=dict)
    relations: list[Relationship] = field(default_factory=list)
    direction: str = "TB"


def parse(lines: list[Line]) -> ERModel:
    model = ERModel()
    body: Entity | None = None

    def entity(name: str) -> Entity:
        m = re.match(r'^(' + ENT + r')\s*\[\s*"?(.*?)"?\s*\]$', name)
        key, label = (m.group(1), m.group(2)) if m else (name, name)
        if key not in model.entities:
            model.entities[key] = Entity(key, label)
        elif m:
            model.entities[key].label = label
        return model.entities[key]

    for line in lines[1:]:
        s = line.text.strip()
        if body is not None:
            if s == "}":
                body = None
                continue
            m = re.match(r'^(\S+)\s+(\S+)\s*((?:PK|FK|UK)(?:\s*,\s*(?:PK|FK|UK))*)?\s*(?:"([^"]*)")?$', s)
            if not m:
                raise MermaidError(f"Attribut nicht verstanden: „{s[:50]}“ (Form: typ name PK \"Kommentar\")", line.no)
            body.attributes.append(Attribute(m.group(1), m.group(2), (m.group(3) or "").replace(" ", ""),
                                             m.group(4) or ""))
            continue
        m = re.match(r"^direction\s+(TB|TD|BT|LR|RL)$", s, re.IGNORECASE)
        if m:
            model.direction = "TB" if m.group(1).upper() == "TD" else m.group(1).upper()
            continue
        m = re.match(r'^(' + ENT + r'(?:\s*\[[^\]]*\])?)\s*\{\s*(\})?$', s)
        if m:
            e = entity(m.group(1))
            body = None if m.group(2) else e
            continue
        m = REL_RE.match(s)
        if m:
            a, b = entity(m.group("a")).name, entity(m.group("b")).name
            model.relations.append(Relationship(a, b, CARD[m.group("l")], CARD[m.group("r")],
                                                m.group("line") == "--", unquote(m.group("label") or "")))
            continue
        if re.match(r"^" + ENT + r"$", s):
            entity(s)
            continue
        if re.match(r"^(style|classDef|class)\b", s):
            continue
        raise MermaidError(f"Nicht verstanden: „{s[:60]}“", line.no)
    if body is not None:
        raise MermaidError(f"Entität „{body.name}“: schließende „}}“ fehlt")
    if len(model.entities) + len(model.relations) > MAX_ELEMENTS:
        raise MermaidError("Diagramm zu groß")
    return model


# ---- Zeichnen --------------------------------------------------------------------------------------------------------
ROW_FS = FONT_SIZE * 0.85
ROW_H = ROW_FS * 1.55


def _columns(e: Entity) -> tuple[float, float, float, float]:
    c1 = max((text_width(a.type, ROW_FS) for a in e.attributes), default=0) + 16
    c2 = max((text_width(a.name, ROW_FS) for a in e.attributes), default=0) + 16
    c3 = max((text_width(a.keys, ROW_FS, True) for a in e.attributes), default=0) + (16 if any(a.keys for a in e.attributes) else 0)
    c4 = max((text_width(a.comment, ROW_FS) for a in e.attributes), default=0) + (16 if any(a.comment for a in e.attributes) else 0)
    return c1, c2, c3, c4


def _size(e: Entity) -> tuple[float, float]:
    head = text_width(e.label, FONT_SIZE, True) + 32
    cols = sum(_columns(e))
    return max(head, cols, 110.0), FONT_SIZE * 1.3 + 16 + len(e.attributes) * ROW_H


def _crow(svg: Svg, tip, before, card: str, color: str) -> None:
    """Krähenfuß am Ende `tip` (Richtung von `before` kommend)."""
    dx, dy = tip[0] - before[0], tip[1] - before[1]
    d = math.hypot(dx, dy) or 1
    ux, uy, px, py = dx / d, dy / d, -dy / d, dx / d

    def at(dist, side=0.0):
        return (tip[0] - ux * dist + px * side, tip[1] - uy * dist + py * side)
    many = card in ("zero_many", "one_many")
    if many:
        base = at(14)
        for side in (-8, 0, 8):
            end = (tip[0] + px * side, tip[1] + py * side)
            svg.line(base[0], base[1], end[0], end[1], color, 1.3)
    else:
        a, b = at(7, -7), at(7, 7)
        svg.line(a[0], a[1], b[0], b[1], color, 1.3)
    if card in ("one", "one_many"):
        a, b = at(19 if many else 13, -7), at(19 if many else 13, 7)
        svg.line(a[0], a[1], b[0], b[1], color, 1.3)
    if card in ("zero_one", "zero_many"):
        c = at(24 if many else 18)
        svg.ellipse(c[0], c[1], 5, 5, svg.theme.bg, color, 1.3)


def render(model: ERModel, theme: Theme, title: str = "") -> Diagram:
    t = theme
    if not model.entities:
        raise MermaidError("Keine Entitäten")
    sizes = {n: _size(e) for n, e in model.entities.items()}
    nodes = [lay.LNode(n, *sizes[n]) for n in model.entities]
    edges = []
    for i, r in enumerate(model.relations):
        lw, lh = block_size(r.label, FONT_SIZE * 0.85) if r.label else (0, 0)
        edges.append(lay.LEdge(i, r.a, r.b, lw + 10 if lw else 0, lh + 4 if lh else 0))
    L = lay.layout(nodes, edges, [], {}, model.direction, nodesep=46, ranksep=60)
    svg = Svg(t)
    shift = 30.0 if title else 0.0
    if title:
        svg.text(L.width / 2, 20, title, FONT_SIZE * 1.15, bold=True)
    for e in edges:
        r = model.relations[e.key]
        pts = [(x, y + shift) for x, y in L.edges.get(e.key, [])]
        if len(pts) < 2:
            continue
        svg.path(smooth_path(pts), None, t.line, 1.3, "" if r.identifying else "6,4")
        _crow(svg, pts[0], pts[1], r.card_a, t.line)
        _crow(svg, pts[-1], pts[-2], r.card_b, t.line)
        if r.label and e.key in L.labels:
            lx, ly = L.labels[e.key]
            lw, lh = block_size(r.label, FONT_SIZE * 0.85)
            svg.rect(lx - lw / 2 - 5, ly + shift - lh / 2 - 2, lw + 10, lh + 4, t.bg, None, 0, rx=3)
            svg.text_block(lx, ly + shift, r.label, FONT_SIZE * 0.85)
    for name, ent in model.entities.items():
        cx, cy = L.nodes[name]
        w, h = sizes[name]
        x, y = cx - w / 2, cy - h / 2 + shift
        head = FONT_SIZE * 1.3 + 16
        svg.rect(x, y, w, h, t.bg, t.node_stroke, 1.3, rx=3)
        svg.rect(x, y, w, head, t.node_fill, t.node_stroke, 1.3, rx=3)
        svg.text(cx, y + head / 2 + FONT_SIZE * 0.35, ent.label, FONT_SIZE, bold=True)
        c1, c2, c3, _c4 = _columns(ent)
        for i, a in enumerate(ent.attributes):
            ry = y + head + i * ROW_H
            if i % 2:
                svg.rect(x + 1, ry, w - 2, ROW_H, t.cluster_fill, None, 0)
            base = ry + ROW_H / 2 + ROW_FS * 0.35
            svg.text(x + 8, base, a.type, ROW_FS, anchor="start", fill=t.muted)
            svg.text(x + c1 + 8, base, a.name, ROW_FS, anchor="start")
            if a.keys:
                svg.text(x + c1 + c2 + 8, base, a.keys, ROW_FS, anchor="start", bold=True, fill=t.accent)
            if a.comment:
                svg.text(x + c1 + c2 + c3 + 8, base, a.comment, ROW_FS, anchor="start", italic=True, fill=t.muted)
    return Diagram("er", svg.to_string(L.width, L.height + shift), L.width, L.height + shift, title)
