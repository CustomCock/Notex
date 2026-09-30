"""Mermaid-Sequenzdiagramm (`sequenceDiagram`): Parser + Zeichnen.

Unterstützt: participant/actor (mit „as“-Alias), Nachrichten ->  -->  ->>  -->>  -x  --x  -)  --)  <<->>  <<-->>,
Aktivierung (activate/deactivate, +/- an der Nachricht), Notizen (left of / right of / over A,B), Blöcke
loop / alt+else / opt / par+and / critical+option / break / rect, autonumber, title, box … end (Gruppierung wird
gelesen, aber nicht gezeichnet), create/destroy (Schlüsselwort wird ignoriert).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from notex.core.mermaid.common import MAX_ELEMENTS, Diagram, Line, MermaidError, unquote
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, block_size, text_width

ARROWS = ["<<-->>", "<<->>", "-->>", "->>", "-->", "->", "--x", "-x", "--)", "-)"]
MSG_RE = re.compile(r"^(?P<a>[^\s:<>+\-][^:<>]*?)\s*(?P<arrow>" + "|".join(re.escape(a) for a in ARROWS) +
                    r")\s*(?P<mod>[+-])?\s*(?P<b>[^:+\-][^:]*?)\s*(?::\s*(?P<text>.*))?$")
BLOCKS = ("loop", "alt", "opt", "par", "critical", "break", "rect")


@dataclass
class Participant:
    id: str
    label: str
    kind: str = "participant"      # participant | actor


@dataclass
class Message:
    src: str
    dst: str
    text: str
    dotted: bool
    head: str | None               # arrow | cross | open | None
    both: bool = False
    activate: bool = False
    deactivate: bool = False


@dataclass
class Note:
    position: str                  # left | right | over
    targets: list[str]
    text: str


@dataclass
class Event:
    kind: str                      # msg | note | activate | deactivate | start | else | end
    data: object = None


@dataclass
class Sequence:
    participants: dict[str, Participant] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    autonumber: bool = False
    title: str = ""


def parse(lines: list[Line]) -> Sequence:
    seq = Sequence()
    stack: list[str] = []

    def participant(pid: str) -> str:
        pid = pid.strip()
        if pid not in seq.participants:
            seq.participants[pid] = Participant(pid, pid)
        return pid

    for line in lines[1:]:
        s = line.text.strip()
        try:
            _statement(s, seq, stack, participant)
        except MermaidError as error:
            error.line = error.line or line.no
            raise
    if stack:
        raise MermaidError(f"Block „{stack[-1]}“ ohne „end“")
    if len(seq.events) > MAX_ELEMENTS * 2:
        raise MermaidError("Diagramm zu groß")
    return seq


def _statement(s: str, seq: Sequence, stack: list[str], participant) -> None:
    low = s.lower()
    if low.startswith(("create ", "destroy ")):
        if low.startswith("destroy "):
            return
        s = s[7:].strip()
        low = s.lower()
    m = re.match(r"^title\s*:?\s*(.+)$", s, re.IGNORECASE)
    if m:
        seq.title = unquote(m.group(1))
        return
    if low == "autonumber" or low.startswith("autonumber "):
        seq.autonumber = True
        return
    m = re.match(r"^(participant|actor)\s+(.+?)(?:\s+as\s+(.+))?$", s, re.IGNORECASE)
    if m:
        pid = unquote(m.group(2))
        label = unquote(m.group(3)) if m.group(3) else pid
        if pid in seq.participants:
            seq.participants[pid].label = label
            seq.participants[pid].kind = m.group(1).lower()
        else:
            seq.participants[pid] = Participant(pid, label, m.group(1).lower())
        return
    m = re.match(r"^(activate|deactivate)\s+(.+)$", s, re.IGNORECASE)
    if m:
        seq.events.append(Event(m.group(1).lower(), participant(m.group(2))))
        return
    m = re.match(r"^note\s+(left of|right of|over)\s+([^:]+?)\s*:\s*(.*)$", s, re.IGNORECASE)
    if m:
        targets = [participant(t) for t in m.group(2).split(",")]
        seq.events.append(Event("note", Note(m.group(1).split()[0].lower(), targets, unquote(m.group(3)))))
        return
    word = low.split(" ", 1)[0]
    if word in BLOCKS or word == "box":
        label = s[len(word):].strip()
        stack.append(word)
        if word != "box":
            seq.events.append(Event("start", (word, unquote(label))))
        return
    if word in ("else", "and", "option"):
        if not stack:
            raise MermaidError(f"„{word}“ außerhalb eines Blocks")
        seq.events.append(Event("else", (word, unquote(s[len(word):].strip()))))
        return
    if low == "end":
        if not stack:
            raise MermaidError("„end“ ohne passenden Block")
        if stack.pop() != "box":
            seq.events.append(Event("end"))
        return
    if low.startswith(("links ", "link ", "properties ", "details ")):
        return                                         # Menüs/Links bewusst ignoriert
    m = MSG_RE.match(s)
    if m:
        arrow = m.group("arrow")
        a, b = participant(m.group("a")), participant(m.group("b"))
        head = "cross" if arrow.endswith("x") else ("open" if arrow.endswith(")") else
                                                    ("arrow" if arrow.endswith(">>") else None))
        msg = Message(a, b, unquote(m.group("text") or ""), "--" in arrow, head, arrow.startswith("<<"),
                      m.group("mod") == "+", m.group("mod") == "-")
        seq.events.append(Event("msg", msg))
        return
    raise MermaidError(f"Nicht verstanden: „{s[:60]}“")


# ---- Zeichnen --------------------------------------------------------------------------------------------------------
BOX_H = 38.0
GAP = 46.0
MSG_FS = FONT_SIZE * 0.92


def render(seq: Sequence, theme: Theme, title: str = "") -> Diagram:
    t = theme
    title = seq.title or title
    parts = list(seq.participants.values())
    if not parts:
        raise MermaidError("Keine Teilnehmer")
    col = {p.id: i for i, p in enumerate(parts)}
    widths = [max(text_width(p.label, FONT_SIZE, True) + 28, 84.0) for p in parts]
    # Mindestabstände zwischen benachbarten Spalten (Mitte zu Mitte)
    need = [widths[i] / 2 + widths[i + 1] / 2 + GAP for i in range(len(parts) - 1)]
    for ev in seq.events:
        if ev.kind == "msg":
            m: Message = ev.data
            i, j = sorted((col[m.src], col[m.dst]))
            tw = max((text_width(line, MSG_FS) for line in m.text.split("<br>")), default=0) + 36
            if i == j:
                if i < len(need):
                    need[i] = max(need[i], tw + widths[i] / 2 + 16)
            else:
                span = sum(need[i:j])
                if span < tw:
                    extra = (tw - span) / (j - i)
                    for k in range(i, j):
                        need[k] += extra
        elif ev.kind == "note":
            n: Note = ev.data
            nw = block_size(n.text, MSG_FS)[0] + 24
            i = col[n.targets[0]]
            if n.position == "right" and i < len(need):
                need[i] = max(need[i], nw + 20)
            elif n.position == "left" and i > 0:
                need[i - 1] = max(need[i - 1], nw + 20)
    left = max(widths[0] / 2, 40.0) + 12
    for ev in seq.events:                             # Notiz links vom ersten Teilnehmer braucht Platz
        if ev.kind == "note" and ev.data.position == "left" and col[ev.data.targets[0]] == 0:
            left = max(left, block_size(ev.data.text, MSG_FS)[0] + 50)
    xs = [left]
    for gap in need:
        xs.append(xs[-1] + gap)
    top_title = 34.0 if title else 0.0
    y0 = top_title + BOX_H + (22 if any(p.kind == "actor" for p in parts) else 0) + 26

    svg = Svg(t)
    layer_bg: list[tuple] = []      # Blockrahmen (hinter allem)
    acts: dict[str, list[float]] = {p.id: [] for p in parts}
    act_boxes: list[tuple] = []
    items: list[tuple] = []          # (Art, Daten…) zum späteren Zeichnen
    blocks: list[dict] = []
    y = y0
    number = 0

    def act_offset(pid: str) -> float:
        return 5.0 * len(acts[pid])

    for ev in seq.events:
        if ev.kind == "msg":
            m = ev.data
            number += 1
            th = block_size(m.text, MSG_FS)[1] if m.text else 0
            y += th + 10
            i, j = col[m.src], col[m.dst]
            for b in blocks:
                b["cols"].update((i, j))
            if i == j:
                x = xs[i] + act_offset(m.src)
                items.append(("self", x, y, m, number))
                y += 30
            else:
                x1 = xs[i] + (act_offset(m.src) if j > i else -act_offset(m.src))
                if m.activate:
                    acts[m.dst].append(y)
                x2 = xs[j] + (-act_offset(m.dst) if j > i else act_offset(m.dst))
                items.append(("msg", x1, x2, y, m, number))
            if m.deactivate and acts[m.src]:
                start = acts[m.src].pop()
                act_boxes.append((m.src, start, y + 6, len(acts[m.src])))
            y += 18
        elif ev.kind == "activate":
            acts[ev.data].append(y)
        elif ev.kind == "deactivate":
            if acts[ev.data]:
                start = acts[ev.data].pop()
                act_boxes.append((ev.data, start, y, len(acts[ev.data])))
        elif ev.kind == "note":
            n = ev.data
            nw, nh = block_size(n.text, MSG_FS)
            nw, nh = nw + 20, nh + 14
            idx = [col[x] for x in n.targets]
            for b in blocks:
                b["cols"].update(idx)
            if n.position == "over":
                a, b2 = min(idx), max(idx)
                cx = (xs[a] + xs[b2]) / 2
                nw = max(nw, xs[b2] - xs[a] + 50)
                nx = cx - nw / 2
            elif n.position == "right":
                nx = xs[idx[0]] + 12
            else:
                nx = xs[idx[0]] - 12 - nw
            y += 8
            items.append(("note", nx, y, nw, nh, n))
            y += nh + 12
        elif ev.kind == "start":
            kind, label = ev.data
            y += 10
            blocks.append({"kind": kind, "label": label, "y": y, "cols": set(), "elses": []})
            y += 30
        elif ev.kind == "else":
            if blocks:
                blocks[-1]["elses"].append((y + 4, ev.data[1]))
            y += 30
        elif ev.kind == "end":
            if blocks:
                b = blocks.pop()
                y += 8
                layer_bg.append((b, y, len(blocks)))
                for outer in blocks:
                    outer["cols"].update(b["cols"])
            y += 12
    for pid, starts in acts.items():                  # offene Aktivierungen bis zum Ende
        for k, start in enumerate(starts):
            act_boxes.append((pid, start, y + 6, k))
    bottom = y + 16
    width = xs[-1] + max(widths[-1] / 2, 40) + 12
    for kind, *rest in items:                         # Notizen/Selbstnachrichten rechts außen berücksichtigen
        if kind == "note":
            width = max(width, rest[0] + rest[2] + 12)
        elif kind == "self":
            width = max(width, rest[0] + 40 + text_width(rest[2].text, MSG_FS))
    height = bottom + BOX_H + (22 if any(p.kind == "actor" for p in parts) else 0) + 10

    if title:
        svg.text(width / 2, 22, title, FONT_SIZE * 1.15, bold=True)
    # Blockrahmen
    for b, end_y, depth in layer_bg:
        cols = sorted(b["cols"]) or list(range(len(parts)))
        x1 = xs[cols[0]] - widths[cols[0]] / 2 - 10 + depth * 6
        x2 = xs[cols[-1]] + widths[cols[-1]] / 2 + 10 - depth * 6
        fill = t.cluster_fill if b["kind"] != "rect" else t.note_fill
        svg.rect(x1, b["y"], x2 - x1, end_y - b["y"], fill, t.cluster_stroke, 1.1, rx=4)
        tag = b["kind"]
        tw = text_width(tag, FONT_SIZE * 0.8, True) + 14
        svg.polygon([(x1, b["y"]), (x1 + tw, b["y"]), (x1 + tw, b["y"] + 13), (x1 + tw - 6, b["y"] + 20),
                     (x1, b["y"] + 20)], t.node_fill, t.cluster_stroke, 1.1)
        svg.text(x1 + 7, b["y"] + 14, tag, FONT_SIZE * 0.8, anchor="start", bold=True, fill=t.text)
        if b["label"]:
            svg.text((x1 + x2) / 2 + tw / 2, b["y"] + 15, f"[{b['label']}]", FONT_SIZE * 0.85, bold=True,
                     fill=t.text)
        for ey, label in b["elses"]:
            svg.line(x1, ey, x2, ey, t.cluster_stroke, 1.1, "4,3")
            if label:
                svg.text((x1 + x2) / 2, ey + 16, f"[{label}]", FONT_SIZE * 0.85, bold=True, fill=t.text)
    # Lebenslinien
    for p in parts:
        x = xs[col[p.id]]
        svg.line(x, top_title + BOX_H + (22 if p.kind == "actor" else 0), x, bottom, t.muted, 1.0, "4,4")
    for pid, start, end, depth in act_boxes:
        x = xs[col[pid]] - 5 + depth * 5
        svg.rect(x, start - 4, 10, max(8.0, end - start), t.node_fill, t.node_stroke, 1.1)
    # Nachrichten und Notizen
    for kind, *rest in items:
        if kind == "msg":
            x1, x2, y, m, num = rest
            dash = "5,4" if m.dotted else ""
            direction = 1 if x2 > x1 else -1
            end_x = x2 - direction * (3 if m.head else 0)
            start_x = x1 + direction * (3 if m.both else 0)
            svg.line(start_x, y, end_x, y, t.line, 1.4, dash)
            if m.head:
                svg.arrow_head((x2, y), (x1, y), m.head, t.line, 9)
            if m.both:
                svg.arrow_head((x1, y), (x2, y), "arrow", t.line, 9)
            if m.text:
                th = block_size(m.text, MSG_FS)[1]
                svg.text_block((x1 + x2) / 2, y - th / 2 - 5, m.text, MSG_FS)
            if seq.autonumber:
                _number(svg, x1, y, num, t)
        elif kind == "self":
            x, y, m, num = rest
            svg.path(f"M{x},{y} C{x + 46},{y - 8} {x + 46},{y + 30} {x + 4},{y + 26}", None, t.line, 1.4,
                     "5,4" if m.dotted else "")
            if m.head:
                svg.arrow_head((x + 2, y + 26), (x + 30, y + 24), m.head, t.line, 9)
            if m.text:
                th = block_size(m.text, MSG_FS)[1]
                svg.text_block(x + 50, y - th / 2 + 4, m.text, MSG_FS, anchor="start")
            if seq.autonumber:
                _number(svg, x, y, num, t)
        elif kind == "note":
            nx, ny, nw, nh, n = rest
            svg.rect(nx, ny, nw, nh, t.note_fill, t.note_stroke, 1.1, rx=2)
            svg.text_block(nx + nw / 2, ny + nh / 2, n.text, MSG_FS)
    # Teilnehmer oben und unten
    for p in parts:
        x, w = xs[col[p.id]], widths[col[p.id]]
        for top in (top_title, bottom):
            if p.kind == "actor":
                _actor(svg, x, top, p.label, t)
            else:
                svg.rect(x - w / 2, top, w, BOX_H, t.node_fill, t.node_stroke, 1.3, rx=4)
                svg.text_block(x, top + BOX_H / 2, p.label, bold=True)
    return Diagram("sequence", svg.to_string(width, height), width, height, title)


def _number(svg: Svg, x: float, y: float, num: int, t: Theme) -> None:
    svg.ellipse(x, y, 8, 8, t.accent, t.accent)
    svg.text(x, y + 3.6, str(num), FONT_SIZE * 0.7, bold=True, fill=t.bg)


def _actor(svg: Svg, x: float, top: float, label: str, t: Theme) -> None:
    svg.ellipse(x, top + 8, 7, 7, t.node_fill, t.node_stroke, 1.4)
    svg.line(x, top + 15, x, top + 34, t.node_stroke, 1.4)
    svg.line(x - 12, top + 22, x + 12, top + 22, t.node_stroke, 1.4)
    svg.line(x, top + 34, x - 10, top + 46, t.node_stroke, 1.4)
    svg.line(x, top + 34, x + 10, top + 46, t.node_stroke, 1.4)
    svg.text(x, top + 60, label, FONT_SIZE, bold=True)
