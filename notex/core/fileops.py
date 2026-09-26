"""Dateioperationen ohne Qt: atomar speichern, anlegen, umbenennen, Papierkorb."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from notex.core.encoding import encode_text


ENCRYPTED_SUFFIXES = (".ntx",)   # verschlüsselte Notizen: Inhalte nie lesen, indexieren oder sichern


def is_encrypted_path(path: Path | str) -> bool:
    return str(path).lower().endswith(ENCRYPTED_SUFFIXES)


FULL_HASH_LIMIT = 16 * 1024 * 1024
EDGE_BYTES = 1024 * 1024


def file_signature(path: Path) -> bytes | None:
    """Fingerabdruck für „extern geändert?“: bis 16 MB SHA-1 über den Inhalt; darüber Größe + Änderungszeit +
    SHA-1 über das erste und letzte MB – sonst würde jede große Datei (Log, Hex-Tab) beim Öffnen komplett gelesen.
    None, wenn die Datei nicht lesbar ist."""
    import hashlib
    try:
        stat = path.stat()
        with open(path, "rb") as handle:
            if stat.st_size <= FULL_HASH_LIMIT:
                return hashlib.sha1(handle.read()).digest()
            hasher = hashlib.sha1(f"{stat.st_size}:{stat.st_mtime_ns}:".encode())
            hasher.update(handle.read(EDGE_BYTES))
            handle.seek(max(0, stat.st_size - EDGE_BYTES))
            hasher.update(handle.read(EDGE_BYTES))
            return hasher.digest()
    except OSError:
        return None


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Schreibt erst eine Temp-Datei im selben Ordner und tauscht sie dann per os.replace ein.

    Warum derselbe Ordner? os.replace ist nur innerhalb eines Laufwerks atomar.
    Warum fsync? Damit die Daten wirklich auf der Platte sind, bevor umbenannt wird.
    Ergebnis: Entweder liegt die alte Datei komplett da oder die neue – nie ein halber Mix.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_text_file(path: Path, text: str, encoding: str, eol: str) -> None:
    atomic_write_bytes(path, encode_text(text, encoding, eol))


def unique_path(folder: Path, stem: str, suffix: str = "") -> Path:
    """Liefert einen noch nicht belegten Namen: 'Neu.txt', 'Neu (2).txt', 'Neu (3).txt' ..."""
    candidate = folder / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def create_file(folder: Path, name: str) -> Path:
    path = Path(folder) / name
    if path.exists():
        raise FileExistsError(f"Existiert bereits: {path.name}")
    path.touch()
    return path


def create_folder(folder: Path, name: str) -> Path:
    path = Path(folder) / name
    path.mkdir()
    return path


def rename_path(path: Path, new_name: str) -> Path:
    target = Path(path).with_name(new_name)
    if target.exists():
        raise FileExistsError(f"Existiert bereits: {target.name}")
    Path(path).rename(target)
    return target


def move_path(path: Path, target_folder: Path) -> Path:
    target = Path(target_folder) / Path(path).name
    if target.exists():
        raise FileExistsError(f"Existiert bereits: {target.name}")
    shutil.move(str(path), str(target))
    return target


def move_to_trash(path: Path) -> None:
    """In den Papierkorb statt endgültig löschen – send2trash spricht die OS-API an."""
    from send2trash import send2trash

    send2trash(str(path))


def reveal_in_file_manager(path: Path) -> None:
    """Windows: Explorer öffnen und die Datei markieren. Andere Systeme: Ordner öffnen."""
    path = Path(path)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
        return
    folder = path if path.is_dir() else path.parent
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(folder)])


def is_within(path: Path, root: Path) -> bool:
    """Sicherheitscheck: liegt `path` wirklich unterhalb von `root`?"""
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False
