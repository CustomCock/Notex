"""Zentrale Werkzeug-Registry: welche Werkzeuge es gibt, in welcher Kategorie, für welche Dateitypen sie gelten und
welches Modul sie bereitstellt. Ohne Qt – die Oberfläche (Menü „Werkzeuge", Übersicht, Kontextmenü) liest hieraus.

So ist alles an EINER Stelle definiert und die Reihenfolge der Kategorien ist fest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Kategorien in fester Reihenfolge (Schlüssel, Anzeigename)
CATEGORIES: list[tuple[str, str]] = [
    ("analyse", "Dateianalyse"),
    ("netzwerk", "Netzwerk"),
    ("logs", "Logs & Vorfälle"),
    ("text", "Text & Daten"),
    ("doku", "Dokumentation"),
]
CATEGORY_LABELS = dict(CATEGORIES)

# Dateiart-Vokabular für die „passt zur Datei?"-Prüfung
ALL_KINDS = frozenset({"text", "binary", "image", "document", "data", "log", "pcap", "yara"})


@dataclass(frozen=True)
class Tool:
    command: str               # ID des Palette-Kommandos (wird zum Auslösen benutzt)
    name: str
    category: str              # Kategorie-Schlüssel
    module: str = ""           # Modul-Schlüssel; "" = immer verfügbar (kein Modul nötig)
    kinds: frozenset = field(default_factory=lambda: ALL_KINDS)   # passende Dateiarten
    needs_file: bool = False   # braucht eine (aktuelle oder markierte) Datei
    shortcut: str = ""
    icon: str = "wrench"
    description: str = ""


TOOLS: list[Tool] = [
    # 1. Dateianalyse
    Tool("file:hex", "Als Hex öffnen", "analyse", "hex", ALL_KINDS, True, "Ctrl+Shift+Alt+H", "binary",
         "Datei byteweise als Hexdump ansehen"),
    Tool("file:checksums", "Prüfsummen", "analyse", "hex", ALL_KINDS, True, "Ctrl+Shift+Alt+C", "hash",
         "MD5, SHA-1, SHA-256, SHA-512 berechnen und vergleichen"),
    Tool("analysis:strings", "Strings extrahieren", "analyse", "strings", ALL_KINDS, True, "Ctrl+Alt+S", "text-search",
         "Druckbare Zeichenketten aus einer (Binär-)Datei"),
    Tool("analysis:embedded", "Eingebettete Dateien", "analyse", "embedded", ALL_KINDS, True, "Ctrl+Alt+F",
         "file-search", "Dateien in Dateien finden und extrahieren"),
    Tool("analysis:entropy", "Entropie", "analyse", "entropy", ALL_KINDS, True, "Ctrl+Alt+E", "activity",
         "Entropie-Kurve – erkennt verschlüsselte/komprimierte Bereiche"),
    Tool("analysis:metadata", "Metadaten", "analyse", "metadata", frozenset({"image", "document", "binary"}), True,
         "Ctrl+Alt+M", "scan-eye", "EXIF/GPS, PDF- und Office-Metadaten anzeigen und entfernen"),
    Tool("yara:test", "YARA-Regel testen", "analyse", "yara", ALL_KINDS, True, "Ctrl+Alt+Y", "bug-play",
         "YARA-Regeln gegen Datei oder Ordner prüfen"),
    # 2. Netzwerk
    Tool("scan:open", "Netzwerk-Scanner", "netzwerk", "scanner", ALL_KINDS, False, "Ctrl+Shift+Alt+P", "radar",
         "Hosts und offene Ports im eigenen Netz prüfen"),
    Tool("ports:lookup", "Port nachschlagen", "netzwerk", "ports", ALL_KINDS, False, "Ctrl+Alt+P", "network",
         "Dienst zu einer Portnummer (offline)"),
    Tool("ip:overview", "IP-Übersicht", "netzwerk", "ip_conflicts", ALL_KINDS, False, "Ctrl+Shift+Alt+I", "server",
         "IP-Zuordnungen, Konflikte und freie Adressen"),
    Tool("rdap:lookup", "RDAP / ASN abfragen", "netzwerk", "rdap", ALL_KINDS, False, "Ctrl+Alt+R", "globe-lock",
         "Inhaber, Netzblock und ASN (nur auf Klick, Netzwerk)"),
    Tool("pcap:open", "PCAP-Übersicht", "netzwerk", "pcap", frozenset({"pcap"}), True, "Ctrl+Shift+Alt+K", "radar",
         "Mitschnitt (.pcap/.pcapng) auswerten"),
    # 3. Logs & Vorfälle
    Tool("logs:open", "Log-Auswertung", "logs", "logs", frozenset({"log", "text", "binary"}), True, "Ctrl+Shift+Alt+L",
         "scroll-text", "Log- und Ereignisdateien auswerten"),
    Tool("file:live", "Live verfolgen", "logs", "", frozenset({"log", "text"}), True, "Ctrl+Shift+Alt+F", "activity",
         "Datei live weiterlesen (wie tail -f)"),
    Tool("timeline:show", "Zeitleiste anzeigen", "logs", "timeline", ALL_KINDS, False, "Ctrl+Shift+Alt+Z", "clock-4",
         "Chronologische Ereignisliste"),
    Tool("timeline:add", "Zur Zeitleiste hinzufügen", "logs", "timeline", frozenset({"text", "log", "data"}), True,
         "Ctrl+Alt+Z", "clock-4", "Aktuelle Zeile als Zeitleisten-Eintrag"),
    Tool("evidence:new", "Beweismittel anlegen", "logs", "timeline", ALL_KINDS, False, "", "shield-check",
         "Chain-of-Custody-Notiz aus Vorlage"),
    # 4. Text & Daten
    Tool("ioc:defang", "IOCs entschärfen", "text", "ioc", frozenset({"text", "log", "data"}), True, "Ctrl+Alt+D",
         "shield", "URLs, Domains, IPs, E-Mails entschärfen"),
    Tool("ioc:refang", "IOCs wieder scharf machen", "text", "ioc", frozenset({"text", "log", "data"}), True,
         "Ctrl+Shift+Alt+D", "shield", "Entschärfte IOCs zurückverwandeln"),
    Tool("data:format", "JSON/YAML formatieren", "text", "", frozenset({"data", "text"}), True, "Shift+Alt+F",
         "braces", "JSON/YAML einrücken"),
    Tool("view:table", "CSV als Tabelle", "text", "", frozenset({"data"}), True, "", "table",
         "CSV/TSV in der Tabellenansicht öffnen"),
    Tool("var:insert", "Variable einfügen", "text", "variables", frozenset({"text", "data", "log"}), True,
         "Ctrl+Alt+V", "variable", "Textbaustein einfügen"),
    # 5. Dokumentation
    Tool("doc:templates", "Neue Datei aus Vorlage", "doku", "", ALL_KINDS, False, "Ctrl+Shift+T", "file-plus",
         "Notiz aus einer Vorlage anlegen"),
]
BY_COMMAND = {t.command: t for t in TOOLS}

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg", ".ico"}
PCAP_EXT = {".pcap", ".pcapng", ".cap"}
YARA_EXT = {".yar", ".yara"}
DATA_EXT = {".csv", ".tsv", ".json", ".yaml", ".yml"}
DOC_EXT = {".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".odt", ".ods"}
LOG_EXT = {".log", ".evtx", ".gz"}
TEXT_EXT = {".txt", ".md", ".markdown", ".ini", ".cfg", ".conf", ".xml", ".html", ".htm", ".css", ".js", ".py",
            ".sh", ".ps1", ".bat", ".sql", ".c", ".cpp", ".h", ".java", ".rs", ".go", ".rb", ".php", ".ntx"}


def file_kind(path: Path | str | None) -> str:
    """Grobe Dateiart aus Name/Endung – für die „passt das Werkzeug zur Datei?"-Prüfung. Ohne die Datei zu lesen."""
    if path is None:
        return "none"
    path = Path(path)
    ext = path.suffix.lower()
    name = path.name.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in PCAP_EXT:
        return "pcap"
    if ext in YARA_EXT:
        return "yara"
    if ext in DATA_EXT:
        return "data"
    if ext in DOC_EXT:
        return "document"
    if ext in LOG_EXT or "log" in name or name in ("auth", "secure", "syslog", "messages"):
        return "log"
    if ext in TEXT_EXT:
        return "text"
    return "binary"


def applies(tool: Tool, kind: str) -> bool:
    """Passt das Werkzeug zu einer Dateiart? Werkzeuge ohne Dateibedarf passen immer."""
    if not tool.needs_file:
        return True
    if kind == "none":
        return False
    return kind in tool.kinds


def tools_in_category(category: str, enabled: set[str]) -> list[Tool]:
    """Werkzeuge einer Kategorie, deren Modul aktiv ist (leeres Modul = immer aktiv)."""
    return [t for t in TOOLS if t.category == category and (not t.module or t.module in enabled)]


def grouped(enabled: set[str]) -> list[tuple[str, str, list[Tool]]]:
    """(Kategorie-Schlüssel, Label, Werkzeuge) in fester Reihenfolge, nur mit aktiven Modulen; leere Kategorien weg."""
    out = []
    for key, label in CATEGORIES:
        tools = tools_in_category(key, enabled)
        if tools:
            out.append((key, label, tools))
    return out


def enabled_modules(config: dict) -> set[str]:
    from notex.core.modules import BY_KEY
    state = config.get("modules", {}) if isinstance(config, dict) else {}
    result = set()
    for key, info in BY_KEY.items():
        value = state.get(key, info.default)
        if value is True:
            result.add(key)
    return result
