# Changelog

Alle nennenswerten Änderungen an Notex. Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/).

## [1.0.0] – 2026-09-26

Erstes Release. Notex ist ein portabler Explorer + Editor für Textdateien unter Windows:
ein Ordner mit `Notex.exe`, `data/`, `config.json`, `themes/`, `fonts/user/`.

### Explorer und Dateien
- Verzeichnisbaum von `data/` mit Suche (Name/Volltext, rekursiv, im Hintergrund-Thread)
- Tabs, Encoding-Erkennung (UTF-8, UTF-8-BOM, cp1252), Zeilenenden bleiben erhalten
- Atomisches Speichern, Datei-Watcher, Papierkorb, Drag & Drop, Umbenennen
- Dateien von außen: Kommandozeile, Einzelinstanz, Drag & Drop aufs Fenster, Bereich „Geöffnet“,
  „In data/ kopieren/verschieben“, schreibgeschützte Dateien mit „Speichern unter …“
- Zuletzt geöffnet (Ctrl+R, Empty State)
- Windows-Dateizuordnung auf Knopfdruck, nur HKCU, restlos entfernbar

### Editor
- Weißes Blatt auf dunklem Tisch mit Schatten, Blatt-Modus mit maximaler Textbreite oder volle Breite
- Kein horizontales Scrollen: Umbruch immer aktiv, hängende Einrückung für Listen, Lese-Position
  bleibt beim Reflow erhalten
- Bearbeitungsleiste über dem Blatt (ein-/ausklappbar): Verlauf, Suchen, Textschrift, Ansicht,
  Zeilen- und Textwerkzeuge, Markdown-Toggles, Prüfung, Encoding/Zeilenende
- Zeilennummern, Suchen/Ersetzen, Zoom, Sprung zu Suchtreffern

### Rechtschreibung und Grammatik
- Rechtschreibung offline mit Hunspell (de_DE, en_US), rote Wellenlinie, Vorschläge, eigenes Wörterbuch,
  Sprache global und pro Tab, pro Dateiendung schaltbar
- Grammatik optional über LanguageTool (lokaler Server oder öffentliche API nach Freigabe)

### Design und Themes
- Design-Tokens, Presets (Matt, Graphit, Mitternacht, Warm), Blatt-Varianten (Weiß, Papier, Sepia, Dunkel)
- Einstellungsdialog mit Live-Vorschau, eigene Themes als JSON, Import/Export, Kontrast-Check
- Eine feste Oberflächenschrift (SF Pro aus `fonts/user/`, sonst Inter), einstellbare Textschrift,
  Schrift je Dateiendung
- Kurze Animationen (abschaltbar), Empty State, Toast, dunkle Titelleiste

### Technik
- Python 3.12, PySide6, Qt-freie Kernlogik mit 82 Tests
- PyInstaller-Build nach `dist/Notex/`, GitHub-Actions-Release bei Tag `v*`
