import codecs
from pathlib import Path

from textbaum.core.encoding import decode_bytes, detect_encoding, detect_eol, encode_text, read_text_file


def test_detect_utf8_bom() -> None:
    assert detect_encoding(codecs.BOM_UTF8 + "hallo".encode("utf-8")) == "utf-8-sig"


def test_detect_utf8_without_bom() -> None:
    assert detect_encoding("Grüße ✓".encode("utf-8")) == "utf-8"


def test_detect_cp1252_fallback() -> None:
    assert detect_encoding("Grüße".encode("cp1252")) == "cp1252"


def test_empty_file_is_utf8_lf() -> None:
    tf = decode_bytes(b"")
    assert (tf.text, tf.encoding, tf.eol) == ("", "utf-8", "\n")


def test_eol_detection() -> None:
    assert detect_eol("a\r\nb\r\n") == "\r\n"
    assert detect_eol("a\nb\n") == "\n"
    assert detect_eol("kein Umbruch") == "\n"


def test_decode_normalizes_line_endings() -> None:
    tf = decode_bytes(b"eins\r\nzwei\r\n")
    assert tf.text == "eins\nzwei\n"
    assert tf.eol == "\r\n"


def test_roundtrip_keeps_encoding_and_eol(tmp_path: Path) -> None:
    original = codecs.BOM_UTF8 + "Zeile 1\r\nZeile 2 ä\r\n".encode("utf-8")
    path = tmp_path / "f.txt"
    path.write_bytes(original)
    tf = read_text_file(path)
    assert encode_text(tf.text, tf.encoding, tf.eol) == original


def test_roundtrip_cp1252(tmp_path: Path) -> None:
    original = "Äpfel\nBirnen\n".encode("cp1252")
    tf = decode_bytes(original)
    assert tf.encoding == "cp1252"
    assert encode_text(tf.text, tf.encoding, tf.eol) == original


def test_cp1252_unencodable_char_does_not_raise() -> None:
    data = encode_text("Smiley 😀", "cp1252", "\n")
    assert data.startswith(b"Smiley ")
    assert b"&#128512;" in data
