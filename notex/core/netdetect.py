"""Netz-Erkennung ohne Qt: eigene Subnetze aus Adaptern, Ausschlusslisten und NetBIOS-Namensabfrage.

Die Subnetz-Erkennung parst die Ausgabe von `ip -o addr` (Linux/macOS) bzw. `ipconfig` (Windows) – so bleibt sie
ohne Zusatzabhängigkeit und mit Beispielausgaben testbar. NetBIOS (UDP 137, NBSTAT) fragt bei Windows-Hosts den
Rechnernamen ab; hier stecken nur Paketbau und -auswertung (kein Netz), damit sie testbar sind.
"""
from __future__ import annotations

import ipaddress
import re
import sys
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Adapter:
    name: str
    ip: str
    cidr: str            # z. B. "192.168.1.0/24"

    @property
    def network(self):
        return ipaddress.ip_network(self.cidr, strict=False)


# ---- Subnetz-Erkennung ----------------------------------------------------------------------------

def parse_ip_addr(output: str) -> list[Adapter]:
    """`ip -o addr show` auswerten (Zeilen wie: '2: eth0 inet 192.168.1.10/24 brd ...')."""
    adapters = []
    for line in output.splitlines():
        m = re.search(r"^\d+:\s+(?P<dev>\S+)\s+inet\s+(?P<ip>\d+\.\d+\.\d+\.\d+)/(?P<pfx>\d+)", line)
        if not m:
            continue
        dev, ip, pfx = m.group("dev"), m.group("ip"), int(m.group("pfx"))
        if ip.startswith("127."):
            continue
        net = ipaddress.ip_network(f"{ip}/{pfx}", strict=False)
        adapters.append(Adapter(dev, ip, str(net)))
    return adapters


def parse_ipconfig(output: str) -> list[Adapter]:
    """Windows-`ipconfig` auswerten: IPv4-Adresse + Subnetzmaske je Adapterblock."""
    adapters = []
    current = "Adapter"
    ip = None
    for raw in output.splitlines():
        line = raw.rstrip()
        if line and not line.startswith(" "):
            current = line.strip().rstrip(":")
            ip = None
            continue
        m_ip = re.search(r"IPv4.*?:\s*(\d+\.\d+\.\d+\.\d+)", line)
        if m_ip:
            ip = m_ip.group(1)
            continue
        m_mask = re.search(r"(?:Subnet Mask|Subnetzmaske).*?:\s*(\d+\.\d+\.\d+\.\d+)", line)
        if m_mask and ip and not ip.startswith("169.254") and not ip.startswith("127."):
            try:
                net = ipaddress.ip_network(f"{ip}/{m_mask.group(1)}", strict=False)
                adapters.append(Adapter(current, ip, str(net)))
            except ValueError:
                pass
            ip = None
    return adapters


def _run(command: list[str]) -> str:
    import subprocess
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8)
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def local_adapters(runner: Callable[[list[str]], str] | None = None) -> list[Adapter]:
    """Aktive Adapter mit IPv4-Subnetz. `runner` ist für Tests austauschbar."""
    run = runner or _run
    if sys.platform.startswith("win"):
        return parse_ipconfig(run(["ipconfig"]))
    output = run(["ip", "-o", "addr", "show"])
    if output.strip():
        return parse_ip_addr(output)
    return parse_ipconfig(run(["ifconfig"]))   # macOS/alt: ifconfig ähnelt ipconfig nicht – best effort


# ---- Ausschlussliste ------------------------------------------------------------------------------

def parse_exclusions(text: str) -> set[str]:
    """Auszuschließende IPs aus Text (Zeilen/Kommas: einzelne IPs, Bereiche a-b, CIDR)."""
    out: set[str] = set()
    for token in re.split(r"[\s,;]+", text.strip()):
        if not token:
            continue
        try:
            if "/" in token:
                for ip in ipaddress.ip_network(token, strict=False).hosts():
                    out.add(str(ip))
            elif "-" in token:
                start, end = token.split("-", 1)
                start_ip = ipaddress.ip_address(start.strip())
                # „a-b" mit vollständigem Ende oder nur letztem Oktett
                if "." in end:
                    end_ip = ipaddress.ip_address(end.strip())
                else:
                    prefix = start.strip().rsplit(".", 1)[0]
                    end_ip = ipaddress.ip_address(f"{prefix}.{end.strip()}")
                cur = int(start_ip)
                while cur <= int(end_ip):
                    out.add(str(ipaddress.ip_address(cur)))
                    cur += 1
            else:
                out.add(str(ipaddress.ip_address(token)))
        except ValueError:
            continue
    return out


# ---- NetBIOS (UDP 137, NBSTAT) --------------------------------------------------------------------

def _encode_netbios_name(name: str) -> bytes:
    """NetBIOS-Level-1-Kodierung des 16-Byte-Namens (Halb-ASCII)."""
    padded = name.encode("ascii", "replace")[:16].ljust(16, b"\x00")
    encoded = bytearray()
    for byte in padded:
        encoded.append((byte >> 4) + ord("A"))
        encoded.append((byte & 0x0F) + ord("A"))
    return bytes(encoded)


def build_nbstat_request(txn_id: int = 0x4E54) -> bytes:
    """NBSTAT-Anfrage („*"-Name, Typ 0x21) – wird an UDP 137 des Zielhosts geschickt."""
    header = txn_id.to_bytes(2, "big") + b"\x00\x00" + b"\x00\x01" + b"\x00\x00\x00\x00\x00\x00"
    question = b"\x20" + _encode_netbios_name("*") + b"\x00" + b"\x00\x21" + b"\x00\x01"
    return header + question


def parse_nbstat_response(data: bytes) -> str | None:
    """Rechnernamen aus einer NBSTAT-Antwort lesen (erster eindeutiger Nicht-Gruppen-Name, Suffix 0x00)."""
    if len(data) < 57:
        return None
    # Header (12) + Frage (Name 34 + Typ 2 + Klasse 2) + Antwort (Name 34 + Typ 2 + Klasse 2 + TTL 4 + RDLEN 2)
    # RDATA beginnt mit der Zahl der Namen.
    try:
        offset = 12
        # Fragename überspringen (bis 0x00)
        while data[offset] != 0:
            offset += data[offset] + 1
        offset += 1 + 4            # Nullbyte + Typ/Klasse der Frage
        # Antwort: Name (Zeiger 0xC0.. oder Labelfolge)
        if data[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            while data[offset] != 0:
                offset += data[offset] + 1
            offset += 1
        offset += 2 + 2 + 4        # Typ + Klasse + TTL
        rdlen = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        if offset >= len(data):
            return None
        num_names = data[offset]
        offset += 1
        for _ in range(num_names):
            if offset + 18 > len(data):
                break
            name = data[offset:offset + 15].decode("ascii", "replace").strip()
            suffix = data[offset + 15]
            flags = int.from_bytes(data[offset + 16:offset + 18], "big")
            group = bool(flags & 0x8000)
            offset += 18
            if suffix == 0x00 and not group and name:
                return name
    except (IndexError, ValueError):
        return None
    return None


# ---- Wake-on-LAN ----------------------------------------------------------------------------------

def build_wol_packet(mac: str) -> bytes:
    """Magic Packet: 6× 0xFF gefolgt von 16× der 6-Byte-MAC."""
    from notex.core.oui import normalize
    norm = normalize(mac)
    if not norm:
        raise ValueError("Keine gültige MAC-Adresse")
    mac_bytes = bytes.fromhex(norm)
    return b"\xff" * 6 + mac_bytes * 16


def send_wol(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Magic Packet per UDP-Broadcast senden (weckt den Rechner, falls WoL aktiv ist)."""
    import socket
    packet = build_wol_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
