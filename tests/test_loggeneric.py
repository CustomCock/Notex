"""Tests für die allgemeine Log-Auswertung (core/loggeneric.py) – ohne Qt."""
from __future__ import annotations

from notex.core import loggeneric as lg


def test_detect_level_variants():
    assert lg.detect_level("ERROR something bad") == "error"
    assert lg.detect_level("2024-01-01 [WARN] hi") == "warning"
    assert lg.detect_level("FATAL: kaboom") == "critical"
    assert lg.detect_level("Info    SP     started") == "info"
    assert lg.detect_level("FEHLER beim Start") == "error"
    assert lg.detect_level("nur ein satz ohne stufe") == "other"
    # „error" als Teil eines Wortes zählt nicht
    assert lg.detect_level("terrorformous message") == "other"


def test_parse_iso_with_level():
    e = lg.parse_line("2024-01-02 10:11:12 ERROR db Verbindung verloren", 1)
    assert e is not None
    assert e.time is not None and e.time.year == 2024
    assert e.level == "error"
    assert "Verbindung verloren" in e.message


def test_parse_setupact_style():
    # setupact.log: „2016-07-16 12:00:00, Info                  SP     Message"
    e = lg.parse_line("2016-07-16 12:00:00, Info                  SP     Executing action", 2)
    assert e.level == "info"
    assert e.time is not None
    assert "Executing action" in e.message


def test_parse_syslog_source():
    e = lg.parse_line("Jan  5 06:25:43 host nginx[1234]: 500 error upstream", 3)
    assert e.source == "nginx"
    # 500 -> Zahl, aber „error" als Wort -> Fehlerstufe
    assert e.level == "error"


def test_parse_bracket_source():
    e = lg.parse_line("2024-01-01 00:00:00 [auth] WARN token abgelaufen", 4)
    # Quelle in Klammern erkannt
    assert e.source == "auth"
    assert e.level == "warning"


def test_empty_line_is_none():
    assert lg.parse_line("   \n") is None
    assert lg.parse_line("") is None


def test_template_groups_numbers_and_paths():
    a = lg.template("Failed to open C:\\Users\\a\\file1.txt (code 5)")
    b = lg.template("Failed to open C:\\Users\\b\\file2.txt (code 9)")
    assert a == b
    assert "<pfad>" in a and "<n>" in a


def test_template_ip_and_uuid():
    t = lg.template("client 10.0.0.5 id 550e8400-e29b-41d4-a716-446655440000 done")
    assert "<ip>" in t and "<id>" in t


def test_analyze_counts_and_span():
    lines = [
        "2024-01-01 10:00:00 INFO start",
        "2024-01-01 10:05:00 ERROR disk full on /var",
        "2024-01-01 11:00:00 ERROR disk full on /tmp",
        "2024-01-01 11:30:00 WARN low memory",
        "just a line without timestamp or level",
    ]
    events = [lg.parse_line(l, i) for i, l in enumerate(lines)]
    events = [e for e in events if e]
    summary = lg.analyze_generic(events)
    assert summary.total == 5
    assert summary.with_time == 4
    assert summary.error_count == 2
    assert summary.warning_count == 1
    assert summary.first_time.hour == 10 and summary.last_time.hour == 11
    # die zwei "disk full on <pfad>" fallen zu einem Muster zusammen
    patterns = dict(summary.top_error_messages)
    assert any(count == 2 for count in patterns.values())
    md = lg.to_markdown(summary, "test.log")
    assert "Stufen" in md and "Fehler" in md


def test_collect_generic_limit(tmp_path):
    p = tmp_path / "big.log"
    p.write_text("\n".join(f"2024-01-01 00:00:{i%60:02d} INFO line {i}" for i in range(100)))
    events, truncated = lg.collect_generic(p, limit=10)
    assert len(events) == 10
    assert truncated is True
