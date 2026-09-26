"""Strings: druckbare Zeichenketten aus Binärdateien (wie `strings`), gestreamt, mit Offset. Ohne Qt.

- ASCII: druckbare Zeichen 0x20–0x7E und Tab; UTF-16LE/-BE: dieselben Zeichen mit Nullbyte davor/danach.
- Die Datei wird blockweise gelesen; eine Zeichenkette, die über eine Blockgrenze reicht, wird zusammengesetzt
  (Rest wird mitgenommen). Auch UTF-16 an ungerader Position wird gefunden.
- classify() markiert interessante Treffer: URLs, E-Mails, IPv4, Pfade, Registry-Schlüssel, Base64-verdächtig.
- Nur lesend; bei .ntx sieht man nur Geheimtext (es gibt keinen Klartext auf der Platte).
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

CHUNK = 4 * 1024 * 1024
MAX_STRING = 64 * 1024        # längere Läufe werden als Stück ausgegeben (sonst wüchse der Übertrag grenzenlos)
DEFAULT_LIMIT = 200_000
ENCODINGS = ("ascii", "utf16le", "utf16be")
LABELS = {"ascii": "ASCII", "utf16le": "UTF-16LE", "utf16be": "UTF-16BE"}


@dataclass(frozen=True)
class FoundString:
    offset: int
    encoding: str
    text: str
    length: int          # Länge in Bytes (für die Auswahl in der Hex-Ansicht)


class Cancelled(Exception):
    pass


def _pattern(encoding: str, min_len: int) -> re.Pattern:
    char = rb"[\x20-\x7E\t]"
    if encoding == "ascii":
        return re.compile(char + rb"{%d,}" % min_len)
    if encoding == "utf16le":
        return re.compile(rb"(?:" + char + rb"\x00){%d,}" % min_len)
    return re.compile(rb"(?:\x00" + char + rb"){%d,}" % min_len)


def _decode(raw: bytes, encoding: str) -> str:
    if encoding == "ascii":
        return raw.decode("ascii")
    return raw.decode("utf-16-le" if encoding == "utf16le" else "utf-16-be")


def _scan(chunks: Iterator[tuple[bytes, bool]], pattern: re.Pattern, encoding: str,
          keep: int) -> Iterator[FoundString]:
    """`keep`: so viele Bytes am Blockende mitnehmen, dass ein angefangener (noch zu kurzer) String weiterwachsen
    kann – aber nie Bytes eines schon ausgegebenen Treffers (sonst doppelt)."""
    buffer, base = b"", 0
    slack = 0 if encoding == "ascii" else 1     # UTF-16: ein halbes Zeichenpaar am Ende kann noch dazugehören
    for data, last in chunks:
        buffer += data
        cut, emitted_end = len(buffer), 0
        for match in pattern.finditer(buffer):
            if match.end() >= len(buffer) - slack and not last and len(buffer) - match.start() <= MAX_STRING:
                cut = match.start()            # kann im nächsten Block weitergehen → mitnehmen
                break
            raw = match.group()
            emitted_end = match.end()
            yield FoundString(base + match.start(), encoding, _decode(raw, encoding), len(raw))
        else:
            if not last:
                cut = max(emitted_end, len(buffer) - keep)
        base += cut
        buffer = buffer[cut:]


def _chunks(path: Path, chunk_size: int, progress, cancelled) -> Iterator[tuple[bytes, bool]]:
    size = path.stat().st_size
    done = 0
    with open(path, "rb") as handle:
        while True:
            if cancelled is not None and cancelled():
                raise Cancelled()
            data = handle.read(chunk_size)
            done += len(data)
            if progress is not None:
                progress(done, size)
            last = done >= size or not data
            yield data, last
            if last:
                return


def extract_bytes(data: bytes, min_len: int = 4, encodings=("ascii", "utf16le")) -> list[FoundString]:
    """Für kleine Daten und Tests: alles auf einmal."""
    found: list[FoundString] = []
    for encoding in encodings:
        found.extend(_scan(iter([(data, True)]), _pattern(encoding, min_len), encoding, 0))
    return sorted(found, key=lambda f: (f.offset, f.encoding))


def extract_file(path: Path | str, min_len: int = 4, encodings=("ascii", "utf16le"), *, limit: int = DEFAULT_LIMIT,
                 chunk_size: int = CHUNK, progress: Callable[[int, int], None] | None = None,
                 cancelled: Callable[[], bool] | None = None) -> tuple[list[FoundString], bool]:
    """Gestreamt über die Datei, je Encoding ein Durchgang. Gibt (Treffer nach Offset, abgeschnitten?) zurück."""
    path = Path(path)
    found: list[FoundString] = []
    truncated = False
    count = max(1, len(encodings))
    for number, encoding in enumerate(encodings):
        step = (lambda done, total, n=number: progress(n * total + done, count * total)) if progress else None
        keep = 2 * max(1, min_len) + 2
        for item in _scan(_chunks(path, chunk_size, step, cancelled), _pattern(encoding, max(1, min_len)), encoding, keep):
            found.append(item)
            if len(found) >= limit:
                truncated = True
                break
        if truncated:
            break
    found.sort(key=lambda f: (f.offset, f.encoding))
    return found, truncated


# ---- Interessante Treffer ------------------------------------------------------------------------------
CATEGORIES = {"url": "URL", "email": "E-Mail", "ip": "IP-Adresse", "path": "Pfad", "registry": "Registry",
              "base64": "Base64?"}
_URL = re.compile(r"\b(?:https?|ftp|wss?|file)://[^\s\"'<>]{3,}", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
_WINPATH = re.compile(r"(?:\b[A-Za-z]:\\|\\\\[\w.$-]+\\)[^\s\"<>|]*")
_UNIXPATH = re.compile(r"(?<![\w/])/(?:[\w.-]+/)+[\w.-]*")
_REGISTRY = re.compile(r"\b(?:HKEY_[A-Z_]+|HKLM|HKCU|HKCR|HKU|HKCC)\\|\bSoftware\\(?:Microsoft|Classes|Policies)\\",
                       re.I)
_BASE64 = re.compile(r"^[A-Za-z0-9+/]{20,}={0,2}$")


def classify(text: str) -> str | None:
    """Kategorie eines Strings oder None. Reihenfolge: das Spezifischste zuerst."""
    if _URL.search(text):
        return "url"
    if _EMAIL.search(text):
        return "email"
    for match in _IPV4.finditer(text):
        try:
            ipaddress.IPv4Address(match.group(1))
            return "ip"
        except ValueError:
            continue
    if _REGISTRY.search(text):
        return "registry"
    if _WINPATH.search(text) or _UNIXPATH.search(text):
        return "path"
    stripped = text.strip()
    if _BASE64.match(stripped) and len(stripped) % 4 == 0 and _mixed(stripped):
        return "base64"
    return None


def _mixed(text: str) -> bool:
    """Base64 aus echten Daten mischt Groß-, Kleinbuchstaben und Ziffern – „AAAAAAAAAAAAAAAAAAAA“ zählt nicht."""
    return sum((any(c.isupper() for c in text), any(c.islower() for c in text), any(c.isdigit() for c in text))) >= 2 \
        and len(set(text)) >= 10


def to_text_export(items: list[FoundString]) -> str:
    """Export als .txt: Offset (hex), Encoding, Text – eine Zeile je Treffer."""
    return "".join(f"0x{item.offset:08X}\t{LABELS[item.encoding]}\t{item.text}\n" for item in items)
