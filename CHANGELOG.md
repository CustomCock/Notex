# Changelog

Alle nennenswerten Änderungen an Notex. Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/).

## [1.10.0] – 2026-09-26

### Hinzugefügt
- Modul Port-Infos (Standard an): Tooltip über Portangaben im Editor (Port 3389, :443, 3389/tcp, tcp/445,
  Portlisten, nmap-Zeilen) mit Dienst, Hinweis und IANA-Einträgen – ohne Treffer auf Jahreszahlen, Beträge oder
  Uhrzeiten; „Port nachschlagen“ (`Ctrl+Alt+P`) nach Nummer oder Name; IANA-Portliste offline mitgeliefert
- Editor: allgemeine Hover-Schnittstelle für Module
- Modul IP-Konflikte: IP-Zuordnungen aus Tabellen und „IP Host“/„Host: IP“ in allen Notizen (ohne .ntx),
  IP-Übersicht nach Subnetz (`Ctrl+Shift+Alt+I`) mit Konflikten, Sprung zur Stelle, Subnetz-Auswertung mit
  Ausschlussbereichen und „Nächste freie IP kopieren“; Konflikte im Editor unterwellt
- Modul RDAP/ASN (nur auf Klick): Karte zu IP, Domain oder AS-Nummer über den IANA-Bootstrap (Netzblock, Inhaber,
  Land, Abuse-Kontakt, Daten; Registrar/Nameserver bei Domains), ASN über RIPEstat; private/reservierte Adressen
  werden nie abgefragt; Sitzungs-Cache, Mindestabstand und Retry-After; „Als Markdown einfügen“ (`Ctrl+Alt+R`)

## [1.9.0] – 2026-09-26

### Hinzugefügt
- Modul Metadaten (`Ctrl+Alt+M`): EXIF inkl. GPS (OpenStreetMap nur auf Klick), XMP, IPTC, PNG-Text; PDF-Info, XMP
  und Speicherstände; Office-Eigenschaften und Namen aus Kommentaren/Änderungsverfolgung. Kopieren, als Markdown
  einfügen, „Metadaten entfernen“ als geprüfte Kopie (Bilder verlustfrei ohne Neukodierung)
- Abhängigkeit pypdf 6.19.0 (BSD-3, reines Python) für PDF-Metadaten
- Modul YARA (`Ctrl+Alt+Y`): Syntax-Highlighting für .yar/.yara, „Regel testen“ gegen Datei oder Ordner (rekursiv)
  mit Trefferliste (Regel, Datei, Offset, String, Treffer), Doppelklick → Hex-Ansicht, Syntaxfehler mit Zeile im
  Editor markiert; Baum-Kontextmenü auch für Ordner; Vorlage „YARA-Regel.yar“
- Modul Zeitleiste & Beweismittel: Zeitleisten-Notizen (Markdown mit Frontmatter), „Zur Zeitleiste hinzufügen“
  (`Ctrl+Alt+Z`) mit Zeitstempel-Erkennung aus Log-/Textzeilen, Ansicht mit Filtern und UTC/lokal (`Ctrl+Shift+Alt+Z`),
  Export als Markdown-Tabelle und CSV; Vorlage „Beweismittel.md“ (Chain of Custody) mit „Prüfsummen einfügen“ und
  „Übergabe eintragen“
- Vorlagen: später hinzugekommene Standardvorlagen landen einmalig auch in bestehenden `templates/`-Ordnern
- Abhängigkeit yara-python 4.5.4 (Apache-2.0, libyara BSD-3; Linux-Wheel mit OpenSSL-1.1-libcrypto)
- Modul IOC entschärfen (Standard an): Rechtsklick → Umwandeln, `Ctrl+Alt+D` / `Ctrl+Shift+Alt+D` – URLs, Domains,
  IPv4/IPv6 und E-Mails in Auswahl oder Datei entschärfen (hxxp, [.], [@], [:]) und wieder scharf machen; Dateinamen,
  Versionen und schon Entschärftes bleiben unverändert, Code-Blöcke optional ausgenommen

### Verbessert
- Baum zeigt alle Dateien, solange ein Analyse-Modul (Strings, Eingebettete Dateien, Entropie) an ist, oder per
  Schalter „Alle Dateien anzeigen“ – vorher waren .exe/.zip/.pcap im Baum unsichtbar und nicht per Rechtsklick
  erreichbar

## [1.8.0] – 2026-09-26

### Hinzugefügt
- Hex-Ansicht: Auswahl kopieren als Hex, Text, Base64 oder C-Array (Rechtsklick); Werte-Zeile u8/u16/u32/u64 LE/BE
  ab Cursor; Wert der Auswahl (1/2/4/8 Bytes) in der Statusleiste
- Dateityp-Erkennung: TAR, PCAP (µs/ns, LE/BE), PCAPNG, EVTX
- Modul Strings (Ctrl+Alt+S): ASCII/UTF-16LE/-BE mit Offset, Mindestlänge einstellbar, gestreamt im Hintergrund,
  Filter/Regex/Kategorie, interessante Treffer hervorgehoben (URL, E-Mail, IP, Pfad, Registry, Base64), Doppelklick
  → Hex-Ansicht, Export als .txt
- Modul Eingebettete Dateien (Ctrl+Alt+F): Signaturen an jedem Offset mit Kopfprüfung, Größe aus dem Format,
  Daten hinter Dateiende-Markern, Sprung in die Hex-Ansicht, Extrahieren in <Datei>_extrahiert/ ohne Überschreiben
- Modul Entropie (Ctrl+Alt+E): Kurve je Block (einstellbar), Bereiche ≥ 7,5 / < 2 markiert, Gesamtentropie mit
  Einschätzung, Hover und Klick in die Hex-Ansicht

## [1.7.0] – 2026-09-26

### Hinzugefügt
- Module: Einstellungen → Module schaltet Funktionen einzeln an/aus, sofort und ohne Neustart; ausgeschaltete Module
  hängen nichts ein (Menü, Palette, Kürzel, Panels) und laden keine Bibliotheken. Hex-Ansicht und Prüfsummen sind
  jetzt das Modul „Hex & Dateianalyse“ (Standard an)
- Variablen: Textbausteine wie §gruss aus variables.json; im Editor erscheint der Wert im Lesefluss (Datei behält das
  Token), Token verhält sich wie ein Zeichen, Hover, Vorschläge nach dem Präfix (Ctrl+Alt+V), Rechtsklick: entfernen
  (\§gruss), durch Wert ersetzen, bearbeiten, wieder als Variable verwenden; Palette: alle ersetzen / in Auswahl
  entfernen; Kopieren setzt Werte ein (einstellbar), Vorschau zeigt Werte, Rechtschreibung ignoriert Tokens, Suche
  optional auch in Werten; Einstellungen → Variablen mit Import/Export und einstellbarem Präfix

### Behoben
- Split View: Nach dem Aufheben der Teilung zeigten Signale und Bearbeitungsleiste verschobener Tabs noch auf die
  gelöschte Gruppe (Fehlermeldungen, Schriftgröße in der Leiste ohne Wirkung); Tabs werden beim Verschieben jetzt
  neu verdrahtet
- Dateien mit Bytes, die cp1252 nicht kennt (0x81, 0x8D, 0x8F, 0x90, 0x9D), ließen sich im Editor nicht öffnen;
  jetzt Latin-1 als letzte Stufe (Speichern bleibt byte-identisch)

## [1.6.0] – 2026-09-26

### Hinzugefügt
- Bilder: Ctrl+V mit Bild bzw. Bilddateien auf eine .md ziehen legt das Bild in assets/ neben der Notiz ab und
  verlinkt es (Ordner einstellbar, nie in .ntx); Bild-Tab mit Einpassen/100 %, Mausrad-Zoom, Verschieben, Maße und
  Größe in der Statusleiste; Bilder und PDFs im Baum (Config-Migration); beim Verschieben einer Notiz Rückfrage,
  ob ihre Bilder mitkommen; „Unbenutzte Bilder finden“ mit Vorschau statt automatischem Löschen
- Dateityp-Erkennung über Magic Bytes (eigene Signaturtabelle) als Grundlage für Viewer-Tabs; Symbole im Baum
  nach Dateityp
- CSV/TSV als Tabelle (Ctrl+Shift+V, pro Tab): Trennzeichen, Quoting und Encoding automatisch erkannt und
  überschreibbar, Kopfzeile umschaltbar, Sortieren per Spaltenklick (numerisch erkannt), Filter über alle Spalten,
  Zellen/Zeilen/Spalten bearbeiten, Blöcke kopieren/einfügen; Speichern erhält Trennzeichen, Quoting-Stil, Encoding
  und Zeilenenden; 100 000 Zeilen ohne Einfrieren; Einstellung „CSV/TSV direkt als Tabelle öffnen“
- JSON/YAML: Formatieren (Shift+Alt+F, Einrückung einstellbar), Minimieren (Shift+Alt+M), Prüfen (Shift+Alt+V und
  beim Tippen) mit Zeile/Spalte in der Statusleiste und Markierung im Text; JSON token-basiert (Zahlen und Escapes
  bleiben exakt); Baumansicht mit Pfad (`$.users[3].name`) und „Pfad kopieren“; YAML nur safe_load/safe_dump,
  Warnung vor dem Formatieren, wenn Kommentare verloren gingen
- Hex-Ansicht (nur lesen, automatisch für unbekannte Binärdateien, „Als Hex öffnen“ im Baum): Offset/Hex/ASCII
  mit synchroner Auswahl, Gehe zu Offset (dezimal/hex), Suche nach Hex-Bytes oder Text im Hintergrund, seitenweises
  Lesen ohne offenes Handle – mehrere GB öffnen sofort
- Dateityp per Magic Bytes in der Statusleiste mit Warnung, wenn die Endung nicht passt
- Prüfsummen (MD5, SHA-1, SHA-256, SHA-512) im Hintergrund mit Fortschritt, kopierbar, „Vergleichen mit …“ grün/rot
- Live verfolgen (Ctrl+Shift+Alt+F) für .log und jede Textdatei: neue Zeilen mit Autoscroll, Pause beim
  Hochscrollen („Pausiert – Ende anspringen“), Rotation/Kürzung erkannt, Filter ERROR / WARN+ / Text / Regex nur für
  die Anzeige, ERROR/WARN farbig, nur lesend, keine „Neu laden?“-Rückfragen während live; optional für .log automatisch
- PDF-Tab (QtPdf, nur lesen): Scrollen, Zoom, Seitensprung, Textsuche, Lesezeichen, Text markieren und kopieren,
  „Als Zitat in Notiz einfügen“ (Markdown-Zitat mit Dateiname und Seite in die Notiz im anderen Teil der Ansicht);
  keine Formulare/Skripte; Datei bleibt nicht gesperrt; Passwort-PDFs fragen nach dem Passwort
- Teilen (Ctrl+\\) geht auch aus einem Bild-/PDF-/Hex-Tab heraus
- Neue Abhängigkeit PyYAML 6.0.3 (MIT, exakt gepinnt)
- UTF-16-Dateien mit BOM werden erkannt (z. B. „Unicode-Text“-Export aus Excel)

### Verbessert
- Externe Änderungen werden bei Dateien über 16 MB über Größe, Änderungszeit und Anfang/Ende erkannt statt über einen
  Hash des ganzen Inhalts (vorher las schon das Öffnen einer 3-GB-Datei alles einmal komplett)
- Große Dateien öffnen deutlich schneller (100 000 Zeilen: ~12 s → ~2 s): kein Hervorheben während des Ladens,
  ein statt drei Durchläufe danach, Einrückungen nur bei echter Schriftänderung neu berechnet

## [1.5.0] – 2026-09-26

### Hinzugefügt
- Kontextmenü im Editor neu: Vorschläge, Bearbeiten (Ausschneiden, Kopieren, Einfügen, Löschen, Alles markieren),
  Text (GROSS, klein, Wortanfänge groß, bei .md Fett/Kursiv/Code/Link – die Aktionen der Bearbeitungsleiste) und
  Nachschlagen; ohne Markierung gilt das Wort unter dem Mauszeiger
- Nachschlage-Karte für Wikipedia (Ctrl+Alt+W) und Wiktionary (Ctrl+Alt+T): Popover neben der Markierung, ganze
  Karte öffnet den Browser, Quelle umschaltbar, Begriffsklärung als Liste, unscharfe Suche, Sprach-Fallback
  Deutsch/Englisch, Skeleton beim Laden, Fehler in der Karte mit Websuche als Ausweg, Sitzungs-Cache,
  Vorschaubilder optional; Abruf nur auf ausdrückliche Aktion, im Hintergrund, 5 s Timeout, eigener User-Agent
- Websuche (Ctrl+Alt+G) nur als Browser-Link: Google, DuckDuckGo, Startpage oder eigene URL mit {q}
- Einstellungen → Nachschlagen (online an/aus, Sprache, Vorschaubilder, Suchmaschine); aus .ntx-Notizen
  Rückfrage vor jedem Senden

## [1.4.0] – 2026-09-26

### Hinzugefügt
- Vorlagen in `templates/` neben der App (Woche, Tagesnotiz, Besprechung als Start), Platzhalter {{date}} {{time}}
  {{weekday}} {{week}} {{year}} {{title}} {{cursor}} plus Formate und Tagesversätze; Neue Datei aus Vorlage
  (Ctrl+Shift+T), jede Vorlage als Befehl in der Command Palette
- Neue Woche (Alt+W): Wochenplan der aktuellen ISO-Woche in `data/Wochen/`, vorhandener Plan wird geöffnet;
  „Nächste Woche anlegen“; Ordner, Dateiname und Vorlage einstellbar
- Update-Check über die GitHub-Releases-API: höchstens einmal täglich, abschaltbar, nur ein Hinweis –
  kein Download; Hilfe › Nach Updates suchen mit Versionshinweisen, Release-Seite öffnen, Version überspringen;
  ignoriert Entwürfe, Vorabversionen und Tags, die keine Version sind
- Linux: Build als `Notex-vX.Y.Z-linux-x86_64.tar.gz` (Ubuntu 22.04), Desktop-Integration auf Knopfdruck
  (notex.desktop, MIME-Typ für .ntx mit Magic, Icon – nur in ~/.local/share, Standardprogramm wird nie gesetzt),
  Rückfrage nach dem Verschieben des Ordners
- CI: Tests auf Ubuntu und Windows; Build-Check beider Plattformen bei Änderungen am Build, ohne Release

### Behoben
- Überblendung beim Tabwechsel deckte kurz die Tab-Leiste ab und ließ unten einen Streifen frei (falsche
  Koordinaten); bleibt die Animation hängen, verschwindet die Blende trotzdem

## [1.3.0] – 2026-09-26

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
