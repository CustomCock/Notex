import json
import time
from pathlib import Path

import pytest

from notex.core.history import (DAY, HOUR, History, Version, diff_lines, diff_stats, format_age, text_sha, thin)

NOW = 1_800_000_000.0


def test_snapshot_dedups_and_compresses(tmp_path: Path) -> None:
    h = History(tmp_path / "history")
    v1 = h.snapshot("notizen/a.md", "eins\n" * 1000, now=NOW)
    assert v1 is not None and v1.size == 5000
    assert h.snapshot("notizen/a.md", "eins\n" * 1000, now=NOW + 5) is None          # unverändert
    v2 = h.snapshot("notizen/a.md", "zwei\n", now=NOW + 10)
    assert [v.sha for v in h.versions("notizen/a.md")] == [v2.sha, v1.sha]            # neueste zuerst
    h.snapshot("b.txt", "eins\n" * 1000, now=NOW + 20)                                # gleicher Inhalt, andere Datei
    objects = list((tmp_path / "history" / "objects").glob("*/*.z"))
    assert len(objects) == 2                                                           # Objekt geteilt
    assert objects[0].stat().st_size < 1000                                            # komprimiert
    assert h.content(v1.sha) == "eins\n" * 1000


def test_index_persists_and_survives_garbage(tmp_path: Path) -> None:
    h = History(tmp_path / "h")
    h.snapshot("a.md", "x", now=NOW)
    h.snapshot("a.md", "y", now=NOW + 1)
    again = History(tmp_path / "h")
    assert [v.size for v in again.versions("A.MD")] == [1, 1]                         # Pfad case-insensitiv
    (tmp_path / "h" / "index.json").write_text("{kaputt", encoding="utf-8")
    assert History(tmp_path / "h").versions("a.md") == []
    (tmp_path / "h" / "index.json").write_text(json.dumps(
        {"files": {"1": {"path": "a.md", "versions": [{"t": "x"}, {"t": 1, "sha": "zz"}]}}}), encoding="utf-8")
    assert History(tmp_path / "h").versions("a.md") == []


def test_encrypted_and_large_files_never_stored(tmp_path: Path) -> None:
    h = History(tmp_path / "h", max_file_bytes=100)
    assert h.snapshot("geheim.ntx", "Klartext!", now=NOW) is None
    assert h.snapshot("ordner/GEHEIM.NTX", "Klartext!", now=NOW) is None
    assert h.snapshot("gross.txt", "x" * 101, now=NOW) is None
    assert not (tmp_path / "h" / "objects").exists() or not list((tmp_path / "h" / "objects").glob("*/*.z"))


def test_rename_file_folder_and_to_ntx(tmp_path: Path) -> None:
    h = History(tmp_path / "h")
    h.snapshot("alt/a.md", "a", now=NOW)
    h.snapshot("alt/sub/b.md", "b", now=NOW)
    h.snapshot("c.md", "c", now=NOW)
    assert h.rename("alt", "neu") == 2
    assert h.tracked_paths() == ["c.md", "neu/a.md", "neu/sub/b.md"]
    assert h.rename("c.md", "d.md") == 1 and h.versions("d.md") and not h.versions("c.md")
    # Umbenennen in .ntx: Klartext-Historie wird gelöscht, Objekt verschwindet
    sha = h.versions("d.md")[0].sha
    h.rename("d.md", "d.ntx")
    assert h.versions("d.ntx") == [] and h.versions("d.md") == []
    assert not h._object_path(sha).exists()


def test_rename_onto_existing_history_merges(tmp_path: Path) -> None:
    h = History(tmp_path / "h")
    h.snapshot("a.md", "a1", now=NOW)
    h.snapshot("b.md", "b1", now=NOW + 1)
    h.rename("a.md", "b.md")
    assert [h.content(v.sha) for v in h.versions("b.md")] == ["b1", "a1"]


def test_forget_removes_objects(tmp_path: Path) -> None:
    h = History(tmp_path / "h")
    v = h.snapshot("x/a.md", "geheim", now=NOW)
    assert h.forget("x") and h.versions("x/a.md") == []
    assert not h._object_path(v.sha).exists()


def test_thinning_keeps_recent_all_and_one_per_bucket() -> None:
    versions = [Version(NOW - m * 60, text_sha(str(m)), 1) for m in range(0, 60)]              # letzte Stunde
    versions += [Version(NOW - 2 * DAY - m * 60, text_sha(f"d{m}"), 1) for m in range(0, 120)]   # vor 2 Tagen, 2 h
    versions += [Version(NOW - 10 * DAY - h * HOUR, text_sha(f"w{h}"), 1) for h in range(0, 48)]  # vor 10 Tagen, 2 Tage
    kept = thin(versions, NOW)
    recent = [v for v in kept if NOW - v.timestamp <= DAY]
    assert len(recent) == 60                                            # < 24 h: alles
    two_days = [v for v in kept if DAY < NOW - v.timestamp <= 7 * DAY]
    assert 2 <= len(two_days) <= 3                                      # eine pro Stunde
    ten_days = [v for v in kept if 7 * DAY < NOW - v.timestamp <= 30 * DAY]
    assert 2 <= len(ten_days) <= 3                                      # eine pro Tag
    assert max(kept, key=lambda v: v.timestamp).timestamp == NOW        # neueste bleibt
    old = [Version(NOW - 400 * DAY, text_sha("alt"), 1)]
    assert thin(old, NOW) == old                                        # einzige Version bleibt immer


def test_size_limit_drops_oldest_but_keeps_newest(tmp_path: Path) -> None:
    import os
    h = History(tmp_path / "h", max_bytes=30_000)
    for i in range(8):
        h.snapshot("a.txt", os.urandom(6000).hex(), now=NOW + i)        # schlecht komprimierbar
    h.snapshot("b.txt", "klein", now=NOW)
    assert h.object_bytes() > 30_000
    removed = h.enforce_limit()
    assert removed > 0 and h.object_bytes() <= 30_000
    assert h.versions("a.txt")[0].timestamp == NOW + 7                  # neueste von a bleibt
    assert h.versions("b.txt")                                          # b (neueste) bleibt


def test_content_detects_corruption(tmp_path: Path) -> None:
    import zlib
    h = History(tmp_path / "h")
    v = h.snapshot("a.md", "original", now=NOW)
    h._object_path(v.sha).write_bytes(zlib.compress(b"manipuliert"))
    with pytest.raises(ValueError):
        h.content(v.sha)


def test_diff_lines_and_stats() -> None:
    old = "a\nb\nc\nd\ne\nf\ng\nh"
    new = "a\nb\nC\nd\ne\nf\ng\nh\ni"
    lines = diff_lines(old, new, context=1)
    kinds = [(d.kind, d.text) for d in lines]
    assert ("-", "c") in kinds and ("+", "C") in kinds and ("+", "i") in kinds
    assert lines[0].kind == "@"
    assert diff_stats(lines) == (2, 1)
    assert diff_lines("gleich", "gleich") == []
    minus = next(d for d in lines if d.kind == "-")
    assert minus.old_no == 3 and minus.new_no is None


def test_format_age() -> None:
    assert format_age(NOW - 10, NOW) == "gerade eben"
    assert format_age(NOW - 5 * 60, NOW) == "vor 5 Min."
    assert format_age(NOW - 3 * HOUR, NOW) == "vor 3 Std."
    assert format_age(NOW - 40 * DAY, NOW) == time.strftime("%d.%m.%Y %H:%M", time.localtime(NOW - 40 * DAY))
