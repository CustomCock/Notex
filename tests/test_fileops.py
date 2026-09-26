import os
from pathlib import Path

import pytest

from notex.core import fileops


def test_atomic_write_creates_file_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "neu.txt"
    fileops.atomic_write_bytes(target, b"inhalt")
    assert target.read_bytes() == b"inhalt"
    assert os.listdir(tmp_path) == ["neu.txt"]


def test_atomic_write_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "alt.txt"
    target.write_bytes(b"alt")
    fileops.atomic_write_bytes(target, b"neu")
    assert target.read_bytes() == b"neu"
    assert os.listdir(tmp_path) == ["alt.txt"]


def test_atomic_write_keeps_old_content_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simuliert einen Absturz zwischen Schreiben und Umbenennen: die alte Datei bleibt unversehrt."""
    target = tmp_path / "wichtig.txt"
    target.write_bytes(b"alter Inhalt")

    def kaputt(src, dst):
        raise OSError("Platte weg")

    monkeypatch.setattr(fileops.os, "replace", kaputt)
    with pytest.raises(OSError):
        fileops.atomic_write_bytes(target, b"neuer Inhalt")
    assert target.read_bytes() == b"alter Inhalt"
    assert os.listdir(tmp_path) == ["wichtig.txt"]  # Temp-Datei wurde aufgeräumt


def test_save_text_file_uses_encoding_and_eol(tmp_path: Path) -> None:
    target = tmp_path / "t.txt"
    fileops.save_text_file(target, "a\nb\n", "utf-8-sig", "\r\n")
    assert target.read_bytes() == b"\xef\xbb\xbfa\r\nb\r\n"


def test_unique_path(tmp_path: Path) -> None:
    assert fileops.unique_path(tmp_path, "Neu", ".txt").name == "Neu.txt"
    (tmp_path / "Neu.txt").touch()
    assert fileops.unique_path(tmp_path, "Neu", ".txt").name == "Neu (2).txt"


def test_create_rename_move(tmp_path: Path) -> None:
    f = fileops.create_file(tmp_path, "a.txt")
    with pytest.raises(FileExistsError):
        fileops.create_file(tmp_path, "a.txt")
    f = fileops.rename_path(f, "b.txt")
    assert f.name == "b.txt" and f.exists()
    sub = fileops.create_folder(tmp_path, "sub")
    moved = fileops.move_path(f, sub)
    assert moved == sub / "b.txt" and moved.exists()


def test_is_within(tmp_path: Path) -> None:
    assert fileops.is_within(tmp_path / "a" / "b", tmp_path)
    assert not fileops.is_within(tmp_path.parent, tmp_path)
