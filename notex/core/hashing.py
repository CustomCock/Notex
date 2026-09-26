"""Prüfsummen (MD5, SHA-1, SHA-256, SHA-512) für Dateien – blockweise, mit Fortschritt und Abbruch. Ohne Qt.

MD5 und SHA-1 sind nur zum Vergleichen mit veröffentlichten Werten gedacht, nicht als Sicherheitsnachweis.
Verschlüsselte Notizen (.ntx) werden als Datei auf der Platte gehasht, also nur der Geheimtext – nie Klartext.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable

ALGORITHMS = ("md5", "sha1", "sha256", "sha512")
LABELS = {"md5": "MD5", "sha1": "SHA-1", "sha256": "SHA-256", "sha512": "SHA-512"}
HEX_LENGTHS = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
CHUNK = 1024 * 1024


class Cancelled(Exception):
    pass


def hash_file(path: Path | str, algorithms=ALGORITHMS, progress: Callable[[int, int], None] | None = None,
              cancelled: Callable[[], bool] | None = None, chunk_size: int = CHUNK) -> dict[str, str]:
    """Alle Algorithmen in EINEM Lesedurchgang. Wirft Cancelled bei Abbruch, OSError bei Lesefehlern."""
    hashers = {name: hashlib.new(name) for name in algorithms}
    path = Path(path)
    total = path.stat().st_size
    done = 0
    with open(path, "rb") as handle:
        while True:
            if cancelled is not None and cancelled():
                raise Cancelled()
            block = handle.read(chunk_size)
            if not block:
                break
            for hasher in hashers.values():
                hasher.update(block)
            done += len(block)
            if progress is not None:
                progress(done, total)
    return {name: hasher.hexdigest() for name, hasher in hashers.items()}


def normalize_digest(text: str) -> str:
    """Eingabe zum Vergleichen säubern: „SHA256: AB CD…“, „ab:cd:…“, „<hash>  datei.iso“ (sha256sum) → „abcd…“."""
    value = text.strip()
    label = re.match(r"^([A-Za-z][A-Za-z0-9-]*)\s*[:=]\s*", value)
    if label and re.search(r"[g-zG-Z]", label.group(1)):      # „SHA256:“, „MD5 =“ – aber nicht „e3:b0:…“
        value = value[label.end():]
    value = re.split(r"\s{2,}|\t|\s\*", value)[0]            # sha256sum: „<hash>  name“ bzw. „<hash> *name“
    cleaned = re.sub(r"[\s:-]", "", value).lower()
    return cleaned if re.fullmatch(r"[0-9a-f]+", cleaned) else ""


def match_digest(expected: str, digests: dict[str, str]) -> str | None:
    """Algorithmus, dessen Prüfsumme dem eingegebenen Wert entspricht – sonst None."""
    value = normalize_digest(expected)
    if not value:
        return None
    for name, digest in digests.items():
        if digest.lower() == value:
            return name
    return None


def expected_algorithm(expected: str) -> str | None:
    """Welcher Algorithmus zur Länge des eingegebenen Werts passt (für die Anzeige „erwartet SHA-256“)."""
    return HEX_LENGTHS.get(len(normalize_digest(expected)))
