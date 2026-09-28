"""MAC-Hersteller-Zuordnung (OUI) offline – ohne Qt.

Datenquelle: öffentliche MAC-Adressblock-Zuordnungen der IEEE (Registration Authority), erzeugt mit
`tools/update_oui.py` nach `notex/assets/oui/oui.tsv.gz`. Die Zuordnungen sind reine Fakten (Präfix ↔ Organisation)
und von der IEEE frei nutzbar. Bewusst NICHT Wiresharks GPL-`manuf`.

Neben dem Hersteller erkennt das Modul auch **lokal verwaltete** (selbst vergebene / zufällige) und
**Multicast**-Adressen – die haben keinen echten Hersteller.
"""
from __future__ import annotations

import gzip
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "assets" / "oui" / "oui.tsv.gz"

_SEP = re.compile(r"[:\-.\s]")


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    table: dict[str, str] = {}
    try:
        with gzip.open(DATA, "rt", encoding="utf-8") as handle:
            for line in handle:
                oui, _, name = line.partition("\t")
                name = name.strip()
                if len(oui) == 6 and name:
                    table[oui.upper()] = name
    except OSError:
        pass
    return table


def normalize(mac: str) -> str | None:
    """MAC auf reine Hex-Ziffern (Großbuchstaben) bringen; None, wenn keine 12-stellige MAC."""
    if not mac:
        return None
    hex_only = _SEP.sub("", mac).upper()
    if len(hex_only) == 12 and re.fullmatch(r"[0-9A-F]{12}", hex_only):
        return hex_only
    return None


def oui_prefix(mac: str) -> str | None:
    norm = normalize(mac)
    return norm[:6] if norm else None


def is_locally_administered(mac: str) -> bool:
    """Zweitniedrigstes Bit des ersten Oktetts gesetzt → lokal verwaltet (z. B. zufällige MAC)."""
    norm = normalize(mac)
    if not norm:
        return False
    return bool(int(norm[:2], 16) & 0b10)


def is_multicast(mac: str) -> bool:
    """Niedrigstes Bit des ersten Oktetts gesetzt → Multicast/Gruppe."""
    norm = normalize(mac)
    if not norm:
        return False
    return bool(int(norm[:2], 16) & 0b01)


def lookup(mac: str) -> str | None:
    """Hersteller zu einer MAC/OUI; None wenn unbekannt oder lokal verwaltet."""
    prefix = oui_prefix(mac)
    if not prefix or is_locally_administered(mac):
        return None
    return _table().get(prefix)


def vendor_label(mac: str) -> str:
    """Kurzer Anzeigetext: Hersteller, „lokal verwaltet", „Multicast" oder „unbekannt"."""
    if is_multicast(mac):
        return "Multicast"
    if is_locally_administered(mac):
        return "lokal verwaltet"
    return lookup(mac) or "unbekannt"


def data_available() -> bool:
    return bool(_table())
