# fckNotes (vorher Notex) – Fortschritt

Dieses Dokument ist der Einstiegspunkt für jede Arbeitssession: **zuerst lesen**, nach jedem
Feature aktualisieren (erledigt / offen / Entscheidungen / nächster Schritt). Es ersetzt kein
CHANGELOG (das ist für Nutzer), sondern hält den Arbeitsstand und die Gründe fest.

Branch für alle Arbeiten: `claude/textbaum-text-editor-it6n6b`. Releases entstehen durch Merge
nach `main` und ein annotiertes Tag `vX.Y.Z` (löst den Windows-Build in Actions aus). Tags kann nur
der Repo-Besitzer pushen.

**Entscheidung des Besitzers (26.09.2026):** Für 1.2.0 und die folgenden Blöcke vorerst kein eigenes
Release. Versionen werden weiter hochgezählt, CHANGELOG gepflegt und lokal getaggt; nach jedem Block
wird gestoppt und zusammengefasst, danach geht es ohne Release direkt weiter, wenn der Besitzer es sagt.

**Planwechsel (26.09.2026, Besitzer):** Der bisherige Plan „Blöcke F–I“ (Dateitypen, Werkzeuge, Lernen,
Sicherung) ist **verworfen** und durch den Plan „Blöcke F–K“ ersetzt (F Modul-System + Variablen, G Forensik-Basis,
H Forensik & CTF, I Netzwerk-Infos, J Netzwerk-Scanner, K Log-Auswertung + PCAP). Vom alten Plan war Block F zum
Zeitpunkt des Wechsels bereits vollständig umgesetzt (Commits `8c4a3db`–`7882924`, lokal getaggt `v1.6.0`) – nichts
davon wird gelöscht; der Besitzer entscheidet, wie damit umgegangen wird (siehe „Nächster Schritt“).

## Stand

| Version | Inhalt | Status |
|---|---|---|
| 1.0.0 | Explorer + Editor, Design-System, Themes, Rechtschreibung/Grammatik, Toolbar, Dateizuordnung, Einzelinstanz | released |
| 1.1.0 | Block A: Lizenzen, Config-Autosave, Quick Open / Command Palette, Wiki-Links + Backlinks, Syntax-Highlighting | released |
| 1.1.1 | Fixes nach 1.1.0 (siehe unten) | fertig auf Commit `a332ee9`, Tag `v1.1.1` durch Besitzer |
| 1.2.0 | Block B: Markdown-Vorschau, Split View, erweiterte Suche | fertig auf Commit `c178bcc` (CI grün), kein Release (Besitzer) |
| 1.3.0 | Block C: Versionshistorie, verschlüsselte Notizen `.ntx` | fertig, kein Release (Besitzer) |
| 1.4.0 | Block D: Vorlagen, Update-Check, Linux-Support | fertig, CI grün (Tests Win+Ubuntu, Builds Win+Linux), kein Release (Besitzer) |
| 1.5.0 | Block E: Kontextmenü, Nachschlagen (Wikipedia/Wiktionary-Karte, Websuche) | fertig, kein Release (Besitzer) |
| 1.6.0 | Alter Block F (verworfener Plan): Bilder, CSV, JSON/YAML, Hex/Dateityp/Hashes, Live-Logs, PDF | fertig, CI grün, lokal getaggt, bleibt (Besitzer) |
| 1.7.0 | Neuer Block F: Modul-System, Variablen | fertig, Tests grün, lokal getaggt, kein Release (Besitzer) |
| 1.8.0 | Block G: Forensik-Basis (Hex-Lücken, Strings, Eingebettete Dateien, Entropie) | fertig, Tests grün, lokal getaggt, kein Release (Besitzer) |
| 1.9.0 | Block H: Metadaten, YARA, Zeitleiste & Beweismittel, IOC entschärfen | fertig, Tests grün (Win+Linux), lokal getaggt, kein Release |
| 1.10.0 | Block I: Port-Infos, IP-Konflikte, RDAP/ASN | fertig, Tests grün, lokal getaggt, kein Release |
| 1.11.0 | Block J: Netzwerk-Scanner | fertig, Tests grün, lokal getaggt, kein Release |
| 1.12.0 | Block K: Log-Auswertung, PCAP | fertig, Tests grün, lokal getaggt, kein Release |
| 1.12.1 | Block L: Fehlerbehebung (Scanner, Encoding-Menü, JPEG-Metadaten, PCAP-Auswertung) | fertig, Tests grün, lokal getaggt |
| 1.13.0 | Block M: Werkzeuge-Menü, Explorer-Orte, Neu nach Typ, App-Icon, PDF/HTML-Export, allgemeine Log-Auswertung | fertig, Tests grün, lokal getaggt |
| 1.14.0 | Block Q: Analyse per Rechtsklick (Typ-Erkennung, Karte, Netz-/Hash-/Umwandeln-Aktionen) | fertig, Tests grün, lokal getaggt |
| 1.15.0 | Block N: Geräte-Scanner (Advanced-IP-Scanner-artig), OUI-Hersteller, NetBIOS, Host-Aktionen, Export | fertig, Tests grün, lokal getaggt |
| 1.16.0 | Block O: WYSIWYG-Markdown, Fragebogen-Engine + Assistent, Berichtsheft (ICS), Systemcheck, Sicherheits-Check, E-Mail-/Tabellen-Vorlagen | fertig, Tests grün, lokal getaggt |
| 1.17.0 | Plan R: Netzwerk-Tools/Werkzeuge-Menü repariert, Aufräumen, Netzwerk-Tests + CI mit PySide6, Vorlagen nach Kategorien, Module alle an/aus | released vom Besitzer (Tag v1.17.0; meldet intern noch 1.16.0) |
| 1.17.1 | Umbenennung zu fckNotes (Repo CustomCock/fckNotes), Versionsnummer korrigiert, Screenshots neu | fertig auf dem Arbeitsbranch, Tag durch Besitzer |

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

### 1.2.0 – Block B
- B1 Markdown-Vorschau: `core/markdown.py` (markdown-it-py, html=False, eigener Renderer mit Link-/Bild-Whitelist,
  Aufgaben mit Zeilen-Mapping, Wiki-Links, Fence-Highlighting über `core/syntax`), `ui/preview.py` (QTextBrowser,
  `setOpenLinks(False)`, `loadResource` nur Notizordner + freigegebene Bilder, Bild-Fetch im Thread mit 8-MB-Limit),
  `EditorPage` mit Modi edit/preview/split und proportionalem Scroll-Sync. Ctrl+Shift+V.
- B2 Split View: `ui/editor_area.py` (EditorArea mit 1–2 `EditorTabs`-Gruppen, Attribut-/Signal-Weiterleitung),
  `Editor(share_with=…)` teilt QTextDocument/Undo/Highlighter, Highlighter prüft sichtbare Bereiche aller Ansichten,
  Tab-Drag über eigenes MIME, `core/split_state.py` für config.json. Ctrl+\, Ctrl+Alt+\, Ctrl+Alt+→.
- B3 Suche: `core/search.py` mit Abfragesprache (AND, Phrase, ext:/path:/-path:), Regex mit Timeout (Modul `regex`),
  Ganzes Wort, Mehrfach-Spans; `ui/replace_dialog.py` (Ctrl+Shift+H) mit Häkchen je Zeile.
- Selbstprüfung am Blockende: Zoom/Toolbar-Klappen/Beenden-Rückfrage gruppenübergreifend korrigiert; lokaler
  PyInstaller-Build geprüft (neue Module im Archiv, Build +2 MB), 127 Tests grün.
- CI-Fix: Test-Workflow installiert markdown-it-py, regex und Pygments ausdrücklich (war beim ersten Push rot).

### 1.3.0 – Block C
- C1 Versionsverlauf: `core/history.py` (Objekte `history/objects/xx/<sha256>.z` mit zlib, `index.json` mit IDs statt
  Pfaden, Dedup, `thin()` nach RETENTION, `enforce_limit()` + Garbage Collection, `rename()` für Dateien/Ordner,
  `.ntx` ausgeschlossen, Prüfsumme beim Lesen), `ui/history_dialog.py` (Liste + Diff-HTML, Wiederherstellen als
  Undo-Schritt). Schnappschüsse bei Speichern, Öffnen, Neuladen und vor Schreibzugriffen außerhalb des Editors
  (Ersetzen in Dateien, Link-Anpassung, Verlinken). Ctrl+Shift+Y. Icon-Lader wirft bei fehlendem Icon nicht mehr.
- C2 Verschlüsselte Notizen: `core/crypto_notes.py` (Format v1, 50-Byte-Header als AAD, AES-256-GCM, Argon2id
  64 MiB/3/4 bzw. scrypt 2^17/8/1, Parametergrenzen vor der KDF, NFC-Passwort, `KeyState` ohne Schlüssel im repr),
  `ui/lock_overlay.py` (Sperrbildschirm im Tab, PasswordDialog), `EditorTabs.unlock/lock/_save_encrypted/change_password`,
  Auto-Lock per App-Eventfilter (Standard 5 min, Ctrl+Shift+L), Befehle Neue Notiz / Datei verschlüsseln / Passwort
  ändern, Schloss-Icons in Baum und Tabs, Umbenennen-Schutz für .ntx. Leckstellen geschlossen: Verlauf, Volltext,
  Ersetzen, Link-Index, Erwähnungen, Grammatik (auch Service-seitig), Wörterbuch-Eintrag, Split-View-Zweitansicht.
  Ende-zu-Ende-Test: Marker-Suche über den ganzen App-Ordner inkl. dekomprimierter Historie ohne Treffer.
  `docs/ENCRYPTION.md` liegt auch im Build-Ordner. Build +15 MB (cryptography/OpenSSL).

### 1.4.0 – Block D
- D1 Vorlagen: `core/templates.py` (Platzhalter inkl. strftime-Format und Tagesversatz, ISO-Woche/-Jahr,
  `ensure_defaults` legt Woche/Tagesnotiz/Besprechung nur beim allerersten Mal an), `templates/` neben der App,
  Befehle Neue Datei aus Vorlage (Ctrl+Shift+T), Neue Woche (Alt+W), Nächste Woche, Vorlagen-Ordner öffnen, jede
  Vorlage als Palette-Befehl, Einstellungen (Wochen-Ordner, -Dateiname). Nebenbei behoben: Tab-Überblendung in
  falschen Koordinaten (seit 1.0).
- D2 Update-Check: `core/update_check.py` (höchste gültige Version statt jüngstes Datum, Entwürfe/Vorabversionen/
  Nicht-Versions-Tags wie „main“ ignoriert, nur Links ins eigene Repo, 2-MB-Grenze, 1×/Tag), `ui/update_service.py`
  (QThread + Dialog), Hinweis per Toast, Hilfe › Nach Updates suchen, überspringen, Einstellungen → System. Kein
  Download. Tests inkl. lokalem Fake-Server.
- D3 Linux: `core/linux_desktop.py` (Desktop Entry mit Exec-Quoting nach Spec, MIME-XML mit Glob + Magic für .ntx,
  Icon, update-desktop-database/update-mime-database falls vorhanden, nie `xdg-mime default`; geprüft mit
  desktop-file-validate und update-mime-database), Einstellungen → System zeigt unter Linux diesen Abschnitt statt der
  Windows-Zuordnung, Rückfrage nach Ordnerwechsel. CI: Tests-Matrix Ubuntu + Windows; release.yml baut Windows-ZIP und
  Linux-tar.gz (ubuntu-22.04), bei Branch-Pushes mit Build-Änderungen als Build-Check ohne Release.

### 1.5.0 – Block E
- Kontextmenü (`Editor.build_context_menu` + `context_menu_hook` des Hauptfensters): Vorschläge, Bearbeiten, Text mit
  den QActions der Bearbeitungsleiste (keine doppelte Logik), Nachschlagen; Rechtsklick außerhalb der Markierung setzt
  den Cursor → Wort unter dem Mauszeiger.
- `core/lookup.py`: Begriffsaufbereitung, URL-Bau (Titel-Encoding, Suchseiten, Suchmaschinen inkl. eigener URL mit/ohne
  {q}), `fetch_json` mit Fehlerarten (404/429/Timeout/Offline/kaputtes JSON), WikipediaClient (REST summary, opensearch,
  Begriffsklärung über Wikitext-Bullets), WiktionaryClient (Action-API parse/wikitext, Parser für de/en, Schreibvarianten,
  opensearch), `clean_wikitext`, `with_fallback`, `LookupService` (Sitzungs-Cache, eine Anfrage nach der anderen),
  `SendGuard`, `place_card`. 31 Tests mit Fake-Server.
- `ui/lookup_card.py`: Popup-Karte (Skeleton, Worker-Thread, ganze Karte klickbar, Links für Quelle/Web/Begriffsklärung/
  „mehr“, Fehlerzustände, Fade-In, optionales Vorschaubild). Einstellungen-Kategorie „Nachschlagen“. Ctrl+Alt+W/T/G
  (vorher geprüft: frei; auf deutscher Windows-Tastatur erzeugt AltGr+W/T/G kein Zeichen).
- Live-Abgleich mit den Wikimedia-APIs war in der Arbeitsumgebung nicht möglich (Netzrichtlinie sperrt wikipedia.org/
  wiktionary.org); Parser auf die dokumentierten Wikitext-Formate gebaut und mit realistischen Auszügen getestet.
- Screenshot-Skript: virtueller Full-HD-Bildschirm (offscreen war 800×600 und kürzte Menüs).

### 1.6.0 – Block F
- Build-Größen (Build-Check-Artefakte): vorher Windows-ZIP ≈ 96,2 MB, Linux-tar.gz ≈ 91,4 MB; nach F6
  Windows ≈ 96,7 MB, Linux ≈ 92,6 MB (Qt6Pdf lag über das PDF-Bildformat-Plugin schon großteils im Build).
- F6 vorab gemessen: QtPdf+QtPdfWidgets Windows 5,0 MB entpackt / ≈ 2,7 MB in der ZIP, Linux ≈ 5 MB entpackt
  (QtNetwork ist wegen der Einzelinstanz ohnehin dabei) → unter 25 MB, wird umgesetzt.
- F1 Bilder: `core/images.py` (asset_name, assets_dir, relative/encodierte Links, image_links inkl. <…>-Links und <img>,
  plan_assets_move mit Verschieben/Kopieren, find_unused_images, can_embed_images = nie in .ntx), `ui/viewer_page.py`
  (Basis für Nicht-Editor-Tabs), `ui/image_view.py`, `ui/unused_images_dialog.py`; EditorTabs mit Viewer-Registry,
  viewer_kind_for (Bild/PDF/Hex nach Endung + Magic), Viewer in open_paths/Umbenennen/Schließen/Split-Verschieben;
  Editor.image_hook für Ctrl+V/Drop; Config images.assets_folder, extensions_version 4.
- `core/filetype.py` (aus F4 vorgezogen, weil die Tab-Wahl ihn braucht).
- F2 CSV: `core/csvdata.py` (sniff mit Sniffer + Zähl-Fallback, Quoting-Stil „minimal“/„all“, parse/serialize,
  to_number deutsch/englisch, Sortier-/Filter-Indizes), `ui/csv_view.py` (CsvModel = QAbstractTableModel über
  Zeilenlisten, Ansicht per Indexliste; CsvView mit Leiste). EditorPage kennt jetzt Datenmodi (`DATA_MODES` =
  table/tree, `view_modes` je Datei, `flush_data_view()` schreibt als EIN Undo-Schritt zurück – vor Speichern,
  Speichern unter und beim Zurückschalten). Der Editortext bleibt Quelle der Wahrheit; externe Änderungen/Neu lesen
  laden die Tabelle nach. Encoding-Override über `encoding.decode_as` (liest die Datei neu, fragt bei ungespeicherten
  Änderungen). Text-Befehle (Ctrl+D, Groß/klein …) sind in der Datenansicht gesperrt, Ctrl+F springt ins Filterfeld.
  Config `data_view.csv_as_table`, `data_view.json_indent` (für F3).
- F3 JSON/YAML: `core/structured.py` (kind_for, validate/parse mit ParseError Zeile/Spalte/Position, format_json
  token-basiert – Literale bleiben exakt, minify, YAML nur safe_load_all/safe_dump(_all) mit sort_keys=False,
  yaml_has_comments, path_string `$.a[3]["x y"]`, preview/type_name/children), `ui/tree_view.py` (DataTreeView,
  lazy Kinder, max. 5000 je Knoten, Werte Python-seitig in `_nodes` statt QVariant), `ui/structured_commands.py`
  (Befehle + Live-Prüfung: Timer 600 ms, nicht neu gestartet → beim Tippen höchstens alle 0,6 s; Cache nach Pfad,
  weil PySide für `document()` jedes Mal neue Wrapper liefert → `id()` taugt nicht). Editor.set_problem (rote
  Welle), StatusBar.problem_button (auch für Dateityp-Warnungen in F4). Entscheidung: PyYAML==6.0.3 exakt gepinnt.
- F4 Hex/Typ/Hashes: `core/hexdata.py` (PagedFile: 64-KB-Seiten, LRU 32, Datei nur je Lesevorgang offen –
  Entscheidung gegen mmap, weil Windows gemappte Dateien nicht umbenennen/löschen lässt; parse_offset,
  parse_hex_pattern, search_file blockweise mit Überlappung + Umlauf + Abbruch), `core/hashing.py` (ein
  Lesedurchgang für alle vier, normalize/match_digest), `ui/hex_view.py` (_HexArea selbst gezeichnet,
  Scrollbalken skaliert ab 1 Mrd. Zeilen, Suche in QThread), `ui/hash_dialog.py`. Baum-Kontextmenü „Als Hex
  öffnen“/„Prüfsummen …“, Dateityp-Warnung über StatusBar.problem_button, Token `success`. Watcher:
  `fileops.file_signature` (> 16 MB Größe+mtime+Rand-Hash). 3 GB: Öffnen 0,06 s, Suche bis Ende ~3–17 s im Hintergrund.
- F5 Live: `core/tail.py` (Tailer mit Datei-ID (st_dev, st_ino) für Rotation, Größe < Position = Kürzung,
  inkrementeller Decoder, CRLF über Blockgrenzen, angefangene Zeile zurückgehalten, max. 2 MB pro poll, Start mit den
  letzten 8 MB; classify ERROR/WARN; LogFilter mit Timeout-Regex aus core.search; can_follow = nie .ntx),
  `ui/log_view.py` (QPlainTextEdit mit maximumBlockCount 200k, Poll 500 ms im UI-Thread – liest nur Zuwachs;
  Level-Highlighter). EditorPage-Modus „live“ (in DATA_MODES, aber nicht im Ctrl+Shift+V-Zyklus); Watcher-Rückfragen
  (geändert/entfernt) für live-Pfade unterdrückt, beim Beenden neu beobachten und Editor von der Platte laden.
  Token `warning`.
- F6 PDF: `core/pdfdoc.py` (PageLayout, fit-Skalen, snap_to_lines, clean_selection inkl. PDFium-Trennmarker
  U+FFFE, quote_markdown), `ui/pdf_view.py` – eigene Seitenansicht statt QPdfView (Entscheidung: QPdfView kann
  keine Textauswahl); QPdfPageRenderer MultiThreaded + Bild-Cache 24, Auswahl über getSelection mit Einrasten auf
  Zeilenboxen aus getAllText().bounds() (PDFium trifft nur exakt auf Glyphen; Zeichenboxen einzeln wären ~0,2 ms/Zeichen),
  QPdfSearchModel, QPdfBookmarkModel. Laden über QBuffer (≤ 256 MB) → keine Dateisperre. Nur QtPdf, kein
  QtPdfWidgets. build.py: QtPdf nicht mehr ausgeschlossen, Hidden-Import. Zitat: EditorArea.pdf_quote →
  MainWindow._insert_pdf_quote (Notiz im anderen Teil, sonst Zwischenablage). Split auch aus Viewer-Tabs.
- CI-Fix: Grammatik-Rate-Limit schläft bis der Mindestabstand wirklich erreicht ist (Windows-Uhr ≈16 ms).
- Screenshots 38–45 (Bild, CSV, JSON-Baum/-Fehler, Hex, Prüfsummen, Live-Log, PDF-Zitat) in README eingebunden.
- Nebenbei: großes Öffnen beschleunigt (Highlighter während `load()` ausgesetzt, `schedule_reset` fasst Laden +
  Resolver zu einem Durchlauf zusammen, hängende Einrückung nur bei geänderter Schriftmetrik). 100k Zeilen:
  Öffnen ~2 s + ~1 s Einfärben (vorher ~12 s), Tabelle 0,5 s, Sortieren 0,2 s, Filtern 0,05 s.

### 1.7.0 – neuer Block F
- F1 Module: `core/modules.py` – MODULES (15 Einträge mit Name, Beschreibung, Abhängigkeit, Standard, Block),
  ModuleRegistry mit Aktivator-Muster: `contribute(key, activate)`; activate hängt ein und gibt einen Rückbau zurück;
  läuft nur, wenn das Modul an ist; set_enabled baut ohne Neustart auf/ab; has_contributions → „folgt in Block …“.
  Config `modules` (Standard an: variables, hex, ports, ioc). Hex & Dateianalyse ist das erste Modul:
  Viewer-Registrierung, Menü-/Palette-Einträge, Kürzel und Baum-Kontextmenü (`FileTree.menu_providers`) hängen am
  Aktivator; beim Abschalten werden offene Hex-Tabs geschlossen. Einstellungen → Module; Abbrechen dreht Module über
  die Registry zurück. Nebenbei: Latin-1 als letzte Encoding-Stufe (cp1252 kennt 5 Bytes nicht).
- F2 Variablen: `core/variables.py` (find_tokens: ganzer \w-Lauf muss definiert sein → längster Name gewinnt,
  „§23a“ bleibt Text; Escape `\§name` nur für definierte Namen; resolve/resolve_with_line_map, escape/unescape,
  replace_all, escape_all, completions, typed_name_before, JSON laden/atomar speichern), `ui/variables_service.py`,
  `ui/variable_render.py`, `ui/variables_dialog.py`, Highlighter-Ebene, Editor-Hooks, Vorschau, Suche (Chip „§“).
  **Entscheidung Anzeige:** Wert statt Token im Lesefluss. Umsetzung ohne Eingriff in den Dokumenttext: der
  Highlighter macht die Token-Zeichen unsichtbar und gibt ihnen per absolutem Zeichenabstand genau die Breite des
  Werts (+ Rand), der Editor zeichnet den Wert in die Lücke (paintEvent). Vorher gemessen: Breite stimmt auf < 0,5 px,
  Zwischenpositionen im Token sind unsortiert – deshalb rastet der Cursor an den Token-Rändern ein
  (cursorPositionChanged, Richtung bei ←/→), Entf/Rücktaste löschen das ganze Token, Auswahlen wachsen nach außen.
  Vorteil gegenüber Objekt-Ersetzungszeichen (U+FFFC): Undo, Suche, Speichern, Verlauf, Wiki-Links sehen weiter das
  Token, die Datei bleibt byte-identisch. Grenzen: Token in anderer Schriftgröße (z. B. Überschrift mit eigener
  Schrift) → Breite leicht ungenau; Werte über 80 Zeichen werden in der Anzeige gekürzt (Hover zeigt alles),
  mehrzeilige Werte einzeilig mit „⏎“. Kopieren: eigenes QMimeData, weil QTextEditMimeData setText ignoriert.
- Nebenbei behoben: Split View – beim Verschieben zwischen Gruppen blieben Signale/Leiste an der alten Gruppe
  (nach Aufheben der Teilung gelöscht). Jetzt `EditorTabs.wire_page/unwire_page`, aufgerufen in `_move_page` und
  beim Verschieben von Viewern.
- Build-Größe: keine neuen Abhängigkeiten, build.py unverändert → Build-Check lief nicht; Stand wie nach 1.6.0
  (Windows ≈ 96,7 MB, Linux ≈ 92,6 MB).
- Screenshots 46–49 (Module, Variablen im Editor, Vorschläge, Einstellungen → Variablen).

### 1.8.0 – Block G
- G1 (Lücken, Rest stammt aus 1.6.0/F4): hexdata.to_base64/to_c_array/interpret/selection_value, Signaturen TAR
  (ustar @257), PCAP (4 Magics), PCAPNG, EVTX; Hex-Kontextmenü mit Kopierformaten, Werte-Zeile „HexInspector“,
  Auswahlwert in der Statusleiste; HexPage.select_range + MainWindow.show_in_hex/_analysis_target für G2–G4.
- G2 Strings: `core/strings.py` (_scan über Blöcke mit Übertrag: Treffer am Blockende bzw. halbes UTF-16-Paar werden
  mitgenommen, sonst die letzten 2·min+2 Bytes – aber nie Bytes eines ausgegebenen Treffers → keine Duplikate;
  Grenze 200 000 Treffer; classify mit ipaddress-Prüfung, Base64 nur bei gemischten Zeichen), `ui/analysis_dialog.py`
  (gemeinsame Basis: AnalysisWorker-QThread, Fortschritt, Abbrechen, nicht modal), `ui/strings_dialog.py`.
  MainWindow._activate_analysis: gemeinsamer Modul-Aktivator (Menü, Palette, Kürzel, Baum); beim Abschalten werden
  offene Analysefenster geschlossen. 50 MB Zufallsdaten: 0,6 s bis zur Grenze.
- G3 Eingebettete Dateien: `core/carve.py` – Scan per bytes.find je Signatur (Überlappung für Grenzen), Kandidaten
  erst danach geprüft (eigene Prüfer je Format, Größe aus Format; gzip/bzip2/xz: Dekomprimieren mit 1-MB-Schritten
  und max. 1 GB Ausgabe gegen Bomben, Grenze 256 MB Eingabe je Fund), `_trailers` (Daten hinter dem Ende, außer
  Nullen/FF und außer wenn ein umschließender Fund bis Dateiende reicht). Bewusst NICHT gesucht (keine prüfbaren
  Köpfe, zu viele Falsch-Positive): ICO, TIFF, Mach-O-Fat/Java-Class, WASM, MP3/OGG/FLAC. Extrahieren mit open("xb").
  Tests mit selbst erzeugten Dateien (14 Formate in einem Container, JPEG+ZIP, PNG+Anhang, Füllbytes, Blockgrenze,
  docx-Erkennung, gzip-Länge, Falsch-Positive). 64 MB Zufallsdaten: 0 Funde, 1,1 s. `ui/embedded_dialog.py`.
- G4 Entropie: `core/entropy.py` (Counter je Block, Gesamtwert aus summierten Häufigkeiten; Blockgröße ≥ 1 KB und
  **Miller–Madow-Korrektur** je Block – Entscheidung: ohne sie erreichen 256-B-Blöcke aus Zufallsdaten nur ~7,1 und
  die Schwelle 7,5 wäre wertlos; assess() mit Anteilen hoch/niedrig; regions()), `ui/entropy_dialog.py`
  (QPainter-Diagramm nach den Visualisierungsregeln: eine Serie, eine Achse, 2-px-Linie, Raster zurückhaltend,
  Schwelle gestrichelt, Bänder mit Legende, Fadenkreuz-Hover, Bereichsliste als Tabellenansicht). 64 MB: 1,5 s.
- Build-Größe: keine neuen Abhängigkeiten (bz2/lzma/zlib aus der Standardbibliothek), build.py unverändert → kein
  Build-Check; Stand wie nach 1.6.0 (Windows ≈ 96,7 MB, Linux ≈ 92,6 MB).
- Screenshots 50–53 (Hex mit Werte-Zeile + Kopiermenü, Strings, Eingebettete Dateien, Entropie).

### 1.9.0 – Block H
- Vorab (Rückfrage des Besitzers „wie benutze ich die Tools?“): Binärdateien waren im Baum unsichtbar (nur
  eingestellte Endungen). `core/modules.show_all_files` – Baum zeigt alle Dateien per Schalter `tree_show_all` oder
  automatisch, solange ein Analyse-Modul an ist; MainWindow.apply_tree_filter bei Modulwechsel und aus den Einstellungen.
- **Besitzer (26.09.2026): H, I, J und K ohne Zwischenstopp nacheinander bauen**, Zusammenfassung erst am Ende.
- H4 IOC entschärfen: `core/ioc.py` – Spans in fester Reihenfolge (URL → E-Mail → IPv6 → IPv4 → Domain), keine
  Überlappung; Domain nur mit TLD aus Liste bzw. zwei Buchstaben, mehrdeutige ccTLDs (md, py, sh, so, rs …) erst ab
  drei Teilen, Dateiendungen (exe, txt, pdf, zip …) nie; IPv6/IPv4 per ipaddress geprüft; URL: nur Host entschärft,
  Pfad bleibt; schon Entschärftes wird erkannt. refang per Ersetzungstabelle (auch [dot], (.), {.}, [at], h[xx]p).
  UI: MainWindow._activate_ioc (Bearbeiten → Umwandeln, Kontextmenü-Gruppe, Palette), Einstellung
  `ioc.skip_code`. Nur im Editor-Dokument → .ntx-Regel erfüllt (nichts auf Platte).
- H1 Metadaten: `core/metadata.py`, `ui/metadata_dialog.py`. **Entscheidung Bibliotheken:** Bilder mit eigenem
  Parser (TIFF/EXIF-IFDs mit Grenzen- und Schleifenschutz, JPEG-Segmente per mmap, PNG-Chunks, WebP-RIFF, IPTC-IIM)
  statt Pillow – Pillow kostet ~10 MB und kodiert JPEG beim Speichern neu; so bleibt das Entfernen verlustfrei.
  PDF mit **pypdf 6.19.0** (BSD-3, reines Python, ~1 MB im Build): Info, XMP, Verschlüsselung; beim Entfernen
  `compress_identical_objects(remove_unreferenced=True)` – sonst blieben Info/XMP als verwaiste Objekte in der
  Datei (vom Test gefunden). Office über zipfile/ElementTree (XML > 8 MB oder mit `<!ENTITY` wird nicht geparst).
  JPEG: echtes Bildende über SOS-Scan (Füllbytes FF00, RST, Segmente zwischen Scans) → Daten dahinter (MPF, Trailer)
  werden gemeldet und entfernt; APP0/APP2-ICC/APP14 bleiben. Kopie mit open("xb"), danach verify() (liest die Kopie
  neu). Grenzen: TIFF/HEIC nicht bereinigt; Namen im Office-/PDF-Inhalt bleiben (nur gemeldet).
- H2 YARA: **yara-python 4.5.4** eingebunden – vorab geprüft: Wheels cp312 für win_amd64 und manylinux_2_17 (je
  ~2–3 MB, Linux bündelt libcrypto 1.1 → Lizenz beigelegt), Apache-2.0/BSD-3 → MIT-verträglich; build.py Hidden
  Import + check_dependencies. `core/yara_rules.py` (compile mit include_callback relativ zum Regelordner,
  Fehlerzeile aus „line N“/„(N)“, scan über os.walk ohne Symlinks, Zeitlimit 60 s/Datei, Grenzen 20 000 Stellen,
  200 je String). Lexer „yara“ aus Pygments (C-artige Blockkommentare), Config-Migration extensions_version 5
  (.yar/.yara in Baum + Syntax). `ui/yara_dialog.py`, MainWindow._activate_yara/test_yara/mark_yara_error
  (Editor.set_problem, gelöscht beim nächsten Tippen). FileTree.folder_menu_providers (neu, für Ordner).
  Vorlagen: `LATER_TEMPLATES` + config templates.installed – neue Standardvorlagen einmalig in alte Ordner.
- H3 Zeitleiste & Beweismittel: **Format-Entscheidung** Markdown + Frontmatter `notex: zeitleiste` + Tabelle
  (statt eigenem Format): lesbar in Vorschau/anderen Editoren, diffbar im Verlauf, Pipes als `\|` maskiert. Zeiten
  ISO 8601 mit Offset; keine IANA-Namen (Windows-Python ohne tzdata hat keine Zonen-DB) – Anzeige UTC / Systemzeit /
  wie gespeichert. `core/timeline.py` (parse, add_entry chronologisch vor dem ersten späteren Eintrag,
  detect_timestamp für ISO/CLF/deutsch/US/syslog/Datum/Epoch mit Falsch-Positiv-Tests, Export MD/CSV, append_row für
  Beweismittel-Tabellen, find_timelines liest je .md max. 4 KB). .ntx-Regel: `can_take_from` sperrt die Übernahme aus
  .ntx (Aktion ausgegraut). UI `ui/timeline_dialog.py`; Einfügen in offene Zeitleiste über den Editor (Undo), sonst
  atomar in die Datei mit Original-Encoding/Zeilenenden. Vorlagen `Zeitleiste.md`, `Beweismittel.md` (LATER_TEMPLATES).

- Screenshots 54–57 (Metadaten, YARA, Zeitleiste, IOC entschärft).
- Build-Größe (CI-Build-Check, Artefakt-ZIP) nach H mit pypdf + yara-python: Windows ≈ 99,9 MB (vorher 96,7),
  Linux ≈ 96,7 MB (vorher 92,6). Block I bringt keine Abhängigkeiten, nur ~150 KB Portdaten.

### 1.10.0 – Block I
- I1 Port-Infos: `core/ports.py`, Daten `assets/ports/iana-ports.tsv.gz` (11 721 Einträge, 149 KB, Bereiche als
  start–ende), erzeugt mit `tools/update_ports.py` (reproduzierbares gzip, mtime=0). **Quelle:** iana.org ist in der
  Arbeitsumgebung per Netzwerk-Policy gesperrt → CSV von einem GitHub-Spiegel (HackBugs/Computer-Networking,
  neuester Eintrag 2024-10-08, Stichproben gegen bekannte Einträge geprüft); Lizenz: IANA/IETF-Erklärung 2021 „frei
  für jeden Zweck“. Beim nächsten Lauf mit Netz `python tools/update_ports.py` direkt von iana.org. Eigene Tabelle
  COMMON (~85 Dienste, Hinweise auf Deutsch) + ALIASES. Erkennung nur mit Kontext (Port-Wort, Liste nach „Ports“,
  Host:Port mit IP/Domain/localhost/[IPv6], n/tcp, tcp/n, nmap), Falsch-Positiv-Tests (Jahr, Betrag, Uhrzeit,
  Version, Pfad, Rechnungsnr., 16:9). `Editor.hover_providers` (neu, klassenweit) – Tooltip nur, wenn die Maus
  wirklich auf der Zeile steht; gesperrte .ntx nie. `ui/ports_dialog.py`.
- I2 IP-Konflikte: `core/ipmap.py` (extract je Zeile: Tabellen mit IP-/Namensspalte, hosts-Stil, „Name: IP“ mit
  Rollen-Ausschluss; conflicts mit Kurzname-Vergleich; group /24 bzw. /64; usage mit Ausschlussbereichen
  „a-b“, „a-Endoktett“, CIDR, Einzel-IP; IpIndex inkrementell über (mtime, Größe), nur .md/.txt → .ntx nie gelesen,
  auch nicht aus offenen Editoren). UI `ui/ip_dialog.py`; Abgleich im AnalysisWorker auf einer Kopie des Index,
  Übernahme im UI-Thread. Editor: `set_module_marks` (neu, je Modul eine Gruppe welliger Unterstreichungen).
  „File-Watcher“ = file_saved/file_opened/status_changed der Tabs + inkrementeller Ordnerabgleich beim Öffnen der
  Übersicht bzw. „Aktualisieren“ (Qt-Watcher auf ganzen Bäumen ist unter Windows unzuverlässig und teuer).
  Konflikte werden mit Warn-Icon markiert, weil das Stylesheet Baum-Textfarben festlegt.
- I3 RDAP/ASN: `core/rdap.py` (classify inkl. entschärfter Werte, local_reason – reserviert VOR privat prüfen, weil
  Python 240.0.0.0/4 als „private“ führt; Bootstrap mit längstem Präfix und https bevorzugt; parse_ip/autnum/domain
  inkl. verschachtelter Entities (Abuse unter Registrant), cidr0 oder summarize_address_range; Client mit injizierbarem
  fetch/sleep/clock → Tests ohne Netz, Cache je URL nur im Speicher, 1 s je Host, 429 + Retry-After (> 30 s → Meldung)).
  **Entscheidung ASN-Quelle: RIPEstat prefix-overview** (frei, ohne Schlüssel, weltweit aus RIS-BGP-Daten, JSON über
  HTTPS) statt Team Cymru (DNS-TXT – bräuchte eine DNS-Bibliothek) oder ipinfo/ipapi (Schlüssel/Limits/Lizenz).
  `ui/rdap_dialog.py` (QThread; beim Schließen wird nicht gewartet, der Thread hängt sich ans Fenster und räumt sich
  weg). Kontextmenü zeigt private IPs ausgegraut mit Grund; .ntx → Rückfrage vor dem Senden.
- Screenshots 58–60 (IP-Übersicht, Port nachschlagen, RDAP-Karte).
- Screenshot 61 (Netzwerk-Scanner mit Beispieldaten).

### 1.11.0 – Block J
- J1 Scan-Engine `core/scan.py`: asyncio TCP-Connect (Connector injizierbar → Tests ohne Netz), Semaphore für
  Parallelität, Host-Semaphore begrenzt gleichzeitige Hosts; parse_targets (IP/Name/CIDR/Bereich/Liste, dedupe,
  Obergrenze), parse_ports (Profile top100/top1000, Listen/Bereiche), Banner (HTTP-Probe + Gruß-Dienste),
  Host-Erkennung per TCP-Knock, optional System-ping über Executor; ping_alive und parse_arp robust gegen DE/EN und
  Linux/Windows/macOS. to_dict/load, Markdown-Report, compare (neue/weg, offen/zu, Banner), as_ip_note.
- **Umgebung: kein ping/arp, TCP nach außen wird vom Agent-Proxy abgefangen** → alle Netzpfade injizierbar, Tests
  nutzen Fake-Reader/Writer; im Smoke-Test asyncio.open_connection gepatcht.
- J2 UI `ui/scan_dialog.py`: ScanThread(QThread) trägt asyncio.run, Signale host_found/progress/finished/failed;
  Tabelle live, Abbrechen, Speichern (JSON+MD in data/scans/), Vergleich, „An IP-Übersicht geben“
  (ip_index.extra["scan"]), Skript-Export-Dialog. Bestätigung bei öffentlichen Zielen (merkbar „nicht mehr fragen“).
- J3 `core/scan_export.py`: PowerShell (TcpClient, ExecutionPolicy-Hinweis) und Bash (/dev/tcp, timeout, ping),
  gleiche Ziele/Ports, CSV. Test: bash -n immer, PowerShell-Parser wenn pwsh da (auf CI-Ubuntu/Windows vorhanden).
- Keine neue Python-Abhängigkeit (nur Standardbibliothek) → Build unverändert.
### 1.12.0 – Block K
- K1 Log-Auswertung `core/logauth.py`: Linux-Syslog-Parser (prog-Kontext, da _SYSLOG den „prog:“-Präfix abtrennt;
  Regeln für sshd/sudo/su/useradd/userdel/usermod/passwd, rotierte .gz per gzip-Stream) und Windows-.evtx über das
  Paket **evtx** (Rust, MIT, abi3-Wheels Win/Linux ~1 MB). **Entscheidung gegen python-evtx**: dessen Dep `hexdump`
  hat eine kaputte setup.py (baut auf neuem setuptools nicht) → in beiden Builds unsicher. Event-ID-Zuordnung als
  reine Funktion auf dem Event-XML (parse_evtx_xml), ohne Bibliothek testbar. analyze() Dashboard (Fehlversuche
  je IP/User, Erfolg-nach-Fehlversuch, Brute-Force, neue User/Gruppen/Dienste, log_cleared, lockouts, Stunden-
  Zeitleiste). `ui/logauth_dialog.py` mit QPainter-Zeitleiste; MainWindow.add_prepared_timeline_entry verbindet die
  Log-Zeile mit Modul H3. requirements/build/CI/Lizenzen: evtx 0.13.1, dpkt 1.9.8.
- K2 PCAP-Übersicht `core/pcapinfo.py` mit **dpkt** (BSD, nicht scapy=GPL): Format-Erkennung (pcap/pcapng-Magic),
  Streaming mit Fortschritt, robust gegen kaputte Records (überspringen und zählen). Datalink 1/101/113 behandelt.
  Protokolle, Talker, Conversations, DNS (dpkt.dns), HTTP (dpkt.http.Request → Host/Pfad/UA + Basic-Auth),
  eigener TLS-ClientHello-SNI-Parser (SNI als UTF-8, nicht idna – idna kennt kein errors="ignore"), Klartext-
  Zugangsdaten (FTP/Telnet/POP3/IMAP/SMTP-AUTH per Zeilen-Heuristik, IMAP-Tag beachtet). Tests mit selbst gebauten
  pcaps (dpkt.pcap.Writer). `ui/pcap_dialog.py` (sortierbare Tabellen, Zugangsdaten rot, RDAP je IP).
  ANALYSIS_MODULES um logs/pcap erweitert → Baum zeigt .evtx/.pcap, solange das Modul an ist.
- Screenshots 62–63 (Log-Auswertung, PCAP-Übersicht).
- Build-Größe nach K (Build-Check-Artefakte, commit c8b5445): Windows ≈ 104,3 MB, Linux ≈ 101,8 MB (vorher nach H ≈ 99,9 / 96,7 MB; + evtx-Rust-Wheel und dpkt). CI Tests + Build-Check grün auf Win+Linux.
- Fix: dpkt fehlte zunächst in requirements.txt (nur in build.py/CI/Lizenzen) → Build-Check rot; mit c8b5445 ergänzt, danach grün.
### 1.12.1 – Block L (Fehlerbehebung)
- L1 Scanner-Hang: `_reverse_dns` → `run_in_executor` mit `resolve_timeout` (Std. 2 s) + Sitzungs-Cache; gemeinsamer
  `_close_writer` schließt Verbindungen immer mit Timeout (auch in `_discover`); `scan_host` prüft `cancelled` je Probe.
  Tests: langsamer Resolver (parallel, < 4 s statt 6 s seriell), nie zurückkehrender Resolver/Writer, Abbruch mitten
  in den Probes.
- L2 Encoding-Menü: `EditorToolbar` – Überlaufmenü wird lazy in `aboutToShow` gebaut (`_build_overflow_menu`),
  `_relayout` merkt nur die versteckten Gruppen und wird über `QTimer.singleShot(0)` entkoppelt; Encoding-/EOL-
  Optionen als Datenkonstanten → jedes Menü baut eigene QActions (keine geteilten mehr). Regressionstest.
- L3 Metadaten JPEG: `read()` liefert immer Datei/Format/Größe; `_read_jpeg` parst SOF (Maße, Verfahren, Komponenten),
  JFIF, ICC (mit Beschreibung), Adobe, DQT→geschätzte Qualität, Vorschaubild, Segmentliste; „Keine EXIF/XMP/IPTC“-
  Hinweis, generisch auch für PNG/WebP/PDF/Office. Tests: ohne EXIF, progressiv, mit ICC, .JPG-Großschreibung.
- L4 PCAP neu: `core/pcapinfo.py` komplett überarbeitet (Protokoll-Hierarchie, Hosts/Rollen, ARP+Spoofing-Befund,
  ICMP-Echo-RTT, DNS-Paarung, TCP-Status/Bytes/Retransmissions + `stream()`, HTTP req+resp, TLS, Dienste, Befunde).
  **Fixture selbst erzeugt** (`tools/make_fixture_pcap.py` → `tests/fixtures/beispiel_traffic.pcap`, 13 Pakete/958 B),
  Sollwerte per Test festgeschrieben. `ui/pcap_dialog.py` mit Reitern und „Stream folgen“ (Text/Hex).
- Screenshot 63 (PCAP) auf die neue Auswertung aktualisiert.

### 1.13.0 – Block M
- **Besitzer-Wunsch beim App-Icon:** Variante A (Notizblatt) gewählt, ergänzt um einen Terminal-Prompt `>_` im Akzent.
- M1 Werkzeuge: `core/tools.py` – zentrale, Qt-freie Registry (Tool = command/name/category/module/kinds/needs_file/
  shortcut/icon/description); `file_kind`, `applies`, `grouped`, `enabled_modules`. Menü „Werkzeuge“ in der Menüleiste
  (aboutToShow baut aus der Registry, Kategorien als Untermenüs, nicht passende ausgegraut, Module aus = weg),
  Werkzeug-Übersicht (`ui/tool_overview.py`, `Ctrl+Shift+W`), „Werkzeuge“-Button in der Blatt-Leiste (Hook
  `tools_menu_builder` über EditorArea/EditorTabs/Toolbar), Baum-Kontextmenü. Analyse-/Netzwerk-/Log-Einträge nur noch
  im Werkzeuge-Menü (nicht mehr doppelt im Datei-Menü); Kürzel bleiben über die window-weiten QActions.
- M2 Explorer-Orte: `core/places.py` (Qt-frei) – Notizen/Schnellzugriff/Dieser PC, Laufwerke plattformabhängig
  (Windows-Buchstaben, Unix `/` + `/media`,`/mnt`,`/run/media`,`/Volumes`), `is_system_path` (konservativ),
  `add/remove/is_pinned`. `ui/places_panel.py` (QTreeWidget) über dem Baum (Splitter). `FileTree` re-rootbar
  (`set_root`, `set_hidden`, `_guard_write` warnt außerhalb der Notizen, in Systemordnern deutlich); Persistenz des
  Aufklapp-Zustands bleibt für data/ erhalten. Config: `tree_show_hidden`, `quick_access`.
- M3 Neu nach Typ: `core/newfile.py` (Qt-frei) – Typen mit Startinhalt + Cursor-Marker, `build_content`/`encode_content`
  mit Zeilenende LF/CRLF (Config `new_file_eol`). Untermenü im Datei- und Baum-Kontextmenü, je Typ Palette-Befehl;
  Datei wird als Bytes geschrieben (Zeilenende exakt), Cursor springt an die Marke. Öffnen wählt die Ansicht weiter
  über `filetype.detect` (Text/Hex/Bild/PDF/CSV …).
- M4 App-Icon: `assets/notex.svg` ersetzt (Notizblatt mit `>_`), `tools/make_icon.py` erzeugt `notex.png` (256) und
  `notex.ico` (7 Größen); drei Entwürfe liegen in `docs/icon-varianten/`. Fenster-Icon, Leeransicht, Linux-Desktop
  und Windows-Build nutzen dieselbe Quelle.
- M5 Export: `core/export.py` (Qt-frei) baut HTML (Markdown gerendert, CSV als Tabelle, sonst `<pre>`; Variablen
  aufgelöst; Kopf mit Logo/Titel/Meta, Fußzeile, Druck-CSS). `ui/export_service.py` – HTML schreiben; PDF über
  QPdfWriter + QTextDocument seitenweise, Kopf/Fuß/Logo je Seite mit QPainter. **Wichtig:** QTextDocument rechnet in
  96 dpi, der PDF-Maler in Geräte-dpi → Maler beim Zeichnen des Körpers um `resolution/96` skalieren, sonst wird der
  Text winzig. .ntx nur nach Rückfrage.
- M6 Allgemeine Logs (Wunsch des Besitzers „jede Log auswerten“): `core/loggeneric.py` (Qt-frei) – je Zeile
  Zeitstempel (über `timeline.detect_timestamp`), Stufe (ERROR/WARN/INFO/DEBUG, deutsch+englisch, in `[..]`/`:`),
  Quelle (`[name]`, `prog[pid]`, `name:`), Meldung; `template()` verdichtet Zahlen/Pfade/IDs zu Mustern.
  `analyze_generic` → Stufen, Fehler/Warnungen, häufigste Muster, aktivste Quellen, Zeitspanne, Stunden-Zeitleiste.
  `ui/loggeneric_dialog.py` (Filter, Tabelle, Diagramm, Report). `logauth.looks_like_auth` wählt automatisch zwischen
  Sicherheits-Dashboard und allgemeiner Auswertung; Palette-Befehl erzwingt die allgemeine Sicht.
- Neue Qt-freie Tests: `test_tools`, `test_places`, `test_newfile`, `test_export`, `test_loggeneric` und Ergänzungen
  in `test_logauth`. Keine neuen Abhängigkeiten (QtPdf war ab Block F im Build). Alle Tests grün (offscreen).

### 1.14.0 – Block Q
- Q1 Erkennung: `core/detect.py` (Qt-frei) – `analyze(text)` liefert alle plausiblen Typen mit Konfidenz
  (IPv4/IPv6/CIDR/MAC/Domain/URL/E-Mail/Port, Hashes nach Länge+Präfix, Base64/Base32/Hex-Blob, JWT, Unix-Zeit,
  ISO-Datum, Zahl, Hex-Farbe, CVE, ATT&CK, User-Agent). Bewusst konservativ (Satz != Base64, Jahr != Port,
  gültige Oktette). `token_at` für „nichts markiert". 16 Tests.
- Q2 Menü: `ui/analyze_actions.py::AnalyzeController.menu_provider` hängt die Gruppe „Analysieren" ins Editor-
  Kontextmenü (über `_editor_menu_providers`), nur passende Aktionen, modul-gated (sonst „… – Modul aktivieren"),
  „Erkennen …" + Palette-Befehle `analyze:*`.
- Q3 Netzwerk: DNS (socket A/AAAA/PTR – MX/TXT bräuchten eine DNS-Lib, nicht im Build), Ping/Ports über `core/scan`,
  Port-Info über `core/ports`; RDAP/IP-Übersicht/Scanner rufen die vorhandenen Fenster. Alles im Worker-Thread.
- Q4 Hash-Info: `core/hashlookup.py` (Qt-frei, Netz injizierbar) – **Nitrxgen MD5-Datenbank** (frei, ohne Schlüssel).
  **Entscheidung:** nur MD5 hat einen freien, schlüssellosen Klartext-Dienst → SHA-1/256/NTLM-Knopf deaktiviert mit
  Begründung; gesalzene Formate ebenso. Datenschutz-Rückfrage, Einstellung `analysis.hash_online` (Settings-Seite
  „Analyse"), .ntx sperrt den Lookup. „Hash dieses Worts bilden" lokal (NTLM = MD4(UTF-16LE), eigenes MD4 in
  `core/convert.py`, da OpenSSL 3 oft kein md4 hat). Hash klar von Verschlüsselung getrennt (UI + Doku). Keine
  Wortlisten/Rainbow-Tables (Begründung in der Doku).
- Q5 Umwandeln: `core/convert.py` (Qt-frei) – Base64/Base32/Hex/URL, JWT (Signatur ungeprüft), Zeitstempel, Zahl in
  Basen, Hex-Farbe, User-Agent. Ergebnisse in der Karte (`ui/analysis_card.py`, Popover, wiederverwendbar), „Als Notiz
  einfügen".
- Q6 Doku: README-Abschnitt „Analyse per Rechtsklick" (Tabelle Typ→Aktionen, Hash≠Verschlüsselung), CHANGELOG,
  THIRD_PARTY_LICENSES (Online-Dienste inkl. Nitrxgen). Screenshot 67.
- Neue Qt-freie Tests: `test_detect` (16), `test_convert` (10), `test_hashlookup` (9). Keine neuen Abhängigkeiten.

### 1.15.0 – Block N
- N1 Erkennung (Qt-frei): `core/oui.py` – MAC→Hersteller aus den öffentlichen **IEEE-MAC-Blöcken**
  (`assets/oui/oui.tsv.gz`, 38.930 Einträge; `tools/update_oui.py` lädt bevorzugt die IEEE-CSV, sonst aus einem
  erreichbaren Spiegel NUR die Fakten – **nicht** Wiresharks GPL-`manuf`). Erkennt lokal verwaltete/Multicast-MACs.
  `core/netdetect.py` – eigene Subnetze aus `ip addr`/`ipconfig`, Ausschlusslisten, NetBIOS-Namensabfrage (NBSTAT
  Bau+Parse), Wake-on-LAN-Paket. Tests: `test_oui` (6), `test_netdetect` (7).
- N2/N3 UI: `ui/network_scanner.py::NetworkScannerDialog` – Live-Tabelle (Status/Name/IP/MAC/Hersteller/Kommentar/
  Dienste/ms), Profile Schnell/Standard/Gründlich, Ausschluss, Filter, Spalten ein-/ausblendbar + Breiten gespeichert.
  Anreicherung im Worker (ARP-MAC, OUI, NetBIOS, Antwortzeit per TCP-Connect). Host-Aktionen: Browser/RDP/Freigabe/
  SSH/Ping/Traceroute/Ports vertiefen/RDAP/Wake-on-LAN/Remote-Shutdown+Neustart (Windows, Bestätigung)/Kommentar/
  Favoriten/Kopieren/an IP-Übersicht. Export CSV/JSON/Markdown/HTML/PDF. `scan:open` = Geräte-Scanner,
  `scan:ports` = alter Port-Scan. Reverse-DNS/Ping/Ports teilen die Logik mit Block Q (core/scan).
- **Entscheidung OUI-Quelle:** IEEE-Registry (frei, reine Fakten – wie IANA-Ports). standards-oui.ieee.org war in der
  Umgebung gesperrt; Fakten aus einem Spiegel extrahiert. Wiresharks `manuf` (GPL) bewusst gemieden.
- **Zurückgestellt/vereinfacht (ehrlich):** mDNS/LLMNR-Namensabfrage und SMB-Freigaben-Auflistung sind noch nicht
  umgesetzt (nur Reverse-DNS + NetBIOS; Freigaben werden über den Datei-Manager geöffnet, nicht aufgelistet);
  „unbekannte Hersteller ausblenden" und feine Geschwindigkeits-Regler (Timeout/Retries) fehlen noch – Profile decken
  das Wesentliche ab.
- Screenshot 68 (Geräte-Scanner). Keine neuen Python-Abhängigkeiten (nur Standardbibliothek + vorhandene Engine).

### 1.16.0 – Block O
- O0 WYSIWYG: `core/richmd.py` (Qt-frei) – Markdown ↔ Blockmodell mit stabilem, idempotentem Roundtrip (Überschriften,
  Absätze, Listen/Aufgaben, Zitate, Codeblöcke, Tabellen, Trennlinien; Inline fett/kursiv/durchgestrichen/Code/Link);
  Variablen bleiben erhalten. `ui/rich_markdown.py`: RichMarkdownEditor (QTextEdit) + Symbolleiste/Kürzel +
  „Formatiert | Quelltext"-Umschalter; RichMarkdownDialog + Befehl „Formatiert bearbeiten" (nur .md, nicht .ntx).
  **Entscheidung:** eigenes Blockmodell statt Qt-`toHtml`-Roundtrip (deterministisch, Qt-frei testbar). Tabellen/Code
  werden formatiert gezeigt, Feinarbeit über Quelltext.
- O1 Engine: `core/questionnaire.py` (Qt-frei) – YAML-Fragebögen, Typen, Bedingungen (`when`), Pflicht, Gewichtung,
  Auswertung (`score`/`score_summary`, Ampel), Ausgabe (`output`-Vorlage `{{id}}` + `§`-Variablen), Antworten im
  Frontmatter (`parse_answers`). `ui/questionnaire_dialog.py`: Assistent (ein Abschnitt/Seite, Chips, Zwischenstand).
  Ergebnis → formatierte Notiz, öffnet im WYSIWYG-Editor; bewertete Fragebögen bekommen die Auswertung vorangestellt.
- O2 Berichtsheft: `berichtsheft.yaml` + **ICS-Import** `core/ics.py` (Qt-frei, RFC 5545, keine neue Abhängigkeit:
  VEVENT/DTSTART/DTEND/SUMMARY, ganztägig, RRULE DAILY/WEEKLY+INTERVAL/COUNT/UNTIL/BYDAY, EXDATE, CLASS:PRIVATE
  übersprungen; `berichtsheft_rows` fasst eine ISO-Woche zusammen). Befehl „Berichtsheft aus Kalender (.ics)".
- O3 Systemcheck: `systemcheck.yaml`. O6 Sicherheits-Check: `sicherheits-check.yaml` mit gewichteten yesno-Fragen +
  Auswertung (eigene Formulierungen, an DIN SPEC 27076 / BSI IT-Grundschutz angelehnt).
- O4/O5: E-Mail-Vorlagen (Betreff als erste Zeile, ohne Grußformel/Signatur) und Tabellen-Vorlagen (CSV/Markdown,
  Benutzerlisten ohne Passwortspalte) in `core/templates.py`; `.csv` als Vorlagen-Endung ergänzt.
- **Vereinfacht/ehrlich:** der WYSIWYG-Editor ist ein eigenes Fenster (kein neuer Tab-Modus, um den bestehenden Editor
  nicht zu gefährden); TZID im ICS wird als lokale Zeit behandelt (keine Zonen-DB); der „Frage-Antwort Tag-für-Tag"-
  Modus des Berichtshefts ist über Tabelle + Vorschlags-Chips + ICS-Vorbefüllung abgedeckt, kein eigener Dialog.
- Neue Qt-freie Tests: `test_richmd` (11), `test_questionnaire` (10), `test_ics` (6). Keine neuen Python-Abhängigkeiten.

### Plan R (Fehlerbehebung + Aufräumen, ab 29.09.2026)
- **R1 Netzwerk-Tools + totes Werkzeuge-Menü – erledigt.** Diagnose per Offscreen-Szenarien (20 Zustände):
  0) gemeinsame Ursache: `--windowed`-Build ohne Exception-Hook → jeder Slot-Fehler lautlos. Neu `core/errorlog.py`
     + `ui/error_hook.py` (sys/threading.excepthook → `logs/fehlerprotokoll.log` + gedrosselter Toast).
  1) Windows-Konsolenausgabe ist OEM (cp850), `text=True` las cp1252 → UnicodeDecodeError bei jedem deutschen Ping.
     Neu `core/syscmd.py` (Bytes lesen, OEM dekodieren, errors=replace); Scanner-Ping im `JobThread`.
  2) Traceroute: `scan.traceroute()` + Textfenster statt Popen ohne Ausgabe.
  3) Split View: Leisten-Knöpfe sind NoFocus → aktive Gruppe blieb die andere → Menü/Leiste wirkten auf deren Datei.
     EditorArea-Eventfilter (MouseButtonPress) + Leiste aktiviert ihre Gruppe beim Menü-Öffnen.
  4) `_build_tools_menu`: Untermenüs per deleteLater (Leck), Einträge einzeln abgesichert (ein Fehler leerte das Menü).
  5) Toasts statt stummer Rückkehr (`show_ip_overview`, unbekanntes Werkzeug).
  Tests: `test_errorlog`, `test_syscmd`, `test_network_ui`, `test_ui_smoke` (echtes Hauptfenster offscreen).
  **Nicht reproduzierbar unter Linux:** ein totes Menü ohne Split View – wäre jetzt als Hinweis + Logeintrag sichtbar.
- **R2 Vorsichtig aufräumen – erledigt** (Besitzer: ohne Kandidatenliste, selbstständig). Werkzeuge: ruff (F-Regeln),
  vulture, AST-Duplikatsuche, Referenzsuche für docs/assets. Entfernt: ungenutzte Imports (32 + 4 in Tests),
  platzhalterlose f-Strings, ungenutzte lokale Variablen, 12 nie referenzierte Helfer/Konstanten, ein toter
  `if False`-Zweig (Link-Ziel anlegen). **Bewusst liegen gelassen:** Qt-Overrides (von vulture fälschlich gemeldet),
  `convert.encode_hex` (symmetrisches Set), `crypto_notes.SUFFIX`/`grammar.PUBLIC_API` (dokumentieren Format/URL),
  `register_command` (Erweiterungs-Haken), `spelling_page`/`_footer` (Referenzen gegen GC), 1–3-zeilige gleichnamige
  Privat-Helfer (`_cell`, `_muted`, `_alpha`, `_pad` – Zusammenlegen brächte nur Kopplung), 46 nicht direkt
  referenzierte Icons (~16 KB, Namen teils dynamisch), Screenshots (von tools/screenshot.py erzeugt),
  docs/icon-varianten (Entscheidungsgrundlage M4). Kein Verhalten geändert, alle Tests grün.
- **R3 Netzwerk-Werkzeuge testen – erledigt.** Gemeinsame UI-Fixture (`tests/conftest.py` `win`, `tests/uihelp.py`).
  `test_network_tools_ui.py`: Menü → jedes Netzwerk-Werkzeug öffnet ein Fenster; Port-Infos; IP-Übersicht mit
  Konflikt; RDAP (Fake-Client, private IP nie abgefragt); PCAP gegen Fixture; Geräte-Scanner + Port-Scan per echtem
  TCP-Connect gegen Listener auf 127.0.0.1; Q-Aktionen DNS (localhost)/Ping/Ports + Analysieren-Menü.
  `test_ui_smoke.py`: 6 Szenarien des Ursprungsproblems. **CI:** installiert requirements.txt inkl. PySide6
  (Linux: libegl1/libgl1/libxkbcommon0/libfontconfig1/libdbus-1-3/libenchant-2-2), `QT_QPA_PLATFORM=offscreen`.
  **Dabei gefundene Fehler (behoben, mit Regressionstest):** Geräte-Scanner-Start entpackte `parse_targets`
  (Ziele, Warnungen) nicht → AttributeError, „Scannen tut nichts“; `refresh_ip_index` verwarf Anforderungen während
  eines laufenden Abgleichs. Manuelle Checkliste: `docs/TESTPLAN-WINDOWS.md` (Abschnitte A–F).
- **R4a Vorlagen nach Kategorien – erledigt.** `core/template_catalog.py` (Qt-frei): Kategorie je Vorlage
  (Unterordner > `category:` im Fragebogen-YAML / feste Zuordnung `BUILTIN_CATEGORY` > Präfix `E-Mail-`/`Tabelle-` >
  „Sonstiges“), Reihenfolge Ausbildung, Kunde/Einsatz, E-Mail, Tabellen, Planung & Notizen, Sicherheit & Forensik,
  eigene (alphabetisch), Sonstiges; Titel alphabetisch mit Umlaut-Faltung; Suche = alle Wörter in Titel/Kategorie/
  Dateiname. `ui/template_picker.py` ersetzt das Dropdown in „Neue Datei aus Vorlage“; Fragebögen stehen mit in der
  Liste (Berichtsheft unter „Ausbildung“) und starten den Assistenten. **Entscheidung:** Kategorie wird berechnet,
  nie Dateien verschoben (nichts geht verloren, eigene Ordnung per Unterordner). **Gefundener Fehler:** wurde
  `templates/fragebogen/` vor `templates/` angelegt, kamen die Standardvorlagen nie → Reihenfolge in
  `questionnaires_folder()` + Erststart-Erkennung in `ensure_defaults` (gelöschte bleiben gelöscht).
- **R4b Module alle an/aus – erledigt.** `ModuleRegistry.set_all/summary/enabled_count`; Einstellungen → Module:
  Tri-State „Alle Module“ + Knöpfe + Zähler (Einzelschalter werden mit blockSignals nachgezogen, kein Doppel-
  Schalten); Palette `modules:all_on/all_off`. Persistenz über Config-Autosave, Abbrechen über den Snapshot.
- Test-Infrastruktur: `close_window` führt `deleteLater` aus (Suite 86 s → 23 s; alte Fenster samt App-Filtern
  sammelten sich an).

### Umbenennung (29.09.2026, Besitzer)
- „Notex“ ist geschützt → **Anzeigename „fckNotes“**; der Besitzer hat am 30.09.2026 auch das GitHub-Repo in
  `CustomCock/fckNotes` umbenannt (GitHub leitet die alte Adresse weiter). `REPO`/`REPO_URL` in `notex/__init__.py`.
- **Entscheidung:** nur der Anzeigename wechselt. `notex/__init__.py`: `APP_NAME` (sichtbar), `EXE_NAME`/`EXE_FILE`
  (Build, Texte), dazu **stabile interne Kennungen** `APP_ID`, `PROG_ID`, `REG_KEY = "Notex"` (Registry) und
  `LEGACY_EXE_FILES` (alter „Öffnen mit“-Eintrag wird beim Registrieren/Entfernen aufgeräumt). Alle sichtbaren
  Texte lesen `APP_NAME`/`EXE_FILE` (55 Literale umgestellt); `build.py` und `release.yml` holen den Namen aus dem
  Paket. **Nie ändern:** `.ntx`-Magic `NOTEXENC`, Paketname `notex/`, `REPO` im Update-Check, Scan-JSON-Schlüssel
  `notex_scan`, Linux-Desktop-ID `notex.desktop`, Env `NOTEX_ROOT`.
- Nächster Namenswechsel: `APP_NAME` ändern, README/CHANGELOG-Titel anpassen, Screenshots neu erzeugen.
  Screenshots 01–63 am 30.09.2026 mit `python tools/screenshot.py` neu erzeugt (Demo-Daten mit neuem Namen,
  „Dieser PC“ im Skript fest auf C:\ / D:\ statt der Laufwerke der Build-Umgebung). 64–70 stammen aus einmaligen
  Skripten und enthalten keinen App-Namen – unverändert.

### Mermaid-Diagramme (30.09.2026, Besitzer: „soll Mermaid anzeigen können“)
- Vorher: nicht vorhanden (```mermaid wurde als Codeblock gezeigt). Jetzt: `notex/core/mermaid/` (Qt-frei) –
  `render(source, colors) → Diagram(svg, width, height)`, `render_safe` wirft nie (Fehlerbox mit Zeilennummer).
  Parser je Typ (`flowchart`, `sequence`, `classdiagram`, `state`, `er`, `pie`, `gantt`), gemeinsames
  Sugiyama-Layout `layout.py` (Zyklen brechen, Ränge mit Label-Dummies, Baryzentrum-Sortierung, Cluster rekursiv
  mit eigener Richtung, Kanten dürfen an Cluster andocken), `svg.py` (Theme aus den Vorschaufarben, Textbreiten-
  Tabelle, Pfeilspitzen als Polygone – Qts SVG-Tiny kennt kein `<marker>`), `examples.py` (Palette).
- Einbindung: `markdown.render_fence` → `<img src="notex-mermaid:<sha1>">` + `RenderResult.diagrams`;
  Vorschau liefert das Bild über `loadResource` (`ui/diagram_image.svg_to_image`, HiDPI), rendert bei
  Breitenänderung neu; HTML-Export bettet `data:image/svg+xml;base64` ein, PDF-Export legt die Bilder (3×) als
  `QTextDocument`-Ressourcen an. Rechtsklick → PNG/SVG speichern (.ntx nur nach Rückfrage). Palette
  `md:mermaid`, Config `preview_mermaid` (Standard an).
- Tests: `tests/test_mermaid.py` (53, Qt-frei: Parser, Layout ohne Überlappung/Cluster-Einschluss, SVG
  wohlgeformt und ohne script/foreignObject/href/url(), Fehler, Limits, Markdown/Export), `tests/test_mermaid_ui.py`
  (Vorschau-Bild, PNG/SVG, PDF mit Bild, Einstellung, Palette, .ntx-Rückfrage).

## Offen

### Block C – 1.3.0

### Block D – 1.4.0

### Bekannte Einschränkungen (nicht geplant zu ändern, außer angegeben)
- Syntax-Highlighting ab 2 MB pro Datei aus; 40k-Zeilen-Dateien öffnen in ~1,5 s, Tippen dort ~25 ms/Taste (Qt-intern).
- Unverlinkte Erwähnungen werden synchron gescannt, Grenze 400 Dateien.
- Dateiindex: Baum-Signale + 60-s-Intervall, externe Änderungen erscheinen in Ctrl+P mit Verzug.
- Grammatik braucht einen LanguageTool-Server. Kontextmenü unter Windows 11 nur im klassischen Menü.
- Windows-spezifische Teile (Registry, DWM-Titelleiste, EXE-Build) sind in der Linux-Entwicklungsumgebung nur per Fake-Registry testbar.
- Vorschau: Qt-Rich-Text statt Browser (Teilmenge von CSS), Scroll-Sync proportional statt zeilengenau.
- Mermaid: eigenes Layout, nicht pixelgleich zu mermaid.js; eine Kante von außen zu einem inneren Knoten eines Subgraphen kann einen Nachbarknoten kreuzen. Nicht ausgewertet: click/linkStyle/Icons/`%%{init}%%`-Themes. Weitere Typen (mindmap, gitGraph, journey …) nur als Hinweis.
- Split View: höchstens zwei Gruppen; Tab-Drag startet, wenn der Tab senkrecht aus der Leiste gezogen wird.
- Regex-Timeout gilt pro Zeile (0,25 s), nicht für die ganze Suche.

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
| Markdown-Rendering | **markdown-it-py** (`html=False`) → eigener Token-Renderer → `QTextBrowser`; Links nur http(s)/mailto/#/relativ im Notizordner, Bilder lokal aus dem Notizordner oder extern erst nach Klick; eigene Schemata `notex-open:`/`notex-toggle:`/`notex-load:`/`notex-file:` | kein QtWebEngine (+~100 MB, JS-Angriffsfläche); eigener Renderer statt HTML-Sanitizer, weil nie fremdes HTML durchgereicht wird – bestätigt |
| Split View | EditorArea mit höchstens zwei `EditorTabs`, gleiche Datei = geteiltes `QTextDocument` | ein Dokument heißt ein Undo-Stack und kein Auseinanderlaufen der Inhalte |
| Regex-Timeout | Modul `regex` (Apache-2.0), 0,25 s pro Zeile; Fallback auf `re` ohne Timeout | `re` kennt kein Timeout; Thread-Abbruch würde katastrophales Backtracking nicht stoppen |
| Kryptografie | `cryptography>=44,<52` (Argon2id ab 44): AES-256-GCM, Argon2id m=64 MiB, t=3, **p=4** (RFC 9106, zweite Empfehlung), 16-Byte-Salt, 12-Byte-Nonce neu pro Speichern, kompletter 50-Byte-Header (inkl. Nonce) als AAD; Fallback scrypt N=2^17, r=8, p=1; Lesegrenzen Argon2id ≤ 1 GiB/64 Iterationen, scrypt ≤ 2^22 | keine eigene Kryptografie; Parameter im Header, damit spätere Versionen sie erhöhen können; argon2-cffi unnötig, weil cryptography Argon2id selbst kann |
| Sperren | Schlüssel pro entsperrter Notiz im Speicher (KeyState), Sperren speichert Ungespeichertes verschlüsselt und leert Text + Undo; keine zweite Split-View-Ansicht für .ntx | Klartext nur solange nötig im Speicher; eine Ansicht = ein Ort, der geräumt werden muss |
| Versionsverlauf | eigener Objektspeicher statt Git; zlib + SHA-256-Dedup, IDs statt Pfaden | kein externes Programm, portabel, Umbenennen ohne Kopieren |
| Update-Check | `/releases?per_page=20`, höchste gültige Version, Standard an, 1×/Tag, kein Download | `/releases/latest` würde das versehentliche Release „main“ liefern; Datenschutz: nur die Anfrage selbst |
| Linux-Integration | nur `~/.local/share`, nie Default setzen, Build auf ubuntu-22.04 | Symmetrie zu Windows (HKCU, kein UserChoice); älteres glibc = breitere Lauffähigkeit |
| Vorlagen | eigene Platzhalter-Engine statt Jinja; `{{date+N}}` als Erweiterung | keine Abhängigkeit, Wochenpläne brauchen Tagesversatz |
| Wiktionary-Quelle | Action-API `action=parse&prop=wikitext` für de und en, eigener Parser je Sprache | REST-Definition-API nur für en und ohne Herkunft/IPA; Action-API ist MediaWiki-Kern und auf beiden Wikis gleich |
| Wikipedia-Quelle | REST `page/summary` (+ `redirect=true`), bei 404 `opensearch` → bester Treffer, Begriffsklärung über Wikitext-Bullets | summary liefert Beschreibung/Auszug/Bild kompakt; die Optionen einer Begriffsklärung stehen nur im Seiteninhalt |
| Websuche | nur `QDesktopServices.openUrl`, nie ein Abruf durch Notex | Vorgabe: keine Scraping-/Such-API |
| Mermaid | eigener Renderer in reinem Python → SVG → QSvgRenderer, statt mermaid.js | mermaid.js braucht einen Browser/JS-Engine (QtWebEngine ausgeschlossen, +~100 MB, Angriffsfläche); Node/CLI wäre extern und nicht offline-portabel; keine neue Abhängigkeit |

## Abschluss Blöcke F–K

Der Plan F–K ist vollständig umgesetzt (1.7.0–1.12.0), alle lokal getaggt, CI grün, kein Release (Besitzer entscheidet):

- **F (1.7.0)** Modul-System (an/aus ohne Neustart) + Variablen.
- **G (1.8.0)** Forensik-Basis: Hex-Lücken, Strings, eingebettete Dateien, Entropie.
- **H (1.9.0)** Metadaten (EXIF/GPS, PDF, Office; Entfernen als geprüfte Kopie), YARA (Highlighting + Regel testen),
  Zeitleiste & Beweismittel, IOCs entschärfen.
- **I (1.10.0)** Port-Infos (IANA offline + Hover), IP-Konflikte (Übersicht, Subnetz-Auswertung), RDAP/ASN.
- **J (1.11.0)** Netzwerk-Scanner (TCP-Connect, Banner, ARP-MAC, Report, Vergleich, Skript-Export PS/Bash).
- **K (1.12.0)** Log-Auswertung (auth.log/secure/.gz, Windows-.evtx) und PCAP-Übersicht (dpkt).

Neue Abhängigkeiten (alle MIT-verträglich, kein GPL/QtWebEngine): pypdf (BSD), yara-python (Apache/BSD),
evtx (MIT, Rust-Wheels), dpkt (BSD). regex/PyYAML/cryptography wie bisher. Kein scapy.

15 Module vorhanden: variables, hex, strings, embedded, entropy, metadata, yara, timeline, ioc, ports, ip_conflicts,
rdap, scanner, logs, pcap. Standardmäßig an: variables, hex, ports, ioc.

## Nächster Schritt

**Plan R abgeschlossen und als 1.17.0 veröffentlicht.** Umbenennung = 1.17.1 (Arbeitsbranch, `__version__` =
1.17.1) – wartet auf Merge nach `main` und Tag v1.17.1 durch den Besitzer. Offen beim Besitzer: manuelle Prüfung nach `docs/TESTPLAN-WINDOWS.md`.

**Plan Q → N → O abgeschlossen** (1.14.0 / 1.15.0 / 1.16.0), alle lokal getaggt, CI grün, kein Release (Besitzer).
- **Q (1.14.0)** Kontextmenü-Analyse für markierten Text – **erledigt**.
- **N (1.15.0)** Geräte-Scanner als Ersatz für „Advanced IP Scanner“ – **erledigt**.
- **O (1.16.0)** WYSIWYG-Markdown + Fragebögen/Vorlagen – **erledigt**.

- **P (Inventar/Docusnap-artig) ist ZURÜCKGESTELLT** (Entscheidung Besitzer 27.09.2026): vorerst NICHT bauen.

**Mermaid-Diagramme erledigt** (auf dem Arbeitsbranch, CHANGELOG unter „Unveröffentlicht“). Beim nächsten Release
`__version__` auf 1.18.0 setzen und den CHANGELOG-Abschnitt benennen – sonst meldet die App wieder die alte Nummer.

Keine offenen Blöcke auf Entwicklerseite – auf neue Wünsche des Besitzers warten.

Offen beim Besitzer (unverändert):
1. Release: Branch nach `main` mergen und taggen – der Workflow baut dann Windows-ZIP und Linux-tar.gz.
   (Tags ab v1.2.0 existieren nur lokal in der Arbeitsumgebung.)
2. Aufräumen auf GitHub: Release/Tag „main“ löschen, Repo-Beschreibung „Textdateien“.
