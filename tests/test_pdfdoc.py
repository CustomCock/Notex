from notex.core import pdfdoc
from notex.core.pdfdoc import PageLayout, clean_selection, quote_markdown

A4 = (595.0, 842.0)


def test_layout_positions_and_centering() -> None:
    layout = PageLayout([A4, A4, (842.0, 595.0)], scale=1.0, viewport_width=1000)
    first, second, third = layout.pages
    assert first.y == pdfdoc.MARGIN and second.y == first.y + 842 + pdfdoc.PAGE_GAP
    assert first.x == (1000 - 595) / 2 and third.x == (1000 - 842) / 2
    assert layout.height == third.y + 595 + pdfdoc.MARGIN
    narrow = PageLayout([A4], scale=2.0, viewport_width=300)       # breiter als die Ansicht → horizontal scrollen
    assert narrow.width == 595 * 2 + 2 * pdfdoc.MARGIN and narrow.pages[0].x == pdfdoc.MARGIN


def test_page_at_and_visible() -> None:
    layout = PageLayout([A4] * 10, scale=0.5, viewport_width=800)
    step = 842 * 0.5 + pdfdoc.PAGE_GAP
    assert layout.page_at_y(0) == 0 and layout.page_at_y(pdfdoc.MARGIN + step * 3 + 5) == 3
    assert layout.page_at_y(10 ** 9) == 9
    visible = layout.visible(pdfdoc.MARGIN + step * 2, pdfdoc.MARGIN + step * 2 + 500)
    assert [p.index for p in visible] == [2, 3]
    assert PageLayout([], 1.0, 500).page_at_y(100) == 0 and PageLayout([], 1.0, 500).hit(1, 1) is None


def test_hit_and_roundtrip() -> None:
    layout = PageLayout([A4, A4], scale=1.5, viewport_width=1200)
    page = layout.pages[1]
    hit = layout.hit(page.x + 150, page.y + 300)
    assert hit == (1, 100.0, 200.0)
    assert layout.to_view(1, 100, 200) == (page.x + 150, page.y + 300)
    assert layout.hit(1, page.y + 10) is None                          # links neben der Seite
    assert layout.clamp_hit(1, page.x - 50, page.y + 10 ** 6) == (0.0, 842.0)


def test_fit_scales() -> None:
    assert round(pdfdoc.fit_width_scale([A4], 595 + 2 * pdfdoc.MARGIN), 3) == 1.0
    assert pdfdoc.fit_page_scale(A4, 2000, 842 + 2 * pdfdoc.MARGIN) == 1.0
    assert pdfdoc.fit_width_scale([], 10) == pdfdoc.MIN_ZOOM


def test_clean_selection_joins_lines_and_hyphens() -> None:
    raw = "Das ist ein lan-\ngerer Satz über\nzwei Zeilen.\n\nNeuer Absatz mit E-\nMail."
    assert clean_selection(raw) == "Das ist ein langerer Satz über zwei Zeilen.\n\nNeuer Absatz mit E- Mail."
    assert clean_selection("  \n \n") == ""
    assert clean_selection("weich­getrennt") == "weichgetrennt"


def test_quote_markdown() -> None:
    quote = quote_markdown("Erste Zeile\nzweite Zeile\n\nNeuer Absatz", "Bericht *2026*.pdf", "iv")
    assert quote == ("> Erste Zeile zweite Zeile\n>\n> Neuer Absatz\n>\n"
                     "> — *Bericht \\*2026\\*.pdf*, S. iv\n")
    assert quote_markdown("   ", "a.pdf", "1") == ""


def test_snap_to_lines() -> None:
    lines = [(72, 68, 160, 86), (72, 113, 334, 122), (72, 129, 302, 141)]
    assert pdfdoc.snap_to_lines(lines, 80, 76) == (80, 77.0)                 # auf der Zeile: bleibt
    assert pdfdoc.snap_to_lines(lines, 10, 118) == (73, 117.5)               # links daneben → Zeilenanfang
    assert pdfdoc.snap_to_lines(lines, 900, 135) == (303, 135.0)             # rechts daneben → hinter das letzte Zeichen
    assert pdfdoc.snap_to_lines(lines, 100, 100)[1] == 117.5                 # zwischen Zeilen → die nähere
    assert pdfdoc.snap_to_lines([], 1, 1) is None


def test_clean_selection_pdfium_hyphen_marker() -> None:
    assert clean_selection("Die Silben￾\r\ntrennung") == "Die Silbentrennung"
