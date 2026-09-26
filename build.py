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

from notex import APP_NAME, __version__

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "notex"
# PyInstaller trennt Quelle und Ziel mit ";" auf Windows und ":" sonst
SEP = ";" if sys.platform == "win32" else ":"


def write_version_file() -> Path:
    """Windows-Dateiinfo der EXE (Rechtsklick > Eigenschaften > Details): Produkt, Version, Beschreibung."""
    parts = [int(p) for p in __version__.split(".")[:3]] + [0]
    tuple_text = ", ".join(str(p) for p in parts[:4])
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tuple_text}), prodvers=({tuple_text}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{APP_NAME}'),
      StringStruct('FileDescription', '{APP_NAME} – portabler Explorer + Editor für Textdateien'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    path = ROOT / "build" / "version_info.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def check_dependencies() -> None:
    """PyInstaller baut auch ohne PySide6 stumm weiter – dann startet die Exe mit „No module named 'PySide6'“."""
    missing = []
    for module in ("PySide6", "pygments", "enchant", "spylls", "send2trash", "markdown_it", "regex", "cryptography", "yaml", "pypdf", "yara"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        sys.exit(
            f"Fehlende Pakete im Build-Python ({sys.executable}): {', '.join(missing)}\n"
            f"Bitte mit demselben Interpreter installieren:  {sys.executable} -m pip install -r requirements-dev.txt"
        )


def main() -> None:
    os.chdir(ROOT)
    check_dependencies()
    for stale in (ROOT / "build", ROOT / "dist" / "Notex"):
        shutil.rmtree(stale, ignore_errors=True)
    version_file = write_version_file()

    args = [
        str(ROOT / "main.py"),
        "--name", "Notex",
        "--noconfirm",
        "--clean",
        "--windowed",                       # kein Konsolenfenster
        "--icon", str(PACKAGE / "assets" / "notex.ico"),
        *(["--version-file", str(version_file)] if sys.platform == "win32" else []),   # Dateiinfo gibt es nur bei Windows-EXEs
        # Nicht-Python-Dateien, die die App zur Laufzeit lädt (Pfad im Bundle wie im Quellbaum)
        "--add-data", f"{PACKAGE / 'theme' / 'dark.qss'}{SEP}notex/theme",
        "--add-data", f"{PACKAGE / 'assets'}{SEP}notex/assets",
        "--add-data", f"{PACKAGE / 'dictionaries'}{SEP}notex/dictionaries",
        "--collect-data", "enchant",   # enchant-DLLs + Provider aus dem Windows-Wheel
        # Pygments lädt Lexer dynamisch – nur die benutzten Module einsammeln (klein halten)
        *[f"--hidden-import=pygments.lexers.{m}" for m in ("python", "data", "configs", "shell", "html", "css",
                                                          "javascript", "sql", "markup", "textfmts", "special", "yara")],
        "--hidden-import=pygments.formatters",
        "--hidden-import=markdown_it", "--hidden-import=mdurl", "--hidden-import=regex", "--hidden-import=yaml", "--hidden-import=pypdf", "--hidden-import=yara", "--hidden-import=PySide6.QtPdf", "--hidden-import=cryptography.hazmat.primitives.kdf.argon2",
        # Nicht benötigte Qt-Module weglassen, damit der Ordner kleiner bleibt
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
    ]
    PyInstaller.__main__.run(args)
    # Lizenzen gehören in den Build-Ordner: eigene Lizenz, Übersicht und die Texte der Bibliotheken
    target = ROOT / "dist" / "Notex"
    for name in ("LICENSE", "THIRD_PARTY_LICENSES.md", "CHANGELOG.md"):
        shutil.copyfile(ROOT / name, target / name)
    shutil.copytree(ROOT / "licenses", target / "licenses", dirs_exist_ok=True)
    (target / "docs").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "docs" / "ENCRYPTION.md", target / "docs" / "ENCRYPTION.md")
    print(f"\nFertig: {target}")


if __name__ == "__main__":
    main()
