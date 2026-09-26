"""LanguageTool-Client, ohne Qt: schickt Text an einen Server und liefert Treffer zurück.

Standard ist ein lokaler Server (http://localhost:8081). Die öffentliche API
(https://api.languagetool.org) darf nur benutzt werden, wenn der Nutzer das
ausdrücklich erlaubt hat – der Text wandert dabei zu einem fremden Server.

Rate-Limit: zwischen zwei Anfragen liegt mindestens `min_interval` Sekunden
(lokal 0,3 s, öffentlich 3,5 s – die öffentliche API erlaubt 20 Anfragen pro Minute).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

PUBLIC_API = "https://api.languagetool.org"
LANGUAGE_CODES = {"de": "de-DE", "en": "en-US", "both": "auto"}
MAX_TEXT_LENGTH = 20000     # Grenze der öffentlichen API


@dataclass
class GrammarMatch:
    offset: int
    length: int
    message: str
    replacements: list[str] = field(default_factory=list)
    rule: str = ""
    category: str = ""


class GrammarUnavailable(Exception):
    """Server nicht erreichbar, Fehlerantwort oder öffentliche API nicht erlaubt."""


def is_public_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host.endswith("languagetool.org")


def parse_matches(payload: dict) -> list[GrammarMatch]:
    """Aus der JSON-Antwort von /v2/check die Treffer herausziehen. Unerwartete Felder werden ignoriert."""
    matches: list[GrammarMatch] = []
    for raw in payload.get("matches", []) if isinstance(payload, dict) else []:
        try:
            replacements = [r.get("value", "") for r in raw.get("replacements", []) if isinstance(r, dict)]
            rule = raw.get("rule", {}) if isinstance(raw.get("rule"), dict) else {}
            matches.append(GrammarMatch(
                offset=int(raw["offset"]), length=int(raw["length"]),
                message=str(raw.get("message", "")).strip(),
                replacements=[r for r in replacements if r][:5],
                rule=str(rule.get("id", "")),
                category=str(rule.get("category", {}).get("name", "")) if isinstance(rule.get("category"), dict) else "",
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return matches


class GrammarClient:
    def __init__(self, server_url: str, allow_public: bool = False, timeout: float = 8.0) -> None:
        self.server_url = server_url.rstrip("/")
        self.allow_public = allow_public
        self.timeout = timeout
        self.min_interval = 3.5 if is_public_url(self.server_url) else 0.3
        self._last_request = 0.0

    def wait_for_slot(self) -> None:
        """Blockiert, bis die nächste Anfrage erlaubt ist (Rate-Limit)."""
        remaining = self.min_interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def check(self, text: str, language: str = "de") -> list[GrammarMatch]:
        if is_public_url(self.server_url) and not self.allow_public:
            raise GrammarUnavailable("Öffentliche LanguageTool-API ist nicht freigegeben")
        if not text.strip():
            return []
        self.wait_for_slot()
        data = urllib.parse.urlencode({
            "text": text[:MAX_TEXT_LENGTH],
            "language": LANGUAGE_CODES.get(language, "auto"),
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.server_url}/v2/check", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
                     "User-Agent": "Notex"},
        )
        self._last_request = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise GrammarUnavailable(str(error)) from error
        return parse_matches(payload)

    def ping(self) -> bool:
        """Kurzer Erreichbarkeitstest gegen /v2/languages."""
        try:
            with urllib.request.urlopen(f"{self.server_url}/v2/languages", timeout=min(3.0, self.timeout)) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError):
            return False
