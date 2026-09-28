"""Tests für den ICS-Kalenderimport (core/ics.py) – ohne Qt."""
from __future__ import annotations

from datetime import date

from notex.core import ics


SIMPLE = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Kundentermin
DTSTART:20260907T090000
DTEND:20260907T113000
END:VEVENT
BEGIN:VEVENT
SUMMARY:Ganztägig Schulung
DTSTART;VALUE=DATE:20260908
DTEND;VALUE=DATE:20260909
END:VEVENT
BEGIN:VEVENT
SUMMARY:Privat
CLASS:PRIVATE
DTSTART:20260907T140000
DTEND:20260907T150000
END:VEVENT
END:VCALENDAR
"""

FOLDED = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Ein sehr langer\r\n  Titel\r\nDTSTART:20260907T080000\r\nDTEND:20260907T090000\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"

RECURRING = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Daily-Standup
DTSTART:20260907T090000
DTEND:20260907T091500
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;COUNT=5
EXDATE:20260909T090000
END:VEVENT
END:VCALENDAR
"""


def test_parse_simple_and_private_skipped():
    events = ics.parse(SIMPLE, horizon_end=date(2026, 12, 31))
    summaries = [e.summary for e in events]
    assert "Kundentermin" in summaries
    assert "Ganztägig Schulung" in summaries
    assert "Privat" not in summaries          # CLASS:PRIVATE übersprungen


def test_hours():
    events = ics.parse(SIMPLE, horizon_end=date(2026, 12, 31))
    k = next(e for e in events if e.summary == "Kundentermin")
    assert k.hours == 2.5


def test_line_folding():
    events = ics.parse(FOLDED, horizon_end=date(2026, 12, 31))
    assert events[0].summary == "Ein sehr langer Titel"


def test_week_range():
    monday, sunday = ics.week_range(2026, 37)
    assert monday.weekday() == 0 and sunday.weekday() == 6
    assert (sunday - monday).days == 6


def test_recurring_with_exdate():
    # KW37 2026: Mo 2026-09-07 .. So 2026-09-13
    events = ics.events_in_range(RECURRING, date(2026, 9, 7), date(2026, 9, 13))
    days = sorted(e.start.date().isoformat() for e in events)
    # Mo,Di,Do,Fr (Mi 09.09. per EXDATE entfernt) → 4 Termine
    assert "2026-09-09" not in days
    assert len(events) == 4


def test_berichtsheft_rows():
    rows = ics.berichtsheft_rows(SIMPLE, 2026, 37)
    by_day = {r["Tag"]: r for r in rows}
    assert "Montag" in by_day                       # 07.09.2026 = Montag
    assert "Kundentermin" in by_day["Montag"]["Tätigkeit"]
    # ganztägiger Termin am Dienstag bekommt Standardstunden
    assert by_day["Dienstag"]["Stunden"] in ("8.0", "8")
