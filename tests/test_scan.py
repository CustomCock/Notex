import asyncio

import pytest

from notex.core import scan


def run(coro):
    return asyncio.run(coro)


# ---- Ziele und Ports ----------------------------------------------------------------------------------------------
def test_parse_targets_forms() -> None:
    resolver = lambda name: {"host.example": ["192.168.1.9"], "dual.example": ["10.0.0.1", "10.0.0.2"]}.get(name, [])
    targets, warnings = scan.parse_targets("10.0.0.1, 10.0.0.0/30 192.168.1.10-192.168.1.12 host.example",
                                           resolver=resolver)
    ips = [t.ip for t in targets]
    assert "10.0.0.1" in ips and "10.0.0.2" in ips                 # /30 → .1,.2 (Netz/Broadcast weg), .1 dedupe
    assert "192.168.1.10" in ips and "192.168.1.12" in ips and "192.168.1.9" in ips
    assert next(t for t in targets if t.ip == "192.168.1.9").label == "host.example"
    assert warnings == []


def test_parse_targets_range_short_and_errors() -> None:
    targets, _ = scan.parse_targets("10.0.0.5-8")
    assert [t.ip for t in targets] == ["10.0.0.5", "10.0.0.6", "10.0.0.7", "10.0.0.8"]
    _t, warnings = scan.parse_targets("nixda.invalid", resolver=lambda n: [])
    assert warnings and "nicht auflösbar" in warnings[0]


def test_parse_targets_limit() -> None:
    targets, warnings = scan.parse_targets("10.0.0.0/16", limit=50)
    assert len(targets) == 50 and any("abgeschnitten" in w for w in warnings)


def test_private_detection() -> None:
    priv, _ = scan.parse_targets("192.168.1.0/30 10.0.0.1 127.0.0.1")
    assert scan.all_private(priv)
    pub, _ = scan.parse_targets("192.168.1.1 8.8.8.8")
    assert not scan.all_private(pub)


def test_parse_ports() -> None:
    assert scan.parse_ports("22,80,443") == [22, 80, 443]
    assert scan.parse_ports("20-22, 80") == [20, 21, 22, 80]
    assert scan.parse_ports("top100") == sorted(scan.TOP_100)
    assert 443 in scan.parse_ports("top1000") and len(scan.parse_ports("top1000")) == len(scan.TOP_1000)
    for bad in ("", "0", "70000", "50-40", "abc"):
        with pytest.raises(ValueError):
            scan.parse_ports(bad)


# ---- Banner -------------------------------------------------------------------------------------------------------
def test_banner_helpers() -> None:
    assert scan.clean_banner(b"SSH-2.0-OpenSSH_9.6\r\n\x00") == "SSH-2.0-OpenSSH_9.6"
    http = b"HTTP/1.1 200 OK\r\nServer: nginx/1.25\r\n\r\n<html><title>Login  Seite</title>"
    summary = scan.http_summary(http)
    assert "200 OK" in summary and "nginx/1.25" in summary and "Login Seite" in summary


# ---- Scan mit Fake-Verbindung -------------------------------------------------------------------------------------
class FakeWriter:
    def __init__(self) -> None:
        self.buffer = b""

    def write(self, data: bytes) -> None:
        self.buffer += data

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


class FakeReader:
    def __init__(self, data: bytes) -> None:
        self.data = data

    async def read(self, n: int) -> bytes:
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk


def make_connect(open_ports: dict[str, dict[int, bytes]]):
    async def connect(ip: str, port: int, timeout: float):
        banners = open_ports.get(ip, {})
        if port not in banners:
            raise ConnectionRefusedError()
        return FakeReader(banners[port]), FakeWriter()
    return connect


def test_scan_host_reports_open_ports_with_banner() -> None:
    connect = make_connect({"10.0.0.5": {22: b"SSH-2.0-OpenSSH_9.6\r\n", 80: b"HTTP/1.1 200 OK\r\nServer: nginx\r\n\r\n",
                                         3306: b"J\x00\x00\x00\n8.0.36\x00"}})
    ports = run(scan.scan_host("10.0.0.5", [22, 80, 443, 3306], connect=connect, timeout=0.5))
    got = {p.port: p for p in ports}
    assert set(got) == {22, 80, 3306}
    assert got[22].banner.startswith("SSH-2.0-OpenSSH") and got[22].service == "SSH"
    assert "nginx" in got[80].banner and got[443] if 443 in got else True


def test_full_scan_with_discovery_and_progress() -> None:
    connect = make_connect({"10.0.0.5": {80: b"HTTP/1.0 200 OK\r\n\r\n"}, "10.0.0.7": {22: b"SSH-2.0-x\r\n"}})
    targets = [scan.Target(f"10.0.0.{n}") for n in (5, 6, 7)]
    config = scan.ScanConfig(ports=[22, 80, 443], timeout=0.3, reverse_dns=True)
    seen = []
    hosts = run(scan.scan(targets, config, connect=connect, resolver=lambda ip: f"name-{ip.split('.')[-1]}",
                          progress=lambda d, t: seen.append((d, t))))
    alive = {h.ip: h for h in hosts if h.alive}
    assert set(alive) == {"10.0.0.5", "10.0.0.7"} and alive["10.0.0.5"].hostname == "name-5"
    assert alive["10.0.0.7"].open_ports == [22] and seen[-1] == (3, 3)
    dead = next(h for h in hosts if h.ip == "10.0.0.6")
    assert not dead.alive and dead.ports == []


def test_scan_cancel() -> None:
    async def slow_connect(ip, port, timeout):
        await asyncio.sleep(0.05)
        raise ConnectionRefusedError()
    targets = [scan.Target(f"10.0.0.{n}") for n in range(1, 40)]
    config = scan.ScanConfig(ports=[80], timeout=0.3, discover=False)
    with pytest.raises(asyncio.CancelledError):
        run(scan.scan(targets, config, connect=slow_connect, cancelled=lambda: True))


# ---- ping / arp Parsing -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("output,code,expected", [
    ("64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.5 ms", 0, True),
    ("Antwort von 10.0.0.1: Bytes=32 Zeit=1ms TTL=128", 0, True),
    ("Request timed out.\r\n100% packet loss", 1, False),
    ("5 packets transmitted, 0 received, 100% packet loss", 1, False),
    ("Destination Host Unreachable", 1, False),
    ("Ziel-Host nicht erreichbar", 1, False),
])
def test_ping_alive(output: str, code: int, expected: bool) -> None:
    assert scan.ping_alive(output, code) is expected


def test_system_ping_uses_runner() -> None:
    calls = []
    assert scan.system_ping("10.0.0.1", runner=lambda cmd: (calls.append(cmd), (0, "ttl=64 time=1ms"))[1])
    assert "10.0.0.1" in calls[0]
    assert not scan.system_ping("10.0.0.2", runner=lambda cmd: (_ for _ in ()).throw(OSError()))


def test_parse_arp_formats() -> None:
    unix = "10.0.0.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n10.0.0.2 dev eth0 lladdr 11-22-33-44-55-66 STALE"
    win = "Internet Address      Physical Address      Type\n  10.0.0.1          aa-bb-cc-dd-ee-ff     dynamic\n" \
          "  10.0.0.9          00-00-00-00-00-00     invalid"
    assert scan.parse_arp(unix) == {"10.0.0.1": "AA:BB:CC:DD:EE:FF", "10.0.0.2": "11:22:33:44:55:66"}
    assert scan.parse_arp(win) == {"10.0.0.1": "AA:BB:CC:DD:EE:FF"}      # Nulladresse übersprungen


# ---- Speichern, Report, Vergleich ---------------------------------------------------------------------------------
def sample() -> list[scan.Host]:
    a = scan.Host("10.0.0.5", "nas", "AA:BB:CC:00:11:22", True, "TCP 445 offen")
    a.ports = [scan.OpenPort(445, "SMB"), scan.OpenPort(80, "HTTP", "Server: nginx")]
    b = scan.Host("10.0.0.7", "", "", True, "offener Port")
    b.ports = [scan.OpenPort(22, "SSH", "SSH-2.0-OpenSSH_9.6")]
    return [a, b]


def test_roundtrip_and_report() -> None:
    config = scan.ScanConfig(ports=[22, 80, 445])
    data = scan.to_dict(sample(), config, "10.0.0.0/24")
    import json
    restored = scan.load(json.dumps(data))
    assert [h.ip for h in restored] == ["10.0.0.5", "10.0.0.7"] and restored[0].ports[0].port == 445
    report = scan.to_markdown_report(sample(), config, "10.0.0.0/24")
    assert "| 10.0.0.5 | nas | AA:BB:CC:00:11:22 | 445, 80 |" in report and "nginx" in report
    with pytest.raises(scan.ScanError):
        scan.load('{"foo": 1}')


def test_compare() -> None:
    old = sample()
    new = sample()
    new[0].ports = [scan.OpenPort(445, "SMB"), scan.OpenPort(3389, "RDP")]          # 80 zu, 3389 neu
    new[1].ports[0] = scan.OpenPort(22, "SSH", "SSH-2.0-OpenSSH_9.7")                # Banner geändert
    extra = scan.Host("10.0.0.9", "neu", "", True, "offener Port")
    extra.ports = [scan.OpenPort(443, "HTTPS")]
    new.append(extra)
    diff = scan.compare(old, new)
    assert diff.new_hosts == ["10.0.0.9"] and diff.opened["10.0.0.5"] == [3389]
    assert diff.closed["10.0.0.5"] == [80]
    assert diff.banner_changed["10.0.0.7"][0][0] == 22
    md = scan.diff_to_markdown(diff)
    assert "Neue Hosts" in md and "neu offen** 3389" in md
    assert scan.compare(old, old).empty and "Keine Änderungen" in scan.diff_to_markdown(scan.compare(old, old))


def test_as_ip_note() -> None:
    note = scan.as_ip_note(sample())
    from notex.core import ipmap
    pairs = [(a.ip, a.host) for a in ipmap.extract(note, __import__("pathlib").Path("scan.md"))]
    assert ("10.0.0.5", "nas") in pairs and ("10.0.0.7", "?") in pairs


def test_ping_fallback_marks_host_alive() -> None:
    connect = make_connect({})                       # kein Port offen
    config = scan.ScanConfig(ports=[80], timeout=0.2, use_ping=True, reverse_dns=False)
    hosts = run(scan.scan([scan.Target("10.0.0.5")], config, connect=connect,
                          pinger=lambda ip: ip == "10.0.0.5"))
    assert hosts[0].alive and hosts[0].reason == "ping"


# ---- L1: Scanner darf nach dem ersten Host nicht hängen ------------------------------------------------------------
def test_reverse_dns_runs_in_thread_and_does_not_block(monkeypatch) -> None:
    """Ein langsamer (blockierender) Resolver darf den Event-Loop nicht serialisieren – 12 Hosts parallel."""
    import time as _time
    connect = make_connect({f"10.0.0.{n}": {80: b""} for n in range(1, 13)})

    def slow_resolver(ip: str) -> str:
        _time.sleep(0.5)                      # blockierender Namensdienst (wie socket.gethostbyaddr)
        return f"host-{ip.split('.')[-1]}"
    targets = [scan.Target(f"10.0.0.{n}") for n in range(1, 13)]
    config = scan.ScanConfig(ports=[80], timeout=0.3, discover=True, reverse_dns=True, resolve_timeout=2.0)
    start = _time.monotonic()
    hosts = run(scan.scan(targets, config, connect=connect, resolver=slow_resolver))
    elapsed = _time.monotonic() - start
    assert all(h.hostname.startswith("host-") for h in hosts)
    assert elapsed < 4.0                      # seriell wären es 12 × 0,5 s = 6 s; parallel im Thread deutlich weniger


def test_reverse_dns_timeout_never_hangs() -> None:
    import time as _time
    connect = make_connect({"10.0.0.5": {80: b""}})

    def stuck_resolver(ip: str) -> str:
        _time.sleep(1.5)                       # deutlich länger als resolve_timeout
        return "spät"
    config = scan.ScanConfig(ports=[80], timeout=0.3, reverse_dns=True, resolve_timeout=0.2)
    start = _time.monotonic()
    hosts = run(scan.scan([scan.Target("10.0.0.5")], config, connect=connect, resolver=stuck_resolver))
    assert hosts[0].hostname == "" and hosts[0].alive          # Timeout → kein Name, aber Host da
    assert _time.monotonic() - start < 3.0


def test_scan_continues_when_wait_closed_hangs() -> None:
    """Ein Writer, dessen wait_closed nie zurückkehrt, darf den Scan nicht blockieren (Windows-ProactorLoop)."""
    class HangingWriter(FakeWriter):
        async def wait_closed(self):
            await asyncio.sleep(30)
    async def connect(ip, port, timeout):
        if port != 80:
            raise ConnectionRefusedError()
        return FakeReader(b""), HangingWriter()
    import time as _time
    targets = [scan.Target(f"10.0.0.{n}") for n in range(1, 6)]
    config = scan.ScanConfig(ports=[80], timeout=0.3, reverse_dns=False, discover=True)
    start = _time.monotonic()
    hosts = run(scan.scan(targets, config, connect=connect))
    assert len(hosts) == 5 and all(h.alive for h in hosts) and _time.monotonic() - start < 4.0


def test_cancel_stops_during_port_probes() -> None:
    calls = []
    async def counting_connect(ip, port, timeout):
        calls.append(port)
        await asyncio.sleep(0.02)
        raise ConnectionRefusedError()
    cancel = {"v": False}
    async def driver():
        task = asyncio.ensure_future(scan.scan([scan.Target("10.0.0.5")],
                                               scan.ScanConfig(ports=list(range(1, 200)), timeout=0.3, concurrency=10,
                                                               discover=False, reverse_dns=False),
                                               connect=counting_connect, cancelled=lambda: cancel["v"]))
        await asyncio.sleep(0.05)
        cancel["v"] = True
        await task
    run(driver())
    assert len(calls) < 199                   # Abbruch verhindert, dass alle 199 Ports geprobt werden
