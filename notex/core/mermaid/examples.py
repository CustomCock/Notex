"""Startbeispiele je Diagrammtyp für „Mermaid-Diagramm einfügen“ (Palette)."""
from __future__ import annotations

EXAMPLES: dict[str, tuple[str, str]] = {
    "flowchart": ("Flussdiagramm", """flowchart TD
    A[Start] --> B{Alles klar?}
    B -- Ja --> C[Weiter]
    B -- Nein --> D[Nachfragen]
    D --> B"""),
    "sequence": ("Sequenzdiagramm", """sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Anfrage
    activate S
    S-->>C: Antwort
    deactivate S"""),
    "class": ("Klassendiagramm", """classDiagram
    class Notiz {
      +str titel
      +speichern() bool
    }
    class Ordner
    Ordner "1" --> "*" Notiz : enthält"""),
    "state": ("Zustandsdiagramm", """stateDiagram-v2
    [*] --> Entwurf
    Entwurf --> Prüfung : einreichen
    Prüfung --> Entwurf : ablehnen
    Prüfung --> Fertig : freigeben
    Fertig --> [*]"""),
    "er": ("ER-Diagramm", """erDiagram
    KUNDE ||--o{ BESTELLUNG : gibt_auf
    KUNDE {
      int id PK
      string name
    }
    BESTELLUNG {
      int id PK
      int kunde_id FK
    }"""),
    "pie": ("Kreisdiagramm", """pie showData title Zeitaufwand
    "Planung" : 3
    "Umsetzung" : 8
    "Tests" : 4"""),
    "gantt": ("Gantt-Diagramm", """gantt
    title Projektplan
    dateFormat YYYY-MM-DD
    section Vorbereitung
    Analyse      :a1, 2025-01-06, 5d
    Konzept      :after a1, 3d
    section Umsetzung
    Bauen        :crit, b1, 2025-01-15, 10d
    Abnahme      :milestone, after b1, 0d"""),
}


def fence(kind: str) -> str:
    """Beispiel als fertiger ```mermaid-Block (mit Zeilenumbruch am Ende)."""
    return f"```mermaid\n{EXAMPLES[kind][1]}\n```\n"


def insertion(kind: str, text_before_cursor: str) -> str:
    """Text zum Einfügen an der Cursorposition: der Block beginnt immer auf einer eigenen Zeile."""
    lead = "\n" if text_before_cursor and not text_before_cursor.endswith("\n") else ""
    return lead + fence(kind)
