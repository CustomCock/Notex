"""Metadaten lesen und entfernen – Bilder (EXIF inkl. GPS, XMP, IPTC, PNG-Text), PDF, Office (docx/xlsx/pptx). Ohne Qt.

Bibliotheken (Entscheidung, siehe PROGRESS.md):
- Bilder: eigener Parser (TIFF/EXIF, JPEG-Segmente, PNG-Chunks, WebP-RIFF) aus der Standardbibliothek. Pillow
  bräuchte ~10 MB und würde beim Entfernen JPEGs neu kodieren – hier werden nur Segmente/Chunks weggelassen, die
  Bilddaten bleiben Byte für Byte gleich (verlustfrei).
- PDF: pypdf (BSD-3, reines Python) – Info-Dictionary, XMP, verschlüsselte PDFs; Entfernen schreibt die Datei neu
  (dabei verschwinden auch ältere, inkrementell angehängte Fassungen).
- Office: zipfile + xml.etree (docProps/core.xml, app.xml, custom.xml).

Entfernen erzeugt immer eine KOPIE (<name>_ohne_Metadaten.<endung>, nie überschrieben), das Original bleibt; danach
wird die Kopie erneut gelesen und geprüft (verify).
"""
from __future__ import annotations

import mmap
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_XML = 8 * 1024 * 1024          # größter gelesener XML-Teil (Schutz vor Zip-Bomben)
MAX_TEXT = 2000                    # längere Werte werden gekürzt angezeigt


class MetadataError(Exception):
    pass


@dataclass
class Field:
    group: str
    name: str
    value: str
    removable: bool = True         # verschwindet beim Entfernen (sonst: Formatangabe, Inhalt o. Ä.)


@dataclass
class Report:
    kind: str                                  # jpeg | png | webp | tiff | pdf | office | unbekannt
    fields: list[Field] = field(default_factory=list)
    gps: tuple[float, float] | None = None
    removes: list[str] = field(default_factory=list)     # was „Metadaten entfernen“ wegnimmt (für die Rückfrage)
    keeps: list[str] = field(default_factory=list)       # was bewusst bleibt
    can_strip: bool = False

    def add(self, group: str, name: str, value, removable: bool = True) -> None:
        text = _text(value)
        if text != "":
            self.fields.append(Field(group, name, text, removable))

    @property
    def removable_fields(self) -> list[Field]:
        return [f for f in self.fields if f.removable]


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    text = str(value).replace("\x00", "").strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " …"


# ---- EXIF / TIFF --------------------------------------------------------------------------------------------------
TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4}

IFD0_TAGS = {
    0x010E: ("Beschreibung", "Bild"), 0x010F: ("Hersteller", "Kamera"), 0x0110: ("Modell", "Kamera"),
    0x0112: ("Ausrichtung", "Bild"), 0x0131: ("Software", "Software"), 0x0132: ("Geändert", "Zeit"),
    0x013B: ("Urheber", "Person"), 0x8298: ("Copyright", "Person"), 0x9C9B: ("Titel (Windows)", "Bild"),
    0x9C9C: ("Kommentar (Windows)", "Bild"), 0x9C9D: ("Autor (Windows)", "Person"),
    0x9C9E: ("Stichwörter (Windows)", "Bild"), 0x9C9F: ("Betreff (Windows)", "Bild"),
    0x0100: ("Breite", "Bild"), 0x0101: ("Höhe", "Bild"), 0x013C: ("Host-Computer", "Software"),
}
EXIF_TAGS = {
    0x9003: ("Aufgenommen", "Zeit"), 0x9004: ("Digitalisiert", "Zeit"), 0x9010: ("Zeitzone (Geändert)", "Zeit"),
    0x9011: ("Zeitzone (Aufnahme)", "Zeit"), 0x9290: ("Sekundenbruchteile", "Zeit"),
    0x829A: ("Belichtungszeit", "Aufnahme"), 0x829D: ("Blende", "Aufnahme"), 0x8827: ("ISO", "Aufnahme"),
    0x920A: ("Brennweite", "Aufnahme"), 0xA405: ("Brennweite (KB)", "Aufnahme"), 0x9209: ("Blitz", "Aufnahme"),
    0xA002: ("Pixel-Breite", "Bild"), 0xA003: ("Pixel-Höhe", "Bild"), 0x9286: ("Benutzerkommentar", "Bild"),
    0xA420: ("Bild-ID", "Kamera"), 0xA430: ("Besitzer", "Person"), 0xA431: ("Seriennummer Gehäuse", "Kamera"),
    0xA433: ("Objektiv-Hersteller", "Kamera"), 0xA434: ("Objektiv", "Kamera"), 0xA435: ("Seriennummer Objektiv", "Kamera"),
    0x927C: ("MakerNote", "Kamera"),
}
GPS_TAGS = {
    0x0005: "Höhe Bezug", 0x0006: "Höhe", 0x0007: "Zeit (UTC)", 0x0012: "Kartendatum", 0x0010: "Richtung Bezug",
    0x0011: "Richtung", 0x001B: "Verfahren", 0x001D: "Datum (UTC)",
}
ORIENTATION = {1: "normal", 2: "gespiegelt", 3: "180°", 4: "vertikal gespiegelt", 5: "gespiegelt + 90° links",
               6: "90° rechts", 7: "gespiegelt + 90° rechts", 8: "90° links"}


def parse_tiff(data) -> dict[str, dict[int, object]]:
    """TIFF-Struktur (EXIF-Block) → {"IFD0": {...}, "Exif": {...}, "GPS": {...}, "IFD1": {...}}. Robust gegen Müll."""
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise MetadataError("kein TIFF/EXIF-Kopf")
    endian = "<" if data[:2] == b"II" else ">"
    if struct.unpack(endian + "H", data[2:4])[0] != 42:
        raise MetadataError("kein TIFF/EXIF-Kopf")
    result: dict[str, dict[int, object]] = {}
    seen: set[int] = set()

    def value(kind: int, count: int, raw):
        if kind == 2:
            return bytes(raw).split(b"\x00")[0].decode("utf-8", "replace")
        if kind in (1, 7):
            return bytes(raw)
        if kind == 6:
            return list(struct.unpack(f"{count}b", raw))
        fmt = {3: "H", 4: "I", 8: "h", 9: "i", 11: "f", 12: "d", 13: "I"}.get(kind)
        if fmt:
            items = list(struct.unpack(endian + fmt * count, raw))
        else:                                              # 5/10: Brüche
            fmt = "I" if kind == 5 else "i"
            nums = struct.unpack(endian + fmt * (2 * count), raw)
            items = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
        return items[0] if count == 1 else items

    def read_ifd(name: str, offset: int) -> int:
        if offset in seen or not 8 <= offset < len(data) - 2 or len(result) > 8:
            return 0
        seen.add(offset)
        count = struct.unpack(endian + "H", data[offset:offset + 2])[0]
        entries: dict[int, object] = {}
        for index in range(min(count, 1000)):
            pos = offset + 2 + 12 * index
            if pos + 12 > len(data):
                break
            tag, kind, n = struct.unpack(endian + "HHI", data[pos:pos + 8])
            size = TYPE_SIZES.get(kind)
            if size is None or n == 0 or n > 10_000_000:
                continue
            total = size * n
            if total <= 4:
                raw = data[pos + 8:pos + 8 + total]
            else:
                start = struct.unpack(endian + "I", data[pos + 8:pos + 12])[0]
                if start + total > len(data):
                    continue
                raw = data[start:start + min(total, 1 << 20)] if kind in (1, 7) else data[start:start + total]
                if kind in (1, 7) and total > 1 << 20:
                    entries[tag] = ("groß", total)
                    continue
            try:
                entries[tag] = value(kind, n if kind not in (1, 7, 2) else len(raw), raw)
            except struct.error:
                continue
        result[name] = entries
        next_pos = offset + 2 + 12 * count
        return struct.unpack(endian + "I", data[next_pos:next_pos + 4])[0] if next_pos + 4 <= len(data) else 0

    first = struct.unpack(endian + "I", data[4:8])[0]
    next_ifd = read_ifd("IFD0", first)
    ifd0 = result.get("IFD0", {})
    for tag, name in ((0x8769, "Exif"), (0x8825, "GPS")):
        pointer = ifd0.get(tag)
        if isinstance(pointer, int):
            read_ifd(name, pointer)
    if next_ifd:
        read_ifd("IFD1", next_ifd)
    return result


def _rational(value) -> float | None:
    if isinstance(value, tuple) and len(value) == 2:
        return value[0] / value[1] if value[1] else None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _fmt(tag: int, value) -> str:
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "groß":
        return f"{value[1]} Bytes"
    if tag == 0x0112 and isinstance(value, int):
        return f"{value} ({ORIENTATION.get(value, '?')})"
    if tag == 0x829A:
        r = _rational(value)
        return f"1/{round(1 / r)} s" if r and r < 1 else (f"{r:g} s" if r else "")
    if tag == 0x829D:
        r = _rational(value)
        return f"f/{r:.1f}" if r else ""
    if tag in (0x920A,):
        r = _rational(value)
        return f"{r:g} mm" if r else ""
    if tag == 0x927C and isinstance(value, bytes):
        return f"vorhanden ({len(value)} Bytes, herstellerspezifisch)"
    if 0x9C9B <= tag <= 0x9C9F and isinstance(value, bytes):
        return value.decode("utf-16-le", "replace").rstrip("\x00")
    if tag == 0x9286 and isinstance(value, bytes):
        head, body = value[:8], value[8:]
        text = body.decode("utf-16-le" if head.startswith(b"UNICODE") else "latin-1", "replace")
        return text.strip("\x00 ")
    if isinstance(value, tuple) and len(value) == 2:
        r = _rational(value)
        return f"{r:g}" if r is not None else ""
    if isinstance(value, bytes):
        printable = value.rstrip(b"\x00")
        if printable and all(32 <= b < 127 for b in printable):
            return printable.decode("ascii")
        return f"{len(value)} Bytes"
    if isinstance(value, list):
        return ", ".join(_fmt(0, v) for v in value[:16]) + (" …" if len(value) > 16 else "")
    return str(value)


def _dms(values, ref) -> float | None:
    if not isinstance(values, list) or len(values) != 3:
        return None
    parts = [_rational(v) for v in values]
    if any(p is None for p in parts):
        return None
    deg = parts[0] + parts[1] / 60 + parts[2] / 3600
    return -deg if str(ref).upper().startswith(("S", "W")) else deg


def add_exif(report: Report, data, prefix: str = "EXIF") -> None:
    try:
        ifds = parse_tiff(data)
    except (MetadataError, struct.error):
        report.add(prefix, "Fehler", "EXIF-Block nicht lesbar")
        return
    for ifd_name, tags in (("IFD0", IFD0_TAGS), ("Exif", EXIF_TAGS)):
        for tag, value in ifds.get(ifd_name, {}).items():
            if tag in (0x8769, 0x8825, 0xA005):
                continue
            name, group = tags.get(tag, (f"Tag 0x{tag:04X}", "Weitere"))
            if group == "Weitere" and isinstance(value, bytes) and len(value) > 64:
                continue
            report.add(f"{prefix} · {group}", name, _fmt(tag, value))
    gps = ifds.get("GPS", {})
    if gps:
        lat, lon = _dms(gps.get(2), gps.get(1, "N")), _dms(gps.get(4), gps.get(3, "E"))
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon):
            report.gps = (lat, lon)
            report.add(f"{prefix} · GPS", "Koordinaten", f"{lat:.6f}, {lon:.6f}")
        for tag, name in GPS_TAGS.items():
            if tag in gps:
                value = gps[tag]
                if tag == 0x0007 and isinstance(value, list):
                    value = ":".join(f"{int(_rational(v) or 0):02d}" for v in value)
                elif tag == 0x0006:
                    r = _rational(value)
                    value = f"{r:.1f} m" if r is not None else ""
                else:
                    value = _fmt(tag, value)
                report.add(f"{prefix} · GPS", name, value)
    thumb = ifds.get("IFD1", {})
    if 0x0201 in thumb and 0x0202 in thumb:
        report.add(f"{prefix} · Bild", "Eingebettetes Vorschaubild",
                   f"{thumb[0x0202]} Bytes (kann das Motiv vor einem Zuschnitt zeigen)")


# ---- XMP ----------------------------------------------------------------------------------------------------------
PREFIXES = {
    "http://purl.org/dc/elements/1.1/": "dc", "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/xap/1.0/mm/": "xmpMM", "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://ns.adobe.com/pdf/1.3/": "pdf", "http://ns.adobe.com/exif/1.0/": "exif",
    "http://ns.adobe.com/tiff/1.0/": "tiff", "http://ns.adobe.com/xap/1.0/rights/": "xmpRights",
    "http://ns.adobe.com/camera-raw-settings/1.0/": "crs", "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/": "Iptc4xmpCore",
}
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"


def _qname(tag: str) -> str:
    if tag.startswith("{"):
        uri, _, local = tag[1:].partition("}")
        return f"{PREFIXES.get(uri, uri.rstrip('/').rsplit('/', 1)[-1])}:{local}"
    return tag


def parse_xmp(xml: bytes) -> list[tuple[str, str]]:
    """XMP-Paket → [(Name, Wert)]; Listen (rdf:Seq/Bag/Alt) zusammengefasst, Attribut-Kurzform berücksichtigt."""
    start, end = xml.find(b"<x:xmpmeta"), xml.rfind(b"</x:xmpmeta>")
    if start < 0:
        start, end = xml.find(b"<rdf:RDF"), xml.rfind(b"</rdf:RDF>")
        end = end + len(b"</rdf:RDF>") if end >= 0 else -1
    else:
        end += len(b"</x:xmpmeta>")
    if start < 0 or end <= start or b"<!ENTITY" in xml[:end]:
        return []
    try:
        root = ET.fromstring(xml[start:end])
    except ET.ParseError:
        return []
    out: list[tuple[str, str]] = []
    for desc in root.iter(f"{RDF}Description"):
        for key, val in desc.attrib.items():
            if not key.startswith(RDF) and not key.startswith("{http://www.w3.org/XML/1998/namespace}"):
                out.append((_qname(key), val))
        for child in desc:
            items = [li.text or "" for li in child.iter(f"{RDF}li") if (li.text or "").strip()]
            text = "; ".join(items) if items else (child.text or "").strip()
            if not text:
                nested = [f"{_qname(k).split(':')[-1]}={v}" for sub in child.iter() for k, v in sub.attrib.items()
                          if not k.startswith(RDF)]
                text = ", ".join(nested[:10])
            if text:
                out.append((_qname(child.tag), text))
    return out[:500]


def add_xmp(report: Report, xml: bytes, group: str = "XMP") -> None:
    for name, value in parse_xmp(xml):
        report.add(group, name, value)


# ---- IPTC (Photoshop APP13) ---------------------------------------------------------------------------------------
IPTC_NAMES = {5: "Objektname", 25: "Stichwort", 55: "Erstellt am", 60: "Erstellt um", 80: "Autor", 85: "Autor-Titel",
              90: "Stadt", 92: "Ortsteil", 95: "Bundesland", 101: "Land", 105: "Überschrift", 110: "Credit",
              115: "Quelle", 116: "Copyright", 118: "Kontakt", 120: "Beschreibung", 122: "Verfasser Beschreibung"}


def add_iptc(report: Report, payload: bytes) -> None:
    pos = payload.find(b"8BIM\x04\x04")
    if pos < 0:
        return
    name_len = payload[pos + 6] if pos + 6 < len(payload) else 0
    pos += 6 + 1 + name_len + ((1 + name_len) % 2)
    if pos + 4 > len(payload):
        return
    size = struct.unpack(">I", payload[pos:pos + 4])[0]
    data, i = payload[pos + 4:pos + 4 + size], 0
    while i + 5 <= len(data) and data[i] == 0x1C:
        record, dataset, length = data[i + 1], data[i + 2], struct.unpack(">H", data[i + 3:i + 5])[0]
        value = data[i + 5:i + 5 + length]
        if record == 2 and dataset in IPTC_NAMES:
            report.add("IPTC", IPTC_NAMES[dataset], value.decode("utf-8", "replace"))
        i += 5 + length


# ---- JPEG ---------------------------------------------------------------------------------------------------------
KEEP_APP = {0xE0, 0xE2, 0xEE}     # JFIF, ICC-Profil, Adobe (Farbumrechnung) – für die Darstellung nötig


def _jpeg_segments(mm) -> tuple[list[tuple[int, int, int]], int, int]:
    """[(Marker, Start, Ende)] bis SOS; dazu Position von SOS und des echten Bildendes (EOI) oder -1."""
    segments, pos, size = [], 2, len(mm)
    while pos + 4 <= size:
        if mm[pos] != 0xFF:
            raise MetadataError(f"JPEG-Struktur bei Offset {pos} unerwartet")
        marker = mm[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        length = struct.unpack(">H", mm[pos + 2:pos + 4])[0]
        segments.append((marker, pos, pos + 2 + length))
        if marker == 0xDA:
            break
        pos += 2 + length
    else:
        return segments, -1, -1
    sos = pos
    # Bildende: nach SOS das erste FF D9, das kein Füllbyte (FF 00) und kein RST ist; Segmente dazwischen überspringen
    pos = sos + 2 + length
    while True:
        pos = mm.find(b"\xff", pos)
        if pos < 0 or pos + 1 >= size:
            return segments, sos, -1
        nxt = mm[pos + 1]
        if nxt == 0xD9:
            return segments, sos, pos + 2
        if nxt in (0x00, 0xFF) or 0xD0 <= nxt <= 0xD7:
            pos += 1 if nxt == 0xFF else 2
            continue
        if pos + 4 > size:
            return segments, sos, -1
        pos += 2 + struct.unpack(">H", mm[pos + 2:pos + 4])[0]


def _read_jpeg(path: Path, report: Report) -> None:
    with _mapped(path) as mm:
        segments, sos, eoi = _jpeg_segments(mm)
        removed: dict[str, int] = {}
        for marker, start, end in segments:
            payload = bytes(mm[start + 4:end])
            if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
                add_exif(report, payload[6:])
                removed["EXIF (Kamera, Zeiten, GPS, Vorschaubild)"] = 1
            elif marker == 0xE1 and payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
                add_xmp(report, payload[29:])
                removed["XMP"] = 1
            elif marker == 0xE1 and payload.startswith(b"http://ns.adobe.com/xmp/extension/"):
                report.add("XMP", "Erweitertes XMP", f"{len(payload)} Bytes")
                removed["XMP"] = 1
            elif marker == 0xED:
                add_iptc(report, payload)
                removed["IPTC/Photoshop (APP13)"] = 1
            elif marker == 0xFE:
                report.add("Kommentar", "JPEG-Kommentar", payload.decode("utf-8", "replace"))
                removed["JPEG-Kommentar"] = 1
            elif marker == 0xE2 and payload.startswith(b"MPF\x00"):
                report.add("Datei", "Weitere Bilder (MPF)", "vorhanden – liegen hinter dem Hauptbild")
                removed["Mehrbild-Verweise (MPF)"] = 1
            elif 0xE1 <= marker <= 0xEF and marker not in KEEP_APP:
                ident = payload[:24].split(b"\x00")[0].decode("latin-1", "replace")
                report.add("Weitere Segmente", f"APP{marker - 0xE0}", f"{ident or '?'} ({len(payload)} Bytes)")
                removed[f"APP{marker - 0xE0}-Segmente (herstellerspezifisch)"] = 1
        if eoi > 0 and eoi < len(mm):
            tail = len(mm) - eoi
            report.add("Datei", "Daten hinter dem Bildende", f"{tail} Bytes (z. B. weiteres Bild, Tiefenkarte)")
            removed["Daten hinter dem Bildende"] = 1
        report.removes = list(removed)
        report.keeps = ["Bilddaten (unverändert, keine Neukodierung)", "JFIF-Kopf, ICC-Farbprofil, Adobe-Segment"]
        report.can_strip = sos > 0
        orientation = next((f.value for f in report.fields if f.name == "Ausrichtung"), "")
        if orientation and not orientation.startswith("1 "):
            report.keeps.append(f"Hinweis: Ausrichtung „{orientation}“ steht im EXIF – ohne sie kann das Bild gedreht "
                                "erscheinen")


def _strip_jpeg(src: Path, handle) -> None:
    with _mapped(src) as mm:
        segments, sos, eoi = _jpeg_segments(mm)
        if sos < 0:
            raise MetadataError("JPEG ohne Bilddaten (SOS) – nicht bereinigt")
        handle.write(b"\xff\xd8")
        for marker, start, end in segments:
            if marker == 0xDA:
                break
            payload = mm[start + 4:start + 8]
            drop = (0xE1 <= marker <= 0xEF and marker not in KEEP_APP) or marker == 0xFE or \
                (marker == 0xE2 and payload == b"MPF\x00")
            if not drop:
                handle.write(mm[start:end])
        _copy_range(mm, sos, eoi if eoi > 0 else len(mm), handle)


# ---- PNG ----------------------------------------------------------------------------------------------------------
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_META = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME", b"dSIG"}


def _png_chunks(handle):
    handle.seek(8)
    while True:
        head = handle.read(8)
        if len(head) < 8:
            return
        length, kind = struct.unpack(">I", head[:4])[0], head[4:]
        start = handle.tell() - 8
        yield kind, start, length
        handle.seek(start + 12 + length)
        if kind == b"IEND":
            return


def _read_png(path: Path, report: Report) -> None:
    removed: dict[str, int] = {}
    size = path.stat().st_size
    with open(path, "rb") as handle:
        end = 8
        for kind, start, length in _png_chunks(handle):
            end = start + 12 + length
            if kind not in PNG_META:
                continue
            handle.seek(start + 8)
            data = handle.read(min(length, MAX_XML))
            if kind == b"tEXt":
                key, _, text = data.partition(b"\x00")
                report.add("PNG-Text", key.decode("latin-1"), text.decode("latin-1"))
            elif kind == b"zTXt":
                key, _, rest = data.partition(b"\x00")
                report.add("PNG-Text", key.decode("latin-1"), _inflate(rest[1:]).decode("latin-1", "replace"))
            elif kind == b"iTXt":
                key, _, rest = data.partition(b"\x00")
                compressed, rest = rest[:1] == b"\x01", rest[2:]
                _lang, _, rest = rest.partition(b"\x00")
                _translated, _, text = rest.partition(b"\x00")
                text = _inflate(text) if compressed else text
                if key == b"XML:com.adobe.xmp":
                    add_xmp(report, text)
                else:
                    report.add("PNG-Text", key.decode("latin-1"), text.decode("utf-8", "replace"))
            elif kind == b"eXIf":
                add_exif(report, data)
            elif kind == b"tIME" and len(data) == 7:
                y, mo, d, h, mi, s = struct.unpack(">HBBBBB", data)
                report.add("Zeit", "Zuletzt geändert (tIME)", f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d} UTC")
            elif kind == b"dSIG":
                report.add("Datei", "Digitale Signatur", f"{length} Bytes")
            removed[{b"tEXt": "Text-Chunks", b"zTXt": "Text-Chunks", b"iTXt": "Text-Chunks/XMP", b"eXIf": "EXIF",
                     b"tIME": "Änderungszeit (tIME)", b"dSIG": "Signatur (dSIG)"}[kind]] = 1
        if end < size:
            report.add("Datei", "Daten hinter IEND", f"{size - end} Bytes")
            removed["Daten hinter dem Bildende"] = 1
    report.removes = list(removed)
    report.keeps = ["Bilddaten und Farbinformationen (unverändert)"]
    report.can_strip = True


def _strip_png(src: Path, out) -> None:
    with open(src, "rb") as handle:
        out.write(PNG_SIG)
        for kind, start, length in list(_png_chunks(handle)):
            if kind in PNG_META:
                continue
            handle.seek(start)
            _copy_stream(handle, 12 + length, out)


def _inflate(data: bytes) -> bytes:
    try:
        return zlib.decompressobj().decompress(data, 1 << 20)
    except zlib.error:
        return b""


# ---- WebP ---------------------------------------------------------------------------------------------------------
def _webp_chunks(handle, size: int):
    pos = 12
    while pos + 8 <= size:
        handle.seek(pos)
        head = handle.read(8)
        kind, length = head[:4], struct.unpack("<I", head[4:])[0]
        yield kind, pos, length
        pos += 8 + length + (length & 1)


def _read_webp(path: Path, report: Report) -> None:
    removed = []
    size = path.stat().st_size
    with open(path, "rb") as handle:
        for kind, pos, length in _webp_chunks(handle, size):
            if kind in (b"EXIF", b"XMP "):
                handle.seek(pos + 8)
                data = handle.read(min(length, MAX_XML))
                if kind == b"EXIF":
                    add_exif(report, data[6:] if data.startswith(b"Exif\x00\x00") else data)
                    removed.append("EXIF")
                else:
                    add_xmp(report, data)
                    removed.append("XMP")
    report.removes, report.can_strip = sorted(set(removed)), True
    report.keeps = ["Bilddaten, ICC-Profil, Animation (unverändert)"]


def _strip_webp(src: Path, out) -> None:
    size = src.stat().st_size
    with open(src, "rb") as handle:
        body = bytearray()
        for kind, pos, length in list(_webp_chunks(handle, size)):
            if kind in (b"EXIF", b"XMP "):
                continue
            handle.seek(pos)
            chunk = bytearray(handle.read(8 + length + (length & 1)))
            if kind == b"VP8X" and len(chunk) > 8:
                chunk[8] &= ~0x0C & 0xFF            # Flags EXIF (0x08) und XMP (0x04) löschen
            body += chunk
        out.write(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + bytes(body))


# ---- PDF ----------------------------------------------------------------------------------------------------------
PDF_NAMES = {"/Title": "Titel", "/Author": "Autor", "/Subject": "Thema", "/Keywords": "Stichwörter",
             "/Creator": "Erstellt mit", "/Producer": "PDF-Erzeuger", "/CreationDate": "Erstellt",
             "/ModDate": "Geändert", "/Trapped": "Trapped"}


def pdf_date(value: str) -> str:
    """D:20240131142233+01'00' → 2024-01-31 14:22:33 +01:00 (unbekannte Formate bleiben unverändert)."""
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+-])?(\d{2})?'?(\d{2})?", value or "")
    if not m:
        return value
    y, mo, d, h, mi, s, tz, th, tm = m.groups()
    text = f"{y}-{mo or '01'}-{d or '01'} {h or '00'}:{mi or '00'}:{s or '00'}"
    if tz in ("Z", "z"):
        text += " UTC"
    elif tz:
        text += f" {tz}{th or '00'}:{tm or '00'}"
    return text


def _pdf_reader(path: Path):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as error:                        # pragma: no cover - Build ohne pypdf
        raise MetadataError("pypdf fehlt – PDF-Metadaten nicht verfügbar") from error
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise MetadataError("PDF ist verschlüsselt – ohne Passwort nicht lesbar")
        return reader
    except (PdfReadError, ValueError, KeyError, OSError) as error:
        raise MetadataError(f"PDF nicht lesbar: {error}") from error


def _read_pdf(path: Path, report: Report) -> None:
    reader = _pdf_reader(path)
    info = reader.metadata or {}
    for key, value in info.items():
        name = PDF_NAMES.get(key, key.lstrip("/"))
        text = pdf_date(str(value)) if key in ("/CreationDate", "/ModDate") else value
        report.add("PDF-Info", name, text)
    try:
        meta = reader.trailer["/Root"].get("/Metadata")
        if meta is not None:
            add_xmp(report, meta.get_object().get_data()[:MAX_XML])
    except Exception:                                   # noqa: BLE001 - kaputtes XMP darf die Anzeige nicht stoppen
        report.add("XMP", "Fehler", "XMP-Block nicht lesbar")
    report.add("Datei", "PDF-Version", reader.pdf_header.lstrip("%"), removable=False)
    report.add("Datei", "Seiten", len(reader.pages), removable=False)
    report.add("Datei", "Verschlüsselt", "ja (ohne Passwort lesbar)" if reader.is_encrypted else "nein", removable=False)
    with _mapped(path) as mm:
        saves = _count(mm, b"%%EOF")
    if saves > 1:
        report.add("Datei", "Speicherstände", f"{saves} (ältere Fassungen samt Metadaten stecken noch in der Datei)")
    report.removes = ["Info-Dictionary (Autor, Titel, Programme, Zeiten)", "XMP-Metadaten (Dokument und Seiten)"] + \
        (["ältere Speicherstände (die Kopie wird neu geschrieben)"] if saves > 1 else [])
    report.keeps = ["Seiteninhalt, Formulare, Anmerkungen, Lesezeichen",
                    "Hinweis: Namen in Kommentaren oder im Text selbst bleiben"]
    report.can_strip = not reader.is_encrypted
    if reader.is_encrypted:
        report.keeps.append("Verschlüsselte PDFs werden nicht bereinigt (Rechte gingen verloren)")


def _strip_pdf(src: Path, out) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import NameObject
    reader = _pdf_reader(src)
    if reader.is_encrypted:
        raise MetadataError("Verschlüsselte PDFs werden nicht bereinigt")
    writer = PdfWriter(clone_from=reader)
    writer.metadata = None
    for holder in [writer._root_object] + list(writer.pages):
        for key in ("/Metadata", "/PieceInfo"):
            if key in holder:
                del holder[NameObject(key)]
    # Entfernte Objekte (Info, XMP) stünden sonst als verwaiste Objekte weiterhin in der Datei
    writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    writer.write(out)


# ---- Office (OOXML) -----------------------------------------------------------------------------------------------
NS = {"cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
      "dc": "http://purl.org/dc/elements/1.1/", "dcterms": "http://purl.org/dc/terms/",
      "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
      "cu": "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties",
      "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
CORE_NAMES = {"title": "Titel", "subject": "Thema", "creator": "Autor", "keywords": "Stichwörter",
              "description": "Kommentar", "lastModifiedBy": "Zuletzt geändert von", "revision": "Revision",
              "created": "Erstellt", "modified": "Geändert", "lastPrinted": "Zuletzt gedruckt",
              "category": "Kategorie", "contentStatus": "Status", "identifier": "Kennung", "language": "Sprache",
              "version": "Version"}
APP_NAMES = {"Application": "Programm", "AppVersion": "Programmversion", "Company": "Firma", "Manager": "Vorgesetzter",
             "Template": "Vorlage", "TotalTime": "Bearbeitungszeit (Minuten)", "Pages": "Seiten", "Words": "Wörter",
             "Characters": "Zeichen", "Lines": "Zeilen", "Paragraphs": "Absätze", "Slides": "Folien",
             "Notes": "Notizen", "HiddenSlides": "Ausgeblendete Folien", "HyperlinkBase": "Link-Basis",
             "DocSecurity": "Dokumentschutz"}
EMPTY_CORE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<cp:coreProperties xmlns:cp="'
              + NS["cp"] + '" xmlns:dc="' + NS["dc"] + '" xmlns:dcterms="' + NS["dcterms"]
              + '" xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
              'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"></cp:coreProperties>').encode()
EMPTY_APP = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<Properties xmlns="' + NS["ep"]
             + '" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"></Properties>').encode()
EMPTY_CUSTOM = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<Properties xmlns="' + NS["cu"]
                + '" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"></Properties>').encode()
PROPS = {"docProps/core.xml": EMPTY_CORE, "docProps/app.xml": EMPTY_APP, "docProps/custom.xml": EMPTY_CUSTOM}


def is_office(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return "[Content_Types].xml" in archive.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def _xml(archive: zipfile.ZipFile, name: str):
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_XML:
        return None
    data = archive.read(name)
    if b"<!ENTITY" in data:
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


def _people(archive: zipfile.ZipFile) -> dict[str, set[str]]:
    """Namen, die im Inhalt stecken: Kommentar-Autoren, Änderungsverfolgung (Word), Kommentare (Excel/PowerPoint)."""
    found: dict[str, set[str]] = {}
    for name in archive.namelist():
        low = name.lower()
        if not low.endswith(".xml") or archive.getinfo(name).file_size > 256 * 1024 * 1024:
            continue
        if low.startswith("word/") and low.rsplit("/", 1)[-1] in ("document.xml", "comments.xml", "footnotes.xml",
                                                                  "endnotes.xml") or "comment" in low:
            label = "Kommentar-Autoren" if "comment" in low else "Autoren in der Änderungsverfolgung"
            try:
                with archive.open(name) as stream:
                    for _event, elem in ET.iterparse(stream):
                        tag = elem.tag.rsplit("}", 1)[-1]
                        author = elem.get(f"{{{NS['w']}}}author") or (elem.get("name") if tag == "cmAuthor" else None)
                        if author and tag in ("ins", "del", "comment", "moveFrom", "moveTo", "rPrChange", "pPrChange",
                                              "cmAuthor"):
                            found.setdefault(label, set()).add(author)
                        elif tag == "author" and elem.text:
                            found.setdefault(label, set()).add(elem.text.strip())
                        elem.clear()
            except ET.ParseError:
                continue
    return found


def _read_office(path: Path, report: Report) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        core = _xml(archive, "docProps/core.xml")
        if core is not None:
            for child in core:
                local = child.tag.rsplit("}", 1)[-1]
                report.add("Dokument", CORE_NAMES.get(local, local), child.text)
        app = _xml(archive, "docProps/app.xml")
        if app is not None:
            for child in app:
                local = child.tag.rsplit("}", 1)[-1]
                if local in APP_NAMES:
                    report.add("Programm", APP_NAMES[local], child.text)
        custom = _xml(archive, "docProps/custom.xml")
        if custom is not None:
            for prop in custom:
                value = "".join(prop.itertext()).strip()
                report.add("Eigene Eigenschaften", prop.get("name", "?"), value)
        thumbs = [n for n in names if n.lower().startswith("docprops/thumbnail")]
        for thumb in thumbs:
            report.add("Datei", "Vorschaubild", f"{thumb} ({archive.getinfo(thumb).file_size} Bytes)")
        for label, people in _people(archive).items():
            report.add("Im Inhalt", label, ", ".join(sorted(people)), removable=False)
    report.removes = ["Dokumenteigenschaften (Autor, zuletzt geändert von, Zeiten, Revision)",
                      "Programmangaben (Firma, Vorlage, Bearbeitungszeit)", "eigene Eigenschaften"] + \
        (["Vorschaubild"] if thumbs else [])
    report.keeps = ["Inhalt unverändert – Namen in Kommentaren und Änderungsverfolgung bleiben (vorher im Programm "
                    "entfernen: „Dokument prüfen“)"]
    report.can_strip = True


def _strip_office(src: Path, out) -> None:
    with zipfile.ZipFile(src) as archive, zipfile.ZipFile(out, "w") as target:
        thumbs = {n for n in archive.namelist() if n.lower().startswith("docprops/thumbnail")}
        for info in archive.infolist():
            if info.filename in thumbs:
                continue
            if info.filename in PROPS:
                data = PROPS[info.filename]
            elif info.filename in ("_rels/.rels", "[Content_Types].xml") and thumbs:
                data = archive.read(info.filename)
                for thumb in thumbs:
                    data = re.sub(rb"<(Relationship|Override)\b[^>]*" + re.escape(thumb.encode()) + rb"\"[^>]*/>",
                                  b"", data)
            else:
                with archive.open(info) as stream, target.open(_clean_info(info), "w") as sink:
                    _copy_stream(stream, info.file_size, sink)
                continue
            target.writestr(_clean_info(info), data)


def _clean_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    """Gleicher Name und Kompression, aber festes Datum und keine Extra-Felder/Kommentare."""
    clean = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
    clean.compress_type = info.compress_type if info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) \
        else zipfile.ZIP_DEFLATED
    clean.external_attr = 0
    return clean


# ---- Allgemein ----------------------------------------------------------------------------------------------------
class _mapped:
    """mmap einer Datei (auch 0 Bytes) – große Dateien werden nie komplett gelesen."""

    def __init__(self, path: Path) -> None:
        self.handle = open(path, "rb")
        size = self.handle.seek(0, 2)
        self.mm = mmap.mmap(self.handle.fileno(), 0, access=mmap.ACCESS_READ) if size else b""

    def __enter__(self):
        return self.mm

    def __exit__(self, *exc) -> None:
        if isinstance(self.mm, mmap.mmap):
            self.mm.close()
        self.handle.close()


def _count(mm, needle: bytes) -> int:
    count, pos = 0, mm.find(needle)
    while pos >= 0 and count < 10_000:
        count += 1
        pos = mm.find(needle, pos + 1)
    return count


def _copy_range(mm, start: int, end: int, out) -> None:
    step = 4 * 1024 * 1024
    for pos in range(start, end, step):
        out.write(mm[pos:min(end, pos + step)])


def _copy_stream(stream, length: int, out) -> None:
    remaining = length
    while remaining > 0:
        block = stream.read(min(remaining, 4 * 1024 * 1024))
        if not block:
            break
        out.write(block)
        remaining -= len(block)


def detect(path: Path) -> str:
    with open(path, "rb") as handle:
        head = handle.read(16)
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(PNG_SIG):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    with open(path, "rb") as handle:
        if b"%PDF-" in handle.read(1024):
            return "pdf"
    if head.startswith(b"PK\x03\x04") and is_office(path):
        return "office"
    return "unbekannt"


READERS = {"jpeg": _read_jpeg, "png": _read_png, "webp": _read_webp, "pdf": _read_pdf, "office": _read_office}
STRIPPERS = {"jpeg": _strip_jpeg, "png": _strip_png, "webp": _strip_webp, "pdf": _strip_pdf, "office": _strip_office}
KIND_NAMES = {"jpeg": "JPEG-Bild", "png": "PNG-Bild", "webp": "WebP-Bild", "tiff": "TIFF-Bild", "pdf": "PDF",
              "office": "Office-Dokument (OOXML)", "unbekannt": "unbekannt"}


def read(path: Path) -> Report:
    """Alle Metadaten einer Datei. Wirft MetadataError bei kaputten oder nicht unterstützten Dateien."""
    path = Path(path)
    kind = detect(path)
    report = Report(kind)
    if kind == "tiff":
        with _mapped(path) as mm:
            add_exif(report, mm, prefix="TIFF")
        report.keeps = ["TIFF-Dateien werden nicht bereinigt (Metadaten und Bildstruktur sind verwoben)"]
        return report
    reader = READERS.get(kind)
    if reader is None:
        raise MetadataError("Dateityp nicht unterstützt (Bilder: JPEG, PNG, WebP, TIFF · PDF · docx/xlsx/pptx)")
    try:
        reader(path, report)
    except (struct.error, IndexError, zipfile.BadZipFile, EOFError) as error:
        raise MetadataError(f"Datei beschädigt oder unvollständig: {error}") from error
    return report


def clean_name(path: Path) -> Path:
    """Nächster freier Name <stem>_ohne_Metadaten[ (n)].<ext> neben dem Original."""
    base = path.with_name(f"{path.stem}_ohne_Metadaten{path.suffix}")
    n = 2
    while base.exists():
        base = path.with_name(f"{path.stem}_ohne_Metadaten ({n}){path.suffix}")
        n += 1
    return base


def strip(path: Path, target: Path | None = None) -> Path:
    """Bereinigte KOPIE schreiben (nie überschreiben, Original bleibt). Gibt den Pfad der Kopie zurück."""
    path = Path(path)
    kind = detect(path)
    stripper = STRIPPERS.get(kind)
    if stripper is None:
        raise MetadataError(f"{KIND_NAMES.get(kind, kind)}: Entfernen nicht unterstützt")
    target = Path(target) if target is not None else clean_name(path)
    try:
        with open(target, "xb") as out:
            stripper(path, out)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def verify(original: Path, cleaned: Path) -> list[Field]:
    """Liest die Kopie erneut: Liste der noch vorhandenen entfernbaren Felder (leer = sauber)."""
    report = read(cleaned)
    left = report.removable_fields
    if detect(original) != report.kind:
        left.append(Field("Datei", "Dateityp", "Kopie hat einen anderen Typ als das Original"))
    return left


def osm_url(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=16/{lat:.6f}/{lon:.6f}"


def to_text(report: Report) -> str:
    return "\n".join(f"{f.group}\t{f.name}\t{f.value}" for f in report.fields)


def to_markdown(report: Report, name: str) -> str:
    def cell(text: str) -> str:
        return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
    lines = [f"### Metadaten: {cell(name)}", "", f"Typ: {KIND_NAMES.get(report.kind, report.kind)}", ""]
    if report.fields:
        lines += ["| Gruppe | Feld | Wert |", "|---|---|---|"]
        lines += [f"| {cell(f.group)} | {cell(f.name)} | {cell(f.value)} |" for f in report.fields]
    else:
        lines.append("Keine Metadaten gefunden.")
    if report.gps:
        lines += ["", f"GPS: [{report.gps[0]:.6f}, {report.gps[1]:.6f}]({osm_url(*report.gps)})"]
    return "\n".join(lines) + "\n"
