"""Einstiegspunkt von Textbaum.

Diese Datei ist bewusst winzig: PyInstaller bekommt sie als Startskript,
und im Dev-Modus ruft man einfach `python main.py` auf.
"""
from textbaum.app import run

if __name__ == "__main__":
    raise SystemExit(run())
