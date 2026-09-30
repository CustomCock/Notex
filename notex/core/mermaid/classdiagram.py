"""Mermaid-Klassendiagramm (`classDiagram`): Parser + Zeichnen.

Unterstützt: class X / class X { … } / class X~T~ / X : +member / <<interface>> (auch als eigene Zeile),
Beziehungen <|-- *-- o-- --> -- ..> ..|> .. (beidseitig spiegelbar, z. B. --|>), Kardinalitäten "1" "*",
Beschriftung nach „:“, direction, namespace { … } (Klassen werden gezeichnet, der Rahmen als Gruppe).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from notex.core.mermaid import layout as lay
from notex.core.mermaid.common import MAX_ELEMENTS, Diagram, Line, MermaidError, unquote
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, block_size, smooth_path, text_width

NAME = r"[A-Za-z_À-￿][\wÀ-￿.]*(?:~[^~]+~)?"
REL_RE = re.compile(r"^(?P<a>" + NAME + r")\s*(?:\"(?P<ca>[^\"]*)\")?\s*(?P<l><\||\*|o|<)?(?P<line>--|\.\.)"
                    r"(?P<r>\|>|\*|o|>)?\s*(?:\"(?P<cb>[^\"]*)\")?\s*(?P<b>" + NAME + r")\s*(?::\s*(?P<label>.*))?$")


@dataclass
class Klass:
    name: str
    label: str
    annotation: str = ""
    attributes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)


@dataclass
class Relation:
    a: str
    b: str
    left: str | None       # Markierung am Ende bei a
    right: str | None      # Markierung am Ende bei b
    dotted: bool
    label: str = ""
    card_a: str = ""
    card_b: str = ""


@dataclass
class ClassModel:
    classes: dict[str, Klass] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    direction: str = "TB"
    namespaces: dict[str, list[str]] = field(default_factory=dict)
    membership: dict[str, str] = field(default_factory=dict)


MARK = {"<|": "triangle", "|>": "triangle", "*": "diamond", "o": "diamond_open", "<": "arrow", ">": "arrow"}


def _display(name: str) -> str:
    return re.sub(r"~([^~]+)~", r"<\1>", name)


def parse(lines: list[Line]) -> ClassModel:
    model = ClassModel()
    body_of: str | None = None
    ns_stack: list[str] = []

    def klass(name: str) -> Klass:
        key = re.sub(r"~[^~]+~", "", name)
        if key not in model.classes:
            model.classes[key] = Klass(key, _display(name))
            if ns_stack:
                model.membership[key] = ns_stack[-1]
                model.namespaces.setdefault(ns_stack[-1], []).append(key)
        elif "~" in name:
            model.classes[key].label = _display(name)
        return model.classes[key]

    def add_member(k: Klass, member: str) -> None:
        member = member.strip()
        if not member:
            return
        if member.startswith("<<") and member.endswith(">>"):
            k.annotation = member
        elif "(" in member and ")" in member:
            k.methods.append(_display(member))
        else:
            k.attributes.append(_display(member))

    for line in lines[1:]:
        s = line.text.strip()
        if body_of is not None:
            if s == "}":
                body_of = None
            else:
                add_member(model.classes[body_of], s)
            continue
        m = re.match(r"^direction\s+(TB|TD|BT|LR|RL)$", s, re.IGNORECASE)
        if m:
            model.direction = "TB" if m.group(1).upper() == "TD" else m.group(1).upper()
            continue
        m = re.match(r"^namespace\s+(\S+)\s*\{$", s)
        if m:
            ns_stack.append(m.group(1))
            continue
        if s == "}" and ns_stack:
            ns_stack.pop()
            continue
        m = re.match(r"^class\s+(" + NAME + r")\s*(?:\[\"?([^\]\"]*)\"?\])?\s*(\{)?\s*(?::::\w+)?\s*$", s)
        if m:
            k = klass(m.group(1))
            if m.group(2):
                k.label = m.group(2)
            if m.group(3):
                body_of = k.name
            continue
        m = re.match(r"^<<(.+?)>>\s*(" + NAME + r")$", s)
        if m:
            klass(m.group(2)).annotation = f"<<{m.group(1)}>>"
            continue
        m = REL_RE.match(s)
        if m:
            a, b = klass(m.group("a")).name, klass(m.group("b")).name
            model.relations.append(Relation(a, b, MARK.get(m.group("l") or ""), MARK.get(m.group("r") or ""),
                                            m.group("line") == "..", unquote(m.group("label") or ""),
                                            m.group("ca") or "", m.group("cb") or ""))
            continue
        m = re.match(r"^(" + NAME + r")\s*:\s*(.+)$", s)
        if m:
            add_member(klass(m.group(1)), m.group(2))
            continue
        if re.match(r"^(note|link|click|callback|cssClass|style|classDef)\b", s):
            continue
        raise MermaidError(f"Nicht verstanden: „{s[:60]}“", line.no)
    if body_of is not None:
        raise MermaidError(f"Klasse „{body_of}“: schließende „}}“ fehlt")
    if len(model.classes) + len(model.relations) > MAX_ELEMENTS:
        raise MermaidError("Diagramm zu groß")
    return model


# ---- Zeichnen --------------------------------------------------------------------------------------------------------
MEMBER_FS = FONT_SIZE * 0.85


def _box_size(k: Klass) -> tuple[float, float, float, float]:
    head_lines = ([k.annotation] if k.annotation else []) + [k.label]
    head_w = max(text_width(k.label, FONT_SIZE, True), text_width(k.annotation, MEMBER_FS))
    head_h = len(head_lines) * FONT_SIZE * 1.3 + 10
    rows = k.attributes + k.methods
    member_w = max((text_width(r, MEMBER_FS) for r in rows), default=0)
    attr_h = max(len(k.attributes), 0) * MEMBER_FS * 1.35 + 10
    meth_h = max(len(k.methods), 0) * MEMBER_FS * 1.35 + 10
    return max(head_w, member_w) + 28, head_h + attr_h + meth_h, head_h, attr_h


def render(model: ClassModel, theme: Theme, title: str = "") -> Diagram:
    t = theme
    if not model.classes:
        raise MermaidError("Keine Klassen")
    sizes = {k.name: _box_size(k) for k in model.classes.values()}
    nodes = [lay.LNode(n, s[0], s[1]) for n, s in sizes.items()]
    edges = []
    flipped: set[int] = set()
    for i, r in enumerate(model.relations):
        lw, lh = block_size(r.label, FONT_SIZE * 0.85) if r.label else (0, 0)
        # Oberklasse/Ganzes oben: steht die Markierung (Dreieck/Raute) rechts, Richtung fürs Layout umdrehen
        flip = r.right in ("triangle", "diamond", "diamond_open") and not r.left
        src, dst = (r.b, r.a) if flip else (r.a, r.b)
        if flip:
            flipped.add(i)
        edges.append(lay.LEdge(i, src, dst, lw + 8 if lw else 0, lh + 4 if lh else 0))
    clusters = [lay.LCluster(ns, None, None, text_width(ns, FONT_SIZE, True) + 12, FONT_SIZE * 1.3)
                for ns in model.namespaces]
    L = lay.layout(nodes, edges, clusters, model.membership, model.direction, nodesep=40, ranksep=56)
    svg = Svg(t)
    shift = 30.0 if title else 0.0
    if title:
        svg.text(L.width / 2, 20, title, FONT_SIZE * 1.15, bold=True)
    for ns, (x, y, w, h) in L.clusters.items():
        svg.rect(x, y + shift, w, h, t.cluster_fill, t.cluster_stroke, 1.1, rx=6, dash="5,4")
        svg.text(x + 10, y + shift + 8 + FONT_SIZE, ns, FONT_SIZE * 0.95, anchor="start", bold=True)
    for e in edges:
        r = model.relations[e.key]
        pts = [(x, y + shift) for x, y in L.edges.get(e.key, [])]
        if len(pts) < 2:
            continue
        if e.key in flipped:                        # Punkte wieder von a nach b
            pts.reverse()
        svg.path(smooth_path(pts), None, t.line, 1.4, "5,4" if r.dotted else "")
        if r.left:
            svg.arrow_head(pts[0], pts[1], r.left if r.left != "arrow" else "open", t.line, 10)
        if r.right:
            svg.arrow_head(pts[-1], pts[-2], r.right if r.right != "arrow" else "open", t.line, 10)
        if r.label and e.key in L.labels:
            lx, ly = L.labels[e.key]
            lw, lh = block_size(r.label, FONT_SIZE * 0.85)
            svg.rect(lx - lw / 2 - 4, ly + shift - lh / 2 - 2, lw + 8, lh + 4, t.bg, None, 0, rx=3)
            svg.text_block(lx, ly + shift, r.label, FONT_SIZE * 0.85)
        for card, (p, q) in ((r.card_a, (pts[0], pts[1])), (r.card_b, (pts[-1], pts[-2]))):
            if card:
                dx, dy = q[0] - p[0], q[1] - p[1]
                d = max((dx * dx + dy * dy) ** 0.5, 1)
                svg.text(p[0] + dx / d * 18 + 10, p[1] + dy / d * 18 + 4, card, FONT_SIZE * 0.8, fill=t.muted)
    for k in model.classes.values():
        cx, cy = L.nodes[k.name]
        w, h, head_h, attr_h = sizes[k.name]
        x, y = cx - w / 2, cy - h / 2 + shift
        svg.rect(x, y, w, h, t.node_fill, t.node_stroke, 1.3, rx=3)
        yy = y + 6
        if k.annotation:
            svg.text(cx, yy + MEMBER_FS, k.annotation.replace("<<", "«").replace(">>", "»"), MEMBER_FS,
                     italic=True, fill=t.muted)
            yy += FONT_SIZE * 1.3
        svg.text(cx, yy + FONT_SIZE * 0.95, k.label, FONT_SIZE, bold=True)
        svg.line(x, y + head_h, x + w, y + head_h, t.node_stroke, 1.1)
        svg.line(x, y + head_h + attr_h, x + w, y + head_h + attr_h, t.node_stroke, 1.1)
        for i, a in enumerate(k.attributes):
            svg.text(x + 10, y + head_h + 5 + (i + 1) * MEMBER_FS * 1.35 - 3, a, MEMBER_FS, anchor="start")
        for i, m in enumerate(k.methods):
            italic = ")*" in m                          # abstrakt: kursiv; statisch ($) ohne Markierung
            shown = m.replace(")*", ")").replace(")$", ")")
            svg.text(x + 10, y + head_h + attr_h + 5 + (i + 1) * MEMBER_FS * 1.35 - 3, shown,
                     MEMBER_FS, anchor="start", italic=italic)
    return Diagram("class", svg.to_string(L.width, L.height + shift), L.width, L.height + shift, title)
