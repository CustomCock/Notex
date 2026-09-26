"""Hex-Ansicht ohne Qt: seitenweises Lesen, Zeilen formatieren, Offsets und Suchmuster parsen, suchen.

PagedFile liest in 64-KB-Seiten mit kleinem LRU-Cache und öffnet die Datei nur für den jeweiligen Lesevorgang.
Das ist bewusst kein mmap: unter Windows ließe sich eine gemappte Datei nicht umbenennen, verschieben oder in den
Papierkorb legen, solange der Tab offen ist. Mehrere GB sind kein Problem – gelesen wird nur, was sichtbar ist.
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Callable

BYTES_PER_ROW = 16
PAGE_SIZE = 64 * 1024
CACHE_PAGES = 32                 # 2 MB Cache
SEARCH_CHUNK = 4 * 1024 * 1024


class PagedFile:
    def __init__(self, path: Path | str, page_size: int = PAGE_SIZE, cache_pages: int = CACHE_PAGES) -> None:
        self.path = Path(path)
        self.page_size = page_size
        self.cache_pages = cache_pages
        self._pages: OrderedDict[int, bytes] = OrderedDict()
        self.size = self.path.stat().st_size

    def refresh(self) -> None:
        """Datei hat sich geändert (Größe/Inhalt) – Cache verwerfen."""
        self._pages.clear()
        self.size = self.path.stat().st_size

    def _page(self, number: int) -> bytes:
        page = self._pages.get(number)
        if page is not None:
            self._pages.move_to_end(number)
            return page
        with open(self.path, "rb") as handle:
            handle.seek(number * self.page_size)
            page = handle.read(self.page_size)
        self._pages[number] = page
        while len(self._pages) > self.cache_pages:
            self._pages.popitem(last=False)
        return page

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length <= 0 or offset >= self.size:
            return b""
        length = min(length, self.size - offset)
        out = bytearray()
        position = offset
        while len(out) < length:
            number, inner = divmod(position, self.page_size)
            page = self._page(number)
            if inner >= len(page):
                break                      # Datei wurde währenddessen kürzer
            piece = page[inner:inner + length - len(out)]
            out += piece
            position += len(piece)
        return bytes(out)


# ---- Formatieren -------------------------------------------------------------------------------
def offset_digits(size: int) -> int:
    """8 Hex-Stellen bis 4 GB, darüber so viele wie nötig (gerade Anzahl)."""
    digits = max(8, len(f"{max(0, size - 1):X}"))
    return digits + digits % 2


def offset_label(offset: int, digits: int = 8) -> str:
    return f"{offset:0{digits}X}"


def hex_cells(data: bytes) -> list[str]:
    return [f"{b:02X}" for b in data]


def ascii_char(byte: int) -> str:
    return chr(byte) if 0x20 <= byte < 0x7F else "."


def ascii_line(data: bytes) -> str:
    return "".join(ascii_char(b) for b in data)


def row_text(offset: int, data: bytes, digits: int = 8) -> str:
    """Eine Zeile als Text (für Kopieren/Tests): Offset | 16 Bytes hex (Lücke nach 8) | ASCII."""
    cells = hex_cells(data) + ["  "] * (BYTES_PER_ROW - len(data))
    hex_part = " ".join(cells[:8]) + "  " + " ".join(cells[8:])
    return f"{offset_label(offset, digits)}  {hex_part}  {ascii_line(data)}"


# ---- Eingaben ----------------------------------------------------------------------------------
_HEX_DIGITS = re.compile(r"^[0-9a-fA-F]+$")


def parse_offset(text: str) -> int:
    """„1234“ dezimal, „0x4D2“ / „4D2h“ / „$4D2“ hex, reine Hex-Buchstaben („ff“) ebenfalls hex.
    ValueError bei allem anderen oder negativen Werten."""
    value = text.strip().replace("_", "").replace(" ", "").replace(".", "")
    if not value:
        raise ValueError("Kein Offset angegeben")
    lowered = value.lower()
    if lowered.startswith("0x"):
        digits = value[2:]
    elif lowered.endswith("h"):
        digits = value[:-1]
    elif value.startswith(("$", "#")):
        digits = value[1:]
    elif value.isdigit():
        return int(value)
    else:
        digits = value
    if not _HEX_DIGITS.match(digits or "-"):
        raise ValueError(f"„{text.strip()}“ ist kein Offset (dezimal oder hex wie 0x1F)")
    return int(digits, 16)


def parse_hex_pattern(text: str) -> bytes:
    """„DE AD be ef“, „0xDE,0xAD“, „deadbeef“ → bytes. ValueError bei ungerader Länge/ungültigen Zeichen."""
    cleaned = re.sub(r"0x", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"[\s,;:\-]", "", cleaned)
    if not cleaned:
        raise ValueError("Leeres Suchmuster")
    if not _HEX_DIGITS.match(cleaned):
        raise ValueError("Nur Hex-Ziffern 0–9 und A–F erlaubt")
    if len(cleaned) % 2:
        raise ValueError("Ungerade Anzahl Hex-Ziffern – jedes Byte braucht zwei")
    return bytes.fromhex(cleaned)


def to_hex_string(data: bytes) -> str:
    return " ".join(hex_cells(data))


def to_base64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")


def to_c_array(data: bytes, name: str = "data", per_line: int = 12) -> str:
    """unsigned char data[] = { 0x4D, 0x5A, … }; mit Länge – zum Einfügen in C/C++-Code."""
    lines = []
    for start in range(0, len(data), per_line):
        lines.append("    " + ", ".join(f"0x{b:02X}" for b in data[start:start + per_line]))
    body = ",\n".join(lines)
    return f"unsigned char {name}[{len(data)}] = {{\n{body}\n}};\n"


def interpret(data: bytes) -> list[tuple[str, int | None, int | None]]:
    """Werte ab Cursor: (Typ, Little Endian, Big Endian) für u8/u16/u32/u64 – None, wenn die Bytes nicht reichen."""
    rows = []
    for name, size in (("u8", 1), ("u16", 2), ("u32", 4), ("u64", 8)):
        chunk = data[:size]
        if len(chunk) < size:
            rows.append((name, None, None))
        else:
            rows.append((name, int.from_bytes(chunk, "little"), int.from_bytes(chunk, "big")))
    return rows


def selection_value(data: bytes) -> str:
    """Kurzform für die Statusleiste bei Auswahl von 1/2/4/8 Bytes: „u32 LE 1.234 · BE 3.523.215.360“."""
    names = {1: "u8", 2: "u16", 4: "u32", 8: "u64"}
    if len(data) not in names:
        return ""
    le, be = int.from_bytes(data, "little"), int.from_bytes(data, "big")
    fmt = lambda v: f"{v:,}".replace(",", ".")
    return f"{names[len(data)]} {fmt(le)}" if len(data) == 1 else f"{names[len(data)]} LE {fmt(le)} · BE {fmt(be)}"


# ---- Suchen ------------------------------------------------------------------------------------
def search_file(path: Path | str, pattern: bytes, start: int = 0, *, ignore_case: bool = False, wrap: bool = True,
                progress: Callable[[int, int], None] | None = None,
                cancelled: Callable[[], bool] | None = None, chunk_size: int = SEARCH_CHUNK) -> int | None:
    """Erstes Vorkommen ab `start` (mit Umlauf an den Anfang). Liest blockweise mit Überlappung, damit auch Treffer
    über Blockgrenzen gefunden werden. `ignore_case` gilt für ASCII-Buchstaben. None = nicht gefunden/abgebrochen."""
    if not pattern:
        return None
    needle = pattern.lower() if ignore_case else pattern
    size = os.path.getsize(path)
    overlap = len(pattern) - 1
    ranges = [(start, size)] + ([(0, min(size, start + overlap))] if wrap and start > 0 else [])
    total = size
    done = 0
    with open(path, "rb") as handle:
        for begin, end in ranges:
            position = begin
            while position < end:
                if cancelled is not None and cancelled():
                    return None
                handle.seek(position)
                block = handle.read(min(chunk_size + overlap, end - position + overlap))
                if not block:
                    break
                haystack = block.lower() if ignore_case else block
                found = haystack.find(needle)
                if found >= 0 and position + found + len(pattern) <= size:
                    return position + found
                position += chunk_size
                done += min(chunk_size, end - begin)
                if progress is not None:
                    progress(min(done, total), total)
    return None
