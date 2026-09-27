"""Erkennung des markierten Texts – welche „Sorte" Wert steckt in einer Markierung?

Ohne Qt und gut testbar. `analyze(text)` gibt alle plausiblen Typen mit Konfidenz zurück (Mehrdeutigkeit ist
gewollt: 32 Hex-Zeichen sind MD5 ODER NTLM, Ziffern können Zahl/Port/Zeitstempel sein). Die Oberfläche baut daraus
das Kontextmenü „Analysieren" und die Erkennungs-Karte.

Bewusst konservativ: ein ganzer Satz ist kein Base64, eine Jahreszahl kein Port. Deshalb prüfen die Detektoren nicht
nur Muster, sondern auch Plausibilität (gültige Oktette, dekodierbares Base64, sinnvoller Zeitbereich …).
"""
from __future__ import annotations

import base64 as _b64
import binascii
import ipaddress
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Kanonische Typschlüssel → deutsche Bezeichnung
TYPE_LABELS: dict[str, str] = {
    "ipv4": "IPv4-Adresse", "ipv6": "IPv6-Adresse", "cidr": "IP-Netz (CIDR)", "mac": "MAC-Adresse",
    "domain": "Domain/Hostname", "url": "URL", "email": "E-Mail-Adresse", "port": "Portnummer",
    "hash_md5": "MD5-Hash", "hash_sha1": "SHA-1-Hash", "hash_sha256": "SHA-256-Hash",
    "hash_sha512": "SHA-512-Hash", "hash_ntlm": "NTLM-Hash", "hash_bcrypt": "bcrypt (gesalzen)",
    "hash_argon2": "argon2 (gesalzen)", "hash_sha512crypt": "sha512crypt (gesalzen)",
    "hash_md5crypt": "md5crypt (gesalzen)", "hash_sha256crypt": "sha256crypt (gesalzen)",
    "hash_yescrypt": "yescrypt (gesalzen)",
    "base64": "Base64", "base32": "Base32", "hex_blob": "Hex-Daten", "jwt": "JWT (JSON Web Token)",
    "unix_timestamp": "Unix-Zeitstempel", "iso_date": "ISO-Datum", "number": "Zahl",
    "hex_color": "Hex-Farbe", "cve": "CVE-Kennung", "attack_id": "MITRE ATT&CK-Technik",
    "user_agent": "User-Agent",
}

# Welche Hash-Typen sind ungesalzen (für Online-Lookup geeignet) bzw. gesalzen?
UNSALTED_HASHES = {"hash_md5", "hash_sha1", "hash_sha256", "hash_sha512", "hash_ntlm"}
SALTED_HASHES = {"hash_bcrypt", "hash_argon2", "hash_sha512crypt", "hash_md5crypt", "hash_sha256crypt",
                 "hash_yescrypt"}


@dataclass(frozen=True)
class Match:
    type: str
    confidence: float
    detail: str = ""

    @property
    def label(self) -> str:
        return TYPE_LABELS.get(self.type, self.type)


@dataclass
class Detection:
    text: str
    matches: list[Match] = field(default_factory=list)

    @property
    def types(self) -> list[str]:
        return [m.type for m in self.matches]

    @property
    def best(self) -> Match | None:
        return self.matches[0] if self.matches else None

    def has(self, type_key: str) -> bool:
        return any(m.type == type_key for m in self.matches)


_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
_MAC_CISCO_RE = re.compile(r"^(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_URL_RE = re.compile(r"^(?:https?|ftp|ftps|sftp)://[^\s]+$", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")
_PORT_SUFFIX_RE = re.compile(r"^(?:.+:)?(\d{1,5})$")
_PORT_PROTO_RE = re.compile(r"^(\d{1,5})/(tcp|udp)$|^(tcp|udp)/(\d{1,5})$", re.IGNORECASE)
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_ATTACK_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")
_BASE32_RE = re.compile(r"^[A-Z2-7]+=*$")
_JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$")

_TS_MIN = 978307200          # 2001-01-01
_TS_MAX = 4102444800         # 2100-01-01


def _add(matches, type_key, confidence, detail=""):
    matches.append(Match(type_key, round(confidence, 2), detail))


def _detect_ip(text, matches):
    try:
        ip = ipaddress.ip_address(text)
        _add(matches, "ipv6" if ip.version == 6 else "ipv4", 0.98,
             "privat/reserviert" if (ip.is_private or ip.is_reserved or ip.is_loopback) else "öffentlich")
        return True
    except ValueError:
        return False


def _detect_cidr(text, matches):
    if "/" not in text:
        return
    try:
        net = ipaddress.ip_network(text, strict=False)
    except ValueError:
        return
    if net.num_addresses > 1:
        _add(matches, "cidr", 0.95, f"{net.num_addresses} Adressen")


def _detect_mac(text, matches):
    if _MAC_RE.match(text) or _MAC_CISCO_RE.match(text):
        first = int(re.sub(r"[^0-9A-Fa-f]", "", text)[:2], 16)
        local = "lokal verwaltet" if first & 0b10 else "global (OUI)"
        _add(matches, "mac", 0.95, local)


def _detect_hashes(text, matches):
    # Präfix-Formate (gesalzen)
    prefixes = [("$2a$", "hash_bcrypt"), ("$2b$", "hash_bcrypt"), ("$2y$", "hash_bcrypt"),
                ("$argon2", "hash_argon2"), ("$6$", "hash_sha512crypt"), ("$1$", "hash_md5crypt"),
                ("$5$", "hash_sha256crypt"), ("$y$", "hash_yescrypt"), ("$7$", "hash_yescrypt")]
    for prefix, key in prefixes:
        if text.startswith(prefix):
            _add(matches, key, 0.95, "gesalzen → Online-Lookup sinnlos")
            return
    if not _HEX_RE.match(text):
        return
    n = len(text)
    if n == 32:
        _add(matches, "hash_md5", 0.6, "32 Hex-Zeichen")
        _add(matches, "hash_ntlm", 0.5, "32 Hex-Zeichen (auch NTLM)")
    elif n == 40:
        _add(matches, "hash_sha1", 0.7, "40 Hex-Zeichen")
    elif n == 64:
        _add(matches, "hash_sha256", 0.75, "64 Hex-Zeichen")
    elif n == 128:
        _add(matches, "hash_sha512", 0.75, "128 Hex-Zeichen")


def _detect_hex_blob(text, matches):
    if _HEX_RE.match(text) and len(text) >= 8 and len(text) % 2 == 0 and len(text) not in (32, 40, 64, 128):
        _add(matches, "hex_blob", 0.45, f"{len(text)//2} Bytes")


def _detect_number(text, matches):
    if re.fullmatch(r"\d+", text):
        _add(matches, "number", 0.7, "dezimal")
    elif re.fullmatch(r"0[xX][0-9a-fA-F]+", text):
        _add(matches, "number", 0.9, "hexadezimal")
    elif re.fullmatch(r"0[bB][01]+", text):
        _add(matches, "number", 0.9, "binär")


def _detect_port(text, matches):
    m = _PORT_PROTO_RE.match(text)
    if m:
        value = int(m.group(1) or m.group(4))
        if 1 <= value <= 65535:
            _add(matches, "port", 0.9, f"Port {value}")
            return
    if ":" in text:
        m = _PORT_SUFFIX_RE.match(text)
        if m:
            value = int(m.group(1))
            if 1 <= value <= 65535:
                _add(matches, "port", 0.6, f"Port {value}")
                return
    # nackte Zahl im Portbereich: nur als schwache Zusatzoption
    if re.fullmatch(r"\d{1,5}", text):
        value = int(text)
        if 1 <= value <= 65535 and not (_TS_MIN <= value <= _TS_MAX):
            _add(matches, "port", 0.3, f"könnte Port {value} sein")


def _detect_timestamp(text, matches):
    if re.fullmatch(r"\d{10}", text):
        value = int(text)
        if _TS_MIN <= value <= _TS_MAX:
            dt = datetime.fromtimestamp(value, timezone.utc)
            _add(matches, "unix_timestamp", 0.6, dt.strftime("%Y-%m-%d %H:%M:%S UTC"))
    elif re.fullmatch(r"\d{13}", text):
        value = int(text) // 1000
        if _TS_MIN <= value <= _TS_MAX:
            dt = datetime.fromtimestamp(value, timezone.utc)
            _add(matches, "unix_timestamp", 0.6, dt.strftime("%Y-%m-%d %H:%M:%S UTC (ms)"))


def _detect_iso_date(text, matches):
    if _ISO_DATE_RE.match(text):
        _add(matches, "iso_date", 0.85)


def _detect_jwt(text, matches):
    if text.count(".") != 2 or not _JWT_RE.match(text):
        return
    header = text.split(".", 1)[0]
    data = _b64url_decode(header)
    if data and data.lstrip().startswith(b"{") and b"alg" in data:
        _add(matches, "jwt", 0.95, "Signatur wird NICHT geprüft")


def _detect_base(text, matches):
    # JWT/hex/zahl schon behandelt; hier allgemeines Base64/Base32
    if len(text) >= 8 and _BASE32_RE.match(text) and len(text) % 8 == 0:
        _add(matches, "base32", 0.4)
    looks_b64 = (len(text) >= 8 and len(text) % 4 == 0
                 and (_BASE64_RE.match(text) or _BASE64URL_RE.match(text))
                 and not _HEX_RE.match(text) and not text.isdigit())
    if looks_b64 and _mixed_classes(text):
        decoded = _b64_decode(text)
        if decoded is not None:
            printable = _mostly_printable(decoded)
            _add(matches, "base64", 0.55 if printable else 0.4,
                 "dekodiert zu Text" if printable else "dekodiert zu Binärdaten")


def _detect_url_email_domain(text, matches):
    if _URL_RE.match(text):
        _add(matches, "url", 0.95)
        return
    if _EMAIL_RE.match(text):
        _add(matches, "email", 0.95)
        return
    if _DOMAIN_RE.match(text) and not text.isdigit():
        _add(matches, "domain", 0.7)


def _detect_misc(text, matches):
    if _HEX_COLOR_RE.match(text):
        _add(matches, "hex_color", 0.95)
    if _CVE_RE.match(text):
        _add(matches, "cve", 0.98)
    if _ATTACK_RE.match(text):
        _add(matches, "attack_id", 0.9)
    if _looks_user_agent(text):
        _add(matches, "user_agent", 0.75)


# ---- Hilfen ---------------------------------------------------------------------------------------

def _mixed_classes(text: str) -> bool:
    """Base64 nur, wenn wirklich gemischt – „12345678" oder „abcdefgh" sind kein sinnvolles Base64."""
    core = text.rstrip("=")
    has_upper = any(c.isupper() for c in core)
    has_lower = any(c.islower() for c in core)
    has_digit = any(c.isdigit() for c in core)
    has_special = any(c in "+/-_" for c in core)
    return sum([has_upper, has_lower, has_digit, has_special]) >= 2


def _mostly_printable(data: bytes) -> bool:
    if not data:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
    return printable / len(text) > 0.85


def _b64_decode(text: str) -> bytes | None:
    for decoder in (_b64.b64decode, lambda t: _b64.urlsafe_b64decode(_pad(t))):
        try:
            return decoder(_pad(text))
        except (binascii.Error, ValueError):
            continue
    return None


def _b64url_decode(text: str) -> bytes | None:
    try:
        return _b64.urlsafe_b64decode(_pad(text))
    except (binascii.Error, ValueError):
        return None


def _pad(text: str) -> str:
    return text + "=" * (-len(text) % 4)


_UA_HINTS = ("Mozilla/", "AppleWebKit", "Gecko/", "Chrome/", "Safari/", "Edg/", "curl/", "Wget/",
             "python-requests", "(Windows NT", "(X11;", "(Macintosh;", "(iPhone;", "(Linux;", "(Android")


def _looks_user_agent(text: str) -> bool:
    return len(text) >= 12 and sum(1 for hint in _UA_HINTS if hint in text) >= 2


DETECTORS = [
    _detect_ip, _detect_cidr, _detect_mac, _detect_url_email_domain, _detect_hashes, _detect_hex_blob,
    _detect_number, _detect_port, _detect_timestamp, _detect_iso_date, _detect_jwt, _detect_base, _detect_misc,
]


def analyze(text: str) -> Detection:
    """Alle plausiblen Typen einer Markierung, nach Konfidenz sortiert. Leere/mehrzeilige Eingabe → wenig/keine Treffer."""
    stripped = (text or "").strip()
    matches: list[Match] = []
    if not stripped or "\n" in stripped or len(stripped) > 8192:
        return Detection(stripped, matches)
    for detector in DETECTORS:
        try:
            detector(stripped, matches)
        except Exception:                       # noqa: BLE001 – ein Detektor darf die anderen nie kippen
            continue
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return Detection(stripped, matches)


def token_at(text: str, position: int) -> str:
    """Wort/Token um die Cursorposition – für „nichts markiert, aber Rechtsklick auf ein Wort"."""
    if not text:
        return ""
    position = max(0, min(position, len(text)))
    breakers = set(" \t\r\n\"'`()[]{}<>,;")     # Punkt/Doppelpunkt/Slash bleiben Teil von URLs/IPs/Ports
    start = position
    while start > 0 and text[start - 1] not in breakers:
        start -= 1
    end = position
    while end < len(text) and text[end] not in breakers:
        end += 1
    return text[start:end].strip(".,;:")
