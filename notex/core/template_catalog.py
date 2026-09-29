"""Vorlagen-Katalog: jede Vorlage (Datei in templates/ oder Fragebogen in templates/fragebogen/) bekommt eine
Kategorie, wird alphabetisch einsortiert und ist über Name + Kategorie durchsuchbar.

Die Kategorie wird nur **berechnet** – keine Datei wird verschoben oder umbenannt, bestehende Vorlagen bleiben,
wo sie sind. Reihenfolge der Regeln:
  1. Unterordner in templates/ (eine Ebene) = Kategorie (eigene Ordnung des Nutzers, auch neue Kategorien)
  2. Fragebogen-YAML mit `category:` / mitgelieferte Vorlagen und Fragebögen per fester Zuordnung
  3. Namenspräfix „E-Mail-…“ → E-Mail, „Tabelle-…“ → Tabellen
  4. sonst „Sonstiges“
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from notex.core.templates import TEMPLATE_SUFFIXES

QUESTIONNAIRE_DIR = "fragebogen"
QUESTIONNAIRE_SUFFIXES = (".yaml", ".yml")
OTHER = "Sonstiges"
# feste Reihenfolge der bekannten Kategorien; eigene (Unterordner) kommen alphabetisch davor, „Sonstiges“ ans Ende
CATEGORIES = ("Ausbildung", "Kunde/Einsatz", "E-Mail", "Tabellen", "Planung & Notizen", "Sicherheit & Forensik")

BUILTIN_CATEGORY = {
    "Woche.md": "Planung & Notizen",
    "Tagesnotiz.md": "Planung & Notizen",
    "Besprechung.md": "Planung & Notizen",
    "YARA-Regel.yar": "Sicherheit & Forensik",
    "Zeitleiste.md": "Sicherheit & Forensik",
    "Beweismittel.md": "Sicherheit & Forensik",
    "berichtsheft.yaml": "Ausbildung",
    "systemcheck.yaml": "Kunde/Einsatz",
    "sicherheits-check.yaml": "Kunde/Einsatz",
}
PREFIXES = (("E-Mail-", "E-Mail"), ("Tabelle-", "Tabellen"))

_YAML_FIELD = re.compile(r"^(title|category):\s*(.+?)\s*$", re.MULTILINE)
_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


@dataclass(frozen=True)
class Entry:
    key: str            # Pfad relativ zu templates/ („Besprechung.md“, „Kunde/Bericht.md“, „fragebogen/x.yaml“)
    title: str          # Anzeigename
    category: str
    kind: str           # "file" | "questionnaire"

    @property
    def name(self) -> str:
        return Path(self.key).name


def sort_key(text: str) -> str:
    """Alphabetisch wie im Deutschen erwartet: ohne Groß/klein, Umlaute wie Grundbuchstaben."""
    return text.casefold().translate(_FOLD)


def category_for(name: str, subfolder: str = "", declared: str = "") -> str:
    if subfolder:
        return _known_spelling(subfolder)
    if declared.strip():
        return _known_spelling(declared.strip())
    if name in BUILTIN_CATEGORY:
        return BUILTIN_CATEGORY[name]
    for prefix, category in PREFIXES:
        if name.startswith(prefix):
            return category
    return OTHER


def _known_spelling(category: str) -> str:
    """„e-mail“ als Ordnername → „E-Mail“ (gleiche Kategorie wie die mitgelieferten)."""
    for known in CATEGORIES + (OTHER,):
        if sort_key(known) == sort_key(category):
            return known
    return category


def display_title(name: str, category: str) -> str:
    """„E-Mail-Terminbestätigung.md“ in „E-Mail“ → „Terminbestätigung“ (Präfix doppelt nicht)."""
    stem = Path(name).stem
    for prefix, prefixed_category in PREFIXES:
        if category == prefixed_category and stem.startswith(prefix) and len(stem) > len(prefix):
            return stem[len(prefix):]
    return stem


def _questionnaire_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in _YAML_FIELD.findall(text):
        fields.setdefault(key, value.strip().strip("\"'"))
    return fields


def scan(folder: Path) -> list[Entry]:
    """Alle Vorlagen unter `folder` (templates/): Dateien direkt darin, eine Ebene Unterordner, Fragebögen."""
    folder = Path(folder)
    entries: list[Entry] = []
    try:
        children = sorted(folder.iterdir())
    except OSError:
        return []
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_file() and child.suffix.lower() in TEMPLATE_SUFFIXES:
            category = category_for(child.name)
            entries.append(Entry(child.name, display_title(child.name, category), category, "file"))
        elif child.is_dir() and child.name.lower() == QUESTIONNAIRE_DIR:
            entries.extend(_scan_questionnaires(child))
        elif child.is_dir():
            try:
                files = sorted(p for p in child.iterdir()
                               if p.is_file() and p.suffix.lower() in TEMPLATE_SUFFIXES and not p.name.startswith("."))
            except OSError:
                continue
            for path in files:
                category = category_for(path.name, subfolder=child.name)
                entries.append(Entry(f"{child.name}/{path.name}", display_title(path.name, category), category, "file"))
    return sort_entries(entries)


def _scan_questionnaires(folder: Path) -> list[Entry]:
    entries = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in QUESTIONNAIRE_SUFFIXES or path.name.startswith("."):
            continue
        try:
            fields = _questionnaire_fields(path.read_text(encoding="utf-8", errors="replace")[:4000])
        except OSError:
            fields = {}
        category = category_for(path.name, declared=fields.get("category", ""))
        title = fields.get("title") or path.stem
        entries.append(Entry(f"{folder.name}/{path.name}", title, category, "questionnaire"))
    return entries


def _category_rank(category: str) -> tuple[int, str]:
    if category in CATEGORIES:
        return (0, f"{CATEGORIES.index(category):02d}")
    if category == OTHER:
        return (2, "")
    return (1, sort_key(category))


def sort_entries(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda e: (_category_rank(e.category), sort_key(e.title), sort_key(e.key)))


def matches(entry: Entry, query: str) -> bool:
    """Alle Suchwörter kommen in Name, Kategorie oder Dateiname vor (ohne Groß/klein, Umlaute tolerant)."""
    haystack = sort_key(f"{entry.title} {entry.category} {entry.key}")
    return all(sort_key(token) in haystack for token in query.split())


def filter_entries(entries: list[Entry], query: str) -> list[Entry]:
    return [e for e in entries if matches(e, query)] if query.strip() else list(entries)


def grouped(entries: list[Entry]) -> list[tuple[str, list[Entry]]]:
    """(Kategorie, Einträge) in Anzeige-Reihenfolge; leere Kategorien entfallen."""
    out: list[tuple[str, list[Entry]]] = []
    for entry in sort_entries(entries):
        if out and out[-1][0] == entry.category:
            out[-1][1].append(entry)
        else:
            out.append((entry.category, [entry]))
    return out
