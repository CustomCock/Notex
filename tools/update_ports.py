"""IANA-Portliste für Notex aufbereiten: notex/assets/ports/iana-ports.tsv.gz

Quelle: IANA „Service Name and Transport Protocol Port Number Registry“ (RFC 6335),
https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv
Laut gemeinsamer Erklärung von IANA und IETF (2021) dürfen die Protokoll-Register von jedem für jeden Zweck frei
genutzt werden (https://www.iana.org/help/licensing-terms).

Aufruf:  python tools/update_ports.py            (lädt die CSV von iana.org)
         python tools/update_ports.py datei.csv  (lokale Kopie)
Ausgabe: je Zeile  start<TAB>ende<TAB>protokoll<TAB>name<TAB>beschreibung  – nur Einträge mit Portnummer.
"""
from __future__ import annotations

import csv
import gzip
import io
import sys
import urllib.request
from pathlib import Path

URL = "https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv"
TARGET = Path(__file__).resolve().parent.parent / "notex" / "assets" / "ports" / "iana-ports.tsv.gz"


def convert(text: str) -> list[str]:
    lines, newest = [], ""
    for row in csv.DictReader(io.StringIO(text)):
        port = (row.get("Port Number") or "").strip()
        proto = (row.get("Transport Protocol") or "").strip().lower()
        if not port or not proto:
            continue
        start, _, end = port.partition("-")
        name = (row.get("Service Name") or "").strip()
        desc = " ".join((row.get("Description") or "").split())
        if desc.lower() in ("reserved", "unassigned") and not name:
            continue
        newest = max(newest, row.get("Modification Date") or "", row.get("Registration Date") or "")
        lines.append("\t".join((start, end or start, proto, name, desc.replace("\t", " "))))
    lines.insert(0, f"# IANA Service Name and Transport Protocol Port Number Registry, neuester Eintrag {newest}")
    return lines


def main() -> int:
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")
    lines = convert(text)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    data = ("\n".join(lines) + "\n").encode("utf-8")
    with open(TARGET, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(data)                                   # mtime=0 → gleiche Eingabe, gleiche Datei
    print(f"{len(lines) - 1} Einträge → {TARGET} ({TARGET.stat().st_size} Bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
