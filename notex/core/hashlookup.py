"""Online-Hash-Lookup (Umkehr bekannter, UNGESALZENER Hashes → Klartext) – ohne Qt, Netz injizierbar.

WICHTIG: Ein Hash ist NICHT verschlüsselt. Hier wird nichts „entschlüsselt", sondern in einer öffentlichen
Datenbank nachgeschlagen, ob der Klartext zu einem bekannten Hash vorliegt. Das klappt nur für ungesalzene Hashes
gängiger Passwörter; gesalzene Formate (bcrypt/argon2/sha512crypt …) sind sinnlos abzufragen.

Dienst: **Nitrxgen MD5-Datenbank** (https://www.nitrxgen.net/md5db/) – frei nutzbar, ohne Schlüssel, liefert den
Klartext als reinen Text (leer = nicht gefunden). Deckt **MD5** ab. Für SHA-1/SHA-256/NTLM ist kein freier,
schlüsselloser Klartext-Dienst hinterlegt – diese werden nicht abgefragt (Knopf bleibt deaktiviert mit Begründung).
Offline-Cracking mit Wortlisten/Rainbow-Tables ist bewusst NICHT enthalten – dafür gibt es eigene Werkzeuge
(hashcat, John the Ripper); das ist nicht Aufgabe von Notex.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

SERVICE_NAME = "Nitrxgen MD5-Datenbank"
SERVICE_HOST = "www.nitrxgen.net"
SERVICE_URL = "https://www.nitrxgen.net/md5db/"

# detect.py-Typschlüssel → welchen die Dienst-Wahl abfragt
SUPPORTED_TYPES = {"hash_md5"}
_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")


@dataclass
class LookupResult:
    found: bool
    plaintext: str = ""
    message: str = ""


def can_lookup(hash_type: str) -> bool:
    return hash_type in SUPPORTED_TYPES


def reason_unsupported(hash_type: str) -> str:
    from notex.core.detect import SALTED_HASHES
    if hash_type in SALTED_HASHES:
        return "Gesalzener Hash – ein Online-Lookup ist hier sinnlos."
    return f"Für diesen Hash-Typ ist kein freier Lookup-Dienst hinterlegt (nur MD5 über {SERVICE_NAME})."


def build_url(hash_value: str) -> str:
    return SERVICE_URL + hash_value.strip().lower()


def parse_response(body: str) -> LookupResult:
    """Nitrxgen liefert den Klartext als reinen Text; leer/Whitespace = nicht gefunden."""
    text = (body or "").strip()
    if not text:
        return LookupResult(False, message="nicht gefunden")
    # Schutz gegen HTML-Fehlerseiten: echte Treffer sind kurze Klartexte ohne Markup
    if "<" in text or len(text) > 200:
        return LookupResult(False, message="nicht gefunden")
    return LookupResult(True, plaintext=text)


def _default_fetch(url: str, timeout: float) -> tuple[int, str]:
    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": "Notex-HashLookup"})
    with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 – feste https-URL
        return response.status, response.read(1_000_000).decode("utf-8", "replace")


class HashLookupClient:
    def __init__(self, fetch: Callable[[str, float], tuple[int, str]] | None = None, timeout: float = 8.0) -> None:
        self._fetch = fetch or _default_fetch
        self.timeout = timeout

    def lookup(self, hash_value: str, hash_type: str) -> LookupResult:
        if not can_lookup(hash_type):
            return LookupResult(False, message=reason_unsupported(hash_type))
        value = hash_value.strip().lower()
        if not _HEX32.match(value):
            return LookupResult(False, message="Kein gültiger MD5-Hash (32 Hex-Zeichen)")
        status, body = self._fetch(build_url(value), self.timeout)
        if status != 200:
            return LookupResult(False, message=f"Dienst antwortete mit HTTP {status}")
        return parse_response(body)
