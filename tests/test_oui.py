"""Tests für die OUI-Herstellerzuordnung (core/oui.py) – ohne Qt."""
from __future__ import annotations

from notex.core import oui


def test_normalize():
    assert oui.normalize("00:1A:2B:3C:4D:5E") == "001A2B3C4D5E"
    assert oui.normalize("001a.2b3c.4d5e") == "001A2B3C4D5E"
    assert oui.normalize("00-1a-2b-3c-4d-5e") == "001A2B3C4D5E"
    assert oui.normalize("keine mac") is None
    assert oui.normalize("") is None


def test_prefix():
    assert oui.oui_prefix("00:00:0C:11:22:33") == "00000C"
    assert oui.oui_prefix("xx") is None


def test_locally_administered_and_multicast():
    # 02:.. hat das lokal-Bit gesetzt
    assert oui.is_locally_administered("02:00:00:00:00:01") is True
    assert oui.is_locally_administered("00:00:0C:00:00:01") is False
    # 01:.. ist Multicast (niedrigstes Bit)
    assert oui.is_multicast("01:00:5E:00:00:01") is True
    assert oui.is_multicast("00:00:0C:00:00:01") is False


def test_lookup_known_vendor():
    # 00:00:0C ist Cisco (IEEE-Registry)
    assert oui.data_available() is True
    assert "Cisco" in (oui.lookup("00:00:0C:12:34:56") or "")


def test_lookup_locally_administered_is_none():
    # lokal verwaltete MACs haben keinen Hersteller
    assert oui.lookup("02:11:22:33:44:55") is None


def test_vendor_label():
    assert "Cisco" in oui.vendor_label("00:00:0C:12:34:56")
    assert oui.vendor_label("02:11:22:33:44:55") == "lokal verwaltet"
    assert oui.vendor_label("01:00:5E:00:00:01") == "Multicast"
    assert oui.vendor_label("FF:FF:FF:00:00:00") in ("unbekannt", "Multicast", "lokal verwaltet")
