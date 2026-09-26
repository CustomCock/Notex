"""Port-Infos: Offline-Verzeichnis (IANA) + eigene Tabelle gängiger Dienste mit Hinweisen, Erkennung von
Portangaben im Text. Ohne Qt, ohne Netzwerk.

Quelle der Portliste: IANA „Service Name and Transport Protocol Port Number Registry“ (RFC 6335), aufbereitet mit
tools/update_ports.py nach notex/assets/ports/iana-ports.tsv.gz. Laut gemeinsamer Erklärung von IANA und IETF (2021)
frei für jeden Zweck nutzbar (https://www.iana.org/help/licensing-terms).

Erkannt werden nur Portangaben mit Kontext – nie nackte Zahlen (Jahreszahlen, Beträge, Versionen):
  „Port 3389“, „Ports 80, 443 und 8080“, „:443“ hinter Host/IP, „3389/tcp“, „tcp/445“, „22/tcp open ssh“ (nmap).
"""
from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "assets" / "ports" / "iana-ports.tsv.gz"

# Eigene Tabelle: Name, Protokolle, Hinweis (Sicherheit/Einordnung). Kurz und sachlich.
COMMON: dict[int, tuple[str, str, str]] = {
    20: ("FTP-Daten", "tcp", "Aktiver FTP-Datenkanal; Klartext."),
    21: ("FTP", "tcp", "Klartext inkl. Passwort; anonymer Zugang häufig; besser SFTP/FTPS."),
    22: ("SSH", "tcp", "Fernzugriff/SFTP; Brute-Force-Ziel – Schlüssel statt Passwort, kein Root-Login."),
    23: ("Telnet", "tcp", "Klartext inkl. Passwort; auf Geräten oft mit Standardzugang – abschalten."),
    25: ("SMTP", "tcp", "Mailserver-zu-Mailserver; offenes Relay prüfen, VRFY/EXPN verraten Nutzer."),
    53: ("DNS", "tcp/udp", "Namensauflösung; offene Resolver → Verstärkungsangriffe, Zonentransfer (AXFR) prüfen."),
    67: ("DHCP-Server", "udp", "Adressvergabe; fremder DHCP-Server im Netz = Umleitung möglich."),
    68: ("DHCP-Client", "udp", "Antworten an Clients."),
    69: ("TFTP", "udp", "Ohne Anmeldung; oft für Netzwerkgeräte-Konfigurationen und PXE."),
    80: ("HTTP", "tcp", "Webserver ohne Verschlüsselung; Anmeldedaten im Klartext."),
    88: ("Kerberos", "tcp/udp", "Active-Directory-Anmeldung (Domänencontroller); Kerberoasting/AS-REP-Roasting."),
    110: ("POP3", "tcp", "Mailabruf im Klartext; besser 995."),
    111: ("rpcbind/portmapper", "tcp/udp", "Verzeichnis der RPC-Dienste (NFS u. a.); nach außen nie offen."),
    123: ("NTP", "udp", "Zeitsynchronisation; monlist → Verstärkungsangriffe."),
    135: ("MS-RPC Endpoint Mapper", "tcp", "Windows-RPC; Grundlage für DCOM/WMI-Fernzugriff."),
    137: ("NetBIOS-Namen", "udp", "Windows-Namensdienst; NBNS-Spoofing (Responder)."),
    138: ("NetBIOS-Datagramm", "udp", "Altes Windows-Netz."),
    139: ("NetBIOS-Sitzung (SMB)", "tcp", "SMB über NetBIOS; wie 445."),
    143: ("IMAP", "tcp", "Mailzugriff im Klartext (außer STARTTLS); besser 993."),
    161: ("SNMP", "udp", "Geräteverwaltung; v1/v2c mit Community-Strings („public“/„private“) im Klartext."),
    162: ("SNMP-Trap", "udp", "Meldungen von Geräten."),
    179: ("BGP", "tcp", "Routing zwischen Netzen; gehört nicht ins offene Internet außer zu Peers."),
    389: ("LDAP", "tcp/udp", "Verzeichnisdienst (AD); anonyme Bindung und Klartext-Anmeldung prüfen."),
    443: ("HTTPS", "tcp", "Web mit TLS; auch VPNs (SSL-VPN) und QUIC (udp/443)."),
    445: ("SMB", "tcp", "Windows-Dateifreigaben; nie ins Internet (EternalBlue, Ransomware); SMBv1 abschalten."),
    464: ("Kerberos-Passwort", "tcp/udp", "kpasswd, Domänencontroller."),
    465: ("SMTPS", "tcp", "Mailversand mit TLS (Submission)."),
    500: ("IKE (IPsec)", "udp", "VPN-Aushandlung; Aggressive Mode verrät PSK-Hashes."),
    502: ("Modbus", "tcp", "Industriesteuerung (ICS/OT); keine Anmeldung – nie aus dem Büronetz erreichbar."),
    514: ("Syslog", "udp", "Log-Versand im Klartext, ohne Absenderprüfung."),
    515: ("LPD", "tcp", "Druckdienst (alt)."),
    587: ("SMTP-Submission", "tcp", "Mailversand durch Clients mit Anmeldung (STARTTLS)."),
    623: ("IPMI", "udp", "Server-Fernwartung (BMC); IPMI 2.0 gibt Passwort-Hashes preis (RAKP)."),
    636: ("LDAPS", "tcp", "LDAP über TLS."),
    873: ("rsync", "tcp", "Dateisynchronisation; Module oft ohne Anmeldung lesbar."),
    993: ("IMAPS", "tcp", "IMAP über TLS."),
    995: ("POP3S", "tcp", "POP3 über TLS."),
    1080: ("SOCKS", "tcp", "Proxy; offen = fremder Verkehr über dein Netz."),
    1194: ("OpenVPN", "udp", "VPN."),
    1433: ("MS SQL Server", "tcp", "Datenbank; sa-Konto, xp_cmdshell."),
    1434: ("MS SQL Browser", "udp", "Listet SQL-Instanzen."),
    1521: ("Oracle TNS", "tcp", "Oracle-Datenbank-Listener."),
    1723: ("PPTP", "tcp", "Veraltetes VPN, kryptografisch gebrochen."),
    1883: ("MQTT", "tcp", "IoT-Nachrichten; oft ohne Anmeldung, Klartext (TLS: 8883)."),
    1900: ("SSDP/UPnP", "udp", "Geräteerkennung; Verstärkungsangriffe, UPnP öffnet Ports am Router."),
    2049: ("NFS", "tcp/udp", "Netzwerk-Dateisystem; Freigaben mit no_root_squash prüfen."),
    2375: ("Docker-API", "tcp", "Ohne TLS und Anmeldung = Root auf dem Host."),
    2376: ("Docker-API (TLS)", "tcp", "Docker mit TLS-Client-Zertifikaten."),
    3000: ("Entwicklungs-Webserver", "tcp", "Häufig Node.js/Grafana; oft ohne Härtung erreichbar."),
    3128: ("Squid-Proxy", "tcp", "HTTP-Proxy."),
    3268: ("AD Global Catalog", "tcp", "LDAP über den ganzen Forest."),
    3306: ("MySQL/MariaDB", "tcp", "Datenbank; nicht ins Internet."),
    3389: ("RDP", "tcp/udp", "Windows-Remotedesktop; Brute-Force/BlueKeep – nur über VPN, NLA an."),
    4444: ("Metasploit-Standard", "tcp", "Nicht registriert, aber Standardport von Metasploit-Handlern – Auffälligkeit."),
    4789: ("VXLAN", "udp", "Overlay-Netze."),
    5060: ("SIP", "tcp/udp", "VoIP-Signalisierung; Gebührenbetrug über offene Anlagen."),
    5061: ("SIP-TLS", "tcp", "SIP verschlüsselt."),
    5353: ("mDNS", "udp", "Bonjour/Avahi; verrät Gerätenamen im lokalen Netz."),
    5355: ("LLMNR", "udp", "Windows-Namensauflösung; Spoofing (Responder) → Hash-Diebstahl."),
    5432: ("PostgreSQL", "tcp", "Datenbank."),
    5601: ("Kibana", "tcp", "Elastic-Oberfläche; oft ohne Anmeldung."),
    5672: ("AMQP (RabbitMQ)", "tcp", "Nachrichtenwarteschlange; Standardkonto guest/guest."),
    5900: ("VNC", "tcp", "Bildschirmfernsteuerung; schwache/keine Passwörter häufig."),
    5985: ("WinRM (HTTP)", "tcp", "PowerShell-Remoting; mit Admin-Rechten Codeausführung."),
    5986: ("WinRM (HTTPS)", "tcp", "PowerShell-Remoting über TLS."),
    6379: ("Redis", "tcp", "Oft ohne Passwort → Daten und teils Codeausführung."),
    6443: ("Kubernetes-API", "tcp", "Cluster-Steuerung; anonymen Zugriff prüfen."),
    8080: ("HTTP-Alternative", "tcp", "Proxys, Tomcat, Admin-Oberflächen."),
    8291: ("MikroTik Winbox", "tcp", "Router-Verwaltung; nie ins Internet."),
    8443: ("HTTPS-Alternative", "tcp", "Admin-Oberflächen, Appliances."),
    8888: ("HTTP-Alternative", "tcp", "Jupyter u. a.; Token prüfen."),
    9000: ("verschieden", "tcp", "PHP-FPM, Portainer, SonarQube …"),
    9090: ("Prometheus/Cockpit", "tcp", "Monitoring bzw. Server-Verwaltung."),
    9100: ("JetDirect / node_exporter", "tcp", "Rohdruck auf Netzwerkdrucker bzw. Prometheus-Metriken."),
    9200: ("Elasticsearch", "tcp", "REST-API; ohne Security-Plugin offen lesbar."),
    10250: ("Kubelet", "tcp", "Knoten-API; anonymer Zugriff = Codeausführung in Pods."),
    11211: ("Memcached", "tcp/udp", "Ohne Anmeldung; UDP → massive Verstärkungsangriffe."),
    20000: ("DNP3", "tcp", "Fernwirktechnik (ICS/OT)."),
    27017: ("MongoDB", "tcp", "Früher standardmäßig ohne Anmeldung."),
    31337: ("„elite“", "tcp", "Klassischer Hintertür-Port (Back Orifice) – Auffälligkeit."),
    47808: ("BACnet", "udp", "Gebäudeautomation (ICS/OT)."),
    51820: ("WireGuard", "udp", "VPN."),
    102: ("S7comm (ISO-TSAP)", "tcp", "Siemens-SPS (ICS/OT); keine Anmeldung in alten Versionen."),
}
ALIASES = {"rdp": 3389, "smb": 445, "ssh": 22, "http": 80, "https": 443, "dns": 53, "ftp": 21, "telnet": 23,
           "smtp": 25, "ldap": 389, "ldaps": 636, "kerberos": 88, "winrm": 5985, "vnc": 5900, "mysql": 3306,
           "mssql": 1433, "postgres": 5432, "postgresql": 5432, "redis": 6379, "snmp": 161, "ntp": 123,
           "imap": 143, "pop3": 110, "mongodb": 27017, "docker": 2375, "elasticsearch": 9200, "nfs": 2049}


@dataclass
class PortInfo:
    port: int
    name: str = ""
    protocols: str = ""
    note: str = ""
    iana: list[tuple[str, str, str]] = field(default_factory=list)   # (Name, Protokoll, Beschreibung)

    @property
    def title(self) -> str:
        if self.name:
            return self.name
        return self.iana[0][0] if self.iana and self.iana[0][0] else ""

    def summary(self) -> str:
        head = f"Port {self.port}" + (f" · {self.title}" if self.title else "")
        return head + (f" ({self.protocols})" if self.protocols else "")


@lru_cache(maxsize=1)
def _table() -> tuple[dict[int, list[tuple[str, str, str]]], list[tuple[int, int, str, str, str]], str]:
    """Einmal geladen: Einzelports → Einträge, Bereiche, Stand."""
    single: dict[int, list[tuple[str, str, str]]] = {}
    ranges: list[tuple[int, int, str, str, str]] = []
    stand = ""
    try:
        with gzip.open(DATA, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("#"):
                    stand = line.rsplit(" ", 1)[-1].strip()
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 5:
                    continue
                start, end, proto, name, desc = int(parts[0]), int(parts[1]), parts[2], parts[3], parts[4]
                if start == end:
                    single.setdefault(start, []).append((name, proto, desc))
                else:
                    ranges.append((start, end, proto, name, desc))
    except (OSError, ValueError):
        pass
    return single, ranges, stand


def data_version() -> str:
    return _table()[2]


def lookup(port: int) -> PortInfo | None:
    if not 0 <= port <= 65535:
        return None
    single, ranges, _stand = _table()
    iana: list[tuple[str, str, str]] = []
    seen: dict[tuple[str, str], int] = {}
    for name, proto, desc in single.get(port, []) + [(n, p, d) for s, e, p, n, d in ranges if s <= port <= e]:
        key = (name, desc)
        if key in seen:                                  # tcp/udp/sctp mit gleichem Namen zusammenfassen
            i = seen[key]
            iana[i] = (name, iana[i][1] + "/" + proto, desc)
        else:
            seen[key] = len(iana)
            iana.append((name, proto, desc))
    common = COMMON.get(port)
    if common is None and not iana:
        return PortInfo(port, note="Nicht bei der IANA registriert." if port >= 1024 else "Nicht zugewiesen.")
    name, protocols, note = common or ("", "", "")
    if not protocols and iana:
        protocols = "/".join(dict.fromkeys(p for _n, ps, _d in iana for p in ps.split("/")))
    return PortInfo(port, name, protocols, note, iana)


def search(term: str, limit: int = 30) -> list[PortInfo]:
    """„3389“, „rdp“, „ms-wbt-server“ oder Teil einer Beschreibung → passende Ports."""
    term = term.strip().lower()
    if not term:
        return []
    if term.isdigit():
        info = lookup(int(term))
        return [info] if info else []
    ports: list[int] = []
    if term in ALIASES:
        ports.append(ALIASES[term])
    ports += [p for p, (name, _pr, _n) in COMMON.items() if term in name.lower() and p not in ports]
    single, _ranges, _stand = _table()
    exact = [p for p, entries in single.items() if any(n.lower() == term for n, _p, _d in entries)]
    partial = [p for p, entries in single.items() if any(term in n.lower() or term in d.lower() for n, _p, d in entries)]
    for port in sorted(exact) + sorted(partial):
        if port not in ports:
            ports.append(port)
        if len(ports) >= limit:
            break
    return [info for info in (lookup(p) for p in ports[:limit]) if info]


# ---- Erkennung im Text ------------------------------------------------------------------------------------------
_NUM = r"(\d{1,5})"
_WORD = re.compile(r"\b(?:[Pp]orts?|PORTS?)\s*(?:[:=#]\s*|Nr\.?\s*)?" + _NUM + r"\b")
_LIST = re.compile(r"\b(?:[Pp]orts|PORTS)\s*[:=]?\s*((?:\d{1,5}(?:\s*(?:,|/|und|and|&|-)\s*)?){2,40})")
_SLASH = re.compile(r"(?<![\w./])" + _NUM + r"/(tcp|udp|sctp)\b", re.I)
_PROTO = re.compile(r"\b(tcp|udp|sctp)[/:]" + _NUM + r"\b", re.I)
_HOSTPORT = re.compile(r"(?:\b(?:\d{1,3}\.){3}\d{1,3}|\]|\blocalhost|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24})"
                       r":" + _NUM + r"(?![\d:])", re.I)
_NMAP = re.compile(r"^\s*" + _NUM + r"/(tcp|udp)\s+(open|closed|filtered)", re.I)


def find_ports(line: str) -> list[tuple[int, int, int, str]]:
    """Portangaben einer Zeile → [(Start, Ende, Port, Protokoll oder "")], nach Position, ohne Überlappung."""
    hits: list[tuple[int, int, int, str]] = []

    def add(start: int, end: int, value: str, proto: str = "") -> None:
        port = int(value)
        if 0 < port <= 65535 and not any(s < end and start < e for s, e, _p, _pr in hits):
            hits.append((start, end, port, proto.lower()))

    for match in _SLASH.finditer(line):
        add(match.start(), match.end(), match.group(1), match.group(2))
    for match in _PROTO.finditer(line):
        add(match.start(), match.end(), match.group(2), match.group(1))
    for match in _HOSTPORT.finditer(line):
        add(match.start(1), match.end(1), match.group(1))
    for match in _LIST.finditer(line):
        body_start = match.start(1)
        for number in re.finditer(r"\d{1,5}", match.group(1)):
            add(body_start + number.start(), body_start + number.end(), number.group())
    for match in _WORD.finditer(line):
        add(match.start(1), match.end(1), match.group(1))
    return sorted(hits)


def port_at(line: str, column: int) -> tuple[int, str] | None:
    for start, end, port, proto in find_ports(line):
        if start <= column <= end:
            return port, proto
    return None


def to_markdown(info: PortInfo) -> str:
    lines = [f"**{info.summary()}**"]
    if info.note:
        lines.append(info.note)
    for name, proto, desc in info.iana[:6]:
        lines.append(f"- IANA: `{name or '–'}` ({proto}) – {desc}")
    return "\n".join(lines) + "\n"


def tooltip_html(info: PortInfo) -> str:
    import html
    parts = [f"<b>{html.escape(info.summary())}</b>"]
    if info.note:
        parts.append(html.escape(info.note))
    for name, proto, desc in info.iana[:4]:
        parts.append(f"<span style='opacity:.75'>IANA: {html.escape(name or '–')} ({html.escape(proto)}) – "
                     f"{html.escape(desc)}</span>")
    if len(info.iana) > 4:
        parts.append(f"<span style='opacity:.75'>… {len(info.iana) - 4} weitere IANA-Einträge</span>")
    return "<br>".join(parts)
