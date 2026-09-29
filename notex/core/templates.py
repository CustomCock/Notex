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
TEMPLATE_SUFFIXES = (".md", ".txt", ".yar", ".yara", ".csv")
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

# Später hinzugekommene Standardvorlagen: landen genau einmal auch in bestehenden Vorlagen-Ordnern
# (gemerkt in config["templates"]["installed"] – vom Nutzer gelöschte Vorlagen kommen nicht zurück)
LATER_TEMPLATES: dict[str, str] = {
    "YARA-Regel.yar": (
        "rule Neue_Regel\n{\n    meta:\n        author = \"\"\n        description = \"{{cursor}}\"\n"
        "        date = \"{{date}}\"\n\n    strings:\n        $text = \"evil.example.com\" ascii wide nocase\n"
        "        $hex  = { 4D 5A 90 00 }\n        $re   = /https?:\\/\\/[a-z0-9.-]+\\/gate\\.php/\n\n"
        "    condition:\n        any of them\n}\n"
    ),
    "Zeitleiste.md": (
        "---\nnotex: zeitleiste\ntitel: {{title}}\n---\n# Zeitleiste: {{title}}\n\n"
        "Einträge: Rechtsklick in einer Datei/Logzeile → „Zur Zeitleiste hinzufügen“ oder Ctrl+Alt+Z. "
        "Ansicht mit Filter und Zeitzone: Ctrl+Shift+Alt+Z.\n\n"
        "| Zeit | Quelle | Beschreibung | Tags |\n|---|---|---|---|\n"
    ),
    "Beweismittel.md": (
        "# Beweismittel B-{{date:%Y%m%d}}-{{cursor}}\n\n"
        "| Feld | Wert |\n|---|---|\n"
        "| Beweismittel-ID | B-{{date:%Y%m%d}}- |\n"
        "| Beschreibung |  |\n"
        "| Fundort |  |\n"
        "| Zeitpunkt der Sicherstellung | {{date:%Y-%m-%d}} {{time}} (Zeitzone angeben) |\n"
        "| Sichergestellt von |  |\n"
        "| Art der Sicherung | Original / forensisches Abbild / logische Kopie |\n"
        "| Aufbewahrungsort |  |\n\n"
        "## Prüfsummen\n\n"
        "Einfügen: Command Palette → „Beweismittel: Prüfsummen einfügen“ (berechnet MD5, SHA-1, SHA-256).\n\n"
        "| Algorithmus | Wert | Datei |\n|---|---|---|\n|  |  |  |\n\n"
        "## Übergaben\n\n"
        "Neue Zeile mit aktueller Zeit: Command Palette → „Beweismittel: Übergabe eintragen“.\n\n"
        "| Wann | Von | An | Zweck | Unterschrift |\n|---|---|---|---|---|\n|  |  |  |  |  |\n\n"
        "## Notizen\n\n"
    ),
    # --- E-Mail-Vorlagen (O4): erste Zeile = Betreff, ohne Grußformel/Signatur (kommt aus Outlook) ---
    "E-Mail-Terminbestätigung.md": (
        "Betreff: Terminbestätigung {{date}}\n\n"
        "hiermit bestätige ich unseren Termin am §datum um §uhrzeit bei §kunde.\n\n"
        "Bitte melden Sie sich, falls etwas dazwischenkommt.\n"
    ),
    "E-Mail-Terminverschiebung.md": (
        "Betreff: Terminverschiebung\n\n"
        "leider muss ich unseren Termin verschieben. Passt Ihnen stattdessen §datum um §uhrzeit?\n\n"
        "Alternativ nennen Sie mir gern zwei Zeitfenster.\n"
    ),
    "E-Mail-Störung-Rückfrage.md": (
        "Betreff: Rückfrage zur gemeldeten Störung\n\n"
        "danke für Ihre Meldung. Für die Eingrenzung brauche ich noch ein paar Angaben:\n\n"
        "- Seit wann tritt das Problem auf?\n- Welche Geräte/Benutzer sind betroffen?\n"
        "- Gab es kürzlich Änderungen (Updates, neue Hardware)?\n- Genaue Fehlermeldung?\n"
    ),
    "E-Mail-Ticket-Eingang.md": (
        "Betreff: Ihr Anliegen ist eingegangen (Ticket §ticket)\n\n"
        "Ihre Anfrage haben wir unter der Nummer §ticket aufgenommen und kümmern uns darum.\n"
        "Sie erhalten eine Rückmeldung, sobald es Neuigkeiten gibt.\n"
    ),
    "E-Mail-Wartungsankündigung.md": (
        "Betreff: Geplante Wartung am §datum\n\n"
        "am §datum führen wir zwischen §uhrzeit und §uhrzeit_ende Wartungsarbeiten durch.\n"
        "In dieser Zeit kann §dienst zeitweise nicht erreichbar sein. Wir halten die Einschränkung so kurz wie möglich.\n"
    ),
    "E-Mail-Abschlussmeldung.md": (
        "Betreff: Erledigt – §betreff\n\n"
        "die gemeldete Sache ist erledigt. Kurz zusammengefasst:\n\n"
        "- Ursache: \n- Maßnahme: \n- Status: abgeschlossen\n\n"
        "Bitte prüfen Sie kurz, ob bei Ihnen alles wie erwartet funktioniert.\n"
    ),
    "E-Mail-Passwort-zurückgesetzt.md": (
        "Betreff: Passwort zurückgesetzt\n\n"
        "Ihr Passwort für §konto wurde zurückgesetzt. Aus Sicherheitsgründen wird das neue Passwort NICHT per "
        "E-Mail versendet – Sie erhalten es über den vereinbarten sicheren Weg und ändern es bitte bei der ersten "
        "Anmeldung.\n"
    ),
    "E-Mail-Angebotsanfrage.md": (
        "Betreff: Angebotsanfrage §thema\n\n"
        "für §thema hätten wir gern ein Angebot. Eckdaten:\n\n"
        "- Anzahl/Umfang: \n- Gewünschter Zeitraum: \n- Besonderheiten: \n\n"
        "Bitte nennen Sie uns Preis, Lieferzeit und Konditionen.\n"
    ),
    "E-Mail-Nachfassen.md": (
        "Betreff: Nachfrage zu §betreff\n\n"
        "ich komme kurz auf meine Nachricht vom §datum zurück. Konnten Sie schon einen Blick darauf werfen?\n"
        "Für Rückfragen stehe ich gern zur Verfügung.\n"
    ),
    "E-Mail-Phishing-Info.md": (
        "Betreff: Vorsicht: verdächtige E-Mails im Umlauf\n\n"
        "aktuell sind gefälschte E-Mails im Umlauf. Bitte:\n\n"
        "- keine Links oder Anhänge aus unerwarteten Mails öffnen\n"
        "- keine Zugangsdaten eingeben\n- im Zweifel kurz bei der IT nachfragen\n\n"
        "Verdächtige Mails bitte weiterleiten und dann löschen.\n"
    ),
    "E-Mail-Urlaubsübergabe.md": (
        "Betreff: Vertretung während meiner Abwesenheit\n\n"
        "vom §von bis §bis bin ich nicht erreichbar. In dringenden Fällen wenden Sie sich bitte an §vertretung.\n\n"
        "Offene Punkte:\n\n- \n- \n"
    ),
    # --- Tabellen-Vorlagen (O5): CSV bzw. Markdown; KEINE Passwortspalten ---
    "Tabelle-IP-Adressliste.csv": "Name,IP,MAC,Gerätetyp,Standort,Notiz\n",
    "Tabelle-Hardware-Inventar.csv": "Gerät,Hersteller,Modell,Seriennummer,Standort,Kaufdatum,Garantie bis,Notiz\n",
    "Tabelle-Softwarelizenzen.csv": "Software,Version,Lizenztyp,Anzahl,Ablauf,Zugeordnet an,Notiz\n",
    "Tabelle-Wartungsplan.csv": "Aufgabe,Intervall,Zuständig,Zuletzt,Nächste Fälligkeit,Status\n",
    "Tabelle-Backup-Protokoll.csv": "Datum,System,Umfang,Ergebnis,Dauer,Wiederherstellung getestet,Notiz\n",
    "Tabelle-Change-Log.csv": "Datum,Was geändert,Grund,Durchgeführt von,Zurückrollbar,Notiz\n",
    "Tabelle-VoIP-Nebenstellen.csv": "Nebenstelle,Name,Abteilung,Gerät,MAC,Notiz\n",
    "Tabelle-Patchfeld.csv": "Dose,Patchfeld-Port,Switch,Switch-Port,VLAN,Raum,Notiz\n",
    "Tabelle-Kontakte.csv": "Name,Firma,Rolle,Telefon,E-Mail,Notiz\n",
    "Tabelle-Zeiterfassung.csv": "Datum,Von,Bis,Pause,Tätigkeit,Projekt\n",
    "Tabelle-Benutzer-Zugänge.md": (
        "# Benutzer & Zugänge\n\n"
        "> Hinweis: **Keine Passwörter hier eintragen.** Passwörter gehören in einen Passwortmanager.\n\n"
        "| Benutzer | Konto/Login | System | Rolle/Rechte | MFA | Aktiv seit | Notiz |\n"
        "|---|---|---|---|---|---|---|\n|  |  |  |  |  |  |  |\n"
    ),
    "Tabelle-Lernplan.md": (
        "# Lernplan {{date:%Y}}\n\n"
        "| Woche | Thema | Ziel | Ressourcen | Status |\n|---|---|---|---|---|\n| {{week}} | {{cursor}} |  |  | offen |\n"
    ),
    "Tabelle-Aufgabenliste.md": (
        "# Aufgaben\n\n| Aufgabe | Priorität | Fällig | Status | Notiz |\n|---|---|---|---|---|\n"
        "| {{cursor}} | mittel | {{date+7}} | offen |  |\n"
    ),
}
DEFAULT_TEMPLATES.update(LATER_TEMPLATES)


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


def ensure_defaults(folder: Path, installed: list[str] | None = None) -> list[Path]:
    """Beim ersten Mal die Standardvorlagen anlegen. Vorhandene Dateien werden nie überschrieben;
    ist der Ordner schon da (auch leer, weil der Nutzer alles gelöscht hat), passiert nichts – außer für
    LATER_TEMPLATES, die noch nicht in `installed` stehen (die Liste wird ergänzt)."""
    folder = Path(folder)
    created = []
    # Erststart – auch wenn templates/ nur existiert, weil vorher templates/fragebogen/ angelegt wurde
    # (dann liegt dort keine einzige Vorlage und installiert wurde noch nichts)
    first_run = not folder.exists() or (installed is not None and not installed and not list_templates(folder))
    if first_run:
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in DEFAULT_TEMPLATES.items():
            path = folder / name
            if not path.exists():
                path.write_text(text, encoding="utf-8")
                created.append(path)
        if installed is not None:
            installed.extend(n for n in LATER_TEMPLATES if n not in installed)
        return created
    if installed is None:
        return []
    for name, text in LATER_TEMPLATES.items():
        if name in installed:
            continue
        path = folder / name
        if not path.exists():
            path.write_text(text, encoding="utf-8")
            created.append(path)
        installed.append(name)
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
