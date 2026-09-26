"""Startet Notex offscreen mit Testdaten und speichert Screenshots wichtiger Zustände.

Aufruf: python tools/screenshot.py [Zielordner]   (Default: docs/)
Nutzt QT_QPA_PLATFORM=offscreen, braucht also keinen Bildschirm – läuft auch in CI.
Mit NOTEX_SCALE=1.5 lässt sich High-DPI (150 %) prüfen.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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
from notex.core.theme_model import theme_from_preset  # noqa: E402
from notex.theme.manager import theme_manager  # noqa: E402
from notex.ui.settings_dialog import SettingsDialog  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs"
OUT.mkdir(parents=True, exist_ok=True)

SPELL_SAMPLE = (
    "# Rechtschreibung\n\n"
    "Notex prüft Wörter offline mit Hunspell. Ein Tippfehller wie dieser bekommt eine rote Wellenlinie,\n"
    "und im Kontextmenü stehen Vorschläge. Das Wort das gerade getippt wird bleibt bis zur Pause unmarkiert.\n\n"
    "URLs wie https://languagetool.org, Pfade wie C:\\Notex\\data und `inline_code` werden ausgelassen.\n\n"
    "```python\nprint(\"in Codeblöcken wird nichts geprüft\")\n```\n\n"
    "Grammatik kommt von LanguageTool: Ich weiß daß es geht  hier.\n"
)


class FakeLanguageTool(BaseHTTPRequestHandler):
    """Antwortet wie LanguageTool, aber nur für den Beispieltext – damit der Screenshot ohne Server geht."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        matches = []
        if "geht  hier" in body:
            text = body.split("text=")[1].split("&")[0]
            from urllib.parse import unquote_plus
            text = unquote_plus(text)
            matches = [
                {"offset": text.index("daß"), "length": 3, "message": "Seit der Rechtschreibreform 1996 schreibt man „dass“.",
                 "replacements": [{"value": "dass"}], "rule": {"id": "DASS_MIT_SS", "category": {"name": "Grammatik"}}},
                {"offset": text.index("geht  hier") + 4, "length": 2, "message": "Möglicherweise doppeltes Leerzeichen.",
                 "replacements": [{"value": " "}], "rule": {"id": "WHITESPACE_RULE"}},
            ]
        payload = json.dumps({"matches": matches}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"[]")

    def log_message(self, *args):
        pass


CODE_SAMPLE = (
    "import os\nfrom pathlib import Path\n\n\ndef app_root() -> Path:\n"
    "    \"\"\"Ordner der laufenden App.\n    Im Build: neben der EXE.\"\"\"\n"
    "    if getattr(sys, \"frozen\", False):\n        return Path(sys.executable).parent  # PyInstaller\n"
    "    return Path(__file__).resolve().parent\n\n\nMAX_RETRIES = 3\n"
)
LOG_SAMPLE = (
    "2026-09-26 08:31:30 INFO  Server gestartet auf 127.0.0.1:8081\n"
    "2026-09-26 08:31:32 DEBUG Konfiguration aus C:\\Apps\\Notex\\config.json geladen\n"
    "2026-09-26 08:32:01 WARN  Langsame Antwort von 10.0.0.5 (1240 ms)\n"
    "2026-09-26 08:32:05 ERROR Verbindung zu 192.168.1.10:443 fehlgeschlagen: Timeout\n"
    "2026-09-26 08:32:06 ERROR Traceback in /var/log/app.log gespeichert\n"
)
WIKI_SAMPLE = (
    "# Python-Notizen\n\nSiehe auch [[osint-checkliste|OSINT]] und [[lpic1-lernplan#Woche 2]].\n"
    "Kaputter Link: [[gibt-es-nicht]].\n\n```python\nprint([[kein]])  # in Codeblöcken zählen Links nicht\n```\n"
)

PREVIEW_SAMPLE = (
    "# Wochenplan\n\nSiehe [[osint-checkliste|OSINT]] und die [Python-Notizen](../Python/notizen.md#Pathlib).\n\n"
    "## Aufgaben\n\n- [x] Rechtschreibprüfung testen\n- [ ] Release taggen\n- [ ] Screenshots erneuern\n\n"
    "## Notizen\n\n> Portabel heißt: alles neben der EXE, nichts in AppData.\n\n"
    "| Version | Inhalt |\n|---|---|\n| 1.1 | Wiki-Links, Syntax |\n| 1.2 | Vorschau, Split View |\n\n"
    "```python\nfrom pathlib import Path\nroot = Path(__file__).resolve().parent\n```\n\n"
    "![Logo](https://example.org/logo.png)\n"
)

SAMPLE = {
    "Projekte/Notex/vorschau.md": PREVIEW_SAMPLE,
    "Projekte/Notex/rechtschreibung.md": SPELL_SAMPLE,
    "Projekte/Python/snippets.py": CODE_SAMPLE,
    "Projekte/Notex/server.log": LOG_SAMPLE,
    "Projekte/Python/wiki.md": WIKI_SAMPLE,
    "Projekte/Notex/links.txt": (
        "Lange Zeilen brechen um, nichts scrollt seitlich:\n\n"
        "https://github.com/CustomCock/Notex/blob/main/notex/ui/editor.py#L120-L180?utm_source=readme&utm_campaign=portable_editor_2026\n\n"
        "SHA-256: 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n\n"
        "- Listenpunkte behalten beim Umbruch ihre Einrückung, auch wenn der Text so lang ist, dass er über mehrere Zeilen läuft und weiterläuft.\n"
        "  - Verschachtelte Punkte ebenso, hier mit einem Windows-Pfad: C:\\Users\\Philipp\\Documents\\Notex\\data\\Projekte\\Notex\\links.txt\n"
        "1. Nummerierte Listen genauso, damit die Struktur beim Lesen erkennbar bleibt, egal wie schmal das Fenster gerade ist.\n"
    ),
    "Projekte/Notex/README.md": "# Notex\n\nPortabler Explorer + Editor für Textdateien.\n\n## Ziele\n\n- portabel\n- schnell\n- ruhig im Design\n",
    "Projekte/Notex/todo.txt": "[ ] Suche testen\n[x] Encoding-Erkennung\n[ ] Release taggen, siehe [[wiki]]\n[ ] Screenshot für README (wiki-Seite prüfen)\n",
    "Projekte/Python/notizen.md": "# Python-Notizen\n\n## Dataclasses\n\nEin `@dataclass` erzeugt __init__, __repr__ und __eq__ automatisch.\nFrozen dataclasses sind unveränderlich – gut für Design-Tokens.\n\n## Pathlib\n\n`Path(__file__).resolve().parent` liefert den Ordner der Datei.\nDas ist die Grundlage für portable Apps: Root relativ zur EXE ermitteln.\n\n## Threads\n\nEin `threading.Event` ist die einfachste Art, einen Worker sauber abzubrechen.\nDie Suche in Notex prüft das Event einmal pro Datei.\n",
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
    httpd = HTTPServer(("127.0.0.1", 0), FakeLanguageTool)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    (WORK / "user_dictionary.txt").write_text("Notex\nHunspell\nLanguageTool\n", encoding="utf-8")
    (WORK / "config.json").write_text(json.dumps({
        "grammar": {"enabled": True, "server_url": f"http://127.0.0.1:{httpd.server_port}"},
    }), encoding="utf-8")
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
        window.tabs.save_current()   # löst den Toast aus
        later(250, s_toast)

    def s_toast():
        save(window, "08-toast")
        dialog = SettingsDialog(window, window.theme_store)
        dialog.show()
        later(300, lambda: s_settings(dialog))

    def s_settings(dialog):
        offset = QPoint((window.width() - dialog.width()) // 2, (window.height() - dialog.height()) // 2)
        compose(window, dialog, "09-settings", offset)
        dialog.show_category("Blatt")
        later(150, lambda: (compose(window, dialog, "10-settings-paper", offset), dialog.reject(), later(100, s_presets)))

    def s_presets():
        window.sidebar.tree.select_path(data / "Projekte/Python/notizen.md")
        theme_manager().apply(theme_from_preset("Mitternacht", "Sepia"))
        later(200, lambda: save(window, "11-preset-mitternacht-sepia"))
        later(400, lambda: theme_manager().apply(theme_from_preset("Warm", "Papier")))
        later(600, lambda: save(window, "12-preset-warm-papier"))
        later(800, lambda: theme_manager().apply(theme_from_preset("Graphit", "Dunkel")))
        later(1000, lambda: save(window, "13-preset-graphit-dunkel"))
        later(1200, lambda: theme_manager().apply(theme_from_preset("Matt", "Weiß")))
        later(1400, s_spelling)

    def s_spelling():
        # Bearbeitungsleiste: Markdown-Gruppe, eingeklappt, schmales Fenster mit Überlauf, lange URLs
        window.sidebar.tree.select_path(data / "Projekte/Python/notizen.md")
        window.tabs.open_file(data / "Projekte/Python/notizen.md")
        later(200, lambda: save(window, "16-toolbar-markdown"))
        later(300, lambda: window.tabs.toggle_toolbar())
        later(700, lambda: save(window, "17-toolbar-collapsed"))
        later(800, lambda: (window.tabs.toggle_toolbar(), window.resize(820, 700)))
        later(1300, lambda: save(window, "18-toolbar-overflow"))
        later(1400, lambda: (window.resize(1280, 800), window.tabs.open_file(data / "Projekte/Notex/links.txt")))
        later(1900, lambda: save(window, "19-wrap-long-lines"))
        later(2000, s_spelling_open)

    def s_spelling_open():
        editor = window.tabs.open_file(data / "Projekte/Notex/rechtschreibung.md")
        window.sidebar.tree.select_path(data / "Projekte/Notex/rechtschreibung.md")
        editor.goto_line(3, 0, 0)
        later(2800, lambda: s_spelling_menu(editor))

    def s_spelling_menu(editor):
        block = editor.document().findBlockByNumber(2)
        column = block.text().index("Tippfehller") + 4
        cursor = editor.textCursor()
        cursor.setPosition(block.position() + column)
        editor.setTextCursor(cursor)
        point = editor.cursorRect(cursor).center()
        menu = editor.build_context_menu(point)
        menu.show()
        origin = editor.viewport().mapTo(window, point)
        compose(window, menu, "14-spellcheck", origin + QPoint(8, 8))
        menu.close()
        dialog = SettingsDialog(window, window.theme_store)
        dialog.show_category("Rechtschreibung")
        dialog.show()
        offset = QPoint((window.width() - dialog.width()) // 2, (window.height() - dialog.height()) // 2)
        later(300, lambda: (compose(window, dialog, "15-settings-spelling", offset), dialog.show_category("System")))
        later(500, lambda: (compose(window, dialog, "20-settings-system", offset), dialog.reject(), later(100, s_end)))

    def s_end():
        # v1.1: Quick Open, Command Palette, Wiki-Links + Backlinks, Syntax (.py, .log, md-Fence)
        window.show_palette("files")
        window.palette.field.setText("snip")
        later(400, lambda: save(window, "21-quick-open"))
        later(500, lambda: (window.palette.close_overlay(), window.show_palette("commands"), window.palette.field.setText(">blatt")))
        later(900, lambda: save(window, "22-command-palette"))
        later(1000, lambda: (window.palette.close_overlay(), window.tabs.open_file(data / "Projekte/Python/wiki.md"),
                             window.sidebar.tree.select_path(data / "Projekte/Python/wiki.md"), window.set_backlinks_visible(True)))
        later(1600, lambda: save(window, "23-wikilinks-backlinks"))
        later(1700, lambda: (window.set_backlinks_visible(False), window.tabs.open_file(data / "Projekte/Python/snippets.py")))
        later(2100, lambda: save(window, "24-syntax-python"))
        later(2200, lambda: window.tabs.open_file(data / "Projekte/Notex/server.log"))
        later(2600, lambda: save(window, "25-syntax-log"))
        # v1.2: Markdown-Vorschau geteilt
        later(2700, lambda: (window.tabs.open_file(data / "Projekte/Notex/vorschau.md"), window.set_preview_mode("split")))
        later(3300, lambda: save(window, "26-markdown-preview"))
        later(3400, lambda: (window.set_preview_mode("edit"), window.tabs.open_file(data / "Projekte/Python/notizen.md"),
                             window.tabs.split(), window.tabs.open_file(data / "Projekte/Python/snippets.py")))
        later(4000, lambda: save(window, "27-split-view"))
        # v1.2: Ersetzen in Dateien
        later(4100, lambda: (window.tabs.unsplit(), window.sidebar.search_field.setText("portabel"),
                             window.open_replace_in_files(), window._replace_dialog.replace_field.setText("portable")))
        later(5000, lambda: save(window._replace_dialog, "28-replace-in-files"))
        # v1.3: Versionsverlauf
        def open_history():
            from notex.ui.history_dialog import HistoryDialog
            window._replace_dialog.close()
            target = data / "Projekte/Notex/README.md"
            editor = window.tabs.open_file(target)
            rel = window.tabs.relative(target)
            window.history.snapshot(rel, editor.toPlainText().replace("- schnell", "- schnell\n- klein"), now=time.time() - 3 * 86400)
            window.history.snapshot(rel, editor.toPlainText().replace("ruhig", "leise"), now=time.time() - 7200)
            window.history.snapshot(rel, editor.toPlainText(), now=time.time() - 60)
            editor.insert_text("Neuer Absatz, noch nicht gespeichert.\n\n")
            window._shot_history = HistoryDialog(window, window.history, rel, editor.toPlainText())
            window._shot_history.list.setCurrentRow(1)
            window._shot_history.show()
        later(5100, open_history)
        later(5700, lambda: save(window._shot_history, "29-history"))
        def open_locked():
            from notex.core import crypto_notes
            window._shot_history.close()
            window.tabs.current_editor().document().setModified(False)
            target = data / "Security/zugangsdaten.ntx"
            key = crypto_notes.new_key("screenshot", crypto_notes.KDF_SCRYPT, (10, 8, 1))
            target.write_bytes(crypto_notes.seal("nur ein Beispiel", key))
            window.tabs.open_file(target)
        later(5800, open_locked)
        later(6400, lambda: save(window, "30-encrypted-locked"))
        later(6500, lambda: (window.close(), app.quit()))

    later(500, s_empty)
    later(60000, app.quit)
    code = app.exec()
    httpd.shutdown()
    httpd.server_close()
    shutil.rmtree(WORK, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
