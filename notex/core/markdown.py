"""Markdown → HTML für die Vorschau. Ohne Qt, damit der Renderer testbar ist.

Sicherheitsregeln (die Vorschau zeigt fremde Notizen an, z. B. importierte Dateien):
- Rohes HTML im Markdown wird NICHT durchgereicht (markdown-it mit html=False escaped es).
- Links: nur http(s), mailto, #Anker und relative Pfade innerhalb des Notizordners. Alles andere
  (javascript:, data:, file:, vbscript:, absolute Pfade) wird zu reinem Text.
- Bilder: lokale Bilder nur aus dem Notizordner (relativ zur Datei). Externe Bilder werden nie
  automatisch geladen, sondern als Platzhalter mit „Bild laden“-Link gerendert; erst wenn die
  URL in `loaded_images` steht (Nutzer hat geklickt), entsteht ein <img>.
- Kein JavaScript: QTextBrowser führt ohnehin keins aus, und wir erzeugen keins.

Eigene URL-Schemata für die Vorschau (verarbeitet die UI, nie ein Browser):
  notex-open:<relativer Pfad>[#Überschrift]   relative Markdown-Links und [[Wiki-Links]]
  notex-toggle:<Zeile>                          Checkbox einer Aufgabe umschalten (0-basiert)
  notex-load:<URL>                              externes Bild nachladen
  notex-mermaid:<Schlüssel>                     Mermaid-Diagramm (SVG aus RenderResult.diagrams, offline gerendert)
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from notex.core import syntax
from notex.core.wikilinks import LINK_RE as WIKI_RE

SAFE_SCHEMES = ("http", "https", "mailto")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg")
TASK_RE = re.compile(r"^\[( |x|X)\]\s")
LINE_TASK_RE = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\](\s.*|)$")


@dataclass
class RenderOptions:
    colors: dict[str, str] = field(default_factory=dict)   # text, muted, accent, code_bg, border, danger + Syntax-Klassen
    loaded_images: set[str] = field(default_factory=set)   # externe Bild-URLs, die der Nutzer freigegeben hat
    base_dir: str = ""      # Ordner der Datei (relativ zum Notizordner, "" = Wurzel) für relative Pfade
    max_source_chars: int = 2_000_000
    diagrams: bool = True           # ```mermaid als Diagramm zeigen (sonst als Code)
    max_diagram_width: int = 0      # > 0: breitere Diagramme proportional verkleinern (Anzeigebreite)


@dataclass
class RenderResult:
    html: str
    external_images: list[str] = field(default_factory=list)   # URLs, die als Platzhalter gerendert wurden
    task_lines: list[int] = field(default_factory=list)        # 0-basierte Zeilen mit Checkbox
    truncated: bool = False
    diagrams: dict = field(default_factory=dict)               # Schlüssel → mermaid.Diagram (für notex-mermaid:)


def slugify(heading: str) -> str:
    """Anker-Name einer Überschrift: klein, Leerzeichen zu '-', nur Buchstaben/Ziffern/-_."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug.strip("-") or "abschnitt"


def classify_url(url: str) -> tuple[str, str]:
    """(Art, Wert): "external" (http/https/mailto), "anchor" (#…), "relative" (Pfad im Notizordner) oder "blocked"."""
    url = url.strip()
    if not url:
        return "blocked", ""
    if url.startswith("#"):
        return "anchor", url[1:]
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in SAFE_SCHEMES:
        return "external", url
    if scheme:
        return "blocked", url          # javascript:, data:, file:, vbscript:, C: …
    if url.startswith(("/", "\\")) or "\\" in url:
        return "blocked", url          # absolute Pfade / Windows-Pfade nicht aus der Vorschau öffnen
    return "relative", url


def resolve_relative(base_dir: str, target: str) -> str | None:
    """Relativen Pfad gegen den Ordner der Datei auflösen; None, wenn er den Notizordner verlässt."""
    path = PurePosixPath(base_dir) / unquote(target) if base_dir else PurePosixPath(unquote(target))
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def toggle_task_line(text: str, line_no: int) -> str | None:
    """Kästchen in Zeile `line_no` (0-basiert) umschalten; None, wenn dort keine Aufgabe steht."""
    lines = text.split("\n")
    if not 0 <= line_no < len(lines):
        return None
    m = LINE_TASK_RE.match(lines[line_no])
    if m is None:
        return None
    new_state = " " if m.group(2) in ("x", "X") else "x"
    lines[line_no] = f"{m.group(1)}[{new_state}]{m.group(3)}"
    return "\n".join(lines)


# ---- Renderer -----------------------------------------------------------------------------------

def _parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    return md


_MD = _parser()


class _Renderer:
    def __init__(self, options: RenderOptions) -> None:
        self.o = options
        self.c = options.colors
        self.result = RenderResult(html="")
        self._links: list[bool] = []

    # -- Hilfen --
    def color(self, key: str, fallback: str = "") -> str:
        return self.c.get(key, fallback)

    def attr(self, token: Token, name: str) -> str:
        value = token.attrGet(name)
        return value if isinstance(value, str) else ""

    def link_href(self, url: str) -> str | None:
        kind, value = classify_url(url)
        if kind == "external":
            return html.escape(value, quote=True)
        if kind == "anchor":
            return "#" + html.escape(slugify(value), quote=True)
        if kind == "relative":
            target, _, fragment = value.partition("#")
            rel = resolve_relative(self.o.base_dir, target)
            if rel is None:
                return None
            return "notex-open:" + html.escape(rel + ("#" + fragment if fragment else ""), quote=True)
        return None

    # -- Inline --
    def render_inline(self, tokens: list[Token]) -> str:
        out: list[str] = []
        for token in tokens:
            t = token.type
            if t == "text":
                out.append(self.text_with_wikilinks(token.content))
            elif t == "softbreak":
                out.append("\n")
            elif t == "hardbreak":
                out.append("<br>")
            elif t == "code_inline":
                out.append(f'<code style="background-color:{self.color("code_bg")}">{html.escape(token.content)}</code>')
            elif t == "strong_open":
                out.append("<b>")
            elif t == "strong_close":
                out.append("</b>")
            elif t == "em_open":
                out.append("<i>")
            elif t == "em_close":
                out.append("</i>")
            elif t == "s_open":
                out.append("<s>")
            elif t == "s_close":
                out.append("</s>")
            elif t == "link_open":
                href = self.link_href(self.attr(token, "href"))
                title = self.attr(token, "title")
                if href is None:   # gesperrtes Ziel: nur der Text bleibt, dezent markiert
                    self._links.append(False)
                    out.append(f'<span style="color:{self.color("danger")}" title="Link gesperrt">')
                else:
                    self._links.append(True)
                    title_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
                    out.append(f'<a href="{href}"{title_attr} style="color:{self.color("accent")}">')
            elif t == "link_close":
                out.append("</a>" if (self._links.pop() if self._links else True) else "</span>")
            elif t == "image":
                out.append(self.render_image(token))
            elif t == "notex_checkbox":
                out.append(self.render_checkbox(token))
            elif t == "html_inline":
                out.append(html.escape(token.content))   # kommt bei html=False nicht vor – sicherheitshalber
            else:
                out.append(html.escape(token.content))
        return "".join(out)

    def text_with_wikilinks(self, text: str) -> str:
        parts: list[str] = []
        last = 0
        for m in WIKI_RE.finditer(text):
            parts.append(html.escape(text[last:m.start()]))
            target, heading, display = m.group(1), m.group(2), m.group(3)
            label = html.escape((display or target).strip())
            href = "notex-open:" + html.escape(target.strip() + ("#" + heading.strip() if heading else ""), quote=True)
            parts.append(f'<a href="{href}" style="color:{self.color("accent")}">{label}</a>')
            last = m.end()
        parts.append(html.escape(text[last:]))
        return "".join(parts)

    def render_image(self, token: Token) -> str:
        src = self.attr(token, "src")
        alt = html.escape(token.content or self.attr(token, "alt"))
        kind, value = classify_url(src)
        if kind == "external":
            if value in self.o.loaded_images:
                return f'<img src="{html.escape(value, quote=True)}" alt="{alt}">'
            self.result.external_images.append(value)
            label = alt or value
            return (f'<span style="color:{self.color("muted")}">[Bild: {label}] </span>'
                    f'<a href="notex-load:{html.escape(value, quote=True)}" style="color:{self.color("accent")}">Bild laden</a>')
        if kind == "relative":
            rel = resolve_relative(self.o.base_dir, value)
            if rel is not None and rel.lower().endswith(IMAGE_SUFFIXES):
                return f'<img src="notex-file:{html.escape(rel, quote=True)}" alt="{alt}">'
        return f'<span style="color:{self.color("muted")}">[Bild nicht verfügbar: {alt or html.escape(src)}]</span>'

    def render_checkbox(self, token: Token) -> str:
        line = token.meta["line"]
        checked = token.meta["checked"]
        glyph = "☑" if checked else "☐"
        return f'<a href="notex-toggle:{line}" style="color:{self.color("accent")};text-decoration:none">{glyph}</a> '

    # -- Blöcke --
    def render_mermaid(self, source: str) -> str:
        import hashlib
        from notex.core import mermaid
        diagram, error = mermaid.render_safe(source, self.o.colors)
        key = hashlib.sha1((source + repr(sorted(self.o.colors.items()))).encode("utf-8")).hexdigest()[:16]
        self.result.diagrams[key] = diagram
        width, height = diagram.width, diagram.height
        if self.o.max_diagram_width and width > self.o.max_diagram_width:
            height = height * self.o.max_diagram_width / width
            width = self.o.max_diagram_width
        alt = html.escape(diagram.title or "Mermaid-Diagramm", quote=True)
        out = (f'<p align="center"><img src="notex-mermaid:{key}" width="{round(width)}" height="{round(height)}" '
               f'alt="{alt}"></p>\n')
        if error:                                       # Code darunter zeigen, damit man den Fehler findet
            out += f'<pre style="background-color:{self.color("code_bg")}">{html.escape(source.rstrip())}</pre>\n'
        return out

    def render_fence(self, token: Token) -> str:
        info = (token.info or "").strip().split()[:1]
        if info and info[0].lower() == "mermaid" and self.o.diagrams:
            return self.render_mermaid(token.content)
        lexer = _fence_lexer(info[0].lower() if info else "")
        lines_html: list[str] = []
        state = syntax.STATE_NONE
        for line in token.content.rstrip("\n").split("\n"):
            spans, state = syntax.lex_line(line, lexer, state) if lexer else ([], state)
            lines_html.append(self.colorize(line, spans))
        body = "\n".join(lines_html)
        return (f'<pre style="background-color:{self.color("code_bg")}">'
                f"{body}</pre>\n")

    def colorize(self, line: str, spans) -> str:
        if not spans:
            return html.escape(line)
        out: list[str] = []
        pos = 0
        for span in spans:
            if span.start > pos:
                out.append(html.escape(line[pos:span.start]))
            color = self.color(span.style)
            piece = html.escape(line[span.start:span.end])
            out.append(f'<span style="color:{color}">{piece}</span>' if color else piece)
            pos = span.end
        out.append(html.escape(line[pos:]))
        return "".join(out)

    def render(self, tokens: list[Token]) -> str:
        out: list[str] = []
        list_stack: list[str] = []
        for token in tokens:
            t = token.type
            if t == "inline":
                out.append(self.render_inline(token.children or []))
            elif t == "paragraph_open":
                out.append("<p>")
            elif t == "paragraph_close":
                out.append("</p>\n")
            elif t == "heading_open":
                level = token.tag
                slug = slugify(token.meta.get("text", ""))
                out.append(f'<a name="{html.escape(slug, quote=True)}"></a><{level}>')
            elif t == "heading_close":
                out.append(f"</{token.tag}>\n")
            elif t == "bullet_list_open":
                list_stack.append("ul")
                out.append("<ul>")
            elif t == "ordered_list_open":
                list_stack.append("ol")
                start = self.attr(token, "start")
                out.append(f'<ol start="{html.escape(start, quote=True)}">' if start else "<ol>")
            elif t in ("bullet_list_close", "ordered_list_close"):
                out.append(f"</{list_stack.pop() if list_stack else 'ul'}>\n")
            elif t == "list_item_open":
                out.append("<li>")
            elif t == "list_item_close":
                out.append("</li>\n")
            elif t == "blockquote_open":
                out.append(f'<blockquote style="color:{self.color("muted")}">')
            elif t == "blockquote_close":
                out.append("</blockquote>\n")
            elif t == "hr":
                out.append("<hr>\n")
            elif t == "fence":
                out.append(self.render_fence(token))
            elif t == "code_block":
                out.append(f'<pre style="background-color:{self.color("code_bg")}">{html.escape(token.content.rstrip(chr(10)))}</pre>\n')
            elif t == "table_open":
                out.append(f'<table border="1" cellspacing="0" cellpadding="6" bordercolor="{self.color("border")}">')
            elif t == "table_close":
                out.append("</table>\n")
            elif t in ("thead_open", "tbody_open", "tr_open"):
                out.append(f"<{token.tag}>")
            elif t in ("thead_close", "tbody_close", "tr_close"):
                out.append(f"</{token.tag}>")
            elif t == "th_open":
                align = self.attr(token, "style").replace("text-align:", "")
                out.append(f'<th align="{align}" bgcolor="{self.color("code_bg")}">' if align else f'<th bgcolor="{self.color("code_bg")}">')
            elif t == "td_open":
                align = self.attr(token, "style").replace("text-align:", "")
                out.append(f'<td align="{align}">' if align else "<td>")
            elif t in ("th_close", "td_close"):
                out.append(f"</{token.tag}>")
            elif t == "html_block":
                out.append(f"<p>{html.escape(token.content)}</p>\n")
            else:
                if token.content:
                    out.append(html.escape(token.content))
        return "".join(out)


def _fence_lexer(lang: str) -> str | None:
    aliases = {"py": "python", "js": "javascript", "sh": "bash", "shell": "bash", "zsh": "bash", "yml": "yaml",
               "ps1": "powershell", "ps": "powershell", "cmd": "batch", "bat": "batch", "htm": "html"}
    lang = aliases.get(lang, lang)
    if not lang:
        return None
    return lang if lang in syntax.FENCE_LANGS else None


def _mark_tasks(tokens: list[Token], result: RenderResult) -> None:
    """- [ ] Aufgabe → eigenes Token `notex_checkbox` vor dem Text; Zeile aus dem Source-Mapping."""
    for i, token in enumerate(tokens):
        if token.type != "list_item_open" or token.map is None:
            continue
        # erstes inline-Token im Listenpunkt (paragraph_open, inline)
        for j in range(i + 1, min(i + 4, len(tokens))):
            inline = tokens[j]
            if inline.type == "list_item_close":
                break
            if inline.type != "inline" or not inline.children:
                continue
            first = inline.children[0]
            if first.type != "text":
                break
            m = TASK_RE.match(first.content)
            if m is None:
                break
            first.content = first.content[m.end():]
            box = Token("notex_checkbox", "", 0)
            box.meta = {"line": token.map[0], "checked": m.group(1) in ("x", "X")}
            inline.children.insert(0, box)
            result.task_lines.append(token.map[0])
            break


def _mark_headings(tokens: list[Token]) -> None:
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and i + 1 < len(tokens) and tokens[i + 1].type == "inline":
            token.meta["text"] = tokens[i + 1].content


def render(text: str, options: RenderOptions | None = None) -> RenderResult:
    """Markdown-Text als HTML-Body für QTextBrowser."""
    options = options or RenderOptions()
    truncated = False
    if len(text) > options.max_source_chars:
        text = text[: options.max_source_chars]
        truncated = True
    tokens = _MD.parse(text)
    renderer = _Renderer(options)
    _mark_tasks(tokens, renderer.result)
    _mark_headings(tokens)
    body = renderer.render(tokens)
    if truncated:
        body += f'<p style="color:{options.colors.get("muted", "")}">… Vorschau gekürzt (Datei zu groß)</p>'
    renderer.result.html = body
    renderer.result.truncated = truncated
    return renderer.result


def stylesheet(colors: dict[str, str], font_family: str, font_size: int, code_family: str) -> str:
    """CSS für QTextDocument (unterstützt nur eine Teilmenge von CSS – deshalb schlicht)."""
    family = f'"{font_family}"' if font_family else "sans-serif"
    return f"""
        body {{ color: {colors.get('text', '#1a1a1a')}; font-family: {family}; font-size: {font_size}px; }}
        p, li {{ line-height: 150%; margin-top: 0; margin-bottom: {max(4, font_size // 2)}px; }}
        h1 {{ font-size: {round(font_size * 1.8)}px; font-weight: 600; margin-top: {font_size}px; margin-bottom: {font_size // 2}px; }}
        h2 {{ font-size: {round(font_size * 1.45)}px; font-weight: 600; margin-top: {font_size}px; margin-bottom: {font_size // 2}px; }}
        h3 {{ font-size: {round(font_size * 1.2)}px; font-weight: 600; margin-top: {font_size}px; margin-bottom: {font_size // 3}px; }}
        h4, h5, h6 {{ font-size: {font_size}px; font-weight: 600; margin-top: {font_size // 2}px; }}
        a {{ color: {colors.get('accent', '#5f7aa0')}; text-decoration: none; }}
        code {{ font-family: "{code_family}"; font-size: {max(8, font_size - 1)}px; }}
        pre {{ font-family: "{code_family}"; font-size: {max(8, font_size - 1)}px; margin: {font_size // 2}px 0; padding: 8px; }}
        blockquote {{ margin-left: {font_size}px; padding-left: 8px; }}
        th {{ font-weight: 600; }}
        hr {{ color: {colors.get('border', '#cccccc')}; }}
    """
