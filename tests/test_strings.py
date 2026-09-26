from pathlib import Path

import pytest

from notex.core import strings as st
from notex.core.strings import classify, extract_bytes, extract_file


def texts(found):
    return [(f.offset, f.encoding, f.text) for f in found]


def test_ascii_and_utf16_with_offsets() -> None:
    data = b"\x00\x01Hello World\x00\x02" + "Grüße?".encode("utf-16-le")[:0] + "Pfad".encode("utf-16-le") + b"\xff" + "BE-Text".encode("utf-16-be")
    found = extract_bytes(data, 4, ("ascii", "utf16le", "utf16be"))
    assert (2, "ascii", "Hello World") in texts(found)
    assert (15, "utf16le", "Pfad") in texts(found)
    be = [f for f in found if f.encoding == "utf16be"]
    assert be and be[0].text == "BE-Text" and be[0].length == 14


def test_min_length_and_tabs() -> None:
    assert texts(extract_bytes(b"abc\x00abcd\x00a\tbc", 4, ("ascii",))) == [(4, "ascii", "abcd"), (9, "ascii", "a\tbc")]
    assert extract_bytes(b"abc", 4, ("ascii",)) == []


def test_chunk_boundaries_ascii_and_odd_utf16(tmp_path: Path) -> None:
    payload = b"\x00" * 7 + b"ABCDEFGHIJKLMNOP" + b"\x00" * 5 + "unicode-string".encode("utf-16-le") + b"\x01"
    path = tmp_path / "blob.bin"
    path.write_bytes(payload)
    for size in (3, 4, 5, 8, 13):                               # kleine Blöcke: Grenzen liegen mitten in Strings
        found, truncated = extract_file(path, 4, ("ascii", "utf16le"), chunk_size=size)
        assert not truncated
        assert (7, "ascii", "ABCDEFGHIJKLMNOP") in texts(found), size
        assert (28, "utf16le", "unicode-string") in texts(found), size
        assert len([f for f in found if f.encoding == "ascii" and f.text.startswith("ABC")]) == 1


def test_limit_progress_cancel(tmp_path: Path) -> None:
    path = tmp_path / "many.bin"
    path.write_bytes(b"\x00".join(b"wort%04d" % i for i in range(500)))
    found, truncated = extract_file(path, 4, ("ascii",), limit=100)
    assert truncated and len(found) == 100
    seen = []
    extract_file(path, 4, ("ascii", "utf16le"), chunk_size=512, progress=lambda d, t: seen.append((d, t)))
    assert seen[-1][0] == seen[-1][1]
    with pytest.raises(st.Cancelled):
        extract_file(path, 4, ("ascii",), cancelled=lambda: True)


@pytest.mark.parametrize("text,category", [
    ("http://evil.example.com/payload.bin", "url"),
    ("Kontakt: admin@example.org", "email"),
    ("connect 192.168.10.254:445", "ip"),
    ("version 1.2.3.4567", None),                              # keine IP (Oktett > 255)
    ("C:\\Windows\\System32\\cmd.exe", "path"),
    ("\\\\server\\share\\x", "path"),
    ("/usr/lib/x86_64-linux-gnu/libc.so.6", "path"),
    ("HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "registry"),
    ("SOFTWARE\\Microsoft\\Windows NT", "registry"),
    ("TVqQAAMAAAAEAAAA//8AALgAAAAAAAAAQAAAAAAAAAA=", "base64"),
    ("AAAAAAAAAAAAAAAAAAAAAAAA", None),
    ("Hello World", None),
])
def test_classify(text: str, category) -> None:
    assert classify(text) == category


def test_export_format() -> None:
    items = extract_bytes(b"\x00\x00Hallo\x00", 4, ("ascii",))
    assert st.to_text_export(items) == "0x00000002\tASCII\tHallo\n"


def test_ntx_only_ciphertext(tmp_path: Path) -> None:
    """.ntx-Regel: Strings liest nur die Datei – der Klartext einer verschlüsselten Notiz taucht nie auf."""
    from notex.core import crypto_notes
    secret = "Streng geheimes Passwort 12345"
    path = tmp_path / "geheim.ntx"
    path.write_bytes(crypto_notes.seal(secret, crypto_notes.new_key("pw", crypto_notes.KDF_SCRYPT, (10, 8, 1))))
    found, _ = extract_file(path, 4, ("ascii", "utf16le", "utf16be"))
    assert all("geheim" not in f.text and "12345" not in f.text for f in found)
