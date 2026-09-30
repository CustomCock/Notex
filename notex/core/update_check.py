"""Update-Check über die GitHub-Releases-API. Ohne Qt; der Netzabruf ist eine einzelne Funktion.

- höchstens einmal pro Tag (should_check), abschaltbar, „Jetzt prüfen“ geht immer
- es wird NIE etwas heruntergeladen oder installiert – Notex zeigt nur an, dass es eine neuere Version gibt,
  und öffnet auf Klick die Release-Seite im Browser
- Tags, die keine Version sind (z. B. ein versehentliches Release „main“), Entwürfe und Vorabversionen werden
  ignoriert; gewinnt die höchste Versionsnummer, nicht das jüngste Datum
- übertragen wird nur die normale HTTPS-Anfrage (IP-Adresse, User-Agent „Notex/<Version>“) – keine Kennung,
  keine Nutzungsdaten
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from notex import REPO as PACKAGE_REPO

REPO = PACKAGE_REPO
API_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CHECK_INTERVAL = 24 * 3600
TIMEOUT = 10
MAX_BYTES = 2 * 1024 * 1024
_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


@dataclass(frozen=True)
class Release:
    version: tuple[int, int, int]
    tag: str
    name: str
    url: str
    published: str
    notes: str

    @property
    def version_text(self) -> str:
        return ".".join(str(n) for n in self.version)


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = _VERSION.match(text.strip())
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_newer(candidate: tuple[int, int, int], current: tuple[int, int, int]) -> bool:
    return candidate > current


def should_check(last_check: float, now: float | None = None, interval: float = CHECK_INTERVAL) -> bool:
    now = time.time() if now is None else now
    return not last_check or now - last_check >= interval or last_check > now   # Uhr zurückgestellt: prüfen


def _short_notes(body: str, limit: int = 1200) -> str:
    body = (body or "").replace("\r\n", "\n").strip()
    return body if len(body) <= limit else body[:limit].rsplit("\n", 1)[0] + "\n…"


def latest_release(payload: Any) -> Release | None:
    """Höchste gültige Version aus der API-Antwort (Liste von Releases)."""
    if not isinstance(payload, list):
        return None
    best: Release | None = None
    for item in payload:
        if not isinstance(item, dict) or item.get("draft") or item.get("prerelease"):
            continue
        version = parse_version(str(item.get("tag_name", "")))
        url = str(item.get("html_url", ""))
        if version is None or not url.startswith(f"https://github.com/{REPO}/"):
            continue   # nur echte Versionen, nur Links ins eigene Repo
        release = Release(version, str(item["tag_name"]), str(item.get("name") or item["tag_name"]), url,
                          str(item.get("published_at") or ""), _short_notes(str(item.get("body") or "")))
        if best is None or release.version > best.version:
            best = release
    return best


def update_available(payload: Any, current: str, skipped: str = "") -> Release | None:
    """Release, auf das hingewiesen werden soll – oder None (aktuell, übersprungen, ungültig)."""
    current_version = parse_version(current)
    release = latest_release(payload)
    if release is None or current_version is None or not is_newer(release.version, current_version):
        return None
    if skipped and parse_version(skipped) == release.version:
        return None
    return release


def fetch_releases(current: str, url: str = API_URL, timeout: float = TIMEOUT) -> Any:
    """Die eigentliche Netzanfrage. Wirft OSError/ValueError bei Problemen."""
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Notex/{current}",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Antwort zu groß")
    return json.loads(data.decode("utf-8"))
