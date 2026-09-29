"""R4a: Vorlagen-Auswahl mit Abschnitten und Suche; Fragebögen (Berichtsheft) stehen mit in der Liste."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from notex.core import template_catalog as tc  # noqa: E402
from uihelp import visible_windows  # noqa: E402


@pytest.fixture
def entries(win):
    win.questionnaires_folder()
    return tc.scan(win.templates_folder())


def test_picker_sections_and_search(win, entries):
    from notex.ui.template_picker import TemplatePickerDialog
    dialog = TemplatePickerDialog(win, entries)
    sections = dialog.section_titles()
    assert sections[:4] == ["Ausbildung", "Kunde/Einsatz", "E-Mail", "Tabellen"]
    assert len(dialog.visible_entries()) == len(entries)
    dialog.search.setText("berichtsheft")
    assert [e.key for e in dialog.visible_entries()] == ["fragebogen/berichtsheft.yaml"]
    assert dialog.section_titles() == ["Ausbildung"]
    dialog.search.setText("tabellen")                                  # Suche nach Kategorie
    assert dialog.visible_entries() and all(e.category == "Tabellen" for e in dialog.visible_entries())
    dialog.search.setText("gibtsnicht")
    assert dialog.visible_entries() == [] and not dialog.ok_button.isEnabled()
    dialog.search.setText("termin best")
    dialog.search.returnPressed.emit()                                 # Enter nimmt den ersten Treffer
    assert dialog.chosen is not None and dialog.chosen.key == "E-Mail-Terminbestätigung.md"


def test_new_from_template_creates_file(win, monkeypatch, entries):
    from notex.ui import dialogs, template_picker
    chosen = next(e for e in entries if e.key == "Besprechung.md")
    monkeypatch.setattr(template_picker, "choose_template", lambda *a, **k: chosen)
    monkeypatch.setattr(dialogs, "ask_text", lambda *a, **k: "Team-Runde.md")
    win.new_from_template()
    QApplication.processEvents()
    created = win.root / "Team-Runde.md"
    assert created.exists() and win._current_file() == created


def test_new_from_template_questionnaire_starts_assistant(win, monkeypatch, entries):
    from notex.ui import template_picker
    chosen = next(e for e in entries if e.key == "fragebogen/berichtsheft.yaml")
    monkeypatch.setattr(template_picker, "choose_template", lambda *a, **k: chosen)
    before = visible_windows()
    win.new_from_template()
    QApplication.processEvents()
    assert any("Ausbildungsnachweis" in w.windowTitle() for w in visible_windows() - before)


def test_palette_lists_templates_with_category(win):
    (win.templates_folder() / "Kunde X").mkdir()
    (win.templates_folder() / "Kunde X" / "Protokoll.md").write_text("# {{date}}\n", encoding="utf-8")
    win._refresh_template_commands()
    titles = {c.title for c in win.registry.all() if c.id.startswith("template:")}
    assert "Vorlage: E-Mail › Terminbestätigung" in titles
    assert "Vorlage: Kunde X › Protokoll" in titles
