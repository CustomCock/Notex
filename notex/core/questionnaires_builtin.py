"""Mitgelieferte Fragebögen (YAML) für Block O – werden beim ersten Mal in templates/fragebogen/ geschrieben.

Eigene Fragebögen kann der Nutzer dort als weitere .yaml-Dateien ablegen (siehe README). Nichts hiervon erfasst
Passwörter, Schlüssel oder Tokens.
"""
from __future__ import annotations

BERICHTSHEFT = """\
id: berichtsheft
title: Ausbildungsnachweis (Woche)
output: |
  # Ausbildungsnachweis – Woche {{kw}}

  - **Name:** {{name}}
  - **Ausbildungsjahr:** {{jahr}}
  - **Abteilung:** {{abteilung}}
  - **Zeitraum:** {{zeitraum}}

  ## Tätigkeiten

  {{taetigkeiten}}

  ## Berufsschule

  {{schulthemen}}

  ## Summe

  - **Stunden gesamt:** {{stunden_gesamt}}
  - Besonderes (Urlaub/Krank/Feiertag): {{abwesenheit}}

  ---

  Datum, Unterschrift Azubi: ______________________

  Datum, Unterschrift Ausbilder/in: ______________________
sections:
  - id: stammdaten
    title: Stammdaten
    questions:
      - {id: name, type: text, label: Name, required: true}
      - {id: jahr, type: number, label: Ausbildungsjahr}
      - {id: abteilung, type: text, label: Abteilung}
  - id: woche
    title: Woche
    questions:
      - {id: kw, type: number, label: Kalenderwoche, required: true}
      - {id: zeitraum, type: text, label: "Zeitraum (z. B. 08.–12.09.)"}
  - id: taetigkeiten
    title: Tätigkeiten der Woche
    questions:
      - id: taetigkeiten
        type: table
        label: Was wurde gemacht?
        columns: [Tag, Tätigkeit, Stunden, Lernort]
        help: "Lernort z. B. Betrieb, Berufsschule oder ÜBS."
  - id: schule
    title: Berufsschule
    questions:
      - {id: schulthemen, type: text, label: Themen in der Berufsschule,
         chips: [Netzwerktechnik, Programmierung, Betriebssysteme, IT-Sicherheit, Datenschutz]}
  - id: summe
    title: Summe & Abwesenheit
    questions:
      - {id: stunden_gesamt, type: number, label: Stunden gesamt}
      - {id: abwesenheit, type: text, label: "Urlaub / Krank / Feiertag (falls zutreffend)"}
"""

SYSTEMCHECK = """\
id: systemcheck
title: Systemcheck beim Kunden
sections:
  - id: kopf
    title: Allgemein
    questions:
      - id: kunde
        type: text
        label: "Kunde"
        required: true
      - {id: standort, type: text, label: "Standort"}
      - {id: datum, type: date, label: "Datum"}
      - {id: techniker, type: text, label: "Techniker/in"}
      - {id: ansprechpartner, type: text, label: "Ansprechpartner beim Kunden"}
  - id: server
    title: Server & Backup
    questions:
      - {id: server_status, type: yesno, label: "Server laufen fehlerfrei?"}
      - {id: backup_ok, type: yesno, label: "Letzter Backup-Lauf erfolgreich?"}
      - {id: restore_getestet, type: yesno, label: "Wiederherstellung getestet?"}
      - {id: speicherplatz, type: text, label: "Freier Speicherplatz (Server/NAS)"}
  - id: sicherheit
    title: Updates & Schutz
    questions:
      - {id: updates, type: yesno, label: "Betriebssystem- und Software-Updates aktuell?"}
      - {id: virenschutz, type: yesno, label: "Virenschutz aktiv und aktuell?"}
      - {id: firewall, type: yesno, label: "Firewall/Router konfiguriert?"}
      - {id: zertifikate, type: text, label: "Zertifikate (Ablaufdaten)"}
  - id: infrastruktur
    title: Infrastruktur
    questions:
      - {id: wlan, type: yesno, label: "WLAN stabil und abgesichert?"}
      - {id: usv, type: yesno, label: "USV vorhanden und getestet?"}
      - {id: drucker, type: text, label: "Drucker/Peripherie"}
      - {id: voip, type: text, label: "VoIP/Telefonie"}
      - {id: fachanwendungen, type: text, label: "Fachanwendungen"}
  - id: ergebnis
    title: Befunde & Empfehlungen
    questions:
      - {id: befunde, type: text, label: "Befunde (mit Priorität)"}
      - {id: empfehlungen, type: text, label: "Empfehlungen"}
      - {id: naechste_schritte, type: text, label: "Nächste Schritte"}
      - {id: unterschrift, type: text, label: "Unterschrift Kunde (Name)"}
"""

SICHERHEITSCHECK = """\
id: sicherheits-check
title: Sicherheits-Check (kleine Unternehmen)
sections:
  - id: organisation
    title: Organisation & Verantwortung
    questions:
      - {id: verantwortlich, type: yesno, weight: 1, label: "Gibt es eine für IT-Sicherheit verantwortliche Person?"}
      - {id: richtlinien, type: yesno, weight: 1, label: "Gibt es verständliche Sicherheitsregeln für Mitarbeitende?"}
  - id: backup
    title: Backup & Wiederherstellung
    questions:
      - {id: backup, type: yesno, weight: 2, required: true, label: "Werden Daten regelmäßig gesichert?"}
      - {id: backup_offline, type: yesno, weight: 2, label: "Liegt mindestens eine Sicherung getrennt vom Netz?"}
      - {id: restore, type: yesno, weight: 2, label: "Wurde die Wiederherstellung schon einmal getestet?"}
  - id: updates
    title: Updates
    questions:
      - {id: auto_updates, type: yesno, weight: 2, label: "Werden Updates zeitnah eingespielt?"}
      - {id: eol, type: yesno, weight: 2, label: "Sind alle Systeme noch mit Sicherheitsupdates versorgt (kein EOL)?"}
  - id: konten
    title: Konten & Passwörter
    questions:
      - {id: mfa, type: yesno, weight: 2, label: "Ist Mehr-Faktor-Anmeldung (MFA) aktiv, wo möglich?"}
      - {id: admin_getrennt, type: yesno, weight: 1, label: "Sind Admin- und normale Konten getrennt?"}
      - {id: standardpw, type: yesno, weight: 2, label: "Wurden Standardpasswörter überall geändert?"}
  - id: netzwerk
    title: Netzwerk
    questions:
      - {id: segmentierung, type: yesno, weight: 1, label: "Ist das Netz sinnvoll getrennt (z. B. Gäste-WLAN separat)?"}
      - {id: fernzugriff, type: yesno, weight: 2, label: "Ist Fernzugriff abgesichert (VPN/MFA)?"}
      - {id: offene_ports, type: yesno, weight: 2, label: "Sind unnötige Dienste/Ports nach außen geschlossen?"}
  - id: endgeraete
    title: Endgeräte
    questions:
      - {id: av, type: yesno, weight: 1, label: "Virenschutz auf allen Geräten aktiv?"}
      - {id: verschluesselung, type: yesno, weight: 1, label: "Sind Datenträger verschlüsselt (z. B. BitLocker/LUKS)?"}
  - id: email
    title: E-Mail & Phishing
    questions:
      - {id: phishing_schulung, type: yesno, weight: 1, label: "Sind Mitarbeitende für Phishing sensibilisiert?"}
      - {id: spamfilter, type: yesno, weight: 1, label: "Ist ein Spam-/Malware-Filter aktiv?"}
  - id: notfall
    title: Notfall & Physisches
    questions:
      - {id: notfallplan, type: yesno, weight: 2, label: "Gibt es einen Notfallplan (wer tut was bei einem Vorfall)?"}
      - {id: zutritt, type: yesno, weight: 1, label: "Sind Serverraum/Technik vor unbefugtem Zutritt geschützt?"}
      - {id: bemerkungen, type: text, label: "Bemerkungen"}
"""

BUILTIN = {
    "berichtsheft.yaml": BERICHTSHEFT,
    "systemcheck.yaml": SYSTEMCHECK,
    "sicherheits-check.yaml": SICHERHEITSCHECK,
}
"""
Hinweis: `sicherheits-check` orientiert sich inhaltlich an gängigen Rahmenwerken (DIN SPEC 27076 CyberRisikoCheck,
BSI IT-Grundschutz), verwendet aber ausschließlich eigene Formulierungen.
"""
