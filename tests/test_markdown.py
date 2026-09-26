from notex.core.markdown import (RenderOptions, classify_url, render, resolve_relative, slugify, stylesheet,
                                 toggle_task_line)

COLORS = {"text": "#111", "muted": "#888", "accent": "#357", "code_bg": "#eee", "border": "#ccc", "danger": "#a00",
          "keyword": "#00f", "string": "#080"}


def test_basic_blocks_and_inline() -> None:
    out = render("# Titel\n\nEin **fetter** und *kursiver* Text mit `code`.\n\n- eins\n- zwei\n\n1. a\n2. b\n\n> Zitat\n\n---\n").html
    assert '<a name="titel"></a><h1>Titel</h1>' in out
    assert "<b>fetter</b>" in out and "<i>kursiver</i>" in out and "<code" in out
    assert "<ul><li><p>eins</p>" in out or "<ul><li>eins" in out
    assert "<ol>" in out and "<blockquote" in out and "<hr>" in out


def test_raw_html_is_escaped_never_passed_through() -> None:
    out = render('<script>alert(1)</script>\n\nText <b onclick="x">bold</b> <img src="http://evil/x.png">\n').html
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "onclick" not in out or "&lt;b onclick" in out
    assert '<img src="http://evil' not in out


def test_link_schemes() -> None:
    assert classify_url("https://example.org/x")[0] == "external"
    assert classify_url("mailto:a@b.de")[0] == "external"
    assert classify_url("#Kapitel Eins") == ("anchor", "Kapitel Eins")
    assert classify_url("notizen/plan.md")[0] == "relative"
    for bad in ("javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "file:///etc/passwd",
                "vbscript:x", "/etc/passwd", "C:\\Windows\\x.txt", ""):
        assert classify_url(bad)[0] == "blocked", bad


def test_links_rendered_or_blocked() -> None:
    out = render("[ok](https://example.org) [bad](javascript:alert(1)) [ftp](ftp://x/y) [abs](/etc/passwd) "
                 "[note](plan.md#Ziele) [top](#Kapitel-Eins)",
                 RenderOptions(colors=COLORS, base_dir="ordner")).html
    assert '<a href="https://example.org"' in out
    # markdown-it selbst lässt javascript: gar nicht als Link durch – es bleibt reiner Text ohne href
    assert 'href="javascript' not in out and "[bad](javascript:alert(1))" in out
    assert '<span style="color:#a00" title="Link gesperrt">ftp</span>' in out and 'href="ftp' not in out
    assert '<span style="color:#a00" title="Link gesperrt">abs</span>' in out and "passwd" not in out.split("abs</span>")[0][-40:]
    assert '<a href="notex-open:ordner/plan.md#Ziele"' in out
    assert '<a href="#kapitel-eins"' in out


def test_relative_paths_stay_inside_root() -> None:
    assert resolve_relative("a/b", "../c.md") == "a/c.md"
    assert resolve_relative("", "./x.md") == "x.md"
    assert resolve_relative("a", "../../etc/passwd") is None
    out = render("[weg](../../x.md)", RenderOptions(colors=COLORS, base_dir="a")).html
    assert "notex-open:" not in out and "Link gesperrt" in out


def test_wiki_links_become_internal_links() -> None:
    out = render("Siehe [[Plan]] und [[ordner/notiz#Ziele|die Ziele]], aber nicht `[[code]]`.", RenderOptions(colors=COLORS)).html
    assert '<a href="notex-open:Plan"' in out
    assert '<a href="notex-open:ordner/notiz#Ziele" style="color:#357">die Ziele</a>' in out
    assert "notex-open:code" not in out and "[[code]]" in out


def test_external_images_are_placeholders_until_loaded() -> None:
    text = "![Logo](https://example.org/logo.png)\n\n![lokal](bilder/x.png)\n\n![raus](../x.png)\n\n![blocked](data:image/png;base64,AAAA)"
    result = render(text, RenderOptions(colors=COLORS, base_dir="notes"))
    assert result.external_images == ["https://example.org/logo.png"]
    assert '<a href="notex-load:https://example.org/logo.png"' in result.html and "<img" in result.html
    assert '<img src="notex-file:notes/bilder/x.png"' in result.html
    assert "Bild nicht verfügbar" in result.html and "data:image" not in result.html
    loaded = render(text, RenderOptions(colors=COLORS, base_dir="notes", loaded_images={"https://example.org/logo.png"}))
    assert '<img src="https://example.org/logo.png"' in loaded.html and "notex-load:" not in loaded.html


def test_tasks_get_toggle_links_with_source_lines() -> None:
    text = "Intro\n\n- [ ] offen\n- [x] erledigt\n  - [ ] unter\n- normal"
    result = render(text, RenderOptions(colors=COLORS))
    assert result.task_lines == [2, 3, 4]
    assert '<a href="notex-toggle:2"' in result.html and "☐" in result.html and "☑" in result.html
    assert "[ ] offen" not in result.html and "offen" in result.html
    assert toggle_task_line(text, 2).split("\n")[2] == "- [x] offen"
    assert toggle_task_line(text, 3).split("\n")[3] == "- [ ] erledigt"
    assert toggle_task_line(text, 4).split("\n")[4] == "  - [x] unter"
    assert toggle_task_line(text, 5) is None and toggle_task_line(text, 99) is None
    assert toggle_task_line("1. [ ] nummeriert", 0) == "1. [x] nummeriert"


def test_fenced_code_is_colored_with_syntax_classes() -> None:
    out = render("```python\ndef f():\n    return 'x'\n```\n\n```\nplain <b>\n```", RenderOptions(colors=COLORS)).html
    assert '<span style="color:#00f">def</span>' in out
    assert "&lt;b&gt;" in out and "<pre" in out


def test_tables_and_strikethrough() -> None:
    out = render("| a | b |\n|---|:-:|\n| 1 | 2 |\n\n~~weg~~", RenderOptions(colors=COLORS)).html
    assert '<table border="1"' in out and "<th" in out and '<td align="center">2</td>' in out
    assert "<s>weg</s>" in out


def test_slugify_and_truncation() -> None:
    assert slugify("Kapitel Eins: Überblick!") == "kapitel-eins-überblick"
    assert slugify("   ") == "abschnitt"
    result = render("x" * 50, RenderOptions(max_source_chars=10))
    assert result.truncated and "gekürzt" in result.html
    css = stylesheet(COLORS, "Inter", 14, "JetBrains Mono")
    assert "font-size: 14px" in css and "JetBrains Mono" in css
