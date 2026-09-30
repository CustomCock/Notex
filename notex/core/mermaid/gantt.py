"""Mermaid-Gantt (`gantt`): Parser + Zeichnen.

Unterstützt: title, dateFormat (YYYY MM DD HH mm ss, Standard YYYY-MM-DD), axisFormat (strftime, z. B. %d.%m),
excludes weekends, section, Aufgaben „Name : [done|active|crit|milestone,]* [id,] [Start,] Ende/Dauer“ mit Start als
Datum oder „after id1 id2“, Ende als Datum, „until id“ oder Dauer (30m, 12h, 3d, 2w). Ohne Start beginnt eine
Aufgabe nach der vorherigen. todayMarker/tickInterval werden gelesen und ignoriert (kein Zeitbezug in der Ausgabe).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from notex.core.mermaid.common import MAX_ELEMENTS, Diagram, Line, MermaidError, unquote
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, text_width

TAGS = {"done", "active", "crit", "milestone"}
DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(ms|s|m|min|h|d|w|M|y)$")


@dataclass
class Task:
    name: str
    section: str
    start: datetime
    end: datetime
    tags: set[str] = field(default_factory=set)
    id: str = ""


@dataclass
class Gantt:
    title: str = ""
    date_format: str = "YYYY-MM-DD"
    axis_format: str = "%d.%m."
    exclude_weekends: bool = False
    sections: list[str] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)


def _strptime_format(fmt: str) -> str:
    out = fmt
    for a, b in (("YYYY", "%Y"), ("YY", "%y"), ("MM", "%m"), ("DD", "%d"), ("HH", "%H"), ("mm", "%M"),
                 ("ss", "%S")):
        out = out.replace(a, b)
    return out


def _parse_date(text: str, fmt: str) -> datetime | None:
    text = text.strip()
    for f in (_strptime_format(fmt), "%Y-%m-%d", "%Y-%m-%d %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, f)
        except ValueError:
            continue
    return None


def _add(start: datetime, amount: float, unit: str, skip_weekends: bool) -> datetime:
    if unit in ("d", "w") and skip_weekends:
        days = amount * (7 if unit == "w" else 1)
        current, remaining = start, days
        while remaining > 0:
            current += timedelta(days=1)
            if current.weekday() < 5:
                remaining -= 1
        return current
    seconds = {"ms": 0.001, "s": 1, "m": 60, "min": 60, "h": 3600, "d": 86400, "w": 604800, "M": 2629800,
               "y": 31557600}[unit]
    return start + timedelta(seconds=amount * seconds)


def parse(lines: list[Line]) -> Gantt:
    g = Gantt()
    section = ""
    by_id: dict[str, Task] = {}
    prev_end: datetime | None = None
    for line in lines[1:]:
        s = line.text.strip()
        low = s.lower()
        m = re.match(r"^(title|dateFormat|axisFormat|excludes|section|todayMarker|tickInterval|includes|weekday)\b\s*(.*)$",
                     s, re.IGNORECASE)
        if m:
            key, value = m.group(1).lower(), m.group(2).strip()
            if key == "title":
                g.title = unquote(value)
            elif key == "dateformat":
                g.date_format = value or g.date_format
            elif key == "axisformat":
                g.axis_format = value or g.axis_format
            elif key == "excludes":
                g.exclude_weekends = "weekend" in value.lower()
            elif key == "section":
                section = unquote(value)
                g.sections.append(section)
            continue
        if low.startswith(("acctitle", "accdescr", "click")):
            continue
        if ":" not in s:
            raise MermaidError(f"Aufgabe braucht „Name : …“, gefunden: „{s[:50]}“", line.no)
        name, meta = s.split(":", 1)
        items = [x.strip() for x in meta.split(",") if x.strip()]
        tags = set()
        while items and items[0].lower() in TAGS:
            tags.add(items.pop(0).lower())
        task_id = ""
        if len(items) >= 3:
            task_id = items.pop(0)
        start_spec, end_spec = (items[0], items[1]) if len(items) == 2 else (None, items[0] if items else "1d")
        if len(items) == 2 and not _looks_like_start(start_spec, g.date_format) and \
                (_looks_like_start(end_spec, g.date_format) or DURATION_RE.match(end_spec)):
            task_id, start_spec = start_spec, None      # „id, Dauer“: Start nach der Vorgängeraufgabe
            if _looks_like_start(end_spec, g.date_format):  # „id, Datum/after x“: das ist der Start, 1 Tag lang
                start_spec, end_spec = end_spec, "1d"
        start = _resolve_start(start_spec, g, by_id, prev_end, line.no)
        end = _resolve_end(end_spec, start, g, by_id, line.no)
        if end < start:
            raise MermaidError("Ende liegt vor dem Anfang", line.no)
        if not section:
            section = ""
            if "" not in g.sections:
                g.sections.append("")
        task = Task(unquote(name.strip()), section, start, end, tags, task_id)
        g.tasks.append(task)
        if task_id:
            by_id[task_id] = task
        prev_end = end
        if len(g.tasks) > MAX_ELEMENTS:
            raise MermaidError("Zu viele Aufgaben")
    if not g.tasks:
        raise MermaidError("Keine Aufgaben im Gantt-Diagramm")
    return g


def _looks_like_start(spec: str | None, fmt: str) -> bool:
    return bool(spec) and (spec.lower().startswith("after ") or _parse_date(spec, fmt) is not None)


def _resolve_start(spec, g: Gantt, by_id, prev_end, line_no) -> datetime:
    if spec is None:
        if prev_end is None:
            raise MermaidError("Erste Aufgabe braucht ein Startdatum", line_no)
        return prev_end
    if spec.lower().startswith("after "):
        ends = []
        for ref in spec[6:].split():
            if ref not in by_id:
                raise MermaidError(f"„after {ref}“: Aufgabe mit dieser ID gibt es (noch) nicht", line_no)
            ends.append(by_id[ref].end)
        return max(ends)
    date = _parse_date(spec, g.date_format)
    if date is None:
        raise MermaidError(f"Datum „{spec}“ passt nicht zu dateFormat {g.date_format}", line_no)
    return date


def _resolve_end(spec: str, start: datetime, g: Gantt, by_id, line_no) -> datetime:
    m = DURATION_RE.match(spec)
    if m:
        return _add(start, float(m.group(1)), m.group(2), g.exclude_weekends)
    if spec.lower().startswith("until "):
        ref = spec[6:].strip()
        if ref not in by_id:
            raise MermaidError(f"„until {ref}“: Aufgabe mit dieser ID gibt es (noch) nicht", line_no)
        return by_id[ref].start
    date = _parse_date(spec, g.date_format)
    if date is None:
        raise MermaidError(f"Ende „{spec}“ ist weder Datum noch Dauer (z. B. 3d)", line_no)
    return date


# ---- Zeichnen --------------------------------------------------------------------------------------------------------
ROW = 28.0
BAR = 20.0


def render(g: Gantt, theme: Theme, title: str = "") -> Diagram:
    t = theme
    title = g.title or title
    start = min(task.start for task in g.tasks)
    end = max(task.end for task in g.tasks)
    span_days = max((end - start).total_seconds() / 86400, 1 / 24)
    section_w = max((text_width(s, FONT_SIZE * 0.9, True) for s in g.sections), default=0) + 24
    chart_w = max(480.0, min(1000.0, span_days * 26))
    scale = chart_w / (span_days * 86400)
    top = (40.0 if title else 12.0)
    left = section_w + 8
    rows = len(g.tasks)
    height = top + rows * ROW + 44
    width = left + chart_w + 16
    fs = FONT_SIZE * 0.85
    for task in g.tasks:                               # Beschriftungen rechts neben kurzen Balken
        bar_w = (task.end - task.start).total_seconds() * scale
        if text_width(task.name, fs) + 12 > bar_w:
            width = max(width, left + (task.end - start).total_seconds() * scale + text_width(task.name, fs) + 24)
    svg = Svg(t)
    if title:
        svg.text(width / 2, 26, title, FONT_SIZE * 1.15, bold=True)

    def x_of(when: datetime) -> float:
        return left + (when - start).total_seconds() * scale

    # Abschnitte als Bänder
    colors: dict[str, str] = {}
    for i, sec in enumerate(g.sections):
        colors[sec] = t.series[i % len(t.series)]
    row_of = {id(task): k for k, task in enumerate(g.tasks)}
    for i, sec in enumerate(g.sections):
        idx = [row_of[id(task)] for task in g.tasks if task.section == sec]
        if not idx:
            continue
        y1, y2 = top + min(idx) * ROW, top + (max(idx) + 1) * ROW
        if i % 2 == 0:
            svg.rect(0, y1, width, y2 - y1, t.cluster_fill, None, 0)
        if sec:
            svg.text(10, (y1 + y2) / 2 + 5, sec, FONT_SIZE * 0.9, anchor="start", bold=True)
    # Raster + Achse
    ticks = _ticks(start, end)
    axis_y = top + rows * ROW + 6
    for tick in ticks:
        x = x_of(tick)
        svg.line(x, top, x, axis_y, t.cluster_stroke, 0.8, "2,3")
        svg.text(x, axis_y + 16, tick.strftime(g.axis_format), FONT_SIZE * 0.75, fill=t.muted)
    svg.line(left, axis_y, left + chart_w, axis_y, t.muted, 1)
    # Balken
    for k, task in enumerate(g.tasks):
        cy = top + k * ROW + ROW / 2
        x1, x2 = x_of(task.start), x_of(task.end)
        base = colors.get(task.section, t.accent)
        if "milestone" in task.tags:
            s = BAR * 0.55
            cx = x1 if task.end == task.start else (x1 + x2) / 2
            svg.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)],
                        t.danger if "crit" in task.tags else base, t.text, 1)
            svg.text(cx + s + 6, cy + 4, task.name, fs, anchor="start")
            continue
        fill = base
        if "done" in task.tags:
            fill = t.muted if not t.dark else "#6b6f75"
        stroke = t.danger if "crit" in task.tags else t.bg
        opacity = 0.55 if "active" in task.tags else 1.0
        svg.rect(x1, cy - BAR / 2, max(2.0, x2 - x1), BAR, fill, stroke, 2 if "crit" in task.tags else 1, rx=3,
                 opacity=opacity)
        if text_width(task.name, fs) + 12 <= x2 - x1:
            svg.text((x1 + x2) / 2, cy + 4, task.name, fs, fill="#ffffff" if opacity == 1 else t.text)
        else:
            svg.text(x2 + 6, cy + 4, task.name, fs, anchor="start")
    return Diagram("gantt", svg.to_string(width, height), width, height, title)


def _ticks(start: datetime, end: datetime) -> list[datetime]:
    days = (end - start).total_seconds() / 86400
    base = datetime(start.year, start.month, start.day)
    if days <= 2:
        step, cur = timedelta(hours=6), base
    elif days <= 16:
        step, cur = timedelta(days=1), base
    elif days <= 120:
        cur = base - timedelta(days=base.weekday())          # Montage
        step = timedelta(weeks=1)
    else:
        out, cur = [], datetime(start.year, start.month, 1)
        while cur <= end:
            if cur >= start:
                out.append(cur)
            cur = datetime(cur.year + (cur.month // 12), cur.month % 12 + 1, 1)
        return out or [start]
    out = []
    while cur <= end:
        if cur >= start:
            out.append(cur)
        cur += step
    return out or [start]
