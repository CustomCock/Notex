"""Startet Notex offscreen mit Testdaten und speichert Screenshots wichtiger Zustände.

Aufruf: python tools/screenshot.py [Zielordner]   (Default: docs/)
Nutzt QT_QPA_PLATFORM=offscreen, braucht also keinen Bildschirm – läuft auch in CI.
Mit NOTEX_SCALE=1.5 lässt sich High-DPI (150 %) prüfen.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.environ.get("NOTEX_SCALE"):
    os.environ["QT_SCALE_FACTOR"] = os.environ["NOTEX_SCALE"]

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Testdaten in einem Temp-Ordner, damit das Projekt sauber bleibt
WORK = Path(tempfile.mkdtemp(prefix="notex-shots-"))
os.environ["NOTEX_ROOT"] = str(WORK)

from PySide6.QtCore import QPoint, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from notex.app import create_app, create_window  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs"
OUT.mkdir(parents=True, exist_ok=True)

SAMPLE = {
    "Projekte/Notex/README.md": "# Notex\n\nPortabler Explorer + Editor für Textdateien.\n\n## Ziele\n\n- portabel\n- schnell\n- ruhig im Design\n",
    "Projekte/Notex/todo.txt": "[ ] Suche testen\n[x] Encoding-Erkennung\n[ ] Release v0.1.0 taggen\n[ ] Screenshot für README\n",
    "Projekte/Python/notizen.md": "# Python-Notizen\n\n## Dataclasses\n\nEin `@dataclass` erzeugt __init__, __repr__ und __eq__ automatisch.\nFrozen dataclasses sind unveränderlich – gut für Design-Tokens.\n\n## Pathlib\n\n`Path(__file__).resolve().parent` liefert den Ordner der Datei.\nDas ist die Grundlage für portable Apps: Root relativ zur EXE ermitteln.\n\n## Threads\n\nEin `threading.Event` ist die einfachste Art, einen Worker sauber abzubrechen.\nDie Suche in Notex prüft das Event einmal pro Datei.\n",
    "Projekte/Python/snippets.py": "from pathlib import Path\n\n\ndef app_root() -> Path:\n    return Path(__file__).resolve().parent\n\n\nif __name__ == \"__main__\":\n    print(app_root())\n",
    "Security/osint-checkliste.md": "# OSINT-Checkliste\n\n1. Domain: whois, DNS, Subdomains\n2. Personen: Usernames, Profile, Leaks\n3. Infrastruktur: Ports, Banner, Zertifikate\n\nImmer dokumentieren, welche Quelle welchen Fund geliefert hat.\n",
    "Security/lpic1-lernplan.md": "# LPIC-1 Lernplan\n\nWoche 1: Dateisystem, Pfade, Rechte\nWoche 2: Prozesse, Threads, Signale\nWoche 3: Shell, Pipes, Textwerkzeuge\nWoche 4: Pakete, Dienste, Logs\n",
    "Tagebuch/2026-09.txt": "26.09. Design-Phase gestartet. Tokens, Typografie, das Blatt.\n27.09. Komponenten: Baum, Tabs, Suche.\n",
    "config-beispiel.ini": "[allgemein]\nname = Notex\nportabel = ja\n",
}


def write_sample() -> None:
    data = WORK / "data"
    for rel, text in SAMPLE.items():
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def save(widget, name: str) -> None:
    pixmap = widget.grab()
    pixmap.save(str(OUT / f"{name}.png"))
    print("gespeichert:", OUT / f"{name}.png")


def compose(window, popup, name: str, offset: QPoint) -> None:
    """Fenster + Popup (Menü) in ein Bild zeichnen, weil offscreen kein Screen-Grab geht."""
    base = window.grab().toImage()
    top = popup.grab().toImage()
    painter = QPainter(base)
    painter.drawImage(offset, top)
    painter.end()
    base.save(str(OUT / f"{name}.png"))
    print("gespeichert:", OUT / f"{name}.png")


def main() -> int:
    write_sample()
    app = create_app([])
    window = create_window()
    window.resize(1280, 800)
    window.show()
    data = WORK / "data"
    steps = []

    def later(ms: int, fn) -> None:
        steps.append(QTimer.singleShot(ms, fn))

    def s_empty():
        save(window, "01-empty-state")
        tree = window.sidebar.tree
        tree.restore_expanded(["Projekte", "Projekte/Notex", "Projekte/Python", "Security"])
        later(400, s_tree)

    def s_tree():
        save(window, "02-tree")
        window.tabs.open_file(data / "Projekte/Python/notizen.md")
        window.tabs.open_file(data / "Projekte/Notex/todo.txt")
        window.tabs.open_file(data / "Projekte/Python/notizen.md")
        window.sidebar.tree.select_path(data / "Projekte/Python/notizen.md")
        editor = window.tabs.current_editor()
        editor.goto_line(9, 0, 0)
        later(300, s_file)

    def s_file():
        save(window, "03-editor")
        window.sidebar.by_name.setChecked(True)
        window.sidebar.full_text.setChecked(True)
        window.sidebar.search_field.setText("Path")
        later(900, s_search)

    def s_search():
        save(window, "04-search")
        window.sidebar.clear_search()
        window.set_sidebar_visible(False, animate=False)
        later(300, s_collapsed)

    def s_collapsed():
        save(window, "05-sidebar-collapsed")
        window.set_sidebar_visible(True, animate=False)
        later(300, s_menu)

    def s_menu():
        tree = window.sidebar.tree
        index = tree.index_for(data / "Projekte/Notex/todo.txt")
        tree.setCurrentIndex(index)
        rect = tree.visualRect(index)
        menu = tree.build_context_menu(data / "Projekte/Notex/todo.txt")
        menu.show()  # nur aufbauen, nicht exec() – sonst blockiert es
        origin = tree.viewport().mapTo(window, rect.center())
        compose(window, menu, "06-context-menu", origin + QPoint(24, 4))
        menu.close()
        window.find_bar.open(with_replace=True)
        window.find_bar.find_field.setText("Pfad")
        later(200, s_find)

    def s_find():
        save(window, "07-find-replace")
        window.find_bar.close_bar()
        window.close()
        app.quit()

    later(500, s_empty)
    later(15000, app.quit)
    code = app.exec()
    shutil.rmtree(WORK, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
