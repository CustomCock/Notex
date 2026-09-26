"""Baut die portable App mit PyInstaller nach dist/Notex/.

Aufruf:  python build.py
Ergebnis: dist/Notex/Notex.exe (Windows) plus _internal/ mit allen Abhängigkeiten.
Den Ordner dist/Notex kann man komplett kopieren; data/ und config.json
entstehen beim ersten Start daneben.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "notex"
# PyInstaller trennt Quelle und Ziel mit ";" auf Windows und ":" sonst
SEP = ";" if sys.platform == "win32" else ":"


def main() -> None:
    os.chdir(ROOT)
    for stale in (ROOT / "build", ROOT / "dist" / "Notex"):
        shutil.rmtree(stale, ignore_errors=True)

    args = [
        str(ROOT / "main.py"),
        "--name", "Notex",
        "--noconfirm",
        "--clean",
        "--windowed",                       # kein Konsolenfenster
        "--icon", str(PACKAGE / "assets" / "notex.ico"),
        # Nicht-Python-Dateien, die die App zur Laufzeit lädt (Pfad im Bundle wie im Quellbaum)
        "--add-data", f"{PACKAGE / 'theme' / 'dark.qss'}{SEP}notex/theme",
        "--add-data", f"{PACKAGE / 'assets'}{SEP}notex/assets",
        "--add-data", f"{PACKAGE / 'dictionaries'}{SEP}notex/dictionaries",
        "--collect-data", "enchant",   # enchant-DLLs + Provider aus dem Windows-Wheel
        # Nicht benötigte Qt-Module weglassen, damit der Ordner kleiner bleibt
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "PySide6.QtPdf",
    ]
    PyInstaller.__main__.run(args)
    print(f"\nFertig: {ROOT / 'dist' / 'Notex'}")


if __name__ == "__main__":
    main()
