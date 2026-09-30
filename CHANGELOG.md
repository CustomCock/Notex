# Changelog

Alle nennenswerten Änderungen an fckNotes (bis 1.17.0: Notex). Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/).

## [1.17.1] – 2026-09-30

### Umbenannt
- **Notex heißt jetzt „fckNotes“** (der alte Name ist geschützt), das GitHub-Repo heißt `CustomCock/fckNotes`.
  Fenstertitel, Menüs, Dialoge, EXE (`fckNotes.exe`), Release-ZIP, Export-Fußzeile und User-Agent tragen den neuen Namen; ein späterer Wechsel ist
  eine Zeile (`APP_NAME` in `notex/__init__.py`). **Unverändert und kompatibel:** verschlüsselte `.ntx`-Notizen
  (Dateikennung `NOTEXENC`), `data/`/`config.json`, Python-Paket `notex/`, Registry-Schlüssel der
  Dateizuordnung. Beim ersten Start meldet sich die Dateizuordnung als veraltet – „Pfad aktualisieren“ entfernt
  dabei auch den alten „Notex“-Eintrag aus „Öffnen mit“. Fehlerprotokoll heißt jetzt `logs/fehlerprotokoll.log`.

### Behoben
- **Versionsnummer**: Das Release 1.17.0 meldete intern noch 1.16.0 – der Update-Check hätte dort dauerhaft
  „1.17.0 verfügbar“ angezeigt. Ab 1.17.1 stimmt die Nummer wieder mit dem Release überein.
- Update-Check, Links und User-Agent zeigen auf das umbenannte Repo (`REPO` in `notex/__init__.py`).
- Screenshots in `docs/` neu erzeugt (neuer Name; „Dieser PC“ zeigt typische Windows-Laufwerke).

## [1.17.0] – 2026-09-29

### Hinzugefügt
- **Module: „Alle aktivieren“ / „Alle deaktivieren“** in Einstellungen → Module, dazu ein Tri-State-Schalter
  „Alle Module“ (an / teils / aus) mit Zähler. Wirkt sofort ohne Neustart, wird gespeichert, „Abbrechen“ stellt
  den vorherigen Stand her. Auch als Palette-Befehle „Module: alle aktivieren/deaktivieren“.

### Geändert
- **Vorlagen nach Kategorien** (`Ctrl+Shift+T`): Auswahl mit Abschnitten (Ausbildung, Kunde/Einsatz, E-Mail,
  Tabellen, Planung & Notizen, Sicherheit & Forensik, Sonstiges), alphabetisch, mit Suche nach Name und Kategorie.
  Fragebögen (Berichtsheft, Systemcheck, Sicherheits-Check) stehen mit in der Liste. Unterordner in `templates/`
  werden zu eigenen Kategorien. Keine Vorlage wird verschoben; Palette-Einträge heißen „Vorlage: Kategorie › Name“.

### Behoben
- **Nichts passiert mehr lautlos**: Der Windows-Build hat keine Konsole – Fehler in Menü-/Knopf-Aktionen verschwanden
  bisher spurlos („Klick tut nichts“). Jetzt erscheint ein Hinweis, und `logs/fehlerprotokoll.log` hält Datei:Zeile und
  eine Kurzmeldung fest (keine Inhalte).
- **Ping, Traceroute, ipconfig, ARP auf deutschem Windows**: Die Ausgabe (OEM-Codepage cp850) wurde als cp1252
  gelesen; schon „Ping-Statistik für“ ließ jeden Ping abstürzen. Scanner-Ping läuft jetzt im Hintergrund, ein
  abgebrochener Scan setzt den Start-Knopf zurück.
- **Traceroute** zeigt sein Ergebnis (Hintergrund, kopierbares Fenster) statt einer unsichtbaren Konsole.
- **Werkzeuge-Menü/Blatt-Leiste in der geteilten Ansicht**: wirkten auf die Datei der anderen Gruppe (oft fast alles
  ausgegraut), bis man die Datei neu öffnete. Ein Klick ins Blatt – auch auf die Leiste – wählt jetzt dessen Gruppe.
- **Werkzeuge-Menü**: alte Untermenüs werden beim Neuaufbau gelöscht (Speicherleck); ein fehlerhafter Eintrag leert
  nicht mehr das ganze Menü. „IP-Übersicht“ und nicht verfügbare Werkzeuge melden sich mit Hinweis statt stumm.
- **Geräte-Scanner: „Scannen“ tat nichts** – die Zielliste wurde falsch ausgewertet (Absturz direkt beim Start,
  im Windows-Build unsichtbar). Leeres oder ungültiges Ziel wird jetzt gemeldet.
- **Standardvorlagen fehlten**, wenn zuerst „Fragebogen ausfüllen“ benutzt wurde (templates/ galt dann als schon
  eingerichtet). Vom Nutzer gelöschte Vorlagen bleiben weiterhin gelöscht.
- **IP-Übersicht „Aktualisieren“** kurz nach dem Start oder während eines Abgleichs wurde verworfen – wird nachgeholt.

### Tests
- UI-Tests mit echtem Hauptfenster für alle Netzwerk-Werkzeuge und das Werkzeuge-Menü; die CI installiert jetzt
  PySide6 und fährt sie auf Windows und Ubuntu. Manuelle Checkliste: `docs/TESTPLAN-WINDOWS.md`.

## [1.16.0] – 2026-09-28

### Hinzugefügt
- **Formatierte Bearbeitung (WYSIWYG-Markdown)** (Block O0): `**fett**` wird als **fett** angezeigt und bearbeitet –
  keine Sternchen mehr im Blick. Symbolleiste und Kürzel (Ctrl+B/I, Überschriften, Listen, Aufgaben, Zitat,
  Trennlinie, Link) formatieren; Umschalter **Formatiert | Quelltext (Markdown)**. Unter der Haube bleibt Markdown
  (verlustarmer Roundtrip). Befehl „Formatiert bearbeiten“ (Palette + Baum-Kontextmenü) für .md-Notizen; Variablen
  (§name) bleiben erhalten. Tabellen/Codeblöcke werden formatiert gezeigt, Feinarbeit über die Quelltext-Ansicht.
- **Fragebögen/Formulare** (Block O1): Fragebogen-Assistent (ein Abschnitt pro Seite, Fortschritt, Zurück/Weiter,
  Vorschlags-Chips, Zwischenstand gemerkt) füllt YAML-Fragebögen aus `templates/fragebogen/` aus. Fragetypen
  Freitext/Ja-Nein/Auswahl/Mehrfachauswahl/Zahl/Datum/Uhrzeit/Tabelle, Bedingungen, Pflichtfelder, Gewichtung.
  Das Ergebnis wird als formatierte Notiz gespeichert (Antworten im Frontmatter, erneut ausfüllbar). Eigene
  Fragebögen ohne Programmieren möglich.
- **Mitgelieferte Fragebögen**: **Ausbildungsnachweis/Berichtsheft** (O2) – wahlweise **aus einem Kalender-Export
  (.ics) vorbefüllt** (RFC 5545, Serien/EXDATE, ohne Zusatzabhängigkeit); **Systemcheck beim Kunden** (O3);
  **Sicherheits-Check** für kleine Unternehmen (O6) mit **Auswertung** (Punkte je Bereich, Ampel, Gesamtbewertung;
  eigene Formulierungen, inhaltlich an DIN SPEC 27076 / BSI IT-Grundschutz angelehnt).
- **E-Mail-Vorlagen** (O4): Terminbestätigung/-verschiebung, Störungs-Rückfrage, Ticket-Eingang, Wartungsankündigung,
  Abschlussmeldung, Passwort zurückgesetzt (ohne Passwort im Text), Angebotsanfrage, Nachfassen, Phishing-Info,
  Urlaubsübergabe – Betreff als erste Zeile, ohne Grußformel/Signatur.
- **Tabellen-Vorlagen** (O5): IP-Adressliste, Hardware-Inventar, Softwarelizenzen, Wartungsplan, Backup-Protokoll,
  Change-Log, VoIP-Nebenstellen, Patchfeld, Kontakte, Zeiterfassung, Lernplan, Aufgabenliste sowie Benutzer/Zugänge
  **ohne Passwortspalte** (Hinweis: Passwortmanager). CSV zählt jetzt als Vorlagen-Endung.

## [1.15.0] – 2026-09-28

### Hinzugefügt
- **Geräte-Scanner** (Block N, wie „Advanced IP Scanner", `Ctrl+Shift+Alt+P`): findet Geräte im eigenen Netz und
  zeigt sie in einer Live-Tabelle mit **Status, Name, IP, MAC, Hersteller, Kommentar, Dienste-Chips und Antwortzeit**.
  Das eigene Subnetz wird automatisch erkannt (mehrere Adapter möglich), mit Ausschlussliste und Profilen
  (Schnell/Standard/Gründlich). Host-Erkennung kombiniert Ping/TCP-Anklopfen und liest die ARP-Tabelle für MACs;
  Namen aus Reverse-DNS und **NetBIOS**; **Hersteller aus der Offline-OUI-Liste** (öffentliche IEEE-Daten, per
  `tools/update_oui.py` aktualisierbar – bewusst nicht Wiresharks GPL-`manuf`), lokal verwaltete MACs gekennzeichnet.
- **Host-Aktionen** (Kontextmenü/Doppelklick): im Browser öffnen, Remotedesktop (RDP), Freigaben öffnen (`\\host`),
  SSH im Terminal, Ping, Traceroute, Ports vertiefen, RDAP/ASN (nur öffentliche IPs), **Wake-on-LAN**, Remote-
  Herunterfahren/Neustart (Windows, mit deutlicher Bestätigung), Kommentar, Favoriten, IP/MAC/Name kopieren, an die
  IP-Übersicht übergeben. Spalten ein-/ausblendbar, sortierbar, Breiten gespeichert; Live-Filter.
- **Export** des Scans als CSV, JSON, Markdown, HTML und PDF. Der bisherige Port-Scan bleibt als „Port-Scan" in der
  Command Palette erhalten (`scan:ports`).

### Geändert
- `Ctrl+Shift+Alt+P` / „Netzwerk-Scanner" öffnet jetzt den Geräte-Scanner (vorher den reinen Port-Scan).

## [1.14.0] – 2026-09-27

### Hinzugefügt
- **Analyse per Rechtsklick** (Block Q): Text markieren → Kontextmenü **Analysieren**. Notex erkennt den Typ
  (IPv4/IPv6/CIDR/MAC, Domain/URL/E-Mail, Port, Hash, Base64/Base32/Hex, JWT, Unix-Zeit, ISO-Datum, Zahl, Hex-Farbe,
  CVE, ATT&CK-ID, User-Agent – Mehrdeutigkeit erlaubt) und bietet passende Aktionen; das Ergebnis erscheint in einer
  kompakten Karte neben der Markierung, nicht in großen Dialogen. Dieselben Aktionen gibt es in der Command Palette.
  Nicht passende oder abgeschaltete Module erscheinen als „… – Modul aktivieren".
- **Netzwerk-Aktionen** auf markiertem Text: DNS auflösen (A/AAAA/PTR), Ping, gängige Ports prüfen (Modul-frei über
  die Scan-Engine), Port nachschlagen, RDAP/ASN, „In IP-Übersicht/Netzwerk-Scanner öffnen" – alles im Hintergrund,
  private/reservierte Adressen bei RDAP abgefangen.
- **Hash-Info**: erkannte Hash-Typen mit Konfidenz (Länge/Zeichensatz/Präfix erklärt), ein Button „Online-Lookup"
  mit Ergebniszeile darunter. Nur ungesalzene Hashes (MD5 über die Nitrxgen-Datenbank); gesalzene Formate
  (bcrypt/argon2/sha512crypt) sind deaktiviert mit Begründung. Datenschutz-Rückfrage vor dem ersten Senden,
  Einstellung unter „Analyse"; aus verschlüsselten Notizen (.ntx) gesperrt. Zusätzlich „Hash dieses Worts bilden"
  (MD5/SHA-1/SHA-256/NTLM, lokal). **Ein Hash ist eine Einwegfunktion, keine Verschlüsselung** – Notex „entschlüsselt"
  nichts und bringt bewusst keine Wortlisten/Rainbow-Tables mit (dafür gibt es hashcat/John the Ripper).
- **Umwandeln** in der Karte: Base64/Base32/Hex/URL dekodieren, JWT zerlegen (Signatur ungeprüft), Unix-Zeit ↔ Datum,
  Zahl in Basen + Bits, Hex-Farbvorschau, User-Agent zerlegen, CVE im Browser nachschlagen. Jedes Ergebnis lässt sich
  „Als Notiz einfügen".

## [1.13.0] – 2026-09-27

### Hinzugefügt
- Menü **Werkzeuge** in der Menüleiste (nach „Bearbeiten“) mit Kategorien (Dateianalyse, Netzwerk, Logs & Vorfälle,
  Text & Daten, Dokumentation) als Untermenüs; nicht passende Werkzeuge sind ausgegraut (Tooltip erklärt warum),
  abgeschaltete Module erscheinen nicht. **Werkzeug-Übersicht** (`Ctrl+Shift+W`, auch in der Palette) als
  durchsuchbarer Katalog mit „Starten“/„Aktivieren“. „Werkzeuge“-Button in der Blatt-Leiste und Untermenü im
  Baum-Kontextmenü (jeweils nur passende Werkzeuge). Alles aus einer zentralen Registry (`notex/core/tools.py`)
- **Explorer-Baum mit Orten**: Leiste über dem Datei-Baum mit „Notizen“ (data/), „Schnellzugriff“ (angeheftete
  Ordner) und „Dieser PC“ (persönlicher Ordner + Laufwerke/Wurzeln, plattformabhängig). Ein Klick schaltet den Baum
  auf den Ort um; versteckte Dateien per Kontextmenü einblendbar; außerhalb des Notiz-Ordners wird vor Schreibzugriffen
  gewarnt, in Systemordnern besonders deutlich; Ordner per Kontextmenü anheften. Palette-Befehle für Notizen/Dieser
  PC/verstecken/anheften
- **Neue Datei nach Typ**: Text, Markdown, CSV, JSON, YAML, HTML, Python, Shell, INI mit passendem Startinhalt und
  wählbarem Zeilenende (LF/CRLF, gemerkt); im Datei-Menü, im Baum-Kontextmenü und je Typ in der Palette
- **Export als PDF und HTML** (Datei › Exportieren, auch in der Palette): Markdown wird gerendert, CSV als Tabelle,
  sonst als Text; Variablen (`§name`) werden aufgelöst. PDF mit seitenweiser Kopf- (Logo, Titel, Autor/Datum) und
  Fußzeile (Seite X von Y); HTML als eigenständiges Dokument mit eingebettetem Logo und Druck-CSS. Klartext
  verschlüsselter Notizen (.ntx) nur nach Rückfrage
- **Allgemeine Log-Auswertung** für beliebige Logs (setupact.log, dpkg/apt, pip, Nginx/Apache, App- und Dienst-Logs,
  MailStore u. a.): Stufen-Verteilung (ERROR/WARN/INFO/DEBUG, deutsch und englisch), Fehler/Warnungen, häufigste
  Meldungen zu Mustern verdichtet, aktivste Quellen, Zeitspanne und Stunden-Zeitleiste; Filter, Tabelle, Report.
  Die Log-Auswertung wählt automatisch zwischen Sicherheits-Dashboard (Anmelde-Logs) und allgemeiner Auswertung

### Geändert
- Neues **App-Icon** (helles Notizblatt mit Terminal-Prompt `>_` im Akzent) – vereint Editor- und Werkzeug-Charakter
- Analyse-, Netzwerk- und Log-Werkzeuge stehen nicht mehr doppelt im Datei-Menü; ihre Tastenkürzel bleiben erhalten

## [1.12.1] – 2026-09-27

### Behoben
- Netzwerk-Scanner blieb nach dem ersten Host hängen: Reverse-DNS läuft jetzt mit Timeout in einem Thread (blockiert
  den Event-Loop nie) und wird zwischengespeichert; Verbindungen werden immer mit Timeout geschlossen (Windows/
  Proactor); Abbruch greift auch während laufender Port-Probes
- Encoding-Umstellung machte den Menüpunkt kaputt (Windows): Überlaufmenü der Bearbeitungsleiste wird lazy in
  aboutToShow gebaut, Relayout verzögert, keine zwischen Menüs geteilten QActions mehr
- Metadaten-Fenster war bei JPEGs ohne EXIF leer: es zeigt jetzt immer Dateigröße, Format, Bildmaße (SOF),
  Farbkomponenten, Verfahren (Baseline/Progressiv), JFIF, ICC-Profil, geschätzte Qualität, Vorschaubild-Status und
  die Segmentliste; fehlen EXIF/XMP/IPTC (bzw. Dokumenteigenschaften), steht das ausdrücklich als Hinweis darin
- PCAP-Auswertung überarbeitet: Protokoll-Hierarchie (Ethernet › ARP/IPv4 › ICMP/UDP/TCP › DNS/HTTP/TLS mit Paketen
  und Bytes je Ebene), Hosts mit MAC/Adresstyp/Rolle, ARP (inkl. Spoofing- und Gratuitous-Hinweis), ICMP mit
  Echo-Paarung und RTT, DNS mit Anfrage/Antwort-Paarung, TCP-Verbindungen mit Status/Bytes je Richtung und
  „Stream folgen“ (Text/Hex), HTTP mit Anfrage+Antwort, TLS-SNI/Version, Dienste, Befunde

## [1.12.0] – 2026-09-27

### Hinzugefügt
- Modul Log-Auswertung (Standard aus, `Ctrl+Shift+Alt+L`): auth.log/secure (auch rotierte .gz) und Windows-.evtx
  (Paket evtx, Rust/MIT) mit Dashboard (Fehlversuche je IP/Benutzer, Erfolg nach Fehlversuchen, Brute-Force-Verdacht,
  neue Benutzer/Gruppen/Dienste, geleerte Protokolle, Kontosperren), Zeitleiste (QPainter), Filter, Sprung zur Quelle,
  „Zur Zeitleiste hinzufügen“, RDAP für IPs, Markdown-Report; große Logs gestreamt
- Modul PCAP-Übersicht (Standard aus, `Ctrl+Shift+Alt+K`): .pcap/.pcapng streamen (dpkt) – Zeitraum, Protokolle,
  Top-Verbindungen/-Talker, DNS, HTTP (Hosts/Pfade/User-Agents), TLS-SNI und im Klartext übertragene Zugangsdaten
  (FTP/Telnet/HTTP Basic/POP3/IMAP/SMTP AUTH) rot markiert; Tabellen filter-/sortierbar, RDAP je IP, Markdown-Report;
  kaputte Aufzeichnungen werden übersprungen
- Abhängigkeiten evtx 0.13.1 (MIT, Wheels) und dpkt 1.9.8 (BSD-3) hinzugefügt

## [1.11.0] – 2026-09-27

### Hinzugefügt
- Modul Netzwerk-Scanner (Standard aus, `Ctrl+Shift+Alt+P`): TCP-Connect-Scan im eigenen Netz (asyncio, ohne
  Admin-Rechte, Windows und Linux gleich), Host-Erkennung (TCP-Anklopfen, optional System-ping), Banner für
  HTTP/SSH/FTP/SMTP u. a., Reverse-DNS, MAC aus der ARP-Tabelle; Ziele als IP/Hostname/CIDR/Bereich/Liste mit
  Obergrenze und Bestätigung für öffentliche Ziele; speicherbare Portprofile; Ergebnis als Tabelle, Speichern als
  JSON + Markdown-Report in data/scans/, Scan-Vergleich, Übergabe an die IP-Übersicht
- Skript-Export des Scans als eigenständiges PowerShell- und Bash-Skript (nur Bordmittel, CSV-Ausgabe); CI prüft die
  erzeugten Skripte auf Syntax (bash -n, PowerShell-Parser)

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
