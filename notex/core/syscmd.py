"""System-Befehle (ping, tracert/traceroute, ipconfig, arp) ausführen und ihre Ausgabe robust lesen.

Windows-Konsolenprogramme schreiben in der OEM-Codepage (deutsch: cp850), Python würde mit `text=True` aber
die ANSI-Codepage (cp1252) annehmen. Schon „Ping-Statistik für" enthält dort das undefinierte Byte 0x81 →
UnicodeDecodeError bei JEDEM Ping auf deutschem Windows. Darum: Bytes lesen und selbst dekodieren
(OEM-Codepage, unlesbare Zeichen ersetzen statt abbrechen).
"""
from __future__ import annotations

import locale
import subprocess
import sys

NO_WINDOW = 0x08000000           # CREATE_NO_WINDOW: kein aufblitzendes Konsolenfenster (nur Windows)


def console_encoding(platform: str | None = None) -> str:
    """Codepage, in der Konsolenprogramme schreiben."""
    if (platform or sys.platform).startswith("win"):
        return "oem"             # Python-Codec für die aktuelle OEM-Codepage (nur unter Windows vorhanden)
    return locale.getpreferredencoding(False) or "utf-8"


def decode(data: bytes | None, encoding: str | None = None) -> str:
    """Bytes → Text; nie eine Exception (unbekannter Codec → UTF-8, kaputte Bytes → Ersatzzeichen)."""
    if not data:
        return ""
    try:
        return data.decode(encoding or console_encoding(), errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def run(command: list[str], timeout: float = 10.0) -> tuple[int, str]:
    """Befehl ausführen → (Rückgabecode, stdout+stderr als Text). Wirft nur OSError/SubprocessError
    (Programm fehlt, Zeitüberschreitung)."""
    result = subprocess.run(command, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                            creationflags=NO_WINDOW if sys.platform.startswith("win") else 0)
    return result.returncode, decode(result.stdout) + decode(result.stderr)
