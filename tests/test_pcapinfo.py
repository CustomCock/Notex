import struct
from pathlib import Path

import pytest

from notex.core import pcapinfo

dpkt = pytest.importorskip("dpkt")


def eth(src_ip: str, dst_ip: str, transport) -> bytes:
    import socket
    ip = dpkt.ip.IP(src=socket.inet_aton(src_ip), dst=socket.inet_aton(dst_ip), p=(dpkt.ip.IP_PROTO_TCP
         if isinstance(transport, dpkt.tcp.TCP) else dpkt.ip.IP_PROTO_UDP), data=transport)
    ip.len = len(ip)
    frame = dpkt.ethernet.Ethernet(src=b"\x00\x11\x22\x33\x44\x55", dst=b"\x66\x77\x88\x99\xaa\xbb", data=ip)
    return bytes(frame)


def tcp(sport: int, dport: int, payload: bytes) -> "dpkt.tcp.TCP":
    return dpkt.tcp.TCP(sport=sport, dport=dport, data=payload, seq=1, off=5, flags=dpkt.tcp.TH_PUSH | dpkt.tcp.TH_ACK)


def udp(sport: int, dport: int, payload: bytes) -> "dpkt.udp.UDP":
    u = dpkt.udp.UDP(sport=sport, dport=dport, data=payload)
    u.ulen = len(u)
    return u


def dns_query(name: str) -> bytes:
    q = dpkt.dns.DNS(id=1, qd=[dpkt.dns.DNS.Q(name=name, type=dpkt.dns.DNS_A)])
    return bytes(q)


def client_hello(server: str) -> bytes:
    host = server.encode()
    sni_ext = b"\x00\x00" + struct.pack(">H", len(host) + 5) + struct.pack(">H", len(host) + 3) + b"\x00" \
        + struct.pack(">H", len(host)) + host
    exts = struct.pack(">H", len(sni_ext)) + sni_ext
    body = b"\x03\x03" + b"\x00" * 32 + b"\x00" + b"\x00\x02\x00\x2f" + b"\x01\x00" + exts   # ver+random+sid+ciphers+comp+exts
    hs = b"\x01" + struct.pack(">I", len(body))[1:] + body
    return b"\x16\x03\x01" + struct.pack(">H", len(hs)) + hs


def write_pcap(path: Path, packets: list[bytes]) -> None:
    with open(path, "wb") as handle:
        writer = dpkt.pcap.Writer(handle)
        for i, pkt in enumerate(packets):
            writer.writepkt(pkt, ts=1_700_000_000 + i)


def test_tls_sni_parser() -> None:
    assert pcapinfo.tls_sni(client_hello("secure.example.com")) == "secure.example.com"
    assert pcapinfo.tls_sni(b"\x16\x03\x01\x00\x05hello") is None
    assert pcapinfo.tls_sni(b"not tls") is None


@pytest.mark.parametrize("sport,dport,payload,proto,needle", [
    (40000, 21, b"USER alice\r\nPASS s3cret\r\n", "FTP", "PASS s3cret"),
    (40000, 110, b"USER bob\r\nPASS hunter2\r\n", "POP3", "PASS hunter2"),
    (40000, 143, b"a1 LOGIN carol pass123\r\n", "IMAP", "LOGIN carol"),
])
def test_extract_credentials(sport, dport, payload, proto, needle) -> None:
    creds = pcapinfo.extract_credentials(sport, dport, payload)
    assert any(c.protocol == proto and needle in c.detail for c in creds)


def test_smtp_auth_base64() -> None:
    import base64
    token = base64.b64encode(b"\x00user@example.com\x00geheim").decode()
    creds = pcapinfo.extract_credentials(50000, 587, f"AUTH PLAIN {token}\r\n".encode())
    assert creds and "user@example.com" in creds[0].detail


def test_no_credentials_on_other_ports() -> None:
    assert pcapinfo.extract_credentials(1234, 5678, b"USER x\r\nPASS y\r\n") == []


def test_analyze_full_capture(tmp_path: Path) -> None:
    http = b"GET /login HTTP/1.1\r\nHost: portal.example.com\r\nUser-Agent: curl/8.5\r\n" \
           b"Authorization: Basic YWxpY2U6Z2VoZWlt\r\n\r\n"      # alice:geheim
    packets = [
        eth("10.0.0.10", "8.8.8.8", udp(50000, 53, dns_query("portal.example.com"))),
        eth("10.0.0.10", "93.184.216.34", tcp(50001, 80, http)),
        eth("10.0.0.10", "93.184.216.34", tcp(50002, 443, client_hello("secure.example.com"))),
        eth("10.0.0.10", "192.168.1.9", tcp(50003, 21, b"USER admin\r\nPASS toor\r\n")),
    ]
    path = tmp_path / "capture.pcap"
    write_pcap(path, packets)
    summary = pcapinfo.analyze(path)
    assert summary.packets == 4 and summary.broken == 0 and summary.duration == pytest.approx(3.0)
    assert "portal.example.com" in summary.dns_queries
    assert summary.http_hosts["portal.example.com"] == 1 and ("portal.example.com", "/login", "curl/8.5") in summary.http_requests
    assert summary.tls_sni["secure.example.com"] == 1
    assert "10.0.0.10" in dict(summary.talkers)
    protos = dict(summary.protocols)
    assert protos.get("DNS") == 1 and protos.get("HTTP") == 1 and protos.get("HTTPS/TLS") == 1
    kinds = {(c.protocol, c.detail) for c in summary.credentials}
    assert any(p == "HTTP Basic" and "alice:geheim" in d for p, d in kinds)
    assert any(p == "FTP" and "PASS toor" in d for p, d in kinds)
    report = pcapinfo.to_markdown(summary, "capture.pcap")
    assert "Klartext-Zugangsdaten" in report and "secure.example.com" in report and "portal.example.com" in report


def test_broken_capture_is_robust(tmp_path: Path) -> None:
    path = tmp_path / "x.pcap"
    write_pcap(path, [eth("10.0.0.1", "10.0.0.2", udp(1, 53, dns_query("a.example.com")))])
    with open(path, "ab") as handle:
        handle.write(b"\xff" * 8 + b"\x10\x00\x00\x00\x10\x00\x00\x00" + b"garbagegarbage!!")   # kaputter Record
    summary = pcapinfo.analyze(path)
    assert summary.packets >= 1                       # der gute Record kommt durch, der kaputte wird gezählt/übersprungen


def test_not_a_pcap(tmp_path: Path) -> None:
    path = tmp_path / "no.pcap"
    path.write_bytes(b"hello world not a capture")
    with pytest.raises(pcapinfo.PcapError):
        pcapinfo.analyze(path)
