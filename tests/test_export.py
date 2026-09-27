"""Tests für den HTML-Aufbau des Exports (core/export.py) – ohne Qt."""
from __future__ import annotations

from notex.core import export


def test_kind_for():
    assert export.kind_for("notiz.md") == "markdown"
    assert export.kind_for("daten.csv") == "csv"
    assert export.kind_for("liste.tsv") == "csv"
    assert export.kind_for("log.txt") == "text"
    assert export.kind_for("ohne") == "text"


def test_body_markdown_renders_heading():
    html = export.body_html("# Titel\n\nText **fett**", "markdown")
    assert "<h1" in html
    assert "Titel" in html


def test_body_text_is_escaped_pre():
    html = export.body_html("a < b & c", "text")
    assert html.startswith("<pre>")
    assert "&lt;" in html and "&amp;" in html


def test_body_csv_table():
    html = export.body_html("Name,Wert\nA,1\nB,2\n", "csv", name="d.csv")
    assert "<table>" in html
    assert "<th>Name</th>" in html
    assert "<td>A</td>" in html and "<td>2</td>" in html


def test_variables_resolved_before_render():
    html = export.body_html("Hallo §name", "text", values={"name": "Welt"}, prefix="§")
    assert "Welt" in html
    assert "§name" not in html


def test_variables_untouched_without_values():
    html = export.body_html("Hallo §name", "text")
    assert "§name" in html


def test_full_document_has_header_footer_and_title():
    meta = export.ExportMeta(title="Mein Bericht", author="Alice", footer="Notex")
    doc = export.to_html_document("# Hi", "markdown", meta)
    assert "<!DOCTYPE html>" in doc
    assert "<title>Mein Bericht</title>" in doc
    assert "Mein Bericht" in doc and "Alice" in doc
    assert "class=\"doc\"" in doc            # Kopf/Fuß
    assert "Notex" in doc


def test_full_document_title_escaped():
    meta = export.ExportMeta(title="A <b> & C")
    doc = export.to_html_document("x", "text", meta)
    assert "<title>A &lt;b&gt; &amp; C</title>" in doc


def test_logo_data_uri_embedded():
    meta = export.ExportMeta(title="T", logo_data_uri="data:image/png;base64,AAAA")
    doc = export.to_html_document("x", "text", meta)
    assert 'src="data:image/png;base64,AAAA"' in doc


def test_date_defaults_to_today():
    from datetime import date
    meta = export.ExportMeta(title="T")
    assert meta.date_or_today() == date.today().isoformat()
