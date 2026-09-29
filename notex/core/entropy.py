"""Entropie: Shannon-Entropie je Block (0–8 Bit pro Byte), Gesamtwert, Einschätzung, auffällige Bereiche. Ohne Qt.

Faustregeln: Text und strukturierte Daten liegen meist bei 4–5, Programmcode bei 5–6,5, komprimierte oder
verschlüsselte Daten nahe 8. Sehr niedrige Werte bedeuten Füllbytes oder leere Bereiche. Die Datei wird blockweise
gestreamt (mehrere GB möglich), die Häufigkeiten aller Blöcke ergeben die Gesamtentropie.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HIGH = 7.5          # darüber: komprimiert/verschlüsselt
LOW = 2.0           # darunter: Füllbytes, leere Bereiche
TARGET_POINTS = 2000
BLOCK_SIZES = [1024, 4096, 16384, 65536, 262144, 1048576]     # < 1 KB: zu wenige Bytes für eine Aussage
READ = 4 * 1024 * 1024


class Cancelled(Exception):
    pass


def shannon(data: bytes) -> float:
    return _from_counts(Counter(data), len(data))


def _from_counts(counts, total: int) -> float:
    if not total:
        return 0.0
    return -sum(c / total * math.log2(c / total) for c in counts.values() if c)


def _block_entropy(counts, total: int) -> float:
    """Entropie eines Blocks mit Miller-Madow-Korrektur: kleine Stichproben unterschätzen die Entropie
    (1 KB Zufallsdaten ergäben sonst ~7,8 statt ~8,0 und fielen unter die Schwelle 7,5)."""
    raw = _from_counts(counts, total)
    if total <= 1:
        return raw
    return min(8.0, raw + (len(counts) - 1) / (2 * total * math.log(2)))


def auto_block_size(size: int) -> int:
    """Blockgröße, die etwa TARGET_POINTS Punkte ergibt (Zweierpotenz, 256 B bis 1 MB)."""
    wanted = max(1, size // TARGET_POINTS)
    for block in BLOCK_SIZES:
        if block >= wanted:
            return block
    return BLOCK_SIZES[-1] * max(1, 2 ** math.ceil(math.log2(wanted / BLOCK_SIZES[-1])))


@dataclass
class Profile:
    size: int
    block_size: int
    values: list[float] = field(default_factory=list)
    total: float = 0.0

    def offset_of(self, index: int) -> int:
        return index * self.block_size


def profile(path: Path | str, block_size: int | None = None, *, progress: Callable[[int, int], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> Profile:
    path = Path(path)
    size = path.stat().st_size
    block = block_size or auto_block_size(size)
    result = Profile(size, block)
    counts: Counter = Counter()
    read = max(block, READ // block * block)            # ganze Blöcke je Lesevorgang
    done = 0
    with open(path, "rb") as handle:
        while True:
            if cancelled is not None and cancelled():
                raise Cancelled()
            data = handle.read(read)
            if not data:
                break
            for start in range(0, len(data), block):
                piece = data[start:start + block]
                piece_counts = Counter(piece)
                result.values.append(_block_entropy(piece_counts, len(piece)))
                counts.update(piece_counts)
            done += len(data)
            if progress is not None:
                progress(done, size)
    result.total = _from_counts(counts, size)
    return result


def assess(prof: Profile) -> str:
    """Einschätzung in einem Satz – Gesamtwert plus Verteilung der Blöcke."""
    if not prof.values:
        return "Leere Datei"
    high = sum(1 for v in prof.values if v >= HIGH) / len(prof.values)
    low = sum(1 for v in prof.values if v < LOW) / len(prof.values)
    total = prof.total
    if high >= 0.9:
        return "Komprimiert oder verschlüsselt (fast überall ≥ 7,5)"
    if high >= 0.15 and high + low < 0.95 and (total < HIGH or low >= 0.05):
        return f"Gemischt – {round(high * 100)} % der Datei wirken komprimiert/verschlüsselt (eingebettete Daten?)"
    if total < 1.0 or low >= 0.9:
        return "Fast leer oder gleichförmig (Füllbytes)"
    if total < 5.0:
        return "Text oder einfach strukturierte Daten"
    if total < 7.2:
        return "Gemischt/strukturiert (z. B. Programmcode, Dokumente, Bilder mit Metadaten)"
    return "Vermutlich komprimiert"


def regions(prof: Profile) -> list[tuple[int, int, str]]:
    """Zusammenhängende Bereiche (Start, Ende exklusiv, "high"|"low") in Bytes."""
    out: list[tuple[int, int, str]] = []
    for index, value in enumerate(prof.values):
        kind = "high" if value >= HIGH else "low" if value < LOW else None
        start, end = prof.offset_of(index), min(prof.size, prof.offset_of(index + 1))
        if kind is None:
            continue
        if out and out[-1][2] == kind and out[-1][1] == start:
            out[-1] = (out[-1][0], end, kind)
        else:
            out.append((start, end, kind))
    return out


def format_value(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")
