"""Baut die portable App mit PyInstaller nach dist/Textbaum/.

Aufruf:  python build.py
Ergebnis: dist/Textbaum/Textbaum.exe (Windows) plus _internal/ mit allen Abhängigkeiten.
Den Ordner dist/Textbaum kann man komplett kopieren; data/ und config.json
entstehen beim ersten Start daneben.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "textbaum"
# PyInstaller trennt Quelle und Ziel mit ";" auf Windows und ":" sonst
SEP = ";" if sys.platform == "win32" else ":"


def main() -> None:
    os.chdir(ROOT)
    for stale in (ROOT / "build", ROOT / "dist" / "Textbaum"):
        shutil.rmtree(stale, ignore_errors=True)

    args = [
        str(ROOT / "main.py"),
        "--name", "Textbaum",
        "--noconfirm",
        "--clean",
        "--windowed",                       # kein Konsolenfenster
        "--icon", str(PACKAGE / "assets" / "textbaum.ico"),
        # Nicht-Python-Dateien, die die App zur Laufzeit lädt (Pfad im Bundle wie im Quellbaum)
        "--add-data", f"{PACKAGE / 'theme' / 'dark.qss'}{SEP}textbaum/theme",
        "--add-data", f"{PACKAGE / 'assets'}{SEP}textbaum/assets",
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
    print(f"\nFertig: {ROOT / 'dist' / 'Textbaum'}")


if __name__ == "__main__":
    main()
