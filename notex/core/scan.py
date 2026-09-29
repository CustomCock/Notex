"""Netzwerk-Scanner für das eigene Netz: Ziele auflösen, Hosts finden, offene TCP-Ports per Connect prüfen,
Banner lesen. Ohne Qt. Auf Windows und Linux identisch (asyncio), ohne Admin-Rechte.

**Ehrliche Grenzen** (was dieser Scanner NICHT kann):
- Nur TCP-*Connect*-Scan (vollständiger Handshake) – kein SYN-/Stealth-Scan (bräuchte Rohsockets = Admin).
- Keine Betriebssystem-Erkennung, kein Fingerprinting.
- UDP wird nicht gescannt (ohne Antwort nicht von „offen“ unterscheidbar; bräuchte protokolleigene Probes).
- „Host aktiv?“ ist heuristisch: System-`ping` (kann geblockt sein) plus TCP-Anklopfen an einigen Ports; eine Firewall,
  die alles verwirft, lässt einen Host tot wirken. Offene Ports gelten immer als Beleg, dass der Host lebt.
- ARP-/MAC-Adressen nur für das lokale Segment und nur aus der schon vorhandenen System-ARP-Tabelle (kein aktives ARP).

Gedacht für das eigene Netz. Ziele außerhalb privater Bereiche verlangen in der Oberfläche eine Bestätigung.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable

# Kleine Standardprofile (nur zur Auswahl; eigene Portlisten sind möglich)
TOP_100 = [7, 20, 21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 161, 179, 199, 389, 443, 445, 465, 514, 515, 543,
           544, 548, 554, 587, 631, 636, 646, 873, 990, 993, 995, 1025, 1026, 1027, 1433, 1521, 1723, 1883, 2049,
           2181, 2375, 3000, 3128, 3268, 3306, 3389, 3690, 4444, 4789, 5000, 5060, 5432, 5601, 5672, 5900, 5985,
           6379, 6443, 6667, 7001, 8000, 8008, 8080, 8081, 8088, 8443, 8888, 9000, 9042, 9090, 9100, 9200, 9300,
           10000, 11211, 27017, 50000]
_TOP_1000_EXTRA = list(range(1, 1025))                     # 1–1024 deckt die meisten registrierten Dienste ab
TOP_1000 = sorted(set(TOP_100) | set(_TOP_1000_EXTRA) | {1433, 1521, 1883, 2049, 2375, 3000, 3306, 3389, 5432, 5900,
                                                         5985, 6379, 6443, 8080, 8443, 9200, 11211, 27017})
PROFILES = {"top100": TOP_100, "top1000": TOP_1000}

MAX_TARGETS = 4096                 # mehr Hosts nur nach ausdrücklicher Bestätigung
MAX_PORTS = 65535
DEFAULT_CONCURRENCY = 200
DEFAULT_TIMEOUT = 1.0
BANNER_PORTS = {21, 22, 23, 25, 110, 143, 587, 3306, 6379}     # Dienste, die von sich aus einen Gruß schicken
HTTP_PORTS = {80, 8000, 8008, 8080, 8081, 8088, 8443, 443, 9200, 5601, 9090}


class ScanError(Exception):
    pass


# ---- Ziele ---------------------------------------------------------------------------------------------------------
@dataclass
class Target:
    ip: str
    label: str = ""            # Hostname, wie eingegeben (für die Anzeige)


def _expand_range(text: str) -> list[str]:
    """„10.0.0.1-10.0.0.20“ oder „10.0.0.1-20“ → Liste von IPv4. Wirft ValueError."""
    left, right = text.split("-", 1)
    start = ipaddress.IPv4Address(left.strip())
    right = right.strip()
    end = ipaddress.IPv4Address(right) if "." in right else \
        ipaddress.IPv4Address(".".join(left.strip().split(".")[:3] + [right]))
    if int(end) < int(start):
        raise ValueError(f"Bereich rückwärts: {text}")
    return [str(ipaddress.IPv4Address(v)) for v in range(int(start), int(end) + 1)]


def parse_targets(text: str, resolver: Callable[[str], list[str]] | None = None,
                  limit: int = MAX_TARGETS) -> tuple[list[Target], list[str]]:
    """Zieltext (IP, Hostname, CIDR, Bereich, Liste – getrennt durch Komma/Leerzeichen/Zeile) → (Ziele, Warnungen).

    Hostnamen werden über `resolver` (Standard: DNS) aufgelöst. Doppelte IPs fallen weg (erste Beschriftung gewinnt).
    Überschreitet die Zahl `limit`, wird abgeschnitten und gewarnt.
    """
    resolver = resolver or _default_resolver
    seen: dict[str, Target] = {}
    warnings: list[str] = []
    for token in re.split(r"[\s,]+", text.strip()):
        if not token:
            continue
        try:
            expanded = _expand_token(token, resolver)
        except ValueError as error:
            warnings.append(str(error))
            continue
        for ip, label in expanded:
            if ip not in seen:
                seen[ip] = Target(ip, label)
            if len(seen) >= limit:
                warnings.append(f"Mehr als {limit} Ziele – Liste abgeschnitten (Obergrenze anheben oder Netz teilen).")
                return list(seen.values()), warnings
    return list(seen.values()), warnings


def _expand_token(token: str, resolver: Callable[[str], list[str]]) -> list[tuple[str, str]]:
    if "/" in token:
        network = ipaddress.ip_network(token, strict=False)
        hosts = network.hosts() if network.num_addresses > 2 else network
        return [(str(ip), "") for ip in hosts]
    if "-" in token and re.match(r"^[\d.]+-[\d.]+$", token):
        return [(ip, "") for ip in _expand_range(token)]
    try:
        return [(str(ipaddress.ip_address(token.strip("[]"))), "")]
    except ValueError:
        pass
    ips = resolver(token)
    if not ips:
        raise ValueError(f"Name nicht auflösbar: {token}")
    return [(ip, token) for ip in ips]


def _default_resolver(name: str) -> list[str]:
    import socket
    try:
        infos = socket.getaddrinfo(name, None)
    except (socket.gaierror, socket.herror, OSError):
        return []
    return list(dict.fromkeys(info[4][0] for info in infos))


def is_private(ip: str) -> bool:
    address = ipaddress.ip_address(ip)
    return address.is_private or address.is_loopback or address.is_link_local


def all_private(targets: Iterable[Target]) -> bool:
    return all(is_private(t.ip) for t in targets)


def parse_ports(text: str) -> list[int]:
    """„22,80,443“, „1-1024“, „top100“, „top1000“, gemischt → sortierte, eindeutige Portliste. Wirft ValueError."""
    text = text.strip().lower()
    if text in PROFILES:
        return list(PROFILES[text])
    ports: set[int] = set()
    for token in re.split(r"[\s,]+", text):
        if not token:
            continue
        if token in PROFILES:
            ports.update(PROFILES[token])
        elif "-" in token:
            low, high = token.split("-", 1)
            lo, hi = int(low), int(high)
            if not (0 < lo <= hi <= MAX_PORTS):
                raise ValueError(f"Portbereich ungültig: {token}")
            ports.update(range(lo, hi + 1))
        else:
            port = int(token)
            if not 0 < port <= MAX_PORTS:
                raise ValueError(f"Port ungültig: {token}")
            ports.add(port)
    if not ports:
        raise ValueError("Keine Ports angegeben")
    return sorted(ports)


# ---- Ergebnisse ----------------------------------------------------------------------------------------------------
@dataclass
class OpenPort:
    port: int
    service: str = ""
    banner: str = ""


@dataclass
class Host:
    ip: str
    hostname: str = ""            # aus Reverse-DNS oder Eingabe
    mac: str = ""
    alive: bool = False
    reason: str = ""             # warum „aktiv“ (ping / tcp / arp)
    ports: list[OpenPort] = field(default_factory=list)

    @property
    def open_ports(self) -> list[int]:
        return [p.port for p in self.ports]


# ---- Banner --------------------------------------------------------------------------------------------------------
def clean_banner(data: bytes, limit: int = 200) -> str:
    text = data.decode("latin-1", "replace")
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def http_summary(data: bytes) -> str:
    text = data.decode("latin-1", "replace")
    server = re.search(r"(?im)^server:\s*(.+)$", text)
    status = re.match(r"HTTP/\d\.\d\s+(\d{3}[^\r\n]*)", text)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    parts = []
    if status:
        parts.append(status.group(1).strip())
    if server:
        parts.append(f"Server: {server.group(1).strip()}")
    if title:
        clean_title = re.sub(r"\s+", " ", title.group(1)).strip()[:60]
        parts.append(f"„{clean_title}“")
    return " · ".join(parts)[:200]


# ---- Scan-Engine (asyncio) ----------------------------------------------------------------------------------------
# Verbindungsfunktion: (ip, port, timeout) -> (reader, writer) oder wirft. Für Tests austauschbar.
Connector = Callable[[str, int, float], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


async def _default_connect(ip: str, port: int, timeout: float):
    return await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)


async def _close_writer(writer, timeout: float) -> None:
    """Verbindung schließen – immer mit Timeout. Unter Windows (ProactorEventLoop) kann wait_closed sonst hängen."""
    try:
        writer.close()
    except (OSError, ConnectionError, RuntimeError):
        return
    try:
        await asyncio.wait_for(writer.wait_closed(), timeout)
    except (OSError, asyncio.TimeoutError, ConnectionError, RuntimeError):
        pass
    except Exception:                       # noqa: BLE001 – Schließen darf den Scan nie stoppen
        pass


async def _probe_port(ip: str, port: int, timeout: float, grab_banner: bool, connect: Connector) -> OpenPort | None:
    try:
        reader, writer = await connect(ip, port, timeout)
    except (OSError, asyncio.TimeoutError, ConnectionError):
        return None
    except Exception:                       # noqa: BLE001 – exotische Loop-Fehler nie den Scan abbrechen lassen
        return None
    result = OpenPort(port, service_name(port))
    try:
        if grab_banner:
            result.banner = await _grab(ip, port, reader, writer, timeout)
    except (OSError, asyncio.TimeoutError, ConnectionError, UnicodeError):
        pass
    finally:
        await _close_writer(writer, timeout)
    return result


async def _grab(ip: str, port: int, reader, writer, timeout: float) -> str:
    if port in HTTP_PORTS or port not in BANNER_PORTS:
        if port in HTTP_PORTS:
            writer.write(f"GET / HTTP/1.0\r\nHost: {ip}\r\nUser-Agent: Notex\r\nConnection: close\r\n\r\n"
                         .encode("latin-1"))
            await asyncio.wait_for(writer.drain(), timeout)
            data = await asyncio.wait_for(reader.read(4096), timeout)
            summary = http_summary(data)
            return summary or clean_banner(data)
        return ""
    data = await asyncio.wait_for(reader.read(256), timeout)     # SSH/FTP/SMTP/… schicken von sich aus einen Gruß
    return clean_banner(data)


async def scan_host(ip: str, ports: list[int], *, timeout: float = DEFAULT_TIMEOUT,
                    concurrency: int = DEFAULT_CONCURRENCY, grab_banner: bool = True,
                    connect: Connector = _default_connect,
                    cancelled: Callable[[], bool] | None = None,
                    on_port: Callable[[str, OpenPort], None] | None = None) -> list[OpenPort]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(port: int):
        if cancelled and cancelled():       # Abbruch greift auch während laufender Port-Probes
            return None
        async with semaphore:
            if cancelled and cancelled():
                return None
            result = await _probe_port(ip, port, timeout, grab_banner, connect)
        if result and on_port:
            on_port(ip, result)
        return result
    results = await asyncio.gather(*(one(port) for port in ports))
    return sorted((r for r in results if r), key=lambda p: p.port)


@dataclass
class ScanConfig:
    ports: list[int]
    timeout: float = DEFAULT_TIMEOUT
    concurrency: int = DEFAULT_CONCURRENCY
    grab_banner: bool = True
    discover: bool = True          # erst prüfen, ob der Host lebt (spart Zeit bei großen Bereichen)
    reverse_dns: bool = True
    use_ping: bool = False         # zusätzlich System-ping bei der Host-Erkennung (kann geblockt sein)
    resolve_timeout: float = 2.0   # Reverse-DNS je Host, läuft in einem Thread (blockiert den Loop nie)


async def scan(targets: list[Target], config: ScanConfig, *, connect: Connector = _default_connect,
               resolver: Callable[[str], str | None] | None = None,
               pinger: Callable[[str], bool] | None = None,
               progress: Callable[[int, int], None] | None = None,
               cancelled: Callable[[], bool] | None = None,
               on_host: Callable[[Host], None] | None = None) -> list[Host]:
    """Alle Ziele scannen. Hosts der Reihe nach (je Host die Ports parallel), damit Fortschritt und Abbruch greifen."""
    hosts: list[Host] = []
    total = len(targets)
    host_semaphore = asyncio.Semaphore(max(1, min(64, config.concurrency // 4 or 1)))
    resolve_cache: dict[str, str] = {}
    lookup = resolver or _reverse_dns

    async def resolve(ip: str) -> str:
        if ip in resolve_cache:
            return resolve_cache[ip]
        loop = asyncio.get_event_loop()
        try:                                  # synchroner Namensdienst → Thread + Timeout, blockiert den Loop nie
            name = await asyncio.wait_for(loop.run_in_executor(None, lookup, ip), config.resolve_timeout)
        except (asyncio.TimeoutError, OSError, Exception):    # noqa: BLE001
            name = None
        resolve_cache[ip] = name or ""
        return resolve_cache[ip]

    async def do(index: int, target: Target) -> Host:
        async with host_semaphore:
            if cancelled and cancelled():
                raise asyncio.CancelledError()
            host = Host(target.ip, target.label)
            probe_ports = config.ports
            if config.discover:
                alive, reason = await _discover(target.ip, config, connect)
                if not alive and config.use_ping and pinger is not None:
                    loop = asyncio.get_event_loop()
                    if await loop.run_in_executor(None, pinger, target.ip):
                        alive, reason = True, "ping"
                host.alive, host.reason = alive, reason
                if not alive:
                    probe_ports = []
            host.ports = await scan_host(target.ip, probe_ports, timeout=config.timeout,
                                         concurrency=config.concurrency, grab_banner=config.grab_banner,
                                         connect=connect, cancelled=cancelled)
            if host.ports:
                host.alive = True
                host.reason = host.reason or "offener Port"
            if config.reverse_dns and not host.hostname and (host.alive or host.ports):
                host.hostname = await resolve(target.ip)
            return host

    tasks = [asyncio.ensure_future(do(i, t)) for i, t in enumerate(targets)]
    done = 0
    try:
        for task in asyncio.as_completed(tasks):
            host = await task
            hosts.append(host)
            done += 1
            if on_host:
                on_host(host)
            if progress:
                progress(done, total)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        raise
    hosts.sort(key=lambda h: ipaddress.ip_address(h.ip))
    return hosts


async def _discover(ip: str, config: ScanConfig, connect: Connector) -> tuple[bool, str]:
    """TCP-Anklopfen an einigen üblichen Ports; der erste offene belegt „lebt“."""
    knock = [p for p in (443, 80, 22, 445, 3389, 135, 139) if p in config.ports] or config.ports[:6]
    timeout = min(config.timeout, 1.0)
    for port in knock:
        try:
            _reader, writer = await connect(ip, port, timeout)
        except (OSError, asyncio.TimeoutError, ConnectionError):
            continue
        except Exception:                   # noqa: BLE001
            continue
        await _close_writer(writer, timeout)
        return True, f"TCP {port} offen"
    return False, "keine Antwort (kann auch eine Firewall sein)"


def _reverse_dns(ip: str) -> str | None:
    import socket
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None


def service_name(port: int) -> str:
    from notex.core import ports as portinfo
    info = portinfo.lookup(port)
    return info.title if info else ""


# ---- System-ping (robust geparst) ---------------------------------------------------------------------------------
_PING_ALIVE = re.compile(r"(?i)\b(\d+)\s*(?:bytes|ttl=|time[=<]|zeit[=<])")
_PING_LOSS = re.compile(r"(\d+)%\s*(?:packet loss|Verlust|loss|perdu)")


def ping_alive(output: str, returncode: int) -> bool:
    """System-`ping`-Ausgabe robust deuten (Linux/Windows/macOS, deutsch/englisch). Rückgabe: Host antwortet?"""
    if "ttl=" in output.lower() or "zeit=" in output.lower() or "time=" in output.lower():
        loss = _PING_LOSS.search(output)
        if loss and int(loss.group(1)) >= 100:
            return False
        return True
    return returncode == 0 and "100%" not in output and "unreachable" not in output.lower() \
        and "nicht erreichbar" not in output.lower()


def system_ping(ip: str, timeout: float = 1.0,
                runner: Callable[[list[str]], tuple[int, str]] | None = None) -> bool:
    """Einmal `ping` aufrufen (kein Admin nötig). `runner` ist für Tests austauschbar."""
    count_flag = "-n" if sys.platform.startswith("win") else "-c"
    wait_flag = "-w" if sys.platform.startswith("win") else "-W"
    wait_value = str(int(timeout * 1000)) if sys.platform.startswith("win") else str(max(1, int(timeout)))
    command = ["ping", count_flag, "1", wait_flag, wait_value, ip]
    run = runner or _run_command
    try:
        code, output = run(command)
    except (OSError, subprocess.SubprocessError, ValueError):   # ValueError: u. a. UnicodeDecodeError
        return False
    return ping_alive(output, code)


TRACE_HOPS = 15
TRACE_TIMEOUT = 90.0             # Sekunden – 15 Hops × 3 Proben × 1 s Warten + Puffer


def traceroute_command(ip: str, platform: str | None = None) -> list[str]:
    """Plattformgerechter Traceroute-Befehl (Windows: tracert, sonst traceroute), numerisch, max. 15 Hops."""
    if (platform or sys.platform).startswith("win"):
        return ["tracert", "-d", "-h", str(TRACE_HOPS), "-w", "1000", ip]
    return ["traceroute", "-n", "-m", str(TRACE_HOPS), "-w", "1", ip]


def traceroute(ip: str, runner: Callable[[list[str]], tuple[int, str]] | None = None) -> str:
    """Traceroute ausführen und die Ausgabe als Text liefern. Fehlt das Programm, eine verständliche Meldung."""
    from notex.core import syscmd
    command = traceroute_command(ip)
    run = runner or (lambda cmd: syscmd.run(cmd, timeout=TRACE_TIMEOUT))
    try:
        _code, output = run(command)
    except FileNotFoundError:
        hint = "" if sys.platform.startswith("win") else " (Paket „traceroute“ installieren)"
        return f"„{command[0]}“ ist auf diesem System nicht vorhanden{hint}."
    except subprocess.TimeoutExpired:
        return f"Keine vollständige Antwort innerhalb von {int(TRACE_TIMEOUT)} s."
    return output.strip() or "Keine Ausgabe."


def _run_command(command: list[str]) -> tuple[int, str]:
    from notex.core import syscmd
    return syscmd.run(command, timeout=10)      # OEM-Codepage unter Windows, siehe core/syscmd.py


# ---- ARP-Tabelle des Systems -------------------------------------------------------------------------------------
_MAC = r"([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})"
_ARP_UNIX = re.compile(r"(\d+\.\d+\.\d+\.\d+).*?" + _MAC)                       # arp -a / ip neigh
_ARP_WIN = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+" + _MAC)


def parse_arp(output: str) -> dict[str, str]:
    """ARP-Ausgabe (Linux `ip neigh`/`arp -n`, Windows `arp -a`, macOS `arp -a`) → {IP: MAC (Doppelpunkte, groß)}."""
    table: dict[str, str] = {}
    for pattern in (_ARP_UNIX, _ARP_WIN):
        for ip, mac in pattern.findall(output):
            mac = mac.replace("-", ":").upper()
            if mac != "00:00:00:00:00:00" and ip not in table:
                table[ip] = mac
    return table


def arp_table(runner: Callable[[list[str]], tuple[int, str]] | None = None) -> dict[str, str]:
    """Vorhandene ARP-Tabelle des Systems auslesen (kein aktives ARP, keine Admin-Rechte)."""
    run = runner or _run_command
    commands = [["ip", "neigh"], ["arp", "-a"]] if not sys.platform.startswith("win") else [["arp", "-a"]]
    for command in commands:
        try:
            _code, output = run(command)
        except (OSError, subprocess.SubprocessError):
            continue
        table = parse_arp(output)
        if table:
            return table
    return {}


# ---- Speichern, Report, Vergleich ---------------------------------------------------------------------------------
import json          # noqa: E402
import time          # noqa: E402


def to_dict(hosts: list[Host], config: ScanConfig, targets_text: str = "") -> dict:
    return {
        "notex_scan": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "targets": targets_text,
        "config": {"ports": config.ports, "timeout": config.timeout, "concurrency": config.concurrency,
                   "grab_banner": config.grab_banner, "discover": config.discover},
        "hosts": [{"ip": h.ip, "hostname": h.hostname, "mac": h.mac, "alive": h.alive, "reason": h.reason,
                   "ports": [{"port": p.port, "service": p.service, "banner": p.banner} for p in h.ports]}
                  for h in hosts],
    }


def from_dict(data: dict) -> list[Host]:
    hosts = []
    for item in data.get("hosts", []):
        host = Host(item["ip"], item.get("hostname", ""), item.get("mac", ""), bool(item.get("alive")),
                    item.get("reason", ""))
        host.ports = [OpenPort(p["port"], p.get("service", ""), p.get("banner", "")) for p in item.get("ports", [])]
        hosts.append(host)
    return hosts


def load(text: str) -> list[Host]:
    data = json.loads(text)
    if data.get("notex_scan") != 1:
        raise ScanError("Keine Notex-Scan-Datei")
    return from_dict(data)


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown_report(hosts: list[Host], config: ScanConfig, targets_text: str = "") -> str:
    alive = [h for h in hosts if h.alive or h.ports]
    lines = [f"# Netzwerk-Scan {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"- Ziele: `{_cell(targets_text)}`" if targets_text else "- Ziele: (Liste)",
             f"- Ports je Host: {len(config.ports)} · Timeout {config.timeout:g} s · {len(hosts)} Ziele, "
             f"{len(alive)} aktiv",
             "- TCP-Connect-Scan (kein SYN/OS-Erkennung, kein UDP).", "",
             "| Host | Name | MAC | Offene Ports | Dienste / Banner |", "|---|---|---|---|---|"]
    for host in sorted(alive, key=lambda h: ipaddress.ip_address(h.ip)):
        ports = ", ".join(str(p.port) for p in host.ports) or "–"
        services = "; ".join(f"{p.port} {p.service}".strip() + (f" – {p.banner}" if p.banner else "")
                             for p in host.ports)
        lines.append(f"| {host.ip} | {_cell(host.hostname)} | {_cell(host.mac)} | {ports} | {_cell(services)} |")
    if not alive:
        lines.append("| – | – | – | – | keine aktiven Hosts |")
    return "\n".join(lines) + "\n"


@dataclass
class Diff:
    new_hosts: list[str] = field(default_factory=list)
    gone_hosts: list[str] = field(default_factory=list)
    opened: dict[str, list[int]] = field(default_factory=dict)      # IP → neu offene Ports
    closed: dict[str, list[int]] = field(default_factory=dict)      # IP → nicht mehr offene Ports
    banner_changed: dict[str, list[tuple[int, str, str]]] = field(default_factory=dict)   # IP → (Port, alt, neu)

    @property
    def empty(self) -> bool:
        return not (self.new_hosts or self.gone_hosts or self.opened or self.closed or self.banner_changed)


def _active(hosts: list[Host]) -> dict[str, Host]:
    return {h.ip: h for h in hosts if h.alive or h.ports}


def compare(old: list[Host], new: list[Host]) -> Diff:
    """Zwei Scans vergleichen: neue/verschwundene Hosts, neu geöffnete/geschlossene Ports, geänderte Banner."""
    old_map, new_map = _active(old), _active(new)
    diff = Diff(new_hosts=sorted(set(new_map) - set(old_map), key=ipaddress.ip_address),
                gone_hosts=sorted(set(old_map) - set(new_map), key=ipaddress.ip_address))
    for ip in sorted(set(old_map) & set(new_map), key=ipaddress.ip_address):
        old_ports = {p.port: p for p in old_map[ip].ports}
        new_ports = {p.port: p for p in new_map[ip].ports}
        opened = sorted(set(new_ports) - set(old_ports))
        closed = sorted(set(old_ports) - set(new_ports))
        if opened:
            diff.opened[ip] = opened
        if closed:
            diff.closed[ip] = closed
        changes = [(port, old_ports[port].banner, new_ports[port].banner)
                   for port in sorted(set(old_ports) & set(new_ports))
                   if old_ports[port].banner != new_ports[port].banner]
        if changes:
            diff.banner_changed[ip] = changes
    return diff


def diff_to_markdown(diff: Diff) -> str:
    if diff.empty:
        return "Keine Änderungen gegenüber dem vorigen Scan.\n"
    lines = ["## Änderungen zum vorigen Scan", ""]
    if diff.new_hosts:
        lines.append(f"- **Neue Hosts:** {', '.join(diff.new_hosts)}")
    if diff.gone_hosts:
        lines.append(f"- **Verschwundene Hosts:** {', '.join(diff.gone_hosts)}")
    for ip, ports in diff.opened.items():
        lines.append(f"- {ip}: **neu offen** {', '.join(map(str, ports))}")
    for ip, ports in diff.closed.items():
        lines.append(f"- {ip}: **geschlossen** {', '.join(map(str, ports))}")
    for ip, changes in diff.banner_changed.items():
        for port, old, new in changes:
            lines.append(f"- {ip}:{port} Banner: „{_cell(old)}“ → „{_cell(new)}“")
    return "\n".join(lines) + "\n"


def as_ip_note(hosts: list[Host]) -> str:
    """Scan-Ergebnis als Zeitleisten-/IP-tauglicher Notiztext (für Modul IP-Konflikte)."""
    lines = ["| Host | IP | Offene Ports |", "|---|---|---|"]
    for host in sorted(_active(hosts).values(), key=lambda h: ipaddress.ip_address(h.ip)):
        name = host.hostname or "?"
        lines.append(f"| {_cell(name)} | {host.ip} | {', '.join(map(str, host.open_ports)) or '–'} |")
    return "\n".join(lines) + "\n"
