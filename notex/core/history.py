"""Lokale Versionshistorie: Schnappschüsse von Textdateien in history/ neben der App. Ohne Qt.

Aufbau auf der Platte (portabel, nichts in AppData):
  history/
    index.json                         {"version": 1, "files": {"<id>": {"path": "rel/pfad.md", "versions": [...]}}}
    objects/ab/abcdef….z               Inhalt als zlib, Name = SHA-256 des UTF-8-Texts

- Deduplizierung: gleicher Inhalt = gleiches Objekt, egal in welcher Datei oder Version. Ist der neue
  Inhalt gleich dem letzten Schnappschuss der Datei, entsteht keine neue Version.
- Umbenennen/Verschieben: der Eintrag hängt an einer ID, nicht am Pfad – rename() zieht nur den Pfad nach
  (auch für ganze Ordner).
- Ausdünnung (thin): die jüngsten Versionen bleiben vollständig, ältere werden auf eine pro Zeitfenster
  reduziert (siehe RETENTION). Die neueste Version einer Datei bleibt immer.
- Größenlimit (enforce_limit): ist history/objects größer als erlaubt, fallen die ältesten Versionen weg
  (nie die neueste einer Datei), danach werden nicht mehr benutzte Objekte gelöscht.
- Verschlüsselte Notizen (.ntx) landen NIE in der Historie – sie würde Klartext speichern.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import time
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notex.core.fileops import ENCRYPTED_SUFFIXES, atomic_write_bytes

INDEX_VERSION = 1
EXCLUDED_SUFFIXES = ENCRYPTED_SUFFIXES
DEFAULT_MAX_BYTES = 200 * 1024 * 1024     # komprimierte Objekte insgesamt
DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024  # größere Dateien bekommen keine Schnappschüsse

HOUR, DAY, WEEK = 3600, 86400, 7 * 86400
# (bis zu diesem Alter, höchstens eine Version pro Fenster); 0 = alle behalten
RETENTION: list[tuple[float, float]] = [
    (DAY, 0),            # letzte 24 Stunden: alles
    (7 * DAY, HOUR),     # bis 7 Tage: eine pro Stunde
    (30 * DAY, DAY),     # bis 30 Tage: eine pro Tag
    (365 * DAY, WEEK),   # bis 1 Jahr: eine pro Woche
    (float("inf"), 30 * DAY),   # älter: eine pro Monat
]


@dataclass(frozen=True)
class Version:
    timestamp: float
    sha: str
    size: int        # Zeichen des Texts
    label: str = ""  # z. B. "vor Ersetzen", "wiederhergestellt"

    def to_json(self) -> dict[str, Any]:
        data = {"t": round(self.timestamp, 3), "sha": self.sha, "size": self.size}
        if self.label:
            data["label"] = self.label
        return data

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Version | None":
        try:
            sha = str(data["sha"])
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                return None
            return Version(float(data["t"]), sha, int(data.get("size", 0)), str(data.get("label", "")))
        except (KeyError, TypeError, ValueError):
            return None


def is_excluded(rel: str) -> bool:
    return rel.lower().endswith(EXCLUDED_SUFFIXES)


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class History:
    def __init__(self, folder: Path, max_bytes: int = DEFAULT_MAX_BYTES,
                 max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
        self.folder = Path(folder)
        self.objects = self.folder / "objects"
        self.index_path = self.folder / "index.json"
        self.max_bytes = max_bytes
        self.max_file_bytes = max_file_bytes
        self.files: dict[str, dict[str, Any]] = {}   # id -> {"path": rel, "versions": [Version]}
        self._by_path: dict[str, str] = {}           # rel (klein) -> id
        self._load()

    # ---- Index --------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        files = raw.get("files", {}) if isinstance(raw, dict) else {}
        for file_id, entry in (files.items() if isinstance(files, dict) else []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                continue
            versions = [v for v in (Version.from_json(x) for x in entry.get("versions", []) if isinstance(x, dict)) if v]
            if not versions or is_excluded(entry["path"]):
                continue
            versions.sort(key=lambda v: v.timestamp)
            self.files[str(file_id)] = {"path": entry["path"], "versions": versions}
            self._by_path[entry["path"].lower()] = str(file_id)

    def _save_index(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        data = {"version": INDEX_VERSION,
                "files": {fid: {"path": e["path"], "versions": [v.to_json() for v in e["versions"]]}
                          for fid, e in self.files.items()}}
        atomic_write_bytes(self.index_path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))

    # ---- Objekte ------------------------------------------------------------------------------
    def _object_path(self, sha: str) -> Path:
        return self.objects / sha[:2] / f"{sha}.z"

    def _store(self, text: str, sha: str) -> None:
        path = self._object_path(sha)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, zlib.compress(text.encode("utf-8"), 6))

    def content(self, sha: str) -> str:
        """Text einer Version. Wirft OSError, wenn das Objekt fehlt, ValueError bei Beschädigung."""
        data = zlib.decompress(self._object_path(sha).read_bytes())
        text = data.decode("utf-8")
        if text_sha(text) != sha:
            raise ValueError("Schnappschuss beschädigt (Prüfsumme stimmt nicht)")
        return text

    # ---- Abfragen -----------------------------------------------------------------------------
    def versions(self, rel: str) -> list[Version]:
        """Versionen einer Datei, neueste zuerst."""
        file_id = self._by_path.get(rel.lower())
        return list(reversed(self.files[file_id]["versions"])) if file_id else []

    def tracked_paths(self) -> list[str]:
        return sorted(e["path"] for e in self.files.values())

    # ---- Schreiben ----------------------------------------------------------------------------
    def snapshot(self, rel: str, text: str, now: float | None = None, label: str = "") -> Version | None:
        """Neue Version, wenn sich der Text seit der letzten geändert hat. None = nichts gespeichert."""
        if is_excluded(rel) or len(text.encode("utf-8")) > self.max_file_bytes:
            return None
        now = time.time() if now is None else now
        sha = text_sha(text)
        file_id = self._by_path.get(rel.lower())
        if file_id is not None:
            versions = self.files[file_id]["versions"]
            if versions and versions[-1].sha == sha:
                return None
        else:
            file_id = uuid.uuid4().hex
            self.files[file_id] = {"path": rel, "versions": []}
            self._by_path[rel.lower()] = file_id
        self._store(text, sha)
        version = Version(now, sha, len(text), label)
        self.files[file_id]["versions"].append(version)
        self.files[file_id]["versions"] = thin(self.files[file_id]["versions"], now)
        self._save_index()
        return version

    def rename(self, old_rel: str, new_rel: str) -> int:
        """Pfad (Datei oder Ordner) umhängen. Gibt die Zahl der betroffenen Einträge zurück."""
        old_low = old_rel.lower().rstrip("/")
        changed = 0
        for file_id, entry in list(self.files.items()):
            path = entry["path"]
            low = path.lower()
            if low == old_low:
                new_path = new_rel
            elif low.startswith(old_low + "/"):
                new_path = new_rel.rstrip("/") + path[len(old_low):]
            else:
                continue
            if is_excluded(new_path):     # z. B. nach .ntx umbenannt: Klartext-Historie weg
                self._forget(file_id)
                changed += 1
                continue
            # Ziel hat schon eine eigene Historie (Datei wurde ersetzt): zusammenführen
            other = self._by_path.get(new_path.lower())
            self._by_path.pop(low, None)
            if other is not None and other != file_id:
                merged = sorted(self.files[other]["versions"] + entry["versions"], key=lambda v: v.timestamp)
                self.files[other]["versions"] = merged
                del self.files[file_id]
            else:
                entry["path"] = new_path
                self._by_path[new_path.lower()] = file_id
            changed += 1
        if changed:
            self._save_index()
            self.collect_garbage()
        return changed

    def _forget(self, file_id: str) -> None:
        entry = self.files.pop(file_id, None)
        if entry is not None:
            self._by_path.pop(entry["path"].lower(), None)

    def forget(self, rel: str) -> bool:
        """Historie einer Datei (oder eines Ordners) löschen, z. B. vor dem Verschlüsseln."""
        low = rel.lower().rstrip("/")
        ids = [fid for fid, e in self.files.items() if e["path"].lower() == low or e["path"].lower().startswith(low + "/")]
        for fid in ids:
            self._forget(fid)
        if ids:
            self._save_index()
            self.collect_garbage()
        return bool(ids)

    # ---- Aufräumen ----------------------------------------------------------------------------
    def object_bytes(self) -> int:
        total = 0
        for path in self.objects.glob("*/*.z"):
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    def collect_garbage(self) -> int:
        """Objekte löschen, auf die keine Version mehr zeigt. Gibt gelöschte Bytes zurück."""
        used = {v.sha for e in self.files.values() for v in e["versions"]}
        freed = 0
        for path in list(self.objects.glob("*/*.z")):
            if path.stem not in used:
                try:
                    freed += path.stat().st_size
                    path.unlink()
                except OSError:
                    pass
        return freed

    def enforce_limit(self) -> int:
        """Älteste Versionen entfernen, bis die Objekte unter max_bytes liegen. Gibt entfernte Versionen zurück."""
        removed = 0
        if self.object_bytes() <= self.max_bytes:
            return 0
        sizes: dict[str, int] = {}
        for path in self.objects.glob("*/*.z"):
            try:
                sizes[path.stem] = path.stat().st_size
            except OSError:
                pass
        total = sum(sizes.values())
        # Kandidaten: alle Versionen außer der neuesten jeder Datei, älteste zuerst
        candidates = sorted(((v.timestamp, fid, v) for fid, e in self.files.items() for v in e["versions"][:-1]),
                            key=lambda item: item[0])
        for _t, fid, version in candidates:
            if total <= self.max_bytes:
                break
            self.files[fid]["versions"].remove(version)
            removed += 1
            still_used = any(v.sha == version.sha for e in self.files.values() for v in e["versions"])
            if not still_used:
                total -= sizes.get(version.sha, 0)
        if removed:
            self._save_index()
            self.collect_garbage()
        return removed

    def clear(self) -> None:
        self.files.clear()
        self._by_path.clear()
        self._save_index()
        self.collect_garbage()


def thin(versions: list[Version], now: float) -> list[Version]:
    """Ausdünnen nach RETENTION: je Zeitfenster die jüngste Version behalten, die neueste immer."""
    if len(versions) <= 1:
        return list(versions)
    ordered = sorted(versions, key=lambda v: v.timestamp)
    newest = ordered[-1]
    kept: list[Version] = []
    seen: set[tuple[int, int]] = set()
    for version in reversed(ordered):      # neueste zuerst: pro Fenster gewinnt die jüngste
        if version is newest:
            kept.append(version)
            continue
        age = max(0.0, now - version.timestamp)
        for tier, (max_age, bucket) in enumerate(RETENTION):
            if age <= max_age:
                if bucket == 0:
                    kept.append(version)
                else:
                    key = (tier, int(version.timestamp // bucket))
                    if key not in seen:
                        seen.add(key)
                        kept.append(version)
                break
    return sorted(kept, key=lambda v: v.timestamp)


# ---- Diff ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DiffLine:
    kind: str            # " " gleich, "-" nur alt, "+" nur neu, "@" Abschnittskopf
    text: str
    old_no: int | None   # Zeilennummer in der alten Fassung (1-basiert)
    new_no: int | None


def diff_lines(old: str, new: str, context: int = 3) -> list[DiffLine]:
    """Zeilen-Diff mit Kontext, für das Diff-Panel. Leere Liste = identisch."""
    a, b = old.split("\n"), new.split("\n")
    result: list[DiffLine] = []
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for group in matcher.get_grouped_opcodes(context):
        first, last = group[0], group[-1]
        result.append(DiffLine("@", f"Zeilen {first[1] + 1}–{last[2]} → {first[3] + 1}–{last[4]}", None, None))
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for k in range(i2 - i1):
                    result.append(DiffLine(" ", a[i1 + k], i1 + k + 1, j1 + k + 1))
                continue
            if tag in ("replace", "delete"):
                for k in range(i1, i2):
                    result.append(DiffLine("-", a[k], k + 1, None))
            if tag in ("replace", "insert"):
                for k in range(j1, j2):
                    result.append(DiffLine("+", b[k], None, k + 1))
    return result


def diff_stats(lines: list[DiffLine]) -> tuple[int, int]:
    return sum(1 for d in lines if d.kind == "+"), sum(1 for d in lines if d.kind == "-")


def format_age(timestamp: float, now: float | None = None) -> str:
    """„gerade eben“, „vor 5 Min.“, „vor 3 Std.“, „gestern 14:05“, sonst Datum."""
    now = time.time() if now is None else now
    delta = max(0, now - timestamp)
    local = time.localtime(timestamp)
    if delta < 60:
        return "gerade eben"
    if delta < HOUR:
        return f"vor {int(delta // 60)} Min."
    if delta < 12 * HOUR:
        return f"vor {int(delta // HOUR)} Std."
    today = time.localtime(now)
    if local.tm_yday == today.tm_yday and local.tm_year == today.tm_year:
        return time.strftime("heute %H:%M", local)
    yesterday = time.localtime(now - DAY)
    if local.tm_yday == yesterday.tm_yday and local.tm_year == yesterday.tm_year:
        return time.strftime("gestern %H:%M", local)
    return time.strftime("%d.%m.%Y %H:%M", local)


def history_folder(app_root: Path) -> Path:
    """history/ liegt neben data/ und config.json – portabel wie alles andere."""
    return Path(app_root) / "history"
