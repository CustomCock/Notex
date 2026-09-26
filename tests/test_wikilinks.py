from notex.core.wikilinks import (LinkIndex, find_heading_line, find_links, headings, link_name, links_in_line,
                                  resolve, rewrite_links, unlinked_mentions)

FILES = ["Projekte/notizen.md", "Projekte/Python/notizen.md", "todo.txt", "Security/osint.md", "a/b/tief.txt"]


def test_find_links_variants_and_positions() -> None:
    text = "Siehe [[notizen]] und [[todo|Aufgaben]] sowie [[osint#Domains|OSINT]].\n`[[nicht]]` im Code"
    links = find_links(text)
    assert [(l.target, l.heading, l.display, l.line, l.start) for l in links] == [
        ("notizen", None, None, 1, 6), ("todo", None, "Aufgaben", 1, 22), ("osint", "Domains", "OSINT", 1, 46)]
    assert links[1].text == "Aufgaben" and links[0].text == "notizen"


def test_links_ignore_code_blocks() -> None:
    text = "```\n[[imcode]]\n```\n[[echt]]\n"
    assert [l.target for l in find_links(text)] == ["echt"]
    assert links_in_line("x [[a]] `[[b]]`") == [links_in_line("x [[a]]")[0]]
    assert links_in_line("[[a]]", in_fence=True) == []


def test_resolve_case_insensitive_shortest_and_explicit() -> None:
    assert resolve("Notizen", FILES) == "Projekte/notizen.md"          # kürzester Pfad gewinnt
    assert resolve("python/notizen", FILES) == "Projekte/Python/notizen.md"
    assert resolve("todo.txt", FILES) == "todo.txt"
    assert resolve("TIEF", FILES) == "a/b/tief.txt"
    assert resolve("gibtsnicht", FILES) is None
    assert link_name("Projekte/Python/notizen.md") == "notizen"


def test_headings_and_mentions() -> None:
    text = "# Titel\n\n## Domains\nText\n```\n# kein heading\n```\n### Ende ###"
    assert headings(text) == [(1, "Titel"), (3, "Domains"), (8, "Ende")]
    assert find_heading_line(text, "domains") == 3 and find_heading_line(text, "x") is None
    mentions = unlinked_mentions("notizen hier, [[notizen]] dort, Notizenbuch nein, `notizen` nein", "notizen")
    assert mentions == [(1, 0, 7)]


def test_rewrite_links_keeps_display_and_heading() -> None:
    text = "a [[notizen|Meine]] b [[Notizen#Kapitel]] c [[todo]] d\n```\n[[notizen]]\n```"
    new_text, count = rewrite_links(text, FILES, "Projekte/notizen.md", "Projekte/ideen.md")
    assert count == 2
    assert new_text.startswith("a [[ideen|Meine]] b [[ideen#Kapitel]] c [[todo]] d")
    assert "```\n[[notizen]]\n```" in new_text           # Codeblock unangetastet
    # Umbenennen auf einen Namen, der woanders schon existiert -> relativer Pfad
    files = FILES + ["Archiv/ideen.md"]
    new_text, _ = rewrite_links("[[notizen]]", files, "Projekte/notizen.md", "Projekte/ideen.md")
    assert new_text == "[[Projekte/ideen]]"


def test_link_index_backlinks_and_rename() -> None:
    index = LinkIndex()
    index.set_files(FILES)
    index.update_file("todo.txt", "siehe [[notizen]] und [[osint]]\nnochmal [[notizen]]")
    index.update_file("Security/osint.md", "[[notizen#Kapitel]] [[fehlt]]")
    assert [(b.source, b.line) for b in index.backlinks("Projekte/notizen.md")] == [
        ("Security/osint.md", 1), ("todo.txt", 1), ("todo.txt", 2)]
    assert index.sources_linking_to("Projekte/notizen.md") == {"Security/osint.md": 1, "todo.txt": 2}
    assert index.unresolved["Security/osint.md"] == ["fehlt"]
    index.rename_file("Projekte/notizen.md", "Projekte/ideen.md")
    assert len(index.backlinks("Projekte/ideen.md")) == 3 and index.backlinks("Projekte/notizen.md") == []
    index.remove_file("todo.txt")
    assert index.backlinks("Projekte/ideen.md") == [index.backlinks("Projekte/ideen.md")[0]]
