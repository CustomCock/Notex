# Notex – Fortschritt

Dieses Dokument ist der Einstiegspunkt für jede Arbeitssession: **zuerst lesen**, nach jedem
Feature aktualisieren (erledigt / offen / Entscheidungen / nächster Schritt). Es ersetzt kein
CHANGELOG (das ist für Nutzer), sondern hält den Arbeitsstand und die Gründe fest.

Branch für alle Arbeiten: `claude/textbaum-text-editor-it6n6b`. Releases entstehen durch Merge
nach `main` und ein annotiertes Tag `vX.Y.Z` (löst den Windows-Build in Actions aus). Tags kann nur
der Repo-Besitzer pushen.

## Stand

| Version | Inhalt | Status |
|---|---|---|
| 1.0.0 | Explorer + Editor, Design-System, Themes, Rechtschreibung/Grammatik, Toolbar, Dateizuordnung, Einzelinstanz | released |
| 1.1.0 | Block A: Lizenzen, Config-Autosave, Quick Open / Command Palette, Wiki-Links + Backlinks, Syntax-Highlighting | released |
| 1.1.1 | Fixes nach 1.1.0 (siehe unten) | fertig auf Commit `a332ee9`, Tag `v1.1.1` durch Besitzer |
| 1.2.0 | Block B: Markdown-Vorschau, Split View, erweiterte Suche | offen |
| 1.3.0 | Block C: Versionshistorie, verschlüsselte Notizen `.ntx` | offen |
| 1.4.0 | Block D: Vorlagen, Update-Check, Linux-Support | offen |

## Erledigt

### 1.0.0
- Portable App: Root = Ordner der EXE (dev: Projektordner, `NOTEX_ROOT` überschreibt), `data/`, `config.json`, `themes/`, `fonts/user/` daneben.
- Verzeichnisbaum, Tabs, Editor (QTextEdit, 1,5-facher Zeilenabstand, immer Umbruch, hängende Einrückung), Zeilennummern, Blatt-Modus.
- Volltextsuche im Hintergrund-Thread, Suchen/Ersetzen-Leiste, Dateiwächter, Papierkorb (send2trash).
- Design-System: Tokens in `notex/theme/tokens.py`, `dark.qss` mit `@token`-Platzhaltern, Lucide-Icons, Inter + JetBrains Mono.
- Eigene Themes (`themes/*.json`), Einstellungsdialog mit Live-Vorschau, Presets, Blatt-Varianten.
- Rechtschreibung (pyenchant/Hunspell, spylls als Fallback, Benutzerwörterbuch), Grammatik über LanguageTool-HTTP.
- Toolbar über dem Blatt mit Überlaufmenü, Schrift-Konzept (UI-Schrift vs. Textschrift pro Endung).
- Einzelinstanz (QLocalServer), Dateien per CLI/Drag&Drop, Windows-Dateizuordnung nur in HKCU auf Knopfdruck.
- PyInstaller-Build (`build.py`), Actions: Tests (Ubuntu) + Release (Windows, ZIP am Release).

### 1.1.0 – Block A
- A1: MIT-LICENSE, THIRD_PARTY_LICENSES.md, `licenses/` im Build, Config-Autosave (1 s, atomar), README-Korrekturen.
- A2: Quick Open (Ctrl+P, Fuzzy, `:Zeile`, `Datei:Zeile`), Command Palette (Ctrl+Shift+P), `core/actions.py` als zentrale Registry, Dateiindex-Thread.
- A3: Wiki-Links (`core/wikilinks.py`), Highlighter-Ebene, Ctrl+Klick, Autovervollständigung nach `[[`/`#`, Backlinks-Panel mit unverlinkten Erwähnungen, Link-Umschreibung beim Umbenennen mit Vorschau.
- A4: Pygments (`core/syntax.py`, zeilenweise mit Block-State für mehrzeilige Konstrukte), Log-Hervorhebung, Syntax-Farben hell/dunkel als Theme-Tokens, pro Endung schaltbar, Endungs-Migration (`extensions_version`).

### 1.1.1 – Fixes
- `build.py` bricht ab, wenn PySide6 & Co. im Build-Python fehlen (stummer Build ohne Qt war die Ursache für „No module named PySide6“).
- Ordner verschoben: beim Start Rückfrage „Registrierung auf den neuen Pfad aktualisieren?“ statt nur Toast; Status zeigt, ob die registrierte EXE noch existiert.
- Warnung beim Start aus einem temporären Ordner (ZIP nicht entpackt): Daten würden dort verloren gehen.
- README: Update-Anleitung (Pfad aktualisieren), `build.bat` erwähnt.

## Offen

### Block B – 1.2.0
- Markdown-Vorschau: markdown-it-py → HTML → QTextBrowser. Kein JS, keine Remote-Ressourcen automatisch (externe Bilder als Platzhalter mit „Laden“), Links nur per Klick im Browser, HTML sanitisieren. Ctrl+Shift+V wechselt Bearbeiten/Vorschau/Split, Checkboxen klickbar, Scroll-Sync.
- Split View (Ctrl+\): zwei Editorgruppen, Tabs per Drag zwischen Gruppen, gleiches Dokument in beiden, vertikal optional.
- Suche: Regex-Chip (ungültige Regex roter Rahmen, Timeout gegen katastrophales Backtracking), Filter `ext:`/`path:`/`-path:`/`"Phrase"`/AND, „Ganzes Wort“, Suchen & Ersetzen über mehrere Dateien mit Vorschau-Checkboxen.

### Block C – 1.3.0
- Lokale Versionshistorie in `history/` (komprimiert, dedupliziert, Ausdünnung, Größenlimit, Diff-Panel, Wiederherstellen, folgt Umbenennungen).
- Verschlüsselte Notizen `.ntx`: keine eigene Kryptografie, `cryptography` AES-256-GCM, Argon2id (Fallback scrypt), Header als AAD, neue Nonce pro Speichern, Klartext nie auf Platte (History/Suche/Index/Grammatik/Config/Logs/Toasts), Auto-Lock, Schloss-Icons, `docs/ENCRYPTION.md`, Tests (Roundtrip, falsches Passwort, Manipulation, Nonce, Formatversion).

### Block D – 1.4.0
- `templates/` + „Neue Woche“ mit Platzhaltern `{{date}} {{time}} {{weekday}} {{week}} {{year}} {{title}} {{cursor}}`.
- Update-Check über GitHub-Releases-API (max. 1×/Tag, kein Auto-Download).
- Linux: Plattform-Guards, .desktop/MIME auf Knopfdruck, CI auf Windows und Ubuntu, Linux-tar.gz-Build.

### Bekannte Einschränkungen (nicht geplant zu ändern, außer angegeben)
- Syntax-Highlighting ab 2 MB pro Datei aus; 40k-Zeilen-Dateien öffnen in ~1,5 s, Tippen dort ~25 ms/Taste (Qt-intern).
- Unverlinkte Erwähnungen werden synchron gescannt, Grenze 400 Dateien.
- Dateiindex: Baum-Signale + 60-s-Intervall, externe Änderungen erscheinen in Ctrl+P mit Verzug.
- Grammatik braucht einen LanguageTool-Server. Kontextmenü unter Windows 11 nur im klassischen Menü.
- Windows-spezifische Teile (Registry, DWM-Titelleiste, EXE-Build) sind in der Linux-Entwicklungsumgebung nur per Fake-Registry testbar.

## Entscheidungen

| Thema | Entscheidung | Grund |
|---|---|---|
| GUI | PySide6 (Qt 6), Editor als `QTextEdit` statt `QPlainTextEdit` | nur QTextEdit respektiert Zeilenhöhe 1,5 und Block-Formate für hängende Einrückung |
| Root/Portabilität | `Path(sys.executable).parent` im Build, Projektordner im Dev, `NOTEX_ROOT` für Tests | alles neben der EXE, nichts in AppData |
| Schichten | `notex/core/` Qt-frei und getestet, `notex/ui/` Qt, `notex/theme/` Tokens+QSS | Kernlogik ohne Display testbar (CI auf Ubuntu offscreen) |
| Rechtschreibung | pyenchant/Hunspell primär, spylls Fallback | spylls-Vorschläge für Deutsch zu langsam; Hunspell-Wörterbücher (de_DE, en_US) gebündelt |
| Grammatik | LanguageTool-HTTP-Client, Server optional | kein Java im Bundle; ohne Server still aus |
| Syntax | Pygments, zeilenweise mit eigenem State-Mapping (Fences ≥ 4, `STATE_FENCE_LANG_BASE`=100+Index) | QSyntaxHighlighter arbeitet blockweise; Pygments-Lexer nur für die genutzten Module als Hidden-Imports |
| Highlighter-Ebenen | Syntax → Wiki-Links → Rechtschreibung/Grammatik, pro Zeichen zusammengeführt | eine `QSyntaxHighlighter`-Instanz je Dokument, Ebenen dürfen sich nicht überschreiben |
| Dateizuordnung | nur HKCU, nur auf Knopfdruck, nie `UserChoice`, kein HKLM | kein Admin, keine Übergriffe; Standard-App wählt der Nutzer in Windows |
| Einzelinstanz | QLocalServer, Name aus Hash des App-Roots | zwei portable Kopien in verschiedenen Ordnern dürfen parallel laufen |
| Lizenz | MIT für Notex; Qt/PySide6 LGPLv3 dynamisch gebunden, Texte liegen bei | keine Konflikte; de_DE-Wörterbuch (GPL) als bloße Aggregation dokumentiert |
| Config | DEFAULTS-Deep-Merge mit Typprüfung, `extensions_version` für einmalige Migrationen, Autosave 1 s atomar | kaputte/alte Configs dürfen nie den Start verhindern |
| Abhängigkeiten | nur bei Bedarf, in `requirements.txt` gepinnt (Untergrenze + Major-Obergrenze) | Build-Größe (~95 MB ZIP) im Blick |
| Markdown-Rendering (Block B) | **markdown-it-py** → HTML → `QTextBrowser`, eigener Sanitizer (Whitelist Tags/Attribute, keine `javascript:`-URLs, `setOpenLinks(False)`, Remote-Bilder nur auf Klick) | kein QtWebEngine (Größe, JS-Angriffsfläche); Entscheidung wird bei Umsetzung bestätigt |
| Kryptografie (Block C, vorläufig) | `cryptography`: AES-256-GCM, KDF Argon2id (`cryptography>=43`, OpenSSL ≥ 3.2 in den Wheels) mit m=64 MiB, t=3, p=1, 16-Byte-Salt, 12-Byte-Nonce, Header (Magic, Version, KDF-Parameter, Salt) als AAD; Fallback scrypt (n=2^17, r=8, p=1) falls Argon2id nicht verfügbar | keine eigene Kryptografie; Parameter werden im Header gespeichert, damit sie später erhöht werden können |

## Nächster Schritt

1. Block B beginnen mit der Markdown-Vorschau (Core: Renderer + Sanitizer in `notex/core/markdown.py`, Tests), dann
   Split View, dann Suche. Nach Block B anhalten, Zusammenfassung, Release 1.2.0.
