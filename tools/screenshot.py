"""Startet fckNotes offscreen mit Testdaten und speichert Screenshots wichtiger Zustände.

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

if os.environ.get("QT_QPA_PLATFORM", "offscreen") == "offscreen":
    # Virtueller Full-HD-Bildschirm: sonst ist er 800×600 und Qt kürzt lange Menüs auf diese Höhe
    import json as _json
    import tempfile as _tempfile
    _screens = Path(_tempfile.gettempdir()) / "notex-offscreen-screens.json"
    _screens.write_text(_json.dumps({"screens": [{"name": "shot", "x": 0, "y": 0, "width": 1920, "height": 1080,
                                                   "logicalDpi": 96, "dpr": 1}]}), encoding="utf-8")
    os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={_screens}"
if os.environ.get("NOTEX_SCALE"):
    os.environ["QT_SCALE_FACTOR"] = os.environ["NOTEX_SCALE"]

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Testdaten in einem Temp-Ordner, damit das Projekt sauber bleibt
WORK = Path(tempfile.mkdtemp(prefix="notex-shots-"))
os.environ["NOTEX_ROOT"] = str(WORK)

from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from notex import APP_NAME  # noqa: E402
from notex.app import create_app, create_window  # noqa: E402
from notex.core.theme_model import theme_from_preset  # noqa: E402
from notex.theme.manager import theme_manager  # noqa: E402
from notex.ui.settings_dialog import SettingsDialog  # noqa: E402
from notex.theme.theme import style_menu  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs"
OUT.mkdir(parents=True, exist_ok=True)

# „Dieser PC" wie auf einem typischen Windows-Rechner zeigen – nicht die Laufwerke der Build-Umgebung
from notex.core import places as _places  # noqa: E402
_places.drive_places = lambda: [_places.Place("drive:C", "C:\\", Path.home(), "drive", "hard-drive"),
                                _places.Place("drive:D", "D:\\", Path.home(), "drive", "hard-drive")]

SPELL_SAMPLE = (
    "# Rechtschreibung\n\n"
    "fckNotes prüft Wörter offline mit Hunspell. Ein Tippfehller wie dieser bekommt eine rote Wellenlinie,\n"
    "und im Kontextmenü stehen Vorschläge. Das Wort das gerade getippt wird bleibt bis zur Pause unmarkiert.\n\n"
    "URLs wie https://languagetool.org, Pfade wie C:\\fckNotes\\data und `inline_code` werden ausgelassen.\n\n"
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
    "2026-09-26 08:31:32 DEBUG Konfiguration aus C:\\Apps\\fckNotes\\config.json geladen\n"
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
    "Projekte/fckNotes/nachschlagen.md": (
        "# Wörter zum Nachschlagen\n\nSerendipität ist ein schönes Wort für glückliche Zufallsfunde.\n\n"
        "Ein Haus am Fluss, eine Bank im Park.\n"),
    "Projekte/fckNotes/vorschau.md": PREVIEW_SAMPLE,
    "Projekte/fckNotes/rechtschreibung.md": SPELL_SAMPLE,
    "Projekte/Python/snippets.py": CODE_SAMPLE,
    "Projekte/fckNotes/server.log": LOG_SAMPLE,
    "Projekte/Python/wiki.md": WIKI_SAMPLE,
    "Projekte/fckNotes/links.txt": (
        "Lange Zeilen brechen um, nichts scrollt seitlich:\n\n"
        "https://github.com/CustomCock/fckNotes/blob/main/notex/ui/editor.py#L120-L180?utm_source=readme&utm_campaign=portable_editor_2026\n\n"
        "SHA-256: 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n\n"
        "- Listenpunkte behalten beim Umbruch ihre Einrückung, auch wenn der Text so lang ist, dass er über mehrere Zeilen läuft und weiterläuft.\n"
        "  - Verschachtelte Punkte ebenso, hier mit einem Windows-Pfad: C:\\Users\\Philipp\\Documents\\fckNotes\\data\\Projekte\\fckNotes\\links.txt\n"
        "1. Nummerierte Listen genauso, damit die Struktur beim Lesen erkennbar bleibt, egal wie schmal das Fenster gerade ist.\n"
    ),
    "Projekte/fckNotes/README.md": "# fckNotes\n\nPortabler Explorer + Editor für Textdateien.\n\n## Ziele\n\n- portabel\n- schnell\n- ruhig im Design\n",
    "Projekte/fckNotes/todo.txt": "[ ] Suche testen\n[x] Encoding-Erkennung\n[ ] Release taggen, siehe [[wiki]]\n[ ] Screenshot für README (wiki-Seite prüfen)\n",
    "Projekte/Python/notizen.md": "# Python-Notizen\n\n## Dataclasses\n\nEin `@dataclass` erzeugt __init__, __repr__ und __eq__ automatisch.\nFrozen dataclasses sind unveränderlich – gut für Design-Tokens.\n\n## Pathlib\n\n`Path(__file__).resolve().parent` liefert den Ordner der Datei.\nDas ist die Grundlage für portable Apps: Root relativ zur EXE ermitteln.\n\n## Threads\n\nEin `threading.Event` ist die einfachste Art, einen Worker sauber abzubrechen.\nDie Suche in fckNotes prüft das Event einmal pro Datei.\n",
    "Security/osint-checkliste.md": "# OSINT-Checkliste\n\n1. Domain: whois, DNS, Subdomains\n2. Personen: Usernames, Profile, Leaks\n3. Infrastruktur: Ports, Banner, Zertifikate\n\nImmer dokumentieren, welche Quelle welchen Fund geliefert hat.\n",
    "Security/lpic1-lernplan.md": "# LPIC-1 Lernplan\n\nWoche 1: Dateisystem, Pfade, Rechte\nWoche 2: Prozesse, Threads, Signale\nWoche 3: Shell, Pipes, Textwerkzeuge\nWoche 4: Pakete, Dienste, Logs\n",
    "Tagebuch/2026-09.txt": "26.09. Design-Phase gestartet. Tokens, Typografie, das Blatt.\n27.09. Komponenten: Baum, Tabs, Suche.\n",
    "config-beispiel.ini": "[allgemein]\nname = fckNotes\nportabel = ja\n",
}


def write_sample() -> None:
    data = WORK / "data"
    for rel, text in SAMPLE.items():
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def save(widget, name: str) -> None:
    # Die Schritte sind vorab getaktet; läuft einer lang, feuert der nächste sofort – dann nicht mitten
    # in einer Tab-Überblendung aufnehmen
    from notex.ui.editor_tabs import FadeOverlay
    for fade in widget.window().findChildren(FadeOverlay):
        fade.hide()
    pixmap = widget.grab()
    pixmap.save(str(OUT / f"{name}.png"))
    print("gespeichert:", OUT / f"{name}.png")


def compose(window, popup, name: str, offset: QPoint) -> None:
    """Fenster + Popup (Menü) in ein Bild zeichnen, weil offscreen kein Screen-Grab geht."""
    from notex.ui.editor_tabs import FadeOverlay
    for fade in window.findChildren(FadeOverlay):
        fade.hide()
    # Popup ganz ins Bild holen (exec() würde es am Bildschirmrand ebenso verschieben)
    size = popup.size().expandedTo(popup.sizeHint())
    offset = QPoint(min(offset.x(), window.width() - size.width() - 8), min(offset.y(), window.height() - size.height() - 8))
    base = window.grab().toImage()
    top = popup.grab().toImage()
    painter = QPainter(base)
    painter.drawImage(offset, top)
    painter.end()
    base.save(str(OUT / f"{name}.png"))
    print("gespeichert:", OUT / f"{name}.png")


def _sample_pdf(path: Path) -> None:
    """Kleines PDF mit Text und Lesezeichen (ohne Zusatzwerkzeug)."""
    pages = [["Einleitung", "fckNotes liest PDFs nur und zeigt Lesezeichen links an. Markierter Text", "wird als Zitat mit Quelle in die Notiz im anderen Teil eingefuegt."],
             ["Kapitel Zwei", "Hier steht das Suchwort Quokka einmal."], ["Kapitel Drei", "Schluss."]]
    n = len(pages)
    page_ids = [5 + i * 2 for i in range(n)]
    content_ids = [6 + i * 2 for i in range(n)]
    out_ids = [5 + n * 2 + i for i in range(n)]
    objs = {1: "<< /Type /Catalog /Pages 2 0 R /Outlines 4 0 R /PageMode /UseOutlines >>",
            2: "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{p} 0 R" for p in page_ids), n),
            3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            4: f"<< /Type /Outlines /First {out_ids[0]} 0 R /Last {out_ids[-1]} 0 R /Count {n} >>"}
    for i, lines in enumerate(pages):
        ops = ["BT /F1 22 Tf 72 760 Td (%s) Tj ET" % lines[0]]
        ops += ["BT /F1 12 Tf 72 %d Td (%s) Tj ET" % (720 - 16 * k, line) for k, line in enumerate(lines[1:])]
        stream = "\n".join(ops)
        objs[content_ids[i]] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
        objs[page_ids[i]] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {content_ids[i]} 0 R "
                             f"/Resources << /Font << /F1 3 0 R >> >> >>")
        prev = f"/Prev {out_ids[i - 1]} 0 R " if i else ""
        nxt = f"/Next {out_ids[i + 1]} 0 R " if i + 1 < n else ""
        objs[out_ids[i]] = f"<< /Title ({lines[0]}) /Parent 4 0 R {prev}{nxt}/Dest [{page_ids[i]} 0 R /XYZ 0 800 0] >>"
    data = b"%PDF-1.4\n"
    offsets = {}
    for key in sorted(objs):
        offsets[key] = len(data)
        data += f"{key} 0 obj\n{objs[key]}\nendobj\n".encode("latin-1")
    xref, count = len(data), max(objs) + 1
    data += f"xref\n0 {count}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offsets[k]:010d} 00000 n \n".encode() for k in range(1, count))
    data += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(data)


def main() -> int:
    write_sample()
    httpd = HTTPServer(("127.0.0.1", 0), FakeLanguageTool)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    (WORK / "variables.json").write_text(json.dumps({"version": 1, "variables": [
        {"name": "gruss", "value": "Mit freundlichen Grüßen", "description": "Briefschluss"},
        {"name": "name", "value": "Alex Beispiel", "description": "Unterschrift"},
        {"name": "firma_tel", "value": "+49 30 1234567", "description": "Telefon Büro"},
        {"name": "23", "value": "Paragraph 23 der Vereinbarung", "description": ""},
        {"name": "adresse", "value": "Musterweg 1\n12345 Berlin", "description": "Postanschrift"},
        {"name": "gute_reise", "value": "Gute Reise und bis bald!", "description": ""}]}, ensure_ascii=False),
        encoding="utf-8")
    (WORK / "user_dictionary.txt").write_text("fckNotes\nHunspell\nLanguageTool\n", encoding="utf-8")
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
        tree.restore_expanded(["Projekte", "Projekte/fckNotes", "Projekte/Python", "Security"])
        later(400, s_tree)

    def s_tree():
        save(window, "02-tree")
        window.tabs.open_file(data / "Projekte/Python/notizen.md")
        window.tabs.open_file(data / "Projekte/fckNotes/todo.txt")
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
        index = tree.index_for(data / "Projekte/fckNotes/todo.txt")
        tree.setCurrentIndex(index)
        rect = tree.visualRect(index)
        menu = tree.build_context_menu(data / "Projekte/fckNotes/todo.txt")
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
        later(1400, lambda: (window.resize(1280, 800), window.tabs.open_file(data / "Projekte/fckNotes/links.txt")))
        later(1900, lambda: save(window, "19-wrap-long-lines"))
        later(2000, s_spelling_open)

    def s_spelling_open():
        editor = window.tabs.open_file(data / "Projekte/fckNotes/rechtschreibung.md")
        window.sidebar.tree.select_path(data / "Projekte/fckNotes/rechtschreibung.md")
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
        later(2200, lambda: window.tabs.open_file(data / "Projekte/fckNotes/server.log"))
        later(2600, lambda: save(window, "25-syntax-log"))
        # v1.2: Markdown-Vorschau geteilt
        later(2700, lambda: (window.tabs.open_file(data / "Projekte/fckNotes/vorschau.md"), window.set_preview_mode("split")))
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
            target = data / "Projekte/fckNotes/README.md"
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
        later(6500, lambda: window.new_week())
        later(7000, lambda: save(window, "31-new-week"))
        def open_update():
            from notex.core.update_check import Release
            from notex.ui.update_service import UpdateDialog
            release = Release((1, 5, 0), "v1.5.0", f"{APP_NAME} 1.5.0", "https://github.com/CustomCock/fckNotes/releases/tag/v1.5.0",
                              "2026-10-10T10:00:00Z", "## Neu\n- Beispielhafte Versionshinweise\n- Noch ein Punkt\n\n"
                              "**Full Changelog**: v1.4.0...v1.5.0")
            window._shot_update = UpdateDialog(window, release)
            window._shot_update.show()
        later(7100, open_update)
        later(7500, lambda: save(window._shot_update, "32-update"))
        # v1.5: Kontextmenü und Nachschlage-Karte (vorbereitete Ergebnisse, kein Netz)
        def lookup_shots():
            from notex.core import lookup as lk
            window._shot_update.close()
            editor = window.tabs.open_file(data / "Projekte/fckNotes/nachschlagen.md")
            QApplication.processEvents()
            found = editor.document().find("Serendipität")
            editor.setTextCursor(found)
            menu = editor.build_context_menu(editor.cursorRect(found).center())
            menu.show()
            origin = editor.viewport().mapTo(window, editor.cursorRect(found).bottomRight())
            compose(window, menu, "33-context-menu", origin + QPoint(4, 4))
            menu.close()
            card = window._lookup_card()
            window._shot_card = card
            anchor = editor.term_rect()
            summary = lk.Summary("wikipedia", "de", "Serendipität", "glücklicher Zufallsfund",
                                 "Serendipität bezeichnet eine zufällige Beobachtung von etwas ursprünglich nicht "
                                 "Gesuchtem, das sich als neue und überraschende Entdeckung erweist. Der Begriff geht "
                                 "auf das persische Märchen „Die drei Prinzen von Serendip“ zurück, das Horace Walpole "
                                 "1754 in einem Brief erwähnte. In der Wissenschaftsgeschichte gelten die Entdeckung des "
                                 "Penicillins und der Röntgenstrahlung als bekannte Beispiele.",
                                 "https://de.wikipedia.org/wiki/Serendipit%C3%A4t")
            card.show_result("wikipedia", "Serendipität", summary, anchor, ["de", "en"])
            later_rel(300, lambda: compose_card(card, "34-lookup-wikipedia"))
            definition = lk.Definition("wiktionary", "de", "Haus", "Deutsch", [lk.PartOfSpeech("Substantiv", [
                "Gebäude, das Menschen zum Wohnen dient", "(übertragen): alle Bewohner eines Hauses",
                "(Astrologie): einer der zwölf Abschnitte des Tierkreises", "Dynastie, Adelsgeschlecht",
                "(Theater): Spielstätte", "Firma, Unternehmen", "Parlament, Kammer"])],
                "haʊ̯s, Plural ˈhɔɪ̯zɐ", "mittelhochdeutsch hūs, althochdeutsch hūs", "https://de.wiktionary.org/wiki/Haus")
            later_rel(500, lambda: card.show_result("wiktionary", "Haus", definition, anchor, ["de", "en"]))
            later_rel(800, lambda: compose_card(card, "35-lookup-wiktionary"))
            disamb = lk.Disambiguation("wikipedia", "de", "Bank", [
                ("Bank (Möbel)", "eine Sitzgelegenheit für mehrere Personen"),
                ("Bank (Kreditinstitut)", "ein Unternehmen, das Geldgeschäfte betreibt"),
                ("Sandbank", "eine Erhebung im Meer"), ("Werkbank", "ein Arbeitstisch"),
                ("Bank (Einheit)", "eine Speichereinheit")], "https://de.wikipedia.org/wiki/Bank")
            later_rel(1000, lambda: card.show_result("wikipedia", "Bank", disamb, anchor, ["de", "en"]))
            later_rel(1300, lambda: compose_card(card, "36-lookup-disambiguation"))
            later_rel(1500, lambda: card.show_error("wikipedia", "Serendipität", "offline", anchor))
            later_rel(1800, lambda: compose_card(card, "37-lookup-error"))
            later_rel(2000, lambda: (card.close(), block_f_shots()))

        def compose_card(card, name):
            origin = window.mapFromGlobal(card.geometry().topLeft())
            compose(window, card, name, origin)

        def later_rel(ms, fn):
            QTimer.singleShot(ms, fn)

        later(7600, lookup_shots)

    def block_f_shots():
        """Block F: Bild, CSV-Tabelle, JSON-Baum/-Fehler, Hex + Typwarnung, Prüfsummen, Live-Log, PDF mit Zitat."""
        from PySide6.QtGui import QColor, QLinearGradient
        from notex.ui.hash_dialog import HashDialog

        def later_rel(ms, fn):
            QTimer.singleShot(ms, fn)

        files = data / "Dateien"
        files.mkdir(exist_ok=True)
        image = QImage(640, 400, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        gradient = QLinearGradient(0, 0, 640, 400)
        gradient.setColorAt(0, QColor("#2f4a66"))
        gradient.setColorAt(1, QColor("#c9a46a"))
        painter.fillRect(image.rect(), gradient)
        painter.end()
        image.save(str(files / "skizze.png"))
        (files / "preise.csv").write_text("Produkt;Preis;Menge;Lager\nÄpfel;3,50;10;Nord\nBirnen;12,00;2;Süd\n"
                                          "\"Kiwi; grün\";1,20;100;Nord\nMango;2,75;18;West\nFeigen;7,90;4;Süd\n",
                                          encoding="utf-8")
        (files / "team.json").write_text('{"team":"fckNotes","users":[{"name":"Ada","rolle":"Admin","aktiv":true},'
                                         '{"name":"Linus","tags":["kernel","git"],"alter":36}],"version":1.10}\n',
                                         encoding="utf-8")
        (files / "kaputt.json").write_text('{\n  "name": "fckNotes",\n  "tags": ["a", "b",]\n}\n', encoding="utf-8")
        (files / "rechnung.pdf").write_bytes(b"MZ" + b"\x00" * 58 + b"\x40\x00\x00\x00" + b"PE\x00\x00"
                                             + bytes(range(256)) * 6 + b"This program cannot be run in DOS mode.")
        (files / "server.log").write_text("".join(
            f"2026-09-26 10:{i:02d}:00 {'ERROR' if i % 9 == 0 else 'WARN' if i % 5 == 0 else 'INFO'} "
            f"{'Verbindung zur Datenbank verloren' if i % 9 == 0 else 'Antwortzeit hoch' if i % 5 == 0 else 'Anfrage ok'}"
            f" (#{i})\n" for i in range(60)), encoding="utf-8")
        _sample_pdf(files / "Bericht.pdf")
        window.resize(1280, 800)

        def shot_image():
            window.tabs.open_file(files / "skizze.png")
            later_rel(300, lambda: save(window, "38-image-tab"))
            later_rel(500, shot_csv)

        def shot_csv():
            window.tabs.open_file(files / "preise.csv")
            window.set_preview_mode("table")
            view = window.tabs.current_page().data_view
            view._sort_by(1)
            later_rel(300, lambda: save(window, "39-csv-table"))
            later_rel(500, shot_json)

        def shot_json():
            window.tabs.open_file(files / "team.json")
            window.set_preview_mode("tree")
            view = window.tabs.current_page().data_view
            view._expand_levels(2)
            users = view.tree.topLevelItem(0).child(1)
            view.tree.setCurrentItem(users.child(1).child(0) if users.child(1).childCount() else users)
            later_rel(300, lambda: save(window, "40-json-tree"))
            later_rel(500, lambda: window.tabs.open_file(files / "kaputt.json"))
            later_rel(1400, lambda: save(window, "41-json-error"))
            later_rel(1600, shot_hex)

        def shot_hex():
            window.tabs.open_file(files / "rechnung.pdf")
            viewer = window.tabs.current_viewer()
            viewer.area.anchor = 0x40
            viewer.area.set_cursor(0x43, extend=True)
            later_rel(300, lambda: save(window, "42-hex-view"))
            later_rel(500, shot_hash)

        def shot_hash():
            dialog = HashDialog(window, files / "skizze.png")
            dialog.show()

            def finish():
                dialog.compare.setText(dialog.fields["sha256"].text().upper())
                dialog.move(window.geometry().center() - dialog.rect().center())
                compose(window, dialog, "43-checksums", window.mapFromGlobal(dialog.geometry().topLeft()))
                dialog.close()
                shot_live()
            later_rel(600, finish)

        def shot_live():
            window.toggle_live(files / "server.log")
            view = window.tabs.current_page().data_view
            view.level_box.setCurrentIndex(1)
            view._apply_filter()
            with open(files / "server.log", "a", encoding="utf-8") as handle:
                handle.write("2026-09-26 11:00:00 ERROR Festplatte fast voll (#60)\n")
            later_rel(900, lambda: save(window, "44-live-log"))
            later_rel(1100, lambda: (window.toggle_live(), shot_pdf()))

        def shot_pdf():
            window.tabs.open_file(files / "Bericht.pdf")
            viewer = window.tabs.current_viewer()
            if not window.tabs.is_split:
                window.toggle_split()
            window.tabs.set_active(window.tabs.groups[1])
            note = data / "Projekte/fckNotes/zitate.md"
            note.write_text("# Zitate\n\nAus dem Bericht:\n", encoding="utf-8")
            editor = window.tabs.open_file(note)
            cursor = editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            editor.setTextCursor(cursor)
            canvas = viewer.canvas
            canvas.selection = canvas._select(0, (70, 110), (400, 140))
            canvas.selection_page = 0
            canvas.selection_changed.emit()
            viewer.quote()
            later_rel(900, lambda: save(window, "45-pdf-quote"))
            later_rel(1100, finish_all)

        def finish_all():
            for editor in window.tabs.editors():
                editor.document().setModified(False)
            modules_shots()

        def modules_shots():
            """Block F (1.7.0): Einstellungen → Module, Variablen im Editor, Vorschläge, Einstellungen → Variablen."""
            from PySide6.QtGui import QTextCursor
            if window.tabs.is_split:
                window.toggle_split()
            note = data / "Projekte/fckNotes/brief.md"
            note.write_text("# Brief an Frau Muster\n\nSehr geehrte Frau Muster,\n\nwie besprochen gilt §23 auch "
                            "für Ihr Projekt. Der Paragraph \\§23 im Gesetz ist etwas anderes.\n\nRückfragen gern "
                            "unter §firma_tel.\n\n§gruss\n§name\n\nAdresse: §adresse\n", encoding="utf-8")
            editor = window.tabs.open_file(note)
            dialog = SettingsDialog(window, window.theme_store)
            dialog.show_category("Module")
            dialog.show()
            offset = QPoint((window.width() - dialog.width()) // 2, (window.height() - dialog.height()) // 2)

            def variables_page():
                compose(window, dialog, "46-settings-modules", offset)
                dialog.show_category("Variablen")
                later_rel(200, lambda: (compose(window, dialog, "49-settings-variables", offset), dialog.reject(),
                                        later_rel(200, editor_shots)))

            def editor_shots():
                save(window, "47-variables-editor")
                cursor = editor.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                editor.setTextCursor(cursor)
                editor.insert_variable_prefix()
                editor.textCursor().insertText("g")
                editor._maybe_complete()
                popup = window._completions.get(id(editor))
                later_rel(300, lambda: (compose(window, popup, "48-variables-completion",
                                                window.mapFromGlobal(popup.geometry().topLeft())) if popup else None,
                                        popup.hide() if popup else None, done()))

            def done():
                editor.document().setModified(False)
                forensics_shots()
            later_rel(400, variables_page)

        def forensics_shots():
            """Block G (1.8.0): Hex mit Werte-Zeile + Kopiermenü, Strings, Eingebettete Dateien, Entropie."""
            import io
            import struct
            import zipfile
            import zlib
            from PySide6.QtWidgets import QMenu
            for key in ("strings", "embedded", "entropy"):
                window.modules.set_enabled(key, True)

            def chunk(kind, data):
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
            image = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(b"\x00" + b"\x30\x60\x90" * 64)) + chunk(b"IEND", b""))
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("notiz.txt", "Treffpunkt: Bahnhof, 18 Uhr")
            rng = __import__("random").Random(3)
            noise = bytes(rng.getrandbits(8) for _ in range(40_000)).replace(b"MZ", b"mz").replace(b"BM", b"bm")
            text = ("Setup-Protokoll: Verbindung zu http://update.example.com/v2/pkg herstellen. "
                    "Konfiguration in C:\\ProgramData\\Beispiel\\settings.ini, Kontakt support@example.com, "
                    "Server 192.168.20.14, HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. ").encode()
            blob = (b"MZ" + b"\x00" * 62 + text * 30 + "Unicode-Kennung: fckNotes-Probe".encode("utf-16-le")
                    + b"\x00" * 20_000 + noise + image + b"ANHANG hinter IEND" + b"\x00" * 64 + archive.getvalue()
                    + text * 10)
            sample = files / "probe.bin"
            sample.write_bytes(blob)
            viewer = window.tabs.open_viewer(sample, "hex")
            viewer.select_range(0x60, 4)
            menu = style_menu(QMenu(viewer.area))
            for label in ("Kopieren als Hex  (4 Bytes)", "Kopieren als Text (ASCII)", "Kopieren als Base64",
                          "Kopieren als C-Array"):
                menu.addAction(label)
            later_rel(300, lambda: (compose(window, menu, "50-hex-copy-inspector",
                                            viewer.area.mapTo(window, viewer.area.rect().center())), strings_shot()))

            def dialog_shot(dialog, name, then):
                dialog.show()
                dialog.move(window.geometry().center() - dialog.rect().center())

                def grab():
                    compose(window, dialog, name, window.mapFromGlobal(dialog.geometry().topLeft()))
                    dialog.close()
                    then()
                later_rel(1200, grab)

            def strings_shot():
                window.show_strings(sample)
                dialog = window._analysis_dialogs["strings"][-1]
                dialog.category.setCurrentIndex(1)
                dialog_shot(dialog, "51-strings", embedded_shot)

            def embedded_shot():
                window.show_embedded(sample)
                dialog_shot(window._analysis_dialogs["embedded"][-1], "52-embedded-files", entropy_shot)

            def entropy_shot():
                window.show_entropy(sample)
                dialog = window._analysis_dialogs["entropy"][-1]
                dialog_shot(dialog, "53-entropy", lambda: block_h_shots(dialog_shot))

        def block_h_shots(dialog_shot):
            """Block H (1.9.0): Metadaten, YARA, Zeitleiste, IOC entschärfen."""
            import sys as _sys
            from notex.core import timeline as tl
            _sys.path.insert(0, str(ROOT / "tests"))
            from test_metadata import jpeg
            for key in ("metadata", "yara", "timeline", "ioc"):
                window.modules.set_enabled(key, True)
            photo = files / "urlaub.jpg"
            photo.write_bytes(jpeg())
            rule = files / "c2-beispiel.yar"
            rule.write_text('rule C2_Beispiel : c2\n{\n    meta:\n        author = "fckNotes"\n    strings:\n'
                            '        $url = "update.example.com" ascii nocase\n        $mz  = { 4D 5A }\n'
                            '        $reg = "CurrentVersion\\\\Run" ascii\n    condition:\n        $mz at 0 and any of '
                            '($url, $reg)\n}\n', encoding="utf-8")
            timeline_path = files / "Vorfall Webserver.md"
            text = tl.new_text("Vorfall Webserver")
            for when, source, what, tags in (
                    ("2026-09-26T13:58:02+02:00", "proxy.log", "Download update.exe von update[.]example[.]com", "#malware"),
                    ("2026-09-26T14:03:11+02:00", "auth.log", "Fehlgeschlagener Login root von 203.0.113.5", "#ssh #bruteforce"),
                    ("2026-09-26T14:05:40+02:00", "auth.log", "Login root von 203.0.113.5 erfolgreich", "#ssh"),
                    ("2026-09-26T12:07:00Z", "EDR", "Neuer Dienst „UpdSvc“ installiert", "#persistenz"),
                    ("2026-09-26T14:20:00+02:00", "Analyst", "Host isoliert, Abbild gesichert (B-20260926-01)", "#reaktion")):
                entry = tl.Entry(tl.parse_iso(when), source, what, tags.split())
                text = tl.add_entry(text, entry)[0]
            timeline_path.write_text(text, encoding="utf-8")

            def metadata_shot():
                window.show_metadata(photo)
                dialog_shot(window._analysis_dialogs["metadata"][-1], "54-metadata", yara_shot)

            def yara_shot():
                window.tabs.open_file(rule)
                window.test_yara(target=files)
                dialog_shot(window._analysis_dialogs["yara"][-1], "55-yara", timeline_shot)

            def timeline_shot():
                window.tabs.open_file(timeline_path)
                window.show_timeline()
                dialog = window._analysis_dialogs["timeline"][-1]
                dialog.mode.setCurrentIndex(1)
                dialog_shot(dialog, "56-timeline", ioc_shot)

            def ioc_shot():
                note = files / "IOCs.md"
                note.write_text("# IOCs aus dem Vorfall\n\n- C2: http://update.example.com/v2/gate.php\n"
                                "- Angreifer: 203.0.113.5, 2001:db8::bad:1\n- Phishing von billing@example.org\n"
                                "- Datei: update.exe (setup.py bleibt unverändert)\n\n```\n"
                                "curl http://update.example.com/v2/pkg\n```\n", encoding="utf-8")
                editor = window.tabs.open_file(note)
                window.convert_iocs(True)
                later_rel(400, lambda: (save(window, "57-ioc-defanged"), editor.document().setModified(False),
                                        block_i_shots(dialog_shot)))
            metadata_shot()

        def block_i_shots(dialog_shot):
            """Block I (1.10.0): IP-Übersicht, Port nachschlagen, RDAP-Karte (Beispieldaten, kein Netz)."""
            from notex.core import rdap
            from notex.ui.ports_dialog import PortDialog
            from notex.ui.rdap_dialog import RdapDialog
            from test_rdap import ROUTES, FakeNet
            for key in ("ip_conflicts", "rdap"):
                window.modules.set_enabled(key, True)
            (files / "Netz Büro.md").write_text(
                "# Netz Büro\n\n| Host | IP | Rolle |\n|---|---|---|\n| router | 10.20.0.1 | Gateway |\n"
                "| fileserver | 10.20.0.5 | NAS |\n| drucker-og | 10.20.0.20 | |\n| backup | 10.20.0.30 | |\n",
                encoding="utf-8")
            (files / "Server.md").write_text("10.20.0.5   web-intern\n10.20.0.40  monitoring\n"
                                             "10.20.1.10  vpn-gw\n", encoding="utf-8")

            def ip_shot():
                window.refresh_ip_index(full=True)
                later_rel(800, open_ip)

            def open_ip():
                window.show_ip_overview()
                dialog = window._analysis_dialogs["ip_conflicts"][-1]
                dialog.network.setText("10.20.0.0/24")
                dialog.exclusions.setText("10.20.0.100-10.20.0.199")
                dialog_shot(dialog, "58-ip-overview", port_shot)

            def port_shot():
                dialog_shot(PortDialog(window, "445"), "59-port-lookup", rdap_shot)

            def rdap_shot():
                client = rdap.Client(FakeNet(ROUTES), lambda _s: None)
                dialog_shot(RdapDialog(window, client, "8.8.8.8"), "60-rdap-card", scanner_shot)

            def scanner_shot():
                from test_scan import FakeReader, FakeWriter
                from notex.core import scan as scanmod
                from notex.ui.scan_dialog import ScanDialog
                ports = {"192.168.1.5": {80: b"HTTP/1.1 200 OK\r\nServer: nginx/1.25\r\n\r\n<title>NAS</title>",
                                         22: b"SSH-2.0-OpenSSH_9.6\r\n", 445: b""},
                         "192.168.1.7": {3389: b""},
                         "192.168.1.20": {80: b"HTTP/1.1 200 OK\r\nServer: lighttpd\r\n\r\n"}}

                async def fake(ip, port, **k):
                    table = ports.get(ip, {})
                    if port not in table:
                        raise ConnectionRefusedError()
                    return FakeReader(table[port]), FakeWriter()
                scanmod.asyncio.open_connection = fake
                scanmod.arp_table = lambda runner=None: {"192.168.1.5": "AA:BB:CC:00:11:22",
                                                         "192.168.1.7": "DE:AD:BE:EF:00:07"}
                window.modules.set_enabled("scanner", True)
                dialog = ScanDialog(window)
                dialog.show()
                dialog.move(window.geometry().center() - dialog.rect().center())
                dialog.target.setText("192.168.1.0/24")
                dialog.ports.setEnabled(True)
                dialog.ports.setText("22,80,443,445,3389")
                dialog.profile.setCurrentIndex(2)
                dialog.start()

                def grab():
                    compose(window, dialog, "61-scanner", window.mapFromGlobal(dialog.geometry().topLeft()))
                    dialog.close()
                    logs_shot()
                later_rel(6000, grab)

            def logs_shot():
                from notex.ui.logauth_dialog import LogAuthDialog
                log = files / "auth.log"
                rows = []
                for i in range(6):
                    rows.append(f"Sep 27 04:0{i}:11 web sshd[10{i}]: Failed password for root from 203.0.113.5 "
                                f"port 5{i}234 ssh2")
                rows.append("Sep 27 04:07:00 web sshd[120]: Accepted password for root from 203.0.113.5 port 55250 ssh2")
                rows.append("Sep 27 04:08:00 web useradd[2000]: new user: name=hacker, UID=0, GID=0, home=/root, "
                            "shell=/bin/bash")
                rows.append("Sep 27 04:08:05 web usermod[2001]: add 'hacker' to group 'sudo'")
                rows.append("Sep 27 05:00:00 web sudo:    bob : TTY=pts/0 ; USER=root ; COMMAND=/bin/cat /etc/shadow")
                log.write_text("\n".join(rows) + "\n", encoding="utf-8")
                window.modules.set_enabled("logs", True)
                dialog = LogAuthDialog(window, log)
                dialog.show()
                dialog.move(window.geometry().center() - dialog.rect().center())

                def grab():
                    compose(window, dialog, "62-logauth", window.mapFromGlobal(dialog.geometry().topLeft()))
                    dialog.close()
                    pcap_shot()
                later_rel(1200, grab)

            def pcap_shot():
                import shutil as _shutil
                from notex.ui.pcap_dialog import PcapDialog
                fixture = ROOT / "tests" / "fixtures" / "beispiel_traffic.pcap"
                _shutil.copyfile(fixture, files / "beispiel_traffic.pcap")
                window.modules.set_enabled("pcap", True)
                dialog = PcapDialog(window, files / "beispiel_traffic.pcap")
                dialog.show()
                dialog.move(window.geometry().center() - dialog.rect().center())

                def grab():
                    dialog.tabs.setCurrentWidget(dialog.t_hosts)
                    compose(window, dialog, "63-pcap", window.mapFromGlobal(dialog.geometry().topLeft()))
                    dialog.close()
                    finish()
                later_rel(1200, grab)
            ip_shot()

        def finish():
            window.close()
            app.quit()

        shot_image()

    later(500, s_empty)
    later(150000, app.quit)
    code = app.exec()
    httpd.shutdown()
    httpd.server_close()
    shutil.rmtree(WORK, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
