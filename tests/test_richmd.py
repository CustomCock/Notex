"""Tests für Markdown ↔ Zwischenmodell (core/richmd.py) – ohne Qt."""
from __future__ import annotations

from notex.core import richmd


def rt(md: str) -> str:
    """Einmal durch parse→to_markdown."""
    return richmd.to_markdown(richmd.parse(md))


def test_headings_and_paragraph():
    out = rt("# Titel\n\nEin Absatz.\n")
    assert out == "# Titel\n\nEin Absatz.\n"


def test_inline_formats():
    out = rt("Text **fett** *kursiv* ~~weg~~ `code`\n")
    assert "**fett**" in out and "*kursiv*" in out and "~~weg~~" in out and "`code`" in out


def test_link():
    out = rt("Siehe [Notex](https://example.com)\n")
    assert "[Notex](https://example.com)" in out


def test_bullet_and_ordered_list():
    out = rt("- a\n- b\n\n1. eins\n2. zwei\n")
    assert "- a" in out and "- b" in out
    assert "1. eins" in out and "1. zwei" in out or "2. zwei" in out


def test_tasks():
    out = rt("- [ ] offen\n- [x] erledigt\n")
    assert "- [ ] offen" in out
    assert "- [x] erledigt" in out


def test_quote_code_hr():
    out = rt("> Zitat\n\n```py\nprint(1)\n```\n\n---\n")
    assert "> Zitat" in out
    assert "```py" in out and "print(1)" in out
    assert "---" in out


def test_table_with_alignment():
    md = "| A | B |\n| :--- | ---: |\n| 1 | 2 |\n"
    out = rt(md)
    assert "| A | B |" in out
    assert ":---" in out and "---:" in out
    assert "| 1 | 2 |" in out


def test_variables_and_placeholders_survive():
    md = "Hallo §name, dein Betrag ist **§betrag** €.\n"
    out = rt(md)
    assert "§name" in out and "§betrag" in out
    assert "**§betrag**" in out


def test_idempotent():
    md = ("# H\n\nText **b** *i*.\n\n- a\n- [ ] t\n\n> q\n\n```\ncode\n```\n\n"
          "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n---\n")
    once = rt(md)
    twice = rt(once)
    assert once == twice           # zweiter Durchlauf ändert nichts mehr


def test_parse_model_shape():
    doc = richmd.parse("# H\n\n- a\n")
    assert doc.blocks[0].type == "heading" and doc.blocks[0].level == 1
    assert doc.blocks[1].type == "li"


def test_bold_italic_combined():
    doc = richmd.parse("***beides***\n")
    md = richmd.to_markdown(doc)
    assert "beides" in md
    # Roundtrip bleibt stabil
    assert richmd.to_markdown(richmd.parse(md)) == md
