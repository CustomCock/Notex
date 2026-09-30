"""Mermaid-Renderer (notex/core/mermaid): Parser je Diagrammtyp, Layout, SVG-Ausgabe, Fehler – ohne Qt."""
import xml.etree.ElementTree as ET

import pytest

from notex.core import export, markdown
from notex.core import mermaid
from notex.core.mermaid import (classdiagram, er, flowchart, gantt, layout as lay, pie, sequence, state)
from notex.core.mermaid.common import MermaidError, parse_style, preprocess, unquote
from notex.core.mermaid.examples import EXAMPLES, fence, insertion
from notex.core.mermaid.svg import text_width, theme_from_colors

LIGHT = {"bg": "#ffffff", "text": "#222222", "muted": "#777777", "accent": "#3366cc", "danger": "#cc3333"}
DARK = {"bg": "#1e1f22", "text": "#e6e6e6", "muted": "#8a8f98", "accent": "#6ea8fe", "danger": "#ff6b6b"}


def lines(src: str):
    return preprocess(src)[0]


def svg_ok(diagram) -> ET.Element:
    """Wohlgeformt, SVG-Wurzel, feste Größe, nichts, was Qts SVG-Tiny-Renderer nicht kann oder was nachlädt."""
    root = ET.fromstring(diagram.svg)
    assert root.tag.endswith("svg")
    assert diagram.width > 0 and diagram.height > 0
    text = diagram.svg
    for forbidden in ("<script", "<foreignObject", "<marker", "<style", "href=", "url(", "<image"):
        assert forbidden not in text, forbidden
    return root


# ---- Beispiele: alle Typen, hell und dunkel ------------------------------------------------------------------------
@pytest.mark.parametrize("kind", list(EXAMPLES))
@pytest.mark.parametrize("colors", [LIGHT, DARK, None])
def test_every_example_renders_valid_svg(kind, colors):
    diagram = mermaid.render(EXAMPLES[kind][1], colors)
    svg_ok(diagram)
    assert diagram.kind != "error"


def test_theme_follows_background_luminance():
    assert not theme_from_colors(LIGHT).dark
    assert theme_from_colors(DARK).dark
    assert theme_from_colors(None).bg


# ---- Vorverarbeitung ---------------------------------------------------------------------------------------------
def test_preprocess_strips_comments_directives_and_reads_frontmatter_title():
    src = "---\ntitle: Mein Titel\n---\n%%{init: {'theme':'dark'}}%%\nflowchart LR\n  %% Kommentar\n  A --> B\n"
    ls, title = preprocess(src)
    assert title == "Mein Titel"
    assert [line.text.strip() for line in ls] == ["flowchart LR", "A --> B"]
    assert ls[1].no == 7                                        # Zeilennummern bleiben die des Quelltexts


def test_unquote_and_entities():
    assert unquote('"Hallo Welt"') == "Hallo Welt"
    assert unquote("`**fett**`") == "fett"
    assert unquote("A #amp; B") == "A & B"


def test_parse_style_keeps_only_safe_properties():
    style = parse_style("fill:#f9f,stroke:#333,stroke-width:4px,background:url(http://x),onload:alert(1)")
    assert style == {"fill": "#f9f", "stroke": "#333", "stroke-width": "4px"}


def test_text_width_grows_with_text_and_bold():
    assert text_width("WWW", 14) > text_width("iii", 14)
    assert text_width("Abc", 14, True) > text_width("Abc", 14)


# ---- Flussdiagramm -----------------------------------------------------------------------------------------------
def test_flowchart_shapes_edges_and_labels():
    fc = flowchart.parse(lines("""flowchart LR
        A[Rechteck] --> B(Rund)
        B -- Text --> C{Raute}
        C -->|Ja| D([Stadion])
        C -.-> E((Kreis))
        E ==> F[(DB)]
        F --- G>Fahne]
        A --o H & I
        """))
    assert fc.direction == "LR"
    shapes = {k: n.shape for k, n in fc.nodes.items()}
    assert shapes["A"] == "rect" and shapes["B"] == "round" and shapes["C"] == "rhombus"
    assert shapes["D"] == "stadium" and shapes["E"] == "circle" and shapes["F"] == "cylinder" and shapes["G"] == "flag"
    by = {(e.src, e.dst): e for e in fc.edges}
    assert by[("B", "C")].label == "Text" and by[("B", "C")].end == "arrow"
    assert by[("C", "D")].label == "Ja"
    assert by[("C", "E")].line == "dotted"
    assert by[("E", "F")].line == "thick"
    assert by[("F", "G")].end is None
    assert by[("A", "H")].end == "circle" and ("A", "I") in by


def test_flowchart_chain_and_graph_keyword():
    fc = flowchart.parse(lines("graph TD\n A --> B --> C; C --> A"))
    assert [(e.src, e.dst) for e in fc.edges] == [("A", "B"), ("B", "C"), ("C", "A")]
    svg_ok(flowchart.render(fc, theme_from_colors(LIGHT)))          # Zyklus: Layout bricht ihn auf


def test_flowchart_subgraphs_membership_and_edges_to_clusters():
    src = """flowchart TB
        X --> Y
        subgraph eins [Erster Block]
          direction LR
          A --> B
          X
        end
        subgraph zwei
          C
        end
        eins --> zwei
        """
    fc = flowchart.parse(lines(src))
    assert fc.subgraphs["eins"].title == "Erster Block"
    assert fc.subgraphs["eins"].direction == "LR"
    assert fc.membership["A"] == "eins" and fc.membership["X"] == "eins" and fc.membership["C"] == "zwei"
    assert "Y" not in fc.membership
    diagram = mermaid.render(src, LIGHT)
    svg_ok(diagram)


def test_flowchart_classdef_and_style_applied():
    src = "flowchart TD\n A:::rot --> B\n classDef rot fill:#ff0000,color:#ffffff\n style B stroke:#00ff00\n"
    fc = flowchart.parse(lines(src))
    assert fc.class_defs["rot"]["fill"] == "#ff0000"
    assert fc.nodes["B"].style["stroke"] == "#00ff00"
    svg = mermaid.render(src, LIGHT).svg
    assert "#ff0000" in svg and "#00ff00" in svg


def test_flowchart_escapes_markup_in_labels():
    diagram = mermaid.render('flowchart TD\n A["<script>alert(1)</script> & Co"] --> B', LIGHT)
    root = svg_ok(diagram)
    texts = "".join(t.text or "" for t in root.iter() if t.tag.endswith("text") or t.tag.endswith("tspan"))
    assert "<script>" in texts and "& Co" in texts                 # als Text, nicht als Element


# ---- Sequenz -----------------------------------------------------------------------------------------------------
def test_sequence_participants_messages_blocks():
    seq = sequence.parse(lines("""sequenceDiagram
        autonumber
        actor U as Nutzer
        participant S as Server
        U->>+S: Login
        S-->>-U: OK
        loop Jede Minute
          U-)S: Ping
        end
        alt Fehler
          S-xU: Abbruch
        else Normal
          Note over U,S: alles gut
        end
        """))
    assert seq.autonumber
    assert seq.participants["U"].kind == "actor" and seq.participants["S"].label == "Server"
    msgs = [e.data for e in seq.events if e.kind == "msg"]
    assert [m.text for m in msgs] == ["Login", "OK", "Ping", "Abbruch"]
    assert msgs[0].activate and msgs[1].deactivate and msgs[1].dotted
    assert msgs[3].head == "cross"
    kinds = [e.kind for e in seq.events]
    assert kinds.count("start") == 2 and kinds.count("end") == 2 and "else" in kinds and "note" in kinds


def test_sequence_unbalanced_end_is_reported_with_line():
    with pytest.raises(MermaidError) as err:
        mermaid.render("sequenceDiagram\n A->>B: hi\n end\n", LIGHT)
    assert err.value.line == 3


# ---- Klassen -----------------------------------------------------------------------------------------------------
def test_class_members_annotations_and_relations():
    model = classdiagram.parse(lines("""classDiagram
        class Tier {
          <<abstract>>
          +String name
          +laut()* void
        }
        class Liste~T~
        Tier <|-- Hund : erbt
        Halter "1" --> "*" Hund
        Tier : +int alter
        """))
    tier = model.classes["Tier"]
    assert tier.annotation.strip("<>") == "abstract"
    assert "+String name" in tier.attributes and "+int alter" in tier.attributes
    assert any("laut" in m for m in tier.methods)
    assert model.classes["Liste"].label == "Liste<T>"
    rel = {(r.a, r.b): r for r in model.relations}
    assert rel[("Tier", "Hund")].left == "triangle" and rel[("Tier", "Hund")].label == "erbt"
    assert rel[("Halter", "Hund")].card_a == "1" and rel[("Halter", "Hund")].card_b == "*"


# ---- Zustände ----------------------------------------------------------------------------------------------------
def test_state_start_end_composites_and_pseudostates():
    model = state.parse(lines("""stateDiagram-v2
        [*] --> Aus
        Aus --> An : Schalter
        state An {
          [*] --> Hell
          Hell --> Dunkel
        }
        state gabel <<fork>>
        state wahl <<choice>>
        An --> [*]
        """))
    kinds = {s.kind for s in model.states.values()}
    assert {"start", "end", "fork", "choice"} <= kinds
    assert "An" in model.composites
    assert model.membership.get("Hell") == "An"
    starts = [s for s in model.states.values() if s.kind == "start"]
    assert len(starts) == 2                                         # [*] je Ebene eigener Startpunkt
    assert any(t.label == "Schalter" for t in model.transitions)


# ---- ER, Kreis, Gantt --------------------------------------------------------------------------------------------
def test_er_entities_attributes_and_cardinalities():
    model = er.parse(lines("""erDiagram
        KUNDE ||--o{ BESTELLUNG : gibt
        BESTELLUNG }|..|{ ARTIKEL : enthaelt
        KUNDE {
          int id PK "Schlüssel"
          string mail UK
        }
        """))
    k = model.entities["KUNDE"]
    assert [(a.type, a.name, a.keys, a.comment) for a in k.attributes] == [
        ("int", "id", "PK", "Schlüssel"), ("string", "mail", "UK", "")]
    r1, r2 = model.relations
    assert (r1.card_a, r1.card_b, r1.identifying) == ("one", "zero_many", True)
    assert (r2.card_a, r2.card_b, r2.identifying) == ("one_many", "one_many", False)


def test_pie_values_and_errors():
    p = pie.parse(lines('pie showData title Anteile\n "A" : 1\n "B" : 2,5\n'))
    assert p.show_data and p.title == "Anteile" and p.slices == [("A", 1.0), ("B", 2.5)]
    with pytest.raises(MermaidError):
        mermaid.render('pie\n "A" : -1\n', LIGHT)
    with pytest.raises(MermaidError):
        mermaid.render('pie\n "A" : 0\n', LIGHT)                    # Summe 0


def test_gantt_dates_durations_after_and_weekends():
    g = gantt.parse(lines("""gantt
        dateFormat YYYY-MM-DD
        excludes weekends
        section A
        Eins :a1, 2025-01-03, 2d
        Zwei :after a1, 1d
        Drei :done, d3, 2025-01-10, 2025-01-12
        Meilenstein :milestone, 2025-01-12, 0d
        """))
    eins, zwei, drei, ms = g.tasks
    assert eins.start.isoformat()[:10] == "2025-01-03"
    assert eins.end.isoformat()[:10] == "2025-01-07"                # Fr + 2 Arbeitstage (Wochenende übersprungen)
    assert zwei.start == eins.end
    assert "done" in drei.tags and drei.id == "d3"
    assert "milestone" in ms.tags and ms.start == ms.end
    with pytest.raises(MermaidError):
        mermaid.render("gantt\n Aufgabe :after fehlt, 1d\n", LIGHT)


# ---- Layout ------------------------------------------------------------------------------------------------------
def _overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


@pytest.mark.parametrize("direction", ["TB", "LR", "BT", "RL"])
def test_layout_nodes_do_not_overlap_and_stay_inside(direction):
    nodes = [lay.LNode(n, 60 + i * 7, 30) for i, n in enumerate("ABCDEFG")]
    edges = [lay.LEdge(i, a, b, 20 if i % 2 else 0, 12 if i % 2 else 0) for i, (a, b) in
             enumerate([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("D", "E"), ("E", "A"), ("F", "G")])]
    L = lay.layout(nodes, edges, direction=direction)
    boxes = {n.id: (L.nodes[n.id][0] - n.w / 2, L.nodes[n.id][1] - n.h / 2, n.w, n.h) for n in nodes}
    ids = list(boxes)
    for i, a in enumerate(ids):
        x, y, w, h = boxes[a]
        assert x >= -0.5 and y >= -0.5 and x + w <= L.width + 0.5 and y + h <= L.height + 0.5
        for b in ids[i + 1:]:
            assert not _overlap(boxes[a], boxes[b]), (a, b)
    assert set(L.edges) == {e.key for e in edges}
    assert all(len(pts) >= 2 for pts in L.edges.values())
    y_of = {k: L.nodes[k][1] for k in "ABD"}
    if direction == "TB":
        assert y_of["A"] < y_of["B"] < y_of["D"]                    # Kanten zeigen nach unten
    if direction == "BT":
        assert y_of["A"] > y_of["B"] > y_of["D"]


def test_layout_clusters_contain_their_members():
    nodes = [lay.LNode(n, 50, 30) for n in "ABCD"]
    edges = [lay.LEdge(0, "A", "B"), lay.LEdge(1, "B", "C"), lay.LEdge(2, "C", "D")]
    clusters = [lay.LCluster("aussen", None, None, 60, 16), lay.LCluster("innen", "aussen", "LR", 40, 16)]
    L = lay.layout(nodes, edges, clusters, {"B": "aussen", "C": "innen", "D": "innen"})
    for node, cid in (("B", "aussen"), ("C", "innen"), ("D", "innen"), ("C", "aussen")):
        cx, cy, cw, ch = L.clusters[cid]
        x, y = L.nodes[node]
        assert cx < x - 25 and x + 25 < cx + cw and cy < y - 15 and y + 15 < cy + ch, (node, cid)
    ax, ay, aw, ah = L.clusters["aussen"]
    ix, iy, iw, ih = L.clusters["innen"]
    assert ax <= ix and ay <= iy and ix + iw <= ax + aw and iy + ih <= ay + ah
    x, y = L.nodes["A"]
    assert not (ax < x < ax + aw and ay < y < ay + ah)              # A liegt außerhalb


# ---- Fehler und Grenzen ------------------------------------------------------------------------------------------
def test_unsupported_and_unknown_types_give_friendly_errors():
    with pytest.raises(MermaidError, match="nicht unterstützt"):
        mermaid.render("mindmap\n  root\n", LIGHT)
    with pytest.raises(MermaidError, match="Unbekannter Diagrammtyp"):
        mermaid.render("blubb\n", LIGHT)
    with pytest.raises(MermaidError, match="Leer"):
        mermaid.render("%% nur Kommentar\n", LIGHT)


def test_render_safe_never_raises_and_returns_error_box():
    diagram, error = mermaid.render_safe("flowchart TD\n A --> \n", LIGHT)
    assert error and diagram.kind == "error"
    svg_ok(diagram)
    assert "nicht darstellbar" in diagram.svg
    ok, none = mermaid.render_safe(EXAMPLES["pie"][1], LIGHT)
    assert none == "" and ok.kind == "pie"


def test_error_message_names_line():
    _, error = mermaid.render_safe('pie\n "A" : 1\n kaputt\n', LIGHT)
    assert error.startswith("Zeile 3")


def test_too_many_elements_is_limited():
    src = "flowchart TD\n" + "\n".join(f" n{i} --> n{i + 1}" for i in range(500))
    diagram, error = mermaid.render_safe(src, LIGHT)
    assert error and diagram.kind == "error"


def test_diagram_kind():
    assert mermaid.diagram_kind("%% x\ngraph LR\nA-->B") == "graph"
    assert mermaid.diagram_kind("stateDiagram-v2\n") == "stateDiagram-v2"


# ---- Einbindung: Markdown, Export, Palette-Beispiele ---------------------------------------------------------------
def test_markdown_fence_becomes_image_with_diagram():
    md = "# T\n\n```mermaid\nflowchart LR\n A --> B\n```\n"
    result = markdown.render(md, markdown.RenderOptions(colors=dict(LIGHT)))
    assert len(result.diagrams) == 1
    key = next(iter(result.diagrams))
    assert f'src="notex-mermaid:{key}"' in result.html
    assert "<pre" not in result.html


def test_markdown_fence_off_shows_code_and_width_is_capped():
    md = "```mermaid\nflowchart LR\n A --> B\n```\n"
    off = markdown.render(md, markdown.RenderOptions(colors=dict(LIGHT), diagrams=False))
    assert not off.diagrams and "<pre" in off.html and "notex-mermaid" not in off.html
    wide = "```mermaid\nflowchart LR\n" + "\n".join(f" n{i}[Ein recht langer Knoten {i}] --> n{i + 1}"
                                                   for i in range(12)) + "\n```\n"
    capped = markdown.render(wide, markdown.RenderOptions(colors=dict(LIGHT), max_diagram_width=300))
    assert 'width="300"' in capped.html


def test_markdown_broken_fence_shows_error_box_and_source():
    md = "```mermaid\nflowchart TD\n A --> \n```\n"
    result = markdown.render(md, markdown.RenderOptions(colors=dict(LIGHT)))
    assert "notex-mermaid:" in result.html and "<pre" in result.html
    assert next(iter(result.diagrams.values())).kind == "error"


def test_html_export_embeds_svg_and_body_parts_lists_diagrams():
    md = "```mermaid\npie\n \"A\" : 1\n```\n"
    html = export.to_html_document(md, "markdown", export.ExportMeta(title="T"), name="n.md")
    assert "data:image/svg+xml;base64," in html and "notex-mermaid:" not in html
    body, diagrams = export.body_parts(md, "markdown", name="n.md")
    assert len(diagrams) == 1 and "notex-mermaid:" in body
    assert export.body_html(md, "markdown", name="n.md") == body


def test_examples_fence_and_insertion():
    assert fence("pie").startswith("```mermaid\npie") and fence("pie").endswith("```\n")
    assert insertion("pie", "") == fence("pie")
    assert insertion("pie", "Text davor") == "\n" + fence("pie")
    assert {label for label, _ in EXAMPLES.values()} >= {"Flussdiagramm", "Gantt-Diagramm"}
