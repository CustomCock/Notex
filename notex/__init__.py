"""Portabler Explorer + Editor für Textdateien (Python-Paket `notex`; Anzeigename siehe APP_NAME)."""

__version__ = "1.16.0"
# Anzeigename – vorläufig, bis ein freier Name gefunden ist. Ein Namenswechsel ist NUR diese Zeile
# (plus Build-Workflow/README); alles Sichtbare liest APP_NAME bzw. EXE_FILE.
APP_NAME = "fckNotes"
EXE_NAME = APP_NAME             # Dateiname der ausführbaren Datei (Windows: + ".exe")
EXE_FILE = f"{EXE_NAME}.exe"
# Interne Kennungen – bleiben bei einer Umbenennung gleich, damit Bestehendes weiter passt:
APP_ID = "Notex.Notex"          # AppUserModelID: Taskleisten-Gruppierung und Icon unter Windows
PROG_ID = "Notex.TextFile"      # ProgID für die Dateizuordnung
REG_KEY = "Notex"               # Registry-Schlüsselname (Capabilities, RegisteredApplications, Kontextmenü-Verb)
LEGACY_EXE_FILES = ("Notex.exe",)   # frühere EXE-Namen – deren „Öffnen mit“-Einträge werden aufgeräumt
