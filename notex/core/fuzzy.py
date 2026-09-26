"""Fuzzy-Matching für Quick Open und Command Palette – ohne Qt.

match("ntz", "notizen.md") findet n-o-t-i-z: alle Zeichen der Anfrage kommen in
dieser Reihenfolge im Text vor. Der Score belohnt Treffer am Wortanfang, direkt
hintereinander und früh im Text; große Lücken kosten Punkte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SEPARATORS = set(" _-./\\:()[]")
_LINE_SUFFIX = re.compile(r"^(.*?):(\d+)$")


@dataclass(frozen=True)
class Match:
    score: float
    indices: tuple[int, ...]     # Positionen der getroffenen Zeichen im Text


def match(query: str, text: str) -> Match | None:
    """Bester Treffer der Anfrage im Text oder None. Leere Anfrage trifft alles mit Score 0."""
    if not query:
        return Match(0.0, ())
    q, t = query.lower(), text.lower()
    if len(q) > len(t):
        return None
    # Gieriger Durchlauf mit Rückversuch am Wortanfang: erst ab Wortanfängen suchen, dann irgendwo
    best: Match | None = None
    for start in _candidate_starts(q[0], t):
        result = _match_from(q, t, start)
        if result is not None and (best is None or result.score > best.score):
            best = result
    return best


def _candidate_starts(first: str, t: str) -> list[int]:
    starts = [i for i, ch in enumerate(t) if ch == first]
    return starts[:12]   # mehr Startpunkte bringen kaum bessere Treffer, kosten aber Zeit


def _match_from(q: str, t: str, start: int) -> Match | None:
    indices: list[int] = []
    pos = start
    for ch in q:
        found = t.find(ch, pos)
        if found < 0:
            return None
        indices.append(found)
        pos = found + 1
    score = 0.0
    previous = -2
    for i in indices:
        if i == 0 or t[i - 1] in _SEPARATORS:
            score += 10          # Wortanfang
        elif i == previous + 1:
            score += 6           # direkt hintereinander
        else:
            score += 1
            score -= min(5, (i - previous - 1) * 0.3)   # Lücke
        previous = i
    score -= indices[0] * 0.15    # früher Beginn ist besser
    score -= (len(t) - len(q)) * 0.02   # kürzere Texte leicht bevorzugen
    if t == q:
        score += 25
    elif t.startswith(q):
        score += 12
    return Match(round(score, 3), tuple(indices))


def highlight(text: str, indices: tuple[int, ...], open_tag: str, close_tag: str) -> str:
    """Text mit markierten Trefferzeichen (Tags werden roh eingefügt, Text muss vorher escaped sein
    – dafür gibt es highlight_escaped)."""
    marks = set(indices)
    out = []
    for i, ch in enumerate(text):
        out.append(f"{open_tag}{ch}{close_tag}" if i in marks else ch)
    return "".join(out)


def parse_goto(query: str) -> tuple[str, int | None]:
    """':123' -> ('', 123), 'datei:12' -> ('datei', 12), 'datei' -> ('datei', None)."""
    m = _LINE_SUFFIX.match(query.strip())
    if m:
        return m.group(1).strip(), int(m.group(2))
    return query.strip(), None
