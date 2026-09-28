"""Tests für den Online-Hash-Lookup (core/hashlookup.py) – Netz injiziert, ohne echten Abruf."""
from __future__ import annotations

from notex.core import hashlookup as hl


def test_can_lookup_only_md5():
    assert hl.can_lookup("hash_md5") is True
    assert hl.can_lookup("hash_sha1") is False
    assert hl.can_lookup("hash_bcrypt") is False


def test_reason_unsupported():
    assert "sinnlos" in hl.reason_unsupported("hash_bcrypt")
    assert "MD5" in hl.reason_unsupported("hash_sha256")


def test_build_url_lowercases():
    assert hl.build_url("D41D8CD98F00B204E9800998ECF8427E").endswith("d41d8cd98f00b204e9800998ecf8427e")


def test_parse_response():
    assert hl.parse_response("password").found is True
    assert hl.parse_response("password").plaintext == "password"
    assert hl.parse_response("   ").found is False
    # HTML-Fehlerseite gilt nicht als Treffer
    assert hl.parse_response("<html>error</html>").found is False


def test_client_found():
    calls = {}

    def fake(url, timeout):
        calls["url"] = url
        return 200, "geheim123"

    client = hl.HashLookupClient(fetch=fake)
    result = client.lookup("5f4dcc3b5aa765d61d8327deb882cf99", "hash_md5")
    assert result.found and result.plaintext == "geheim123"
    assert "5f4dcc3b" in calls["url"]


def test_client_not_found():
    client = hl.HashLookupClient(fetch=lambda url, t: (200, ""))
    assert client.lookup("5f4dcc3b5aa765d61d8327deb882cf99", "hash_md5").found is False


def test_client_rejects_non_md5_type():
    client = hl.HashLookupClient(fetch=lambda url, t: (200, "x"))
    result = client.lookup("a" * 40, "hash_sha1")
    assert result.found is False and "kein freier" in result.message.lower()


def test_client_rejects_bad_md5():
    client = hl.HashLookupClient(fetch=lambda url, t: (200, "x"))
    assert client.lookup("nothex", "hash_md5").found is False


def test_client_http_error():
    client = hl.HashLookupClient(fetch=lambda url, t: (503, ""))
    assert "503" in client.lookup("a" * 32, "hash_md5").message
