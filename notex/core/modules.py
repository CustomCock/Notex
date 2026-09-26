"""Modul-Registry: Features lassen sich einzeln an- und abschalten – ohne Neustart. Ohne Qt.

Jedes Feature meldet einen Aktivator an: eine Funktion, die alles einhängt (Menüeinträge, Palette-Befehle,
Shortcuts, Panels, Hover …) und eine Rückbau-Funktion zurückgibt. Die Registry ruft den Aktivator nur, wenn das
Modul eingeschaltet ist, und den Rückbau beim Abschalten. Ein abgeschaltetes Modul hat damit nichts registriert und
lädt auch keine schweren Bibliotheken (die importiert erst der Aktivator bzw. die Aktion selbst).

Zustand: config["modules"] = {Schlüssel: bool}; fehlende Schlüssel nehmen den Standard aus MODULES.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

Undo = Callable[[], None]
Activator = Callable[[], "Undo | None"]


@dataclass(frozen=True)
class ModuleInfo:
    key: str
    name: str
    description: str
    requires: str = ""          # Hinweis auf zusätzliche Abhängigkeiten („keine“, „PyYAML“, „System-ping“ …)
    default: bool = False
    block: str = ""             # in welchem Ausbau-Block das Modul umgesetzt wird (für „kommt noch“)


MODULES: list[ModuleInfo] = [
    ModuleInfo("variables", "Variablen", "Textbausteine wie §gruss, die im Text als Wert erscheinen",
               "keine", True, "F"),
    ModuleInfo("hex", "Hex & Dateianalyse", "Hex-Ansicht, Dateityp über Magic Bytes, Prüfsummen",
               "keine", True, "G"),
    ModuleInfo("strings", "Strings", "Druckbare Zeichenketten aus Binärdateien (ASCII, UTF-16)", "keine", False, "G"),
    ModuleInfo("embedded", "Eingebettete Dateien", "Dateien in Dateien finden und extrahieren", "keine", False, "G"),
    ModuleInfo("entropy", "Entropie", "Entropie-Kurve über eine Datei", "keine", False, "G"),
    ModuleInfo("metadata", "Metadaten", "EXIF, PDF- und Office-Metadaten anzeigen und entfernen",
               "Pillow, pypdf", False, "H"),
    ModuleInfo("yara", "YARA", "YARA-Regeln hervorheben und gegen Dateien testen", "yara-python", False, "H"),
    ModuleInfo("timeline", "Zeitleiste & Beweismittel", "Zeitleisten-Notizen und Chain-of-Custody-Vorlage",
               "keine", False, "H"),
    ModuleInfo("ioc", "IOC entschärfen", "URLs, Domains, IPs, E-Mails entschärfen und wieder scharf machen",
               "keine", True, "H"),
    ModuleInfo("ports", "Port-Infos", "Offline-Portdatenbank, Hover über Portangaben", "keine", True, "I"),
    ModuleInfo("ip_conflicts", "IP-Konflikte", "IP-Zuordnungen in Notizen sammeln und Konflikte zeigen",
               "keine", False, "I"),
    ModuleInfo("rdap", "RDAP/ASN", "Inhaber, Netzblock und ASN zu IPs und Domains (nur auf Klick, Netzwerk)",
               "keine (Netzwerk)", False, "I"),
    ModuleInfo("scanner", "Netzwerk-Scanner", "Hosts und offene Ports im eigenen Netz prüfen", "keine", False, "J"),
    ModuleInfo("logs", "Log-Auswertung", "auth.log und Windows-Ereignisprotokolle auswerten", "python-evtx", False, "K"),
    ModuleInfo("pcap", "PCAP-Übersicht", "Mitschnitte (.pcap/.pcapng) zusammenfassen", "dpkt", False, "K"),
]
BY_KEY = {m.key: m for m in MODULES}


def defaults() -> dict[str, bool]:
    return {m.key: m.default for m in MODULES}


class ModuleRegistry:
    def __init__(self, config: dict) -> None:
        self.config = config
        state = config.setdefault("modules", {})
        for key, value in defaults().items():
            if not isinstance(state.get(key), bool):
                state[key] = value
        self._activators: dict[str, list[Activator]] = {}
        self._undo: dict[str, list[Undo]] = {}
        self._listeners: list[Callable[[str, bool], None]] = []

    # ---- Zustand ------------------------------------------------------------------------------
    def enabled(self, key: str) -> bool:
        if key not in BY_KEY:
            raise KeyError(f"Unbekanntes Modul: {key}")
        return bool(self.config["modules"].get(key, BY_KEY[key].default))

    def set_enabled(self, key: str, on: bool) -> None:
        if self.enabled(key) == on:
            return
        self.config["modules"][key] = on
        if on:
            for activator in self._activators.get(key, []):
                self._run(key, activator)
        else:
            self._teardown(key)
        for listener in list(self._listeners):
            listener(key, on)

    def on_change(self, listener: Callable[[str, bool], None]) -> None:
        self._listeners.append(listener)

    # ---- Beiträge ------------------------------------------------------------------------------
    def contribute(self, key: str, activator: Activator) -> None:
        """Aktivator anmelden – läuft sofort, falls das Modul an ist, sonst erst beim Einschalten."""
        if key not in BY_KEY:
            raise KeyError(f"Unbekanntes Modul: {key}")
        self._activators.setdefault(key, []).append(activator)
        if self.enabled(key):
            self._run(key, activator)

    def has_contributions(self, key: str) -> bool:
        """Ist das Modul schon umgesetzt (hat es Aktivatoren)? Sonst zeigt die Oberfläche „folgt in Block …“."""
        return bool(self._activators.get(key))

    def active_contributions(self, key: str) -> int:
        """Wie viele Beiträge gerade eingehängt sind (für Tests und die Einstellungen)."""
        return len(self._undo.get(key, []))

    def _run(self, key: str, activator: Activator) -> None:
        undo = activator()
        self._undo.setdefault(key, []).append(undo or (lambda: None))

    def _teardown(self, key: str) -> None:
        for undo in reversed(self._undo.pop(key, [])):
            undo()

    def shutdown(self) -> None:
        for key in list(self._undo):
            self._teardown(key)
