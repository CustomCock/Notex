"""Tests für die Orte-Logik des Explorers (core/places.py) – ohne Qt."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from notex.core import places


def test_notes_place(tmp_path):
    place = places.notes_place(tmp_path)
    assert place.kind == "notes"
    assert place.path == tmp_path
    assert place.key == "notes"


def test_quick_access_dedup_and_normalize():
    import os
    config = {"quick_access": ["/a/b", "/a/b/", "/a//b", "", 123, "/c"]}
    paths = places.quick_access_paths(config)
    # /a/b, /a/b/, /a//b normalisieren auf denselben Pfad → nur einmal; leere/nicht-Strings raus
    # (Trennzeichen plattformabhängig – deshalb über os.path.normpath vergleichen)
    norm = [str(p) for p in paths]
    assert norm == [os.path.normpath("/a/b"), os.path.normpath("/c")]


def test_add_and_remove_pinned():
    config = {}
    assert places.add_pinned(config, "/home/user/logs") is True
    assert places.is_pinned(config, "/home/user/logs") is True
    # zweites Anheften desselben Ordners ändert nichts
    assert places.add_pinned(config, "/home/user/logs/") is False
    assert len(config["quick_access"]) == 1
    # entfernen
    assert places.remove_pinned(config, "/home/user/logs") is True
    assert places.is_pinned(config, "/home/user/logs") is False
    assert places.remove_pinned(config, "/home/user/logs") is False


def test_pinned_places_labels():
    config = {"quick_access": ["/home/user/Downloads", "/var/log"]}
    pinned = places.pinned_places(config)
    assert [p.label for p in pinned] == ["Downloads", "log"]
    assert all(p.kind == "pinned" and p.removable for p in pinned)


def test_home_place():
    place = places.home_place()
    assert place.kind == "home"
    assert place.path == Path.home()


def test_this_pc_has_home_first():
    pcs = places.this_pc_places()
    assert pcs[0].kind == "home"
    assert any(p.kind == "drive" for p in pcs)


def test_is_within(tmp_path):
    child = tmp_path / "a" / "b"
    assert places.is_within(child, tmp_path) is True
    assert places.is_within(tmp_path, child) is False


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Unix-Systempfade")
def test_is_system_path_unix():
    assert places.is_system_path("/etc") is True
    assert places.is_system_path("/etc/ssh/sshd_config") is True
    assert places.is_system_path("/usr/bin") is True
    assert places.is_system_path("/") is True
    # Ein normaler Benutzer-Home unter /home ist kein Systemordner (der Test läuft evtl. als root)
    assert places.is_system_path("/home/alice/notizen") is False


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-Systempfade")
def test_is_system_path_windows():
    assert places.is_system_path(r"C:\Windows") is True
    assert places.is_system_path(r"C:\Windows\System32\drivers") is True
    assert places.is_system_path(r"C:\Program Files\App") is True
    assert places.is_system_path("C:\\") is True


def test_is_system_path_notes_is_safe(tmp_path):
    # Ein normaler Projektordner (nicht in Systempfaden) ist kein Systemordner
    folder = tmp_path / "projekt"
    folder.mkdir()
    assert places.is_system_path(folder) is False
