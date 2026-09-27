"""PCAP-Übersicht: .pcap/.pcapng streamen und zusammenfassen – Zeitraum, Pakete/Bytes, Protokolle, Top-Talker und
-Verbindungen, DNS, HTTP, TLS-SNI und im Klartext übertragene Zugangsdaten. Ohne Qt.

Bibliothek: **dpkt** (BSD-3, reines Python, MIT-verträglich) – bewusst NICHT scapy (GPL, laut Projektregel verboten).

Ehrliche Grenzen: Es gibt keine vollständige TCP-Reassemblierung – HTTP/TLS/Zugangsdaten werden je Paket aus der
Nutzlast gelesen (die Anfrage steckt fast immer im ersten Datenpaket). Verschlüsselte Inhalte werden nicht entschlüsselt;
bei TLS wird nur der SNI-Name aus dem ClientHello gelesen. Kaputte Aufzeichnungen werden übersprungen, nicht abgebrochen.
"""
from __future__ import annotations

import base64
import binascii
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_ROWS = 5000                # je Tabelle
CRED_PORTS = {21: "FTP", 23: "Telnet", 110: "POP3", 143: "IMAP", 25: "SMTP", 587: "SMTP"}


class PcapError(Exception):
    pass


@dataclass
class Credential:
    protocol: str
    server: str
    detail: str                 # z. B. "USER alice", "PASS ***", "Basic alice:geheim"
    src: str = ""


@dataclass
class Summary:
    packets: int = 0
    bytes: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    broken: int = 0
    protocols: Counter = field(default_factory=Counter)
    talkers: Counter = field(default_factory=Counter)             # IP → Bytes
    conversations: Counter = field(default_factory=Counter)       # (a,b) → Bytes
    conversation_packets: Counter = field(default_factory=Counter)
    dns_queries: Counter = field(default_factory=Counter)         # Name → Anzahl
    dns_answers: dict[str, str] = field(default_factory=dict)     # Name → erste Antwort
    http_hosts: Counter = field(default_factory=Counter)
    http_requests: list[tuple[str, str, str]] = field(default_factory=list)   # (host, pfad, user-agent)
    user_agents: Counter = field(default_factory=Counter)
    tls_sni: Counter = field(default_factory=Counter)
    credentials: list[Credential] = field(default_factory=list)

    @property
    def duration(self) -> float:
        if self.first_ts is None or self.last_ts is None:
            return 0.0
        return max(0.0, self.last_ts - self.first_ts)


# ---- Format erkennen und Reader wählen ----------------------------------------------------------------------------
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
    with open(path, "rb") as handle:
        reader = _reader(handle)
        datalink = _safe_datalink(reader)
        iterator = iter(reader)
        index = 0
        while True:
            if cancelled and cancelled() and index % 500 == 0:
                break
            try:
                ts, buf = next(iterator)
            except StopIteration:
                break
            except Exception:                    # noqa: BLE001 – kaputtes Paket überspringen, Rest weiterlesen
                summary.broken += 1
                continue
            index += 1
            _feed(summary, ts, bytes(buf), datalink)
            if progress and index % 2000 == 0:
                progress(handle.tell(), total)
    _trim(summary)
    if progress:
        progress(total, total)
    return summary


def _safe_datalink(reader) -> int:
    try:
        return reader.datalink()
    except Exception:                            # noqa: BLE001
        return 1


def _feed(summary: Summary, ts: float, buf: bytes, datalink: int) -> None:
    import dpkt
    summary.packets += 1
    summary.bytes += len(buf)
    summary.first_ts = ts if summary.first_ts is None else min(summary.first_ts, ts)
    summary.last_ts = ts if summary.last_ts is None else max(summary.last_ts, ts)
    ip = _extract_ip(buf, datalink, dpkt)
    if ip is None:
        summary.protocols["nicht-IP"] += 1
        return
    src, dst = _ip_str(ip.src), _ip_str(ip.dst)
    summary.talkers[src] += len(buf)
    summary.talkers[dst] += len(buf)
    pair = tuple(sorted((src, dst)))
    summary.conversations[pair] += len(buf)
    summary.conversation_packets[pair] += 1
    data = ip.data
    if isinstance(data, dpkt.tcp.TCP):
        _feed_tcp(summary, src, dst, data, dpkt)
    elif isinstance(data, dpkt.udp.UDP):
        _feed_udp(summary, src, dst, data, dpkt)
    elif isinstance(data, dpkt.icmp.ICMP) or isinstance(data, getattr(dpkt, "icmp6", dpkt.icmp).ICMP6
                                                         if hasattr(dpkt, "icmp6") else dpkt.icmp.ICMP):
        summary.protocols["ICMP"] += 1
    else:
        summary.protocols[type(data).__name__.upper()] += 1


def _extract_ip(buf: bytes, datalink: int, dpkt):
    try:
        if datalink == 1:                        # Ethernet
            frame = dpkt.ethernet.Ethernet(buf)
            return frame.data if isinstance(frame.data, (dpkt.ip.IP, dpkt.ip6.IP6)) else None
        if datalink in (101, 12, 14):            # RAW IP
            version = buf[0] >> 4
            return dpkt.ip.IP(buf) if version == 4 else dpkt.ip6.IP6(buf)
        if datalink == 113:                      # Linux cooked (SLL)
            frame = dpkt.sll.SLL(buf)
            return frame.data if isinstance(frame.data, (dpkt.ip.IP, dpkt.ip6.IP6)) else None
        frame = dpkt.ethernet.Ethernet(buf)      # bester Versuch
        return frame.data if isinstance(frame.data, (dpkt.ip.IP, dpkt.ip6.IP6)) else None
    except Exception:                            # noqa: BLE001
        return None


def _ip_str(raw: bytes) -> str:
    import socket
    try:
        return socket.inet_ntoa(raw) if len(raw) == 4 else socket.inet_ntop(socket.AF_INET6, raw)
    except (OSError, ValueError):
        return raw.hex()


def _service(port: int) -> str:
    from notex.core import ports as portinfo
    info = portinfo.lookup(port)
    return info.title if info and info.title else str(port)


def _feed_tcp(summary: Summary, src: str, dst: str, tcp, dpkt) -> None:
    sport, dport = tcp.sport, tcp.dport
    service = _tcp_service(sport, dport)
    summary.protocols[service] += 1
    payload = bytes(tcp.data)
    if not payload:
        return
    if dport in (80, 8080, 8000, 8081, 8088) or sport in (80, 8080, 8000, 8081, 8088):
        _feed_http(summary, src, f"{dst}:{dport}", payload, dpkt)
    if dport == 443 or sport == 443 or dport == 8443:
        sni = tls_sni(payload)
        if sni:
            summary.tls_sni[sni] += 1
    server = f"{dst}:{dport}"
    for cred in extract_credentials(sport, dport, payload):
        cred.src = src
        cred.server = cred.server or server
        summary.credentials.append(cred)


def _tcp_service(sport: int, dport: int) -> str:
    well_known = min(p for p in (sport, dport))
    if 443 in (sport, dport):
        return "HTTPS/TLS"
    if any(p in (80, 8080, 8000, 8081, 8088) for p in (sport, dport)):
        return "HTTP"
    if well_known < 1024:
        return f"TCP {_service(well_known)}"
    return "TCP (sonstige)"


def _feed_udp(summary: Summary, src: str, dst: str, udp, dpkt) -> None:
    sport, dport = udp.sport, udp.dport
    if 53 in (sport, dport):
        summary.protocols["DNS"] += 1
        _feed_dns(summary, bytes(udp.data), dpkt)
        return
    if 443 in (sport, dport):
        summary.protocols["QUIC"] += 1
        return
    summary.protocols[f"UDP {_service(min(sport, dport))}" if min(sport, dport) < 1024 else "UDP (sonstige)"] += 1


def _feed_dns(summary: Summary, data: bytes, dpkt) -> None:
    try:
        dns = dpkt.dns.DNS(data)
    except Exception:                            # noqa: BLE001
        return
    for question in getattr(dns, "qd", []) or []:
        name = _dns_name(question.name)
        if name:
            summary.dns_queries[name] += 1
    for answer in getattr(dns, "an", []) or []:
        name = _dns_name(getattr(answer, "name", ""))
        value = _dns_rdata(answer)
        if name and value and name not in summary.dns_answers:
            summary.dns_answers[name] = value


def _dns_name(name) -> str:
    if isinstance(name, bytes):
        name = name.decode("idna", "ignore") if False else name.decode("utf-8", "replace")
    return str(name).strip(".")


def _dns_rdata(answer) -> str:
    import socket
    try:
        rtype = getattr(answer, "type", None)
        if rtype == 1 and getattr(answer, "ip", None):
            return socket.inet_ntoa(answer.ip)
        if rtype == 28 and getattr(answer, "ip6", None):
            return socket.inet_ntop(socket.AF_INET6, answer.ip6)
        if getattr(answer, "cname", None):
            return _dns_name(answer.cname)
    except (OSError, ValueError):
        return ""
    return ""


def _feed_http(summary: Summary, src: str, server: str, payload: bytes, dpkt) -> None:
    if not payload[:8].lstrip().startswith((b"GET", b"POST", b"HEAD", b"PUT", b"DELETE", b"OPTIONS", b"PATCH")):
        return
    try:
        request = dpkt.http.Request(payload)
    except Exception:                            # noqa: BLE001
        return
    host = request.headers.get("host", server.split(":")[0])
    ua = request.headers.get("user-agent", "")
    summary.http_hosts[host] += 1
    if ua:
        summary.user_agents[ua] += 1
    if len(summary.http_requests) < MAX_ROWS:
        summary.http_requests.append((host, request.uri, ua))
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        decoded = _b64(auth.split(" ", 1)[1])
        if decoded:
            summary.credentials.append(Credential("HTTP Basic", f"{host}", f"{decoded}", src))


# ---- TLS-SNI ------------------------------------------------------------------------------------------------------
def tls_sni(payload: bytes) -> str | None:
    """Server-Name aus einem TLS-ClientHello lesen (robust, ohne dpkt.ssl). None, wenn keiner enthalten ist."""
    if len(payload) < 45 or payload[0] != 0x16:            # Handshake-Record
        return None
    try:
        # TLSPlaintext: type(1) version(2) length(2), dann Handshake: type(1)=ClientHello(1) length(3) ...
        if payload[5] != 0x01:
            return None
        pos = 5 + 4 + 2 + 32                                 # HS-Header + client_version + random
        if pos >= len(payload):
            return None
        session_len = payload[pos]; pos += 1 + session_len
        cipher_len = struct.unpack(">H", payload[pos:pos + 2])[0]; pos += 2 + cipher_len
        comp_len = payload[pos]; pos += 1 + comp_len
        if pos + 2 > len(payload):
            return None
        ext_total = struct.unpack(">H", payload[pos:pos + 2])[0]; pos += 2
        end = min(len(payload), pos + ext_total)
        while pos + 4 <= end:
            ext_type, ext_len = struct.unpack(">HH", payload[pos:pos + 4]); pos += 4
            if ext_type == 0x00:                            # server_name
                # server_name_list: list_len(2) type(1) name_len(2) name
                name_len = struct.unpack(">H", payload[pos + 3:pos + 5])[0]
                name = payload[pos + 5:pos + 5 + name_len]
                return name.decode("utf-8", "replace") if name else None
            pos += ext_len
    except (struct.error, IndexError, UnicodeError):
        return None
    return None


# ---- Klartext-Zugangsdaten ----------------------------------------------------------------------------------------
def _b64(text: str) -> str:
    try:
        raw = base64.b64decode(text, validate=True)
        decoded = raw.decode("utf-8", "replace")
        return decoded.replace("\x00", ":") if "\x00" in decoded else decoded
    except (binascii.Error, ValueError):
        return ""


_LINE = re.compile(rb"^([A-Za-z]+)[ \t]*(.*?)[\r\n]*$", re.M)


def extract_credentials(sport: int, dport: int, payload: bytes) -> list[Credential]:
    """Klartext-Anmeldungen aus einer TCP-Nutzlast (FTP/Telnet/POP3/IMAP/SMTP-AUTH). HTTP Basic separat."""
    protocol = CRED_PORTS.get(dport) or CRED_PORTS.get(sport)
    if protocol is None:
        return []
    found: list[Credential] = []
    text = payload[:4096]
    if protocol == "IMAP":
        for m in re.finditer(rb"(?im)^\S+\s+LOGIN\s+(?P<rest>.+?)[\r\n]*$", text):
            found.append(Credential("IMAP", "", f"LOGIN {m.group('rest').decode('latin-1','replace').strip()}"))
        return found
    for match in _LINE.finditer(text):
        verb = match.group(1).upper()
        rest = match.group(2).decode("latin-1", "replace").strip()
        if protocol in ("FTP",) and verb in (b"USER", b"PASS"):
            found.append(Credential("FTP", "", f"{verb.decode()} {rest}"))
        elif protocol == "POP3" and verb in (b"USER", b"PASS"):
            found.append(Credential("POP3", "", f"{verb.decode()} {rest}"))
        elif protocol == "IMAP" and verb == b"LOGIN":
            found.append(Credential("IMAP", "", f"LOGIN {rest}"))
        elif protocol == "SMTP" and verb == b"AUTH":
            parts = rest.split()
            if len(parts) >= 2 and parts[0].upper() in ("PLAIN", "LOGIN"):
                decoded = _b64(parts[1])
                found.append(Credential("SMTP AUTH", "", f"{parts[0].upper()} {decoded or parts[1]}"))
            else:
                found.append(Credential("SMTP AUTH", "", f"AUTH {rest}"))
        elif protocol == "SMTP" and _looks_base64(match.group(1) + match.group(2)):
            decoded = _b64((match.group(1) + match.group(2)).decode("latin-1").strip())
            if decoded and ":" in decoded or (decoded and decoded.isprintable() and len(decoded) < 80):
                found.append(Credential("SMTP AUTH", "", f"Base64 → {decoded}"))
    return found


def _looks_base64(raw: bytes) -> bool:
    token = raw.strip()
    return len(token) >= 8 and len(token) % 4 == 0 and re.fullmatch(rb"[A-Za-z0-9+/]+=*", token) is not None


# ---- Ausgabe ------------------------------------------------------------------------------------------------------
def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(summary: Summary, name: str) -> str:
    from datetime import datetime, timezone
    def when(ts):
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "?"
    lines = [f"# PCAP-Übersicht: {_cell(name)}", "",
             f"- Pakete: {summary.packets} · Bytes: {summary.bytes} · übersprungen: {summary.broken}",
             f"- Zeitraum: {when(summary.first_ts)} – {when(summary.last_ts)} ({summary.duration:.1f} s)", ""]
    if summary.protocols:
        lines += ["## Protokolle", "", "| Protokoll | Pakete |", "|---|---|"]
        lines += [f"| {_cell(p)} | {n} |" for p, n in summary.protocols.most_common(20)] + [""]
    if summary.conversations:
        lines += ["## Top-Verbindungen", "", "| A ↔ B | Pakete | Bytes |", "|---|---|---|"]
        lines += [f"| {a} ↔ {b} | {summary.conversation_packets[(a, b)]} | {byt} |"
                  for (a, b), byt in summary.conversations.most_common(15)] + [""]
    if summary.dns_queries:
        lines += ["## DNS-Anfragen", "", "| Name | Anzahl | Antwort |", "|---|---|---|"]
        lines += [f"| {_cell(name)} | {n} | {_cell(summary.dns_answers.get(name, ''))} |"
                  for name, n in summary.dns_queries.most_common(30)] + [""]
    if summary.http_hosts:
        lines += ["## HTTP-Hosts", ""] + [f"- {_cell(h)} ({n})" for h, n in summary.http_hosts.most_common(20)] + [""]
    if summary.tls_sni:
        lines += ["## TLS-SNI", ""] + [f"- {_cell(s)} ({n})" for s, n in summary.tls_sni.most_common(20)] + [""]
    if summary.credentials:
        lines += ["## ⚠ Klartext-Zugangsdaten", "", "| Protokoll | Server | Quelle | Detail |", "|---|---|---|---|"]
        lines += [f"| {_cell(c.protocol)} | {_cell(c.server)} | {c.src} | {_cell(c.detail)} |"
                  for c in summary.credentials[:100]] + [""]
    return "\n".join(lines) + "\n"


def _trim(summary: Summary) -> None:
    if len(summary.credentials) > MAX_ROWS:
        del summary.credentials[MAX_ROWS:]
