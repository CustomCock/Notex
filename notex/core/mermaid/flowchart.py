"""Mermaid-Flowchart (`graph` / `flowchart`): Parser + Zeichnen.

Unterstützt: Richtung TB/TD/BT/LR/RL, Knotenformen [ ] ( ) ([ ]) [[ ]] [( )] (( )) ((( ))) { } {{ }} [/ /] [\\ \\]
[/ \\] [\\ /] > ], Kanten --> --- -.-> -.- ==> === ~~~ --o --x <--> mit Text (-->|Text| oder -- Text -->),
Längen (---->), Ketten (A --> B --> C), & (A & B --> C), subgraph … end (verschachtelt, eigener `direction`),
classDef / class / :::klasse / style. `click` wird bewusst ignoriert (keine Links/Skripte aus Notizen).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from notex.core.mermaid import layout as lay
from notex.core.mermaid.common import MAX_ELEMENTS, Diagram, Line, MermaidError, parse_style, px, unquote
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, block_size, smooth_path

HEADER = re.compile(r"^\s*(graph|flowchart)(?:\s+(TB|TD|BT|LR|RL))?\s*;?\s*$", re.IGNORECASE)
ID_RE = re.compile(r"[A-Za-z0-9_À-￿][A-Za-z0-9_À-￿]*")
SHAPES = [("(((", ")))", "dcircle"), ("((", "))", "circle"), ("([", "])", "stadium"), ("[[", "]]", "subroutine"),
          ("[(", ")]", "cylinder"), ("[/", "/]", "lean_r"), ("[\\", "\\]", "lean_l"), ("[/", "\\]", "trapezoid"),
          ("[\\", "/]", "trapezoid_alt"), ("{{", "}}", "hexagon"), ("{", "}", "rhombus"), ("(", ")", "round"),
          ("[", "]", "rect"), (">", "]", "flag")]
EDGE_TEXT = re.compile(r"\s*(?P<l><)?(?P<op>--|==|-\.)\s+(?P<txt>[^\s].*?)\s*"
                       r"(?P<close>-{2,}|={2,}|\.+-)(?P<r>[>ox])?(?=[\s\w\"\[(]|$)")
EDGE_PLAIN = re.compile(r"\s*(?P<l>[<ox])?(?P<body>-{2,}|={2,}|-\.+-|~{3,})(?P<r>[>ox])?(?:\s*\|(?P<txt>[^|]*)\|)?")


@dataclass
class Node:
    id: str
    label: str
    shape: str = "rect"
    classes: list[str] = field(default_factory=list)
    style: dict[str, str] = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    line: str = "solid"          # solid | dotted | thick | invisible
    start: str | None = None     # None | arrow | circle | cross
    end: str | None = "arrow"
    length: int = 1


@dataclass
class Subgraph:
    id: str
    title: str
    parent: str | None
    direction: str | None = None
    members: list[str] = field(default_factory=list)


@dataclass
class Flowchart:
    direction: str = "TB"
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    subgraphs: dict[str, Subgraph] = field(default_factory=dict)
    class_defs: dict[str, dict[str, str]] = field(default_factory=dict)
    membership: dict[str, str] = field(default_factory=dict)


# ---- Parser ----------------------------------------------------------------------------------------------------------
class _Parser:
    def __init__(self, lines: list[Line]) -> None:
        self.lines = lines
        self.fc = Flowchart()
        self.stack: list[str] = []
        self.line_no = 0

    def error(self, message: str) -> MermaidError:
        return MermaidError(message, self.line_no)

    def parse(self) -> Flowchart:
        first = self.lines[0]
        m = HEADER.match(first.text)
        if not m:
            self.line_no = first.no
            raise self.error("Erwartet „graph TD“ oder „flowchart LR“")
        self.fc.direction = "TB" if (m.group(2) or "TB").upper() == "TD" else (m.group(2) or "TB").upper()
        for line in self.lines[1:]:
            self.line_no = line.no
            for stmt in _split_statements(line.text):
                self.statement(stmt.strip())
        if self.stack:
            raise MermaidError(f"„subgraph {self.stack[-1]}“ ohne „end“")
        if len(self.fc.nodes) + len(self.fc.edges) > MAX_ELEMENTS:
            raise MermaidError(f"Diagramm zu groß (mehr als {MAX_ELEMENTS} Knoten und Kanten)")
        return self.fc

    def statement(self, s: str) -> None:
        if not s:
            return
        low = s.lower()
        if low == "end":
            if not self.stack:
                raise self.error("„end“ ohne passendes „subgraph“")
            self.stack.pop()
            return
        if low.startswith("subgraph"):
            self.subgraph(s[8:].strip())
            return
        m = re.match(r"^direction\s+(TB|TD|BT|LR|RL)$", s, re.IGNORECASE)
        if m:
            d = "TB" if m.group(1).upper() == "TD" else m.group(1).upper()
            if self.stack:
                self.fc.subgraphs[self.stack[-1]].direction = d
            else:
                self.fc.direction = d
            return
        m = re.match(r"^classDef\s+([\w,]+)\s+(.+)$", s)
        if m:
            for name in m.group(1).split(","):
                self.fc.class_defs[name.strip()] = parse_style(m.group(2))
            return
        m = re.match(r"^class\s+([\w,\s]+?)\s+(\w+)$", s)
        if m:
            for nid in m.group(1).split(","):
                self.node(nid.strip()).classes.append(m.group(2))
            return
        m = re.match(r"^style\s+(\w+)\s+(.+)$", s)
        if m:
            self.node(m.group(1)).style.update(parse_style(m.group(2)))
            return
        if re.match(r"^(linkStyle|click|accTitle|accDescr|callback)\b", s):
            return                                   # bewusst ignoriert
        self.chain(s)

    def subgraph(self, rest: str) -> None:
        m = re.match(r'^(\w+)\s*\[\s*(.*?)\s*\]$', rest)
        if m:
            sid, title = m.group(1), unquote(m.group(2))
        elif re.match(r"^\w+$", rest):
            sid, title = rest, rest
        else:
            title = unquote(rest) or "Subgraph"
            sid = "sg_" + re.sub(r"\W+", "_", title) + f"_{len(self.fc.subgraphs)}"
        parent = self.stack[-1] if self.stack else None
        if sid in self.fc.nodes:                     # ID war schon als Knoten benutzt (z. B. als Kantenziel)
            del self.fc.nodes[sid]
        self.fc.subgraphs[sid] = Subgraph(sid, title, parent)
        self.stack.append(sid)

    def node(self, nid: str, label: str | None = None, shape: str | None = None) -> Node:
        node = self.fc.nodes.get(nid)
        if node is None:
            node = Node(nid, nid)
            self.fc.nodes[nid] = node
        # Wie Mermaid: ein im Subgraphen erwähnter Knoten gehört dorthin (sofern noch keinem anderen zugeordnet)
        if self.stack and nid not in self.fc.subgraphs and nid not in self.fc.membership:
            self.fc.membership[nid] = self.stack[-1]
        if label is not None:
            node.label = label
        if shape is not None:
            node.shape = shape
        return node

    # A[x] -->|t| B & C --> D
    def chain(self, s: str) -> None:
        pos = 0
        group, pos = self.node_group(s, pos)
        if not group:
            raise self.error(f"Nicht verstanden: „{s[:60]}“")
        while True:
            rest = s[pos:]
            if not rest.strip():
                break
            edge, used = _match_edge(rest)
            if edge is None:
                raise self.error(f"Pfeil oder Ende erwartet bei „{rest.strip()[:40]}“")
            pos += used
            nxt, pos = self.node_group(s, pos)
            if not nxt:
                raise self.error("Zielknoten fehlt nach dem Pfeil")
            for a in group:
                for b in nxt:
                    self.fc.edges.append(Edge(a, b, edge.label, edge.line, edge.start, edge.end, edge.length))
            group = nxt

    def node_group(self, s: str, pos: int) -> tuple[list[str], int]:
        ids = []
        while True:
            nid, pos = self.single_node(s, pos)
            if nid is None:
                return ids, pos
            ids.append(nid)
            m = re.match(r"\s*&\s*", s[pos:])
            if not m:
                return ids, pos
            pos += m.end()

    def single_node(self, s: str, pos: int) -> tuple[str | None, int]:
        m = re.match(r"\s*", s[pos:])
        pos += m.end()
        m = ID_RE.match(s, pos)
        if not m:
            return None, pos
        nid = m.group(0)
        pos = m.end()
        label, shape = None, None
        for opener, closer, name in SHAPES:
            if s.startswith(opener, pos):
                end, text = _read_label(s, pos + len(opener), closer)
                if end is not None:
                    label, shape = text, name
                    pos = end
                    break
        klass = re.match(r":::(\w+)", s[pos:])
        if nid in self.fc.subgraphs and shape is None:
            node_id = nid
        else:
            node = self.node(nid, label, shape)
            node_id = node.id
            if klass:
                node.classes.append(klass.group(1))
        if klass:
            pos += klass.end()
        return node_id, pos


def _split_statements(text: str) -> list[str]:
    """An „;“ trennen – aber nicht innerhalb von Anführungszeichen, Klammern oder |Kantentext|."""
    out, depth, quote, pipe, cur = [], 0, False, False, ""
    for ch in text:
        if ch == '"':
            quote = not quote
        elif not quote:
            if ch in "[({":
                depth += 1
            elif ch in "])}":
                depth = max(0, depth - 1)
            elif ch == "|" and depth == 0:
                pipe = not pipe
            elif ch == ";" and depth == 0 and not pipe:
                out.append(cur)
                cur = ""
                continue
        cur += ch
    out.append(cur)
    return out


def _read_label(s: str, start: int, closer: str) -> tuple[int | None, str]:
    rest = s[start:]
    stripped = rest.lstrip()
    if stripped.startswith('"'):
        offset = len(rest) - len(stripped)
        end_quote = stripped.find('"', 1)
        if end_quote == -1:
            return None, ""
        text = stripped[1:end_quote]
        after = stripped[end_quote + 1:].lstrip()
        if after.startswith(closer):
            used = start + offset + end_quote + 1 + (len(stripped[end_quote + 1:]) - len(after)) + len(closer)
            return used, unquote('"' + text + '"')
        return None, ""
    idx = rest.find(closer)
    if idx == -1:
        return None, ""
    return start + idx + len(closer), unquote(rest[:idx])


def _match_edge(rest: str) -> tuple[Edge | None, int]:
    m = EDGE_TEXT.match(rest)                    # „A -- Text --> B“ zuerst (sonst wäre „--“ eine offene Kante)
    if m:
        body = m.group("op") + m.group("close")
        edge = _edge_from(m.group("l"), body, m.group("r"), m.group("txt").strip())
        return edge, m.end()
    m = EDGE_PLAIN.match(rest)
    if m and m.group("body"):
        body = m.group("body")
        edge = _edge_from(m.group("l"), body, m.group("r"), (m.group("txt") or "").strip())
        return edge, m.end()
    return None, 0


def _edge_from(left, body, right, text) -> Edge:
    if "~" in body:
        line = "invisible"
    elif "=" in body:
        line = "thick"
    elif "." in body:
        line = "dotted"
    else:
        line = "solid"
    marks = {">": "arrow", "o": "circle", "x": "cross", "<": "arrow"}
    length = max(1, len(body.replace(".", "")) - 2) if line != "invisible" else 1
    return Edge("", "", unquote(text) if text else "", line, marks.get(left) if left else None,
                marks.get(right) if right else None, length)


def parse(lines: list[Line]) -> Flowchart:
    return _Parser(lines).parse()


# ---- Zeichnen --------------------------------------------------------------------------------------------------------
PAD_X, PAD_Y = 16.0, 10.0


def _node_size(node: Node) -> tuple[float, float]:
    tw, th = block_size(node.label or " ")
    w, h = max(tw + 2 * PAD_X, 44.0), th + 2 * PAD_Y
    s = node.shape
    if s == "rhombus":
        return max(tw * 1.4 + 36, 64.0), max(th * 1.8 + 26, 52.0)
    if s in ("circle", "dcircle"):
        d = max(tw + 24, th + 24, 48.0) + (8 if s == "dcircle" else 0)
        return d, d
    if s == "hexagon":
        return w + h * 0.6, h
    if s in ("lean_r", "lean_l", "trapezoid", "trapezoid_alt"):
        return w + 24, h
    if s == "cylinder":
        return w, h + 16
    if s == "flag":
        return w + 12, h
    if s == "subroutine":
        return w + 14, h
    return w, h


def _layout_shape(shape: str) -> str:
    return {"rhombus": "diamond", "circle": "circle", "dcircle": "circle"}.get(shape, "rect")


def draw_node(svg: Svg, node: Node, cx: float, cy: float, w: float, h: float, fill: str, stroke: str,
              sw: float, dash: str, text_color: str) -> None:
    x, y = cx - w / 2, cy - h / 2
    s = node.shape
    if s in ("rect", "subroutine"):
        svg.rect(x, y, w, h, fill, stroke, sw, rx=3, dash=dash)
        if s == "subroutine":
            svg.line(x + 7, y, x + 7, y + h, stroke, sw)
            svg.line(x + w - 7, y, x + w - 7, y + h, stroke, sw)
    elif s == "round":
        svg.rect(x, y, w, h, fill, stroke, sw, rx=min(12, h / 2), dash=dash)
    elif s == "stadium":
        svg.rect(x, y, w, h, fill, stroke, sw, rx=h / 2, dash=dash)
    elif s in ("circle", "dcircle"):
        svg.ellipse(cx, cy, w / 2, h / 2, fill, stroke, sw)
        if s == "dcircle":
            svg.ellipse(cx, cy, w / 2 - 5, h / 2 - 5, None, stroke, sw)
    elif s == "rhombus":
        svg.polygon([(cx, y), (x + w, cy), (cx, y + h), (x, cy)], fill, stroke, sw)
    elif s == "hexagon":
        k = h * 0.3
        svg.polygon([(x + k, y), (x + w - k, y), (x + w, cy), (x + w - k, y + h), (x + k, y + h), (x, cy)],
                    fill, stroke, sw)
    elif s in ("lean_r", "lean_l", "trapezoid", "trapezoid_alt"):
        k = 12
        pts = {"lean_r": [(x + k, y), (x + w, y), (x + w - k, y + h), (x, y + h)],
               "lean_l": [(x, y), (x + w - k, y), (x + w, y + h), (x + k, y + h)],
               "trapezoid": [(x + k, y), (x + w - k, y), (x + w, y + h), (x, y + h)],
               "trapezoid_alt": [(x, y), (x + w, y), (x + w - k, y + h), (x + k, y + h)]}[s]
        svg.polygon(pts, fill, stroke, sw)
    elif s == "cylinder":
        ry = 8
        svg.path(f"M{x},{y + ry} L{x},{y + h - ry} A{w / 2},{ry} 0 0 0 {x + w},{y + h - ry} L{x + w},{y + ry} "
                 f"A{w / 2},{ry} 0 0 0 {x},{y + ry} Z", fill, stroke, sw)
        svg.path(f"M{x},{y + ry} A{w / 2},{ry} 0 0 0 {x + w},{y + ry}", None, stroke, sw)
    elif s == "flag":
        svg.polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x + 12, cy)], fill, stroke, sw)
    else:
        svg.rect(x, y, w, h, fill, stroke, sw, rx=3)
    offset = 6 if s == "flag" else (4 if s == "cylinder" else 0)
    svg.text_block(cx + offset, cy, node.label, fill=text_color)


def render(fc: Flowchart, theme: Theme, title: str = "") -> Diagram:
    t = theme
    sizes = {n.id: _node_size(n) for n in fc.nodes.values()}
    lnodes = [lay.LNode(n.id, *sizes[n.id], _layout_shape(n.shape)) for n in fc.nodes.values()]
    ledges = []
    for i, e in enumerate(fc.edges):
        lw, lh = block_size(e.label, FONT_SIZE * 0.9) if e.label else (0, 0)
        if (e.src not in fc.nodes and e.src not in fc.subgraphs) or (e.dst not in fc.nodes and e.dst not in fc.subgraphs):
            continue
        ledges.append(lay.LEdge(i, e.src, e.dst, lw + 8 if lw else 0, lh + 4 if lh else 0, e.length))
    clusters = []
    for sg in fc.subgraphs.values():
        tw, th = block_size(sg.title, FONT_SIZE * 0.95, bold=True)
        clusters.append(lay.LCluster(sg.id, sg.parent, sg.direction, tw + 12, th))
    L = lay.layout(lnodes, ledges, clusters, fc.membership, fc.direction)
    svg = Svg(t)
    top = 0.0
    if title:
        top = 30.0
        svg.text(L.width / 2, 20, title, FONT_SIZE * 1.15, bold=True)
    shift = top

    def sy(y):
        return y + shift
    # Subgraphen (äußere zuerst)
    depth = {}
    for sg in fc.subgraphs.values():
        d, p = 0, sg.parent
        while p:
            d, p = d + 1, fc.subgraphs[p].parent if p in fc.subgraphs else None
        depth[sg.id] = d
    for sid in sorted(L.clusters, key=lambda k: depth.get(k, 0)):
        x, y, w, h = L.clusters[sid]
        sg = fc.subgraphs[sid]
        style = fc.class_defs.get(sid, {})
        svg.rect(x, sy(y), w, h, style.get("fill", t.cluster_fill), style.get("stroke", t.cluster_stroke), 1.2, rx=6)
        svg.text(x + w / 2, sy(y) + 8 + FONT_SIZE * 0.95, sg.title, FONT_SIZE * 0.95, bold=True, fill=t.text)
    # Kanten
    for le in ledges:
        e = fc.edges[le.key]
        pts = L.edges.get(le.key)
        if not pts or e.line == "invisible":
            continue
        pts = [(x, sy(y)) for x, y in pts]
        width = 2.6 if e.line == "thick" else 1.4
        dash = "5,4" if e.line == "dotted" else ""
        trim_end = pts[:]
        if e.end:
            trim_end[-1] = _shorten(pts[-1], pts[-2], 3)
        if e.start:
            trim_end[0] = _shorten(pts[0], pts[1], 3)
        svg.path(smooth_path(trim_end), None, t.line, width, dash)
        if e.end:
            svg.arrow_head(pts[-1], pts[-2], e.end, t.line, 9 if e.line != "thick" else 11)
        if e.start:
            svg.arrow_head(pts[0], pts[1], e.start, t.line, 9 if e.line != "thick" else 11)
        if e.label and le.key in L.labels:
            lx, ly = L.labels[le.key]
            lw, lh = block_size(e.label, FONT_SIZE * 0.9)
            svg.rect(lx - lw / 2 - 4, sy(ly) - lh / 2 - 2, lw + 8, lh + 4, t.bg, None, 0, rx=3)
            svg.text_block(lx, sy(ly), e.label, FONT_SIZE * 0.9, fill=t.text)
    # Knoten
    for n in fc.nodes.values():
        cx, cy = L.nodes[n.id]
        w, h = sizes[n.id]
        style: dict[str, str] = {}
        for c in n.classes:
            style.update(fc.class_defs.get(c, {}))
        if "default" in fc.class_defs and not n.classes:
            style.update(fc.class_defs["default"])
        style.update(n.style)
        draw_node(svg, n, cx, sy(cy), w, h, style.get("fill", t.node_fill), style.get("stroke", t.node_stroke),
                  px(style.get("stroke-width", ""), 1.4), style.get("stroke-dasharray", "").replace(" ", ","),
                  style.get("color", t.text))
    return Diagram("flowchart", svg.to_string(L.width, L.height + top), L.width, L.height + top, title)


def _shorten(tip, before, by):
    import math
    dx, dy = tip[0] - before[0], tip[1] - before[1]
    d = math.hypot(dx, dy) or 1
    return (tip[0] - dx / d * by, tip[1] - dy / d * by)
