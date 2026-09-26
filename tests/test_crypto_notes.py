"""Tests für verschlüsselte Notizen. Schnelle KDF-Parameter, damit die Suite zügig bleibt;
die Standardparameter werden einmal separat geprüft."""
import struct

import pytest

from notex.core import crypto_notes as ntx
from notex.core.crypto_notes import (HEADER_LEN, KDF_ARGON2ID, KDF_SCRYPT, CorruptFile, DecryptionFailed,
                                     UnsupportedFormat, new_key, open_note, open_with_key, parse_header, seal)

FAST_ARGON = (KDF_ARGON2ID, (1024, 1, 1))
FAST_SCRYPT = (KDF_SCRYPT, (10, 8, 1))
TEXT = "Geheime Notiz – Ümläute, Emoji 🔐 und\nmehrere Zeilen.\n"


def kdfs():
    params = [FAST_SCRYPT]
    if ntx.argon2_available():
        params.insert(0, FAST_ARGON)
    return params


@pytest.mark.parametrize("kdf,params", kdfs())
def test_roundtrip(kdf, params) -> None:
    key = new_key("richtig", kdf, params)
    data = seal(TEXT, key)
    assert TEXT.encode() not in data and b"Geheime" not in data
    text, key2 = open_note(data, "richtig")
    assert text == TEXT and key2.key == key.key
    assert open_with_key(data, key) == TEXT


@pytest.mark.parametrize("kdf,params", kdfs())
def test_wrong_password(kdf, params) -> None:
    data = seal(TEXT, new_key("richtig", kdf, params))
    with pytest.raises(DecryptionFailed):
        open_note(data, "falsch")
    with pytest.raises(DecryptionFailed):
        open_note(data, "Richtig")


def test_tampering_any_byte_is_detected() -> None:
    key = new_key("pw", *FAST_SCRYPT)
    data = seal(TEXT, key)
    # jedes Byte in Salt, Nonce, Chiffretext und Tag
    for index in list(range(22, HEADER_LEN)) + [HEADER_LEN, HEADER_LEN + 5, len(data) - 1]:
        broken = bytearray(data)
        broken[index] ^= 0x01
        with pytest.raises(DecryptionFailed):
            open_note(bytes(broken), "pw")
    # KDF-Parameter geändert (bleibt in den Grenzen): anderer Schlüssel bzw. AAD-Fehler
    broken = bytearray(data)
    struct.pack_into(">I", broken, 14, 9)   # r = 9 statt 8
    with pytest.raises(DecryptionFailed):
        open_note(bytes(broken), "pw")
    # abgeschnitten / angehängt
    with pytest.raises(DecryptionFailed):
        open_note(data[:-1], "pw")
    with pytest.raises(DecryptionFailed):
        open_note(data + b"x", "pw")


def test_new_nonce_every_save_same_salt() -> None:
    key = new_key("pw", *FAST_SCRYPT)
    a, b = seal(TEXT, key), seal(TEXT, key)
    assert a != b
    ha, hb = parse_header(a), parse_header(b)
    assert ha.nonce != hb.nonce and ha.salt == hb.salt
    assert new_key("pw", *FAST_SCRYPT).salt != key.salt           # neues Passwort/neue Datei: neues Salt


def test_format_version_and_kdf_checks() -> None:
    data = bytearray(seal(TEXT, new_key("pw", *FAST_SCRYPT)))
    future = bytearray(data)
    future[8] = 2
    with pytest.raises(UnsupportedFormat):
        open_note(bytes(future), "pw")
    unknown_kdf = bytearray(data)
    unknown_kdf[9] = 7
    with pytest.raises(UnsupportedFormat):
        open_note(bytes(unknown_kdf), "pw")
    with pytest.raises(CorruptFile):
        open_note(b"NOTEXENC", "pw")                                   # zu kurz
    with pytest.raises(CorruptFile):
        open_note(b"Klartext statt Chiffre" * 5, "pw")                 # falsches Magic
    with pytest.raises(CorruptFile):
        open_note(b"", "pw")


def test_absurd_parameters_rejected_before_kdf_runs() -> None:
    data = bytearray(seal(TEXT, new_key("pw", *FAST_SCRYPT)))
    huge = bytearray(data)
    struct.pack_into(">I", huge, 10, 40)                               # scrypt N = 2^40
    with pytest.raises(CorruptFile):
        open_note(bytes(huge), "pw")
    header = bytearray(data)
    header[9] = KDF_ARGON2ID
    struct.pack_into(">III", header, 10, 64 * 1024 * 1024, 3, 4)       # Argon2id mit 64 GiB
    with pytest.raises(CorruptFile):
        open_note(bytes(header), "pw")


def test_password_normalization_and_empty() -> None:
    nfc, nfd = "Käse", "Käse"
    data = seal(TEXT, new_key(nfc, *FAST_SCRYPT))
    assert open_note(data, nfd)[0] == TEXT
    with pytest.raises(ValueError):
        new_key("", *FAST_SCRYPT)


def test_open_with_key_rejects_rekeyed_file() -> None:
    key = new_key("pw", *FAST_SCRYPT)
    other = seal(TEXT, new_key("anderes", *FAST_SCRYPT))
    with pytest.raises(DecryptionFailed):
        open_with_key(other, key)


def test_key_is_not_in_repr() -> None:
    key = new_key("pw", *FAST_SCRYPT)
    assert key.key.hex() not in repr(key) and "key=" not in repr(key)


def test_default_parameters() -> None:
    key = new_key("pw")
    header = parse_header(seal("x", key))
    if ntx.argon2_available():
        assert header.kdf == KDF_ARGON2ID and header.params == ntx.ARGON2_DEFAULT
        assert "Argon2id (64 MiB" in ntx.describe(header)
    else:
        assert header.kdf == KDF_SCRYPT and header.params == ntx.SCRYPT_DEFAULT
    assert len(header.salt) == 16 and len(header.nonce) == 12
