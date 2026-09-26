# Changelog

Alle nennenswerten Änderungen an Notex. Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/).

## [1.3.0] – unveröffentlicht

### Hinzugefügt
- Versionsverlauf (Ctrl+Shift+Y): Schnappschüsse in `history/` bei Speichern, Öffnen, Neuladen, Ersetzen in
  Dateien und Link-Anpassung; zlib-komprimiert und dedupliziert, folgt Umbenennungen, Ausdünnung nach Alter,
  Größenlimit (Einstellungen → Editor), Diff zum aktuellen Text, Wiederherstellen als Undo-Schritt
- Verschlüsselte Notizen (.ntx): AES-256-GCM mit Argon2id-Schlüssel (Fallback scrypt) über `cryptography`,
  Header als Associated Data, neue Nonce bei jedem Speichern, Sperrbildschirm im Tab, automatisches Sperren
  nach Inaktivität, Ctrl+Shift+L, Neue verschlüsselte Notiz, Datei verschlüsseln, Passwort ändern, Schloss-Symbole
  in Baum und Tabs; Klartext nie auf der Platte (kein Verlauf, keine Suche, kein Link-Index, keine Grammatik,
  kein Wörterbuch-Eintrag). Format und Grenzen: docs/ENCRYPTION.md
- `.ntx` wird bestehenden Configs einmalig als Baum-Endung hinzugefügt

### Geändert
- Ein fehlendes Icon bricht keine Aktion mehr ab (Ersatzsymbol statt Fehler)
- Umbenennen im Baum kann die Endung .ntx weder setzen noch entfernen

### Abhängigkeiten
- cryptography (Apache-2.0/BSD, bringt cffi und pycparser mit); Lizenztexte in `licenses/`

## [1.2.0] – 2026-09-26

### Hinzugefügt
- Markdown-Vorschau (Ctrl+Shift+V wechselt Bearbeiten → Vorschau → Geteilt): markdown-it-py rendert
  CommonMark plus Tabellen/Durchstreichen in ein zweites Blatt (QTextBrowser, kein JavaScript). Rohes HTML
  wird nie durchgereicht, Links nur http(s)/mailto/#Anker/relativ im Notizordner, externe Bilder erst nach
  Klick auf „Bild laden“, externe Links öffnen den Browser nur auf Klick. Aufgaben-Checkboxen sind in der
  Vorschau klickbar, [[Wiki-Links]] und relative .md-Links öffnen die Zieldatei, Codeblöcke in den
  Syntax-Farben des Themes, Scrollen in der geteilten Ansicht synchron (abschaltbar)
- Split View (Ctrl+\): zweite Tab-Gruppe nebeneinander oder untereinander (Ctrl+Alt+\), Tabs per Drag
  zwischen den Gruppen (Ablegen am rechten/unteren Rand teilt), dieselbe Datei in beiden Gruppen als ein
  Dokument mit gemeinsamem Undo, Zustand der Gruppen wird in config.json gesichert
- Erweiterte Suche: mehrere Begriffe (AND), `"Phrase"`, Filter `ext:`, `path:`, `-path:`; Chips „.*“
  (Regex, ungültig = roter Rahmen, 0,25 s Timeout pro Zeile gegen katastrophales Backtracking) und
  „Wort“ (nur ganze Wörter); alle Treffer einer Zeile werden hervorgehoben
- Ersetzen in Dateien (Ctrl+Shift+H): Vorschau vorher → nachher je Zeile mit Häkchen, Regex-Gruppen
  im Ersatz, offene Dateien werden im Editor ersetzt (rückgängig machbar)

### Abhängigkeiten
- markdown-it-py (MIT) für die Vorschau, regex (Apache-2.0) für das Regex-Timeout; beide mit Lizenztext in `licenses/`

## [1.1.1] – 2026-09-26

### Behoben
- `build.py` bricht mit klarer Meldung ab, wenn PySide6 oder andere Pakete im Build-Python fehlen; vorher
  entstand stumm eine Exe, die mit „No module named 'PySide6'“ startete
- Ordner verschoben: Notex fragt beim Start, ob die Dateizuordnung auf den neuen Pfad gesetzt werden soll
  (vorher nur ein Hinweis); die System-Seite zeigt, ob die registrierte Exe noch existiert
- Warnung beim Start direkt aus der ZIP (Temp-Ordner): Notizen und Einstellungen würden dort verloren gehen

### Geändert
- README: Update-Anleitung mit „Pfad aktualisieren“, `build.bat` für den lokalen Build
- PROGRESS.md hält Arbeitsstand, Entscheidungen und nächste Schritte fest

## [1.1.0] – 2026-09-26

### Hinzugefügt
- Quick Open (Ctrl+P): Fuzzy-Suche über alle Dateien, `:Zeile` und `Datei:Zeile`, Dateiindex im Hintergrund
- Command Palette (Ctrl+Shift+P): alle Befehle mit Kategorie und Kürzel, zuletzt benutzte oben, zentrale Registry
- Wiki-Links `[[Datei]]`, `[[Datei|Text]]`, `[[Datei#Überschrift]]` mit Auflösung über data/, Ctrl+Klick,
  Anlegen fehlender Ziele, Autovervollständigung nach `[[` und `#`
- Backlinks-Panel (Ctrl+Shift+K) mit unverlinkten Erwähnungen und „verlinken“; Links werden beim
  Umbenennen/Verschieben nach Rückfrage in allen Dateien angepasst
- Syntax-Highlighting über Pygments für Code-Endungen und Markdown-Codeblöcke, Log-Hervorhebung
  (Zeitstempel, Level, IPs, Pfade), Farbschemata hell/dunkel als Theme-Tokens, pro Endung abschaltbar
- Neue Standard-Endungen im Baum (.sh .ps1 .bat .yaml .yml .xml .html .css .js .sql); bestehende
  config.json wird einmalig ergänzt, ohne eigene Anpassungen zu überschreiben
- LICENSE (MIT) und THIRD_PARTY_LICENSES.md, Lizenztexte im Build-Ordner

### Geändert
- config.json wird jede Sekunde bei Änderung atomar gesichert, nicht mehr nur beim Beenden

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
