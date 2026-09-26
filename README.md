# Notex

Portabler Explorer + Editor für Textdateien unter Windows. Ein Ordner, eine EXE,
keine Installation: `data/` daneben ist dein Notizbaum, `config.json` merkt sich den Zustand.

## Installation

1. Aus den [Releases](https://github.com/CustomCock/Notex/releases) die Datei `Notex-vX.Y.Z.zip` laden.
2. Entpacken, z. B. nach `C:\Apps\Notex` oder auf einen USB-Stick.
3. `Notex.exe` starten. Beim ersten Start entstehen `data/` und `config.json` daneben.

Mehr ist nicht nötig. SmartScreen warnt beim ersten Start, weil die EXE nicht signiert ist:
„Weitere Informationen“ → „Trotzdem ausführen“. Die ZIP bitte komplett entpacken, nicht die
`Notex.exe` direkt aus dem ZIP-Fenster starten: Windows legt sie dann in einen Temp-Ordner, und
Notizen würden dort landen (Notex warnt in dem Fall beim Start).

**Update:** Notex schließen, im bestehenden Ordner `Notex.exe` und `_internal/` durch die aus der
neuen ZIP ersetzen (`licenses/`, `LICENSE`, `CHANGELOG.md` gleich mit). `data/`, `config.json`,
`themes/`, `fonts/user/` und `user_dictionary.txt` bleiben liegen. Wer den Ordner verschiebt oder
neu entpackt, bekommt beim nächsten Start die Frage, ob die Windows-Dateizuordnung auf den neuen
Pfad gesetzt werden soll (auch später möglich unter Einstellungen → System → „Pfad aktualisieren“).

![Editor mit geöffneter Datei](docs/03-editor.png)

| Start | Suche | Seitenleiste eingeklappt |
|---|---|---|
| ![Empty State](docs/01-empty-state.png) | ![Suche mit Volltexttreffern](docs/04-search.png) | ![Seitenleiste eingeklappt](docs/05-sidebar-collapsed.png) |

| Kontextmenü | Suchen/Ersetzen | Gespeichert-Toast |
|---|---|---|
| ![Kontextmenü](docs/06-context-menu.png) | ![Suchen und Ersetzen](docs/07-find-replace.png) | ![Toast](docs/08-toast.png) |

Die Screenshots erzeugt `python tools/screenshot.py` automatisch (offscreen, mit Testdaten).
Standardschrift ist Inter; mit SF Pro in `fonts/user/` sieht die Oberfläche entsprechend anders aus.

## Was es kann

- **Verzeichnisbaum** von `data/` links, Dateien per Klick im Editor öffnen, mehrere Tabs
- **Suche** (Ctrl+Shift+F): rekursiv, case-insensitive, nach Dateiname und/oder Volltext,
  läuft im Hintergrund-Thread, Klick auf einen Treffer springt in die Zeile. Filter, Regex und
  „Ganzes Wort“ siehe [Suche und Ersetzen in Dateien](#suche-und-ersetzen-in-dateien)
- **Editor**: weißes Blatt auf dunklem Tisch, Zeilennummern, aktuelle Zeile hervorgehoben,
  Suchen/Ersetzen (Ctrl+F / Ctrl+H), Zoom (Ctrl+Mausrad, Ctrl+Plus/Minus)
- **Bearbeitungsleiste** über dem Blatt (Ctrl+Shift+E): Verlauf, Suchen, Textschrift, Ansicht,
  Zeilen- und Textwerkzeuge, Markdown-Toggles bei .md, Prüfung, Encoding/Zeilenende
- **Kein horizontales Scrollen**: Zeilen brechen immer an der Blattbreite um, auch lange URLs,
  Hashes und Pfade; Listen behalten beim Umbruch ihre Einrückung
- **Dateien**: Encoding (UTF-8, UTF-8-BOM, cp1252) und Zeilenenden (CRLF/LF) bleiben beim
  Speichern erhalten; atomares Speichern, damit bei einem Absturz nie eine halbe Datei liegt
- **Baum-Kontextmenü**: Neue Datei, Neuer Ordner, Umbenennen (F2), Papierkorb (Entf),
  Im Explorer anzeigen; Drag & Drop zum Verschieben
- **Watcher**: extern hinzugefügte Dateien tauchen im Baum auf; wird eine offene Datei
  extern geändert, fragt die App, ob sie neu laden soll
- **Dateien von außen**: Doppelklick im Explorer, Drag & Drop aufs Fenster oder Ctrl+O öffnen Dateien
  auch außerhalb von `data/` am Originalort; alle landen in EINEM Fenster (Einzelinstanz)
- **Zustand** in `config.json`: Fenster, Seitenleiste, aufgeklappte Ordner, offene Tabs,
  Zoom, Blatt-Modus, Bearbeitungsleiste, Zeilennummern, Such-Chips, Theme, zuletzt geöffnet
- **Design**: matt schwarz/grau, das Blatt weiß und zentriert (Alt+P schaltet auf volle Breite),
  ein einziger dezenter Akzent, kurze Animationen (abschaltbar unter Ansicht)

## Dateien von außen und Dateizuordnung

`Notex.exe "C:\pfad\datei.txt"` öffnet die Datei. Läuft Notex schon, übernimmt die laufende
Instanz sie als Tab und holt das Fenster nach vorn. Markierst du mehrere Dateien im Explorer und
drückst Enter, landen alle in einem Fenster. Dateien außerhalb von `data/` werden direkt am
Originalort bearbeitet, nicht kopiert; sie erscheinen in der Seitenleiste unter „Geöffnet“ mit
Kontextmenü „In data/ kopieren“, „In data/ verschieben“ und „Im Explorer anzeigen“. Ihre Tabs
tragen ein kleines Pfeil-Symbol. Schreibgeschützte Dateien melden sich in der Statusleiste,
Speichern bietet dann „Speichern unter …“ an. **Ctrl+R** zeigt die zuletzt geöffneten Dateien.

Damit ein Doppelklick auf `.txt` Notex startet, registrierst du es in den Einstellungen unter
**System**: Dateitypen wählen (.txt ist vorausgewählt), „Notex für Dateitypen registrieren“.
Das schreibt nur in HKCU (kein Admin) und überschreibt keine bestehende Zuordnung: Notex erscheint
unter „Öffnen mit“, in den Windows-Standard-Apps und im Kontextmenü als „Mit Notex öffnen“
(unter Windows 11 im klassischen Menü unter „Weitere Optionen anzeigen“). Den Standard für
`.txt` wählst du selbst in den Windows-Einstellungen; der Button „Windows-Standard-Apps öffnen“
bringt dich direkt dorthin. „Registrierung entfernen“ räumt alles wieder restlos weg. Wird der
Notex-Ordner verschoben, weist ein Hinweis beim Start darauf hin, und „Pfad aktualisieren“ schreibt
den neuen Pfad. Aus dem Dev-Modus (`python main.py`) ist die Registrierung bewusst deaktiviert.

![Einstellungen System](docs/20-settings-system.png)

## Quick Open und Command Palette

**Ctrl+P** öffnet ein Overlay über dem Blatt mit Fuzzy-Suche über alle Dateien in `data/` und die
zuletzt geöffneten externen Dateien: „ntz“ findet `notizen.md`, getroffene Zeichen sind
hervorgehoben, zuletzt geöffnete Dateien stehen weiter oben. `:123` springt in der aktuellen
Datei zu Zeile 123, `notizen:12` öffnet die Datei und springt. Der Dateiindex wird im Hintergrund
aufgebaut und über den Watcher aktuell gehalten.

**Ctrl+Shift+P** (oder `>` in Quick Open) zeigt alle Befehle der App mit Kategorie und Kürzel:
Menüs, Toolbar, Einstellungsseiten, Theme-Presets und Blatt-Varianten, Toggles mit aktuellem
Zustand. Zuletzt benutzte Befehle stehen oben. Neue Features melden sich an einer zentralen
Registry an und tauchen automatisch auf.

| Quick Open | Command Palette | Wiki-Links und Backlinks |
|---|---|---|
| ![Quick Open](docs/21-quick-open.png) | ![Command Palette](docs/22-command-palette.png) | ![Wiki-Links](docs/23-wikilinks-backlinks.png) |

## Wiki-Links und Backlinks

In jeder Textdatei verlinkt `[[notizen]]` auf die Datei `notizen.*` irgendwo in `data/`
(Name ohne Endung, Groß-/Kleinschreibung egal; bei Mehrdeutigkeit gewinnt der kürzeste Pfad,
`[[ordner/notizen]]` zielt explizit). `[[notizen|Anzeigetext]]` zeigt anderen Text,
`[[notizen#Überschrift]]` springt zur Überschrift. Links sind im Akzent unterstrichen, kaputte
Links gestrichelt und gedämpft. **Ctrl+Klick** öffnet das Ziel; bei einem kaputten Link bietet
Notex an, die Datei anzulegen. Nach `[[` erscheint ein Vorschlags-Popup mit Dateien, nach `#`
mit den Überschriften der Zieldatei (Enter oder Tab übernimmt). In Codeblöcken und Inline-Code
zählen Links nicht.

**Ctrl+Shift+K** zeigt das Backlinks-Panel (unter dem Blatt oder rechts, einstellbar): alle
Dateien, die auf die aktuelle Datei verlinken, mit Zeile und Kontext, Klick springt hin.
Darunter „Unverlinkte Erwähnungen“: Stellen, an denen der Dateiname als Text vorkommt, mit
„verlinken“. Wird eine Datei oder ein Ordner umbenannt oder verschoben, fragt Notex „X Links in Y
Dateien anpassen?“ mit Vorschau und schreibt die Links in allen betroffenen Dateien um, auch in
offenen Tabs. Der Link-Index entsteht im Hintergrund und wird über den Watcher aktuell gehalten.

## Suche und Ersetzen in Dateien

Das Suchfeld links versteht eine kleine Abfragesprache:

| Eingabe | Bedeutung |
|---|---|
| `apfel kuchen` | beide Wörter müssen in derselben Zeile stehen (bzw. im Dateinamen) |
| `"grüne birne"` | genaue Phrase mit Leerzeichen |
| `ext:md` oder `ext:md,txt` | nur diese Endungen (auch welche, die nicht im Baum stehen) |
| `path:projekte` | nur Pfade, die „projekte“ enthalten |
| `-path:archiv` | Pfade mit „archiv“ ausschließen |

Die Chips unter dem Feld schalten **`.*`** (regulärer Ausdruck, Python-Syntax) und **Wort** (nur ganze
Wörter) zu. Eine ungültige Regex bekommt einen roten Rahmen und die Fehlermeldung als Tooltip. Jeder
Regex-Treffer hat ein Zeitlimit von 0,25 s pro Zeile, damit ein Muster wie `(a|a)+$` Notex nicht
einfriert; die Suche bricht dann mit „Timeout“ ab.

**Ctrl+Shift+H** öffnet „Ersetzen in Dateien“: gleicher Suchbegriff, Ersatztext (bei Regex mit `\1` für
Gruppen), darunter jede betroffene Zeile als *vorher → nachher* mit Häkchen. Ersetzt wird nur, was
angekreuzt ist. Offene Dateien mit ungespeicherten Änderungen werden im Editor ersetzt (rückgängig
machbar, nicht gespeichert), offene gespeicherte Dateien werden danach gespeichert, alle anderen
atomar mit ihrem Encoding und Zeilenende geschrieben.

![Ersetzen in Dateien](docs/28-replace-in-files.png)

## Markdown-Vorschau

`Ctrl+Shift+V` wechselt bei `.md`-Dateien zwischen Bearbeiten, Vorschau und geteilter Ansicht (Blatt links,
gerendertes Markdown rechts, Scrollen synchron). Die Vorschau ist bewusst zurückhaltend:

- Kein JavaScript, kein rohes HTML aus der Datei, keine Netzverbindung ohne Klick. Externe Bilder erscheinen
  als „Bild laden“, externe Links öffnen den Browser erst beim Anklicken.
- Aufgaben `- [ ]` lassen sich in der Vorschau anhaken, die Datei wird sofort geändert.
- `[[Wiki-Links]]`, relative Links (`ordner/notiz.md#Abschnitt`) und `#Anker` funktionieren.
- Codeblöcke (```python usw.) bekommen die Syntax-Farben des Themes, Tabellen und ~~Durchstreichen~~ werden gerendert.

Einstellungen → Editor legt fest, wie `.md`-Dateien öffnen (Bearbeiten, Vorschau, Geteilt) und ob die
Vorschau mitscrollt.

![Markdown-Vorschau](docs/26-markdown-preview.png)

## Split View

`Ctrl+\` teilt den Editor in zwei Tab-Gruppen, die aktuelle Datei erscheint in beiden (ein Dokument, zwei
Ansichten, gemeinsames Undo). Tabs lassen sich per Drag zwischen den Gruppen ziehen; wird ein Tab am
rechten oder unteren Rand abgelegt, entsteht die zweite Gruppe. `Ctrl+Alt+\` stellt die Gruppen
untereinander statt nebeneinander, `Ctrl+Alt+→` verschiebt den Tab in die andere Gruppe. Schließt der
letzte Tab einer Gruppe, verschwindet sie. Die Aufteilung überlebt einen Neustart.

![Split View](docs/27-split-view.png)

## Syntax-Highlighting

Code und Logs werden über [Pygments](https://pygments.org) farbig hervorgehoben: `.py`, `.json`,
`.ini`, `.sh`, `.ps1`, `.bat`, `.yaml`/`.yml`, `.xml`, `.html`, `.css`, `.js`, `.sql`, `.md` sowie
in Markdown die Codeblöcke mit Sprachangabe (```python usw.). In `.log`-Dateien werden Zeitstempel,
Level (ERROR/WARN/INFO/DEBUG), IP-Adressen und Pfade markiert. Die Farben sind Theme-Tokens mit je
einem Schema für helle Blätter (Weiß, Papier, Sepia) und für das dunkle Blatt, anpassbar unter
Einstellungen → Blatt → Syntax-Farben. Pro Endung abschaltbar unter Einstellungen → Editor.
Gefärbt wird zeilenweise mit Zustand über Zeilengrenzen (Docstrings, `/* */`, Codeblöcke); Dateien
über 2 MB bleiben ohne Highlighting, damit das Öffnen flott bleibt.

| Python | Log |
|---|---|
| ![Syntax Python](docs/24-syntax-python.png) | ![Syntax Log](docs/25-syntax-log.png) |

## Bearbeitungsleiste

Direkt über dem Blatt sitzt eine schmale Leiste in Blattbreite. Der kleine Chevron darunter
(oder **Ctrl+Shift+E**) klappt sie ein und aus, der Zustand bleibt gespeichert. Die Gruppen:

| Gruppe | Werkzeuge |
|---|---|
| Verlauf | Rückgängig, Wiederholen |
| Suchen | Suchen (Ctrl+F), Ersetzen (Ctrl+H) |
| Textschrift | Schriftart-Dropdown, Größe −/Feld/+ |
| Ansicht | Zoom zurücksetzen (Ctrl+0), Blatt-Modus/volle Breite (Alt+P), Zeilennummern (Ctrl+Alt+N) |
| Zeilen | Duplizieren (Ctrl+D), hoch/runter (Alt+↑/↓), sortieren (F9), Duplikate entfernen (Ctrl+Shift+D), Leerzeichen am Zeilenende entfernen |
| Text | GROSS (Ctrl+Shift+U), klein (Ctrl+U), Wortanfänge groß (Ctrl+Alt+U), Datum/Uhrzeit (F5) |
| Markdown (nur .md) | Fett (Ctrl+Alt+B), Kursiv (Ctrl+Alt+I), Überschrift (Ctrl+Alt+H), Liste (Ctrl+Alt+L), Checkbox (Ctrl+Alt+X), Code (Ctrl+Alt+C), Link (Ctrl+K) – jeweils als Toggle |
| Prüfung | Rechtschreibung (F7), Grammatik (Shift+F7) |
| Datei | Encoding (UTF-8 / UTF-8 BOM / cp1252) und Zeilenende (LF / CRLF) anzeigen und umstellen |

Passt nicht alles nebeneinander, wandern die hinteren Gruppen in das „…“-Menü rechts. Die
Tastenkürzel gelten auch bei eingeklappter Leiste. Wichtig: Textdateien haben keine
Formatierung. Schriftart und Größe sind Ansichts-Einstellungen für alle Dateien und ändern
nichts am Inhalt.

| Leiste mit Markdown-Gruppe | Eingeklappt | Schmales Fenster mit „…“ |
|---|---|---|
| ![Toolbar](docs/16-toolbar-markdown.png) | ![Eingeklappt](docs/17-toolbar-collapsed.png) | ![Überlauf](docs/18-toolbar-overflow.png) |

## Schriften

Die Oberfläche benutzt eine feste Schrift, die nicht einstellbar ist. Reihenfolge:
**SF Pro Text / SF Pro Display** (falls vorhanden) → **Inter** (gebündelt, OFL) → Segoe UI
Variable → Segoe UI. SF Pro wird aus Lizenzgründen nie mitgeliefert. Willst du sie (oder andere
Schriften) nutzen, lege die Dateien nach `fonts/user/` neben die App: Sie werden beim Start
automatisch geladen und erscheinen im Schrift-Dropdown. Der Ordner steht in `.gitignore` und
wird vom Build nicht mitkopiert.

Einstellbar ist nur die Schrift des Textinhalts im Blatt (Einstellungen → Schrift oder
Toolbar), standardmäßig dieselbe proportionale Schrift wie die Oberfläche. Für Code-artige
Endungen (.py, .json, .csv, .log, .ini) ist JetBrains Mono voreingestellt; das lässt sich je
Endung ändern.

## Umbruch

Zeilen brechen immer an der Blattbreite um, notfalls mitten im Wort (URLs, Hashes, Pfade,
Base64). Es gibt keine horizontale Scrollbar. Die maximale Textbreite im Blatt-Modus ist ein
Maximum: Wird das Fenster schmaler oder die Seitenleiste geöffnet, schrumpft das Blatt mit,
die Innenabstände gehen bis auf 16 px zurück, und die Lese-Position bleibt beim Reflow erhalten.
Umgebrochene Folgezeilen eingerückter Zeilen und Listenpunkte übernehmen die Einrückung,
Zeilennummern stehen nur an der ersten Zeile.

![Lange Zeilen](docs/19-wrap-long-lines.png)

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
- **Schrift**: Textschrift des Blatts (Standard, gebündelte, eigene und installierte), Größen,
  Zeilenhöhe, Schrift je Dateiendung.

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
| Ctrl+Shift+H | Ersetzen in Dateien (mit Vorschau und Häkchen) |
| Ctrl+Plus / Ctrl+Minus / Ctrl+0 | Zoom |
| Ctrl+Shift+E | Bearbeitungsleiste ein-/ausklappen |
| Ctrl+Alt+N | Zeilennummern |
| Alt+P | Blatt zentrieren / volle Breite |
| Ctrl+P | Quick Open (Datei suchen, `:123` springt zur Zeile, `datei:123` öffnet und springt) |
| Ctrl+Shift+P | Command Palette (alle Befehle, `>` in Quick Open wechselt ebenfalls dorthin) |
| Ctrl+Shift+K | Backlinks-Panel |
| Ctrl+Shift+V | Markdown-Vorschau: Bearbeiten → Vorschau → Geteilt |
| Ctrl+\ | Editor teilen / Teilung aufheben |
| Ctrl+Alt+\ | Gruppen nebeneinander / untereinander |
| Ctrl+Alt+→ | Tab in andere Gruppe verschieben |
| Ctrl+Alt+Shift+→ | Datei auch in anderer Gruppe öffnen |
| Ctrl+Klick | Wiki-Link öffnen (bzw. Ziel anlegen) |
| Ctrl+, | Einstellungen |
| Ctrl+O / Ctrl+R | Datei öffnen / Zuletzt geöffnet |
| Ctrl+Shift+Alt+S | Speichern unter |
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
(Default: `.txt .md .log .csv .json .py .ini .sh .ps1 .bat .yaml .yml .xml .html .css .js .sql`). `fulltext_max_mb` begrenzt die Dateigröße
für die Volltextsuche (Default 5 MB).

## Bekannte Einschränkungen

- Die Grammatikprüfung braucht einen LanguageTool-Server; ohne Server bleibt sie still aus.
- Der Kontextmenü-Eintrag erscheint unter Windows 11 nur im klassischen Menü, kein Eintrag im neuen
  Menü (dafür wäre ein Sparse-Package nötig, das die portable App bewusst nicht mitbringt).
- Die EXE ist nicht signiert (SmartScreen-Hinweis beim ersten Start).
- Sehr große Dateien (mehrere hundert MB) sind nicht das Ziel; getestet sind 5-MB-Logdateien.
- Rechtschreibung kennt nur Deutsch und Englisch; weitere Hunspell-Wörterbücher lassen sich nach
  `notex/dictionaries/` legen, werden aber nicht in der Oberfläche angeboten.

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

Lokaler Build: `build.bat` legt die venv an, installiert alles und ruft `python build.py` auf.
`build.py` bricht ab, wenn PySide6 & Co. im verwendeten Python fehlen, denn PyInstaller würde
sonst stumm eine Exe ohne Qt erzeugen. Immer denselben Interpreter für `pip install` und den
Build nehmen (`py -3.12 -m pip …` und `py -3.12 build.py`).

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

Ein annotiertes Tag der Form `v*` stößt den Workflow `.github/workflows/release.yml` an: Er baut
die App auf `windows-latest`, packt `dist/Notex` als ZIP und hängt es an ein GitHub-Release.
Die Version steht zentral in `notex/__init__.py` und muss zum Tag passen.

```bat
git tag -a v1.1.0 -m "Notex 1.1.0"
git push origin v1.1.0
```
