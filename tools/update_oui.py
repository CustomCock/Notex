"""Erzeugt die Offline-OUI-Tabelle (MAC-Präfix → Hersteller) für den Netzwerk-Scanner.

Quelle sind die **öffentlichen MAC-Adressblock-Zuordnungen der IEEE** (Registration Authority). Diese Zuordnungen
sind reine Fakten (Präfix ↔ Organisation) und von der IEEE frei zur Verfügung gestellt. Bevorzugt wird die
Original-CSV der IEEE geladen; ist deren Host (in mancher Umgebung gesperrt) nicht erreichbar, kann eine lokale
Datei oder ein Spiegel angegeben werden, aus dem NUR die Fakten (OUI + Name) extrahiert werden.

Bewusst NICHT verwendet: Wiresharks `manuf` (GPL). Ausgabe: reproduzierbares gzip mit mtime=0, damit gleiche
Eingabe gleiche Bytes ergibt.

Aufruf:
  python tools/update_oui.py                       # lädt von der IEEE (braucht Netz)
  python tools/update_oui.py --from datei.txt      # aus lokaler Datei (IEEE-CSV oder „HHHHHH Name")
  python tools/update_oui.py --url <mirror>        # aus einem Spiegel (nur Fakten werden übernommen)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import re
import sys
from pathlib import Path

IEEE_CSV = "https://standards-oui.ieee.org/oui/oui.csv"
OUT = Path(__file__).resolve().parent.parent / "notex" / "assets" / "oui" / "oui.tsv.gz"

_HEX6 = re.compile(r"^[0-9A-Fa-f]{6}$")


def _from_ieee_csv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        assignment = (row.get("Assignment") or "").strip().upper()
        org = (row.get("Organization Name") or "").strip()
        if _HEX6.match(assignment) and org:
            out[assignment] = org
    return out


def _from_simple(text: str) -> dict[str, str]:
    """Zeilen der Form „HHHHHH  Herstellername" (z. B. IEEE-abgeleiteter Spiegel)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and _HEX6.match(parts[0]):
            out[parts[0].upper()] = parts[1].strip()
    return out


def parse(text: str) -> dict[str, str]:
    if "Organization Name" in text[:2000] or "Assignment" in text[:2000]:
        return _from_ieee_csv(text)
    return _from_simple(text)


def write(mapping: dict[str, str]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{oui}\t{name}" for oui, name in sorted(mapping.items())]
    data = ("\n".join(lines) + "\n").encode("utf-8")
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(OUT, "wb"), mtime=0) as handle:
        handle.write(data)
    print(f"geschrieben: {OUT}  ({len(mapping)} Einträge, {OUT.stat().st_size} Bytes)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="path", help="lokale Datei statt Download")
    parser.add_argument("--url", help="alternative URL (Spiegel)")
    args = parser.parse_args()
    if args.path:
        text = Path(args.path).read_text(encoding="utf-8", errors="replace")
    else:
        import urllib.request
        url = args.url or IEEE_CSV
        with urllib.request.urlopen(url, timeout=60) as response:   # noqa: S310
            text = response.read().decode("utf-8", "replace")
    mapping = parse(text)
    if not mapping:
        print("keine Einträge erkannt", file=sys.stderr)
        return 1
    write(mapping)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
