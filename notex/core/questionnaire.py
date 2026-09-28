"""Fragebogen-Engine – ohne Qt, damit Logik, Bedingungen, Auswertung und Ausgabe testbar sind.

Ein Fragebogen ist YAML (Abschnitte → Fragen). Fragetypen: text, yesno, choice, multichoice, number, date, time,
table. Fragen können Pflicht sein, eine Bedingung haben (nur zeigen, wenn …), eine Gewichtung und Antwort-Punkte
(für die Auswertung, z. B. Sicherheits-Check), Hilfetexte und Vorschlags-Chips.

`render_markdown` erzeugt aus den Antworten (und einer optionalen Ausgabe-Vorlage) formatiertes Markdown; die
Antworten werden zusätzlich strukturiert im Frontmatter abgelegt, damit ein Ergebnis erneut bearbeitbar ist.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

MARKER = "fragebogen"

YESNO_OPTIONS = [("Ja", 2), ("Teilweise", 1), ("Nein", 0), ("Weiß nicht", 0)]


@dataclass
class Question:
    id: str
    type: str = "text"
    label: str = ""
    help: str = ""
    required: bool = False
    weight: float = 1.0
    options: list = field(default_factory=list)     # [(wert, score)] bzw. Spalten bei table
    chips: list = field(default_factory=list)
    columns: list = field(default_factory=list)      # table: Spaltenüberschriften
    when: dict | None = None                         # Bedingung: {"question","equals"/"in"/"not"}


@dataclass
class Section:
    id: str
    title: str = ""
    questions: list = field(default_factory=list)


@dataclass
class Questionnaire:
    id: str
    title: str = ""
    output: str = ""                                 # optionale Ausgabe-Vorlage mit {{fragen-id}}
    sections: list = field(default_factory=list)

    def all_questions(self) -> list:
        return [q for s in self.sections for q in s.questions]

    def question(self, qid: str):
        for q in self.all_questions():
            if q.id == qid:
                return q
        return None


def _options(raw) -> list:
    out = []
    for item in raw or []:
        if isinstance(item, dict):
            out.append((str(item.get("value", item.get("wert", ""))), float(item.get("score", 0))))
        else:
            out.append((str(item), 0.0))
    return out


def from_dict(spec: dict) -> Questionnaire:
    q = Questionnaire(id=str(spec.get("id", "fragebogen")), title=str(spec.get("title", "")),
                      output=str(spec.get("output", "")))
    for sraw in spec.get("sections", []):
        section = Section(id=str(sraw.get("id", "")), title=str(sraw.get("title", "")))
        for qraw in sraw.get("questions", []):
            qtype = str(qraw.get("type", "text"))
            options = _options(qraw.get("options"))
            if qtype == "yesno" and not options:
                options = [(v, s) for v, s in YESNO_OPTIONS]
            section.questions.append(Question(
                id=str(qraw["id"]), type=qtype, label=str(qraw.get("label", "")),
                help=str(qraw.get("help", "")), required=bool(qraw.get("required", False)),
                weight=float(qraw.get("weight", 1.0)), options=options,
                chips=list(qraw.get("chips", [])), columns=list(qraw.get("columns", [])),
                when=qraw.get("when")))
        q.sections.append(section)
    return q


def load_yaml(text: str) -> Questionnaire:
    import yaml
    return from_dict(yaml.safe_load(text) or {})


# ---- Sichtbarkeit / Bedingungen -------------------------------------------------------------------

def is_visible(question: Question, answers: dict) -> bool:
    cond = question.when
    if not cond:
        return True
    other = answers.get(cond.get("question"))
    if "equals" in cond:
        return _eq(other, cond["equals"])
    if "not" in cond:
        return not _eq(other, cond["not"])
    if "in" in cond:
        values = cond["in"] or []
        if isinstance(other, list):
            return any(o in values for o in other)
        return other in values
    return True


def _eq(a, b) -> bool:
    if isinstance(a, list):
        return b in a
    return str(a) == str(b)


def visible_questions(questionnaire: Questionnaire, answers: dict) -> list:
    return [q for q in questionnaire.all_questions() if is_visible(q, answers)]


def missing_required(questionnaire: Questionnaire, answers: dict) -> list:
    """Pflichtfragen, die sichtbar aber unbeantwortet sind → Liste von (id, label)."""
    out = []
    for q in questionnaire.all_questions():
        if q.required and is_visible(q, answers):
            value = answers.get(q.id)
            if value in (None, "", []) or (isinstance(value, list) and not value):
                out.append((q.id, q.label))
    return out


# ---- Auswertung (für Sicherheits-Check u. Ä.) -----------------------------------------------------

@dataclass
class SectionScore:
    title: str
    got: float
    maximum: float

    @property
    def percent(self) -> int:
        return int(round(100 * self.got / self.maximum)) if self.maximum else 0

    @property
    def level(self) -> str:
        p = self.percent
        return "gut" if p >= 80 else "mittel" if p >= 50 else "kritisch"


@dataclass
class Score:
    sections: list
    got: float
    maximum: float

    @property
    def percent(self) -> int:
        return int(round(100 * self.got / self.maximum)) if self.maximum else 0

    @property
    def level(self) -> str:
        p = self.percent
        return "gut" if p >= 80 else "mittel" if p >= 50 else "kritisch"


def _question_score(question: Question, value) -> tuple[float, float] | None:
    """(erreicht, maximal) für eine bewertbare Frage; None, wenn nicht bewertet."""
    scored = [s for _v, s in question.options]
    if not scored or all(s == 0 for s in scored):
        return None
    best = max(scored) * question.weight
    if value is None:
        return 0.0, best
    values = value if isinstance(value, list) else [value]
    got = 0.0
    for v in values:
        for opt_value, opt_score in question.options:
            if str(opt_value) == str(v):
                got = max(got, opt_score)
    return got * question.weight, best


def score(questionnaire: Questionnaire, answers: dict) -> Score:
    sections = []
    total_got = total_max = 0.0
    for section in questionnaire.sections:
        got = maximum = 0.0
        for q in section.questions:
            if not is_visible(q, answers):
                continue
            result = _question_score(q, answers.get(q.id))
            if result is not None:
                got += result[0]
                maximum += result[1]
        if maximum:
            sections.append(SectionScore(section.title, got, maximum))
            total_got += got
            total_max += maximum
    return Score(sections, total_got, total_max)


# ---- Ausgabe --------------------------------------------------------------------------------------

def format_answer(question: Question, value) -> str:
    if value in (None, "", []):
        return "—"
    if question.type == "table" and isinstance(value, list):
        return _table_markdown(question, value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _table_markdown(question: Question, rows: list) -> str:
    cols = question.columns or (list(rows[0].keys()) if rows and isinstance(rows[0], dict) else [])
    if not cols:
        return ""
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in rows:
        if isinstance(row, dict):
            cells = [str(row.get(c, "")) for c in cols]
        else:
            cells = [str(x) for x in row]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines)


def render_markdown(questionnaire: Questionnaire, answers: dict, variables: dict | None = None,
                    prefix: str = "§", intro: str = "") -> str:
    if questionnaire.output.strip():
        body = _fill_template(questionnaire, answers)
    else:
        body = _default_render(questionnaire, answers)
    if variables:
        from notex.core import variables as var
        body = var.resolve(body, variables, prefix)
    return _frontmatter(questionnaire, answers) + (intro + "\n" if intro else "") + body


def _fill_template(questionnaire: Questionnaire, answers: dict) -> str:
    import re
    text = questionnaire.output

    def repl(match):
        qid = match.group(1)
        q = questionnaire.question(qid)
        return format_answer(q, answers.get(qid)) if q else match.group(0)

    return re.sub(r"\{\{\s*([\w.-]+)\s*\}\}", repl, text)


def _default_render(questionnaire: Questionnaire, answers: dict) -> str:
    lines = [f"# {questionnaire.title}", ""]
    for section in questionnaire.sections:
        visible = [q for q in section.questions if is_visible(q, answers)]
        if not visible:
            continue
        if section.title:
            lines += [f"## {section.title}", ""]
        for q in visible:
            answer = format_answer(q, answers.get(q.id))
            if q.type == "table":
                lines += [f"**{q.label}**", "", answer, ""]
            else:
                lines.append(f"- **{q.label}:** {answer}")
        lines.append("")
    return "\n".join(lines)


def _frontmatter(questionnaire: Questionnaire, answers: dict) -> str:
    payload = json.dumps(answers, ensure_ascii=False)
    return (f"---\nnotex: {MARKER}\nfragebogen: {questionnaire.id}\n"
            f"antworten: {payload}\n---\n\n")


_LEVEL_MARK = {"gut": "🟢 gut", "mittel": "🟡 mittel", "kritisch": "🔴 kritisch"}


def score_summary(result: Score) -> str:
    """Markdown-Auswertung (Ampel je Bereich + Gesamt) für bewertete Fragebögen."""
    lines = ["## Auswertung", "", f"**Gesamt: {result.percent} % – {_LEVEL_MARK.get(result.level, result.level)}**",
             "", "| Bereich | Ergebnis | Bewertung |", "|---|---|---|"]
    for section in result.sections:
        lines.append(f"| {section.title} | {section.percent} % | {_LEVEL_MARK.get(section.level, section.level)} |")
    return "\n".join(lines) + "\n"


def parse_answers(text: str) -> dict:
    """Antworten aus dem Frontmatter eines Ergebnisses lesen (leer, wenn keins)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    for line in text[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == "antworten":
            try:
                return json.loads(value.strip())
            except json.JSONDecodeError:
                return {}
    return {}
