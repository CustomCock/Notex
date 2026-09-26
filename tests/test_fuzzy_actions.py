from pathlib import Path

from notex.core.actions import ActionRegistry, Command
from notex.core.file_index import FileIndex, scan_files
from notex.core.fuzzy import highlight, match, parse_goto


def test_fuzzy_match_basics() -> None:
    assert match("", "egal").score == 0
    assert match("ntz", "notizen.md") is not None
    assert match("xyz", "notizen.md") is None
    assert match("Notizen", "notizen.md").indices == (0, 1, 2, 3, 4, 5, 6)


def test_fuzzy_prefers_word_starts_and_prefix() -> None:
    assert match("no", "notizen.md").score > match("no", "anno.txt").score
    assert match("lp", "lpic1-lernplan.md").score > match("lp", "help.txt").score
    assert match("readme", "README.md").score > match("readme", "read-me-later.txt").score


def test_highlight_and_goto() -> None:
    assert highlight("abc", (0, 2), "<b>", "</b>") == "<b>a</b>b<b>c</b>"
    assert parse_goto(":123") == ("", 123)
    assert parse_goto("notizen:7") == ("notizen", 7)
    assert parse_goto("notizen") == ("notizen", None)
    assert parse_goto("C:\\x.txt") == ("C:\\x.txt", None)


def test_registry_search_and_recent() -> None:
    calls = []
    reg = ActionRegistry()
    reg.add("save", "Speichern", lambda: calls.append("save"), category="Datei", shortcut="Ctrl+S")
    reg.add("save_all", "Alle speichern", lambda: calls.append("all"), category="Datei")
    reg.add("theme_matt", "Preset Matt", lambda: None, category="Theme", keywords="dunkel grau")
    assert [h.command.id for h in reg.search("spei")] == ["save", "save_all"]
    assert reg.run("save_all") and calls == ["all"]
    assert reg.search("")[0].command.id == "save_all"          # zuletzt benutzt zuerst
    assert reg.search("grau")[0].command.id == "theme_matt"     # Schlüsselwörter zählen
    assert reg.run("gibtsnicht") is False
    assert reg.get("save").label == "Datei: Speichern"


def test_scan_files_and_index(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / ".versteckt").mkdir()
    (tmp_path / "a" / "notizen.md").write_text("x")
    (tmp_path / "todo.txt").write_text("x")
    (tmp_path / "bild.png").write_text("x")
    (tmp_path / ".versteckt" / "geheim.txt").write_text("x")
    files = scan_files(tmp_path, [".md", ".txt"])
    assert files == ["a/notizen.md", "todo.txt"]
    index = FileIndex()
    index.set_files(files)
    index.set_externals(["/tmp/extern.txt"])
    hits = index.search("not", recent=[])
    assert hits[0].relative == "a/notizen.md"
    assert index.search("extern", recent=[])[0].external is True
    assert index.search("t", recent=["todo.txt"])[0].relative == "todo.txt"   # zuletzt geöffnet vorn
    assert index.search("a/", recent=[])[0].relative == "a/notizen.md"         # Pfadtreffer
