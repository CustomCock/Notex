"""Windows-Dateizuordnung für Notex – nur auf Knopfdruck, nur in HKCU, kein Admin.

Was angelegt wird (Microsoft-Doku „Default Programs“ / „File Types“), alles unter einem
frei wählbaren Präfix (Standard: HKCU\\Software):
  Classes\\Notex.TextFile                      ProgID mit DefaultIcon und shell\\open\\command
  Classes\\.txt\\OpenWithProgids\\Notex.TextFile  Notex erscheint bei „Öffnen mit“ – die bestehende
                                               Standard-Zuordnung bleibt unangetastet
  Classes\\Applications\\Notex.exe             FriendlyAppName, SupportedTypes, shell\\open\\command
  Notex\\Capabilities (+ FileAssociations)     für die Windows-Standard-Apps
  RegisteredApplications\\Notex                zeigt auf Capabilities
  Classes\\SystemFileAssociations\\.txt\\shell\\Notex  Kontextmenü „Mit Notex öffnen“ (Windows 11:
                                               im klassischen Menü unter „Weitere Optionen“)
Nichts davon berührt UserChoice; den Standard wählt der Nutzer selbst in den Windows-Einstellungen.

Die Registry steckt hinter einem kleinen Backend-Protokoll, damit die Logik ohne Windows
testbar ist (MemoryRegistry) und echte Tests in einen Test-Unterschlüssel schreiben können.
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from notex import APP_NAME, EXE_FILE, LEGACY_EXE_FILES, PROG_ID, REG_KEY

DEFAULT_PREFIX = r"Software"
EXE_NAME = EXE_FILE
SUPPORTED_EXTENSIONS = [".txt", ".md", ".log", ".csv", ".json", ".ini"]
DEFAULT_EXTENSIONS = [".txt"]


class Registry(Protocol):
    """Minimaler Ausschnitt der Registry-API: Werte lesen/schreiben, Schlüssel löschen, Kinder listen."""

    def set_value(self, key: str, name: str | None, value: str) -> None: ...
    def get_value(self, key: str, name: str | None) -> str | None: ...
    def delete_tree(self, key: str) -> None: ...
    def delete_value(self, key: str, name: str) -> None: ...
    def subkeys(self, key: str) -> list[str]: ...
    def exists(self, key: str) -> bool: ...


class MemoryRegistry:
    """Registry-Ersatz für Tests und Nicht-Windows: ein dict mit Pfaden als Schlüssel."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str | None, str]] = {}

    def _norm(self, key: str) -> str:
        return key.strip("\\").lower()

    def set_value(self, key: str, name: str | None, value: str) -> None:
        self.data.setdefault(self._norm(key), {})[name] = value

    def get_value(self, key: str, name: str | None) -> str | None:
        return self.data.get(self._norm(key), {}).get(name)

    def delete_tree(self, key: str) -> None:
        prefix = self._norm(key)
        for existing in list(self.data):
            if existing == prefix or existing.startswith(prefix + "\\"):
                del self.data[existing]

    def delete_value(self, key: str, name: str) -> None:
        self.data.get(self._norm(key), {}).pop(name, None)

    def subkeys(self, key: str) -> list[str]:
        prefix = self._norm(key) + "\\"
        names = {existing[len(prefix):].split("\\")[0] for existing in self.data if existing.startswith(prefix)}
        return sorted(names)

    def exists(self, key: str) -> bool:
        prefix = self._norm(key)
        return any(existing == prefix or existing.startswith(prefix + "\\") for existing in self.data)


class WinRegistry:
    """Echte Registry unter HKEY_CURRENT_USER (nur Windows)."""

    def __init__(self) -> None:
        import winreg
        self.winreg = winreg
        self.root = winreg.HKEY_CURRENT_USER

    def set_value(self, key: str, name: str | None, value: str) -> None:
        with self.winreg.CreateKeyEx(self.root, key, 0, self.winreg.KEY_SET_VALUE) as handle:
            self.winreg.SetValueEx(handle, name, 0, self.winreg.REG_SZ, value)

    def get_value(self, key: str, name: str | None) -> str | None:
        try:
            with self.winreg.OpenKey(self.root, key) as handle:
                value, _ = self.winreg.QueryValueEx(handle, name)
                return str(value)
        except OSError:
            return None

    def delete_tree(self, key: str) -> None:
        for child in self.subkeys(key):
            self.delete_tree(f"{key}\\{child}")
        try:
            self.winreg.DeleteKey(self.root, key)
        except OSError:
            pass

    def delete_value(self, key: str, name: str) -> None:
        try:
            with self.winreg.OpenKey(self.root, key, 0, self.winreg.KEY_SET_VALUE) as handle:
                self.winreg.DeleteValue(handle, name)
        except OSError:
            pass

    def subkeys(self, key: str) -> list[str]:
        names = []
        try:
            with self.winreg.OpenKey(self.root, key) as handle:
                index = 0
                while True:
                    try:
                        names.append(self.winreg.EnumKey(handle, index))
                        index += 1
                    except OSError:
                        break
        except OSError:
            pass
        return names

    def exists(self, key: str) -> bool:
        try:
            with self.winreg.OpenKey(self.root, key):
                return True
        except OSError:
            return False


@dataclass
class AssociationStatus:
    registered: bool = False
    exe_path: str = ""
    extensions: list[str] = field(default_factory=list)

    def matches(self, current_exe: str) -> bool:
        return self.registered and self.exe_path.lower() == current_exe.lower()

    @property
    def exe_exists(self) -> bool:
        """Zeigt die Registrierung noch auf eine vorhandene Datei? (Ordner gelöscht/verschoben → False)"""
        return self.registered and bool(self.exe_path) and Path(self.exe_path).is_file()


class FileAssociation:
    def __init__(self, registry: Registry, exe_path: str, prefix: str = DEFAULT_PREFIX) -> None:
        self.reg = registry
        self.exe_path = exe_path
        self.prefix = prefix.rstrip("\\")

    # ---- Pfade --------------------------------------------------------------------
    @property
    def classes(self) -> str:
        return f"{self.prefix}\\Classes"

    @property
    def progid_key(self) -> str:
        return f"{self.classes}\\{PROG_ID}"

    @property
    def app_key(self) -> str:
        return f"{self.classes}\\Applications\\{EXE_NAME}"

    @property
    def capabilities_key(self) -> str:
        return f"{self.prefix}\\{REG_KEY}\\Capabilities"

    def _legacy_app_keys(self) -> list[str]:
        return [f"{self.classes}\\Applications\\{name}" for name in LEGACY_EXE_FILES if name != EXE_NAME]

    @property
    def registered_apps_key(self) -> str:
        return f"{self.prefix}\\RegisteredApplications"

    def _command(self) -> str:
        return f'"{self.exe_path}" "%1"'

    # ---- Registrieren / Entfernen ------------------------------------------------------
    def register(self, extensions: list[str]) -> None:
        extensions = [e.lower() for e in extensions if e.lower() in SUPPORTED_EXTENSIONS] or DEFAULT_EXTENSIONS
        reg = self.reg
        # ProgID
        reg.set_value(self.progid_key, None, f"{APP_NAME} Textdatei")
        reg.set_value(self.progid_key, "FriendlyTypeName", f"{APP_NAME} Textdatei")
        reg.set_value(f"{self.progid_key}\\DefaultIcon", None, f"{self.exe_path},0")
        reg.set_value(f"{self.progid_key}\\shell\\open", None, f"Mit {APP_NAME} öffnen")
        reg.set_value(f"{self.progid_key}\\shell\\open\\command", None, self._command())
        # Applications\\<exe>: „Öffnen mit“-Liste (Einträge früherer EXE-Namen entfernen, sonst doppelt/verwaist)
        for legacy in self._legacy_app_keys():
            reg.delete_tree(legacy)
        reg.set_value(self.app_key, "FriendlyAppName", APP_NAME)
        reg.set_value(f"{self.app_key}\\DefaultIcon", None, f"{self.exe_path},0")
        reg.set_value(f"{self.app_key}\\shell\\open\\command", None, self._command())
        # Capabilities + RegisteredApplications: Standard-Apps
        reg.set_value(self.capabilities_key, "ApplicationName", APP_NAME)
        reg.set_value(self.capabilities_key, "ApplicationDescription", "Portabler Explorer + Editor für Textdateien")
        reg.set_value(self.registered_apps_key, REG_KEY, self.capabilities_key.split("\\", 1)[1] if self.prefix.lower().startswith("software") else self.capabilities_key)
        # Endungen: nur OpenWithProgids + SupportedTypes, bestehende Standard-Zuordnung bleibt
        for old in self.status().extensions:
            if old not in extensions:
                self._unlink_extension(old)
        for ext in extensions:
            reg.set_value(f"{self.classes}\\{ext}\\OpenWithProgids", PROG_ID, "")
            reg.set_value(f"{self.app_key}\\SupportedTypes", ext, "")
            reg.set_value(f"{self.capabilities_key}\\FileAssociations", ext, PROG_ID)
            # Kontextmenü-Verb für die Endung, unabhängig vom Standardprogramm
            reg.set_value(self._verb_key(ext), None, f"Mit {APP_NAME} öffnen")
            reg.set_value(self._verb_key(ext), "Icon", f"{self.exe_path},0")
            reg.set_value(f"{self._verb_key(ext)}\\command", None, self._command())
        self._notify()

    def _verb_key(self, ext: str) -> str:
        return f"{self.classes}\\SystemFileAssociations\\{ext}\\shell\\{REG_KEY}"

    def _unlink_extension(self, ext: str) -> None:
        self.reg.delete_tree(self._verb_key(ext))
        self.reg.delete_value(f"{self.classes}\\{ext}\\OpenWithProgids", PROG_ID)
        self.reg.delete_value(f"{self.app_key}\\SupportedTypes", ext)
        self.reg.delete_value(f"{self.capabilities_key}\\FileAssociations", ext)

    def unregister(self) -> None:
        """Räumt restlos auf, was register() angelegt hat – fremde Zuordnungen bleiben."""
        for ext in SUPPORTED_EXTENSIONS:
            self._unlink_extension(ext)
        self.reg.delete_tree(self.progid_key)
        self.reg.delete_tree(self.app_key)
        for legacy in self._legacy_app_keys():
            self.reg.delete_tree(legacy)
        self.reg.delete_tree(f"{self.prefix}\\{REG_KEY}")
        self.reg.delete_value(self.registered_apps_key, REG_KEY)
        self._notify()

    def update_path(self) -> None:
        """Ordner verschoben: nur die Pfade neu schreiben, Endungen bleiben."""
        status = self.status()
        if status.registered:
            self.register(status.extensions or DEFAULT_EXTENSIONS)

    # ---- Status --------------------------------------------------------------------------
    def status(self) -> AssociationStatus:
        command = self.reg.get_value(f"{self.progid_key}\\shell\\open\\command", None)
        if not command:
            return AssociationStatus()
        exe = command.split('"')[1] if command.startswith('"') else command.split(" ")[0]
        extensions = [ext for ext in SUPPORTED_EXTENSIONS
                      if self.reg.get_value(f"{self.classes}\\{ext}\\OpenWithProgids", PROG_ID) is not None]
        return AssociationStatus(registered=True, exe_path=exe, extensions=extensions)

    @staticmethod
    def _notify() -> None:
        """Explorer Bescheid sagen, dass sich Zuordnungen geändert haben (SHChangeNotify)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST = 0x08000000, 0x0000
            ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
        except Exception:  # noqa: BLE001
            pass


def is_temporary_location(exe_path: str, temp_dirs: list[str] | None = None) -> bool:
    """Läuft die EXE aus einem temporären Ordner? Typisch, wenn Notex.exe direkt aus dem ZIP gestartet wurde:
    Windows entpackt dann nach %TEMP%, und data/ + config.json würden dort landen und verschwinden."""
    if not exe_path:
        return False
    candidates = temp_dirs if temp_dirs is not None else [
        tempfile.gettempdir(), os.environ.get("TEMP", ""), os.environ.get("TMP", ""),
    ]

    def norm(path: str) -> str:   # Windows-Pfade vergleichen: Trenner vereinheitlichen, Groß/Klein egal
        return path.replace("\\", "/").rstrip("/").lower()

    exe = norm(exe_path)
    if any(temp and exe.startswith(norm(temp) + "/") for temp in candidates):
        return True
    # Explorer-Vorschau aus ZIP: ...\Temp1_Notex-v1.1.0.zip\Notex\Notex.exe
    return any(part.startswith("temp") and part.endswith(".zip") for part in exe.split("/"))


def real_registry() -> Registry | None:
    if sys.platform != "win32":
        return None
    return WinRegistry()


def current_exe() -> str | None:
    """Pfad der gebauten Notex.exe – None im Dev-Modus (dort wird nicht registriert)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return None


def build_association() -> FileAssociation | None:
    """FileAssociation für die laufende Notex.exe, oder None (Dev-Modus / kein Windows)."""
    exe = current_exe()
    registry = real_registry()
    if exe is None or registry is None:
        return None
    return FileAssociation(registry, exe)
