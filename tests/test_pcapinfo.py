import struct
from pathlib import Path

import pytest

from notex.core import pcapinfo

dpkt = pytest.importorskip("dpkt")

FIXTURE = Path(__file__).parent / "fixtures" / "beispiel_traffic.pcap"


@pytest.fixture(scope="module")
def summary():
    return pcapinfo.analyze(FIXTURE)


def test_totals(summary) -> None:
    assert summary.packets == 13 and summary.bytes == 958 and summary.broken == 0
    assert summary.duration == pytest.approx(5.61, abs=0.01)


def test_protocol_hierarchy(summary) -> None:
    layers = {l.name: (l.packets, l.bytes) for l in summary.layers}
    assert layers["Ethernet"] == (13, 958)
    assert layers["ARP"][0] == 2 and layers["IPv4"][0] == 11
    assert layers["ICMP"][0] == 2 and layers["UDP"][0] == 2 and layers["DNS"][0] == 2
    assert layers["TCP"][0] == 7 and layers["HTTP"][0] == 2      # nur die 2 Pakete mit HTTP-Nutzdaten


def test_hosts_and_address_types(summary) -> None:
    hosts = summary.hosts
    assert hosts["192.168.10.20"].addr_type == "privat" and hosts["192.168.10.20"].role == "Client"
    assert hosts["192.168.10.1"].role == "Gateway/Router"
    assert hosts["192.0.2.53"].addr_type == "Dokumentation (TEST-NET-1)" and hosts["192.0.2.53"].role == "DNS-Server"
    assert hosts["198.51.100.25"].addr_type == "Dokumentation (TEST-NET-2)" and hosts["198.51.100.25"].role == "Webserver"
    assert "02:00:00:00:00:10" in hosts["192.168.10.20"].macs


def test_arp(summary) -> None:
    req = next(e for e in summary.arp if e.op == "Anfrage")
    rep = next(e for e in summary.arp if e.op == "Antwort")
    assert req.sender_ip == "192.168.10.20" and req.sender_mac == "02:00:00:00:00:10" and req.target_ip == "192.168.10.1"
    assert rep.sender_mac == "02:00:00:00:00:01"


def test_icmp_echo_pair(summary) -> None:
    reply = next(e for e in summary.icmp if e.kind == "Echo-Antwort")
    assert reply.rtt == pytest.approx(1.001, abs=0.001)
    assert {e.kind for e in summary.icmp} == {"Echo-Anfrage", "Echo-Antwort"}


def test_dns(summary) -> None:
    assert len(summary.dns) == 1
    e = summary.dns[0]
    assert e.name == "example.test" and e.qtype == "A" and e.client == "192.168.10.20" and e.server == "192.0.2.53"
    assert e.rcode == "NOERROR" and e.answers == [("198.51.100.25", 300)]
    assert e.response_time == pytest.approx(1.001, abs=0.001)


def test_tcp_connection(summary) -> None:
    assert len(summary.tcp) == 1
    conn = summary.tcp_list[0]
    assert conn.a == "192.168.10.20:49152" and conn.b == "198.51.100.25:80"
    assert conn.state == "vollständig (Handshake + FIN-Abbau)"
    assert conn.bytes_ab == 88 and conn.bytes_ba == 128 and conn.retransmissions == 0


def test_follow_stream(summary) -> None:
    stream = summary.tcp_list[0].stream()
    assert b"GET /demo HTTP/1.1" in stream and b"200 OK" in stream and b"Hallo, das ist der PCAP-Body" in stream


def test_http(summary) -> None:
    assert len(summary.http) == 1
    e = summary.http[0]
    assert e.method == "GET" and e.host == "example.test" and e.path == "/demo" and e.user_agent == "PCAP-Demo/1.0"
    assert e.status == "200 OK" and e.content_type == "text/plain; charset=utf-8" and e.content_length == "29"
    assert "PCAP-Body" in e.body_preview


def test_findings(summary) -> None:
    texts = [f.text for f in summary.findings]
    assert any("Unverschlüsselte Protokolle" in t and "HTTP" in t for t in texts)
    assert any("Keine Klartext-Zugangsdaten gefunden" in t for t in texts)


def test_report_markdown(summary) -> None:
    report = pcapinfo.to_markdown(summary, "beispiel_traffic.pcap")
    for section in ("Protokoll-Hierarchie", "Hosts", "ARP", "ICMP", "DNS", "TCP-Verbindungen", "HTTP", "Befunde"):
        assert f"## {section}" in report
    assert "example.test" in report and "198.51.100.25" in report and "TEST-NET" in report


# ---- Helfer und Robustheit ----------------------------------------------------------------------------------------
def test_address_type() -> None:
    assert pcapinfo.address_type("192.0.2.10") == "Dokumentation (TEST-NET-1)"
    assert pcapinfo.address_type("10.0.0.1") == "privat" and pcapinfo.address_type("8.8.8.8") == "öffentlich"
    assert pcapinfo.address_type("127.0.0.1") == "Loopback" and pcapinfo.address_type("224.0.0.1") == "Multicast"


def test_locally_administered_mac() -> None:
    assert pcapinfo.is_locally_administered("02:00:00:00:00:10")
    assert not pcapinfo.is_locally_administered("AA:BB:CC:DD:EE:FF") is False   # AA has bit 0x02 set → local
    assert not pcapinfo.is_locally_administered("00:11:22:33:44:55")


def test_tls_sni_and_version() -> None:
    def client_hello(server: str) -> bytes:
        host = server.encode()
        sni_ext = b"\x00\x00" + struct.pack(">H", len(host) + 5) + struct.pack(">H", len(host) + 3) + b"\x00" \
            + struct.pack(">H", len(host)) + host
        exts = struct.pack(">H", len(sni_ext)) + sni_ext
        body = b"\x03\x03" + b"\x00" * 32 + b"\x00" + b"\x00\x02\x00\x2f" + b"\x01\x00" + exts
        hs = b"\x01" + struct.pack(">I", len(body))[1:] + body
        return b"\x16\x03\x01" + struct.pack(">H", len(hs)) + hs
    hello = client_hello("secure.example.com")
    assert pcapinfo.tls_sni(hello) == "secure.example.com" and pcapinfo.tls_version(hello) == "TLS 1.0"
    assert pcapinfo.tls_sni(b"not tls") is None


@pytest.mark.parametrize("sport,dport,payload,needle", [
    (40000, 21, b"USER alice\r\nPASS s3cret\r\n", "PASS s3cret"),
    (40000, 110, b"USER bob\r\nPASS hunter2\r\n", "PASS hunter2"),
    (40000, 143, b"a1 LOGIN carol pass123\r\n", "LOGIN carol"),
])
def test_credentials(sport, dport, payload, needle) -> None:
    creds = pcapinfo.extract_credentials(sport, dport, payload)
    assert any(needle in c.detail for c in creds)


def test_not_a_pcap(tmp_path: Path) -> None:
    path = tmp_path / "no.pcap"
    path.write_bytes(b"hello world not a capture")
    with pytest.raises(pcapinfo.PcapError):
        pcapinfo.analyze(path)


def test_broken_capture_is_robust(tmp_path: Path) -> None:
    import shutil
    path = tmp_path / "x.pcap"
    shutil.copyfile(FIXTURE, path)
    with open(path, "ab") as handle:
        handle.write(b"\xff" * 8 + b"\x10\x00\x00\x00\x10\x00\x00\x00" + b"garbage!!")
    summary = pcapinfo.analyze(path)
    assert summary.packets >= 13
