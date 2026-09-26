"""IP-Zuordnungen aus Notizen sammeln, Konflikte finden, Subnetze auswerten. Ohne Qt, ohne Netzwerk.

Erkannt werden (je Zeile, .md/.txt in data/, nie .ntx):
- Markdown-Tabellen mit einer IP-Spalte (IP, IP-Adresse, Adresse, IPv4, IPv6) und einer Namensspalte (Host,
  Hostname, Name, Gerät, System, Server, Rechner, Client),
- „IP Host“ (hosts-Datei-Stil, auch als Listenpunkt): `10.0.0.5  fileserver`,
- „Host: IP“ bzw. „Host = IP“: `fileserver: 10.0.0.5`.
Konflikt = dieselbe IP bei verschiedenen Hosts.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path

SUFFIXES = (".md", ".txt", ".markdown")
MAX_FILE = 4 * 1024 * 1024
IP_COLUMNS = {"ip", "ip-adresse", "ip adresse", "ipv4", "ipv6", "adresse", "address", "ip address", "ip-address"}
HOST_COLUMNS = {"host", "hostname", "name", "gerät", "geraet", "system", "server", "rechner", "client", "device",
                "computer", "fqdn"}
_HOST = r"[A-Za-z][\w.-]{0,62}"
_IP = r"(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})"
IP_HOST = re.compile(r"^\s*(?:[-*+]\s+)?(" + _IP + r")(?:/\d{1,3})?\s+(" + _HOST + r")\s*(?:#.*)?$")
HOST_IP = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*)?(" + _HOST + r")(?:\*\*)?\s*[:=]\s*(" + _IP + r")(?:/\d{1,3})?\s*$")
# „DNS: 10.0.0.2“ oder „Gateway: …“ beschreiben eine Rolle, keinen Hostnamen (nur für die Form „Name: IP“)
NOT_HOSTS = {"ip", "ipv4", "ipv6", "gateway", "dns", "netz", "subnetz", "subnet", "netmask", "maske", "broadcast",
             "adresse", "address", "server-ip", "von", "bis", "from", "to", "http", "https"}


@dataclass(frozen=True)
class Assignment:
    ip: str
    host: str
    file: Path
    line: int                  # 0-basiert


def _ip(text: str) -> str | None:
    text = text.strip().strip("`").split("/")[0].strip()
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def _cells(line: str) -> list[str] | None:
    text = line.strip()
    if not text.startswith("|"):
        return None
    return [c.strip() for c in re.split(r"(?<!\\)\|", text.strip("|"))]


def extract(text: str, path: Path) -> list[Assignment]:
    found: list[Assignment] = []
    columns: tuple[int, int] | None = None
    for number, line in enumerate(text.split("\n")):
        cells = _cells(line)
        if cells is not None:
            names = [c.lower().strip("* ") for c in cells]
            ip_col = next((i for i, n in enumerate(names) if n in IP_COLUMNS), None)
            host_col = next((i for i, n in enumerate(names) if n in HOST_COLUMNS), None)
            if ip_col is not None and host_col is not None:
                columns = (ip_col, host_col)
                continue
            if columns and max(columns) < len(cells):
                ip = _ip(cells[columns[0]])
                host = cells[columns[1]].strip("`* ")
                if ip and host:
                    found.append(Assignment(ip, host, path, number))
            continue
        columns = None
        match = IP_HOST.match(line)
        if match:
            ip = _ip(match.group(1))
            if ip:                                   # hosts-Stil: auch „10.0.0.2 dns“ ist ein Hostname
                found.append(Assignment(ip, match.group(2), path, number))
            continue
        match = HOST_IP.match(line)
        if match:
            ip = _ip(match.group(2))
            if ip and match.group(1).lower() not in NOT_HOSTS:
                found.append(Assignment(ip, match.group(1), path, number))
    return found


def _same_host(a: str, b: str) -> bool:
    """fileserver == FileServer == fileserver.corp.local (kurzer Name gleich)."""
    a, b = a.lower().rstrip("."), b.lower().rstrip(".")
    return a == b or a.split(".")[0] == b.split(".")[0]


def conflicts(assignments: list[Assignment]) -> dict[str, list[Assignment]]:
    """IP → alle Zuordnungen, wenn mindestens zwei verschiedene Hosts dieselbe IP haben."""
    by_ip: dict[str, list[Assignment]] = {}
    for item in assignments:
        by_ip.setdefault(item.ip, []).append(item)
    result = {}
    for ip, items in by_ip.items():
        hosts: list[str] = []
        for item in items:
            if not any(_same_host(item.host, h) for h in hosts):
                hosts.append(item.host)
        if len(hosts) > 1:
            result[ip] = items
    return result


def subnet_of(ip: str) -> str:
    """Gruppierung: IPv4 /24, IPv6 /64."""
    address = ipaddress.ip_address(ip)
    prefix = 24 if address.version == 4 else 64
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def group(assignments: list[Assignment]) -> dict[str, list[Assignment]]:
    groups: dict[str, list[Assignment]] = {}
    for item in sorted(assignments, key=lambda a: (ipaddress.ip_address(a.ip).version, ipaddress.ip_address(a.ip),
                                                   a.host.lower())):
        groups.setdefault(subnet_of(item.ip), []).append(item)
    return groups


# ---- Subnetz-Auswertung -------------------------------------------------------------------------------------------
@dataclass
class Usage:
    network: str
    total: int                          # nutzbare Adressen
    used: list[str] = field(default_factory=list)
    excluded: int = 0
    free: int = 0
    next_free: str | None = None


def parse_exclusions(text: str) -> list[tuple[int, int]]:
    """„10.0.0.100-10.0.0.199, 10.0.0.1, 10.0.0.64/28“ → [(start, ende)] als Zahlen. Wirft ValueError."""
    ranges = []
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = ipaddress.ip_address(a.strip())
            end = ipaddress.ip_address(b.strip()) if "." in b or ":" in b else \
                ipaddress.ip_address(".".join(a.strip().split(".")[:3] + [b.strip()]))
            ranges.append((int(start), int(end)))
        elif "/" in part:
            net = ipaddress.ip_network(part, strict=False)
            ranges.append((int(net.network_address), int(net.broadcast_address)))
        else:
            value = int(ipaddress.ip_address(part))
            ranges.append((value, value))
    return ranges


def usage(network_text: str, assignments: list[Assignment], exclusions: str = "") -> Usage:
    """Belegte, ausgeschlossene und freie Adressen eines Netzes; nächste freie Adresse (ab der ersten nutzbaren)."""
    network = ipaddress.ip_network(network_text.strip(), strict=False)
    excluded = parse_exclusions(exclusions)
    if network.version == 4 and network.prefixlen < 31:
        first, last = int(network.network_address) + 1, int(network.broadcast_address) - 1
    else:
        first, last = int(network.network_address), int(network.broadcast_address)
    total = max(0, last - first + 1)
    used = sorted({a.ip for a in assignments if ipaddress.ip_address(a.ip) in network}, key=ipaddress.ip_address)
    used_set = {int(ipaddress.ip_address(ip)) for ip in used}

    def is_excluded(value: int) -> bool:
        return any(s <= value <= e for s, e in excluded)
    excluded_count = sum(max(0, min(e, last) - max(s, first) + 1) for s, e in _merge(excluded))
    excluded_used = sum(1 for v in used_set if is_excluded(v))
    free = max(0, total - excluded_count - (len(used_set) - excluded_used))
    next_free = None
    value, checked = first, 0
    while value <= last and checked < 1_000_000:
        if value not in used_set and not is_excluded(value):
            next_free = str(ipaddress.ip_address(value))
            break
        value += 1
        checked += 1
    return Usage(str(network), total, used, excluded_count, free, next_free)


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# ---- Index über data/ (inkrementell) ------------------------------------------------------------------------------
class IpIndex:
    """Merkt sich je Datei (mtime, Größe) und liest nur Geänderte neu; .ntx wird nie gelesen."""

    def __init__(self, root: Path, limit: int = 5000) -> None:
        self.root = Path(root)
        self.limit = limit
        self.files: dict[Path, tuple[float, int, list[Assignment]]] = {}
        self.extra: dict[str, list[Assignment]] = {}          # weitere Quellen (z. B. Scan-Ergebnisse)

    @staticmethod
    def eligible(path: Path) -> bool:
        return path.suffix.lower() in SUFFIXES

    def refresh(self) -> int:
        """Ganzen Ordner abgleichen. Gibt die Zahl neu gelesener Dateien zurück."""
        seen, changed = set(), 0
        for path in sorted(self.root.rglob("*")):
            if len(seen) >= self.limit:
                break
            if not path.is_file() or not self.eligible(path):
                continue
            seen.add(path)
            changed += self.update_file(path)
        for gone in set(self.files) - seen:
            del self.files[gone]
        return changed

    def update_file(self, path: Path) -> int:
        path = Path(path)
        if not self.eligible(path):
            return 0
        try:
            stat = path.stat()
        except OSError:
            self.files.pop(path, None)
            return 0
        cached = self.files.get(path)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return 0
        if stat.st_size > MAX_FILE:
            self.files[path] = (stat.st_mtime, stat.st_size, [])
            return 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0
        self.files[path] = (stat.st_mtime, stat.st_size, extract(text, path))
        return 1

    def assignments(self, override: dict[Path, str] | None = None) -> list[Assignment]:
        """Alle Zuordnungen; `override` ersetzt den Inhalt einzelner Dateien (ungespeicherter Editor-Text)."""
        override = {Path(k): v for k, v in (override or {}).items() if self.eligible(Path(k))}
        items = [a for path, (_m, _s, found) in self.files.items() if path not in override for a in found]
        for path, text in override.items():
            items += extract(text, path)
        for extra in self.extra.values():
            items += extra
        return items
