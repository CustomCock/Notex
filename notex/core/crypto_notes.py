"""Verschlüsselte Notizen (.ntx). Ohne Qt. KEINE eigene Kryptografie – nur Bausteine aus `cryptography`:

- Schlüsselableitung: Argon2id (RFC 9106), Fallback scrypt, wenn die OpenSSL-Version kein Argon2 kann
- Verschlüsselung: AES-256-GCM (authentifiziert), 96-bit-Nonce, bei JEDEM Speichern neu zufällig
- Der komplette Header (Magic, Version, KDF, Parameter, Salt, Nonce) ist Associated Data: jede Änderung
  daran lässt die Entschlüsselung scheitern, genau wie eine Änderung am Chiffretext

Dateiformat v1 (alle Zahlen Big Endian):
  Offset Länge  Inhalt
  0      8      Magic b"NOTEXENC"
  8      1      Formatversion = 1
  9      1      KDF: 1 = Argon2id, 2 = scrypt
  10     4      Argon2id: Speicher in KiB   | scrypt: log2(N)
  14     4      Argon2id: Iterationen        | scrypt: r
  18     4      Argon2id: Lanes              | scrypt: p
  22     16     Salt (pro Datei, neu bei Passwortwechsel)
  38     12     Nonce (neu bei jedem Speichern)
  50     …      AES-256-GCM-Chiffretext des UTF-8-Texts, 16-Byte-Tag am Ende

Der Schlüssel wird einmal pro Entsperren abgeleitet (KeyState) und nur im Speicher gehalten; jedes Speichern
verwendet denselben Schlüssel mit neuer Zufalls-Nonce. Beim Lesen werden KDF-Parameter auf sinnvolle Grenzen
geprüft, bevor die KDF läuft – eine manipulierte Datei kann so nicht 64 GB RAM anfordern.
"""
from __future__ import annotations

import os
import struct
import unicodedata
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from notex import APP_NAME

MAGIC = b"NOTEXENC"
FORMAT_VERSION = 1
KDF_ARGON2ID = 1
KDF_SCRYPT = 2
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32
TAG_LEN = 16
_HEADER = struct.Struct(">8sBBIII16s12s")
HEADER_LEN = _HEADER.size   # 50
SUFFIX = ".ntx"

# Standard: RFC 9106, zweite Empfehlung (64 MiB, 3 Durchläufe, 4 Lanes)
ARGON2_DEFAULT = (64 * 1024, 3, 4)
SCRYPT_DEFAULT = (17, 8, 1)          # N = 2^17, r = 8, p = 1 (≈ 128 MiB)
# Grenzen beim Lesen – großzügig genug für stärkere Einstellungen, klein genug gegen Missbrauch
ARGON2_LIMITS = ((8, 1024 * 1024), (1, 64), (1, 64))      # Speicher 8 KiB … 1 GiB
SCRYPT_LIMITS = ((10, 22), (1, 32), (1, 16))


class NtxError(Exception):
    """Basis aller Fehler rund um .ntx-Dateien."""


class DecryptionFailed(NtxError):
    """Falsches Passwort oder die Datei wurde verändert – GCM kann beides nicht unterscheiden."""


class CorruptFile(NtxError):
    """Keine gültige .ntx-Datei (zu kurz, falsches Magic, unsinnige Parameter)."""


class UnsupportedFormat(NtxError):
    """Formatversion oder KDF, die diese Notex-Version nicht kennt."""


@dataclass(frozen=True)
class Header:
    version: int
    kdf: int
    params: tuple[int, int, int]
    salt: bytes
    nonce: bytes

    def pack(self) -> bytes:
        return _HEADER.pack(MAGIC, self.version, self.kdf, *self.params, self.salt, self.nonce)


@dataclass(frozen=True, repr=False)
class KeyState:
    """Abgeleiteter Schlüssel einer entsperrten Notiz. repr=False: der Schlüssel landet nie in Logs/Tracebacks."""
    kdf: int
    params: tuple[int, int, int]
    salt: bytes
    key: bytes

    def __repr__(self) -> str:
        return f"KeyState(kdf={self.kdf}, params={self.params})"


def argon2_available() -> bool:
    try:
        from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
        Argon2id(salt=b"\0" * 16, length=32, iterations=1, lanes=1, memory_cost=8).derive(b"x")
        return True
    except (ImportError, UnsupportedAlgorithm):
        return False


def _normalize(password: str) -> bytes:
    if not password:
        raise ValueError("Leeres Passwort")
    return unicodedata.normalize("NFC", password).encode("utf-8")


def _check_params(kdf: int, params: tuple[int, int, int]) -> None:
    limits = ARGON2_LIMITS if kdf == KDF_ARGON2ID else SCRYPT_LIMITS if kdf == KDF_SCRYPT else None
    if limits is None:
        raise UnsupportedFormat(f"Unbekannte Schlüsselableitung {kdf}")
    for value, (low, high) in zip(params, limits):
        if not low <= value <= high:
            raise CorruptFile("Unzulässige KDF-Parameter")
    if kdf == KDF_ARGON2ID and params[0] < 8 * params[2]:
        raise CorruptFile("Unzulässige KDF-Parameter")


def derive_key(password: str, kdf: int, params: tuple[int, int, int], salt: bytes) -> KeyState:
    _check_params(kdf, params)
    secret = _normalize(password)
    if kdf == KDF_ARGON2ID:
        try:
            from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
        except ImportError as error:
            raise UnsupportedFormat("Argon2id wird von dieser Installation nicht unterstützt") from error
        memory, iterations, lanes = params
        try:
            key = Argon2id(salt=salt, length=KEY_LEN, iterations=iterations, lanes=lanes, memory_cost=memory).derive(secret)
        except UnsupportedAlgorithm as error:
            raise UnsupportedFormat("Argon2id wird von dieser Installation nicht unterstützt") from error
    else:
        log2n, r, p = params
        key = Scrypt(salt=salt, length=KEY_LEN, n=2 ** log2n, r=r, p=p).derive(secret)
    return KeyState(kdf, params, salt, key)


def new_key(password: str, kdf: int | None = None, params: tuple[int, int, int] | None = None) -> KeyState:
    """Neuer Schlüssel mit frischem Salt – für neue Notizen und Passwortwechsel."""
    if kdf is None:
        kdf = KDF_ARGON2ID if argon2_available() else KDF_SCRYPT
    if params is None:
        params = ARGON2_DEFAULT if kdf == KDF_ARGON2ID else SCRYPT_DEFAULT
    return derive_key(password, kdf, params, os.urandom(SALT_LEN))


def seal(text: str, key: KeyState) -> bytes:
    """Text verschlüsseln – bei jedem Aufruf mit neuer Zufalls-Nonce."""
    header = Header(FORMAT_VERSION, key.kdf, key.params, key.salt, os.urandom(NONCE_LEN))
    packed = header.pack()
    return packed + AESGCM(key.key).encrypt(header.nonce, text.encode("utf-8"), packed)


def is_ntx(data: bytes) -> bool:
    return data[:len(MAGIC)] == MAGIC


def parse_header(data: bytes) -> Header:
    if len(data) < HEADER_LEN + TAG_LEN or not is_ntx(data):
        raise CorruptFile(f"Keine verschlüsselte {APP_NAME}-Notiz (Kopf fehlt oder ist zu kurz)")
    _magic, version, kdf, a, b, c, salt, nonce = _HEADER.unpack_from(data)
    if version != FORMAT_VERSION:
        raise UnsupportedFormat(f"Formatversion {version} ist neuer als diese {APP_NAME}-Version")
    header = Header(version, kdf, (a, b, c), salt, nonce)
    _check_params(kdf, header.params)
    return header


def open_with_key(data: bytes, key: KeyState) -> str:
    """Mit bekanntem Schlüssel entschlüsseln (z. B. Neuladen nach externer Änderung)."""
    header = parse_header(data)
    if (header.kdf, header.params, header.salt) != (key.kdf, key.params, key.salt):
        raise DecryptionFailed("Die Datei wurde mit einem anderen Passwort neu verschlüsselt")
    return _decrypt(data, header, key)


def open_note(data: bytes, password: str) -> tuple[str, KeyState]:
    """Datei entschlüsseln. Gibt (Text, Schlüssel) zurück; der Schlüssel dient dem späteren Speichern."""
    header = parse_header(data)
    key = derive_key(password, header.kdf, header.params, header.salt)
    return _decrypt(data, header, key), key


def _decrypt(data: bytes, header: Header, key: KeyState) -> str:
    try:
        plain = AESGCM(key.key).decrypt(header.nonce, data[HEADER_LEN:], data[:HEADER_LEN])
    except InvalidTag as error:
        raise DecryptionFailed("Falsches Passwort oder die Datei wurde verändert") from error
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError as error:   # authentisch, aber kein Text – kann nur ein Fremdformat sein
        raise CorruptFile("Inhalt ist kein UTF-8-Text") from error


def describe(header: Header) -> str:
    if header.kdf == KDF_ARGON2ID:
        memory, iterations, lanes = header.params
        return f"AES-256-GCM, Argon2id ({memory // 1024} MiB, {iterations} Durchläufe, {lanes} Lanes)"
    log2n, r, p = header.params
    return f"AES-256-GCM, scrypt (N=2^{log2n}, r={r}, p={p})"
