"""Lokale Umwandlungen für die Analyse-Karte – ohne Qt und ohne Netz, gut testbar.

Base64/Base32/Hex/URL de-/kodieren, JWT zerlegen (Signatur NICHT geprüft), Unix-Zeit ↔ Datum, Zahl in Basen + Bits,
Hex-Farbe, User-Agent grob zerlegen, Hash eines Worts bilden (MD5/SHA-1/SHA-256/NTLM). NTLM = MD4(UTF-16LE); da
manche OpenSSL-Builds MD4 nicht mehr anbieten, ist MD4 hier als kleine reine Python-Funktion enthalten.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import struct
import urllib.parse
from datetime import datetime, timezone


# ---- Base64 / Base32 / Hex / URL ------------------------------------------------------------------

def _pad(text: str) -> str:
    return text + "=" * (-len(text) % 4)


def decode_base64(text: str) -> bytes:
    text = text.strip()
    try:
        return base64.b64decode(_pad(text), validate=True)
    except binascii.Error:
        return base64.urlsafe_b64decode(_pad(text.replace("-", "+").replace("_", "/")))


def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_base32(text: str) -> bytes:
    text = text.strip().upper()
    return base64.b32decode(text + "=" * (-len(text) % 8))


def encode_base32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii")


def decode_hex(text: str) -> bytes:
    return bytes.fromhex(text.strip().replace(" ", "").replace(":", ""))


def encode_hex(data: bytes) -> str:
    return data.hex()


def url_decode(text: str) -> str:
    return urllib.parse.unquote(text)


def url_encode(text: str) -> str:
    return urllib.parse.quote(text, safe="")


def bytes_preview(data: bytes, limit: int = 400) -> str:
    """Dekodierte Bytes menschlich zeigen: als UTF-8, sonst als Hex."""
    try:
        text = data.decode("utf-8")
        if all(c.isprintable() or c in "\r\n\t" for c in text):
            return text[:limit]
    except UnicodeDecodeError:
        pass
    return data[:limit].hex()


# ---- JWT ------------------------------------------------------------------------------------------

def jwt_decode(token: str) -> tuple[dict, dict, str]:
    """(Header, Payload, Hinweis). Wirft ValueError bei kaputtem Token. Signatur wird NICHT geprüft."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Kein JWT (drei Teile erwartet)")
    header = json.loads(base64.urlsafe_b64decode(_pad(parts[0])))
    payload = json.loads(base64.urlsafe_b64decode(_pad(parts[1])))
    return header, payload, "Signatur wird NICHT geprüft"


def jwt_times(payload: dict) -> list[tuple[str, str]]:
    """Lesbare Zeitfelder (iat/exp/nbf) aus einem JWT-Payload."""
    out = []
    for key, label in (("iat", "Ausgestellt"), ("nbf", "Gültig ab"), ("exp", "Läuft ab")):
        if isinstance(payload.get(key), (int, float)):
            dt = datetime.fromtimestamp(int(payload[key]), timezone.utc)
            out.append((label, dt.strftime("%Y-%m-%d %H:%M:%S UTC")))
    return out


# ---- Zeitstempel ----------------------------------------------------------------------------------

def timestamp_to_dates(value: int) -> tuple[str, str]:
    """Unix-Sekunden → (UTC, lokale Zeit)."""
    if value > 10_000_000_000:               # sieht nach Millisekunden aus
        value //= 1000
    utc = datetime.fromtimestamp(value, timezone.utc)
    local = datetime.fromtimestamp(value).astimezone()
    return utc.strftime("%Y-%m-%d %H:%M:%S UTC"), local.strftime("%Y-%m-%d %H:%M:%S %Z")


def date_to_timestamp(text: str) -> int:
    from notex.core.timeline import parse_iso
    dt = parse_iso(text)
    if dt is None:
        raise ValueError("Kein erkennbares Datum")
    return int(dt.timestamp())


# ---- Zahlen ---------------------------------------------------------------------------------------

def parse_int(text: str) -> int:
    text = text.strip().lower()
    if text.startswith("0x"):
        return int(text, 16)
    if text.startswith("0b"):
        return int(text, 2)
    if text.startswith("0o"):
        return int(text, 8)
    return int(text)


def number_bases(value: int) -> dict[str, str]:
    out = {"Dezimal": str(value), "Hexadezimal": hex(value), "Oktal": oct(value), "Binär": bin(value)}
    if 0 <= value < (1 << 64):
        width = 8 if value < 256 else 16 if value < 65536 else 32 if value < (1 << 32) else 64
        out["Bits"] = format(value, f"0{width}b")
    return out


# ---- Hex-Farbe ------------------------------------------------------------------------------------

def hex_color(text: str) -> tuple[int, int, int, str]:
    text = text.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        raise ValueError("Keine 3- oder 6-stellige Hex-Farbe")
    r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    return r, g, b, f"#{text.lower()}"


# ---- User-Agent -----------------------------------------------------------------------------------

_OS_RULES = [("Windows NT 10.0", "Windows 10/11"), ("Windows NT 6.3", "Windows 8.1"),
             ("Windows NT 6.1", "Windows 7"), ("Mac OS X", "macOS"), ("Android", "Android"),
             ("iPhone", "iOS (iPhone)"), ("iPad", "iPadOS"), ("CrOS", "ChromeOS"), ("Linux", "Linux")]
_BROWSER_RULES = [("Edg/", "Microsoft Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"),
                  ("Firefox/", "Firefox"), ("Safari/", "Safari"), ("curl/", "curl"),
                  ("Wget/", "Wget"), ("python-requests", "python-requests")]


def parse_user_agent(ua: str) -> dict[str, str]:
    def find(rules, default):
        for needle, name in rules:
            if needle in ua:
                if "/" in needle:                # Version mitnehmen
                    ver = ua.split(needle, 1)[1].split(" ")[0].split(";")[0]
                    return f"{name} {ver}".strip()
                return name
        return default

    device = "Mobil" if any(x in ua for x in ("Mobile", "Android", "iPhone")) else "Desktop"
    return {"Browser": find(_BROWSER_RULES, "unbekannt"), "System": find(_OS_RULES, "unbekannt"), "Gerät": device}


# ---- Hash eines Worts -----------------------------------------------------------------------------

def _md4(data: bytes) -> bytes:
    """Kleine reine MD4-Implementierung (für NTLM), falls hashlib kein md4 hat."""
    def lrot(x, n):
        x &= 0xFFFFFFFF
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    msg = bytearray(data)
    length = (8 * len(data)) & 0xFFFFFFFFFFFFFFFF
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack("<Q", length)
    a, b, c, d = 0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476
    for off in range(0, len(msg), 64):
        x = list(struct.unpack("<16I", msg[off:off + 64]))
        aa, bb, cc, dd = a, b, c, d
        for i in [0, 4, 8, 12]:
            a = lrot(a + ((b & c) | (~b & d)) + x[i], 3)
            d = lrot(d + ((a & b) | (~a & c)) + x[i + 1], 7)
            c = lrot(c + ((d & a) | (~d & b)) + x[i + 2], 11)
            b = lrot(b + ((c & d) | (~c & a)) + x[i + 3], 19)
        for i in [0, 1, 2, 3]:
            a = lrot(a + ((b & c) | (b & d) | (c & d)) + x[i] + 0x5a827999, 3)
            d = lrot(d + ((a & b) | (a & c) | (b & c)) + x[i + 4] + 0x5a827999, 5)
            c = lrot(c + ((d & a) | (d & b) | (a & b)) + x[i + 8] + 0x5a827999, 9)
            b = lrot(b + ((c & d) | (c & a) | (d & a)) + x[i + 12] + 0x5a827999, 13)
        for i in [0, 2, 1, 3]:
            a = lrot(a + (b ^ c ^ d) + x[i] + 0x6ed9eba1, 3)
            d = lrot(d + (a ^ b ^ c) + x[i + 8] + 0x6ed9eba1, 9)
            c = lrot(c + (d ^ a ^ b) + x[i + 4] + 0x6ed9eba1, 11)
            b = lrot(b + (c ^ d ^ a) + x[i + 12] + 0x6ed9eba1, 15)
        a = (a + aa) & 0xFFFFFFFF
        b = (b + bb) & 0xFFFFFFFF
        c = (c + cc) & 0xFFFFFFFF
        d = (d + dd) & 0xFFFFFFFF
    return struct.pack("<4I", a, b, c, d)


def ntlm(text: str) -> str:
    return _md4(text.encode("utf-16-le")).hex()


def hash_word(text: str, algo: str) -> str:
    """Hash eines Worts. algo ∈ {md5, sha1, sha256, sha512, ntlm}."""
    algo = algo.lower()
    if algo == "ntlm":
        return ntlm(text)
    if algo in ("md5", "sha1", "sha256", "sha512"):
        return hashlib.new(algo, text.encode("utf-8")).hexdigest()
    raise ValueError(f"Unbekannter Algorithmus: {algo}")
