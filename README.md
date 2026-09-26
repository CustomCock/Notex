# Notex

Portabler Explorer + Editor für Textdateien unter Windows. Ein Ordner, eine EXE,
keine Installation: `data/` daneben ist dein Notizbaum, `config.json` merkt sich den Zustand.

![Editor mit geöffneter Datei](docs/03-editor.png)

| Start | Suche | Seitenleiste eingeklappt |
|---|---|---|
| ![Empty State](docs/01-empty-state.png) | ![Suche mit Volltexttreffern](docs/04-search.png) | ![Seitenleiste eingeklappt](docs/05-sidebar-collapsed.png) |

| Kontextmenü | Suchen/Ersetzen | Gespeichert-Toast |
|---|---|---|
| ![Kontextmenü](docs/06-context-menu.png) | ![Suchen und Ersetzen](docs/07-find-replace.png) | ![Toast](docs/08-toast.png) |

Die Screenshots erzeugt `python tools/screenshot.py` automatisch (offscreen, mit Testdaten).

## Was es kann

- **Verzeichnisbaum** von `data/` links, Dateien per Klick im Editor öffnen, mehrere Tabs
- **Suche** (Ctrl+Shift+F): rekursiv, case-insensitive, nach Dateiname und/oder Volltext,
  läuft im Hintergrund-Thread, Klick auf einen Treffer springt in die Zeile
- **Editor**: weißes Blatt auf dunklem Tisch, Zeilennummern, aktuelle Zeile hervorgehoben,
  Suchen/Ersetzen (Ctrl+F / Ctrl+H), Zoom (Ctrl+Mausrad, Ctrl+Plus/Minus), Zeilenumbruch (Alt+Z)
- **Dateien**: Encoding (UTF-8, UTF-8-BOM, cp1252) und Zeilenenden (CRLF/LF) bleiben beim
  Speichern erhalten; atomares Speichern, damit bei einem Absturz nie eine halbe Datei liegt
- **Baum-Kontextmenü**: Neue Datei, Neuer Ordner, Umbenennen (F2), Papierkorb (Entf),
  Im Explorer anzeigen; Drag & Drop zum Verschieben
- **Watcher**: extern hinzugefügte Dateien tauchen im Baum auf; wird eine offene Datei
  extern geändert, fragt die App, ob sie neu laden soll
- **Zustand** in `config.json`: Fenster, Seitenleiste, aufgeklappte Ordner, offene Tabs,
  Zoom, Umbruch, Blatt-Modus, Such-Chips, Animationen
- **Design**: matt schwarz/grau, das Blatt weiß und zentriert (Alt+P schaltet auf volle Breite),
  ein einziger dezenter Akzent, kurze Animationen (abschaltbar unter Ansicht)

## Themes anpassen

Einstellungen öffnest du mit **Ctrl+,** oder über das Zahnrad unten in der Seitenleiste.
Alles wirkt sofort als Vorschau; **Abbrechen** stellt den Zustand von vorher wieder her,
**Übernehmen** speichert in `config.json`.

- **Darstellung**: Preset (Matt, Graphit, Mitternacht, Warm), alle Farb-Tokens per Farbwähler
  oder Hex-Eingabe, Eckenradius 0–12 px, Dichte (Kompakt / Normal / Luftig), Animationen an/aus
  und Geschwindigkeit. Neben einer Farbe erscheint ein Warnsymbol, wenn der Kontrast zum
  Hintergrund unter 4.5:1 (WCAG) fällt.
- **Blatt**: Varianten Weiß, Papier, Sepia, Dunkel; Blatt-, Text-, Zeilennummern- und
  Auswahlfarbe, Schatten und Stärke, Innenabstand, Blatt-Modus und maximale Textbreite.
- **Schrift**: UI- und Editor-Schrift (gebündelte plus installierte), Größen, Zeilenhöhe.

Eigene Themes speicherst du mit **Speichern als …**; sie liegen als JSON in `themes/` neben
der App und wandern mit dem Ordner mit. Duplizieren, Umbenennen, Löschen, Import und Export
(.json) gibt es daneben. Eine kaputte oder unvollständige Theme-Datei bringt die App nicht zum
Absturz: fehlende Werte werden aus dem Standard ergänzt, Fehler erscheinen als kurzer Toast.

| Einstellungen | Mitternacht + Sepia | Warm + Papier |
|---|---|---|
| ![Einstellungen](docs/09-settings.png) | ![Mitternacht](docs/11-preset-mitternacht-sepia.png) | ![Warm](docs/12-preset-warm-papier.png) |

## Rechtschreibung & Grammatik

### Rechtschreibung (offline)

Läuft komplett lokal mit Hunspell-Wörterbüchern für **Deutsch (de_DE)** und **Englisch (en_US)**
aus den LibreOffice-Dictionaries (gebündelt in `notex/dictionaries/`, Lizenzen liegen dabei).
Fehler bekommen eine rote Wellenlinie. Rechtsklick auf ein Wort zeigt bis zu fünf Vorschläge,
**Zum Wörterbuch hinzufügen** (landet in `user_dictionary.txt` neben der App) und
**In dieser Sitzung ignorieren**.

- **F7** schaltet die Prüfung global an/aus, ebenso das Symbol in der Statusleiste.
- Die Sprache (Deutsch / Englisch / Beide) stellst du in den Einstellungen ein; pro Tab lässt sie
  sich über den Sprachknopf in der Statusleiste überschreiben (mit `*` markiert).
- Geprüft wird standardmäßig nur in `.txt` und `.md`; für andere Endungen schaltest du es in den
  Einstellungen zu.
- Ausgelassen werden URLs, E-Mail-Adressen, Dateipfade, Hashes, Wörter mit Ziffern,
  Abkürzungen in Großbuchstaben, CamelCase, snake_case, Inline-Code und Codeblöcke in Markdown.
- Geprüft werden nur sichtbare und geänderte Absätze, jedes Wort wird pro Sprache nur einmal
  nachgeschlagen. Das Wort, das du gerade tippst, bleibt bis zu einer kurzen Pause unmarkiert.

Backend: **pyenchant** mit nativem Hunspell (das Windows-Wheel bringt die Bibliothek mit, die
Wörterbücher findet es über `ENCHANT_CONFIG_DIR`). Fehlt enchant, springt **spylls** ein, eine
reine Python-Implementierung von Hunspell: gleiche Ergebnisse, aber deutlich langsamer bei
deutschen Vorschlägen.

### Grammatik (optional, standardmäßig aus)

Grammatik prüft [LanguageTool](https://languagetool.org) über seine HTTP-API. Treffer bekommen
eine blaue Wellenlinie, Rechtsklick zeigt die Regelbeschreibung und Korrekturvorschläge.
Die Prüfung läuft im Hintergrund, absatzweise, etwa 1,5 s nach dem letzten Tastendruck.
Ist der Server nicht erreichbar, schaltet sie sich still ab und die Statusleiste zeigt
„LanguageTool nicht erreichbar“; nach einer Minute wird es erneut versucht.

- **Shift+F7** oder das Symbol in der Statusleiste schaltet die Grammatikprüfung um.
- Standard ist ein **lokaler Server** unter `http://localhost:8081`. Dann verlässt kein Text
  deinen Rechner.
- Die **öffentliche API** (`https://api.languagetool.org`) funktioniert erst, wenn du sie in den
  Einstellungen ausdrücklich erlaubst. Jeder geprüfte Absatz geht dann an einen externen Server.

Lokalen LanguageTool-Server starten (Java 17+ nötig):

```bat
rem 1. ZIP von https://languagetool.org/download/LanguageTool-stable.zip laden und entpacken
cd LanguageTool-6.x
java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081 --allow-origin
```

Alternativ per Docker: `docker run -d -p 8081:8010 erikvl87/languagetool` (dann Server-URL
`http://localhost:8081` eintragen).

| Rechtschreibung mit Kontextmenü | Einstellungen: Rechtschreibung |
|---|---|
| ![Rechtschreibung](docs/14-spellcheck.png) | ![Einstellungen Rechtschreibung](docs/15-settings-spelling.png) |

### Tastenkürzel

| Kürzel | Aktion |
|---|---|
| Ctrl+S / Ctrl+Shift+S | Speichern / Alle speichern |
| Ctrl+W | Tab schließen |
| Ctrl+N / Ctrl+Shift+N | Neue Datei / Neuer Ordner |
| Ctrl+B | Seitenleiste ein-/ausklappen |
| Ctrl+Shift+F | Suche in Dateien (Esc leert sie) |
| Ctrl+F / Ctrl+H | Suchen / Ersetzen in der aktuellen Datei |
| Ctrl+Plus / Ctrl+Minus / Ctrl+0 | Zoom |
| Alt+Z | Zeilenumbruch |
| Alt+P | Blatt zentrieren / volle Breite |
| Ctrl+, | Einstellungen |
| F7 / Shift+F7 | Rechtschreibung / Grammatik umschalten |
| F2 / Entf | Umbenennen / In den Papierkorb (im Baum) |

## Ordnerstruktur der portablen App

```
Notex/
  Notex.exe
  _internal/      <- Python + Qt, nicht anfassen
  data/           <- hier kommen deine Textdatei-Ordner rein (wird beim Start angelegt)
  config.json     <- Einstellungen und Zustand (wird beim Beenden geschrieben)
```

Welche Dateiendungen im Baum erscheinen, steht in `config.json` unter `extensions`
(Default: `.txt .md .log .csv .json .py .ini`). `fulltext_max_mb` begrenzt die Dateigröße
für die Volltextsuche (Default 5 MB).

## Entwicklung

Voraussetzung: Python 3.12 (3.11 funktioniert auch).

```bat
git clone https://github.com/customcock/notex.git
cd notex
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py
```

Im Dev-Modus liegen `data/` und `config.json` im Projektordner (beide in `.gitignore`).

### Tests

```bat
python -m pytest
```

Die Tests decken die Qt-freie Kernlogik in `notex/core/` ab: Suche, Encoding-Erkennung,
atomares Speichern, Config und Theme-Dateien (auch kaputte), Rechtschreibregeln und
-Backends sowie den LanguageTool-Client gegen einen Fake-Server.

### Design-System

Alle Farben, Abstände (4-px-Raster), Radien (6/8 px), Schriftgrößen und Animationsdauern
stehen als Tokens in `notex/theme/tokens.py`. Daraus wird `dark.qss` erzeugt; im UI-Code
gibt es keine losen Zahlenwerte. Schriften: Inter (UI) und JetBrains Mono (Editor), beide
gebündelt unter `notex/assets/fonts/` (SIL Open Font License). Icons: Lucide als SVG unter
`notex/assets/icons/` (ISC-Lizenz), zur Laufzeit in Theme-Farbe gerendert. Das App-Icon ist
`notex/assets/notex.svg`; `python tools/make_icon.py` rastert daraus PNG und ICO.

### Projektstruktur

```
main.py                 Einstieg
notex/
  paths.py              App-Ordner ermitteln (EXE-Ordner bzw. Projektordner)
  app.py                QApplication, Theme, Hauptfenster
  core/                 Qt-frei: config, encoding, fileops, search, theme_model,
                        theme_store, spell, spell_rules, grammar
  ui/                   Fenster und Widgets (Baum, Tabs, Blatt, Suche, Statusleiste, Toast,
                        Einstellungen, Rechtschreib-Highlighter, Grammatik-Service)
  dictionaries/         Hunspell-Wörterbücher de_DE, en_US (mit Lizenzen)
  theme/                tokens.py, dark.qss, Fonts- und Icon-Lader
  assets/               App-Icon, Fonts, Lucide-Icons (mit Lizenzen)
tools/                  make_icon.py, screenshot.py
docs/                   Screenshots
tests/                  pytest
build.py / build.bat    PyInstaller-Build
.github/workflows/      Tests bei jedem Push, Release-Build bei Tag v*
```

## Build (portable EXE)

```bat
python build.py
```

oder Doppelklick auf `build.bat` (legt bei Bedarf ein venv an). Ergebnis: `dist/Notex/`.
Diesen Ordner kannst du komplett kopieren, z. B. auf einen USB-Stick.

## Release über GitHub Actions

Ein Tag der Form `v*` stößt den Workflow `.github/workflows/release.yml` an: Er baut die App
auf `windows-latest`, packt `dist/Notex` als ZIP und hängt es an ein GitHub-Release.

```bat
git tag v0.1.0
git push origin v0.1.0
```
