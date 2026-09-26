from pathlib import Path

from notex.core.ipc import decode_open_request, encode_open_request, file_arguments, server_name
from notex.core.recent import add_recent, prune_recent, shorten_path


def test_add_recent_moves_to_front_and_limits() -> None:
    entries = add_recent(["b", "a"], "a")
    assert entries == ["a", "b"]
    many = []
    for i in range(20):
        many = add_recent(many, f"f{i}")
    assert len(many) == 15 and many[0] == "f19"


def test_prune_recent_drops_missing_and_duplicates(tmp_path: Path) -> None:
    existing = tmp_path / "x.txt"
    existing.write_text("x")
    entries = [str(existing), str(tmp_path / "weg.txt"), str(existing), 42, ""]
    assert prune_recent(entries) == [str(existing)]


def test_shorten_path() -> None:
    assert shorten_path("kurz.txt") == "kurz.txt"
    long = "C:\\Users\\Philipp\\Documents\\Sehr\\Lange\\Ordnerstruktur\\Notizen\\datei.txt"
    short = shorten_path(long, 40)
    assert len(short) <= 40 and "…" in short and short.endswith("datei.txt")


def test_ipc_roundtrip_and_garbage(tmp_path: Path) -> None:
    a, b = tmp_path / "a.txt", tmp_path / "b.md"
    data = encode_open_request([a, b])
    assert data.endswith(b"\n")
    assert decode_open_request(data) == [str(a.resolve()), str(b.resolve())]
    assert decode_open_request(b"kein json") == []
    assert decode_open_request(b'{"open": "nicht liste"}') == []
    assert decode_open_request(b'{"open": [1, "", "ok"]}') == ["ok"]


def test_server_name_depends_on_root(tmp_path: Path) -> None:
    assert server_name(tmp_path) == server_name(str(tmp_path))
    assert server_name(tmp_path) != server_name(tmp_path / "andere")
    assert server_name(tmp_path).startswith("notex-")


def test_file_arguments_filters(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("x")
    assert file_arguments([str(f), "--flag", str(tmp_path / "fehlt.txt"), str(tmp_path)]) == [f.resolve()]
