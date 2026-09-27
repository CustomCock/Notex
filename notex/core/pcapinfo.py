"""PCAP-Übersicht: .pcap/.pcapng streamen und wie Wireshark auswerten – Protokoll-Hierarchie, Hosts (MAC, Adresstyp,
Rolle), ARP, ICMP, DNS (Anfrage/Antwort gepaart), TCP-Verbindungen (Status, Bytes je Richtung, „Stream folgen“),
HTTP (Anfrage mit Antwort), TLS-SNI, Dienste und Befunde (unverschlüsselt, Klartext-Zugangsdaten). Ohne Qt.

Bibliothek: **dpkt** (BSD-3, reines Python) – bewusst NICHT scapy (GPL). Ehrliche Grenzen: TCP-Reassemblierung ist
vereinfacht (Nutzdaten werden nach Sequenznummer sortiert zusammengesetzt, ohne Lückenfüllung); verschlüsselte
Inhalte werden nicht entschlüsselt (bei TLS nur SNI/Version/ALPN). Kaputte Pakete werden übersprungen.
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import re
import socket
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_ROWS = 5000
MAX_STREAM = 256 * 1024        # je Richtung höchstens so viele Bytes für „Stream folgen“ behalten
CRED_PORTS = {21: "FTP", 23: "Telnet", 110: "POP3", 143: "IMAP", 25: "SMTP", 587: "SMTP"}
HTTP_PORTS = {80, 8000, 8008, 8080, 8081, 8088}
DOC_NETS = [(ipaddress.ip_network("192.0.2.0/24"), "TEST-NET-1"), (ipaddress.ip_network("198.51.100.0/24"), "TEST-NET-2"),
            (ipaddress.ip_network("203.0.113.0/24"), "TEST-NET-3"), (ipaddress.ip_network("2001:db8::/32"), "Doku")]


class PcapError(Exception):
    pass


# ---- Datentypen ----------------------------------------------------------------------------------------------------
@dataclass
class Layer:
    name: str
    packets: int = 0
    bytes: int = 0
    depth: int = 0


@dataclass
class HostInfo:
    ip: str
    macs: set = field(default_factory=set)
    addr_type: str = ""
    role: str = ""
    sent_packets: int = 0
    sent_bytes: int = 0
    recv_packets: int = 0
    recv_bytes: int = 0


@dataclass
class ArpEntry:
    op: str                    # "Anfrage" | "Antwort"
    sender_ip: str
    sender_mac: str
    target_ip: str
    target_mac: str
    gratuitous: bool = False


@dataclass
class IcmpEntry:
    kind: str
    src: str
    dst: str
    detail: str = ""
    rtt: float | None = None


@dataclass
class DnsEntry:
    name: str
    qtype: str
    client: str
    server: str
    rcode: str = ""
    answers: list = field(default_factory=list)     # [(Wert, TTL)]
    response_time: float | None = None


@dataclass
class TcpConn:
    a: str                     # "ip:port" – Initiator (SYN-Sender), falls erkennbar
    b: str
    state: str = "unvollständig"
    start: float | None = None
    end: float | None = None
    bytes_ab: int = 0
    bytes_ba: int = 0
    packets: int = 0
    syn: int = 0
    fin: int = 0
    rst: int = 0
    retransmissions: int = 0
    _ab: dict = field(default_factory=dict)         # seq -> payload (Richtung a->b), für „Stream folgen“
    _ba: dict = field(default_factory=dict)
    _seen: set = field(default_factory=set)

    @property
    def duration(self) -> float:
        return (self.end - self.start) if self.start is not None and self.end is not None else 0.0

    def stream(self, both: bool = True) -> bytes:
        parts = []
        for seq in sorted(self._ab):
            parts.append(self._ab[seq])
        ba = [self._ba[seq] for seq in sorted(self._ba)]
        return (b"".join(parts) + b"".join(ba)) if both else b"".join(parts)


@dataclass
class HttpExchange:
    client: str
    server: str
    method: str = ""
    host: str = ""
    path: str = ""
    user_agent: str = ""
    status: str = ""
    content_type: str = ""
    content_length: str = ""
    response_time: float | None = None
    body_preview: str = ""


@dataclass
class TlsInfo:
    server: str
    sni: str = ""
    version: str = ""
    alpn: str = ""


@dataclass
class Credential:
    protocol: str
    server: str
    detail: str
    src: str = ""


@dataclass
class Finding:
    severity: str              # "warnung" | "info"
    text: str


@dataclass
class Summary:
    packets: int = 0
    bytes: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    broken: int = 0
    layers: list = field(default_factory=list)
    hosts: dict = field(default_factory=dict)              # ip -> HostInfo
    arp: list = field(default_factory=list)
    icmp: list = field(default_factory=list)
    dns: list = field(default_factory=list)
    tcp: dict = field(default_factory=dict)                # key -> TcpConn
    http: list = field(default_factory=list)
    tls: list = field(default_factory=list)
    services: dict = field(default_factory=dict)           # "ip:port" -> Dienstname
    credentials: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    conversations: Counter = field(default_factory=Counter)      # (a,b) -> bytes
    conversation_packets: Counter = field(default_factory=Counter)

    @property
    def duration(self) -> float:
        if self.first_ts is None or self.last_ts is None:
            return 0.0
        return max(0.0, self.last_ts - self.first_ts)

    @property
    def tcp_list(self) -> list:
        return sorted(self.tcp.values(), key=lambda c: c.start if c.start is not None else 0.0)


# ---- Adress-Einordnung ---------------------------------------------------------------------------------------------
def address_type(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "?"
    for net, name in DOC_NETS:
        if addr.version == net.version and addr in net:
            return f"Dokumentation ({name})"
    if str(addr) in ("255.255.255.255", "0.0.0.0"):
        return "Broadcast" if str(addr).startswith("255") else "unspezifiziert"
    if addr.is_loopback:
        return "Loopback"
    if addr.is_link_local:
        return "Link-Local"
    if addr.is_multicast:
        return "Multicast"
    if addr.is_private:
        return "privat"
    if addr.is_reserved or not addr.is_global:
        return "reserviert"
    return "öffentlich"


def mac_str(raw: bytes) -> str:
    return ":".join(f"{b:02X}" for b in raw)


def is_locally_administered(mac: str) -> bool:
    try:
        first = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return False
    return bool(first & 0x02)


# ---- Format erkennen -----------------------------------------------------------------------------------------------
def _reader(handle):
    import dpkt
    head = handle.read(4)
    handle.seek(0)
    if head == b"\x0a\x0d\x0d\x0a":
        return dpkt.pcapng.Reader(handle)
    if head in (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1"):
        return dpkt.pcap.Reader(handle)
    raise PcapError("Keine pcap-/pcapng-Datei (unbekannte Signatur)")


def analyze(path: Path, progress: Callable[[int, int], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> Summary:
    try:
        import dpkt  # noqa: F401
    except ImportError as error:
        raise PcapError("Das Paket „dpkt“ ist nicht installiert – pcap-Dateien können nicht gelesen werden.") from error
    path = Path(path)
    total = path.stat().st_size or 1
    summary = Summary()
    layers: dict[str, Layer] = {}
    echo_requests: dict[tuple, float] = {}
    dns_pending: dict[tuple, tuple] = {}      # (id, name) -> (ts, client, server)
    with open(path, "rb") as handle:
        reader = _reader(handle)
        datalink = _safe_datalink(reader)
        index = 0
        for item in _iter(reader, summary):
            if cancelled and cancelled() and index % 500 == 0:
                break
            index += 1
            ts, buf = item
            _feed(summary, layers, echo_requests, dns_pending, ts, bytes(buf), datalink)
            if progress and index % 2000 == 0:
                progress(handle.tell(), total)
    summary.layers = sorted(layers.values(), key=lambda l: (l.depth, -l.packets))
    _finalize(summary)
    if progress:
        progress(total, total)
    return summary


def _iter(reader, summary: Summary):
    it = iter(reader)
    while True:
        try:
            yield next(it)
        except StopIteration:
            return
        except Exception:                     # noqa: BLE001 – kaputtes Paket überspringen
            summary.broken += 1
            continue


def _safe_datalink(reader) -> int:
    try:
        return reader.datalink()
    except Exception:                         # noqa: BLE001
        return 1


def _layer(layers: dict, name: str, depth: int, size: int) -> None:
    entry = layers.get(name)
    if entry is None:
        entry = layers[name] = Layer(name, depth=depth)
    entry.packets += 1
    entry.bytes += size


def _host(summary: Summary, ip: str) -> HostInfo:
    host = summary.hosts.get(ip)
    if host is None:
        host = summary.hosts[ip] = HostInfo(ip, addr_type=address_type(ip))
    return host


def _feed(summary, layers, echo_requests, dns_pending, ts, buf, datalink) -> None:
    import dpkt
    summary.packets += 1
    summary.bytes += len(buf)
    summary.first_ts = ts if summary.first_ts is None else min(summary.first_ts, ts)
    summary.last_ts = ts if summary.last_ts is None else max(summary.last_ts, ts)
    try:
        frame = dpkt.ethernet.Ethernet(buf) if datalink == 1 else None
    except Exception:                         # noqa: BLE001
        frame = None
    if frame is None:
        _layer(layers, "Roh/Unbekannt", 0, len(buf))
        return
    _layer(layers, "Ethernet", 0, len(buf))
    src_mac, dst_mac = mac_str(frame.src), mac_str(frame.dst)
    data = frame.data
    if isinstance(data, dpkt.arp.ARP):
        _layer(layers, "ARP", 1, len(buf))
        _feed_arp(summary, data, src_mac)
        return
    if isinstance(data, dpkt.ip.IP):
        _layer(layers, "IPv4", 1, len(buf))
        _feed_ip(summary, layers, echo_requests, dns_pending, ts, data, src_mac, dst_mac, len(buf), dpkt)
        return
    if isinstance(data, dpkt.ip6.IP6):
        _layer(layers, "IPv6", 1, len(buf))
        _feed_ip(summary, layers, echo_requests, dns_pending, ts, data, src_mac, dst_mac, len(buf), dpkt)
        return
    _layer(layers, f"Ethertype 0x{frame.type:04X}", 1, len(buf))


def _feed_arp(summary: Summary, arp, src_mac: str) -> None:
    sender_ip, target_ip = _ip_str(arp.spa), _ip_str(arp.tpa)
    op = "Anfrage" if arp.op == 1 else "Antwort"
    entry = ArpEntry(op, sender_ip, mac_str(arp.sha), target_ip, mac_str(arp.tha) if arp.op == 2 else "",
                     gratuitous=(arp.op == 2 and sender_ip == target_ip))
    summary.arp.append(entry)
    host = _host(summary, sender_ip)
    if mac_str(arp.sha) != "00:00:00:00:00:00":
        host.macs.add(mac_str(arp.sha))


def _feed_ip(summary, layers, echo_requests, dns_pending, ts, ip, src_mac, dst_mac, size, dpkt) -> None:
    src, dst = _ip_str(ip.src), _ip_str(ip.dst)
    s_host, d_host = _host(summary, src), _host(summary, dst)
    if src_mac != "00:00:00:00:00:00":
        s_host.macs.add(src_mac)
    if dst_mac not in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        d_host.macs.add(dst_mac)
    s_host.sent_packets += 1
    s_host.sent_bytes += size
    d_host.recv_packets += 1
    d_host.recv_bytes += size
    pair = tuple(sorted((src, dst)))
    summary.conversations[pair] += size
    summary.conversation_packets[pair] += 1
    data = ip.data
    if isinstance(data, dpkt.icmp.ICMP):
        _layer(layers, "ICMP", 2, size)
        _feed_icmp(summary, echo_requests, ts, src, dst, data)
    elif isinstance(data, dpkt.udp.UDP):
        _layer(layers, "UDP", 2, size)
        if 53 in (data.sport, data.dport):
            _layer(layers, "DNS", 3, size)
            _feed_dns(summary, dns_pending, ts, src, dst, data, dpkt)
    elif isinstance(data, dpkt.tcp.TCP):
        _layer(layers, "TCP", 2, size)
        _feed_tcp(summary, layers, ts, src, dst, data, size, dpkt)


def _feed_icmp(summary, echo_requests, ts, src, dst, icmp) -> None:
    types = {0: "Echo-Antwort", 8: "Echo-Anfrage", 3: "Ziel nicht erreichbar", 11: "TTL abgelaufen",
             5: "Redirect"}
    kind = types.get(icmp.type, f"Typ {icmp.type}")
    entry = IcmpEntry(kind, src, dst)
    if icmp.type in (0, 8) and hasattr(icmp.data, "id"):
        ident, seq = icmp.data.id, icmp.data.seq
        entry.detail = f"id={ident} seq={seq}"
        if icmp.type == 8:
            echo_requests[(ident, seq)] = ts
        elif icmp.type == 0 and (ident, seq) in echo_requests:
            entry.rtt = ts - echo_requests[(ident, seq)]
    elif icmp.type == 3:
        entry.detail = {0: "Netz", 1: "Host", 3: "Port"}.get(icmp.code, f"Code {icmp.code}")
    summary.icmp.append(entry)


def _feed_dns(summary, dns_pending, ts, src, dst, udp, dpkt) -> None:
    try:
        dns = dpkt.dns.DNS(bytes(udp.data))
    except Exception:                         # noqa: BLE001
        return
    qtype = {1: "A", 28: "AAAA", 5: "CNAME", 15: "MX", 16: "TXT", 2: "NS", 12: "PTR", 6: "SOA"}
    if dns.qr == 0:                           # Anfrage
        for q in getattr(dns, "qd", []) or []:
            name = _dns_name(q.name)
            dns_pending[(dns.id, name)] = (ts, src, dst)
            summary.dns.append(DnsEntry(name, qtype.get(q.type, str(q.type)), src, dst))
        return
    for q in getattr(dns, "qd", []) or []:    # Antwort → zur Anfrage zuordnen
        name = _dns_name(q.name)
        answers = []
        for a in getattr(dns, "an", []) or []:
            value = _dns_rdata(a)
            if value:
                answers.append((value, getattr(a, "ttl", 0)))
        rcode = {0: "NOERROR", 2: "SERVFAIL", 3: "NXDOMAIN", 5: "REFUSED"}.get(dns.rcode, f"RCODE {dns.rcode}")
        key = (dns.id, name)
        entry = next((e for e in summary.dns if e.name == name and not e.answers and e.rcode == ""), None)
        if entry is None:
            entry = DnsEntry(name, qtype.get(q.type, str(q.type)), dst, src)
            summary.dns.append(entry)
        entry.answers = answers
        entry.rcode = rcode
        if key in dns_pending:
            entry.response_time = ts - dns_pending[key][0]
            entry.client, entry.server = dns_pending[key][1], dns_pending[key][2]


def _conn_key(src, sport, dst, dport):
    return tuple(sorted(((src, sport), (dst, dport))))


def _feed_tcp(summary, layers, ts, src, dst, tcp, size, dpkt) -> None:
    key = _conn_key(src, tcp.sport, dst, tcp.dport)
    conn = summary.tcp.get(key)
    if conn is None:
        conn = summary.tcp[key] = TcpConn(a=f"{src}:{tcp.sport}", b=f"{dst}:{tcp.dport}", start=ts)
    conn.packets += 1
    conn.end = ts
    conn.start = ts if conn.start is None else min(conn.start, ts)
    flags = tcp.flags
    if flags & dpkt.tcp.TH_SYN:
        conn.syn += 1
        if not (flags & dpkt.tcp.TH_ACK):
            conn.a, conn.b = f"{src}:{tcp.sport}", f"{dst}:{tcp.dport}"   # echter Initiator
    if flags & dpkt.tcp.TH_FIN:
        conn.fin += 1
    if flags & dpkt.tcp.TH_RST:
        conn.rst += 1
    payload = bytes(tcp.data)
    forward = f"{src}:{tcp.sport}" == conn.a
    if payload:
        marker = (src, tcp.sport, tcp.seq, len(payload))
        if marker in conn._seen:
            conn.retransmissions += 1
        else:
            conn._seen.add(marker)
            store = conn._ab if forward else conn._ba
            if sum(len(v) for v in store.values()) < MAX_STREAM:
                store[tcp.seq] = payload
            if forward:
                conn.bytes_ab += len(payload)
            else:
                conn.bytes_ba += len(payload)
        server_port = tcp.dport if forward else tcp.sport
        server_ip = dst if forward else src
        if server_port in HTTP_PORTS or 80 in (tcp.sport, tcp.dport):
            _layer(layers, "HTTP", 3, size)
        _feed_service(summary, server_ip, server_port)
    if 443 in (tcp.sport, tcp.dport) and payload:
        info = _tls(payload, f"{dst if forward else src}:{443}")
        if info:
            _layer(layers, "TLS", 3, size)
            summary.tls.append(info)
    for cred in extract_credentials(tcp.sport, tcp.dport, payload):
        cred.src = src
        cred.server = cred.server or (f"{dst}:{tcp.dport}" if forward else f"{src}:{tcp.sport}")
        summary.credentials.append(cred)


def _feed_service(summary, ip, port) -> None:
    if port < 1024 or port in (3389, 3306, 5432, 8080, 8443, 8000):
        from notex.core import ports as portinfo
        info = portinfo.lookup(port)
        summary.services[f"{ip}:{port}"] = info.title if info and info.title else str(port)


# ---- Nach dem Durchlauf: HTTP paaren, TCP-Status, Rollen, Befunde --------------------------------------------------
def _finalize(summary: Summary) -> None:
    for conn in summary.tcp.values():
        conn.state = _tcp_state(conn)
        _extract_http(summary, conn)
    _assign_roles(summary)
    _findings(summary)


def _tcp_state(conn: TcpConn) -> str:
    if conn.rst:
        return "per RST abgebrochen"
    if conn.syn >= 2 and conn.fin >= 1:
        return "vollständig (Handshake + FIN-Abbau)"
    if conn.syn >= 2:
        return "offen (Handshake vollständig)"
    if conn.syn == 1:
        return "halb offen (nur SYN)"
    return "unvollständig (kein Handshake im Mitschnitt)"


def _extract_http(summary: Summary, conn: TcpConn) -> None:
    req_stream = conn.stream(both=False)
    resp_stream = b"".join(conn._ba[s] for s in sorted(conn._ba))
    if not req_stream.startswith((b"GET", b"POST", b"HEAD", b"PUT", b"DELETE", b"OPTIONS", b"PATCH")):
        return
    import dpkt
    try:
        request = dpkt.http.Request(req_stream)
    except Exception:                         # noqa: BLE001
        return
    client, server = conn.a, conn.b
    exchange = HttpExchange(client, server, request.method, request.headers.get("host", server.rsplit(":", 1)[0]),
                            request.uri, request.headers.get("user-agent", ""))
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        decoded = _b64(auth.split(" ", 1)[1])
        if decoded:
            summary.credentials.append(Credential("HTTP Basic", exchange.host, decoded, client.rsplit(":", 1)[0]))
    if resp_stream.startswith(b"HTTP/"):
        try:
            response = dpkt.http.Response(resp_stream)
            exchange.status = f"{response.status} {response.reason}".strip()
            exchange.content_type = response.headers.get("content-type", "")
            exchange.content_length = response.headers.get("content-length", "")
            body = bytes(response.body)[:200]
            if body and all(32 <= b < 127 or b in (9, 10, 13) for b in body):
                exchange.body_preview = body.decode("latin-1", "replace").strip()
        except Exception:                     # noqa: BLE001
            pass
    summary.http.append(exchange)


def _assign_roles(summary: Summary) -> None:
    dns_servers = {e.server for e in summary.dns if e.answers}
    web_servers = {ex.server.rsplit(":", 1)[0] for ex in summary.http}
    web_servers |= {key.rsplit(":", 1)[0] for key, name in summary.services.items() if key.endswith((":80", ":443"))}
    arp_targets = {e.target_ip for e in summary.arp if e.op == "Anfrage"}
    clients = {e.client for e in summary.dns} | {c.a.rsplit(":", 1)[0] for c in summary.tcp.values() if c.syn}
    for ip, host in summary.hosts.items():
        if ip in dns_servers:
            host.role = "DNS-Server"
        elif ip in web_servers:
            host.role = "Webserver"
        elif ip in arp_targets or ip.endswith(".1"):
            host.role = "Gateway/Router"
        elif ip in clients:
            host.role = "Client"


def _findings(summary: Summary) -> None:
    # ARP: eine IP mit mehreren MACs (möglicher Spoofing-Hinweis)
    ip_macs: dict[str, set] = defaultdict(set)
    for entry in summary.arp:
        if entry.sender_mac and entry.sender_mac != "00:00:00:00:00:00":
            ip_macs[entry.sender_ip].add(entry.sender_mac)
    for ip, macs in ip_macs.items():
        if len(macs) > 1:
            summary.findings.append(Finding("warnung", f"IP {ip} mit mehreren MAC-Adressen ({', '.join(sorted(macs))}) "
                                            "– möglicher ARP-Spoofing-Hinweis"))
    if any(e.gratuitous for e in summary.arp):
        summary.findings.append(Finding("info", "Gratuitous ARP beobachtet (Ankündigung/Änderung einer IP-MAC-Zuordnung)"))
    # Unverschlüsselte Protokolle
    plain = sorted({name for name in summary.services.values()
                    if name in ("HTTP", "FTP", "Telnet", "POP3", "IMAP")} | ({"HTTP"} if summary.http else set()))
    if plain:
        summary.findings.append(Finding("warnung", "Unverschlüsselte Protokolle im Verkehr: " + ", ".join(plain)))
    if summary.credentials:
        summary.findings.append(Finding("warnung", f"{len(summary.credentials)} Klartext-Zugangsdaten gefunden"))
    else:
        summary.findings.append(Finding("info", "Keine Klartext-Zugangsdaten gefunden"))


# ---- TLS-SNI -------------------------------------------------------------------------------------------------------
def _tls(payload: bytes, server: str) -> TlsInfo | None:
    sni = tls_sni(payload)
    version = tls_version(payload)
    if not sni and not version:
        return None
    return TlsInfo(server, sni or "", version or "")


TLS_VERSIONS = {0x0301: "TLS 1.0", 0x0302: "TLS 1.1", 0x0303: "TLS 1.2", 0x0304: "TLS 1.3", 0x0300: "SSL 3.0"}


def tls_version(payload: bytes) -> str:
    if len(payload) >= 3 and payload[0] == 0x16:
        return TLS_VERSIONS.get((payload[1] << 8) | payload[2], "")
    return ""


def tls_sni(payload: bytes) -> str | None:
    if len(payload) < 45 or payload[0] != 0x16 or payload[5] != 0x01:
        return None
    try:
        pos = 5 + 4 + 2 + 32
        session_len = payload[pos]
        pos += 1 + session_len
        cipher_len = struct.unpack(">H", payload[pos:pos + 2])[0]
        pos += 2 + cipher_len
        comp_len = payload[pos]
        pos += 1 + comp_len
        if pos + 2 > len(payload):
            return None
        ext_total = struct.unpack(">H", payload[pos:pos + 2])[0]
        pos += 2
        end = min(len(payload), pos + ext_total)
        while pos + 4 <= end:
            ext_type, ext_len = struct.unpack(">HH", payload[pos:pos + 4])
            pos += 4
            if ext_type == 0x00:
                name_len = struct.unpack(">H", payload[pos + 3:pos + 5])[0]
                name = payload[pos + 5:pos + 5 + name_len]
                return name.decode("utf-8", "replace") if name else None
            pos += ext_len
    except (struct.error, IndexError, UnicodeError):
        return None
    return None


# ---- DNS-Helfer / IP ----------------------------------------------------------------------------------------------
def _ip_str(raw: bytes) -> str:
    try:
        return socket.inet_ntoa(raw) if len(raw) == 4 else socket.inet_ntop(socket.AF_INET6, raw)
    except (OSError, ValueError):
        return raw.hex()


def _dns_name(name) -> str:
    if isinstance(name, bytes):
        name = name.decode("utf-8", "replace")
    return str(name).strip(".")


def _dns_rdata(answer) -> str:
    try:
        rtype = getattr(answer, "type", None)
        if rtype == 1 and getattr(answer, "ip", None):
            return socket.inet_ntoa(answer.ip)
        if rtype == 28 and getattr(answer, "ip6", None):
            return socket.inet_ntop(socket.AF_INET6, answer.ip6)
        if getattr(answer, "cname", None):
            return _dns_name(answer.cname)
        if getattr(answer, "ns", None):
            return _dns_name(answer.ns)
    except (OSError, ValueError):
        return ""
    return ""


# ---- Klartext-Zugangsdaten ----------------------------------------------------------------------------------------
def _b64(text: str) -> str:
    try:
        raw = base64.b64decode(text, validate=True)
        decoded = raw.decode("utf-8", "replace")
        return decoded.replace("\x00", ":") if "\x00" in decoded else decoded
    except (binascii.Error, ValueError):
        return ""


_LINE = re.compile(rb"^([A-Za-z]+)[ \t]*(.*?)[\r\n]*$", re.M)


def extract_credentials(sport: int, dport: int, payload: bytes) -> list:
    protocol = CRED_PORTS.get(dport) or CRED_PORTS.get(sport)
    if protocol is None or not payload:
        return []
    found: list = []
    text = payload[:4096]
    if protocol == "IMAP":
        for m in re.finditer(rb"(?im)^\S+\s+LOGIN\s+(?P<rest>.+?)[\r\n]*$", text):
            found.append(Credential("IMAP", "", f"LOGIN {m.group('rest').decode('latin-1','replace').strip()}"))
        return found
    for match in _LINE.finditer(text):
        verb = match.group(1).upper()
        rest = match.group(2).decode("latin-1", "replace").strip()
        if protocol == "FTP" and verb in (b"USER", b"PASS"):
            found.append(Credential("FTP", "", f"{verb.decode()} {rest}"))
        elif protocol == "POP3" and verb in (b"USER", b"PASS"):
            found.append(Credential("POP3", "", f"{verb.decode()} {rest}"))
        elif protocol == "SMTP" and verb == b"AUTH":
            parts = rest.split()
            if len(parts) >= 2 and parts[0].upper() in ("PLAIN", "LOGIN"):
                decoded = _b64(parts[1])
                found.append(Credential("SMTP AUTH", "", f"{parts[0].upper()} {decoded or parts[1]}"))
    return found


# ---- Report ------------------------------------------------------------------------------------------------------
def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _when(ts) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "?"


def to_markdown(summary: Summary, name: str) -> str:
    lines = [f"# PCAP-Übersicht: {_cell(name)}", "",
             f"- Pakete: {summary.packets} · Bytes: {summary.bytes} · übersprungen: {summary.broken}",
             f"- Zeitraum: {_when(summary.first_ts)} – {_when(summary.last_ts)} ({summary.duration:.3f} s)", ""]
    if summary.layers:
        lines += ["## Protokoll-Hierarchie", "", "| Ebene | Protokoll | Pakete | Bytes |", "|---|---|---|---|"]
        lines += [f"| {l.depth} | {'  ' * l.depth}{_cell(l.name)} | {l.packets} | {l.bytes} |" for l in summary.layers]
        lines.append("")
    if summary.hosts:
        lines += ["## Hosts", "", "| IP | MAC | Typ | Rolle | ges. Pakete/Bytes | empf. |", "|---|---|---|---|---|---|"]
        for host in sorted(summary.hosts.values(), key=lambda h: h.ip):
            macs = ", ".join(sorted(host.macs)) or "–"
            lines.append(f"| {host.ip} | {_cell(macs)} | {host.addr_type} | {host.role} | "
                         f"{host.sent_packets}/{host.sent_bytes} | {host.recv_packets}/{host.recv_bytes} |")
        lines.append("")
    if summary.arp:
        lines += ["## ARP", "", "| Vorgang | Absender-IP | Absender-MAC | Ziel-IP | Ziel-MAC |", "|---|---|---|---|---|"]
        lines += [f"| {e.op}{' (gratuitous)' if e.gratuitous else ''} | {e.sender_ip} | {e.sender_mac} | "
                  f"{e.target_ip} | {e.target_mac or '–'} |" for e in summary.arp]
        lines.append("")
    if summary.icmp:
        lines += ["## ICMP", "", "| Typ | Von | Nach | Detail | RTT |", "|---|---|---|---|---|"]
        lines += [f"| {e.kind} | {e.src} | {e.dst} | {_cell(e.detail)} | "
                  f"{f'{e.rtt*1000:.1f} ms' if e.rtt is not None else '–'} |" for e in summary.icmp]
        lines.append("")
    if summary.dns:
        lines += ["## DNS", "", "| Name | Typ | Client | Resolver | RCODE | Antworten | Antwortzeit |",
                  "|---|---|---|---|---|---|---|"]
        for e in summary.dns:
            answers = "; ".join(f"{v} (TTL {t})" for v, t in e.answers) or "–"
            rt = f"{e.response_time*1000:.1f} ms" if e.response_time is not None else "–"
            lines.append(f"| {_cell(e.name)} | {e.qtype} | {e.client} | {e.server} | {e.rcode or '–'} | "
                         f"{_cell(answers)} | {rt} |")
        lines.append("")
    if summary.tcp:
        lines += ["## TCP-Verbindungen", "", "| A | B | Status | Dauer | Bytes A→B | B→A | Retrans |",
                  "|---|---|---|---|---|---|---|"]
        lines += [f"| {c.a} | {c.b} | {c.state} | {c.duration:.3f} s | {c.bytes_ab} | {c.bytes_ba} | "
                  f"{c.retransmissions} |" for c in summary.tcp_list]
        lines.append("")
    if summary.http:
        lines += ["## HTTP", "", "| Methode | Host | Pfad | Status | Content-Type | Länge | Antwortzeit |",
                  "|---|---|---|---|---|---|---|"]
        for e in summary.http:
            rt = f"{e.response_time*1000:.1f} ms" if e.response_time is not None else "–"
            lines.append(f"| {e.method} | {_cell(e.host)} | {_cell(e.path)} | {_cell(e.status) or '–'} | "
                         f"{_cell(e.content_type) or '–'} | {e.content_length or '–'} | {rt} |")
        lines.append("")
    if summary.tls:
        lines += ["## TLS", "", "| Server | SNI | Version | ALPN |", "|---|---|---|---|"]
        lines += [f"| {t.server} | {_cell(t.sni) or '–'} | {t.version or '–'} | {t.alpn or '–'} |" for t in summary.tls]
        lines.append("")
    if summary.services:
        lines += ["## Dienste/Ports", ""]
        lines += [f"- {addr} → {name}" for addr, name in sorted(summary.services.items())]
        lines.append("")
    if summary.credentials:
        lines += ["## ⚠ Klartext-Zugangsdaten", "", "| Protokoll | Server | Quelle | Detail |", "|---|---|---|---|"]
        lines += [f"| {c.protocol} | {_cell(c.server)} | {c.src} | {_cell(c.detail)} |" for c in summary.credentials]
        lines.append("")
    lines += ["## Befunde", ""]
    lines += [f"- {'⚠ ' if f.severity == 'warnung' else ''}{_cell(f.text)}" for f in summary.findings]
    return "\n".join(lines) + "\n"
