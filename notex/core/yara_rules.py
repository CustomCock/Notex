"""YARA-Regeln kompilieren und gegen Dateien/Ordner testen (yara-python, Apache-2.0). Ohne Qt.

- compile_rules: Syntaxfehler mit Zeilennummer (RuleError), include-Dateien relativ zum Ordner der Regeldatei.
- scan: Datei oder Ordner (rekursiv, keine Symlinks), libyara liest die Dateien selbst per mmap – nichts wird
  komplett in den Python-Speicher geladen. Fortschritt je Datei, Abbrechen zwischen Dateien, Zeitlimit je Datei.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_HITS = 20_000              # Trefferzeilen insgesamt (Stellen, nicht Dateien)
MAX_INSTANCES = 200            # Stellen je String und Datei
TIMEOUT = 60                   # Sekunden je Datei


class Cancelled(Exception):
    pass


class YaraMissing(Exception):
    pass


@dataclass
class RuleError(Exception):
    message: str
    line: int | None = None

    def __str__(self) -> str:
        return f"Zeile {self.line}: {self.message}" if self.line else self.message


@dataclass
class Hit:
    rule: str
    file: Path
    offset: int
    identifier: str
    data: bytes
    length: int
    tags: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    hits: list[Hit] = field(default_factory=list)
    files: int = 0
    matched_files: int = 0
    errors: list[str] = field(default_factory=list)
    truncated: bool = False


def available() -> bool:
    try:
        import yara  # noqa: F401
        return True
    except ImportError:
        return False


def _yara():
    try:
        import yara
    except ImportError as error:
        raise YaraMissing("yara-python ist nicht installiert – YARA steht in diesem Build nicht zur Verfügung") from error
    return yara


_LINE = re.compile(r"(?:line (\d+)|\((\d+)\))")


def parse_error(text: str) -> RuleError:
    """„line 4: undefined string "$y"“ bzw. „regel.yar(4): …“ → RuleError(Meldung, Zeile)."""
    match = _LINE.search(text)
    line = int(match.group(1) or match.group(2)) if match else None
    message = text[match.end():].lstrip(": ") if match else text
    return RuleError(message or text, line)


def compile_rules(source: str, base_dir: Path | None = None):
    """Regeltext kompilieren. Wirft RuleError (mit Zeile) oder YaraMissing."""
    yara = _yara()

    def include(requested: str, _parent, _namespace):
        target = Path(requested)
        if not target.is_absolute() and base_dir is not None:
            target = base_dir / target
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    try:
        return yara.compile(source=source, include_callback=include)
    except yara.SyntaxError as error:
        raise parse_error(str(error)) from None
    except yara.Error as error:
        raise RuleError(str(error)) from None


def rule_names(source: str) -> list[str]:
    return re.findall(r"^\s*(?:(?:private|global)\s+)*rule\s+(\w+)", source, re.M)


def iter_files(target: Path, recursive: bool = True):
    if target.is_file():
        yield target
        return
    if not recursive:
        yield from sorted(p for p in target.iterdir() if p.is_file() and not p.is_symlink())
        return
    for root, dirs, files in os.walk(target, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not Path(root, d).is_symlink())
        for name in sorted(files):
            path = Path(root, name)
            if not path.is_symlink():
                yield path


def scan(rules, target: Path, recursive: bool = True, progress: Callable[[int, int], None] | None = None,
         cancelled: Callable[[], bool] | None = None) -> ScanResult:
    yara = _yara()
    target = Path(target)
    files = list(iter_files(target, recursive))
    result = ScanResult()
    for index, path in enumerate(files):
        if cancelled and cancelled():
            raise Cancelled()
        if progress:
            progress(index, len(files))
        result.files += 1
        try:
            if path.stat().st_size == 0:
                continue
            matches = rules.match(filepath=str(path), timeout=TIMEOUT)
        except yara.TimeoutError:
            result.errors.append(f"{path.name}: Zeitlimit ({TIMEOUT} s) überschritten")
            continue
        except (yara.Error, OSError) as error:
            result.errors.append(f"{path.name}: {error}")
            continue
        if matches:
            result.matched_files += 1
        for match in matches:
            strings = list(match.strings)
            if not strings:                                   # Regel ohne Strings (nur condition)
                result.hits.append(Hit(match.rule, path, -1, "", b"", 0, list(match.tags), dict(match.meta)))
            for string in strings:
                for instance in list(string.instances)[:MAX_INSTANCES]:
                    result.hits.append(Hit(match.rule, path, instance.offset, string.identifier,
                                           bytes(instance.matched_data[:64]), instance.matched_length,
                                           list(match.tags), dict(match.meta)))
            if len(result.hits) >= MAX_HITS:
                result.truncated = True
                del result.hits[MAX_HITS:]
                if progress:
                    progress(len(files), len(files))
                return result
    if progress:
        progress(len(files), len(files))
    return result


def preview(data: bytes) -> str:
    """Treffer als Text, wenn druckbar, sonst als Hex."""
    if data and all(32 <= b < 127 or b in (9,) for b in data):
        return data.decode("ascii")
    return " ".join(f"{b:02X}" for b in data)

