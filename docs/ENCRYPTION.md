# Verschlüsselte Notizen (`.ntx`)

fckNotes kann einzelne Notizen mit einem Passwort verschlüsseln. Dieses Dokument beschreibt, was dabei
passiert, was geschützt ist und was nicht. Es richtet sich an alle, die wissen wollen, ob sie der
Funktion vertrauen können.

## Kurz

- **Algorithmen:** AES-256-GCM für den Inhalt, Argon2id (RFC 9106) für den Schlüssel aus dem Passwort.
- **Keine eigene Kryptografie:** Alles kommt aus der Bibliothek [`cryptography`](https://cryptography.io)
  (pyca), die OpenSSL nutzt. fckNotes setzt nur Bausteine zusammen und legt das Dateiformat fest.
- **Klartext liegt nie auf der Platte.** Weder im Verlauf noch im Suchindex, nicht in `config.json`,
  keinem Log und keinem Toast.
- **Ohne Passwort gibt es keinen Weg zurück.** Kein Generalschlüssel, keine Wiederherstellung, auch
  nicht durch fckNotes.

## Benutzung

| Aktion | Wo |
|---|---|
| Neue verschlüsselte Notiz | Datei → Neue verschlüsselte Notiz … (Ctrl+Shift+Alt+N) oder im Baum eine neue Datei mit Endung `.ntx` anlegen |
| Bestehende Datei verschlüsseln | Datei → Datei verschlüsseln … (erzeugt `name.ntx`, löscht den Verlauf des Originals und bietet an, das Original in den Papierkorb zu legen) |
| Entsperren | Datei öffnen, Passwort in den Sperrbildschirm des Tabs eingeben |
| Sperren | Ctrl+Shift+L sperrt alle offenen verschlüsselten Notizen, automatisch nach 5 Minuten ohne Eingabe (Einstellungen → Editor) |
| Passwort ändern | Datei → Passwort ändern … (verlangt das aktuelle Passwort, erzeugt ein neues Salt) |

Beim Sperren werden ungespeicherte Änderungen zuerst verschlüsselt gespeichert. Danach leert fckNotes
den Editor, den Undo-Verlauf und verwirft den Schlüssel.

## Dateiformat v1

Alle Zahlen Big Endian.

| Offset | Länge | Inhalt |
|---|---|---|
| 0 | 8 | Magic `NOTEXENC` |
| 8 | 1 | Formatversion, derzeit `1` |
| 9 | 1 | Schlüsselableitung: `1` = Argon2id, `2` = scrypt |
| 10 | 4 | Argon2id: Speicher in KiB · scrypt: log2(N) |
| 14 | 4 | Argon2id: Iterationen · scrypt: r |
| 18 | 4 | Argon2id: Lanes · scrypt: p |
| 22 | 16 | Salt (pro Datei, neu bei Passwortwechsel) |
| 38 | 12 | Nonce (neu bei jedem Speichern) |
| 50 | … | AES-256-GCM-Chiffretext des UTF-8-Texts, 16-Byte-Tag am Ende |

- **Header als Associated Data:** Die 50 Header-Bytes gehen als AAD in AES-GCM ein. Jede Änderung an
  Version, Parametern, Salt oder Nonce lässt die Entschlüsselung genauso scheitern wie eine Änderung
  am Chiffretext.
- **Nonce:** 96 Bit aus `os.urandom`, bei jedem Speichern neu. Pro Datei und Passwort bleibt der
  Schlüssel gleich. Das Risiko einer Nonce-Kollision bleibt damit weit unter jeder praktischen Grenze
  (etwa 2³² Speichervorgänge pro Schlüssel).
- **Standardparameter:** Argon2id mit 64 MiB, 3 Durchläufen und 4 Lanes (zweite Empfehlung aus
  RFC 9106), 16-Byte-Salt, 32-Byte-Schlüssel. Kann die installierte OpenSSL-Version kein Argon2id,
  nimmt fckNotes scrypt mit N = 2¹⁷, r = 8 und p = 1. Die Parameter stehen in jeder Datei, damit spätere
  Versionen sie erhöhen können, ohne alte Dateien zu brechen.
- **Grenzen beim Lesen:** Bevor die Schlüsselableitung läuft, prüft fckNotes die Parameter
  (Argon2id ≤ 1 GiB Speicher und ≤ 64 Durchläufe, scrypt N ≤ 2²²). Eine manipulierte Datei kann so
  keinen Speicher- oder Rechenzeit-Angriff auslösen.
- **Passwort:** Unicode-NFC-normalisiert, dann UTF-8. „Käse“ ergibt denselben Schlüssel, egal wie das
  „ä“ eingegeben wurde.

Fehlerarten: „Falsches Passwort oder die Datei wurde verändert“ (GCM kann beides nicht unterscheiden),
„keine verschlüsselte fckNotes-Notiz“ (Magic fehlt, Datei zu kurz, unzulässige Parameter) und
„Formatversion ist neuer als diese fckNotes-Version“.

## Wo Klartext nicht hinkommt

| Stelle | Verhalten bei `.ntx` |
|---|---|
| Datei auf der Platte | nur Chiffretext, atomar geschrieben, die Temp-Datei enthält ebenfalls nur Chiffretext |
| Versionsverlauf (`history/`) | nie ein Schnappschuss; „Datei verschlüsseln“ löscht den Verlauf des Originals |
| Volltextsuche, Ersetzen in Dateien | Inhalt wird nie gelesen, nur der Dateiname ist auffindbar |
| Wiki-Link-Index, unverlinkte Erwähnungen | Inhalt wird nie gelesen oder indexiert |
| Grammatikprüfung (LanguageTool) | immer aus; der Text würde sonst über HTTP gesendet |
| Rechtschreibung | nur lokal im Speicher; „Zum Wörterbuch hinzufügen“ fehlt, weil `user_dictionary.txt` Klartext ist |
| `config.json` | nur Pfade offener Tabs und zuletzt geöffneter Dateien, nie Inhalt |
| Toasts, Statusleiste, Fenstertitel | nur Dateiname |
| Split View | eine `.ntx` wird nicht als zweite Ansicht geöffnet |
| Umbenennen im Baum | `.ntx` lässt sich weder anhängen noch entfernen, dafür gibt es „Datei verschlüsseln“ |

## Was die Verschlüsselung nicht leistet

- **Dateinamen und Ordner sind nicht verschlüsselt.** Auch Größe (ungefähr die Textlänge) und
  Änderungszeit bleiben sichtbar.
- **Laufender Rechner:** Solange eine Notiz entsperrt ist, steht der Klartext im Arbeitsspeicher.
  Python kann Speicher nicht zuverlässig überschreiben. Das Betriebssystem kann ihn in die
  Auslagerungsdatei oder den Ruhezustand schreiben. Wer das ausschließen will, braucht zusätzlich
  eine Festplattenverschlüsselung (BitLocker, LUKS).
- **Zwischenablage:** Kopierter Text verlässt fckNotes. Windows-Zwischenablage-Verlauf und Cloud-Sync
  sind außerhalb von fckNotes' Kontrolle.
- **Beim Verschlüsseln einer vorhandenen Datei** lag der Klartext vorher schon auf der Platte. Der
  Papierkorb, SSD-Wear-Leveling, Backups und Schattenkopien können Reste behalten.
- **Schwache Passwörter** schützt keine KDF. Argon2id verlangsamt das Raten, ein kurzes oder
  bekanntes Passwort bleibt trotzdem erratbar. Vier zufällige Wörter sind ein guter Anfang.
- **Keine Mehrbenutzer-Funktionen:** kein Teilen, keine Schlüsseldateien, kein Hardware-Token.

## Code und Tests

- `notex/core/crypto_notes.py`: Format, Schlüsselableitung, Ver- und Entschlüsselung (ohne Qt)
- `tests/test_crypto_notes.py`: Roundtrip mit Argon2id und scrypt, falsches Passwort, Manipulation
  jedes Header-Bytes und des Chiffretexts, Abschneiden und Anhängen, neue Nonce bei jedem Speichern,
  gleiches Salt pro Sitzung, unbekannte Formatversion und KDF, unzulässige Parameter vor der KDF,
  Unicode-Normalisierung, Schlüssel nie im `repr`
- `tests/test_search.py`, `tests/test_history.py`: `.ntx` erscheint nie im Volltext oder Verlauf
