from datetime import date, datetime
from pathlib import Path

from notex.core.templates import (DEFAULT_TEMPLATES, default_file_name, ensure_defaults, iso_week, list_templates,
                                  monday_of, render, render_name, template_text)

NOW = datetime(2026, 9, 26, 14, 5, 9)   # Samstag, KW 39


def test_basic_placeholders() -> None:
    r = render("{{date}} {{time}} {{weekday}} KW{{week}} {{year}} {{title}}", NOW, title="Notiz")
    assert r.text == "26.09.2026 14:05 Samstag KW39 2026 Notiz" and r.cursor is None


def test_formats_offsets_and_spacing() -> None:
    r = render("{{ date:%Y-%m-%d }} {{time:%H:%M:%S}} {{date+2:%d.%m.}} {{weekday-1}} {{DATE}}", NOW)
    assert r.text == "2026-09-26 14:05:09 28.09. Freitag 26.09.2026"


def test_cursor_is_removed_and_positioned() -> None:
    r = render("# {{title}}\n\n- {{cursor}}\n{{cursor}}", NOW, title="X")
    assert r.text == "# X\n\n- \n" and r.cursor == len("# X\n\n- ")


def test_unknown_placeholders_stay() -> None:
    assert render("{{foo}} {{date", NOW).text == "{{foo}} {{date"


def test_iso_week_year_boundary() -> None:
    # 31.12.2026 ist ein Donnerstag in KW 53/2026; 01.01.2027 gehört noch zu KW 53/2026
    assert iso_week(date(2027, 1, 1)) == (2026, 53)
    assert render("KW{{week}} {{year}}", NOW, base=date(2027, 1, 1)).text == "KW53 2026"
    assert render("{{year}}", NOW, base=date(2027, 1, 1)).text == "2027"          # ohne Woche: Kalenderjahr
    assert render("KW{{week}}", NOW, base=date(2027, 1, 4)).text == "KW01"


def test_week_template_from_monday() -> None:
    monday = monday_of(NOW.date())
    assert monday == date(2026, 9, 21)
    r = render(DEFAULT_TEMPLATES["Woche.md"], NOW, base=monday)
    assert r.text.startswith("# KW 39 · 21.09.2026 – 27.09.2026")
    assert "## Montag 21.09." in r.text and "## Freitag 25.09." in r.text
    assert r.cursor is not None and r.text[r.cursor - 6:r.cursor] == "- [ ] "


def test_render_name_sanitizes() -> None:
    assert render_name("KW{{week}} {{year}}", NOW, base=monday_of(NOW.date())) == "KW39 2026"
    assert render_name('a/b:c*?"', NOW) == "a-b-c---"
    assert render_name("  ..  ", NOW) == "Neu"


def test_default_files_and_listing(tmp_path: Path) -> None:
    folder = tmp_path / "templates"
    created = ensure_defaults(folder)
    assert sorted(p.name for p in created) == sorted(DEFAULT_TEMPLATES)
    (folder / "Eigene.txt").write_text("x", encoding="utf-8")
    (folder / ".versteckt.md").write_text("x", encoding="utf-8")
    (folder / "bild.png").write_bytes(b"x")
    from notex.core.templates import TEMPLATE_SUFFIXES
    expected = sorted([n for n in DEFAULT_TEMPLATES if Path(n).suffix.lower() in TEMPLATE_SUFFIXES] + ["Eigene.txt"])
    assert [p.name for p in list_templates(folder)] == expected
    # versteckte Dateien und Nicht-Vorlagen (z. B. .png) tauchen nicht auf
    assert ".versteckt.md" not in [p.name for p in list_templates(folder)]
    assert "bild.png" not in [p.name for p in list_templates(folder)]
    # zweiter Aufruf legt nichts neu an, auch nicht, wenn der Nutzer Vorlagen gelöscht hat
    (folder / "Woche.md").unlink()
    assert ensure_defaults(folder) == [] and not (folder / "Woche.md").exists()
    assert template_text(folder, "Woche.md") == DEFAULT_TEMPLATES["Woche.md"]     # eingebauter Ersatz
    assert template_text(folder, "Eigene.txt") == "x"
    assert list_templates(tmp_path / "gibt-es-nicht") == []


def test_default_file_name() -> None:
    assert default_file_name("Tagesnotiz.md", NOW) == "2026-09-26 Tagesnotiz.md"
    assert default_file_name("Liste.txt", NOW) == "2026-09-26 Liste.txt"


def test_later_templates_arrive_once(tmp_path: Path) -> None:
    from notex.core.templates import LATER_TEMPLATES
    folder = tmp_path / "templates"
    folder.mkdir()
    (folder / "Woche.md").write_text("eigene", encoding="utf-8")        # alter Ordner aus früherer Version
    installed: list[str] = []
    created = ensure_defaults(folder, installed)
    assert sorted(p.name for p in created) == sorted(LATER_TEMPLATES) and installed == list(LATER_TEMPLATES)
    assert (folder / "Woche.md").read_text(encoding="utf-8") == "eigene"
    (folder / "YARA-Regel.yar").unlink()                                 # vom Nutzer gelöscht → bleibt weg
    assert ensure_defaults(folder, installed) == [] and not (folder / "YARA-Regel.yar").exists()
    fresh: list[str] = []
    ensure_defaults(tmp_path / "neu", fresh)                             # Erststart: alles, Liste gefüllt
    assert fresh == list(LATER_TEMPLATES)
