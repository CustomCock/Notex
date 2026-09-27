"""Export von Notizen nach HTML/PDF – der Qt-freie Teil: aus Inhalt HTML bauen.

`to_html_document` erzeugt ein vollständiges, in sich geschlossenes HTML-Dokument (eigenes CSS, Kopf mit
Titel/Autor/Datum und optionalem Logo, Fußzeile). `body_html` liefert nur den Inhalt – die PDF-Ausgabe rendert
diesen Körper mit Qt und malt Kopf-/Fußzeile je Seite selbst. Variablen (§name) werden vor dem Rendern aufgelöst.

Der Klartext verschlüsselter Notizen (.ntx) darf nur nach ausdrücklicher Bestätigung exportiert werden – das
entscheidet die Oberfläche; hier wird nur Text zu HTML.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path

from notex.core import csvdata, markdown, variables


@dataclass
class ExportMeta:
    title: str
    author: str = ""
    date: str = ""                       # ISO-Datum; leer = heute
    footer: str = "Erstellt mit Notex"
    logo_data_uri: str = ""              # optionales eingebettetes Logo (data:-URI) für die Kopfzeile

    def date_or_today(self) -> str:
        return self.date or date.today().isoformat()


DEFAULT_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; color: #1f2328; line-height: 1.55;
       margin: 0; padding: 0; background: #ffffff; font-size: 12pt; }
.page { max-width: 800px; margin: 0 auto; padding: 24px 32px 40px; }
header.doc { display: flex; align-items: center; gap: 14px; border-bottom: 2px solid #5f6f84;
             padding-bottom: 12px; margin-bottom: 22px; }
header.doc img { width: 40px; height: 40px; }
header.doc .title { font-size: 20pt; font-weight: 700; margin: 0; }
header.doc .meta { color: #5b6470; font-size: 10pt; margin-top: 2px; }
h1, h2, h3, h4 { color: #1a1f24; line-height: 1.25; }
h1 { font-size: 18pt; } h2 { font-size: 15pt; } h3 { font-size: 13pt; }
a { color: #3f5876; }
pre { background: #f4f5f7; border: 1px solid #e0e3e8; border-radius: 6px; padding: 12px;
      white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: 10.5pt; }
code { font-family: 'JetBrains Mono', Consolas, monospace; }
table { border-collapse: collapse; width: 100%; font-size: 10.5pt; }
th, td { border: 1px solid #cfd4da; padding: 5px 9px; text-align: left; vertical-align: top; }
th { background: #eef1f4; font-weight: 700; }
tr:nth-child(even) td { background: #f7f8fa; }
blockquote { border-left: 3px solid #9fb0c4; margin: 0; padding: 2px 14px; color: #4a5360; }
footer.doc { border-top: 1px solid #d8dce1; margin-top: 26px; padding-top: 8px;
             color: #7a828c; font-size: 9pt; }
@page { margin: 18mm 16mm; }
"""


def resolve(text: str, values: dict[str, str] | None, prefix: str = "§") -> str:
    """Variablen im Text durch ihre Werte ersetzen (leer = unverändert)."""
    if not values:
        return text
    return variables.resolve(text, values, prefix)


def _csv_table(text: str, name: str = "") -> str:
    dialect = csvdata.sniff(text, name)
    rows = csvdata.parse(text, dialect)
    if not rows:
        return "<p>(leere Tabelle)</p>"
    out = ["<table>"]
    header, *body = rows
    out.append("<thead><tr>" + "".join(f"<th>{escape(c)}</th>" for c in header) + "</tr></thead>")
    out.append("<tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def body_html(content: str, kind: str, name: str = "", base_dir: str = "",
              values: dict[str, str] | None = None, prefix: str = "§") -> str:
    """Nur der Inhalts-Körper als HTML (für die PDF-Ausgabe mit Qt bzw. zum Einbetten)."""
    content = resolve(content, values, prefix)
    if kind == "markdown":
        return markdown.render(content, markdown.RenderOptions(base_dir=base_dir)).html
    if kind == "csv":
        return _csv_table(content, name)
    # Text und alles andere: unverändert als vorformatierter Block
    return f"<pre>{escape(content)}</pre>"


def kind_for(name: str) -> str:
    """Export-Art aus der Endung: markdown | csv | text."""
    suffix = Path(name).suffix.lower()
    if suffix in (".md", ".markdown"):
        return "markdown"
    if suffix in (".csv", ".tsv"):
        return "csv"
    return "text"


def to_html_document(content: str, kind: str, meta: ExportMeta, name: str = "", base_dir: str = "",
                     values: dict[str, str] | None = None, prefix: str = "§", css: str | None = None) -> str:
    """Vollständiges HTML-Dokument mit Kopf (Logo/Titel/Meta), Inhalt und Fußzeile."""
    body = body_html(content, kind, name=name, base_dir=base_dir, values=values, prefix=prefix)
    logo = f'<img src="{escape(meta.logo_data_uri)}" alt="">' if meta.logo_data_uri else ""
    meta_bits = [meta.date_or_today()]
    if meta.author:
        meta_bits.insert(0, escape(meta.author))
    meta_line = "  ·  ".join(meta_bits)
    style = css if css is not None else DEFAULT_CSS
    return (
        "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{escape(meta.title)}</title>\n<style>{style}</style>\n</head>\n<body>\n"
        "<div class=\"page\">\n"
        f"<header class=\"doc\">{logo}<div><p class=\"title\">{escape(meta.title)}</p>"
        f"<div class=\"meta\">{meta_line}</div></div></header>\n"
        f"<main>\n{body}\n</main>\n"
        f"<footer class=\"doc\">{escape(meta.footer)}</footer>\n"
        "</div>\n</body>\n</html>\n"
    )
