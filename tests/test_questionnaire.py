"""Tests für die Fragebogen-Engine (core/questionnaire.py) – ohne Qt."""
from __future__ import annotations

from notex.core import questionnaire as qn

SPEC = {
    "id": "check",
    "title": "Sicherheits-Check",
    "sections": [
        {"id": "backup", "title": "Backup", "questions": [
            {"id": "hat_backup", "type": "yesno", "label": "Gibt es Backups?", "required": True, "weight": 2},
            {"id": "getestet", "type": "yesno", "label": "Wiederherstellung getestet?",
             "when": {"question": "hat_backup", "equals": "Ja"}},
        ]},
        {"id": "konten", "title": "Konten", "questions": [
            {"id": "mfa", "type": "choice", "label": "MFA aktiv?",
             "options": [{"value": "überall", "score": 2}, {"value": "teilweise", "score": 1},
                         {"value": "nein", "score": 0}]},
            {"id": "notiz", "type": "text", "label": "Notiz"},
        ]},
    ],
}


def test_from_dict_structure():
    q = qn.from_dict(SPEC)
    assert q.id == "check" and len(q.sections) == 2
    assert q.question("mfa").options[0] == ("überall", 2.0)
    # yesno bekommt Standardoptionen mit Scores
    assert ("Teilweise", 1) in [(v, int(s)) for v, s in q.question("hat_backup").options]


def test_visibility_condition():
    q = qn.from_dict(SPEC)
    getestet = q.question("getestet")
    assert qn.is_visible(getestet, {"hat_backup": "Ja"}) is True
    assert qn.is_visible(getestet, {"hat_backup": "Nein"}) is False
    assert qn.is_visible(getestet, {}) is False


def test_missing_required():
    q = qn.from_dict(SPEC)
    missing = qn.missing_required(q, {})
    assert ("hat_backup", "Gibt es Backups?") in missing
    assert qn.missing_required(q, {"hat_backup": "Ja"}) == []  # getestet nicht required


def test_score_and_level():
    q = qn.from_dict(SPEC)
    # bestmögliche Antworten
    s = qn.score(q, {"hat_backup": "Ja", "getestet": "Ja", "mfa": "überall"})
    assert s.maximum > 0 and s.got == s.maximum
    assert s.level == "gut"
    # schlechte Antworten
    s2 = qn.score(q, {"hat_backup": "Nein", "mfa": "nein"})
    assert s2.got == 0
    assert s2.level == "kritisch"
    # gewichtete Frage zählt doppelt (weight=2, max score 2 → 4)
    per_section = {sec.title: sec for sec in s.sections}
    assert per_section["Backup"].maximum >= 4


def test_render_default_and_frontmatter():
    q = qn.from_dict(SPEC)
    answers = {"hat_backup": "Ja", "getestet": "Nein", "mfa": "teilweise", "notiz": "ok"}
    md = qn.render_markdown(q, answers)
    assert md.startswith("---\nnotex: fragebogen")
    assert "Sicherheits-Check" in md
    assert "**Gibt es Backups?:** Ja" in md
    # unsichtbare Frage (getestet sichtbar, weil hat_backup=Ja)
    assert "Wiederherstellung getestet?" in md
    # Antworten wieder auslesbar
    assert qn.parse_answers(md)["mfa"] == "teilweise"


def test_render_template_and_variables():
    spec = {"id": "x", "title": "T", "output": "# {{name}}\n\nBetrag: {{betrag}} für §kunde\n",
            "sections": [{"id": "s", "questions": [
                {"id": "name", "type": "text", "label": "Name"},
                {"id": "betrag", "type": "number", "label": "Betrag"}]}]}
    q = qn.from_dict(spec)
    md = qn.render_markdown(q, {"name": "Max", "betrag": "100"}, variables={"kunde": "ACME"})
    assert "# Max" in md and "Betrag: 100" in md
    assert "ACME" in md and "§kunde" not in md


def test_table_answer():
    q = qn.from_dict({"id": "t", "sections": [{"id": "s", "questions": [
        {"id": "tage", "type": "table", "label": "Tage", "columns": ["Tag", "Stunden"]}]}]})
    answers = {"tage": [{"Tag": "Mo", "Stunden": "8"}, {"Tag": "Di", "Stunden": "6"}]}
    md = qn.render_markdown(q, answers)
    assert "| Tag | Stunden |" in md and "| Mo | 8 |" in md


def test_score_summary_and_intro():
    q = qn.from_dict(SPEC)
    result = qn.score(q, {"hat_backup": "Ja", "getestet": "Ja", "mfa": "überall"})
    summary = qn.score_summary(result)
    assert "Auswertung" in summary and "Gesamt" in summary
    assert "Backup" in summary
    md = qn.render_markdown(q, {"hat_backup": "Ja"}, intro="## Auswertung\n\nX\n")
    # intro steht nach dem Frontmatter, Antworten bleiben lesbar
    assert md.startswith("---\nnotex: fragebogen")
    assert "## Auswertung" in md
    assert qn.parse_answers(md) == {"hat_backup": "Ja"}


def test_builtin_questionnaires_load():
    from notex.core import questionnaires_builtin as b
    for name, text in b.BUILTIN.items():
        q = qn.load_yaml(text)
        assert q.sections and q.all_questions()
        # rendert ohne Fehler
        qn.render_markdown(q, {})


def test_multichoice_in_condition():
    q = qn.from_dict({"id": "m", "sections": [{"id": "s", "questions": [
        {"id": "dienste", "type": "multichoice", "label": "Dienste", "options": ["web", "mail"]},
        {"id": "web_frage", "type": "text", "label": "Webserver?",
         "when": {"question": "dienste", "in": ["web"]}}]}]})
    assert qn.is_visible(q.question("web_frage"), {"dienste": ["web", "mail"]}) is True
    assert qn.is_visible(q.question("web_frage"), {"dienste": ["mail"]}) is False
