import struct
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from notex.core import filetype as ft
from notex.core.filetype import detect, detect_file, looks_binary, mismatch


def zip_bytes(*names: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name in names:
            z.writestr(name, "x")
    return buffer.getvalue()


def pe_bytes() -> bytes:
    head = bytearray(b"MZ" + b"\x00" * 126)
    struct.pack_into("<I", head, 60, 64)
    head[64:68] = b"PE\x00\x00"
    return bytes(head)


@pytest.mark.parametrize("head,name,key", [
    (b"\x89PNG\r\n\x1a\n....", "x.png", "png"),
    (b"\xff\xd8\xff\xe0\x00\x10JFIF", "x.jpg", "jpeg"),
    (b"GIF89a....", "x.gif", "gif"),
    (b"%PDF-1.7\n", "x.pdf", "pdf"),
    (b"Rar!\x1a\x07\x01\x00", "x.rar", "rar"),
    (b"7z\xbc\xaf\x27\x1c\x00\x04", "x.7z", "7z"),
    (b"\x1f\x8b\x08\x00", "x.gz", "gzip"),
    (b"\x7fELF\x02\x01\x01", "prog", "elf"),
    (b"\xcf\xfa\xed\xfe\x07\x00\x00\x01", "prog", "macho"),
    (b"SQLite format 3\x00....", "x.db", "sqlite"),
    (b"NOTEXENC\x01\x01....", "geheim.ntx", "ntx"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "x.webp", "webp"),
    (b"BM\x00\x00\x00\x00", "x.bmp", "bmp"),
    (b"Hallo Welt\nZeile 2\n", "x.txt", "text"),
    (b"", "leer.txt", "empty"),
    (b"\x00\x01\x02\x03\xff\xfe\x00\x00", "x.bin", "binary"),
])
def test_signatures(head: bytes, name: str, key: str) -> None:
    assert detect(head, name).key == key


def test_pe_and_zip_variants() -> None:
    assert detect(pe_bytes(), "setup.exe").key == "pe"
    assert detect(zip_bytes("[Content_Types].xml", "word/document.xml"), "brief.docx").key == "docx"
    assert detect(zip_bytes("[Content_Types].xml", "xl/workbook.xml"), "tabelle.zip").key == "xlsx"
    assert detect(zip_bytes("META-INF/MANIFEST.MF", "a.class"), "tool.jar").key == "jar"
    assert detect(zip_bytes("AndroidManifest.xml", "classes.dex"), "app.bin").key == "apk"
    assert detect(zip_bytes("a.txt"), "archiv.zip").key == "zip"


def test_looks_binary() -> None:
    assert not looks_binary("Grüße, Ümläute – UTF-8".encode("utf-8"))
    assert not looks_binary("text".encode("utf-16"))           # BOM → Text
    assert looks_binary(b"abc\x00def")
    assert looks_binary(bytes(range(0, 32)) * 4)


def test_mismatch_warnings() -> None:
    assert mismatch("bild.png", ft.PNG) is None
    assert "PNG-Bild" in mismatch("bild.jpg", ft.PNG)
    assert "Windows-Programm" in mismatch("rechnung.pdf", ft.PE)      # klassische Tarnung
    assert mismatch("notiz.txt", ft.TEXT) is None
    assert mismatch("bericht.docx", ft.DOCX) is None
    assert mismatch("prog", ft.ELF) is None
    assert mismatch("x.png", ft.TEXT) is not None                    # .png mit Textinhalt
    assert mismatch("daten.bin", ft.BINARY) is None


def test_detect_file(tmp_path: Path) -> None:
    (tmp_path / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    assert detect_file(tmp_path / "a.png").key == "png"
    assert detect_file(tmp_path / "fehlt").key == "binary"


def test_block_g_signatures() -> None:
    tar = bytearray(512)
    tar[0:8] = b"datei.tx"
    tar[257:263] = b"ustar\x00"
    assert detect(bytes(tar), "archiv.tar").key == "tar"
    assert detect(b"\xd4\xc3\xb2\xa1\x02\x00\x04\x00" + b"\x00" * 16, "a.pcap").key == "pcap"
    assert detect(b"\xa1\xb2\x3c\x4d\x00\x02\x00\x04" + b"\x00" * 16, "a.pcap").key == "pcap"   # Nanosekunden, BE
    assert detect(b"\x0a\x0d\x0d\x0a\x1c\x00\x00\x00\x4d\x3c\x2b\x1a", "a.pcapng").key == "pcapng"
    assert detect(b"ElfFile\x00" + b"\x00" * 40, "System.evtx").key == "evtx"
    assert mismatch("mitschnitt.txt", ft.PCAP) is not None and mismatch("a.cap", ft.PCAP) is None
