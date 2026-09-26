import hashlib
from pathlib import Path

import pytest

from notex.core import hashing, hexdata
from notex.core.hexdata import PagedFile, parse_hex_pattern, parse_offset, row_text, search_file


def test_paged_file_reads_across_pages(tmp_path: Path) -> None:
    data = bytes(range(256)) * 50
    path = tmp_path / "x.bin"
    path.write_bytes(data)
    paged = PagedFile(path, page_size=100, cache_pages=3)
    assert paged.size == len(data)
    assert paged.read(95, 20) == data[95:115]                 # über eine Seitengrenze
    assert paged.read(len(data) - 5, 100) == data[-5:]        # am Ende gekürzt
    assert paged.read(len(data), 10) == b"" and paged.read(-1, 4) == b""
    for offset in range(0, len(data), 97):
        assert paged.read(offset, 16) == data[offset:offset + 16]
    assert len(paged._pages) <= 3                             # Cache bleibt klein


def test_paged_file_does_not_keep_file_open(tmp_path: Path) -> None:
    path = tmp_path / "a.bin"
    path.write_bytes(b"abc" * 1000)
    paged = PagedFile(path)
    paged.read(0, 10)
    path.rename(tmp_path / "b.bin")                           # unter Windows scheitert das bei mmap/offenem Handle
    assert (tmp_path / "b.bin").exists()


def test_paged_file_refresh(tmp_path: Path) -> None:
    path = tmp_path / "a.bin"
    path.write_bytes(b"12345")
    paged = PagedFile(path)
    assert paged.read(0, 10) == b"12345"
    path.write_bytes(b"abcdefgh")
    paged.refresh()
    assert paged.size == 8 and paged.read(0, 10) == b"abcdefgh"


def test_row_text_layout() -> None:
    line = row_text(0x10, b"Hallo\x00\xff" + bytes(range(0x41, 0x4a)))
    assert line.startswith("00000010  48 61 6C 6C 6F 00 FF 41  42 43")
    assert line.endswith("Hallo..ABCDEFGHI")
    short = row_text(0, b"AB")
    assert short.startswith("00000000  41 42") and short.endswith("  AB")
    assert hexdata.offset_digits(100) == 8 and hexdata.offset_digits(5 * 1024 ** 3) == 10


@pytest.mark.parametrize("text,value", [
    ("1234", 1234), ("0x4D2", 1234), ("4d2h", 1234), ("$4D2", 1234), ("ff", 255), ("1_000", 1000), (" 0X10 ", 16),
])
def test_parse_offset(text: str, value: int) -> None:
    assert parse_offset(text) == value


@pytest.mark.parametrize("text", ["", "zz", "0xg1", "-5", "12k"])
def test_parse_offset_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_offset(text)


def test_parse_hex_pattern() -> None:
    assert parse_hex_pattern("DE AD be ef") == b"\xde\xad\xbe\xef"
    assert parse_hex_pattern("0xDE,0xAD") == b"\xde\xad"
    assert parse_hex_pattern("de:ad-be") == b"\xde\xad\xbe"
    for bad in ("", "ABC", "XY", "12 3"):
        with pytest.raises(ValueError):
            parse_hex_pattern(bad)


def test_search_across_chunks_wrap_and_case(tmp_path: Path) -> None:
    data = bytearray(b"\x00" * 10_000)
    data[4094:4100] = b"NEEDLE"                                # liegt über der Blockgrenze 4096
    data[20:26] = b"needle"
    path = tmp_path / "s.bin"
    path.write_bytes(bytes(data))
    assert search_file(path, b"NEEDLE", 0, chunk_size=4096) == 4094
    assert search_file(path, b"NEEDLE", 5000, chunk_size=4096) == 4094       # Umlauf an den Anfang
    assert search_file(path, b"NEEDLE", 5000, wrap=False, chunk_size=4096) is None
    assert search_file(path, b"NEEDLE", 0, ignore_case=True, chunk_size=4096) == 20
    assert search_file(path, b"\xde\xad", 0) is None
    assert search_file(path, b"NEEDLE", 0, cancelled=lambda: True) is None


def test_hash_file_all_algorithms_and_progress(tmp_path: Path) -> None:
    data = b"Notex" * 100_000
    path = tmp_path / "h.bin"
    path.write_bytes(data)
    seen = []
    digests = hashing.hash_file(path, progress=lambda done, total: seen.append((done, total)), chunk_size=65536)
    assert digests["sha256"] == hashlib.sha256(data).hexdigest()
    assert digests["md5"] == hashlib.md5(data).hexdigest()
    assert set(digests) == {"md5", "sha1", "sha256", "sha512"}
    assert seen[-1] == (len(data), len(data))
    with pytest.raises(hashing.Cancelled):
        hashing.hash_file(path, cancelled=lambda: True)


def test_compare_digest_formats() -> None:
    digests = {"md5": "d41d8cd98f00b204e9800998ecf8427e",
               "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
    sha = digests["sha256"]
    assert hashing.match_digest(sha.upper(), digests) == "sha256"
    assert hashing.match_digest(f"SHA256: {sha}", digests) == "sha256"
    assert hashing.match_digest(f"{sha}  ubuntu.iso", digests) == "sha256"                  # sha256sum-Ausgabe
    assert hashing.match_digest(":".join(sha[i:i + 2] for i in range(0, 64, 2)), digests) == "sha256"
    assert hashing.match_digest("d41d8cd98f00b204e9800998ecf8427f", digests) is None       # ein Zeichen anders
    assert hashing.match_digest("", digests) is None and hashing.match_digest("kein hash", digests) is None
    assert hashing.expected_algorithm(sha) == "sha256" and hashing.expected_algorithm("abc") is None


def test_hashing_ntx_only_sees_ciphertext(tmp_path: Path) -> None:
    """.ntx-Regel: gehasht wird die Datei auf der Platte (Geheimtext), es gibt keinen Klartext-Pfad."""
    from notex.core import crypto_notes
    path = tmp_path / "geheim.ntx"
    secret = "streng geheimer Klartext"
    key = crypto_notes.new_key("passwort-123", crypto_notes.KDF_SCRYPT, (10, 8, 1))
    path.write_bytes(crypto_notes.seal(secret, key))
    raw = path.read_bytes()
    assert secret.encode() not in raw
    assert hashing.hash_file(path)["sha256"] == hashlib.sha256(raw).hexdigest()


def test_copy_formats_and_interpretation() -> None:
    assert hexdata.to_base64(b"Notex") == "Tm90ZXg="
    c = hexdata.to_c_array(bytes(range(14)), "blob")
    assert c.startswith("unsigned char blob[14] = {\n    0x00, 0x01") and c.rstrip().endswith("0x0D\n};")
    rows = hexdata.interpret(b"\x01\x02\x03\x04\x05")
    assert rows[0] == ("u8", 1, 1)
    assert rows[1] == ("u16", 0x0201, 0x0102)
    assert rows[2] == ("u32", 0x04030201, 0x01020304)
    assert rows[3] == ("u64", None, None)                      # nur 5 Bytes da
    assert hexdata.selection_value(b"\x34\x12") == "u16 LE 4.660 · BE 13.330"
    assert hexdata.selection_value(b"\xff") == "u8 255" and hexdata.selection_value(b"abc") == ""
