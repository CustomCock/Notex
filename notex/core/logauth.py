"""Anmelde- und Sicherheits-Logs auswerten: Linux auth.log/secure (auch rotiert .gz) und Windows-Ereignisprotokolle
(.evtx). Ohne Qt. Große Dateien werden gestreamt.

Windows-.evtx über das Paket **evtx** (Rust, MIT, fertige Wheels für Windows und Linux, ein abi3-Wheel für alle
Python ≥ 3.10). **Entscheidung gegen python-evtx**: dessen Abhängigkeit `hexdump` hat eine kaputte setup.py (baut auf
neuem setuptools nicht) – in beiden Builds unsicher. `evtx` bringt vorgebaute Wheels und keine Transitiv-Abhängigkeit.
Die Zuordnung der Event-IDs geschieht auf dem gerenderten Event-XML (siehe parse_evtx_xml) und ist ohne die
Bibliothek testbar.
"""
from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Iterator
from xml.etree import ElementTree as ET

MAX_EVENTS = 500_000


class EvtxMissing(Exception):
    pass


@dataclass
class LogEvent:
    time: datetime | None
    kind: str                    # z. B. "login_failed", "login_ok", "user_added", "log_cleared" …
    user: str = ""
    ip: str = ""
    detail: str = ""
    source: str = ""            # Datei
    line: int = -1              # Zeile (Linux) bzw. Datensatz-Nr. (evtx)
    raw: str = ""
    logon_type: str = ""

    @property
    def summary(self) -> str:
        parts = [KIND_LABELS.get(self.kind, self.kind)]
        if self.user:
            parts.append(f"Benutzer {self.user}")
        if self.ip:
            parts.append(f"von {self.ip}")
        if self.logon_type:
            parts.append(f"Typ {self.logon_type} ({LOGON_TYPES.get(self.logon_type, '?')})")
        if self.detail:
            parts.append(self.detail)
        return " · ".join(parts)


KIND_LABELS = {
    "login_failed": "Fehlgeschlagene Anmeldung", "login_ok": "Erfolgreiche Anmeldung", "logout": "Abmeldung",
    "invalid_user": "Anmeldung mit unbekanntem Benutzer", "sudo": "sudo-Befehl", "sudo_fail": "sudo fehlgeschlagen",
    "su": "su-Wechsel", "user_added": "Benutzer angelegt", "user_deleted": "Benutzer gelöscht",
    "user_enabled": "Benutzer aktiviert", "user_disabled": "Benutzer deaktiviert",
    "user_mod": "Benutzer geändert", "password_change": "Passwort geändert/zurückgesetzt",
    "group_add": "Zu Gruppe hinzugefügt", "group_change": "Gruppe geändert", "locked_out": "Konto gesperrt",
    "explicit_login": "Anmeldung mit anderen Anmeldedaten", "privileged": "Anmeldung mit Sonderrechten",
    "log_cleared": "Ereignisprotokoll geleert", "service_installed": "Neuer Dienst installiert",
    "process": "Prozess gestartet", "accepted_key": "Anmeldung per Schlüssel",
}
LOGON_TYPES = {"2": "interaktiv", "3": "Netzwerk", "4": "Batch", "5": "Dienst", "7": "Entsperren",
               "8": "Netzwerk-Klartext", "9": "neue Anmeldedaten", "10": "Remotedesktop", "11": "zwischengespeichert"}

# Auffällige Vorgänge (für Hervorhebung/Dashboard)
NOTEWORTHY = {"login_failed", "invalid_user", "user_added", "user_deleted", "user_enabled", "user_disabled",
              "group_add", "group_change", "locked_out", "log_cleared", "service_installed", "sudo_fail",
              "password_change", "explicit_login"}


# ---- Linux auth.log / secure --------------------------------------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
                                          "Nov", "Dec"])}
# „Sep 27 04:03:11 host prog[pid]: rest“  – auch ISO-Präfix (rsyslog RFC 5424) am Anfang
_SYSLOG = re.compile(r"^(?:(?P<iso>\d{4}-\d{2}-\d{2}T[\d:.,+\-Z]+)\s+|(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+"
                     r"(?P<time>\d{2}:\d{2}:\d{2})\s+)(?P<host>\S+)\s+(?P<prog>[\w./-]+?)(?:\[(?P<pid>\d+)\])?:\s"
                     r"(?P<msg>.*)$")
# Regeln auf der Nachricht (der „prog:“-Präfix ist von _SYSLOG bereits abgetrennt). prog_prefix schränkt auf ein
# Programm ein (None = beliebig). Reihenfolge zählt: speziellere zuerst.
_RULES = [
    ("invalid_user", None, re.compile(r"(?:Invalid user|illegal user)\s+(?P<user>\S+)(?:\s+from\s+(?P<ip>[\w.:]+))?")),
    ("login_failed", None, re.compile(r"Failed password for (?:invalid user )?(?P<user>\S+)\s+from\s+(?P<ip>[\w.:]+)")),
    ("accepted_key", None, re.compile(r"Accepted publickey for (?P<user>\S+)\s+from\s+(?P<ip>[\w.:]+)")),
    ("login_ok", None, re.compile(r"Accepted (?:password|keyboard-interactive\S*) for (?P<user>\S+)\s+from\s+"
                                  r"(?P<ip>[\w.:]+)")),
    ("sudo_fail", "sudo", re.compile(r"^\s*(?P<user>\S+)\s*:.*(?:incorrect password|authentication failure|"
                                     r"\d+ incorrect password attempt)")),
    ("sudo", "sudo", re.compile(r"^\s*(?P<user>\S+)\s*:.*COMMAND=(?P<detail>.*)$")),
    ("login_failed", None, re.compile(r"authentication failure;.*?(?:rhost=(?P<ip>[\w.:]*))?\s*"
                                      r"(?:user=(?P<user>\S+))?\s*$")),
    ("su", "su", re.compile(r"(?:\(to (?P<detail>\S+)\)\s+\S+|session opened for user (?P<user>\S+))")),
    ("user_added", None, re.compile(r"new user:\s*name=(?P<user>[^,\s]+)")),
    ("user_deleted", None, re.compile(r"delete user '(?P<user>[^']+)'")),
    ("group_add", None, re.compile(r"add(?:ing|ed)? '?(?P<user>[^' ]+)'?\s+to group '?(?P<detail>[^' ]+)")),
    ("group_add", None, re.compile(r"add '(?P<user>[^']+)' to group '(?P<detail>[^']+)'")),
    ("password_change", None, re.compile(r"password (?:changed|reset) for (?P<user>\S+)")),
    ("logout", None, re.compile(r"(?:session closed for user|Disconnected from user|Connection closed by(?: "
                                r"authenticating user)?)\s+(?P<user>\S+)?")),
]


def parse_auth_line(line: str, source: str = "", number: int = -1, year: int | None = None) -> LogEvent | None:
    match = _SYSLOG.match(line)
    if not match:
        return None
    msg = match.group("msg")
    when = _syslog_time(match, year)
    prog = match.group("prog") or ""
    base_prog = re.split(r"[/\[]", prog)[0]
    for kind, prog_prefix, pattern in _RULES:
        if prog_prefix is not None and base_prog != prog_prefix:
            continue
        found = pattern.search(msg)
        if not found:
            continue
        groups = found.groupdict()
        event = LogEvent(when, kind, (groups.get("user") or "").strip(), _clean_ip(groups.get("ip") or ""),
                         (groups.get("detail") or "").strip(), source, number, line.rstrip("\n"))
        if kind == "group_add" and event.detail:
            event.detail = f"Gruppe {event.detail}"
        elif kind == "su" and event.detail:
            event.detail = f"→ {event.detail}"
        return event
    return None


def _clean_ip(text: str) -> str:
    text = text.strip()
    return text if re.match(r"^[\d.]+$|^[0-9a-fA-F:]+$", text) else ""


def _syslog_time(match, year: int | None) -> datetime | None:
    if match.group("iso"):
        try:
            return datetime.fromisoformat(match.group("iso").replace("Z", "+00:00"))
        except ValueError:
            return None
    try:
        month = MONTHS[match.group("mon")]
        y = year or datetime.now().year
        h, m, s = (int(x) for x in match.group("time").split(":"))
        return datetime(y, month, int(match.group("day")), h, m, s)
    except (ValueError, KeyError):
        return None


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def read_auth_log(path: Path, progress: Callable[[int, int], None] | None = None,
                  cancelled: Callable[[], bool] | None = None, year: int | None = None) -> Iterator[LogEvent]:
    path = Path(path)
    total = path.stat().st_size or 1
    with _open_text(path) as handle:
        for number, line in enumerate(handle):
            if cancelled and cancelled() and number % 500 == 0:
                return
            event = parse_auth_line(line, str(path), number, year)
            if event is not None:
                yield event
            if progress and number % 1000 == 0:
                progress(min(handle.buffer.tell() if hasattr(handle, "buffer") else number, total)
                         if path.suffix != ".gz" else number, total if path.suffix != ".gz" else number + 1)


# ---- Windows .evtx ------------------------------------------------------------------------------------------------
_NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
EVENT_KINDS = {
    "4624": "login_ok", "4625": "login_failed", "4634": "logout", "4648": "explicit_login", "4672": "privileged",
    "4720": "user_added", "4722": "user_enabled", "4723": "password_change", "4724": "password_change",
    "4725": "user_disabled", "4726": "user_deleted", "4728": "group_add", "4732": "group_add", "4756": "group_add",
    "4740": "locked_out", "1102": "log_cleared", "7045": "service_installed", "4688": "process",
}


def _find(root, path: str) -> str:
    node = root.find(path, _NS)
    return (node.text or "").strip() if node is not None and node.text else ""


def _event_data(root) -> dict[str, str]:
    data: dict[str, str] = {}
    for node in root.findall("e:EventData/e:Data", _NS):
        name = node.get("Name")
        if name:
            data[name] = (node.text or "").strip()
    return data


def parse_evtx_xml(xml: str, source: str = "", record_id: int = -1) -> LogEvent | None:
    """Ein gerendertes Windows-Event-XML → LogEvent (nur die interessanten Event-IDs). Ohne evtx-Bibliothek testbar."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    event_id = _find(root, "e:System/e:EventID")
    kind = EVENT_KINDS.get(event_id)
    if kind is None:
        return None
    when = None
    node = root.find("e:System/e:TimeCreated", _NS)
    if node is not None and node.get("SystemTime"):
        raw = node.get("SystemTime").replace("Z", "+00:00")
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            when = None
    data = _event_data(root)
    user = data.get("TargetUserName") or data.get("SubjectUserName") or ""
    ip = _clean_ip(data.get("IpAddress", ""))
    event = LogEvent(when, kind, user, ip, "", source, record_id, "", data.get("LogonType", ""))
    if kind == "group_add":
        event.detail = f"Gruppe {data.get('TargetUserName') or data.get('MemberName') or ''}".strip()
        event.user = data.get("SubjectUserName") or user
    elif kind == "service_installed":
        event.detail = f"{data.get('ServiceName', '')} ({data.get('ImagePath', '')})".strip(" ()")
    elif kind == "process":
        event.detail = data.get("NewProcessName", "")
        event.user = data.get("SubjectUserName") or user
    elif kind == "log_cleared":
        event.user = data.get("SubjectUserName") or user
    event.detail = event.detail or (f"EventID {event_id}" if not event.user and not event.ip else "")
    return event


def evtx_available() -> bool:
    try:
        import evtx  # noqa: F401
        return True
    except ImportError:
        return False


def read_evtx(path: Path, progress: Callable[[int, int], None] | None = None,
              cancelled: Callable[[], bool] | None = None, year: int | None = None) -> Iterator[LogEvent]:
    try:
        from evtx import PyEvtxParser
    except ImportError as error:
        raise EvtxMissing("Das Paket „evtx“ ist nicht installiert – .evtx-Dateien können nicht gelesen werden.") \
            from error
    parser = PyEvtxParser(str(path))
    for number, record in enumerate(parser.records()):
        if cancelled and cancelled() and number % 200 == 0:
            return
        if isinstance(record, dict):
            xml = record.get("data", "")
            record_id = record.get("event_record_id", number)
        else:                                # bei einem Fehler-Datensatz überspringen
            continue
        event = parse_evtx_xml(xml, str(path), record_id)
        if event is not None:
            yield event
        if progress and number % 500 == 0:
            progress(number, number + 1)


def read_any(path: Path, **kwargs) -> Iterator[LogEvent]:
    path = Path(path)
    if path.suffix.lower() == ".evtx":
        return read_evtx(path, **kwargs)
    return read_auth_log(path, **kwargs)


def collect(path: Path, limit: int = MAX_EVENTS, **kwargs) -> tuple[list[LogEvent], bool]:
    events: list[LogEvent] = []
    for event in read_any(path, **kwargs):
        events.append(event)
        if len(events) >= limit:
            return events, True
    return events, False


# ---- Auswertung / Dashboard ---------------------------------------------------------------------------------------
@dataclass
class Dashboard:
    total: int = 0
    failed_by_ip: list[tuple[str, int]] = field(default_factory=list)
    failed_by_user: list[tuple[str, int]] = field(default_factory=list)
    success_after_failed: list[LogEvent] = field(default_factory=list)     # erfolgreiche Anmeldung nach Fehlversuchen
    brute_force: list[tuple[str, int]] = field(default_factory=list)       # IPs über der Schwelle
    new_users: list[LogEvent] = field(default_factory=list)
    group_changes: list[LogEvent] = field(default_factory=list)
    logs_cleared: list[LogEvent] = field(default_factory=list)
    new_services: list[LogEvent] = field(default_factory=list)
    lockouts: list[LogEvent] = field(default_factory=list)
    timeline: list[tuple[datetime, int, int]] = field(default_factory=list)   # (Stunde, Fehlversuche, Erfolge)


def analyze(events: list[LogEvent], brute_threshold: int = 5) -> Dashboard:
    from collections import Counter, defaultdict
    dash = Dashboard(total=len(events))
    failed_ip: Counter = Counter()
    failed_user: Counter = Counter()
    failed_ips_seen: dict[str, int] = defaultdict(int)
    per_hour_fail: Counter = Counter()
    per_hour_ok: Counter = Counter()
    for event in events:
        if event.kind in ("login_failed", "invalid_user"):
            if event.ip:
                failed_ip[event.ip] += 1
                failed_ips_seen[event.ip] += 1
            if event.user:
                failed_user[event.user] += 1
            if event.time:
                per_hour_fail[event.time.replace(minute=0, second=0, microsecond=0)] += 1
        elif event.kind in ("login_ok", "accepted_key"):
            if event.ip and failed_ips_seen.get(event.ip):
                dash.success_after_failed.append(event)
            if event.time:
                per_hour_ok[event.time.replace(minute=0, second=0, microsecond=0)] += 1
        elif event.kind == "user_added":
            dash.new_users.append(event)
        elif event.kind in ("group_add", "group_change"):
            dash.group_changes.append(event)
        elif event.kind == "log_cleared":
            dash.logs_cleared.append(event)
        elif event.kind == "service_installed":
            dash.new_services.append(event)
        elif event.kind == "locked_out":
            dash.lockouts.append(event)
    dash.failed_by_ip = failed_ip.most_common(50)
    dash.failed_by_user = failed_user.most_common(50)
    dash.brute_force = [(ip, count) for ip, count in dash.failed_by_ip if count >= brute_threshold]
    hours = sorted(set(per_hour_fail) | set(per_hour_ok))
    dash.timeline = [(hour, per_hour_fail.get(hour, 0), per_hour_ok.get(hour, 0)) for hour in hours]
    return dash


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(dash: Dashboard, source: str) -> str:
    lines = [f"# Log-Auswertung: {_cell(source)}", "", f"- Erkannte Ereignisse: {dash.total}", ""]
    if dash.brute_force:
        lines += ["## Mögliche Brute-Force-Quellen", "", "| IP | Fehlversuche |", "|---|---|"]
        lines += [f"| {ip} | {count} |" for ip, count in dash.brute_force] + [""]
    if dash.success_after_failed:
        lines += ["## Erfolgreiche Anmeldung nach Fehlversuchen", "", "| Zeit | Benutzer | IP |", "|---|---|---|"]
        lines += [f"| {e.time or '?'} | {_cell(e.user)} | {e.ip} |" for e in dash.success_after_failed[:50]] + [""]
    for title, items in (("Neue Benutzer", dash.new_users), ("Gruppenänderungen", dash.group_changes),
                         ("Neue Dienste", dash.new_services), ("Geleerte Protokolle", dash.logs_cleared),
                         ("Kontosperren", dash.lockouts)):
        if items:
            lines += [f"## {title}", ""]
            lines += [f"- {(e.time or '?')}: {_cell(e.summary)}" for e in items[:100]] + [""]
    if dash.failed_by_ip:
        lines += ["## Fehlversuche je IP", "", "| IP | Anzahl |", "|---|---|"]
        lines += [f"| {ip} | {count} |" for ip, count in dash.failed_by_ip[:30]] + [""]
    return "\n".join(lines) + "\n"
