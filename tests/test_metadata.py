import io
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from notex.core import metadata as md


# ---- Testdateien selbst bauen -------------------------------------------------------------------------------------
def tiff(ifds: dict[str, list[tuple[int, int, int, bytes]]]) -> bytes:
    """Kleiner EXIF/TIFF-Block (Little Endian): IFD0 mit Zeigern auf Exif- und GPS-IFD."""
    order = [name for name in ("IFD0", "Exif", "GPS") if name in ifds]
    sizes = {name: 2 + 12 * (len(ifds[name]) + (name == "IFD0") * (len(order) - 1)) + 4 for name in order}
    extra = {name: sum(len(v) for *_x, v in ifds[name] if len(v) > 4) for name in order}
    offsets, pos = {}, 8
    for name in order:
        offsets[name] = pos
        pos += sizes[name] + extra[name]
    out = bytearray(b"II*\x00" + struct.pack("<I", 8))
    for name in order:
        entries = list(ifds[name])
        if name == "IFD0":
            entries += [(0x8769, 4, 1, struct.pack("<I", offsets["Exif"]))] if "Exif" in ifds else []
            entries += [(0x8825, 4, 1, struct.pack("<I", offsets["GPS"]))] if "GPS" in ifds else []
        entries.sort()
        data_pos = offsets[name] + sizes[name]
        block, data = bytearray(struct.pack("<H", len(entries))), bytearray()
        for tag, kind, count, value in entries:
            if len(value) <= 4:
                block += struct.pack("<HHI", tag, kind, count) + value.ljust(4, b"\x00")
            else:
                block += struct.pack("<HHII", tag, kind, count, data_pos + len(data))
                data += value
        block += struct.pack("<I", 0)
        out += block + data
    return bytes(out)


def ascii_tag(tag: int, text: str) -> tuple[int, int, int, bytes]:
    raw = text.encode() + b"\x00"
    return tag, 2, len(raw), raw


def rationals(*pairs) -> bytes:
    return b"".join(struct.pack("<II", a, b) for a, b in pairs)


EXIF = tiff({
    "IFD0": [ascii_tag(0x010F, "Canon"), ascii_tag(0x0110, "EOS 5D"), ascii_tag(0x0131, "GIMP 2.10"),
             ascii_tag(0x0132, "2024:05:01 10:00:00"), ascii_tag(0x013B, "Max Mustermann"),
             (0x0112, 3, 1, struct.pack("<H", 6))],
    "Exif": [ascii_tag(0x9003, "2024:04:30 18:22:11"), ascii_tag(0xA431, "SN12345"),
             (0x829A, 5, 1, rationals((1, 250))), (0x829D, 5, 1, rationals((28, 10)))],
    "GPS": [ascii_tag(0x0001, "N"), (0x0002, 5, 3, rationals((52, 1), (31, 1), (1200, 100))),
            ascii_tag(0x0003, "E"), (0x0004, 5, 3, rationals((13, 1), (24, 1), (3600, 100)))],
})
XMP = (b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
       b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       b'<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
       b'xmp:CreatorTool="Photoshop 25"><dc:creator><rdf:Seq><rdf:li>Erika Beispiel</rdf:li></rdf:Seq></dc:creator>'
       b'</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
SCAN = b"\x12\x34\xff\x00\x56\xff\xd0\x78\x9a"      # Bilddaten mit Füllbyte und RST-Marker


def seg(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def jpeg(trailer: bytes = b"TRAILER") -> bytes:
    iptc = b"Photoshop 3.0\x008BIM\x04\x04\x00\x00" + struct.pack(">I", 16) + b"\x1c\x02\x50\x00\x0bIPTC Person"
    return (b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + seg(0xE1, b"Exif\x00\x00" + EXIF) + seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP)
            + seg(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"x" * 20) + seg(0xED, iptc) + seg(0xFE, b"geheimer Kommentar")
            + seg(0xDB, b"\x00" + bytes(64)) + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + SCAN + b"\xff\xd9" + trailer)


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (md.PNG_SIG + chunk(b"IHDR", ihdr) + chunk(b"tEXt", b"Author\x00Max Mustermann")
            + chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + XMP) + chunk(b"eXIf", EXIF)
            + chunk(b"tIME", struct.pack(">HBBBBB", 2024, 5, 1, 12, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"") + b"hinten")


def webp() -> bytes:
    def riff(kind, data):
        return kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")
    body = riff(b"VP8X", bytes([0x0C, 0, 0, 0]) + bytes(6)) + riff(b"VP8 ", b"\x00" * 11) + \
        riff(b"EXIF", EXIF) + riff(b"XMP ", XMP)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def pdf(tmp_path: Path) -> Path:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.add_metadata({"/Author": "Max Mustermann", "/Creator": "Word", "/Producer": "Acrobat",
                         "/CreationDate": "D:20240131142233+01'00'", "/Company": "ACME"})
    stream = DecodedStreamObject()
    stream.set_data(XMP)
    stream[NameObject("/Type")] = NameObject("/Metadata")
    writer._root_object[NameObject("/Metadata")] = writer._add_object(stream)
    path = tmp_path / "bericht.pdf"
    with open(path, "wb") as handle:
        writer.write(handle)
    update = PdfWriter(str(path), incremental=True)        # zweiter Speicherstand (inkrementelle Aktualisierung)
    update.add_metadata({"/Title": "Neuer Titel"})
    buf = io.BytesIO()
    update.write(buf)
    path.write_bytes(buf.getvalue())
    return path


def docx() -> bytes:
    core = ('<?xml version="1.0"?><cp:coreProperties xmlns:cp="' + md.NS["cp"] + '" xmlns:dc="' + md.NS["dc"]
            + '" xmlns:dcterms="' + md.NS["dcterms"] + '"><dc:creator>Max Mustermann</dc:creator>'
            '<cp:lastModifiedBy>Erika Beispiel</cp:lastModifiedBy><cp:revision>7</cp:revision>'
            '<dcterms:created>2024-01-02T03:04:05Z</dcterms:created></cp:coreProperties>')
    app = ('<?xml version="1.0"?><Properties xmlns="' + md.NS["ep"] + '"><Application>Microsoft Office Word'
           '</Application><Company>ACME GmbH</Company><Template>Geheim.dotm</Template><TotalTime>42</TotalTime>'
           '</Properties>')
    custom = ('<?xml version="1.0"?><Properties xmlns="' + md.NS["cu"] + '" xmlns:vt="x"><property name="Projekt">'
              '<vt:lpwstr>Falke</vt:lpwstr></property></Properties>')
    document = ('<?xml version="1.0"?><w:document xmlns:w="' + md.NS["w"] + '"><w:body><w:p><w:ins w:author="Tom">'
                '<w:r><w:t>neu</w:t></w:r></w:ins></w:p></w:body></w:document>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="x"><Relationship Id="r1" Target="word/document.xml"/>'
            '<Relationship Id="r2" Type="thumb" Target="docProps/thumbnail.jpeg"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="x"><Default Extension="xml"/></Types>')
        archive.writestr("_rels/.rels", rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("docProps/custom.xml", custom)
        archive.writestr("docProps/thumbnail.jpeg", b"\xff\xd8\xff\xd9")
        archive.writestr("word/document.xml", document)
        archive.writestr("word/comments.xml", '<w:comments xmlns:w="' + md.NS["w"] + '"><w:comment w:author="Anna"/>'
                                              '</w:comments>')
    return buf.getvalue()


def values(report: md.Report) -> dict[str, str]:
    return {f.name: f.value for f in report.fields}


# ---- Tests --------------------------------------------------------------------------------------------------------
def test_exif_fields_and_gps() -> None:
    report = md.Report("jpeg")
    md.add_exif(report, EXIF)
    v = values(report)
    assert v["Hersteller"] == "Canon" and v["Modell"] == "EOS 5D" and v["Software"] == "GIMP 2.10"
    assert v["Urheber"] == "Max Mustermann" and v["Aufgenommen"] == "2024:04:30 18:22:11"
    assert v["Belichtungszeit"] == "1/250 s" and v["Blende"] == "f/2.8" and v["Ausrichtung"] == "6 (90° rechts)"
    lat, lon = report.gps
    assert lat == pytest.approx(52 + 31 / 60 + 12 / 3600) and lon == pytest.approx(13 + 24 / 60 + 36 / 3600)
    assert md.osm_url(lat, lon).startswith("https://www.openstreetmap.org/?mlat=52.52")


def test_southern_western_hemisphere() -> None:
    assert md._dms([(33, 1), (51, 1), (0, 1)], "S") == pytest.approx(-33.85)
    assert md._dms([(70, 1), (0, 1), (0, 1)], "W") == -70


def test_jpeg_read_strip_verify(tmp_path: Path) -> None:
    path = tmp_path / "foto.jpg"
    path.write_bytes(jpeg())
    report = md.read(path)
    v = values(report)
    assert report.kind == "jpeg" and report.can_strip and report.gps
    assert v["xmp:CreatorTool"] == "Photoshop 25" and v["dc:creator"] == "Erika Beispiel"
    assert v["Autor"] == "IPTC Person" and v["JPEG-Kommentar"] == "geheimer Kommentar"
    assert v["Daten hinter dem Bildende"].startswith("7 Bytes")
    assert any("EXIF" in r for r in report.removes) and any("Ausrichtung" in k for k in report.keeps)
    clean = md.strip(path)
    assert clean.name == "foto_ohne_Metadaten.jpg" and path.read_bytes() == jpeg()      # Original unverändert
    data = clean.read_bytes()
    assert SCAN in data and data.endswith(b"\xff\xd9") and b"ICC_PROFILE" in data and b"JFIF" in data
    for secret in (b"Canon", b"Erika", b"IPTC Person", b"geheimer", b"TRAILER"):
        assert secret not in data
    assert md.verify(path, clean) == []
    assert md.strip(path).name == "foto_ohne_Metadaten (2).jpg"                      # nie überschreiben


def test_jpeg_eoi_detection_skips_stuffing_and_rst() -> None:
    import mmap  # noqa: F401 - bytes verhalten sich wie mmap
    data = jpeg(trailer=b"X" * 5)
    _segments, sos, eoi = md._jpeg_segments(data)
    assert data[sos:sos + 2] == b"\xff\xda" and eoi == len(data) - 5


def test_png_read_strip_verify(tmp_path: Path) -> None:
    path = tmp_path / "bild.png"
    path.write_bytes(png())
    report = md.read(path)
    v = values(report)
    assert v["Author"] == "Max Mustermann" and v["dc:creator"] == "Erika Beispiel" and v["Hersteller"] == "Canon"
    assert v["Zuletzt geändert (tIME)"] == "2024-05-01 12:00:00 UTC" and "Daten hinter IEND" in v
    clean = md.strip(path)
    data = clean.read_bytes()
    assert b"IHDR" in data and b"IDAT" in data and data.endswith(chunk(b"IEND", b""))
    assert b"Mustermann" not in data and b"eXIf" not in data and md.verify(path, clean) == []


def test_webp_read_strip_verify(tmp_path: Path) -> None:
    path = tmp_path / "bild.webp"
    path.write_bytes(webp())
    assert values(md.read(path))["Modell"] == "EOS 5D"
    clean = md.strip(path)
    data = clean.read_bytes()
    assert b"EXIF" not in data and b"XMP " not in data and data[20] & 0x0C == 0
    assert struct.unpack("<I", data[4:8])[0] == len(data) - 8 and md.verify(path, clean) == []


def test_pdf_read_strip_verify(tmp_path: Path) -> None:
    path = pdf(tmp_path)
    report = md.read(path)
    v = values(report)
    assert v["Autor"] == "Max Mustermann" and v["Erstellt mit"] == "Word" and v["PDF-Erzeuger"] == "Acrobat"
    assert v["Erstellt"] == "2024-01-31 14:22:33 +01:00" and v["Company"] == "ACME"
    assert v["dc:creator"] == "Erika Beispiel" and v["Seiten"] == "1" and v["Speicherstände"].startswith("2 ")
    clean = md.strip(path)
    assert md.verify(path, clean) == []
    data = clean.read_bytes()
    assert b"Mustermann" not in data and b"Erika" not in data and b"pypdf" not in data
    assert data.count(b"%%EOF") == 1


def test_pdf_date_formats() -> None:
    assert md.pdf_date("D:20240131142233Z") == "2024-01-31 14:22:33 UTC"
    assert md.pdf_date("D:2024") == "2024-01-01 00:00:00"
    assert md.pdf_date("kein Datum") == "kein Datum"


def test_office_read_strip_verify(tmp_path: Path) -> None:
    path = tmp_path / "brief.docx"
    path.write_bytes(docx())
    report = md.read(path)
    v = values(report)
    assert report.kind == "office"
    assert v["Autor"] == "Max Mustermann" and v["Zuletzt geändert von"] == "Erika Beispiel" and v["Revision"] == "7"
    assert v["Firma"] == "ACME GmbH" and v["Vorlage"] == "Geheim.dotm" and v["Bearbeitungszeit (Minuten)"] == "42"
    assert v["Projekt"] == "Falke" and "docProps/thumbnail.jpeg" in v["Vorschaubild"]
    assert v["Kommentar-Autoren"] == "Anna" and v["Autoren in der Änderungsverfolgung"] == "Tom"
    clean = md.strip(path)
    left = md.verify(path, clean)
    assert left == []
    with zipfile.ZipFile(clean) as archive:
        names = archive.namelist()
        assert "docProps/thumbnail.jpeg" not in names and "word/document.xml" in names
        assert b"thumbnail" not in archive.read("_rels/.rels")
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
    after = values(md.read(clean))
    assert after["Kommentar-Autoren"] == "Anna"                  # Inhalt bleibt – nur gemeldet


def test_markdown_and_text_export(tmp_path: Path) -> None:
    path = tmp_path / "foto.jpg"
    path.write_bytes(jpeg())
    report = md.read(path)
    text = md.to_markdown(report, "foto|1.jpg")
    assert text.startswith("### Metadaten: foto\\|1.jpg") and "| Gruppe | Feld | Wert |" in text
    assert "openstreetmap.org" in text and "Canon" in md.to_text(report)


def test_unsupported_broken_and_ntx_write_nothing(tmp_path: Path) -> None:
    note = tmp_path / "geheim.ntx"
    note.write_bytes(b"NTX1" + bytes(100))                  # verschlüsselte Notiz: nur Chiffretext
    with pytest.raises(md.MetadataError):
        md.read(note)
    with pytest.raises(md.MetadataError):
        md.strip(note)
    broken = tmp_path / "kaputt.jpg"
    broken.write_bytes(jpeg()[:40])
    md.read(broken)                                          # abgeschnitten: kein Absturz
    assert sorted(p.name for p in tmp_path.iterdir()) == ["geheim.ntx", "kaputt.jpg"]


def test_malformed_exif_does_not_crash() -> None:
    report = md.Report("jpeg")
    md.add_exif(report, b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 500) + b"\xff" * 30)
    md.add_exif(report, b"garbage")
    loop = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 0) + struct.pack("<I", 8)   # IFD zeigt auf sich
    md.add_exif(report, loop)
    assert any(f.value == "EXIF-Block nicht lesbar" for f in report.fields)


def test_tiff_read_only(tmp_path: Path) -> None:
    path = tmp_path / "scan.tif"
    path.write_bytes(EXIF)
    report = md.read(path)
    assert report.kind == "tiff" and not report.can_strip and values(report)["Hersteller"] == "Canon"
    with pytest.raises(md.MetadataError):
        md.strip(path)
