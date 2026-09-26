"""Vorlagen: Textdateien in templates/ neben der App mit Platzhaltern. Ohne Qt.

Platzhalter (Groß/Klein egal, Leerzeichen in den Klammern erlaubt):
  {{date}}       26.09.2026            {{date:%Y-%m-%d}}  beliebiges strftime-Format
  {{time}}       14:05                 {{time:%H:%M:%S}}
  {{weekday}}    Samstag (deutsch)
  {{week}}       39  (ISO-Kalenderwoche, zweistellig)
  {{year}}       2026 (bei {{week}} das ISO-Jahr der Woche, damit „KW 01 2027“ stimmt)
  {{title}}      Name der neuen Datei ohne Endung
  {{cursor}}     hier steht der Cursor nach dem Öffnen (wird entfernt)

Tagesversatz für Wochen- und Tagespläne: {{date+1}}, {{weekday+2}}, {{date-7:%d.%m.}} …
Basis ist das Datum, mit dem die Vorlage gefüllt wird („Neue Woche“: der Montag der Woche).
Unbekannte Platzhalter bleiben unverändert stehen, damit Tippfehler sichtbar sind.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
TEMPLATE_SUFFIXES = (".md", ".txt")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z]+)\s*([+-]\s*\d+)?\s*(?::([^}]*))?\}\}")

DEFAULT_TEMPLATES: dict[str, str] = {
    "Woche.md": (
        "# KW {{week}} · {{date}} – {{date+6}}\n\n"
        "## Ziele\n\n- [ ] {{cursor}}\n\n"
        "## {{weekday}} {{date:%d.%m.}}\n\n"
        "## {{weekday+1}} {{date+1:%d.%m.}}\n\n"
        "## {{weekday+2}} {{date+2:%d.%m.}}\n\n"
        "## {{weekday+3}} {{date+3:%d.%m.}}\n\n"
        "## {{weekday+4}} {{date+4:%d.%m.}}\n\n"
        "## Wochenende\n\n"
        "## Rückblick\n\n- Was lief gut?\n- Was nehme ich mit?\n"
    ),
    "Tagesnotiz.md": "# {{weekday}}, {{date}}\n\n## Heute\n\n- [ ] {{cursor}}\n\n## Notizen\n\n",
    "Besprechung.md": (
        "# {{title}}\n\n**Datum:** {{date}} {{time}}  \n**Teilnehmer:** \n\n"
        "## Themen\n\n1. {{cursor}}\n\n## Entscheidungen\n\n## Aufgaben\n\n- [ ] \n"
    ),
}


@dataclass(frozen=True)
class Rendered:
    text: str
    cursor: int | None   # Zeichenposition von {{cursor}} im Ergebnis, sonst None


def iso_week(day: date) -> tuple[int, int]:
    """(ISO-Jahr, ISO-Woche)."""
    year, week, _ = day.isocalendar()
    return year, week


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def render(template: str, now: datetime, title: str = "", base: date | None = None) -> Rendered:
    """Platzhalter ersetzen. `base` = Datum für {{date}}/{{weekday}}/Versätze (Standard: heute)."""
    base = base or now.date()
    iso_year, iso_wk = iso_week(base)
    out: list[str] = []
    cursor: int | None = None
    pos = 0
    for m in _PLACEHOLDER.finditer(template):
        out.append(template[pos:m.start()])
        pos = m.end()
        name = m.group(1).lower()
        offset = int(m.group(2).replace(" ", "")) if m.group(2) else 0
        fmt = m.group(3).strip() if m.group(3) else None   # „{{ date:%Y }}“: Leerzeichen vor }} gehört nicht zum Format
        day = base + timedelta(days=offset)
        value: str | None
        if name == "date":
            value = day.strftime(fmt) if fmt else day.strftime("%d.%m.%Y")
        elif name == "time":
            value = now.strftime(fmt) if fmt else now.strftime("%H:%M")
        elif name == "weekday":
            value = WEEKDAYS[day.weekday()]
        elif name == "week":
            value = f"{iso_week(day)[1]:02d}"
        elif name == "year":
            value = str(iso_week(day)[0] if "{{week" in template.replace(" ", "").lower() else day.year)
        elif name == "title":
            value = title
        elif name == "cursor" and not offset and not fmt:
            if cursor is None:
                cursor = sum(len(part) for part in out)
            value = ""
        else:
            value = None
        out.append(m.group(0) if value is None else value)
    out.append(template[pos:])
    return Rendered("".join(out), cursor)


def render_name(pattern: str, now: datetime, base: date | None = None) -> str:
    """Dateiname aus einem Muster wie „KW{{week}} {{year}}“ – ohne Cursor, ohne unerlaubte Zeichen."""
    name = render(pattern, now, base=base).text
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip(" .")
    return name or "Neu"


# ---- Ordner ------------------------------------------------------------------------------------

def list_templates(folder: Path) -> list[Path]:
    try:
        return sorted((p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in TEMPLATE_SUFFIXES
                       and not p.name.startswith(".")), key=lambda p: p.name.lower())
    except OSError:
        return []


def ensure_defaults(folder: Path) -> list[Path]:
    """Beim ersten Mal die Standardvorlagen anlegen. Vorhandene Dateien werden nie überschrieben;
    ist der Ordner schon da (auch leer, weil der Nutzer alles gelöscht hat), passiert nichts."""
    folder = Path(folder)
    if folder.exists():
        return []
    folder.mkdir(parents=True, exist_ok=True)
    created = []
    for name, text in DEFAULT_TEMPLATES.items():
        path = folder / name
        path.write_text(text, encoding="utf-8")
        created.append(path)
    return created


def template_text(folder: Path, name: str) -> str | None:
    """Text einer Vorlage aus dem Ordner, sonst die eingebaute Standardvorlage gleichen Namens."""
    path = Path(folder) / name
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return DEFAULT_TEMPLATES.get(name)


def default_file_name(template_name: str, now: datetime) -> str:
    """Vorschlag für neue Dateien: „2026-09-26 Tagesnotiz.md“."""
    stem, suffix = Path(template_name).stem, Path(template_name).suffix or ".md"
    return f"{now:%Y-%m-%d} {stem}{suffix}"
