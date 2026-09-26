import pytest

from notex.core import ports


def found(line: str) -> list[tuple[int, str]]:
    return [(port, proto) for _s, _e, port, proto in ports.find_ports(line)]


@pytest.mark.parametrize("line,expected", [
    ("RDP läuft auf Port 3389.", [(3389, "")]),
    ("offene Ports: 22, 80, 443 und 8080", [(22, ""), (80, ""), (443, ""), (8080, "")]),
    ("Dienst auf 10.0.0.5:445 erreichbar", [(445, "")]),
    ("Admin unter https://fw.example.com:8443/login", [(8443, "")]),
    ("lokal http://localhost:3000 und [::1]:5432", [(3000, ""), (5432, "")]),
    ("Regel erlaubt 3389/tcp und 53/UDP", [(3389, "tcp"), (53, "udp")]),
    ("Firewall: tcp/445 blockiert", [(445, "tcp")]),
    ("22/tcp   open  ssh     OpenSSH 9.6", [(22, "tcp")]),
    ("sshd[1]: Failed password for root from 203.0.113.5 port 52344 ssh2", [(52344, "")]),
    ("PORT=6379", [(6379, "")]),
])
def test_find_ports(line: str, expected: list) -> None:
    assert found(line) == expected


@pytest.mark.parametrize("line", [
    "Im Jahr 2024 kostete das 443 Euro.",
    "Treffen um 14:03 Uhr, Log Sep 26 14:03:11 host",
    "Version 3.389 und Build 10.0.19045",
    "Pfad C:\\Windows\\System32 und /var/log/syslog.1",
    "Rechnung Nr. 8080 vom 26.09.2026",
    "Verhältnis 16:9 und 4:3",
    "Port 70000 gibt es nicht",
])
def test_no_false_positives(line: str) -> None:
    assert found(line) == []


def test_port_at_column() -> None:
    line = "Ports 22 und 3389 offen"
    assert ports.port_at(line, line.index("3389") + 2) == (3389, "")
    assert ports.port_at(line, 0) is None


def test_lookup_common_and_iana() -> None:
    rdp = ports.lookup(3389)
    assert rdp.name == "RDP" and "VPN" in rdp.note
    assert any(name == "ms-wbt-server" and "tcp" in proto for name, proto, _d in rdp.iana)
    ssh = ports.lookup(22)
    assert ssh.iana[0][1].startswith("tcp/udp")               # gleiche Namen zusammengefasst
    assert ports.lookup(4444).note.startswith("Nicht registriert, aber")
    assert ports.lookup(65000).title in ("",) or ports.lookup(65000) is not None
    assert ports.lookup(70000) is None
    assert ports.data_version().startswith("20")


def test_search_by_name_alias_and_number() -> None:
    assert ports.search("rdp")[0].port == 3389
    assert ports.search("3389")[0].port == 3389
    assert ports.search("ms-wbt-server")[0].port == 3389
    assert ports.search("") == []
    assert 445 in [info.port for info in ports.search("smb")]


def test_markdown_and_tooltip_escape() -> None:
    text = ports.to_markdown(ports.lookup(445))
    assert text.startswith("**Port 445 · SMB (tcp)**") and "IANA: `microsoft-ds`" in text
    html = ports.tooltip_html(ports.lookup(445))
    assert "<b>Port 445 · SMB (tcp)</b>" in html and "<script" not in html
