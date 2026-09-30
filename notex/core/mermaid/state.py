"""Mermaid-Zustandsdiagramm (`stateDiagram` / `stateDiagram-v2`): Parser + Zeichnen.

Unterstützt: [*] Start/Ende (je zusammengesetztem Zustand eigen), A --> B : Text, state "Text" as A, A : Beschreibung,
state A { … } (verschachtelt, eigener direction), <<fork>> <<join>> <<choice>>, note left of/right of (einzeilig
und mehrzeilig bis „end note“), -- (Nebenläufigkeit, Trennlinie wird nicht gezeichnet), classDef/class, direction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from notex.core.mermaid import layout as lay
from notex.core.mermaid.common import MAX_ELEMENTS, Diagram, Line, MermaidError, parse_style, unquote
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, block_size, smooth_path, text_width

SID = r"(?:\[\*\]|[\wÀ-￿.]+)"
TRANS_RE = re.compile(r"^(" + SID + r")\s*-->\s*(" + SID + r")\s*(?::\s*(.*))?$")


@dataclass
class State:
    id: str
    label: str
    kind: str = "state"      # state | start | end | fork | join | choice | note
    desc: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)


@dataclass
class Transition:
    src: str
    dst: str
    label: str = ""
    note: bool = False


@dataclass
class StateModel:
    states: dict[str, State] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)
    composites: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)   # id → (Eltern, Richtung)
    membership: dict[str, str] = field(default_factory=dict)
    direction: str = "TB"
    class_defs: dict[str, dict[str, str]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)                               # zusammengesetzte Zustände


def parse(lines: list[Line]) -> StateModel:
    model = StateModel()
    scope: list[str] = []
    note_open: dict | None = None

    def state(sid: str, as_target: bool = False, as_source: bool = False) -> str:
        if sid == "[*]":
            where = scope[-1] if scope else "root"
            kind = "end" if as_target else "start"
            sid = f"__{kind}_{where}"
            if sid not in model.states:
                model.states[sid] = State(sid, "", kind)
                if scope:
                    model.membership[sid] = scope[-1]
            return sid
        if sid not in model.states and sid not in model.composites:
            model.states[sid] = State(sid, sid)
            if scope:
                model.membership[sid] = scope[-1]
        return sid

    for line in lines[1:]:
        s = line.text.strip()
        if note_open is not None:
            if s.lower() == "end note":
                model.states[note_open["id"]].label = "\n".join(note_open["lines"])
                note_open = None
            else:
                note_open["lines"].append(s)
            continue
        m = re.match(r"^direction\s+(TB|TD|BT|LR|RL)$", s, re.IGNORECASE)
        if m:
            d = "TB" if m.group(1).upper() == "TD" else m.group(1).upper()
            if scope:
                parent, _ = model.composites[scope[-1]]
                model.composites[scope[-1]] = (parent, d)
            else:
                model.direction = d
            continue
        if s == "}":
            if not scope:
                raise MermaidError("„}“ ohne offenen zusammengesetzten Zustand", line.no)
            scope.pop()
            continue
        if s == "--":
            continue
        m = re.match(r'^state\s+"([^"]+)"\s+as\s+([\wÀ-￿.]+)\s*(\{)?$', s)
        if m:
            sid = m.group(2)
            if m.group(3):
                _composite(model, scope, sid, m.group(1))
            else:
                model.states[state(sid)].label = m.group(1)
            continue
        m = re.match(r"^state\s+([\wÀ-￿.]+)\s*(<<(fork|join|choice)>>)?\s*(\{)?$", s)
        if m:
            sid = m.group(1)
            if m.group(4):
                _composite(model, scope, sid, sid)
            else:
                st = model.states[state(sid)]
                if m.group(3):
                    st.kind = m.group(3)
            continue
        m = re.match(r"^note\s+(left of|right of)\s+([\wÀ-￿.]+)\s*(?::\s*(.*))?$", s, re.IGNORECASE)
        if m:
            target = state(m.group(2))
            nid = f"__note_{len(model.states)}"
            model.states[nid] = State(nid, unquote(m.group(3) or ""), "note")
            if target in model.membership:
                model.membership[nid] = model.membership[target]
            model.transitions.append(Transition(target, nid, note=True))
            if m.group(3) is None:
                note_open = {"id": nid, "lines": []}
            continue
        m = re.match(r"^classDef\s+(\w+)\s+(.+)$", s)
        if m:
            model.class_defs[m.group(1)] = parse_style(m.group(2))
            continue
        m = re.match(r"^class\s+([\w,\s]+?)\s+(\w+)$", s)
        if m:
            for sid in m.group(1).split(","):
                model.states[state(sid.strip())].classes.append(m.group(2))
            continue
        m = TRANS_RE.match(s)
        if m:
            a, b = state(m.group(1), as_source=True), state(m.group(2), as_target=True)
            model.transitions.append(Transition(a, b, unquote(m.group(3) or "")))
            continue
        m = re.match(r"^([\wÀ-￿.]+)\s*:\s*(.+)$", s)
        if m:
            st = model.states[state(m.group(1))]
            st.desc.append(unquote(m.group(2)))
            continue
        if re.match(r"^[\wÀ-￿.]+$", s):
            state(s)
            continue
        if re.match(r"^(click|style|accTitle|accDescr)\b", s):
            continue
        raise MermaidError(f"Nicht verstanden: „{s[:60]}“", line.no)
    if scope:
        raise MermaidError(f"Zustand „{scope[-1]}“: schließende „}}“ fehlt")
    if len(model.states) + len(model.transitions) > MAX_ELEMENTS:
        raise MermaidError("Diagramm zu groß")
    return model


def _composite(model: StateModel, scope: list[str], sid: str, label: str) -> None:
    model.states.pop(sid, None)                    # war evtl. schon als einfacher Zustand erwähnt
    model.composites[sid] = (scope[-1] if scope else None, None)
    model.labels[sid] = label
    scope.append(sid)


# ---- Zeichnen --------------------------------------------------------------------------------------------------------
def _size(st: State, horizontal: bool) -> tuple[float, float, str]:
    if st.kind == "start":
        return 18, 18, "circle"
    if st.kind == "end":
        return 22, 22, "circle"
    if st.kind in ("fork", "join"):
        return (8, 70, "rect") if horizontal else (70, 8, "rect")
    if st.kind == "choice":
        return 30, 30, "diamond"
    if st.kind == "note":
        w, h = block_size(st.label or " ", FONT_SIZE * 0.9)
        return w + 20, h + 14, "rect"
    tw, th = block_size(st.label, FONT_SIZE)
    dw = max((text_width(d, FONT_SIZE * 0.85) for d in st.desc), default=0)
    dh = len(st.desc) * FONT_SIZE * 0.85 * 1.3 + (8 if st.desc else 0)
    return max(tw, dw) + 32, th + 20 + dh, "rect"


def render(model: StateModel, theme: Theme, title: str = "") -> Diagram:
    t = theme
    if not model.states:
        raise MermaidError("Keine Zustände")
    horizontal = model.direction in ("LR", "RL")
    sizes = {sid: _size(st, horizontal) for sid, st in model.states.items()}
    nodes = [lay.LNode(sid, w, h, shape) for sid, (w, h, shape) in sizes.items()]
    labels = model.labels
    # Übergänge zu einem zusammengesetzten Zustand an dessen Start/Ende hängen
    edges = []
    for i, tr in enumerate(model.transitions):
        src, dst = tr.src, tr.dst                   # zusammengesetzte Zustände: Kante endet am Rahmen
        lw, lh = block_size(tr.label, FONT_SIZE * 0.85) if tr.label else (0, 0)
        edges.append(lay.LEdge(i, src, dst, lw + 8 if lw else 0, lh + 4 if lh else 0))
    clusters = [lay.LCluster(cid, parent, d, text_width(labels.get(cid, cid), FONT_SIZE, True) + 16, FONT_SIZE * 1.3)
                for cid, (parent, d) in model.composites.items()]
    L = lay.layout(nodes, edges, clusters, model.membership, model.direction, nodesep=36, ranksep=46)
    svg = Svg(t)
    shift = 30.0 if title else 0.0
    if title:
        svg.text(L.width / 2, 20, title, FONT_SIZE * 1.15, bold=True)
    depth = {cid: _depth(model, cid) for cid in model.composites}
    for cid in sorted(L.clusters, key=lambda c: depth[c]):
        x, y, w, h = L.clusters[cid]
        svg.rect(x, y + shift, w, h, t.cluster_fill, t.node_stroke, 1.3, rx=10)
        svg.text(x + w / 2, y + shift + 8 + FONT_SIZE, labels.get(cid, cid), FONT_SIZE, bold=True)
        svg.line(x, y + shift + FONT_SIZE * 1.3 + 10, x + w, y + shift + FONT_SIZE * 1.3 + 10, t.cluster_stroke, 1)
    for e in edges:
        tr = model.transitions[e.key]
        pts = [(x, y + shift) for x, y in L.edges.get(e.key, [])]
        if len(pts) < 2:
            continue
        if tr.note:
            svg.path(smooth_path(pts), None, t.note_stroke, 1.1, "3,3")
            continue
        svg.path(smooth_path(pts), None, t.line, 1.4)
        svg.arrow_head(pts[-1], pts[-2], "arrow", t.line, 9)
        if tr.label and e.key in L.labels:
            lx, ly = L.labels[e.key]
            lw, lh = block_size(tr.label, FONT_SIZE * 0.85)
            svg.rect(lx - lw / 2 - 4, ly + shift - lh / 2 - 2, lw + 8, lh + 4, t.bg, None, 0, rx=3)
            svg.text_block(lx, ly + shift, tr.label, FONT_SIZE * 0.85)
    for sid, st in model.states.items():
        cx, cy = L.nodes[sid]
        cy += shift
        w, h, _shape = sizes[sid]
        style: dict[str, str] = {}
        for c in st.classes:
            style.update(model.class_defs.get(c, {}))
        fill, stroke = style.get("fill", t.node_fill), style.get("stroke", t.node_stroke)
        if st.kind == "start":
            svg.ellipse(cx, cy, 8, 8, t.text, t.text)
        elif st.kind == "end":
            svg.ellipse(cx, cy, 10, 10, t.bg, t.text, 1.5)
            svg.ellipse(cx, cy, 6, 6, t.text, t.text)
        elif st.kind in ("fork", "join"):
            svg.rect(cx - w / 2, cy - h / 2, w, h, t.text, t.text, 1, rx=2)
        elif st.kind == "choice":
            svg.polygon([(cx, cy - 15), (cx + 15, cy), (cx, cy + 15), (cx - 15, cy)], fill, stroke, 1.3)
        elif st.kind == "note":
            svg.rect(cx - w / 2, cy - h / 2, w, h, t.note_fill, t.note_stroke, 1.1, rx=2)
            svg.text_block(cx, cy, st.label, FONT_SIZE * 0.9)
        else:
            svg.rect(cx - w / 2, cy - h / 2, w, h, fill, stroke, 1.3, rx=10)
            if st.desc:
                th = block_size(st.label)[1]
                top = cy - h / 2
                svg.text_block(cx, top + 10 + th / 2, st.label, bold=True, fill=style.get("color", t.text))
                svg.line(cx - w / 2, top + th + 16, cx + w / 2, top + th + 16, stroke, 1)
                for i, d in enumerate(st.desc):
                    svg.text(cx - w / 2 + 10, top + th + 20 + (i + 1) * FONT_SIZE * 0.85 * 1.3 - 3, d,
                             FONT_SIZE * 0.85, anchor="start")
            else:
                svg.text_block(cx, cy, st.label, fill=style.get("color", t.text))
    return Diagram("state", svg.to_string(L.width, L.height + shift), L.width, L.height + shift, title)


def _depth(model: StateModel, cid: str) -> int:
    d, p = 0, model.composites[cid][0]
    while p:
        d, p = d + 1, model.composites.get(p, (None, None))[0]
    return d
