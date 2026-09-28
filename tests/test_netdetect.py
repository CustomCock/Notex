"""Tests für die Netz-Erkennung (core/netdetect.py) – ohne Qt, ohne echtes Netz."""
from __future__ import annotations

from notex.core import netdetect


IP_ADDR = """\
1: lo    inet 127.0.0.1/8 scope host lo
2: eth0    inet 192.168.1.10/24 brd 192.168.1.255 scope global eth0
3: wlan0    inet 10.0.5.3/16 brd 10.0.255.255 scope global wlan0
"""

IPCONFIG = """\
Windows-IP-Konfiguration

Ethernet-Adapter Ethernet:
   Verbindungsspezifisches DNS-Suffix: fritz.box
   IPv4-Adresse  . . . . . . . . . . : 192.168.178.25
   Subnetzmaske  . . . . . . . . . . : 255.255.255.0
   Standardgateway . . . . . . . . . : 192.168.178.1

Drahtlos-LAN-Adapter WLAN:
   Verbindungslokale IPv6-Adresse  . : fe80::1
   IPv4-Adresse  . . . . . . . . . . : 169.254.1.1
   Subnetzmaske  . . . . . . . . . . : 255.255.0.0
"""


def test_parse_ip_addr():
    adapters = netdetect.parse_ip_addr(IP_ADDR)
    names = {a.name: a.cidr for a in adapters}
    assert names["eth0"] == "192.168.1.0/24"
    assert names["wlan0"] == "10.0.0.0/16"
    assert "lo" not in names            # 127.0.0.1 wird übersprungen


def test_parse_ipconfig():
    adapters = netdetect.parse_ipconfig(IPCONFIG)
    cidrs = [a.cidr for a in adapters]
    assert "192.168.178.0/24" in cidrs
    # 169.254 (APIPA) wird ausgelassen
    assert all(not c.startswith("169.254") for c in cidrs)


def test_local_adapters_uses_runner():
    # Runner liefert je nach Plattform die passende Ausgabe (Linux: `ip`, Windows: `ipconfig`).
    def runner(cmd):
        if cmd[0] == "ip":
            return IP_ADDR
        if cmd[0] == "ipconfig":
            return IPCONFIG
        return ""
    cidrs = {a.cidr for a in netdetect.local_adapters(runner=runner)}
    assert "192.168.1.0/24" in cidrs or "192.168.178.0/24" in cidrs


def test_parse_exclusions():
    ex = netdetect.parse_exclusions("192.168.1.1, 192.168.1.10-12\n10.0.0.0/30")
    assert "192.168.1.1" in ex
    assert {"192.168.1.10", "192.168.1.11", "192.168.1.12"} <= ex
    # /30 hat 2 nutzbare Hosts
    assert "10.0.0.1" in ex and "10.0.0.2" in ex
    # Müll wird ignoriert
    assert netdetect.parse_exclusions("quatsch") == set()


def test_nbstat_request_shape():
    req = netdetect.build_nbstat_request()
    assert len(req) == 50               # 12 Header + 34 Name + 2 Typ + 2 Klasse
    assert req[-4:] == b"\x00\x21\x00\x01"     # NBSTAT, Klasse IN


def _fake_nbstat_response(name: str) -> bytes:
    header = b"\x4E\x54\x84\x00\x00\x00\x00\x01\x00\x00\x00\x00"
    question = b"\x20" + netdetect._encode_netbios_name("*") + b"\x00" + b"\x00\x21" + b"\x00\x01"
    answer_head = b"\xC0\x0C" + b"\x00\x21" + b"\x00\x01" + b"\x00\x00\x00\x00"
    entry = name.encode("ascii").ljust(15, b" ") + b"\x00" + b"\x00\x04"   # Suffix 0x00, Unique
    rdata = b"\x01" + entry + b"\x00" * 6         # 1 Name + MAC-Statistik (Rest)
    rdlen = len(rdata).to_bytes(2, "big")
    return header + question + answer_head + rdlen + rdata


def test_parse_nbstat_response():
    data = _fake_nbstat_response("WORKSTATION1")
    assert netdetect.parse_nbstat_response(data) == "WORKSTATION1"
    assert netdetect.parse_nbstat_response(b"\x00" * 10) is None


def test_build_wol_packet():
    packet = netdetect.build_wol_packet("00:1A:2B:3C:4D:5E")
    assert len(packet) == 6 + 16 * 6
    assert packet[:6] == b"\xff" * 6
    assert packet[6:12] == bytes.fromhex("001A2B3C4D5E")
    import pytest
    with pytest.raises(ValueError):
        netdetect.build_wol_packet("keine mac")
