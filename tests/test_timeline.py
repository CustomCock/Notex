from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from notex.core import timeline as tl

CET = timezone(timedelta(hours=2))

SAMPLE = """---
notex: zeitleiste
titel: Vorfall
---
# Zeitleiste: Vorfall

| Zeit | Quelle | Beschreibung | Tags |
|---|---|---|---|
| 2026-09-26T14:03:11+02:00 | auth.log | Login root \\| fehlgeschlagen | #ssh #bruteforce |
| 2026-09-26T11:00:00Z | proxy.log | Download evil.exe | malware |
| kaputt | x | wird übersprungen | |

Notizen danach.
"""


def test_parse_sorted_with_escaped_pipes() -> None:
    t = tl.parse(SAMPLE)
    assert tl.is_timeline(SAMPLE) and t.meta["titel"] == "Vorfall"
    assert [e.source for e in t.entries] == ["proxy.log", "auth.log"]          # chronologisch
    assert t.entries[1].description == "Login root | fehlgeschlagen"
    assert t.entries[1].tags == ["#ssh", "#bruteforce"] and t.entries[0].tags == ["#malware"]
    assert t.entries[1].time == datetime(2026, 9, 26, 12, 3, 11, tzinfo=timezone.utc)
    assert t.sources == ["auth.log", "proxy.log"] and t.tags == ["#bruteforce", "#malware", "#ssh"]
    assert t.entries[0].line == 9 and t.header_line == 6 and t.last_row_line == 10


def test_not_a_timeline() -> None:
    assert not tl.is_timeline("# Notiz\n\n| Zeit | x |")
    assert not tl.is_timeline("---\ntitel: x\n---\n")


def test_add_entry_chronologically_and_roundtrip() -> None:
    entry = tl.Entry(datetime(2026, 9, 26, 12, 30, tzinfo=timezone.utc), "fw", "Verbindung | 443", ["#c2"])
    text, line = tl.add_entry(SAMPLE, entry)
    lines = text.split("\n")
    assert line == 11 and lines[11] == "| 2026-09-26T12:30:00Z | fw | Verbindung \\| 443 | #c2 |"   # nach allen früheren
    assert [e.source for e in tl.parse(text).entries] == ["proxy.log", "auth.log", "fw"]
    early = tl.Entry(datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc), "vpn", "früh")
    assert tl.add_entry(SAMPLE, early)[1] == 8                     # vor der ersten späteren Zeile
    late = tl.Entry(datetime(2027, 1, 1, tzinfo=CET), "x", "spät")
    text2, line2 = tl.add_entry(text, late)
    assert text2.split("\n")[line2].startswith("| 2027-01-01T00:00:00+02:00") and text2.endswith("Notizen danach.\n")


def test_add_entry_creates_table() -> None:
    entry = tl.Entry(datetime(2026, 1, 1, tzinfo=timezone.utc), "a", "b")
    text, line = tl.add_entry("---\nnotex: zeitleiste\n---\n# X\n\n\n", entry)
    assert text.split("\n")[line] == entry.row() and tl.parse(text).entries[0].source == "a"
    fresh = tl.new_text("Test")
    assert tl.is_timeline(fresh) and tl.parse(tl.add_entry(fresh, entry)[0]).entries[0].description == "b"


@pytest.mark.parametrize("line,expected", [
    ("2026-09-26T14:03:11.250+02:00 host sshd[1]: Failed", datetime(2026, 9, 26, 14, 3, 11, 250000, tzinfo=CET)),
    ("2026-09-26 12:00:00Z x", datetime(2026, 9, 26, 12, tzinfo=timezone.utc)),
    ('1.2.3.4 - - [26/Sep/2026:14:03:11 +0200] "GET / HTTP/1.1"', datetime(2026, 9, 26, 14, 3, 11, tzinfo=CET)),
    ("Am 26.09.2026 14:03:11 UTC gesehen", datetime(2026, 9, 26, 14, 3, 11, tzinfo=timezone.utc)),
    ("9/26/2026 2:03:11 PM Anmeldung", datetime(2026, 9, 26, 14, 3, 11, tzinfo=timezone.utc)),
    ("Sep  6 04:03:11 host sshd: x", datetime(2025, 9, 6, 4, 3, 11, tzinfo=timezone.utc)),
    ("1790000000.5 event", datetime.fromtimestamp(1790000000, timezone.utc).replace(microsecond=500000)),
])
def test_detect_timestamp(line: str, expected: datetime) -> None:
    found = tl.detect_timestamp(line, year=2025, default_tz=timezone.utc)
    assert found is not None and found[0] == expected


@pytest.mark.parametrize("line", [
    "Betrag 1.234,56 EUR im Jahr 2026", "Version 10.0.19045", "Port 3389 offen", "12345678901234 Bytes",
    "Datei 2026-13-45 kaputt",
])
def test_no_false_timestamps(line: str) -> None:
    assert tl.detect_timestamp(line) is None


def test_entry_from_line_and_ntx_rule() -> None:
    e = tl.entry_from_line("Sep 26 14:03:11 web sshd[99]: Failed password for root", "auth.log", year=2026)
    assert e.time.month == 9 and e.source == "auth.log" and e.description == "web sshd[99]: Failed password for root"
    fallback = tl.entry_from_line("kein Datum hier", "x")
    assert fallback.description == "kein Datum hier" and fallback.time.tzinfo is not None
    assert not tl.can_take_from(Path("geheim.ntx")) and tl.can_take_from(Path("auth.log"))


def test_display_modes_and_exports() -> None:
    entries = tl.parse(SAMPLE).entries
    assert tl.display(entries[1].time, "utc") == "2026-09-26 12:03:11 UTC"
    assert tl.display(entries[1].time, "original") == "2026-09-26 14:03:11 +02:00"
    md = tl.to_markdown(entries)
    assert md.splitlines()[2] == "| 2026-09-26 11:00:00 UTC | proxy.log | Download evil.exe | #malware |"
    assert "Login root \\| fehlgeschlagen" in md
    csv_text = tl.to_csv(entries)
    assert csv_text.splitlines()[0] == "Zeit,Quelle,Beschreibung,Tags"
    assert csv_text.splitlines()[2] == "2026-09-26T12:03:11Z,auth.log,Login root | fehlgeschlagen,#ssh #bruteforce"


def test_filter() -> None:
    entries = tl.parse(SAMPLE).entries
    assert [e.source for e in tl.filter_entries(entries, tag="#ssh")] == ["auth.log"]
    assert [e.source for e in tl.filter_entries(entries, source="proxy.log")] == ["proxy.log"]
    assert [e.source for e in tl.filter_entries(entries, text="EVIL")] == ["proxy.log"]


def test_find_timelines_skips_other_files(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "fall.md").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "notiz.md").write_text("# Notiz", encoding="utf-8")
    (tmp_path / "geheim.ntx").write_bytes(b"NTX1")
    assert [p.name for p in tl.find_timelines(tmp_path)] == ["fall.md"]


EVIDENCE = """# Beweismittel B-001

## Prüfsummen

| Algorithmus | Wert | Datei |
|---|---|---|
|  |  |  |

## Übergaben

| Wann | Von | An | Zweck |
|---|---|---|---|
| 2026-09-26 10:00 | A | B | Analyse |

## Notizen
"""


def test_append_row_replaces_placeholder_then_appends() -> None:
    text, line = tl.append_row(EVIDENCE, "Prüfsummen", ["SHA-256", "ab|cd", "img.dd"])
    assert text.split("\n")[line] == "| SHA-256 | ab\\|cd | img.dd |" and "|  |  |  |" not in text
    text, line = tl.append_row(text, "Prüfsummen", ["MD5", "ef", "img.dd"])
    assert text.split("\n")[line] == "| MD5 | ef | img.dd |" and text.split("\n")[line - 1].startswith("| SHA-256")
    text, line = tl.append_row(text, "Übergaben", ["2026-09-27 09:00", "B", "C", "Gericht"])
    assert text.split("\n")[line - 1].startswith("| 2026-09-26 10:00") and text.endswith("## Notizen\n")
    assert tl.append_row(EVIDENCE, "Gibt es nicht", ["x"]) is None
