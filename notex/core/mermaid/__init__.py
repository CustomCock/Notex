"""Mermaid-Diagramme offline rendern – eigener Renderer in reinem Python (kein JavaScript, kein Browser, kein Netz).

`render(source, colors)` erkennt den Diagrammtyp an der ersten Zeile, parst, ordnet an und liefert ein
`Diagram` mit einem in sich geschlossenen SVG (nur Elemente, die Qts SVG-Renderer kann). Fehler im Mermaid-Code
werden nie zur Exception für die Oberfläche: `render_safe` liefert dann eine Fehlerbox mit Zeilennummer.

Unterstützt: flowchart/graph, sequenceDiagram, classDiagram, stateDiagram(-v2), erDiagram, pie, gantt.
Andere Typen (mindmap, gitGraph, journey …) ergeben einen freundlichen Hinweis statt eines leeren Bereichs.
"""
from __future__ import annotations

import re

from notex.core.mermaid.common import Diagram, MermaidError, preprocess
from notex.core.mermaid.svg import FONT_SIZE, Svg, Theme, block_size, theme_from_colors, text_width

SUPPORTED = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "stateDiagram-v2",
             "erDiagram", "pie", "gantt")
KNOWN_UNSUPPORTED = ("mindmap", "gitGraph", "journey", "timeline", "quadrantChart", "xychart-beta", "sankey-beta",
                     "requirementDiagram", "C4Context", "C4Container", "C4Component", "C4Dynamic", "C4Deployment",
                     "block-beta", "packet-beta", "kanban", "architecture-beta", "radar-beta", "treemap-beta")

__all__ = ["Diagram", "MermaidError", "render", "render_safe", "diagram_kind", "SUPPORTED"]


def diagram_kind(source: str) -> str:
    lines, _title = preprocess(source)
    if not lines:
        return ""
    first = lines[0].text.strip()
    word = re.split(r"[\s;]", first, maxsplit=1)[0]
    return word


def render(source: str, colors: dict[str, str] | None = None) -> Diagram:
    """Mermaid-Quelltext → Diagram. Wirft MermaidError bei Syntaxfehlern oder nicht unterstützten Typen."""
    theme = theme_from_colors(colors)
    lines, title = preprocess(source)
    if not lines:
        raise MermaidError("Leerer Mermaid-Block")
    kind = diagram_kind(source)
    low = kind.lower()
    if low in ("flowchart", "graph"):
        from notex.core.mermaid import flowchart
        return flowchart.render(flowchart.parse(lines), theme, title)
    if low == "sequencediagram":
        from notex.core.mermaid import sequence
        return sequence.render(sequence.parse(lines), theme, title)
    if low == "classdiagram" or low == "classdiagram-v2":
        from notex.core.mermaid import classdiagram
        return classdiagram.render(classdiagram.parse(lines), theme, title)
    if low in ("statediagram", "statediagram-v2"):
        from notex.core.mermaid import state
        return state.render(state.parse(lines), theme, title)
    if low == "erdiagram":
        from notex.core.mermaid import er
        return er.render(er.parse(lines), theme, title)
    if low == "pie":
        from notex.core.mermaid import pie
        return pie.render(pie.parse(lines), theme, title)
    if low == "gantt":
        from notex.core.mermaid import gantt
        return gantt.render(gantt.parse(lines), theme, title)
    if kind in KNOWN_UNSUPPORTED:
        raise MermaidError(f"Der Diagrammtyp „{kind}“ wird (noch) nicht unterstützt. Möglich: flowchart, "
                           "sequenceDiagram, classDiagram, stateDiagram, erDiagram, pie, gantt.", lines[0].no)
    raise MermaidError(f"Unbekannter Diagrammtyp „{kind[:40]}“ – die erste Zeile muss den Typ nennen "
                       "(z. B. „flowchart TD“).", lines[0].no)


def render_safe(source: str, colors: dict[str, str] | None = None) -> tuple[Diagram, str]:
    """Wie render, aber nie eine Exception: bei Fehlern eine Fehlerbox. Liefert (Diagramm, Fehlertext oder "")."""
    try:
        return render(source, colors), ""
    except MermaidError as error:
        return error_diagram(str(error), colors), str(error)
    except RecursionError:
        message = "Diagramm zu tief verschachtelt"
        return error_diagram(message, colors), message
    except Exception as error:                          # noqa: BLE001 – Renderfehler dürfen die Vorschau nie leeren
        message = f"Interner Fehler beim Zeichnen ({type(error).__name__}: {error})"
        return error_diagram(message, colors), message


def error_diagram(message: str, colors: dict[str, str] | None = None) -> Diagram:
    theme: Theme = theme_from_colors(colors)
    svg = Svg(theme)
    size = FONT_SIZE * 0.95
    words, lines, cur = message.split(), [], ""
    for word in words:                                  # schlicht umbrechen (max. ~70 Zeichen je Zeile)
        if cur and text_width(cur + " " + word, size) > 520:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    width = max([text_width(line, size) for line in lines] + [text_width("Mermaid-Diagramm", size, True)]) + 36
    height = 34 + len(lines) * size * 1.35 + 12
    svg.rect(1, 1, width - 2, height - 2, theme.bg, theme.danger, 1.4, rx=6)
    svg.text(16, 24, "Mermaid-Diagramm – nicht darstellbar", size, anchor="start", bold=True, fill=theme.danger)
    for i, line in enumerate(lines):
        svg.text(16, 24 + (i + 1) * size * 1.35, line, size, anchor="start", fill=theme.text)
    _ = block_size
    return Diagram("error", svg.to_string(width, height), width, height)
