"""Linux-Desktop-Integration – nur auf Knopfdruck, nur im Benutzerordner, nie systemweit. Ohne Qt.

Angelegt wird (freedesktop.org: Desktop Entry, Shared MIME Info, Icon Theme), alles unter $XDG_DATA_HOME
(Standard ~/.local/share):
  applications/notex.desktop                 Starter mit MimeType-Liste → Notex erscheint unter „Öffnen mit“
  mime/packages/notex.xml                    MIME-Typ application/x-notex-encrypted für *.ntx
  icons/hicolor/256x256/apps/notex.png       Icon
Danach, falls vorhanden: update-desktop-database und update-mime-database (Caches aktualisieren).

Die Standard-App wird NIE gesetzt (kein `xdg-mime default`) – das entscheidet der Nutzer selbst, genau wie
unter Windows (UserChoice bleibt unangetastet). Die portable App bleibt portabel: wird der Ordner verschoben,
reicht erneutes Registrieren.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from notex import APP_NAME, __version__
from notex.core.fileops import atomic_write_bytes

DESKTOP_ID = "notex.desktop"
ICON_NAME = "notex"
NTX_MIME = "application/x-notex-encrypted"
MIME_TYPES = ["text/plain", "text/markdown", "text/x-markdown", "text/x-log", "text/csv", "application/json",
              "text/x-ini", NTX_MIME]
_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')


def data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(value) if value and Path(value).is_absolute() else Path.home() / ".local" / "share"


def quote_exec(arg: str) -> str:
    """Argument für die Exec-Zeile quoten (Desktop Entry Spec: Reserved Characters, Escape von " ` $ \\)."""
    if arg and not any(c in _RESERVED for c in arg):
        return arg
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def desktop_entry(exe: str) -> str:
    # Im Desktop-Entry selbst muss ein wörtliches "\" noch einmal verdoppelt werden (Stringwert-Escaping)
    exec_line = quote_exec(exe).replace("\\", "\\\\") + " %F"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "GenericName=Texteditor\n"
        "Comment=Portabler Explorer und Editor für Textdateien\n"
        f"Exec={exec_line}\n"
        f"Icon={ICON_NAME}\n"
        "Terminal=false\n"
        "Categories=Utility;TextEditor;\n"
        f"MimeType={';'.join(MIME_TYPES)};\n"
        f"StartupWMClass={APP_NAME}\n"
        f"X-Notex-Version={__version__}\n"
    )


def mime_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
        f'  <mime-type type="{NTX_MIME}">\n'
        f"    <comment>Verschlüsselte {APP_NAME}-Notiz</comment>\n"
        '    <magic priority="80"><match type="string" offset="0" value="NOTEXENC"/></magic>\n'
        '    <glob pattern="*.ntx"/>\n'
        "  </mime-type>\n"
        "</mime-info>\n"
    )


def exec_path_of(entry_text: str) -> str | None:
    """Pfad aus der Exec-Zeile eines (von uns geschriebenen) Desktop-Entries."""
    for line in entry_text.splitlines():
        if line.startswith("Exec="):
            value = line[5:].rsplit(" %F", 1)[0].replace("\\\\", "\\")
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
                for a, b in (('\\"', '"'), ("\\`", "`"), ("\\$", "$"), ("\\\\", "\\")):
                    value = value.replace(a, b)
            return value
    return None


@dataclass
class DesktopStatus:
    registered: bool = False
    exe_path: str = ""

    def matches(self, exe: str) -> bool:
        return self.registered and self.exe_path == exe


Runner = Callable[[list[str]], None]


def _default_runner(command: list[str]) -> None:
    if shutil.which(command[0]):
        try:
            subprocess.run(command, check=False, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


class DesktopIntegration:
    def __init__(self, exe: str, icon_source: Path, base: Path | None = None, runner: Runner | None = None) -> None:
        self.exe = exe
        self.icon_source = Path(icon_source)
        self.base = Path(base) if base is not None else data_home()
        self.run = runner or _default_runner

    @property
    def desktop_file(self) -> Path:
        return self.base / "applications" / DESKTOP_ID

    @property
    def mime_file(self) -> Path:
        return self.base / "mime" / "packages" / "notex.xml"

    @property
    def icon_file(self) -> Path:
        return self.base / "icons" / "hicolor" / "256x256" / "apps" / f"{ICON_NAME}.png"

    def install(self) -> None:
        for path in (self.desktop_file, self.mime_file, self.icon_file):
            path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self.desktop_file, desktop_entry(self.exe).encode("utf-8"))
        atomic_write_bytes(self.mime_file, mime_xml().encode("utf-8"))
        if self.icon_source.is_file():
            atomic_write_bytes(self.icon_file, self.icon_source.read_bytes())
        self._refresh()

    def uninstall(self) -> None:
        for path in (self.desktop_file, self.mime_file, self.icon_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self._refresh()

    def status(self) -> DesktopStatus:
        try:
            text = self.desktop_file.read_text(encoding="utf-8")
        except OSError:
            return DesktopStatus()
        return DesktopStatus(True, exec_path_of(text) or "")

    def _refresh(self) -> None:
        self.run(["update-desktop-database", str(self.base / "applications")])
        self.run(["update-mime-database", str(self.base / "mime")])
