# Notex – Hinweise für Arbeitssessions

- **Zuerst `PROGRESS.md` lesen.** Dort stehen Stand, offene Punkte, getroffene Entscheidungen und der nächste Schritt.
  Nach jedem Feature aktualisieren (erledigt / offen / Entscheidungen / nächster Schritt).
- Arbeitsbranch: `claude/textbaum-text-editor-it6n6b`. Commit pro Feature, Push auf diesen Branch. Tags/Releases
  setzt der Repo-Besitzer.
- Regeln: Bestehendes darf nicht brechen (Funktionen, Design-System, Portabilität). Jedes Feature braucht
  Qt-freie Kern-Tests in `tests/` für `notex/core/`, einen Eintrag in der Command Palette, in der
  README-Tastenkürzel-Tabelle, im CHANGELOG und – falls sinnvoll – in den Einstellungen.
- Tests: `QT_QPA_PLATFORM=offscreen python -m pytest -q`. Screenshots: `python tools/screenshot.py`.
- Neue Abhängigkeiten nur begründet und gepinnt in `requirements.txt`; Build-Größe im Blick (ZIP ≈ 95 MB).
- Keine Modellnamen in Commits, Code oder Doku.
