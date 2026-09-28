"""Markdown ↔ Zwischenmodell für die formatierte (WYSIWYG-)Bearbeitung – ohne Qt, damit der Roundtrip testbar ist.

Die Wahrheit bleibt Markdown. `parse(md)` erzeugt ein einfaches Blockmodell (Überschriften, Absätze, Listen,
Aufgaben, Zitate, Codeblöcke, Tabellen, Trennlinien) mit Inline-Läufen (Text + fett/kursiv/durchgestrichen/Code/Link).
`to_markdown(doc)` schreibt es wieder als Markdown. Die Oberfläche bildet dieses Modell auf ein QTextDocument ab und
zurück – so bleibt die kniffligste Logik (Struktur ↔ Markdown) hier, Qt-frei und mit Roundtrip-Tests.

Variablen (§name) und Platzhalter sind normaler Text und überstehen den Roundtrip unverändert.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from markdown_it import MarkdownIt


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    strike: bool = False
    code: bool = False
    link: str = ""


@dataclass
class Block:
    type: str                       # heading | para | li | quote | code | hr | table
    runs: list[Run] = field(default_factory=list)
    level: int = 0                  # heading: 1-6; li: Verschachtelungstiefe (0 = oberste)
    ordered: bool = False           # li
    checked: bool | None = None     # li: Aufgabe (None = keine Checkbox)
    text: str = ""                  # code: roher Inhalt
    info: str = ""                  # code: Sprache
    header: list[list[Run]] = field(default_factory=list)   # table: Kopfzellen
    rows: list[list[list[Run]]] = field(default_factory=list)  # table: Datenzellen
    aligns: list[str] = field(default_factory=list)         # table: "", "left", "center", "right"


@dataclass
class Document:
    blocks: list[Block] = field(default_factory=list)


def _parser() -> MarkdownIt:
    md = MarkdownIt("commonmark")
    md.enable(["table", "strikethrough"])
    return md


def _inline_runs(token) -> list[Run]:
    runs: list[Run] = []
    bold = italic = strike = False
    link = ""
    for child in token.children or []:
        t = child.type
        if t == "strong_open":
            bold = True
        elif t == "strong_close":
            bold = False
        elif t == "em_open":
            italic = True
        elif t == "em_close":
            italic = False
        elif t in ("s_open",):
            strike = True
        elif t in ("s_close",):
            strike = False
        elif t == "link_open":
            link = dict(child.attrs).get("href", "")
        elif t == "link_close":
            link = ""
        elif t == "code_inline":
            runs.append(Run(child.content, code=True, link=link))
        elif t == "text":
            runs.append(Run(child.content, bold, italic, strike, False, link))
        elif t == "softbreak":
            runs.append(Run(" ", bold, italic, strike, False, link))
        elif t == "hardbreak":
            runs.append(Run("\n", bold, italic, strike, False, link))
    return _merge(runs)


def _merge(runs: list[Run]) -> list[Run]:
    """Benachbarte Läufe mit gleichen Eigenschaften zusammenfassen (saubereres Markdown)."""
    out: list[Run] = []
    for run in runs:
        if not run.text:
            continue
        if out and not run.code and not out[-1].code and (out[-1].bold, out[-1].italic, out[-1].strike, out[-1].link) \
                == (run.bold, run.italic, run.strike, run.link):
            out[-1] = Run(out[-1].text + run.text, run.bold, run.italic, run.strike, False, run.link)
        else:
            out.append(run)
    return out


def _task_state(runs: list[Run]) -> tuple[bool | None, list[Run]]:
    """Erkennt „[ ] "/„[x] " am Anfang eines Listenpunkts → (checked, Rest-Läufe)."""
    if not runs:
        return None, runs
    head = runs[0].text
    for prefix, value in (("[ ] ", False), ("[x] ", True), ("[X] ", True)):
        if head.startswith(prefix):
            first = Run(head[len(prefix):], runs[0].bold, runs[0].italic, runs[0].strike, runs[0].code, runs[0].link)
            rest = [first] + runs[1:] if first.text else runs[1:]
            return value, rest
    return None, runs


def parse(md: str) -> Document:
    tokens = _parser().parse(md or "")
    doc = Document()
    list_stack: list[bool] = []            # ordered? je Ebene
    pending_li: tuple[int, bool] | None = None   # (Ebene, ordered), sobald ein Listenpunkt offen ist
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            runs = _inline_runs(tokens[i + 1]) if i + 1 < len(tokens) else []
            doc.blocks.append(Block("heading", runs=runs, level=level))
            i += 3
            continue
        if tok.type in ("bullet_list_open", "ordered_list_open"):
            list_stack.append(tok.type == "ordered_list_open")
            i += 1
            continue
        if tok.type in ("bullet_list_close", "ordered_list_close"):
            if list_stack:
                list_stack.pop()
            i += 1
            continue
        if tok.type == "list_item_open":
            pending_li = (max(0, len(list_stack) - 1), list_stack[-1] if list_stack else False)
            i += 1
            continue
        if tok.type == "list_item_close":
            pending_li = None
            i += 1
            continue
        if tok.type == "paragraph_open":
            runs = _inline_runs(tokens[i + 1]) if i + 1 < len(tokens) else []
            if pending_li is not None:          # erster Absatz eines Listenpunkts = dessen Text
                level, ordered = pending_li
                checked, runs = _task_state(runs)
                doc.blocks.append(Block("li", runs=runs, level=level, ordered=ordered, checked=checked))
                pending_li = None               # weitere Absätze/Listen im Punkt normal verarbeiten
            else:
                doc.blocks.append(Block("para", runs=runs))
            i += 3
            continue
        if tok.type == "blockquote_open":
            j = i + 1
            while j < len(tokens) and tokens[j].type != "blockquote_close":
                if tokens[j].type == "inline":
                    doc.blocks.append(Block("quote", runs=_inline_runs(tokens[j])))
                j += 1
            i = j + 1
            continue
        if tok.type == "fence" or tok.type == "code_block":
            doc.blocks.append(Block("code", text=tok.content.rstrip("\n"), info=(tok.info or "").strip()))
            i += 1
            continue
        if tok.type == "hr":
            doc.blocks.append(Block("hr"))
            i += 1
            continue
        if tok.type == "table_open":
            block, i = _parse_table(tokens, i)
            doc.blocks.append(block)
            continue
        i += 1
    return doc


def _parse_table(tokens, i):
    block = Block("table")
    i += 1
    while i < len(tokens) and tokens[i].type != "table_close":
        tok = tokens[i]
        if tok.type == "tr_open":
            cells, aligns, is_header = [], [], False
            i += 1
            while tokens[i].type != "tr_close":
                if tokens[i].type in ("th_open", "td_open"):
                    is_header = tokens[i].type == "th_open"
                    style = dict(tokens[i].attrs).get("style", "")
                    align = "center" if "center" in style else "right" if "right" in style else \
                            "left" if "left" in style else ""
                    runs = _inline_runs(tokens[i + 1]) if tokens[i + 1].type == "inline" else []
                    cells.append(runs)
                    aligns.append(align)
                i += 1
            if is_header:
                block.header = cells
                block.aligns = aligns
            else:
                block.rows.append(cells)
        i += 1
    return block, i + 1


# ---- Serialisierung -------------------------------------------------------------------------------

def _runs_to_md(runs: list[Run]) -> str:
    out = []
    for run in runs:
        text = run.text
        if run.code:
            out.append(f"`{text}`")
            continue
        if run.bold:
            text = f"**{text}**"
        if run.italic:
            text = f"*{text}*"
        if run.strike:
            text = f"~~{text}~~"
        if run.link:
            text = f"[{text}]({run.link})"
        out.append(text)
    return "".join(out)


def _cell(runs: list[Run]) -> str:
    return _runs_to_md(runs).replace("|", "\\|").strip() or " "


def to_markdown(doc: Document) -> str:
    lines: list[str] = []
    prev = None
    for block in doc.blocks:
        if block.type == "heading":
            _blank(lines, prev)
            lines.append("#" * block.level + " " + _runs_to_md(block.runs))
        elif block.type == "para":
            _blank(lines, prev)
            lines.append(_runs_to_md(block.runs))
        elif block.type == "li":
            if prev is not None and prev != "li":     # Leerzeile vor dem ersten Listenpunkt
                _blank(lines, prev)
            indent = "  " * block.level
            if block.checked is not None:
                marker = "- [x] " if block.checked else "- [ ] "
            else:
                marker = "1. " if block.ordered else "- "
            lines.append(indent + marker + _runs_to_md(block.runs))
        elif block.type == "quote":
            _blank(lines, prev)
            lines.append("> " + _runs_to_md(block.runs))
        elif block.type == "code":
            _blank(lines, prev)
            lines.append("```" + block.info)
            lines.extend(block.text.split("\n"))
            lines.append("```")
        elif block.type == "hr":
            _blank(lines, prev)
            lines.append("---")
        elif block.type == "table":
            _blank(lines, prev)
            lines.append("| " + " | ".join(_cell(c) for c in block.header) + " |")
            seps = []
            for idx in range(len(block.header)):
                align = block.aligns[idx] if idx < len(block.aligns) else ""
                seps.append({"left": ":---", "center": ":---:", "right": "---:"}.get(align, "---"))
            lines.append("| " + " | ".join(seps) + " |")
            for row in block.rows:
                lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
        prev = block.type
    return "\n".join(lines) + ("\n" if lines else "")


def _blank(lines: list[str], prev: str | None) -> None:
    """Leerzeile vor einem Blockelement (Listenpunkte selbst rufen dies nicht auf, bleiben also zusammen)."""
    if lines:
        lines.append("")
