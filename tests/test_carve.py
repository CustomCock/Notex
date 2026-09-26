import bz2
import gzip
import io
import lzma
import os
import random
import sqlite3
import struct
import tarfile
import zipfile
import zlib
from pathlib import Path

from notex.core import carve


# ---- Beispieldateien (selbst erzeugt) ---------------------------------------------------------------------
def png(width=2, height=2) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg() -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00"
    return b"\xff\xd8" + app0 + sos + b"\x12\x34\xff\x00\x56" + b"\xff\xd9"


def gif() -> bytes:
    return (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
            b"\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b")


def bmp() -> bytes:
    pixels = b"\x00\x00\xff\x00" * 4
    header = b"BM" + struct.pack("<IHHI", 14 + 40 + len(pixels), 0, 0, 54)
    dib = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 32, 0, len(pixels), 2835, 2835, 0, 0)
    return header + dib + pixels


def zip_bytes(names=("a.txt",)) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, "Inhalt " * 20)
    return buffer.getvalue()


def pe() -> bytes:
    dos = bytearray(b"MZ" + b"\x00" * 62)
    struct.pack_into("<I", dos, 0x3C, 0x40)
    coff = b"PE\x00\x00" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 0, 0x22)
    section = b".text\x00\x00\x00" + struct.pack("<IIIIIIHHI", 0x10, 0x1000, 0x40, 0x200, 0, 0, 0, 0, 0x60000020)
    body = bytes(dos) + coff + section
    return body + b"\x00" * (0x200 - len(body)) + b"\xc3" * 0x40      # Sektion endet bei 0x240


def elf64() -> bytes:
    shoff, shnum, shentsize = 64, 2, 64
    header = (b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + struct.pack("<HHIQQQIHHHHHH", 2, 0x3E, 1, 0, 0, shoff, 0, 64, 0, 0,
                                                                     shentsize, shnum, 0))
    return header + b"\x00" * (shentsize * shnum)


def pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def pcap() -> bytes:
    head = b"\xd4\xc3\xb2\xa1" + struct.pack("<HHiIII", 2, 4, 0, 0, 65535, 1)
    packet = b"\x00" * 42
    return head + struct.pack("<IIII", 1, 0, len(packet), len(packet)) + packet


def tar_bytes() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as t:
        data = b"hallo tar"
        info = tarfile.TarInfo("x.txt")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def sqlite_bytes(tmp_path: Path) -> bytes:
    db = tmp_path / "t.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table t(x)")
    con.execute("insert into t values ('eins')")
    con.commit()
    con.close()
    return db.read_bytes()


def found(path, **kw):
    hits, truncated = carve.scan(path, **kw)
    assert not truncated
    return [(h.offset, h.key, h.size) for h in hits]


# ---- Tests -------------------------------------------------------------------------------------------------
def test_zip_after_jpeg_eoi(tmp_path: Path) -> None:
    image, archive = jpeg(), zip_bytes()
    path = tmp_path / "urlaub.jpg"
    path.write_bytes(image + archive)
    assert found(path) == [(0, "jpeg", len(image)), (len(image), "zip", len(archive))]


def test_data_after_png_iend(tmp_path: Path) -> None:
    image = png()
    path = tmp_path / "bild.png"
    path.write_bytes(image + b"GEHEIME NACHRICHT hinter IEND")
    hits, _ = carve.scan(path)
    assert [(h.offset, h.key) for h in hits] == [(0, "png"), (len(image), "trailer")]
    assert hits[1].size == len(b"GEHEIME NACHRICHT hinter IEND") and "PNG" in hits[1].name


def test_padding_after_end_is_not_a_trailer(tmp_path: Path) -> None:
    path = tmp_path / "pad.png"
    path.write_bytes(png() + b"\x00" * 512)
    assert [h.key for h in carve.scan(path)[0]] == ["png"]


def test_many_formats_in_one_container(tmp_path: Path) -> None:
    rng = random.Random(7)
    noise = lambda n: bytes(rng.getrandbits(8) for _ in range(n)).replace(b"MZ", b"mz").replace(b"BM", b"bm")
    parts = [("png", png()), ("jpeg", jpeg()), ("gif", gif()), ("bmp", bmp()), ("zip", zip_bytes()),
             ("gzip", gzip.compress(b"x" * 1000)), ("bzip2", bz2.compress(b"y" * 1000)),
             ("xz", lzma.compress(b"z" * 1000)), ("pe", pe()), ("elf", elf64()), ("pdf", pdf()),
             ("pcap", pcap()), ("tar", tar_bytes()), ("sqlite", sqlite_bytes(tmp_path))]
    blob, expected = bytearray(), []
    for key, data in parts:
        blob += noise(37)
        # TAR: Kopf 512 + Daten 512 + Ende-Markierung 1024; tarfile füllt danach mit Nullen auf 10 KB auf
        size = 2048 if key == "tar" else len(data)
        expected.append((len(blob), key, size))
        blob += data
    blob += noise(37)
    path = tmp_path / "container.bin"
    path.write_bytes(bytes(blob))
    hits = [h for h in carve.scan(path)[0] if h.key != "trailer"]
    got = {(h.offset, h.key): h.size for h in hits}
    for offset, key, size in expected:
        assert got.get((offset, key)) == size, (key, offset, got.get((offset, key)))


def test_false_positives_rejected(tmp_path: Path) -> None:
    junk = (b"MZ" + b"\x00" * 100 + b"BM\x10\x00\x00\x00" + b"BZh9xxxx" + b"PK\x03\x04\xff\xff" + b"%PDF-x.y"
            + b"\x1f\x8b\x08\xff" + b"\x7fELF\x09" + b"GIF89a\x00\x00\x00\x00" + b"7z\xbc\xaf\x27\x1c\x09")
    path = tmp_path / "junk.bin"
    path.write_bytes(os.urandom(64) + junk + os.urandom(64))
    assert found(path) == []


def test_signature_across_chunk_boundary(tmp_path: Path) -> None:
    archive = zip_bytes()
    path = tmp_path / "grenze.bin"
    path.write_bytes(b"\x00" * 1021 + archive)                  # PK\x03\x04 liegt über der Grenze bei 1024
    assert found(path, chunk_size=1024) == [(1021, "zip", len(archive))]


def test_zip_based_types_are_refined(tmp_path: Path) -> None:
    docx = zip_bytes(("[Content_Types].xml", "word/document.xml"))
    path = tmp_path / "anhang.bin"
    path.write_bytes(b"\x01" * 50 + docx)
    hits, _ = carve.scan(path)
    assert (hits[0].key, hits[0].ext) == ("docx", ".docx")


def test_gzip_size_exact_with_following_data(tmp_path: Path) -> None:
    stream = gzip.compress(b"hallo " * 500)
    path = tmp_path / "g.bin"
    path.write_bytes(stream + b"danach kommt etwas anderes, das kein gzip ist")
    assert carve.scan(path)[0][0].size == len(stream)


def test_extract_never_overwrites_and_is_valid(tmp_path: Path) -> None:
    image, archive = jpeg(), zip_bytes(("nachricht.txt",))
    path = tmp_path / "urlaub.jpg"
    path.write_bytes(image + archive)
    hits, _ = carve.scan(path)
    zip_hit = next(h for h in hits if h.key == "zip")
    first = carve.extract(path, zip_hit, hits)
    second = carve.extract(path, zip_hit, hits)
    assert first.parent.name == "urlaub.jpg_extrahiert" and first != second and second.name.endswith("-2.zip")
    assert zipfile.ZipFile(first).namelist() == ["nachricht.txt"]
    assert first.read_bytes() == archive and os.access(first, os.R_OK)


def test_unknown_size_extracts_until_next_hit(tmp_path: Path) -> None:
    rar = b"Rar!\x1a\x07\x01\x00" + b"\x55" * 100
    image = png()
    path = tmp_path / "x.bin"
    path.write_bytes(rar + image)
    hits, _ = carve.scan(path)
    rar_hit = next(h for h in hits if h.key == "rar")
    assert rar_hit.size is None and carve.region_size(rar_hit, hits, path.stat().st_size) == len(rar)


def test_cancel_and_progress(tmp_path: Path) -> None:
    path = tmp_path / "p.bin"
    path.write_bytes(os.urandom(10_000) + png())
    seen = []
    carve.scan(path, chunk_size=4096, progress=lambda d, t: seen.append((d, t)))
    assert seen[-1][0] == seen[-1][1]
    try:
        carve.scan(path, cancelled=lambda: True)
    except carve.Cancelled:
        pass
    else:
        raise AssertionError("kein Abbruch")
