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
atomares Speichern und das Laden einer kaputten `config.json`.

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
  core/                 Qt-frei: config, encoding, fileops, search
  ui/                   Fenster und Widgets (Baum, Tabs, Blatt, Suche, Statusleiste, Toast)
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
