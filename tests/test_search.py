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


# ---- v1.2: Abfragesprache, Regex, Ganzes Wort, Ersetzen ------------------------------------------
from notex.core.search import (HAS_TIMEOUT, RegexTimeout, apply_replace, match_spans, parse_query, preview_replace,
                               replace_query_ok)


def test_parse_query_filters_and_phrases() -> None:
    q = parse_query('apfel "grüne birne" ext:md,txt path:Projekte -path:archiv ext:log')
    assert q.terms == ["apfel", "grüne birne"]
    assert q.extensions == [".md", ".txt", ".log"]
    assert q.path_includes == ["projekte"] and q.path_excludes == ["archiv"]
    assert q.allows_path("Projekte/Notex/a.md") and not q.allows_path("Projekte/archiv/a.md") and not q.allows_path("x/a.md")
    assert q.allows_extension(".MD") and not q.allows_extension(".py")
    assert parse_query("   ").empty and not parse_query("ext:md").empty


def test_and_semantics_and_spans() -> None:
    q = parse_query("apfel kuchen")
    assert match_spans(q, "Der Apfelkuchen") == [(4, 9), (9, 15)]
    assert match_spans(q, "nur apfel") is None
    q = parse_query('"apfel kuchen"')
    assert match_spans(q, "apfel kuchen ja") == [(0, 12)] and match_spans(q, "apfelkuchen") is None


def test_whole_word() -> None:
    q = parse_query("apfel", whole_word=True)
    assert match_spans(q, "ein apfel hier") == [(4, 9)]
    assert match_spans(q, "apfelkuchen") is None and match_spans(q, "(apfel)") == [(1, 6)]


def test_regex_mode_valid_invalid_and_case() -> None:
    q = parse_query(r"ap+fel\d+ ext:txt", regex=True)
    assert q.error is None and q.extensions == [".txt"] and q.terms == [r"ap+fel\d+"]
    assert match_spans(q, "APFEL12 und apfel3") == [(0, 7), (12, 18)]
    bad = parse_query("a(b", regex=True)
    assert bad.error and "Ungültige Regex" in bad.error and not bad.needles
    assert match_spans(parse_query("Apfel", case_sensitive=True), "apfel") is None
    assert match_spans(parse_query(r"a.c", regex=True, whole_word=True), "xabcx abc") == [(6, 9)]


def test_search_with_filters_regex_and_error(tree: Path) -> None:
    result = search(tree, "apfel path:tief", SearchOptions(by_name=False, full_text=True, **OPTS))
    assert [m.relative for m in result.files] == ["a/tief/log.log"]
    result = search(tree, "apfel -path:tief ext:txt", SearchOptions(by_name=True, full_text=True, **OPTS))
    assert [m.relative for m in result.files] == ["Bericht.txt"] and result.names == []
    result = search(tree, r"^Erste\s+Z", SearchOptions(by_name=False, full_text=True, regex=True, **OPTS))
    assert [m.relative for m in result.files] == ["Bericht.txt"]
    result = search(tree, "a(b", SearchOptions(by_name=True, full_text=True, regex=True, **OPTS))
    assert result.error and result.files == [] and result.names == []
    # ext:-Filter erweitert auf Endungen, die nicht im Baum stehen
    (tree / "roh.py").write_text("apfel = 1\n", encoding="utf-8")
    result = search(tree, "apfel ext:py", SearchOptions(by_name=False, full_text=True, **OPTS))
    assert [m.relative for m in result.files] == ["roh.py"]


@pytest.mark.skipif(not HAS_TIMEOUT, reason="regex-Modul ohne Timeout nicht installiert")
def test_catastrophic_regex_times_out(tmp_path: Path) -> None:
    (tmp_path / "boom.txt").write_text("a" * 40 + "!\n", encoding="utf-8")
    result = search(tmp_path, r"(a|a)+$", SearchOptions(by_name=False, full_text=True, regex=True, extensions=(".txt",)))
    assert result.timed_out and result.error and "Timeout" in result.error
    with pytest.raises(RegexTimeout):
        match_spans(parse_query(r"(a|a)+$", regex=True), "a" * 40 + "!")


def test_replace_preview_and_apply() -> None:
    text = "Apfel eins\nkein treffer\napfel zwei apfel\n"
    q = parse_query("apfel")
    assert replace_query_ok(q) is None and replace_query_ok(parse_query("a b")) is not None
    preview = preview_replace(text, q, "Birne")
    assert [(p.line_no, p.after) for p in preview] == [(1, "Birne eins"), (3, "Birne zwei Birne")]
    new_text, count = apply_replace(text, q, "Birne", only_lines={3})
    assert new_text == "Apfel eins\nkein treffer\nBirne zwei Birne\n" and count == 1
    assert apply_replace(text, q, "Birne")[1] == 2
    # Klartext-Ersatz behandelt Backslashes wörtlich, Regex-Ersatz kennt Gruppen
    assert apply_replace("a1", parse_query("a1"), r"\1x")[0] == r"\1x"
    assert apply_replace("a1 a2", parse_query(r"a(\d)", regex=True), r"b\1")[0] == "b1 b2"
    q_word = parse_query("apfel", whole_word=True)
    assert apply_replace("apfelkuchen apfel", q_word, "birne")[0] == "apfelkuchen birne"


def test_encrypted_notes_never_searched_in_full_text(tmp_path: Path) -> None:
    (tmp_path / "geheim.ntx").write_bytes(b"NOTEXENC apfel im Chiffretext")
    (tmp_path / "offen.txt").write_text("apfel\n", encoding="utf-8")
    result = search(tmp_path, "apfel ext:ntx,txt", SearchOptions(by_name=False, full_text=True, extensions=(".txt", ".ntx")))
    assert [m.relative for m in result.files] == ["offen.txt"]
    result = search(tmp_path, "geheim", SearchOptions(by_name=True, full_text=False, extensions=(".ntx",)))
    assert [m.relative for m in result.names] == ["geheim.ntx"]      # Dateiname bleibt auffindbar
