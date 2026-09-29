# Manuelle Prüfung unter Windows – Netzwerk-Werkzeuge und Werkzeuge-Menü

Die automatischen Tests laufen offscreen auf Windows und Ubuntu (CI). Was sie **nicht** abdecken können: echtes
Netz, deutsche Windows-Konsolenausgaben live, Fensterverhalten auf dem Desktop, der gebaute EXE-Start ohne Konsole.
Diese Liste prüft genau das. Dauer: ca. 15 Minuten. Nur im **eigenen** Netz scannen.

**Vorbereitung**
- Frischer Build entpacken (Notex.exe), starten. Einstellungen → Module: Netzwerk-Scanner, Port-Infos,
  IP-Konflikte, RDAP/ASN, PCAP-Übersicht einschalten.
- In `data/` eine Datei `netz.md` anlegen mit zwei Zeilen: `10.0.0.5 fileserver` und `drucker: 10.0.0.5`.
- Bei jedem Punkt gilt: **es muss sichtbar etwas passieren** (Fenster, Karte, Statuszeile oder Hinweis unten rechts).
  „Nichts passiert“ ist immer ein Fehler → Inhalt von `logs\notex-fehler.log` mitschicken.

## A. Werkzeuge-Menü und Blatt-Leiste (Ursprungsproblem)

| # | Schritt | Erwartet | ✓ |
|---|---|---|---|
| A1 | `server.log` und `netz.md` öffnen, zwischen den Tabs wechseln, Menü **Werkzeuge** öffnen | Kategorien mit Untermenüs, Netzwerk-Werkzeuge aktiv | |
| A2 | In der Leiste über dem Blatt auf **Werkzeuge** klicken | Nur passende Werkzeuge, nicht leer | |
| A3 | `Ctrl+\` (teilen), in der anderen Gruppe ein Bild öffnen, dann in der Leiste des **Log**-Blatts auf Werkzeuge | Log-Werkzeuge (Log-Auswertung, Live verfolgen) – nicht die Bild-Werkzeuge | |
| A4 | Aus diesem Leisten-Menü „Strings extrahieren“ | Fenster bezieht sich auf **server.log** (nicht auf das Bild) | |
| A5 | Teilung aufheben (`Ctrl+\`), Tab schließen, Datei neu öffnen, Werkzeuge-Menü 20× auf- und zuklappen | Menü bleibt gefüllt und flott | |

## B. Geräte-Scanner (`Ctrl+Shift+Alt+P`)

| # | Schritt | Erwartet | ✓ |
|---|---|---|---|
| B1 | Öffnen | Fenster erscheint sofort, Ziel ist mit dem eigenen Subnetz vorbefüllt (z. B. `192.168.178.0/24`) | |
| B2 | Ziel leeren, **Scannen** | Statuszeile: „Erst ein Ziel eingeben …“ | |
| B3 | Eigenes Subnetz, Profil „Schnell“, **Scannen** | Knopf wird „Stopp“, Fortschritt läuft, Geräte erscheinen live; am Ende „N Geräte gefunden“ | |
| B4 | Option **System-Ping** an, erneut scannen | Scan läuft durch (früher: Abbruch mit „charmap codec“ auf deutschem Windows) | |
| B5 | Rechtsklick auf den Router → **Ping** | Status sofort „Ping an … “, danach „erreichbar“ – Fenster bleibt bedienbar | |
| B6 | Rechtsklick → **Traceroute** | Status „läuft …“, danach Fenster „Traceroute zu …“ mit lesbarer Ausgabe (Umlaute korrekt: „über maximal 15 Hops“), kein aufblitzendes Konsolenfenster | |
| B7 | Rechtsklick → Im Browser öffnen / Freigaben / Kommentar / Kopieren | jeweils sichtbare Reaktion | |
| B8 | **Exportieren** als CSV und PDF | Dateien entstehen, lassen sich öffnen | |

## C. Port-Scan (Palette → „Port-Scan“)

| # | Schritt | Erwartet | ✓ |
|---|---|---|---|
| C1 | Ziel = IP des Routers, Ports `top100`, **Start** | Ergebnis-Tabelle, Status „Fertig: 1 aktive Host(s), N offene Ports …“ | |
| C2 | Ziel `8.8.8.8` | Bestätigungsfrage „öffentliches Ziel“ | |

## D. Rechtsklick-Analyse (Q) im Editor

In `server.log` die IP `10.0.0.5` markieren (bzw. eine echte IP aus dem eigenen Netz) → Rechtsklick → **Analysieren**.

| # | Schritt | Erwartet | ✓ |
|---|---|---|---|
| D1 | **DNS auflösen** → „Auflösen“ | Karte neben dem Cursor, Ergebnis A/PTR oder verständlicher Fehler | |
| D2 | **Ping (Antwortzeit)** → „Ping senden“ | „erreichbar“ / „keine Antwort“ (früher: „Fehler: 'charmap' codec …“) | |
| D3 | **Gängige Ports prüfen** → „Ports prüfen“ | „offen: …“ oder „keine der Top-100-Ports offen“ | |
| D4 | **In IP-Übersicht öffnen** / **Im Netzwerk-Scanner öffnen** | jeweiliges Fenster öffnet | |

## E. Port-Infos, IP-Übersicht, RDAP, PCAP

| # | Schritt | Erwartet | ✓ |
|---|---|---|---|
| E1 | `Ctrl+Alt+P`, `3389` eingeben | RDP mit IANA-Details | |
| E2 | `Ctrl+Shift+Alt+I` | Subnetz 10.0.0.0/24 rot „1 im Konflikt“ (fileserver ↔ drucker) | |
| E3 | In der IP-Übersicht **Aktualisieren** direkt nach dem Start klicken | Übersicht aktualisiert sich (früher: Klick wurde verworfen) | |
| E4 | `Ctrl+Alt+R` mit `8.8.8.8` | Karte mit Netz/ASN (braucht Internet) | |
| E5 | `Ctrl+Alt+R` mit `192.168.1.1` | Hinweis „… fragt Notex nie ab“, keine Anfrage | |
| E6 | Eine `.pcap` im Baum wählen → `Ctrl+Shift+Alt+K` | Übersicht mit Paketzahl, Tabs Hosts/DNS/TCP gefüllt | |

## F. Fehler sichtbar

| # | Schritt | Erwartet | ✓ |
|---|---|---|---|
| F1 | Modul „Netzwerk-Scanner“ ausschalten, Werkzeug-Übersicht → Netzwerk-Scanner | Hinweis „Modul … ist aus“ | |
| F2 | Nach dem Test `logs\notex-fehler.log` ansehen | Datei fehlt oder ist leer. Falls nicht: Inhalt mitschicken (enthält nur Datei:Zeile + Kurzmeldung, keine Notizinhalte) | |
