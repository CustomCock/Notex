import os
from pathlib import Path

from notex.core import tail
from notex.core.tail import LogFilter, Tailer, classify


def append(path: Path, data: bytes) -> None:
    with open(path, "ab") as handle:
        handle.write(data)


def test_start_and_incremental_lines(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"eins\nzwei\n")
    tailer = Tailer(log)
    first = tailer.start()
    assert first.reset and first.lines == ["eins", "zwei"]
    assert tailer.poll().lines == []
    append(log, b"drei\nvie")
    assert tailer.poll().lines == ["drei"]              # „vie“ ist noch unvollständig
    assert tailer.partial == "vie"
    append(log, b"r\r\nf\xc3")                          # CRLF und ein halbes UTF-8-Zeichen
    assert tailer.poll().lines == ["vier"]
    append(log, b"\xbcnf\n")
    assert tailer.poll().lines == ["fünf"]


def test_file_is_never_modified(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"a\nb\n")
    before = (log.read_bytes(), log.stat().st_mtime_ns)
    tailer = Tailer(log)
    tailer.start()
    tailer.poll()
    LogFilter(level="error", text="x").apply(["a", "b"])
    assert (log.read_bytes(), log.stat().st_mtime_ns) == before


def test_truncation_is_detected(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"alt 1\nalt 2\n")
    tailer = Tailer(log)
    tailer.start()
    log.write_bytes(b"neu\n")                           # `> app.log` und neu schreiben
    result = tailer.poll()
    assert result.reset and result.lines == ["neu"]


def test_rotation_is_detected(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"alt\n" * 10)
    tailer = Tailer(log)
    tailer.start()
    os.replace(log, tmp_path / "app.log.1")             # logrotate: umbenennen, neue Datei anlegen
    missing = tailer.poll()
    assert missing.missing
    log.write_bytes(b"frisch rotiert, aber gleich lang?\n" * 2)
    result = tailer.poll()
    assert result.reset and result.lines[0].startswith("frisch")


def test_big_append_is_chunked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tail, "MAX_READ", 1000)
    log = tmp_path / "app.log"
    log.write_bytes(b"")
    tailer = Tailer(log)
    tailer.start()
    append(log, b"".join(f"zeile {i}\n".encode() for i in range(1000)))
    lines, rounds = [], 0
    while True:
        result = tailer.poll()
        lines += result.lines
        rounds += 1
        if not result.more:
            break
    assert rounds > 5 and lines == [f"zeile {i}" for i in range(1000)]


def test_initial_tail_skips_cut_line(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tail, "INITIAL_TAIL", 50)
    log = tmp_path / "app.log"
    log.write_bytes(b"".join(f"zeile {i:03}\n".encode() for i in range(100)))
    result = Tailer(log).start()
    assert result.skipped > 0 and result.lines[-1] == "zeile 099" and all(l.startswith("zeile") for l in result.lines)


def test_classify_levels() -> None:
    assert classify("2026-01-01 ERROR db down") == "error"
    assert classify("[error] nginx") == "error" and classify("FATAL: x") == "error"
    assert classify("WARNING: disk 90%") == "warn" and classify("[warn] slow") == "warn"
    assert classify("INFO all good") is None and classify("terrorist") is None


def test_log_filter() -> None:
    lines = ["INFO start", "WARN langsam", "ERROR kaputt", "INFO user=bob", "DEBUG x"]
    assert LogFilter(level="error").apply(lines) == ["ERROR kaputt"]
    assert LogFilter(level="warn").apply(lines) == ["WARN langsam", "ERROR kaputt"]
    assert LogFilter(text="BOB").apply(lines) == ["INFO user=bob"]
    assert LogFilter(text="bob", case_sensitive=True).apply(lines) == ["INFO user=bob"]
    assert LogFilter(text=r"user=\w+", regex=True).apply(lines) == ["INFO user=bob"]
    assert LogFilter(text="[", regex=False).apply(["a[b", "c"]) == ["a[b"]
    broken = LogFilter(text="(", regex=True)
    assert broken.error and broken.apply(lines) == lines          # ungültig: nichts ausblenden, Feld wird rot
    assert LogFilter().apply(lines) == lines and not LogFilter().active
    assert LogFilter(level="error", text="(", regex=True).apply(lines) == ["ERROR kaputt"]


def test_ntx_is_never_followed(tmp_path: Path) -> None:
    import pytest
    secret = tmp_path / "geheim.ntx"
    secret.write_bytes(b"NOTEXENC" + b"\x00" * 32)
    assert not tail.can_follow(secret) and tail.can_follow(tmp_path / "x.log") is False
    (tmp_path / "x.log").write_text("a\n")
    assert tail.can_follow(tmp_path / "x.log")
    with pytest.raises(ValueError):
        Tailer(secret)
