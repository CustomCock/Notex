"""Tests für die Neue-Datei-Vorlagen (core/newfile.py) – ohne Qt."""
from __future__ import annotations

from notex.core import newfile


def test_types_have_unique_keys_and_extensions():
    keys = [t.key for t in newfile.TYPES]
    assert len(keys) == len(set(keys))
    for t in newfile.TYPES:
        assert t.extension.startswith(".")
        assert t.label


def test_suggested_name():
    assert newfile.suggested_name("markdown") == "Neu.md"
    assert newfile.suggested_name("json") == "Neu.json"
    assert newfile.suggested_name("unbekannt") == "Neu.txt"


def test_clean_starter_removes_cursor():
    assert newfile.CURSOR not in newfile.clean_starter("# §|\n\n")
    assert newfile.clean_starter("# §|\n") == "# \n"


def test_cursor_offset():
    assert newfile.cursor_offset("# §|\n\n") == 2
    assert newfile.cursor_offset("kein marker") == 0


def test_build_content_lf_and_crlf():
    md = newfile.BY_KEY["markdown"].starter
    lf = newfile.build_content(md, "lf")
    crlf = newfile.build_content(md, "crlf")
    assert "\r" not in lf
    assert "\r\n" in crlf
    # gleicher Inhalt, nur andere Zeilenenden
    assert lf.replace("\n", "X") == crlf.replace("\r\n", "X")
    assert newfile.CURSOR not in lf


def test_build_content_normalizes_existing_crlf():
    assert newfile.build_content("a\r\nb\r\n", "lf") == "a\nb\n"
    assert newfile.build_content("a\nb\n", "crlf") == "a\r\nb\r\n"


def test_encode_content_roundtrip():
    data = newfile.encode_content(newfile.BY_KEY["json"].starter, "lf", "utf-8")
    assert isinstance(data, bytes)
    assert b"{" in data and b"\r" not in data
