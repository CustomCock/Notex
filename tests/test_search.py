"""Tests für core/search.py – laufen ohne Qt."""
import threading
from pathlib import Path

import pytest

from notex.core.search import SearchOptions, iter_files, search


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "tief").mkdir()
    (tmp_path / "Bericht.txt").write_text("Erste Zeile\nHier steht Apfelkuchen\n", encoding="utf-8")
    (tmp_path / "a" / "apfel-notiz.md").write_text("nichts\n", encoding="utf-8")
    (tmp_path / "a" / "tief" / "log.log").write_text("APFEL ganz tief\nnoch ein apfel\n", encoding="utf-8")
    (tmp_path / "bild.png").write_bytes(b"\x89PNG kein text apfel")
    (tmp_path / "a" / "cp1252.txt").write_bytes("Äpfel mit Umlaut\n".encode("cp1252"))
    return tmp_path


OPTS = dict(extensions=(".txt", ".md", ".log"))


def test_iter_files_recursive_and_filtered(tree: Path) -> None:
    names = [p.name for p in iter_files(tree, (".txt", ".md", ".log"))]
    assert names == ["Bericht.txt", "apfel-notiz.md", "cp1252.txt", "log.log"]  # png fehlt, Unterordner dabei


def test_name_search_is_case_insensitive(tree: Path) -> None:
    result = search(tree, "APFEL", SearchOptions(by_name=True, full_text=False, **OPTS))
    assert [m.relative for m in result.names] == ["a/apfel-notiz.md"]
    match = result.names[0]
    assert match.path.name[match.start:match.end] == "apfel"


def test_fulltext_search_recursive_with_line_numbers(tree: Path) -> None:
    result = search(tree, "apfel", SearchOptions(by_name=False, full_text=True, **OPTS))
    by_file = {m.relative: m for m in result.files}
    assert set(by_file) == {"Bericht.txt", "a/tief/log.log"}
    assert [line.line_no for line in by_file["a/tief/log.log"].lines] == [1, 2]
    hit = by_file["Bericht.txt"].lines[0]
    assert hit.line_no == 2
    assert hit.snippet[hit.start:hit.end] == "Apfel"
    assert hit.column == "Hier steht Apfelkuchen".index("Apfel")


def test_fulltext_handles_cp1252(tree: Path) -> None:
    result = search(tree, "äpfel", SearchOptions(by_name=False, full_text=True, **OPTS))
    assert [m.relative for m in result.files] == ["a/cp1252.txt"]


def test_snippet_is_shortened_for_long_lines(tmp_path: Path) -> None:
    (tmp_path / "lang.txt").write_text("x" * 200 + "TREFFER" + "y" * 200, encoding="utf-8")
    result = search(tmp_path, "treffer", SearchOptions(by_name=False, full_text=True, extensions=(".txt",)))
    line = result.files[0].lines[0]
    assert line.snippet.startswith("…") and line.snippet.endswith("…")
    assert line.snippet[line.start:line.end] == "TREFFER"
    assert len(line.snippet) < 120


def test_size_limit_skips_large_files(tmp_path: Path) -> None:
    (tmp_path / "klein.txt").write_text("apfel\n", encoding="utf-8")
    (tmp_path / "gross.txt").write_text("apfel\n" * 1000, encoding="utf-8")
    options = SearchOptions(by_name=False, full_text=True, extensions=(".txt",), max_bytes=100)
    result = search(tmp_path, "apfel", options)
    assert [m.relative for m in result.files] == ["klein.txt"]
    assert result.skipped_large == 1


def test_both_modes_and_callbacks(tree: Path) -> None:
    names, files = [], []
    result = search(tree, "apfel", SearchOptions(by_name=True, full_text=True, **OPTS),
                    on_name=names.append, on_file=files.append)
    assert len(names) == len(result.names) == 1
    assert len(files) == len(result.files) == 2


def test_empty_query_or_no_mode_returns_nothing(tree: Path) -> None:
    assert search(tree, "   ", SearchOptions(by_name=True, full_text=True, **OPTS)).names == []
    assert search(tree, "apfel", SearchOptions(by_name=False, full_text=False, **OPTS)).names == []


def test_cancel_stops_search(tree: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    result = search(tree, "apfel", SearchOptions(by_name=True, full_text=True, **OPTS), cancel=cancel)
    assert result.cancelled is True
    assert result.names == [] and result.files == []
