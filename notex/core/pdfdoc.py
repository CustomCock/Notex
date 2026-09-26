"""PDF-Ansicht ohne Qt: Seiten-Layout (Zoom, Positionen, Treffer) und das Zitat-Format für Notizen.

Die Seiten stehen untereinander, zentriert, mit festem Abstand. Größen kommen in Punkt (1/72 Zoll) aus dem
Dokument; `scale` = Pixel pro Punkt. Alle Umrechnungen Ansicht ↔ Seite liegen hier, damit sie testbar sind.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

POINTS_PER_INCH = 72.0
PAGE_GAP = 16
MARGIN = 16
MIN_ZOOM, MAX_ZOOM = 0.1, 8.0


@dataclass(frozen=True)
class PageRect:
    index: int
    x: float
    y: float
    width: float
    height: float

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


class PageLayout:
    def __init__(self, sizes_pt: list[tuple[float, float]], scale: float, viewport_width: float) -> None:
        self.sizes = sizes_pt
        self.scale = scale
        self.pages: list[PageRect] = []
        widest = max((w for w, _h in sizes_pt), default=0) * scale
        self.width = max(viewport_width, widest + 2 * MARGIN)
        y = MARGIN
        for index, (w, h) in enumerate(sizes_pt):
            pw, ph = w * scale, h * scale
            self.pages.append(PageRect(index, (self.width - pw) / 2, y, pw, ph))
            y += ph + PAGE_GAP
        self.height = y - PAGE_GAP + MARGIN if sizes_pt else 2 * MARGIN
        self._tops = [p.y for p in self.pages]

    def page_at_y(self, y: float) -> int:
        """Seite an einer Höhe (auch im Abstand dazwischen: die darüber). 0 bei leerem Dokument."""
        if not self.pages:
            return 0
        return max(0, min(len(self.pages) - 1, bisect_right(self._tops, y) - 1))

    def visible(self, top: float, bottom: float) -> list[PageRect]:
        first = self.page_at_y(top)
        out = []
        for page in self.pages[first:]:
            if page.y > bottom:
                break
            if page.y + page.height >= top:
                out.append(page)
        return out

    def hit(self, x: float, y: float) -> tuple[int, float, float] | None:
        """Ansicht (Dokumentkoordinaten) → (Seite, x_pt, y_pt) oder None außerhalb der Seiten."""
        if not self.pages:
            return None
        page = self.pages[self.page_at_y(y)]
        if not page.contains(x, y):
            return None
        return page.index, (x - page.x) / self.scale, (y - page.y) / self.scale

    def clamp_hit(self, index: int, x: float, y: float) -> tuple[float, float]:
        """Beim Ziehen über den Seitenrand hinaus: Punkt auf die Seite `index` klemmen (in Punkt)."""
        page = self.pages[index]
        w, h = self.sizes[index]
        return (min(max((x - page.x) / self.scale, 0.0), w), min(max((y - page.y) / self.scale, 0.0), h))

    def to_view(self, index: int, x_pt: float, y_pt: float) -> tuple[float, float]:
        page = self.pages[index]
        return page.x + x_pt * self.scale, page.y + y_pt * self.scale


def fit_width_scale(sizes_pt: list[tuple[float, float]], viewport_width: float) -> float:
    widest = max((w for w, _h in sizes_pt), default=595.0)
    return max(MIN_ZOOM, (viewport_width - 2 * MARGIN) / widest)


def fit_page_scale(size_pt: tuple[float, float], viewport_width: float, viewport_height: float) -> float:
    w, h = size_pt
    return max(MIN_ZOOM, min((viewport_width - 2 * MARGIN) / max(w, 1), (viewport_height - 2 * MARGIN) / max(h, 1)))


def snap_to_lines(lines: list[tuple[float, float, float, float]], x: float, y: float,
                  inset: float = 1.0) -> tuple[float, float] | None:
    """Punkt (in Punkt) auf die nächste Textzeile ziehen: `lines` = (x0, y0, x1, y1) je Zeile. PDFium findet ein
    Zeichen nur, wenn der Punkt genau darauf liegt – so trifft auch ein Klick neben/zwischen die Zeilen."""
    if not lines:
        return None

    def distance(box):
        x0, y0, x1, y1 = box
        dy = 0.0 if y0 <= y <= y1 else min(abs(y - y0), abs(y - y1))
        dx = 0.0 if x0 <= x <= x1 else min(abs(x - x0), abs(x - x1))
        return dy * 4 + dx                  # Zeilen sind wichtiger als Spalten

    x0, y0, x1, y1 = min(lines, key=distance)
    return min(max(x, x0 + inset), x1 + inset), (y0 + y1) / 2     # rechts knapp dahinter: letztes Zeichen gehört dazu


def clean_selection(text: str) -> str:
    """PDF-Text aufräumen: Silbentrennung am Zeilenende zusammenziehen, Zeilen eines Absatzes verbinden."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00ad", "")
    for marker in ("\ufffe", "\x02"):                      # PDFium markiert Trennstriche am Zeilenende so
        text = text.replace(marker + "\n", "").replace(marker, "")
    lines = [line.strip() for line in text.split("\n")]
    paragraphs: list[str] = []
    current = ""
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if current.endswith("-") and len(current) > 1 and current[-2].isalpha() and line[:1].islower():
            current = current[:-1] + line
        else:
            current = f"{current} {line}" if current else line
    if current:
        paragraphs.append(current)
    return "\n\n".join(paragraphs)


def quote_markdown(text: str, file_name: str, page_label: str) -> str:
    """Markierten PDF-Text als Markdown-Zitat mit Quelle: „> …\\n>\\n> — *datei.pdf*, S. 3“."""
    body = clean_selection(text)
    if not body:
        return ""
    quoted = "\n".join(f"> {line}" if line else ">" for line in body.split("\n"))
    name = file_name.replace("*", "\\*")
    return f"{quoted}\n>\n> — *{name}*, S. {page_label}\n"
