"""Tests für lokale Umwandlungen (core/convert.py) – ohne Qt."""
from __future__ import annotations

import base64

import pytest

from notex.core import convert


def test_base64_roundtrip_and_preview():
    data = b"Hallo Welt"
    enc = convert.encode_base64(data)
    assert convert.decode_base64(enc) == data
    assert convert.bytes_preview(data) == "Hallo Welt"
    # Binärdaten → Hex
    assert convert.bytes_preview(b"\x00\x01\xff") == "0001ff"


def test_base32_hex_url():
    assert convert.decode_base32(convert.encode_base32(b"abc")) == b"abc"
    assert convert.decode_hex("48 65:6c6c6f") == b"Hello"
    assert convert.url_decode("a%20b%2Fc") == "a b/c"
    assert convert.url_encode("a b/c") == "a%20b%2Fc"


def test_jwt_decode():
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(b'{"sub":"1","exp":1700000000}').decode().rstrip("=")
    h, p, note = convert.jwt_decode(f"{header}.{payload}.sig")
    assert h["alg"] == "HS256"
    assert p["sub"] == "1"
    assert "NICHT" in note
    times = dict(convert.jwt_times(p))
    assert "Läuft ab" in times


def test_jwt_invalid():
    with pytest.raises(ValueError):
        convert.jwt_decode("nur.zwei")


def test_timestamp():
    utc, local = convert.timestamp_to_dates(1700000000)
    assert utc.startswith("2023-11-14") and "UTC" in utc
    # Millisekunden werden erkannt
    utc_ms, _ = convert.timestamp_to_dates(1700000000000)
    assert utc_ms.startswith("2023-11-14")


def test_number_bases():
    out = convert.number_bases(255)
    assert out["Hexadezimal"] == "0xff"
    assert out["Binär"] == "0b11111111"
    assert out["Bits"] == "11111111"
    assert convert.parse_int("0xff") == 255
    assert convert.parse_int("0b1010") == 10


def test_hex_color():
    r, g, b, norm = convert.hex_color("#1e1e1e")
    assert (r, g, b) == (30, 30, 30)
    assert norm == "#1e1e1e"
    # Kurzform
    assert convert.hex_color("#fff")[:3] == (255, 255, 255)


def test_user_agent():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0 Safari/537.36"
    parsed = convert.parse_user_agent(ua)
    assert "Windows 10" in parsed["System"]
    assert "Chrome" in parsed["Browser"]
    assert parsed["Gerät"] == "Desktop"


def test_hashes_including_ntlm():
    assert convert.hash_word("", "md5") == "d41d8cd98f00b204e9800998ecf8427e"
    assert convert.hash_word("abc", "sha1") == "a9993e364706816aba3e25717850c26c9cd0d89d"
    # NTLM von "password" ist ein bekannter Wert
    assert convert.ntlm("password") == "8846f7eaee8fb117ad06bdd830b7586c"
    assert convert.hash_word("password", "ntlm") == "8846f7eaee8fb117ad06bdd830b7586c"


def test_hash_word_unknown():
    with pytest.raises(ValueError):
        convert.hash_word("x", "crc32")
