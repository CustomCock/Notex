# Textbaum

Portabler Explorer + Editor für Textdateien unter Windows. Ein Ordner, eine EXE,
keine Installation: `data/` daneben ist dein Notizbaum, `config.json` merkt sich den Zustand.

![Screenshot von Textbaum](docs/screenshot.png)
<!-- Screenshot-Platzhalter: docs/screenshot.png anlegen, z. B. mit Win+Shift+S -->

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
  Zoom, Umbruch, Such-Checkboxen

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
| F2 / Entf | Umbenennen / In den Papierkorb (im Baum) |

## Ordnerstruktur der portablen App

```
Textbaum/
  Textbaum.exe
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

Die Tests decken die Qt-freie Kernlogik in `textbaum/core/` ab: Suche, Encoding-Erkennung,
atomares Speichern und das Laden einer kaputten `config.json`.

### Projektstruktur

```
main.py                 Einstieg
textbaum/
  paths.py              App-Ordner ermitteln (EXE-Ordner bzw. Projektordner)
  app.py                QApplication, Theme, Hauptfenster
  core/                 Qt-frei: config, encoding, fileops, search
  ui/                   Fenster und Widgets (Baum, Tabs, Editor, Suche, Statusleiste)
  theme/                Farbpalette, dark.qss, gezeichnete Icons
  assets/               App-Icon (erzeugt von tools/make_icon.py)
tests/                  pytest
build.py / build.bat    PyInstaller-Build
.github/workflows/      Tests bei jedem Push, Release-Build bei Tag v*
```

## Build (portable EXE)

```bat
python build.py
```

oder Doppelklick auf `build.bat` (legt bei Bedarf ein venv an). Ergebnis: `dist/Textbaum/`.
Diesen Ordner kannst du komplett kopieren, z. B. auf einen USB-Stick.

## Release über GitHub Actions

Ein Tag der Form `v*` stößt den Workflow `.github/workflows/release.yml` an: Er baut die App
auf `windows-latest`, packt `dist/Textbaum` als ZIP und hängt es an ein GitHub-Release.

```bat
git tag v0.1.0
git push origin v0.1.0
```
