import os
import time
from pathlib import Path

import pytest

from notex.core import ipmap

NOTE = """# Netz Büro

| Host | IP-Adresse | Rolle |
|---|---|---|
| fileserver | 10.0.0.5 | NAS |
| drucker | `10.0.0.20/24` | |
| kaputt | 999.1.1.1 | |

## hosts

10.0.0.30   backup   # nachts
- 10.0.0.31 cam-01
router: 10.0.0.1
**vpn** = 10.0.1.1
gateway: 10.0.0.1
Zeit: 14:03:11
2001:db8::10 v6host
"""


def pairs(items) -> list[tuple[str, str]]:
    return [(a.ip, a.host) for a in items]


def test_extract_tables_and_lines() -> None:
    found = ipmap.extract(NOTE, Path("netz.md"))
    assert pairs(found) == [("10.0.0.5", "fileserver"), ("10.0.0.20", "drucker"), ("10.0.0.30", "backup"),
                            ("10.0.0.31", "cam-01"), ("10.0.0.1", "router"), ("10.0.1.1", "vpn"),
                            ("2001:db8::10", "v6host")]
    assert found[0].line == 4 and found[4].line == 12


def test_conflicts_ignore_same_host_variants() -> None:
    a = ipmap.extract("10.0.0.5 fileserver\n10.0.0.6 web", Path("a.md"))
    b = ipmap.extract("| Host | IP |\n|---|---|\n| FileServer.corp.local | 10.0.0.5 |\n| mail | 10.0.0.6 |",
                      Path("b.md"))
    result = ipmap.conflicts(a + b)
    assert list(result) == ["10.0.0.6"] and {x.host for x in result["10.0.0.6"]} == {"web", "mail"}


def test_group_by_subnet_sorted() -> None:
    groups = ipmap.group(ipmap.extract(NOTE, Path("n.md")))
    assert list(groups) == ["10.0.0.0/24", "10.0.1.0/24", "2001:db8::/64"]
    assert [a.ip for a in groups["10.0.0.0/24"]] == ["10.0.0.1", "10.0.0.5", "10.0.0.20", "10.0.0.30", "10.0.0.31"]


def test_usage_with_exclusions() -> None:
    items = ipmap.extract("10.0.0.1 router\n10.0.0.2 dns\n10.0.0.150 drucker", Path("x.md"))
    use = ipmap.usage("10.0.0.0/24", items, "10.0.0.100-10.0.0.199, 10.0.0.3")
    assert use.total == 254 and use.used == ["10.0.0.1", "10.0.0.2", "10.0.0.150"]
    assert use.excluded == 101 and use.next_free == "10.0.0.4"
    assert use.free == 254 - 101 - 2                     # 10.0.0.150 liegt im ausgeschlossenen Bereich
    assert ipmap.usage("10.0.0.0/29", items).next_free == "10.0.0.3"
    assert ipmap.usage("10.0.0.0/30", items).next_free is None             # .3 ist Broadcast
    assert ipmap.parse_exclusions("10.0.0.10-20") == [(167772170, 167772180)]
    with pytest.raises(ValueError):
        ipmap.parse_exclusions("kein.ip")


def test_full_subnet_has_no_next_free() -> None:
    items = ipmap.extract("10.9.9.1 a\n10.9.9.2 b", Path("x.md"))
    assert ipmap.usage("10.9.9.0/30", items).next_free is None


def test_index_incremental_skips_ntx(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    note = tmp_path / "sub" / "netz.md"
    note.write_text("10.0.0.5 fileserver\n", encoding="utf-8")
    (tmp_path / "geheim.ntx").write_bytes(b"10.0.0.5 geheim\n")          # würde als Klartext nie gelesen
    (tmp_path / "bild.png").write_bytes(b"10.0.0.5 x")
    index = ipmap.IpIndex(tmp_path)
    assert index.refresh() == 1 and pairs(index.assignments()) == [("10.0.0.5", "fileserver")]
    assert index.refresh() == 0                                           # nichts geändert → nichts gelesen
    note.write_text("10.0.0.5 fileserver\n10.0.0.6 mail\n", encoding="utf-8")
    stamp = time.time() + 5
    os.utime(note, (stamp, stamp))
    assert index.refresh() == 1 and len(index.assignments()) == 2
    live = index.assignments({note: "10.0.0.5 anderer\n"})               # ungespeicherter Editor-Text
    assert pairs(live) == [("10.0.0.5", "anderer")]
    assert index.assignments({tmp_path / "geheim.ntx": "10.0.0.5 geheim"}) == index.assignments()
    note.unlink()
    index.refresh()
    assert index.assignments() == []
