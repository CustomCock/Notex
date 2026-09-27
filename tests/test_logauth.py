import gzip
from datetime import datetime
from pathlib import Path

import pytest

from notex.core import logauth as la

AUTH = """Sep 27 04:03:11 web sshd[1024]: Failed password for root from 203.0.113.5 port 55234 ssh2
Sep 27 04:03:13 web sshd[1024]: Failed password for root from 203.0.113.5 port 55240 ssh2
Sep 27 04:03:20 web sshd[1024]: Invalid user admin from 203.0.113.5
Sep 27 04:03:25 web sshd[1025]: Failed password for invalid user admin from 203.0.113.5 port 60000 ssh2
Sep 27 04:05:00 web sshd[1030]: Accepted password for root from 203.0.113.5 port 55250 ssh2
Sep 27 04:06:00 web sshd[1031]: Accepted publickey for alice from 10.0.0.9 port 40000 ssh2
Sep 27 04:07:01 web sudo:    bob : TTY=pts/0 ; PWD=/home/bob ; USER=root ; COMMAND=/bin/cat /etc/shadow
Sep 27 04:07:10 web sudo:    eve : 1 incorrect password attempts ; TTY=pts/1 ; USER=root ; COMMAND=/bin/su
Sep 27 04:08:00 web useradd[2000]: new user: name=hacker, UID=0, GID=0, home=/root, shell=/bin/bash
Sep 27 04:08:05 web usermod[2001]: add 'hacker' to group 'sudo'
Sep 27 04:09:00 web passwd[2100]: password changed for hacker
Nicht passende Zeile ohne Syslog-Kopf
"""


def kinds(events):
    return [e.kind for e in events]


def test_parse_auth_variants() -> None:
    events = [e for e in (la.parse_auth_line(l, "auth.log", i, year=2026) for i, l in enumerate(AUTH.splitlines()))
              if e]
    assert kinds(events) == ["login_failed", "login_failed", "invalid_user", "login_failed", "login_ok",
                             "accepted_key", "sudo", "sudo_fail", "user_added", "group_add", "password_change"]
    first = events[0]
    assert first.user == "root" and first.ip == "203.0.113.5" and first.time == datetime(2026, 9, 27, 4, 3, 11)
    assert events[5].kind == "accepted_key" and events[5].user == "alice" and events[5].ip == "10.0.0.9"
    assert events[6].detail.startswith("/bin/cat") and events[6].user == "bob"
    assert events[8].user == "hacker" and events[9].detail == "Gruppe sudo"


def test_read_gz_and_plain(tmp_path: Path) -> None:
    plain = tmp_path / "auth.log"
    plain.write_text(AUTH, encoding="utf-8")
    rotated = tmp_path / "auth.log.1.gz"
    with gzip.open(rotated, "wt", encoding="utf-8") as handle:
        handle.write(AUTH)
    a, trunc = la.collect(plain, year=2026)
    b, _ = la.collect(rotated, year=2026)
    assert len(a) == 11 and len(b) == 11 and not trunc
    assert la.collect(plain, limit=3)[1] is True


def test_dashboard() -> None:
    events = (
        [e for e in (la.parse_auth_line(l, "a", i, year=2026) for i, l in enumerate(AUTH.splitlines())) if e])
    dash = la.analyze(events, brute_threshold=3)
    assert dash.total == 11
    assert ("203.0.113.5", 4) in dash.failed_by_ip and dash.brute_force == [("203.0.113.5", 4)]
    assert dash.success_after_failed and dash.success_after_failed[0].user == "root"
    assert [e.user for e in dash.new_users] == ["hacker"]
    assert dash.group_changes and dash.timeline and dash.timeline[0][1] >= 1


# ---- Windows evtx (reine XML-Funktion, ohne Bibliothek) -----------------------------------------------------------
def evtx_xml(event_id: str, data: dict, time="2026-09-27T04:00:00.000000Z") -> str:
    fields = "".join(f'<Data Name="{k}">{v}</Data>' for k, v in data.items())
    return (f'<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System>'
            f'<Provider Name="Microsoft-Windows-Security-Auditing"/><EventID>{event_id}</EventID>'
            f'<TimeCreated SystemTime="{time}"/><Computer>PC1</Computer></System>'
            f'<EventData>{fields}</EventData></Event>')


def test_parse_evtx_events() -> None:
    fail = la.parse_evtx_xml(evtx_xml("4625", {"TargetUserName": "admin", "IpAddress": "203.0.113.9", "LogonType": "3"}))
    assert fail.kind == "login_failed" and fail.user == "admin" and fail.ip == "203.0.113.9"
    assert fail.logon_type == "3" and "Netzwerk" in fail.summary
    assert fail.time == datetime.fromisoformat("2026-09-27T04:00:00+00:00")
    ok = la.parse_evtx_xml(evtx_xml("4624", {"TargetUserName": "root", "IpAddress": "10.0.0.5", "LogonType": "10"}))
    assert ok.kind == "login_ok" and "Remotedesktop" in ok.summary
    added = la.parse_evtx_xml(evtx_xml("4720", {"TargetUserName": "newadmin", "SubjectUserName": "Administrator"}))
    assert added.kind == "user_added" and added.user == "newadmin"
    group = la.parse_evtx_xml(evtx_xml("4732", {"SubjectUserName": "Administrator", "TargetUserName": "Administrators",
                                                "MemberName": "CN=hacker"}))
    assert group.kind == "group_add" and "Administrators" in group.detail
    svc = la.parse_evtx_xml(evtx_xml("7045", {"ServiceName": "EvilSvc", "ImagePath": "C:\\\\evil.exe"}))
    assert svc.kind == "service_installed" and "EvilSvc" in svc.detail
    cleared = la.parse_evtx_xml(evtx_xml("1102", {"SubjectUserName": "Administrator"}))
    assert cleared.kind == "log_cleared" and cleared.user == "Administrator"
    assert la.parse_evtx_xml(evtx_xml("9999", {})) is None       # uninteressante ID
    assert la.parse_evtx_xml("<kaputt>") is None


def test_evtx_dashboard_flow() -> None:
    xmls = [evtx_xml("4625", {"TargetUserName": "admin", "IpAddress": "1.2.3.4"}) for _ in range(4)]
    xmls.append(evtx_xml("4624", {"TargetUserName": "admin", "IpAddress": "1.2.3.4", "LogonType": "3"}))
    events = [la.parse_evtx_xml(x) for x in xmls]
    dash = la.analyze(events, brute_threshold=3)
    assert dash.brute_force == [("1.2.3.4", 4)] and len(dash.success_after_failed) == 1
    report = la.to_markdown(dash, "Security.evtx")
    assert "Brute-Force" in report and "1.2.3.4" in report


@pytest.mark.skipif(not la.evtx_available(), reason="Paket evtx nicht installiert")
def test_read_evtx_library_path(tmp_path: Path) -> None:
    # Ohne echte .evtx nur den Fehlerpfad einer Nicht-evtx-Datei prüfen (die Bibliothek meldet einen Header-Fehler)
    fake = tmp_path / "x.evtx"
    fake.write_bytes(b"not an evtx file")
    with pytest.raises(Exception):
        list(la.read_evtx(fake))
