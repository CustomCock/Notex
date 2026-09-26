import ipaddress
import json

import pytest

from notex.core import rdap

BOOT_V4 = {"services": [[["8.0.0.0/8", "104.16.0.0/12"], ["http://rdap.arin.net/registry/", "https://rdap.arin.net/registry/"]],
                        [["193.0.0.0/8"], ["https://rdap.db.ripe.net/"]]]}
BOOT_ASN = {"services": [[["13312-18431"], ["https://rdap.arin.net/registry/"]]]}
BOOT_DNS = {"services": [[["com", "net"], ["https://rdap.verisign.com/com/v1/"]]]}

IP_ANSWER = {
    "handle": "NET-8-8-8-0-2", "name": "GOGL", "type": "DIRECT ALLOCATION", "country": "US",
    "startAddress": "8.8.8.0", "endAddress": "8.8.8.255",
    "cidr0_cidrs": [{"v4prefix": "8.8.8.0", "length": 24}],
    "events": [{"eventAction": "registration", "eventDate": "2014-03-14T16:52:05-04:00"},
               {"eventAction": "last changed", "eventDate": "2014-03-14T16:52:05-04:00"}],
    "entities": [
        {"roles": ["registrant"], "handle": "GOGL",
         "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "Google LLC"],
                                  ["adr", {"label": "1600 Amphitheatre Parkway\nMountain View"}, "text", ""]]],
         "entities": [{"roles": ["abuse"], "handle": "ABUSE5250-ARIN",
                       "vcardArray": ["vcard", [["fn", {}, "text", "Abuse"],
                                                ["email", {}, "text", "network-abuse@google.com"],
                                                ["tel", {}, "text", "+1-650-253-0000"]]]}]}],
}
AUTNUM = {"startAutnum": 15169, "endAutnum": 15169, "name": "GOOGLE", "country": "US"}
RIPESTAT = {"data": {"resource": "8.8.8.0/24", "asns": [{"asn": 15169, "holder": "GOOGLE - Google LLC"}]}}
DOMAIN = {"ldhName": "EXAMPLE.COM", "status": ["client delete prohibited"],
          "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}], "secureDNS": {"delegationSigned": True},
          "events": [{"eventAction": "expiration", "eventDate": "2027-08-13T04:00:00Z"}],
          "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "RESERVED-IANA"]]]}]}


class FakeNet:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                if isinstance(answer, tuple):
                    return answer
                return 200, {}, json.dumps(answer).encode()
        return 404, {}, b""


def client(routes) -> tuple[rdap.Client, FakeNet, list[float]]:
    net, sleeps = FakeNet(routes), []
    clock = iter(range(0, 10_000, 5))                     # jede Anfrage 5 s später → kein Warten nötig
    return rdap.Client(net, sleeps.append, lambda: next(clock)), net, sleeps


ROUTES = {
    "https://data.iana.org/rdap/ipv4.json": BOOT_V4, "https://data.iana.org/rdap/asn.json": BOOT_ASN,
    "https://data.iana.org/rdap/dns.json": BOOT_DNS, "https://rdap.arin.net/registry/ip/8.8.8.8": IP_ANSWER,
    "https://rdap.arin.net/registry/autnum/15169": AUTNUM, "https://stat.ripe.net/": RIPESTAT,
    "https://rdap.verisign.com/com/v1/domain/example.com": DOMAIN,
}


@pytest.mark.parametrize("ip,reason", [
    ("10.1.2.3", "privat (RFC 1918)"), ("192.168.178.1", "privat (RFC 1918)"), ("127.0.0.1", "Loopback"),
    ("169.254.1.1", "Link-Local"), ("100.64.1.1", "Carrier-Grade-NAT (RFC 6598)"),
    ("203.0.113.5", "Dokumentation (RFC 5737)"), ("224.0.0.1", "Multicast"), ("fe80::1", "Link-Local"),
    ("fd00::1", "Unique Local (RFC 4193)"), ("2001:db8::1", "Dokumentation (RFC 3849)"), ("0.0.0.0", "unspezifiziert"),
    ("240.0.0.1", "reserviert"), ("::ffff:192.168.1.1", "privat (RFC 1918)"), ("8.8.8.8", None),
    ("2606:4700::1111", None),
])
def test_local_reason(ip: str, reason) -> None:
    assert rdap.local_reason(ip) == reason


def test_local_addresses_never_queried() -> None:
    c, net, _ = client(ROUTES)
    with pytest.raises(rdap.LocalAddress):
        c.lookup("192.168.1.10")
    with pytest.raises(rdap.LocalAddress):
        c.lookup("203.0.113.5")
    assert net.calls == []


def test_classify() -> None:
    assert rdap.classify("8.8.8.8") == ("ip", ipaddress.ip_address("8.8.8.8"))
    assert rdap.classify(" AS13335 ") == ("asn", 13335)
    assert rdap.classify("evil[.]example[.]com") == ("domain", "evil.example.com")
    assert rdap.classify("[2001:db8::1]")[0] == "ip"
    for bad in ("13335", "hallo", "999.1.1.1", ""):
        with pytest.raises(rdap.RdapError):
            rdap.classify(bad)


def test_bootstrap_longest_prefix_https() -> None:
    boot = {"services": [[["8.0.0.0/8"], ["https://a/"]], [["8.8.0.0/16"], ["http://b/", "https://b/"]]]}
    assert rdap.server_for("ip", ipaddress.ip_address("8.8.8.8"), boot) == "https://b/"
    assert rdap.server_for("ip", ipaddress.ip_address("9.9.9.9"), boot) is None
    assert rdap.server_for("asn", 15169, BOOT_ASN) == "https://rdap.arin.net/registry/"
    assert rdap.server_for("domain", "x.example.com", BOOT_DNS).startswith("https://rdap.verisign.com")


def test_ip_lookup_with_asn_and_cache() -> None:
    c, net, _ = client(ROUTES)
    card = c.lookup("8.8.8.8")
    assert card.get("Netzblock") == "8.8.8.0/24" and card.get("Inhaber") == "Google LLC"
    assert card.get("Land") == "US" and card.get("Registriert") == "2014-03-14"
    assert card.get("Abuse-Kontakt") == "network-abuse@google.com · +1-650-253-0000"
    assert card.get("Adresse") == "1600 Amphitheatre Parkway, Mountain View"
    assert card.get("BGP-Präfix") == "8.8.8.0/24" and card.get("ASN") == "AS15169 – GOOGLE (US)"
    count = len(net.calls)
    c.lookup("8.8.8.8")
    assert len(net.calls) == count                         # Sitzungs-Cache
    md = rdap.to_markdown(card)
    assert md.startswith("**RDAP: 8.8.8.8** – GOGL") and "| Netzblock | 8.8.8.0/24 |" in md


def test_domain_and_asn_lookup() -> None:
    c, _net, _ = client(ROUTES)
    domain = c.lookup("example.com")
    assert domain.get("Registrar") == "RESERVED-IANA" and domain.get("Nameserver") == "a.iana-servers.net"
    assert domain.get("DNSSEC") == "ja" and domain.get("Läuft ab") == "2027-08-13"
    assert c.lookup("AS15169").get("AS-Name") == "GOOGLE"


def test_rate_limit_and_errors() -> None:
    answers = iter([(429, {"Retry-After": "3"}, b""), (200, {}, json.dumps(AUTNUM).encode())])
    routes = dict(ROUTES)
    net = FakeNet(routes)
    sleeps: list[float] = []
    c = rdap.Client(lambda url: next(answers) if "autnum" in url else net(url), sleeps.append, lambda: 0.0)
    assert c.lookup("AS15169").get("ASN") == "AS15169" and 3.0 in sleeps
    limited = {k: v for k, v in ROUTES.items() if "autnum" not in k}
    c2, _n, _ = client({**limited, "https://rdap.arin.net/registry/autnum/": (429, {"Retry-After": "120"}, b"")})
    with pytest.raises(rdap.RdapError, match="Anfragelimit"):
        c2.lookup("AS15169")
    broken = {k: v for k, v in ROUTES.items() if "/ip/" not in k}
    c3, _n, _ = client({**broken, "https://rdap.arin.net/registry/ip/": (200, {}, b"<html>")})
    with pytest.raises(rdap.RdapError, match="kein JSON"):
        c3.lookup("8.8.4.4")
    c4, _n, _ = client(ROUTES)
    with pytest.raises(rdap.RdapError, match="404"):
        c4.lookup("AS15170")


def test_min_interval_between_requests_same_host() -> None:
    net, sleeps = FakeNet(ROUTES), []
    c = rdap.Client(net, sleeps.append, lambda: 100.0)      # Uhr steht → zweite Anfrage muss warten
    c.lookup("AS15169")
    assert sleeps == []                                    # verschiedene Hosts
    c.lookup("8.8.8.8", with_asn=False)                    # wieder rdap.arin.net → Mindestabstand
    assert sleeps and 0 < sleeps[-1] <= rdap.MIN_INTERVAL


def test_asn_failure_is_a_note_not_an_error() -> None:
    routes = {k: v for k, v in ROUTES.items() if "stat.ripe.net" not in k}
    c, _n, _ = client(routes)
    card = c.lookup("8.8.8.8")
    assert card.get("Inhaber") == "Google LLC" and any("ASN nicht ermittelt" in n for n in card.notes)


def test_ntx_needs_confirmation() -> None:
    assert rdap.needs_confirmation("geheim.NTX") and not rdap.needs_confirmation("notiz.md")


@pytest.mark.parametrize("line,column,expected", [
    ("Verbindung zu 8.8.8.8:53 gesehen", 16, "8.8.8.8"),
    ("C2 http://evil.example.com:8080/gate.php", 12, "evil.example.com"),
    ("Absender admin@mail.example.org", 12, "mail.example.org"),
    ("Netz von AS13335 und 1.1.1.1", 11, "AS13335"),
    ("entschärft evil[.]example[.]com", 14, "evil.example.com"),
    ("nichts hier", 3, None),
])
def test_token_at(line: str, column: int, expected) -> None:
    assert rdap.token_at(line, column) == expected
