"""Eingebettete Dateien finden und extrahieren („binwalk-light“). Ohne Qt.

- Die Datei wird blockweise gelesen und an JEDEM Offset nach Signaturen durchsucht (bytes.find, schnell).
- Jeder Kandidat muss eine Plausibilitätsprüfung seines Kopfes bestehen (Falsch-Positive vermeiden); sehr kurze,
  unspezifische Signaturen ohne prüfbaren Kopf (ICO, TIFF, Mach-O-Fat, WASM, MP3, OGG, FLAC) werden gar nicht gesucht.
- Größe, wo das Format es hergibt: PNG/GIF/TAR/PCAP/PCAPNG durchlaufen, JPEG bis EOI, ZIP über das Verzeichnisende,
  PE/ELF über Sektionstabellen, BMP/WAV/WEBP/7z/SQLite aus dem Kopf, gzip/bzip2/xz durch Dekomprimieren bis
  Stream-Ende. PDF bis zum letzten %%EOF.
- Daten hinter einem Dateiende (z. B. ZIP nach JPEG-EOI, Daten nach PNG-IEND, PE-Overlay) werden als eigener Fund
  gemeldet.
- Extrahieren schreibt Kopien in einen Unterordner neben der Datei, überschreibt nie und führt nichts aus.
"""
from __future__ import annotations

import bz2
import lzma
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable

from notex.core import filetype

CHUNK = 4 * 1024 * 1024
MAX_HITS = 10_000
SCAN_LIMIT = 256 * 1024 * 1024       # so weit wird für eine Größenbestimmung höchstens gelesen
MAX_WALK = 200_000                   # höchstens so viele Blöcke/Chunks je Fund durchlaufen


@dataclass
class Hit:
    offset: int
    key: str                 # Dateityp-Schlüssel ("png", "zip", … oder "trailer")
    name: str                # Anzeige
    size: int | None         # Bytes, None = unbekannt
    info: str = ""           # z. B. „640 × 400“, „3 Einträge“
    ext: str = ".bin"

    @property
    def end(self) -> int | None:
        return None if self.size is None else self.offset + self.size


class Cancelled(Exception):
    pass


# ---- Lesen ---------------------------------------------------------------------------------------------
def _count(number: int, one: str, many: str) -> str:
    return f"{number} {one if number == 1 else many}"


def _read(handle: BinaryIO, offset: int, length: int) -> bytes:
    handle.seek(offset)
    return handle.read(length)


def _u16(data: bytes, pos: int, big: bool = False) -> int:
    return struct.unpack_from(">H" if big else "<H", data, pos)[0]


def _u32(data: bytes, pos: int, big: bool = False) -> int:
    return struct.unpack_from(">I" if big else "<I", data, pos)[0]


def _u64(data: bytes, pos: int, big: bool = False) -> int:
    return struct.unpack_from(">Q" if big else "<Q", data, pos)[0]


# ---- Prüfer: (handle, offset, file_size) -> (size | None, info) oder None = kein plausibler Fund ------------
def _png(h, off, total):
    head = _read(h, off, 33)
    if len(head) < 33 or _u32(head, 8, True) != 13 or head[12:16] != b"IHDR":
        return None
    width, height = _u32(head, 16, True), _u32(head, 20, True)
    if not (0 < width < 1 << 20 and 0 < height < 1 << 20) or head[24] not in (1, 2, 4, 8, 16):
        return None
    pos = off + 8
    for _ in range(MAX_WALK):
        chunk = _read(h, pos, 8)
        if len(chunk) < 8:
            return None, f"{width} × {height}"
        length, kind = _u32(chunk, 0, True), chunk[4:8]
        if length > total or not kind.isalpha():
            return None, f"{width} × {height}"
        pos += 12 + length
        if kind == b"IEND":
            return pos - off, f"{width} × {height}"
    return None, f"{width} × {height}"


def _jpeg(h, off, total):
    head = _read(h, off, 4)
    if len(head) < 4 or head[3] not in set(range(0xE0, 0xF0)) | {0xDB, 0xC0, 0xC2, 0xC4, 0xFE, 0xEE}:
        return None
    pos = off + 2
    for _ in range(10_000):                           # Segmente bis zum Bildbeginn (SOS)
        marker = _read(h, pos, 4)
        if len(marker) < 4 or marker[0] != 0xFF:
            return None
        kind = marker[1]
        if kind == 0xD9:
            return pos + 2 - off, ""
        if kind in range(0xD0, 0xD8) or kind in (0x01, 0xFF):
            pos += 2 if kind != 0xFF else 1
            continue
        length = _u16(marker, 2, True)
        if length < 2:
            return None
        pos += 2 + length
        if kind == 0xDA:
            break
    else:
        return None
    end = pos
    limit = min(total, off + SCAN_LIMIT)
    while end < limit:                                 # komprimierte Daten bis EOI (FF D9)
        block = _read(h, end, CHUNK + 1)
        if not block:
            break
        index = block.find(b"\xff\xd9")
        if index >= 0:
            return end + index + 2 - off, ""
        if len(block) <= CHUNK:
            break                                      # Dateiende erreicht
        end += len(block) - 1
    return None, "Ende nicht gefunden"


def _gif(h, off, total):
    head = _read(h, off, 13)
    if len(head) < 13:
        return None
    width, height, flags = _u16(head, 6), _u16(head, 8), head[10]
    if not (0 < width < 65535 and 0 < height < 65535):
        return None
    info = f"{width} × {height}"
    pos = off + 13 + (3 * (2 << (flags & 7)) if flags & 0x80 else 0)

    def skip_blocks(position: int) -> int | None:
        for _ in range(MAX_WALK):
            size = _read(h, position, 1)
            if not size:
                return None
            position += 1
            if size[0] == 0:
                return position
            position += size[0]
        return None
    for _ in range(MAX_WALK):
        kind = _read(h, pos, 1)
        if not kind:
            return None, info
        if kind == b"\x3b":
            return pos + 1 - off, info
        if kind == b"\x21":
            pos = skip_blocks(pos + 2)
        elif kind == b"\x2c":
            desc = _read(h, pos, 10)
            if len(desc) < 10:
                return None, info
            pos += 10 + (3 * (2 << (desc[9] & 7)) if desc[9] & 0x80 else 0) + 1
            pos = skip_blocks(pos)
        else:
            return None, info
        if pos is None:
            return None, info
    return None, info


def _bmp(h, off, total):
    head = _read(h, off, 30)
    if len(head) < 30:
        return None
    size, reserved, dib, planes = _u32(head, 2), _u32(head, 6), _u32(head, 14), _u16(head, 26)
    if reserved != 0 or dib not in (12, 40, 52, 56, 108, 124) or planes != 1 or not 26 <= size <= total - off:
        return None
    return size, ""


def _riff(h, off, total, kind: bytes):
    head = _read(h, off, 12)
    if len(head) < 12 or head[8:12] != kind:
        return None
    size = _u32(head, 4) + 8
    return (size if size <= total - off else None), ""


def _pdf(h, off, total):
    head = _read(h, off, 8)
    if len(head) < 8 or not (head[5:6].isdigit() and head[6:7] == b"." and head[7:8].isdigit()):
        return None
    last, pos, limit = None, off, min(total, off + SCAN_LIMIT)
    while pos < limit:
        block = _read(h, pos, CHUNK + 5)
        if not block:
            break
        found = block.rfind(b"%%EOF")
        nested = block.find(b"%PDF-", 1 if pos == off else 0)
        if nested >= 0 and (found < 0 or nested < found):
            found = block.rfind(b"%%EOF", 0, nested)
            if found >= 0:
                last = pos + found
            break
        if found >= 0:
            last = pos + found
        if len(block) <= CHUNK:
            break                                      # Dateiende erreicht
        pos += len(block) - 5
    if last is None:
        return None, "Ende nicht gefunden"
    end = last + 5
    tail = _read(h, end, 2)
    end += 2 if tail == b"\r\n" else 1 if tail[:1] in (b"\n", b"\r") else 0
    return end - off, f"PDF {head[5:8].decode()}"


def _zip(h, off, total):
    head = _read(h, off, 30)
    if len(head) < 30:
        return None
    version, method, name_len = _u16(head, 4), _u16(head, 8), _u16(head, 26)
    if version > 63 or method not in (0, 1, 6, 8, 9, 12, 14, 93, 95, 98, 99) or not 0 < name_len <= 1024:
        return None
    pos, limit = off, min(total, off + SCAN_LIMIT)
    while pos < limit:                                  # Verzeichnisende suchen, das zu diesem Archiv passt
        block = _read(h, pos, CHUNK + 22)
        if len(block) < 22:
            break
        index = block.find(b"PK\x05\x06")
        while index >= 0:
            eocd = pos + index
            record = _read(h, eocd, 22)
            if len(record) == 22:
                entries, cd_size, cd_offset, comment = _u16(record, 10), _u32(record, 12), _u32(record, 16), _u16(record, 20)
                if cd_offset + cd_size == eocd - off or cd_offset + cd_size == eocd:
                    return eocd + 22 + comment - off, _count(entries, "Eintrag", "Einträge")
            index = block.find(b"PK\x05\x06", index + 1)
        if len(block) <= CHUNK:
            break                                      # Dateiende erreicht
        pos += len(block) - 22
    return None, "Verzeichnisende nicht gefunden"


MAX_OUTPUT = 1024 * 1024 * 1024      # Dekomprimieren zur Größenbestimmung: höchstens 1 GB Ausgabe (Bomben)
STEP = 1024 * 1024


def _feed(decompressor, data: bytes) -> int:
    """Daten einspeisen, Ausgabe in 1-MB-Schritten verwerfen (nie alles auf einmal im Speicher). Gibt Bytes zurück."""
    produced = 0
    if hasattr(decompressor, "unconsumed_tail"):         # zlib
        out = decompressor.decompress(data, STEP)
        produced += len(out)
        while decompressor.unconsumed_tail and not decompressor.eof and produced < MAX_OUTPUT:
            out = decompressor.decompress(decompressor.unconsumed_tail, STEP)
            produced += len(out)
        return produced
    out = decompressor.decompress(data, STEP)             # bz2 / lzma
    produced += len(out)
    while not decompressor.eof and not decompressor.needs_input and produced < MAX_OUTPUT:
        produced += len(decompressor.decompress(b"", STEP))
    return produced


def _stream(h, off, total, decompressor, info=""):
    """gzip/bzip2/xz: bis zum Ende des Streams dekomprimieren – die genaue Länge ergibt sich aus unused_data."""
    pos, limit, produced = off, min(total, off + SCAN_LIMIT), 0
    try:
        while pos < limit:
            block = _read(h, pos, min(STEP, limit - pos))
            if not block:
                break
            produced += _feed(decompressor, block)
            if decompressor.eof:
                return pos + len(block) - len(decompressor.unused_data) - off, info
            if produced >= MAX_OUTPUT:
                return None, "sehr groß – Ende nicht bestimmt"
            pos += len(block)
    except (OSError, EOFError, ValueError, zlib.error, lzma.LZMAError):
        return None
    return None, info or "Ende nicht gefunden"


def _gzip(h, off, total):
    head = _read(h, off, 10)
    if len(head) < 10 or head[2] != 8 or head[3] & 0xE0 or head[9] not in set(range(14)) | {255}:
        return None
    return _stream(h, off, total, zlib.decompressobj(16 + zlib.MAX_WBITS))


def _bzip2(h, off, total):
    head = _read(h, off, 10)
    if len(head) < 10 or not (0x31 <= head[3] <= 0x39) or head[4:10] != b"1AY&SY":
        return None
    return _stream(h, off, total, bz2.BZ2Decompressor())


def _xz(h, off, total):
    head = _read(h, off, 12)
    if len(head) < 12 or head[6] != 0 or head[7] > 0x0F:
        return None
    return _stream(h, off, total, lzma.LZMADecompressor(format=lzma.FORMAT_XZ))


def _7z(h, off, total):
    head = _read(h, off, 32)
    if len(head) < 32 or head[6] != 0:
        return None
    size = 32 + _u64(head, 12) + _u64(head, 20)
    return (size if size <= total - off else None), f"Version 0.{head[7]}"


def _rar(h, off, total):
    head = _read(h, off, 8)
    if head[6:7] == b"\x00":
        return None, "RAR 4"
    if head[6:8] == b"\x01\x00":
        return None, "RAR 5"
    return None


def _elf(h, off, total):
    head = _read(h, off, 64)
    if len(head) < 52 or head[4] not in (1, 2) or head[5] not in (1, 2) or head[6] != 1:
        return None
    big, is64 = head[5] == 2, head[4] == 2
    if is64 and len(head) < 64:
        return None
    if is64:
        shoff, shentsize, shnum = _u64(head, 40, big), _u16(head, 58, big), _u16(head, 60, big)
    else:
        shoff, shentsize, shnum = _u32(head, 32, big), _u16(head, 46, big), _u16(head, 48, big)
    machine = _u16(head, 18, big)
    size = shoff + shentsize * shnum if shoff and shnum else None
    if size is not None and (size > total - off or shentsize not in (40, 64)):
        return None
    return size, f"{'64' if is64 else '32'} Bit, Maschine 0x{machine:X}"


def _pe(h, off, total):
    head = _read(h, off, 64)
    if len(head) < 64:
        return None
    lfanew = _u32(head, 0x3C)
    if not 0x40 <= lfanew < 0x1000:
        return None
    coff = _read(h, off + lfanew, 24)
    if len(coff) < 24 or coff[:4] != b"PE\x00\x00":
        return None
    sections, opt_size = _u16(coff, 6), _u16(coff, 20)
    if not 0 < sections < 100:
        return None
    table = _read(h, off + lfanew + 24 + opt_size, 40 * sections)
    end = 0
    for i in range(min(sections, len(table) // 40)):
        raw_size, raw_ptr = _u32(table, i * 40 + 16), _u32(table, i * 40 + 20)
        end = max(end, raw_ptr + raw_size)
    machine = {0x14C: "x86", 0x8664: "x64", 0xAA64: "ARM64", 0x1C0: "ARM"}.get(_u16(coff, 4), hex(_u16(coff, 4)))
    kind = "DLL" if _u16(coff, 22) & 0x2000 else "EXE"
    if not end or end > total - off:
        return None, f"{kind} {machine}"
    return end, f"{kind} {machine}"


def _sqlite(h, off, total):
    head = _read(h, off, 32)
    if len(head) < 32:
        return None
    page = _u16(head, 16, True)
    page = 65536 if page == 1 else page
    if page < 512 or page & (page - 1):
        return None
    count = _u32(head, 28, True)
    size = page * count if count else None
    return (size if size and size <= total - off else None), f"Seiten zu {page} Bytes"


def _pcap(h, off, total):
    head = _read(h, off, 24)
    if len(head) < 24:
        return None
    big = head[:4] in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d")
    if _u16(head, 4, big) != 2 or _u16(head, 6, big) != 4:
        return None
    snaplen = _u32(head, 16, big) or 262144
    pos = off + 24
    for count in range(MAX_WALK):
        record = _read(h, pos, 16)
        if len(record) < 16:
            return pos - off, _count(count, "Paket", "Pakete")
        incl, orig = _u32(record, 8, big), _u32(record, 12, big)
        if incl > max(snaplen, 262144) or incl > orig + 65536 or pos + 16 + incl > total:
            return pos - off, _count(count, "Paket", "Pakete")
        pos += 16 + incl
    return None, "sehr viele Pakete"


def _pcapng(h, off, total):
    head = _read(h, off, 12)
    if len(head) < 12 or head[8:12] not in (b"\x4d\x3c\x2b\x1a", b"\x1a\x2b\x3c\x4d"):
        return None
    big = head[8:12] == b"\x1a\x2b\x3c\x4d"
    pos = off
    for count in range(MAX_WALK):
        block = _read(h, pos, 8)
        if len(block) < 8:
            return pos - off, _count(count, "Block", "Blöcke")
        length = _u32(block, 4, big)
        if length < 12 or length % 4 or pos + length > total:
            return (pos - off, _count(count, "Block", "Blöcke")) if count else None
        if count and _u32(block, 0, big) == 0x0A0D0D0A:      # nächste Sektion gehört dazu
            pass
        pos += length
    return None, "sehr viele Blöcke"


def _tar(h, off, total):
    """off zeigt auf den Kopfblock (ustar steht bei +257); Prüfsumme muss stimmen."""
    pos = off
    for count in range(MAX_WALK):
        header = _read(h, pos, 512)
        if len(header) < 512:
            return (pos - off, _count(count, "Eintrag", "Einträge")) if count else None
        if header == b"\x00" * 512:
            return pos + 1024 - off if pos + 1024 <= total else pos - off, _count(count, "Eintrag", "Einträge")
        try:
            stored = int(header[148:156].split(b"\x00")[0].strip() or b"0", 8)
            size = int(header[124:136].split(b"\x00")[0].strip() or b"0", 8)
        except ValueError:
            return None if not count else (pos - off, _count(count, "Eintrag", "Einträge"))
        if sum(header[:148]) + 256 + sum(header[156:]) != stored:
            return None if not count else (pos - off, _count(count, "Eintrag", "Einträge"))
        pos += 512 + (size + 511) // 512 * 512
    return None, "sehr viele Einträge"


def _simple(h, off, total):
    return None, ""


# (Signatur, Offset der Signatur im Dateikopf, Typ, Prüfer)
_ZIP_EXT = {"docx": ".docx", "xlsx": ".xlsx", "pptx": ".pptx", "odf": ".odt", "epub": ".epub", "jar": ".jar", "apk": ".apk"}
SCANNERS: list[tuple[bytes, int, filetype.FileType, Callable]] = [
    (b"\x89PNG\r\n\x1a\n", 0, filetype.PNG, _png),
    (b"\xff\xd8\xff", 0, filetype.JPEG, _jpeg),
    (b"GIF87a", 0, filetype.GIF, _gif),
    (b"GIF89a", 0, filetype.GIF, _gif),
    (b"BM", 0, filetype.BMP, _bmp),
    (b"RIFF", 0, filetype.WEBP, lambda h, o, t: _riff(h, o, t, b"WEBP")),
    (b"RIFF", 0, filetype.WAV, lambda h, o, t: _riff(h, o, t, b"WAVE")),
    (b"%PDF-", 0, filetype.PDF, _pdf),
    (b"PK\x03\x04", 0, filetype.ZIP, _zip),
    (b"\x1f\x8b\x08", 0, filetype.GZIP, _gzip),
    (b"BZh", 0, filetype.BZIP2, _bzip2),
    (b"\xfd7zXZ\x00", 0, filetype.XZ, _xz),
    (b"7z\xbc\xaf\x27\x1c", 0, filetype.SEVENZ, _7z),
    (b"Rar!\x1a\x07", 0, filetype.RAR, _rar),
    (b"\x7fELF", 0, filetype.ELF, _elf),
    (b"MZ", 0, filetype.PE, _pe),
    (b"SQLite format 3\x00", 0, filetype.SQLITE, _sqlite),
    (b"\xd4\xc3\xb2\xa1", 0, filetype.PCAP, _pcap), (b"\xa1\xb2\xc3\xd4", 0, filetype.PCAP, _pcap),
    (b"\x4d\x3c\xb2\xa1", 0, filetype.PCAP, _pcap), (b"\xa1\xb2\x3c\x4d", 0, filetype.PCAP, _pcap),
    (b"\x0a\x0d\x0d\x0a", 0, filetype.PCAPNG, _pcapng),
    (b"ElfFile\x00", 0, filetype.EVTX, _simple),
    (b"ustar", 257, filetype.TAR, _tar),
    (b"NOTEXENC", 0, filetype.NTX, _simple),
]
_EXTENSIONS = {"jpeg": ".jpg", "pe": ".exe", "gzip": ".gz", "bzip2": ".bz2", "sevenz": ".7z", "7z": ".7z",
               "elf": ".elf", "sqlite": ".sqlite", "evtx": ".evtx", "ntx": ".ntx", "tar": ".tar"}


def _extension(ftype: filetype.FileType, info: str) -> str:
    if ftype.key == "pe" and info.startswith("DLL"):
        return ".dll"
    return _EXTENSIONS.get(ftype.key) or (ftype.extensions[0] if ftype.extensions and ftype.extensions[0] else ".bin")


def scan(path: Path | str, *, progress: Callable[[int, int], None] | None = None,
         cancelled: Callable[[], bool] | None = None, chunk_size: int = CHUNK,
         max_hits: int = MAX_HITS) -> tuple[list[Hit], bool]:
    """Alle plausiblen Funde nach Offset (inkl. „Daten hinter dem Ende“). Gibt (Funde, abgeschnitten?) zurück."""
    path = Path(path)
    total = path.stat().st_size
    overlap = max(len(sig) + at for sig, at, _t, _c in SCANNERS)
    candidates: set[tuple[int, int]] = set()          # (Offset des Dateianfangs, Index in SCANNERS)
    with open(path, "rb") as handle:
        pos = 0
        while pos < total:
            if cancelled is not None and cancelled():
                raise Cancelled()
            block = _read(handle, pos, chunk_size + overlap)
            for index, (signature, at, _t, _c) in enumerate(SCANNERS):
                found = block.find(signature)
                while 0 <= found < chunk_size or (0 <= found and pos + chunk_size >= total):
                    start = pos + found - at
                    if start >= 0:
                        candidates.add((start, index))
                    found = block.find(signature, found + 1)
            pos += chunk_size
            if progress is not None:
                progress(min(pos, total) // 2, total)
        hits: list[Hit] = []
        truncated = False
        ordered = sorted(candidates)
        for number, (start, index) in enumerate(ordered):
            if cancelled is not None and cancelled():
                raise Cancelled()
            _sig, _at, ftype, check = SCANNERS[index]
            result = check(handle, start, total)
            if result is None:
                continue
            size, info = result
            key, name = ftype.key, ftype.name
            if ftype is filetype.ZIP:                   # docx/xlsx/jar/apk … als ZIP-basiert erkennen
                refined = filetype.detect(_read(handle, start, filetype.HEAD_BYTES), "")
                key, name = refined.key, refined.name
                ext = _ZIP_EXT.get(key, ".zip")
            else:
                ext = _extension(ftype, info)
            hits.append(Hit(start, key, name, size, info, ext))
            if len(hits) >= max_hits:
                truncated = True
                break
            if progress is not None and number % 64 == 0:
                progress(total // 2 + total * number // max(2, 2 * len(ordered)), total)
        hits.extend(_trailers(handle, hits, total))
    hits.sort(key=lambda hit: (hit.offset, hit.key == "trailer"))
    if progress is not None:
        progress(total, total)
    return hits, truncated


def _trailers(handle, hits: list[Hit], total: int) -> list[Hit]:
    """Daten hinter dem Ende einer erkannten Datei, die nicht zu einem anderen Fund gehören und kein Füllmuster sind."""
    extra = []
    starts = sorted(hit.offset for hit in hits)
    for hit in hits:
        end = hit.end
        if end is None or end >= total:
            continue
        enclosing = [h for h in hits if h is not hit and h.offset < hit.offset and h.end is not None and h.end >= total]
        if hit.offset > 0 and enclosing:
            continue                                   # eingebettet in eine größere Datei – deren Ende zählt
        next_start = next((s for s in starts if s >= end), total)
        if next_start == end:
            continue                                   # direkt dahinter beginnt ein anderer Fund
        gap = next_start - end
        sample = _read(handle, end, min(gap, 4096))
        if not sample.strip(b"\x00") or not sample.strip(b"\xff"):
            continue                                   # nur Nullen/FF: Füllbytes, kein Anhang
        extra.append(Hit(end, "trailer", f"Daten hinter dem Ende von {hit.name}", gap,
                         f"nach 0x{hit.offset:X}", ".bin"))
    return extra


def region_size(hit: Hit, hits: list[Hit], total: int) -> int:
    """Wie viel beim Extrahieren kopiert wird: bekannte Größe, sonst bis zum nächsten Fund bzw. Dateiende."""
    if hit.size is not None:
        return hit.size
    later = [h.offset for h in hits if h.offset > hit.offset and h.key != "trailer"]
    return (min(later) if later else total) - hit.offset


def unique_target(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix = target.stem, target.suffix
    number = 2
    while target.exists():
        target = folder / f"{stem}-{number}{suffix}"
        number += 1
    return target


def extract(path: Path | str, hit: Hit, hits: list[Hit], folder: Path | None = None) -> Path:
    """Fund als Kopie in <Datei>_extrahiert/<Offset>.<Endung> schreiben – nie überschreiben, nie ausführen."""
    path = Path(path)
    folder = folder or path.with_name(f"{path.name}_extrahiert")
    folder.mkdir(parents=True, exist_ok=True)
    total = path.stat().st_size
    length = region_size(hit, hits, total)
    target = unique_target(folder, f"{hit.offset:08X}{hit.ext}")
    with open(path, "rb") as source, open(target, "xb") as out:     # "x": bricht ab, statt zu überschreiben
        source.seek(hit.offset)
        remaining = length
        while remaining > 0:
            block = source.read(min(CHUNK, remaining))
            if not block:
                break
            out.write(block)
            remaining -= len(block)
    return target
