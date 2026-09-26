"""RDAP- und ASN-Abfragen für IPs, Domains und AS-Nummern. Ohne Qt; Netzwerk nur über die übergebene
fetch-Funktion (Tests laufen ohne Netz).

- Zuständiger RDAP-Server über den IANA-Bootstrap (https://data.iana.org/rdap/{ipv4,ipv6,asn,dns}.json, RFC 9224).
- ASN zu einer IP: RIPEstat Data API „prefix-overview“ (https://stat.ripe.net) – frei, ohne Schlüssel, weltweite
  BGP-Sicht aus RIPE RIS; der AS-Name kommt zusätzlich per RDAP „autnum“.
- Private, reservierte und Dokumentations-Adressen werden lokal erkannt und NIE abgefragt.
- Sitzungs-Cache (nur im Speicher), Mindestabstand je Host, 429/Retry-After wird beachtet, Zeitlimit je Anfrage.
"""
from __future__ import annotations

import ipaddress
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

BOOTSTRAP = "https://data.iana.org/rdap/{kind}.json"
RIPESTAT = "https://stat.ripe.net/data/prefix-overview/data.json?resource={ip}&sourceapp=notex"
TIMEOUT = 10
MIN_INTERVAL = 1.0          # Sekunden zwischen zwei Anfragen an denselben Host
USER_AGENT = "Notex (RDAP-Abfrage auf Nutzerwunsch)"

Fetch = Callable[[str], tuple[int, dict, bytes]]     # URL → (Status, Header, Body)


class RdapError(Exception):
    pass


class LocalAddress(RdapError):
    """Private/reservierte Adresse – wird nicht abgefragt."""


@dataclass
class Card:
    kind: str                                  # ip | asn | domain
    query: str
    title: str = ""
    fields: list[tuple[str, str]] = field(default_factory=list)
    source: str = ""                           # RDAP-URL
    notes: list[str] = field(default_factory=list)

    def add(self, label: str, value) -> None:
        text = str(value).strip() if value is not None else ""
        if text:
            self.fields.append((label, text))

    def get(self, label: str) -> str:
        return next((v for k, v in self.fields if k == label), "")


# ---- Einordnung ohne Netz -----------------------------------------------------------------------------------------
SPECIAL = [
    ("100.64.0.0/10", "Carrier-Grade-NAT (RFC 6598)"), ("192.0.2.0/24", "Dokumentation (RFC 5737)"),
    ("198.51.100.0/24", "Dokumentation (RFC 5737)"), ("203.0.113.0/24", "Dokumentation (RFC 5737)"),
    ("2001:db8::/32", "Dokumentation (RFC 3849)"), ("198.18.0.0/15", "Benchmark-Netz (RFC 2544)"),
    ("fc00::/7", "Unique Local (RFC 4193)"),
]


def local_reason(ip) -> str | None:
    """Grund, warum eine Adresse nicht öffentlich ist (→ keine Abfrage), sonst None."""
    address = ipaddress.ip_address(ip) if not isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address)) else ip
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return local_reason(address.ipv4_mapped)
    for net, reason in SPECIAL:
        if address in ipaddress.ip_network(net):
            return reason
    if address.is_loopback:
        return "Loopback"
    if address.is_link_local:
        return "Link-Local"
    if address.is_multicast:
        return "Multicast"
    if address.is_unspecified:
        return "unspezifiziert"
    if address.is_reserved:
        return "reserviert"
    if address.is_private:
        return "privat (RFC 1918)" if address.version == 4 else "privat"
    if not address.is_global:
        return "reserviert"
    return None


_ASN = re.compile(r"^(?:AS)?(\d{1,10})$", re.I)
_DOMAIN = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)


def classify(query: str) -> tuple[str, object]:
    """„8.8.8.8“, „2001:4860::8888“, „AS13335“, „example.com“ (auch entschärft: example[.]com) → (Art, Wert)."""
    text = query.strip().strip("[]").replace("[.]", ".").replace("(.)", ".").replace("[:]", ":").rstrip(".")
    try:
        address = ipaddress.ip_address(text.split("%")[0])
        return "ip", address
    except ValueError:
        pass
    match = _ASN.match(text)
    if match and text.upper().startswith("AS"):
        return "asn", int(match.group(1))
    if _DOMAIN.match(text):
        return "domain", text.lower()
    raise RdapError(f"„{query.strip()[:60]}“ ist weder IP, Domain noch AS-Nummer (z. B. AS13335)")


# ---- Bootstrap ----------------------------------------------------------------------------------------------------
def server_for(kind: str, value, bootstrap: dict) -> str | None:
    """Basis-URL des zuständigen RDAP-Servers aus der Bootstrap-Datei (RFC 9224)."""
    services = bootstrap.get("services", [])
    best, best_len = None, -1
    for entry in services:
        if len(entry) < 2 or not entry[1]:
            continue
        keys, urls = entry[0], entry[1]
        url = next((u for u in urls if u.startswith("https://")), urls[0])
        for key in keys:
            if kind == "ip":
                try:
                    net = ipaddress.ip_network(key, strict=False)
                except ValueError:
                    continue
                if value.version == net.version and value in net and net.prefixlen > best_len:
                    best, best_len = url, net.prefixlen
            elif kind == "asn":
                low, _, high = key.partition("-")
                if low.isdigit() and int(low) <= value <= int(high or low):
                    return url
            elif kind == "domain":
                tld = value.rsplit(".", 1)[-1]
                if key.lower() == tld:
                    return url
    return best


# ---- Auswertung der RDAP-Antworten --------------------------------------------------------------------------------
def _vcard(entity: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    card = entity.get("vcardArray")
    if isinstance(card, list) and len(card) > 1:
        for item in card[1]:
            if not isinstance(item, list) or len(item) < 4:
                continue
            name, value = item[0], item[3]
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if v)
            if name in ("fn", "email", "tel", "adr", "org") and value and name not in out:
                out[name] = str(value).replace("\n", ", ")
            if name == "adr" and isinstance(item[1], dict) and item[1].get("label") and "adr" not in out:
                out["adr"] = item[1]["label"].replace("\n", ", ")
    return out


def _entities(data: dict, depth: int = 0):
    for entity in data.get("entities", []) or []:
        if isinstance(entity, dict):
            yield entity
            if depth < 3:
                yield from _entities(entity, depth + 1)


def _by_role(data: dict, role: str) -> list[dict]:
    return [e for e in _entities(data) if role in (e.get("roles") or [])]


def _events(data: dict) -> dict[str, str]:
    names = {"registration": "Registriert", "last changed": "Zuletzt geändert", "expiration": "Läuft ab"}
    out = {}
    for event in data.get("events", []) or []:
        action = event.get("eventAction")
        if action in names and event.get("eventDate"):
            out[names[action]] = event["eventDate"][:10]
    return out


def _add_common(card: Card, data: dict) -> None:
    for role, label in (("registrant", "Inhaber"), ("administrative", "Admin-Kontakt")):
        for entity in _by_role(data, role)[:1]:
            info = _vcard(entity)
            card.add(label, info.get("fn") or info.get("org") or entity.get("handle"))
            if role == "registrant" and info.get("adr"):
                card.add("Adresse", info["adr"])
    abuse = _by_role(data, "abuse")
    if abuse:
        info = _vcard(abuse[0])
        card.add("Abuse-Kontakt", " · ".join(v for v in (info.get("email"), info.get("tel")) if v)
                 or info.get("fn") or abuse[0].get("handle"))
    for label, date in _events(data).items():
        card.add(label, date)
    for remark in (data.get("remarks") or [])[:2]:
        text = " ".join(remark.get("description") or [])[:300] if isinstance(remark, dict) else ""
        if text:
            card.notes.append(text)


def parse_ip(query: str, data: dict) -> Card:
    card = Card("ip", query, data.get("name") or data.get("handle") or "")
    cidrs = []
    for item in data.get("cidr0_cidrs", []) or []:
        prefix = item.get("v4prefix") or item.get("v6prefix")
        if prefix is not None and item.get("length") is not None:
            cidrs.append(f"{prefix}/{item['length']}")
    if not cidrs and data.get("startAddress") and data.get("endAddress"):
        try:
            nets = ipaddress.summarize_address_range(ipaddress.ip_address(data["startAddress"]),
                                                     ipaddress.ip_address(data["endAddress"]))
            cidrs = [str(n) for n in nets][:4]
        except (ValueError, TypeError):
            cidrs = [f"{data['startAddress']} – {data['endAddress']}"]
    card.add("Netzblock", ", ".join(cidrs))
    card.add("Name", data.get("name"))
    card.add("Handle", data.get("handle"))
    card.add("Typ", data.get("type"))
    card.add("Land", data.get("country"))
    _add_common(card, data)
    return card


def parse_autnum(query: str, data: dict) -> Card:
    start, end = data.get("startAutnum"), data.get("endAutnum")
    number = f"AS{start}" if start == end or not end else f"AS{start}–AS{end}"
    card = Card("asn", query, data.get("name") or number)
    card.add("ASN", number)
    card.add("AS-Name", data.get("name"))
    card.add("Land", data.get("country"))
    _add_common(card, data)
    return card


def parse_domain(query: str, data: dict) -> Card:
    card = Card("domain", query, (data.get("ldhName") or query).lower())
    card.add("Domain", (data.get("ldhName") or "").lower())
    registrar = _by_role(data, "registrar")
    if registrar:
        card.add("Registrar", _vcard(registrar[0]).get("fn") or registrar[0].get("handle"))
    card.add("Status", ", ".join(data.get("status") or []))
    card.add("Nameserver", ", ".join((ns.get("ldhName") or "").lower() for ns in data.get("nameservers", []) or []))
    card.add("DNSSEC", "ja" if (data.get("secureDNS") or {}).get("delegationSigned") else "")
    _add_common(card, data)
    return card


def parse_ripestat(data: dict) -> tuple[str, list[tuple[int, str]]]:
    """prefix-overview → (announciertes Präfix, [(ASN, Inhaber)])."""
    inner = data.get("data") or {}
    asns = [(int(a["asn"]), a.get("holder") or "") for a in inner.get("asns", []) or [] if str(a.get("asn", "")).isdigit()]
    return inner.get("resource") or "", asns


# ---- Client -------------------------------------------------------------------------------------------------------
def urllib_fetch(url: str) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(url, headers={"Accept": "application/rdap+json, application/json",
                                                   "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, dict(response.headers), response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), b""
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RdapError(f"Keine Verbindung: {getattr(error, 'reason', error)}") from error


class Client:
    def __init__(self, fetch: Fetch = urllib_fetch, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.fetch = fetch
        self.sleep = sleep
        self.clock = clock
        self.cache: dict[str, object] = {}         # URL → JSON (nur für diese Sitzung)
        self.bootstrap: dict[str, dict] = {}
        self.last_request: dict[str, float] = {}

    def _get(self, url: str) -> dict:
        if url in self.cache:
            return self.cache[url]
        host = url.split("/")[2]
        wait = MIN_INTERVAL - (self.clock() - self.last_request.get(host, -1e9))
        if wait > 0:
            self.sleep(wait)
        for attempt in range(2):
            self.last_request[host] = self.clock()
            status, headers, body = self.fetch(url)
            if status == 429 and attempt == 0:
                retry = headers.get("Retry-After") or headers.get("retry-after") or "2"
                delay = float(retry) if str(retry).isdigit() else 2.0
                if delay > 30:
                    raise RdapError(f"{host}: Anfragelimit erreicht – bitte in {int(delay)} s erneut versuchen")
                self.sleep(delay)
                continue
            break
        if status == 404:
            raise RdapError("Nicht gefunden (404) – für diese Angabe gibt es keinen RDAP-Eintrag")
        if status == 429:
            raise RdapError(f"{host}: Anfragelimit erreicht – später erneut versuchen")
        if status >= 400 or not body:
            raise RdapError(f"{host} antwortet mit Status {status}")
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError as error:
            raise RdapError(f"{host}: Antwort ist kein JSON") from error
        self.cache[url] = data
        return data

    def _server(self, kind: str, value) -> str:
        table = {"ip": f"ipv{value.version}" if kind == "ip" else "", "asn": "asn", "domain": "dns"}[kind]
        if table not in self.bootstrap:
            self.bootstrap[table] = self._get(BOOTSTRAP.format(kind=table))
        server = server_for(kind, value, self.bootstrap[table])
        if not server:
            raise RdapError("Kein zuständiger RDAP-Server im IANA-Bootstrap")
        return server if server.endswith("/") else server + "/"

    def lookup(self, query: str, with_asn: bool = True) -> Card:
        kind, value = classify(query)
        if kind == "ip":
            reason = local_reason(value)
            if reason:
                raise LocalAddress(f"{value} ist {reason} – wird nicht abgefragt")
            url = f"{self._server('ip', value)}ip/{value}"
            card = parse_ip(str(value), self._get(url))
            card.source = url
            if with_asn:
                self._add_asn(card, value)
            return card
        if kind == "asn":
            url = f"{self._server('asn', value)}autnum/{value}"
            card = parse_autnum(f"AS{value}", self._get(url))
        else:
            url = f"{self._server('domain', value)}domain/{value}"
            card = parse_domain(value, self._get(url))
        card.source = url
        return card

    def _add_asn(self, card: Card, address) -> None:
        try:
            prefix, asns = parse_ripestat(self._get(RIPESTAT.format(ip=address)))
        except RdapError as error:
            card.notes.append(f"ASN nicht ermittelt: {error}")
            return
        if prefix:
            card.add("BGP-Präfix", prefix)
        if not asns:
            card.notes.append("Kein AS announciert dieses Präfix (laut RIPEstat)")
            return
        for asn, holder in asns[:3]:
            name = holder
            try:
                autnum = self.lookup(f"AS{asn}")
                name = autnum.get("AS-Name") or holder
                if autnum.get("Land"):
                    name += f" ({autnum.get('Land')})"
            except RdapError:
                pass
            card.add("ASN", f"AS{asn} – {name}" if name else f"AS{asn}")


def to_markdown(card: Card) -> str:
    def cell(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")
    lines = [f"**RDAP: {cell(card.query)}**" + (f" – {cell(card.title)}" if card.title and card.title != card.query else ""),
             "", "| Feld | Wert |", "|---|---|"]
    lines += [f"| {cell(k)} | {cell(v)} |" for k, v in card.fields]
    if card.source:
        lines += ["", f"Quelle: <{card.source}> (abgefragt {time.strftime('%Y-%m-%d %H:%M')})"]
    return "\n".join(lines) + "\n"


def needs_confirmation(path) -> bool:
    """Abfragen aus verschlüsselten Notizen erst nach Rückfrage – der Wert verlässt sonst unbemerkt den Rechner."""
    return str(path).lower().endswith(".ntx")


_AS_TOKEN = re.compile(r"\bAS\d{1,10}\b")


def token_at(line: str, column: int) -> str | None:
    """IP, Domain (auch aus URL/E-Mail, auch entschärft) oder AS-Nummer an einer Spalte der Zeile."""
    from notex.core import ioc
    plain, _count = ioc.refang(line)
    if plain != line:                          # entschärft: Spalte grob über den Anteil abbilden
        column = round(column * len(plain) / max(1, len(line)))
        line = plain
    for match in _AS_TOKEN.finditer(line):
        if match.start() <= column <= match.end():
            return match.group()
    for start, end, kind in ioc._spans(line, False):
        if not start <= column <= end:
            continue
        value = line[start:end]
        if kind == "url":
            host = value.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].rsplit("@", 1)[-1]
            if host.startswith("["):
                return host[1:].split("]", 1)[0]
            return host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        if kind == "email":
            return value.split("@", 1)[1]
        return value.split("%", 1)[0]
    return None
