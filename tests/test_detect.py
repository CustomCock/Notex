"""Tests für die Typ-Erkennung markierten Texts (core/detect.py) – ohne Qt."""
from __future__ import annotations

import base64

from notex.core import detect


def types(text):
    return detect.analyze(text).types


def best(text):
    m = detect.analyze(text).best
    return m.type if m else None


def test_ipv4():
    assert best("192.168.1.10") == "ipv4"
    assert "ipv4" in types("8.8.8.8")
    # ungültige Oktette sind keine IP
    assert "ipv4" not in types("999.1.1.1")


def test_ipv6_and_cidr():
    assert best("2001:db8::1") == "ipv6"
    assert "cidr" in types("10.0.0.0/24")
    assert "cidr" in types("192.168.0.0/16")


def test_mac():
    assert best("00:1A:2B:3C:4D:5E") == "mac"
    assert best("001a.2b3c.4d5e") == "mac"


def test_url_email_domain():
    assert best("https://example.com/pfad?x=1") == "url"
    assert best("user@example.org") == "email"
    assert "domain" in types("sub.example.com")
    # ganzer Satz ist keine Domain
    assert "domain" not in types("das ist ein satz")


def test_port():
    assert "port" in types("443/tcp")
    assert "port" in types("tcp/22")
    assert "port" in types("10.0.0.1:8080")


def test_hash_lengths_ambiguous():
    md5 = "d41d8cd98f00b204e9800998ecf8427e"
    assert "hash_md5" in types(md5)
    assert "hash_ntlm" in types(md5)          # Mehrdeutigkeit gewollt
    assert best("da39a3ee5e6b4b0d3255bfef95601890afd80709") == "hash_sha1"
    assert best("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") == "hash_sha256"
    assert best("a" * 128) == "hash_sha512"


def test_hash_salted_prefixes():
    assert best("$2b$12$abcdefghijklmnopqrstuv") == "hash_bcrypt"
    assert best("$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA") == "hash_argon2"
    assert best("$6$rounds=5000$salt$hashhashhash") == "hash_sha512crypt"
    # gesalzene Hashes tragen den Hinweis
    m = detect.analyze("$2b$12$abcdefghijklmnopqrstuv").best
    assert "gesalzen" in m.detail
    assert "hash_bcrypt" in detect.SALTED_HASHES


def test_jwt():
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(b'{"sub":"1","name":"x"}').decode().rstrip("=")
    token = f"{header}.{payload}.sig"
    assert best(token) == "jwt"


def test_base64():
    encoded = base64.b64encode(b"Hallo Welt, das ist ein Test").decode()
    assert "base64" in types(encoded)
    # reine Ziffern sind kein Base64
    assert "base64" not in types("12345678")


def test_timestamp_and_date():
    assert "unix_timestamp" in types("1700000000")     # 2023
    # Jahreszahl ist KEIN Zeitstempel und KEIN Port-Favorit
    assert "unix_timestamp" not in types("2024")
    assert "iso_date" in types("2024-01-15")
    assert "iso_date" in types("2024-01-15T10:30:00Z")


def test_number_hex_bin():
    assert "number" in types("0xDEADBEEF")
    assert "number" in types("0b1010")
    assert "number" in types("42")


def test_hex_color_cve_attack():
    assert best("#1e1e1e") == "hex_color"
    assert best("CVE-2021-44228") == "cve"
    assert best("T1059.003") == "attack_id"


def test_user_agent():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0"
    assert "user_agent" in types(ua)


def test_empty_and_multiline():
    assert detect.analyze("").matches == []
    assert detect.analyze("zeile1\nzeile2").matches == []


def test_token_at():
    text = "Verbindung zu 10.0.0.5:443 fehlgeschlagen"
    pos = text.index("10.0.0.5")
    assert detect.token_at(text, pos + 2) == "10.0.0.5:443"
    # Satzzeichen am Rand werden abgeschnitten
    assert detect.token_at("Ende example.com.", 12) == "example.com"


def test_ambiguity_sorted_by_confidence():
    det = detect.analyze("d41d8cd98f00b204e9800998ecf8427e")
    assert det.matches[0].confidence >= det.matches[-1].confidence
