"""Analyse per Rechtsklick: baut die Kontextmenü-Gruppe „Analysieren" aus der Typ-Erkennung (core/detect) und
führt die Aktionen aus – Ergebnisse in der kompakten Analyse-Karte (ui/analysis_card), Netz im Worker-Thread.

Wiederverwendung statt Doppelbau: Umwandlungen aus core/convert, Portinfos aus core/ports, RDAP/Scanner/IP-Übersicht
über die vorhandenen Fenster-Methoden, IOC über die vorhandenen Befehle. Aktionen tauchen konsistent auch in der
Command Palette auf (siehe register_commands).
"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication, QDesktopServices
from PySide6.QtCore import QUrl

from notex.core import convert, detect, fileops, ports
from notex.theme.icons import icon


class AnalyzeController:
    def __init__(self, window) -> None:
        self.window_ = window
        self._card = None
        self._allow_hash_session = False       # „nicht mehr fragen" (nur diese Sitzung)

    # ---- Karte ------------------------------------------------------------------------------------
    def card(self):
        from notex.ui.analysis_card import AnalysisCard
        if self._card is None:
            self._card = AnalysisCard(self.window_)
        return self._card

    # ---- Auswahl / Term ---------------------------------------------------------------------------
    @staticmethod
    def _term(editor) -> str:
        cursor = editor.textCursor()
        text = cursor.selectedText().replace(" ", "\n").strip()
        if text:
            return text
        return detect.token_at(editor.toPlainText(), cursor.position())

    # ---- Kontextmenü ------------------------------------------------------------------------------
    def menu_provider(self, editor, menu) -> None:
        term = self._term(editor)
        if not term:
            return
        det = detect.analyze(term)
        sub = menu.addMenu(icon("scan-text"), "Analysieren")
        short = term if len(term) <= 40 else term[:37] + "…"
        header = sub.addAction(f"„{short}“")
        header.setEnabled(False)
        sub.addSeparator()
        sub.addAction(icon("scan-eye"), "Erkennen …", lambda: self.detect_card(term))

        types = set(det.types)
        added = False

        def act(icon_name, label, module, callback):
            nonlocal added
            added = True
            if module and module not in self.window_._enabled_modules():
                entry = sub.addAction(icon(icon_name), f"{label} – Modul aktivieren")
                entry.triggered.connect(lambda _c=False, m=module: self.window_.modules.set_enabled(m, True))
            else:
                entry = sub.addAction(icon(icon_name), label)
                entry.triggered.connect(lambda _c=False: callback())

        if types & {"ipv4", "ipv6", "domain"}:
            host = term
            act("network", "DNS auflösen (A/AAAA/PTR)", None, lambda: self.dns_lookup(host))
            act("radar", "Ping (Antwortzeit)", None, lambda: self.ping(host))
            act("radar", "Gängige Ports prüfen", None, lambda: self.port_check(host))
            act("globe-lock", "RDAP / ASN", "rdap", lambda: self.window_.rdap_lookup(host))
            act("server", "In IP-Übersicht öffnen", "ip_conflicts", lambda: self.window_.show_ip_overview())
            act("radar", "Im Netzwerk-Scanner öffnen", "scanner", lambda: self.window_.open_scanner())
        if "cidr" in types:
            act("radar", "Im Netzwerk-Scanner öffnen", "scanner", lambda: self.window_.open_scanner())
        if "port" in types:
            act("network", "Port nachschlagen", "ports", lambda: self.port_info(term))
        if types & detect.UNSALTED_HASHES or types & detect.SALTED_HASHES:
            act("fingerprint-pattern", "Hash-Info (Typ + Online-Lookup)", None, lambda: self.hash_info(term, det))
        if "jwt" in types:
            act("braces", "JWT zerlegen", None, lambda: self.jwt(term))
        if "base64" in types:
            act("braces", "Base64 dekodieren", None, lambda: self.decode(term, "base64"))
        if "base32" in types:
            act("braces", "Base32 dekodieren", None, lambda: self.decode(term, "base32"))
        if "hex_blob" in types:
            act("binary", "Hex dekodieren", None, lambda: self.decode(term, "hex"))
        if "%" in term:
            act("braces", "URL dekodieren", None, lambda: self.decode(term, "url"))
        if types & {"url", "domain", "ipv4", "ipv6", "email"}:
            act("shield", "IOC entschärfen (in Auswahl)", "ioc", lambda: self.window_.run_command("ioc:defang"))
        if "unix_timestamp" in types:
            act("clock-4", "Zeitstempel umrechnen", None, lambda: self.timestamp(term))
        if "iso_date" in types:
            act("clock-4", "In Unix-Zeit umrechnen", None, lambda: self.date_to_ts(term))
        if "number" in types:
            act("binary", "Zahl in Basen", None, lambda: self.number(term))
        if "hex_color" in types:
            act("palette", "Farbe anzeigen", None, lambda: self.color(term))
        if "cve" in types:
            act("globe-lock", "CVE nachschlagen (Browser)", None, lambda: self.cve(term))
        if "user_agent" in types:
            act("scan-eye", "User-Agent zerlegen", None, lambda: self.user_agent(term))

        # immer verfügbar: Hash dieses Worts bilden (lokal)
        hashes = sub.addMenu(icon("fingerprint-pattern"), "Hash dieses Worts bilden")
        for algo, label in (("md5", "MD5"), ("sha1", "SHA-1"), ("sha256", "SHA-256"), ("ntlm", "NTLM")):
            hashes.addAction(label, lambda _c=False, a=algo: self.hash_word(term, a))

    # ---- Erkennen ---------------------------------------------------------------------------------
    def detect_card(self, term: str) -> None:
        det = detect.analyze(term)
        card = self.card()
        card.reset("Erkannte Typen", term if len(term) <= 60 else term[:57] + "…")
        if not det.matches:
            card.add_text("Kein bekannter Typ erkannt.")
        for match in det.matches:
            conf = f"{int(match.confidence * 100)} %"
            card.add_row(match.label, f"{conf}" + (f" · {match.detail}" if match.detail else ""))
        lines = ["| Typ | Konfidenz | Hinweis |", "|---|---|---|"]
        lines += [f"| {m.label} | {int(m.confidence*100)} % | {m.detail} |" for m in det.matches]
        card.set_note("**Erkannte Typen**\n\n" + "\n".join(lines) if det.matches else "")
        card.show_near()

    # ---- Netzwerk ---------------------------------------------------------------------------------
    def dns_lookup(self, host: str) -> None:
        card = self.card()
        card.reset("DNS-Auflösung", host)
        card.add_text("MX/TXT brauchen eine DNS-Bibliothek (nicht im Build) – hier A/AAAA/PTR über das System.")
        card.set_action("Auflösen", lambda c: c.run_job(lambda: _resolve(host), _fmt_dns))
        card.show_near()

    def ping(self, host: str) -> None:
        from notex.core import scan
        card = self.card()
        card.reset("Ping", host)
        card.set_action("Ping senden", lambda c: c.run_job(
            lambda: scan.system_ping(host, timeout=2.0), lambda ok: "erreichbar" if ok else "keine Antwort"))
        card.show_near()

    def port_check(self, host: str) -> None:
        from notex.core import scan
        card = self.card()
        card.reset("Gängige Ports prüfen", host)
        ports_list = scan.parse_ports("top100")

        def job():
            import asyncio
            return asyncio.run(scan.scan_host(host, ports_list, timeout=1.0, concurrency=100))

        def fmt(open_ports):
            if not open_ports:
                return "keine der Top-100-Ports offen (oder Host blockt)"
            return "offen: " + ", ".join(f"{p.port}/{scan.service_name(p.port)}" for p in open_ports)

        card.add_text(f"Prüft {len(ports_list)} gängige TCP-Ports (nur auf Klick, im Hintergrund).")
        card.set_action("Ports prüfen", lambda c: c.run_job(job, fmt))
        card.show_near()

    def port_info(self, term: str) -> None:
        import re
        match = re.search(r"(\d{1,5})", term)
        card = self.card()
        card.reset("Port-Info", term)
        if not match:
            card.add_text("Keine Portnummer erkannt.")
            card.show_near()
            return
        info = ports.lookup(int(match.group(1)))
        if info is None:
            card.add_text("Keine Portnummer im gültigen Bereich.")
        else:
            card.add_row("Port", info.summary())
            if info.note:
                card.add_row("Hinweis", info.note)
            for name, proto, desc in info.iana[:6]:
                card.add_row(name or proto, f"{proto} · {desc}")
            card.set_note(f"**Port {info.port}** – {info.title}\n\n{info.note}")
        card.show_near()

    # ---- Umwandlungen -----------------------------------------------------------------------------
    def decode(self, term: str, kind: str) -> None:
        card = self.card()
        titles = {"base64": "Base64 dekodieren", "base32": "Base32 dekodieren", "hex": "Hex dekodieren",
                  "url": "URL dekodieren"}
        card.reset(titles.get(kind, "Dekodieren"), term if len(term) <= 60 else term[:57] + "…")
        try:
            if kind == "url":
                result = convert.url_decode(term)
            else:
                data = {"base64": convert.decode_base64, "base32": convert.decode_base32,
                        "hex": convert.decode_hex}[kind](term)
                result = convert.bytes_preview(data)
            card.add_row("Ergebnis", result, mono=True)
            card.set_note(f"```\n{result}\n```")
        except Exception as error:                        # noqa: BLE001
            card.add_text(f"Konnte nicht dekodieren: {error}")
        card.show_near()

    def jwt(self, term: str) -> None:
        card = self.card()
        card.reset("JWT", "Signatur wird NICHT geprüft")
        try:
            header, payload, _ = convert.jwt_decode(term)
            import json
            card.add_row("Header", json.dumps(header, ensure_ascii=False), mono=True)
            card.add_row("Payload", json.dumps(payload, ensure_ascii=False, indent=2), mono=True)
            for label, value in convert.jwt_times(payload):
                card.add_row(label, value)
            card.set_note("**JWT** (Signatur ungeprüft)\n\n```json\n"
                          + json.dumps({"header": header, "payload": payload}, ensure_ascii=False, indent=2) + "\n```")
        except Exception as error:                        # noqa: BLE001
            card.add_text(f"Kein gültiges JWT: {error}")
        card.show_near()

    def timestamp(self, term: str) -> None:
        import re
        card = self.card()
        card.reset("Unix-Zeitstempel", term)
        digits = re.sub(r"\D", "", term)
        try:
            utc, local = convert.timestamp_to_dates(int(digits))
            card.add_row("UTC", utc)
            card.add_row("Lokal", local)
            card.set_note(f"- {term} = {utc} / {local}")
        except Exception as error:                        # noqa: BLE001
            card.add_text(f"Kein gültiger Zeitstempel: {error}")
        card.show_near()

    def date_to_ts(self, term: str) -> None:
        card = self.card()
        card.reset("Datum → Unix-Zeit", term)
        try:
            ts = convert.date_to_timestamp(term)
            card.add_row("Unix-Zeit", str(ts), mono=True)
            card.set_note(f"- {term} = {ts}")
        except Exception as error:                        # noqa: BLE001
            card.add_text(f"Kein erkennbares Datum: {error}")
        card.show_near()

    def number(self, term: str) -> None:
        card = self.card()
        card.reset("Zahl in Basen", term)
        try:
            bases = convert.number_bases(convert.parse_int(term))
            for label, value in bases.items():
                card.add_row(label, value, mono=True)
            card.set_note("\n".join(f"- {k}: {v}" for k, v in bases.items()))
        except Exception as error:                        # noqa: BLE001
            card.add_text(f"Keine Zahl: {error}")
        card.show_near()

    def color(self, term: str) -> None:
        card = self.card()
        card.reset("Hex-Farbe", term)
        try:
            r, g, b, norm = convert.hex_color(term)
            card.add_row("Vorschau", f"RGB {r}, {g}, {b}", color=norm)
            card.add_row("Hex", norm, mono=True)
            card.add_row("RGB", f"rgb({r}, {g}, {b})", mono=True)
            card.set_note(f"- {norm} = rgb({r}, {g}, {b})")
        except Exception as error:                        # noqa: BLE001
            card.add_text(f"Keine Hex-Farbe: {error}")
        card.show_near()

    def user_agent(self, term: str) -> None:
        card = self.card()
        card.reset("User-Agent", term if len(term) <= 60 else term[:57] + "…")
        parsed = convert.parse_user_agent(term)
        for label, value in parsed.items():
            card.add_row(label, value)
        card.set_note("\n".join(f"- {k}: {v}" for k, v in parsed.items()))
        card.show_near()

    def cve(self, term: str) -> None:
        QDesktopServices.openUrl(QUrl(f"https://nvd.nist.gov/vuln/detail/{term.upper()}"))

    # ---- Hash -------------------------------------------------------------------------------------
    def hash_word(self, term: str, algo: str) -> None:
        card = self.card()
        card.reset(f"{algo.upper()} dieses Worts", term if len(term) <= 60 else term[:57] + "…")
        digest = convert.hash_word(term, algo)
        card.add_row(algo.upper(), digest, mono=True)
        card.add_text("Hinweis: Ein Hash ist eine Einwegfunktion, keine Verschlüsselung.")
        card.set_note(f"- {algo.upper()}(\"{term}\") = `{digest}`")
        card.show_near()

    def hash_info(self, term: str, det: detect.Detection) -> None:
        from notex.core import hashlookup
        card = self.card()
        card.reset("Hash-Info", term if len(term) <= 60 else term[:57] + "…")
        card.add_text("Ein Hash ist eine Einwegfunktion – er wird nicht „entschlüsselt“, sondern höchstens in einer "
                      "öffentlichen Datenbank nachgeschlagen.")
        hash_matches = [m for m in det.matches if m.type in detect.UNSALTED_HASHES | detect.SALTED_HASHES]
        for match in hash_matches:
            card.add_row(match.label, f"{int(match.confidence*100)} % · {match.detail}")
        card.set_note("**Hash-Info**\n\n" + "\n".join(f"- {m.label}: {m.detail}" for m in hash_matches))

        # Lookup-fähigen (ungesalzenen) Typ wählen
        lookup_type = next((m.type for m in hash_matches if m.type in detect.UNSALTED_HASHES), None)
        editor = self.window_.tabs.current_editor()
        is_ntx = editor is not None and editor.path is not None and fileops.is_encrypted_path(editor.path)

        if lookup_type is None:
            card.set_action("Online-Lookup", None, enabled=False,
                            disabled_reason="Gesalzener Hash – Online-Lookup ist sinnlos.")
        elif is_ntx:
            card.set_action("Online-Lookup", None, enabled=False,
                            disabled_reason="Verschlüsselte Notiz: Der Hash darf den Rechner nicht verlassen.")
        elif not hashlookup.can_lookup(lookup_type):
            card.set_action("Online-Lookup", None, enabled=False,
                            disabled_reason=hashlookup.reason_unsupported(lookup_type))
        else:
            card.set_action("Online-Lookup", lambda c: self._do_hash_lookup(c, term, lookup_type))
        card.show_near()

    def _do_hash_lookup(self, card, term: str, hash_type: str) -> None:
        from notex.core import hashlookup
        from notex.ui import dialogs
        cfg = self.window_.config.get("analysis", {})
        if not cfg.get("hash_online", False):
            if dialogs.confirm(self.window_, "Online-Hash-Lookup",
                               f"Der Hash würde an {hashlookup.SERVICE_NAME} ({hashlookup.SERVICE_HOST}) gesendet.",
                               informative="In den Einstellungen aktivieren?", yes="Einstellungen öffnen"):
                self.window_.open_settings("Analyse")
            return
        if not self._allow_hash_session:
            ok = dialogs.confirm(self.window_, "Online-Hash-Lookup",
                                 f"Der Hash wird an {hashlookup.SERVICE_NAME} ({hashlookup.SERVICE_HOST}) gesendet.",
                                 yes="Senden")
            if not ok:
                return
            self._allow_hash_session = True
        client = hashlookup.HashLookupClient()
        card.run_job(lambda: client.lookup(term, hash_type), _fmt_hash)


def _resolve(host: str):
    import socket
    result = {"A": [], "AAAA": [], "PTR": ""}
    try:
        for family, _t, _p, _c, sockaddr in socket.getaddrinfo(host, None):
            addr = sockaddr[0]
            if family == socket.AF_INET and addr not in result["A"]:
                result["A"].append(addr)
            elif family == socket.AF_INET6 and addr not in result["AAAA"]:
                result["AAAA"].append(addr)
    except OSError as error:
        raise RuntimeError(str(error))
    try:
        result["PTR"] = socket.gethostbyaddr(host)[0]
    except OSError:
        pass
    return result


def _fmt_dns(result) -> str:
    parts = []
    if result["A"]:
        parts.append("A: " + ", ".join(result["A"]))
    if result["AAAA"]:
        parts.append("AAAA: " + ", ".join(result["AAAA"]))
    if result["PTR"]:
        parts.append("PTR: " + result["PTR"])
    return " · ".join(parts) if parts else "keine Einträge"


def _fmt_hash(result) -> str:
    if result.found:
        return f"Klartext gefunden: {result.plaintext}"
    return result.message or "nicht gefunden"
