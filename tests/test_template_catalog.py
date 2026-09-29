"""R4a: Vorlagen nach Kategorien – alphabetisch, durchsuchbar, keine Vorlage geht verloren, nichts wird verschoben."""
from pathlib import Path

from notex.core import template_catalog as tc
from notex.core.questionnaires_builtin import BUILTIN
from notex.core.templates import DEFAULT_TEMPLATES, ensure_defaults


def _setup(tmp_path: Path) -> Path:
    folder = tmp_path / "templates"
    ensure_defaults(folder, [])
    q = folder / "fragebogen"
    q.mkdir()
    for name, text in BUILTIN.items():
        (q / name).write_text(text, encoding="utf-8")
    return folder


def test_every_template_and_questionnaire_is_listed(tmp_path):
    folder = _setup(tmp_path)
    before = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    entries = tc.scan(folder)
    keys = {e.key for e in entries}
    assert set(DEFAULT_TEMPLATES) <= keys
    assert {f"fragebogen/{n}" for n in BUILTIN} <= keys
    assert len(entries) == len(keys) == len(DEFAULT_TEMPLATES) + len(BUILTIN)
    after = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert before == after                                             # nichts verschoben/umbenannt


def test_categories_of_builtins(tmp_path):
    by_key = {e.key: e for e in tc.scan(_setup(tmp_path))}
    assert by_key["fragebogen/berichtsheft.yaml"].category == "Ausbildung"
    assert by_key["fragebogen/berichtsheft.yaml"].title == "Ausbildungsnachweis (Woche)"
    assert by_key["fragebogen/berichtsheft.yaml"].kind == "questionnaire"
    assert by_key["fragebogen/systemcheck.yaml"].category == "Kunde/Einsatz"
    assert by_key["E-Mail-Terminbestätigung.md"].category == "E-Mail"
    assert by_key["E-Mail-Terminbestätigung.md"].title == "Terminbestätigung"
    assert by_key["Tabelle-Patchfeld.csv"].category == "Tabellen"
    assert by_key["Woche.md"].category == "Planung & Notizen"
    assert by_key["Beweismittel.md"].category == "Sicherheit & Forensik"


def test_order_categories_then_alphabetical(tmp_path):
    folder = _setup(tmp_path)
    (folder / "Zettel.md").write_text("x", encoding="utf-8")
    (folder / "Ärger-Liste.md").write_text("x", encoding="utf-8")
    groups = tc.grouped(tc.scan(folder))
    names = [g for g, _ in groups]
    assert names[:4] == ["Ausbildung", "Kunde/Einsatz", "E-Mail", "Tabellen"]
    assert names[-1] == "Sonstiges"
    other = [e.title for e in dict(groups)["Sonstiges"]]
    assert other == ["Ärger-Liste", "Zettel"]                        # Ä wie A einsortiert
    for _cat, items in groups:
        titles = [tc.sort_key(e.title) for e in items]
        assert titles == sorted(titles)


def test_subfolder_is_category_and_known_spelling(tmp_path):
    folder = _setup(tmp_path)
    (folder / "Kunde X").mkdir()
    (folder / "Kunde X" / "Protokoll.md").write_text("x", encoding="utf-8")
    (folder / "e-mail").mkdir()
    (folder / "e-mail" / "Absage.md").write_text("x", encoding="utf-8")
    (folder / "Zettel.md").write_text("x", encoding="utf-8")
    by_key = {e.key: e for e in tc.scan(folder)}
    assert by_key["Kunde X/Protokoll.md"].category == "Kunde X"
    assert by_key["e-mail/Absage.md"].category == "E-Mail"          # gleiche Kategorie wie die mitgelieferten
    names = [g for g, _ in tc.grouped(list(by_key.values()))]
    assert names.index("Kunde X") < names.index("Sonstiges")


def test_questionnaire_declared_category(tmp_path):
    folder = tmp_path / "templates"
    (folder / "fragebogen").mkdir(parents=True)
    (folder / "fragebogen" / "eigen.yaml").write_text("id: x\ntitle: Übergabe\ncategory: kunde/einsatz\n",
                                                      encoding="utf-8")
    [entry] = tc.scan(folder)
    assert (entry.title, entry.category, entry.kind) == ("Übergabe", "Kunde/Einsatz", "questionnaire")


def test_search_name_and_category(tmp_path):
    entries = tc.scan(_setup(tmp_path))
    assert {e.key for e in tc.filter_entries(entries, "bericht")} >= {"fragebogen/berichtsheft.yaml"}
    assert all(e.category == "E-Mail" for e in tc.filter_entries(entries, "e-mail"))
    assert {e.key for e in tc.filter_entries(entries, "ausbildung")} == {"fragebogen/berichtsheft.yaml"}
    assert [e.key for e in tc.filter_entries(entries, "termin bestatigung")] == ["E-Mail-Terminbestätigung.md"]
    assert tc.filter_entries(entries, "gibtsnicht") == []
    assert len(tc.filter_entries(entries, "  ")) == len(entries)


def test_missing_folder_is_empty(tmp_path):
    assert tc.scan(tmp_path / "fehlt") == []
