"""Kalender-Import (.ics / RFC 5545) – ohne Qt und ohne Zusatzabhängigkeit.

Bewusst ein kompakter eigener Parser statt einer neuen Bibliothek (Build-Größe): unterstützt VEVENT mit
DTSTART/DTEND/SUMMARY, ganztägige Termine (VALUE=DATE), einfache Serien (RRULE FREQ=DAILY/WEEKLY mit INTERVAL/
COUNT/UNTIL/BYDAY) und EXDATE. Zeitzonen (TZID) werden als lokale Zeit behandelt (ohne Zonendatenbank);
CLASS:PRIVATE und leere Termine werden übersprungen. Für den Ausbildungsnachweis werden die Termine einer Woche
zu Tages-Tätigkeiten mit Dauer zusammengefasst.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_DAY_LABEL = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


@dataclass
class Event:
    start: datetime
    end: datetime
    summary: str
    all_day: bool = False

    @property
    def hours(self) -> float:
        return round((self.end - self.start).total_seconds() / 3600, 2)


def _unfold(text: str) -> list[str]:
    """RFC-5545-Zeilenfaltung auflösen (Folgezeilen beginnen mit Leerzeichen/Tab)."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _split_prop(line: str) -> tuple[str, dict, str]:
    """„NAME;PARAM=x:VALUE" → (NAME, {param}, VALUE)."""
    head, _, value = line.partition(":")
    parts = head.split(";")
    name = parts[0].upper()
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v
    return name, params, value


def _parse_dt(value: str, params: dict) -> tuple[datetime, bool]:
    """(datetime, all_day). VALUE=DATE → ganztägig; ‚Z' → UTC (hier naiv behandelt)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d, True
    v = value.rstrip("Z")
    return datetime.strptime(v[:15], "%Y%m%dT%H%M%S"), False


def _parse_events(text: str) -> list[dict]:
    events, current = [], None
    for line in _unfold(text):
        name, params, value = _split_prop(line)
        if name == "BEGIN" and value == "VEVENT":
            current = {"props": {}, "exdate": []}
        elif name == "END" and value == "VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None:
            if name == "EXDATE":
                for token in value.split(","):
                    try:
                        current["exdate"].append(_parse_dt(token, params)[0].date())
                    except ValueError:
                        pass
            else:
                current["props"][name] = (params, value)
    return events


def _rrule(spec: str) -> dict:
    out = {}
    for part in spec.split(";"):
        k, _, v = part.partition("=")
        out[k.upper()] = v
    return out


def _expand(start: datetime, end: datetime, rule: dict, horizon_end: date, exdates: list) -> list[tuple[datetime, datetime]]:
    freq = rule.get("FREQ", "")
    if freq not in ("DAILY", "WEEKLY"):
        return [(start, end)]
    interval = int(rule.get("INTERVAL", "1") or "1")
    count = int(rule["COUNT"]) if rule.get("COUNT") else None
    until = None
    if rule.get("UNTIL"):
        try:
            until = _parse_dt(rule["UNTIL"], {})[0]
        except ValueError:
            until = None
    bydays = [_WEEKDAYS[d] for d in rule.get("BYDAY", "").split(",") if d in _WEEKDAYS]
    duration = end - start
    occurrences: list[tuple[datetime, datetime]] = []
    limit = datetime.combine(horizon_end + timedelta(days=1), datetime.min.time())
    cursor = start
    guard = 0
    while guard < 3000:
        guard += 1
        if cursor > limit or (until and cursor > until) or (count is not None and len(occurrences) >= count):
            break
        if freq == "WEEKLY" and bydays:
            week_start = cursor - timedelta(days=cursor.weekday())
            for wd in bydays:
                occ = week_start + timedelta(days=wd, hours=start.hour, minutes=start.minute)
                occ = occ.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
                if occ < start:
                    continue
                if until and occ > until:
                    continue
                if occ.date() not in exdates:
                    occurrences.append((occ, occ + duration))
            cursor += timedelta(weeks=interval)
        else:
            if cursor.date() not in exdates:
                occurrences.append((cursor, cursor + duration))
            cursor += timedelta(days=interval if freq == "DAILY" else 7 * interval)
    if count is not None:
        occurrences = occurrences[:count]
    return occurrences


def parse(text: str, horizon_end: date | None = None) -> list[Event]:
    """Alle Termine (Serien expandiert bis `horizon_end`, Standard: ein Jahr)."""
    horizon_end = horizon_end or (date.today() + timedelta(days=366))
    out: list[Event] = []
    for raw in _parse_events(text):
        props = raw["props"]
        if "DTSTART" not in props:
            continue
        if props.get("CLASS", ({}, ""))[1].upper() == "PRIVATE":
            continue
        summary = props.get("SUMMARY", ({}, ""))[1].strip()
        try:
            start, all_day = _parse_dt(props["DTSTART"][1], props["DTSTART"][0])
        except ValueError:
            continue
        if "DTEND" in props:
            try:
                end = _parse_dt(props["DTEND"][1], props["DTEND"][0])[0]
            except ValueError:
                end = start + timedelta(hours=1)
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
        if "RRULE" in props:
            for occ_start, occ_end in _expand(start, end, _rrule(props["RRULE"][1]), horizon_end, raw["exdate"]):
                out.append(Event(occ_start, occ_end, summary, all_day))
        else:
            out.append(Event(start, end, summary, all_day))
    return out


def week_range(year: int, iso_week: int) -> tuple[date, date]:
    """Montag und Sonntag der ISO-Woche."""
    monday = date.fromisocalendar(year, iso_week, 1)
    return monday, monday + timedelta(days=6)


def events_in_range(text: str, start: date, end: date) -> list[Event]:
    events = [e for e in parse(text, horizon_end=end) if start <= e.start.date() <= end]
    return sorted(events, key=lambda e: e.start)


def berichtsheft_rows(text: str, year: int, iso_week: int, daily_hours: float = 8.0) -> list[dict]:
    """Termine der Woche zu Tages-Tätigkeiten zusammenfassen (für den Ausbildungsnachweis)."""
    monday, sunday = week_range(year, iso_week)
    by_day: dict[int, list[Event]] = {}
    for event in events_in_range(text, monday, sunday):
        by_day.setdefault(event.start.weekday(), []).append(event)
    rows = []
    for wd in range(5):                          # Mo–Fr
        day_events = by_day.get(wd, [])
        if not day_events:
            continue
        tasks = "; ".join(e.summary for e in day_events if e.summary)
        hours = sum(e.hours for e in day_events if not e.all_day)
        if any(e.all_day for e in day_events) and hours == 0:
            hours = daily_hours
        rows.append({"Tag": _DAY_LABEL[wd], "Tätigkeit": tasks or "(Termin ohne Titel)",
                     "Stunden": str(round(hours, 1)) if hours else "", "Lernort": "Betrieb"})
    return rows
