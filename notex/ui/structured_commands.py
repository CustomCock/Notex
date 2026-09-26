"""JSON/YAML im Hauptfenster: Formatieren, Minimieren, Prüfen und die Prüfung beim Tippen.

Alles läuft im Speicher auf dem Editortext; Ergebnis als EIN Undo-Schritt. Fehler erscheinen rechts in der
Statusleiste (Klick springt hin) und als rote Wellenlinie im Text. Verschlüsselte Notizen sind über
`structured.kind_for` ausgenommen (Endung .ntx).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from notex.core import structured
from notex.ui import dialogs

LIVE_DELAY_MS = 600


class StructuredCommands(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self._results: dict[str, tuple[int, structured.ParseError | None]] = {}   # Pfad → (Revision, Fehler)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(LIVE_DELAY_MS)
        self._timer.timeout.connect(self._validate_current)
        window.status.problem_clicked.connect(self.jump_to_problem)

    # ---- Hilfen -----------------------------------------------------------------------------------
    def _current(self):
        editor = self.window.tabs.current_editor()
        if editor is None or getattr(editor, "encrypted", False):
            return None, None
        return editor, structured.kind_for(editor.path)

    def _indent(self) -> int:
        return int(self.window.config.get("data_view", {}).get("json_indent", 2))

    def _toast(self, text: str, icon_name: str = "info") -> None:
        self.window.toast.show_message(text, icon_name)

    def _need(self):
        editor, kind = self._current()
        if kind is None:
            self._toast("Nur für JSON- und YAML-Dateien (.json, .yaml, .yml)")
            return None, None
        return editor, kind

    # ---- Befehle ----------------------------------------------------------------------------------
    def format(self) -> None:
        self._rewrite(minify=False)

    def minify(self) -> None:
        self._rewrite(minify=True)

    def _rewrite(self, minify: bool) -> None:
        editor, kind = self._need()
        if editor is None:
            return
        if getattr(editor, "read_only", False):
            self._toast("Die Datei ist schreibgeschützt")
            return
        self.window.tabs.flush_data_views(editor)
        text = editor.toPlainText()
        error = structured.validate(text, kind)
        if error is not None:
            self._show(editor, kind, error, move_cursor=True)
            self._toast(error.short(kind), "triangle-alert")
            return
        if kind == "yaml" and structured.yaml_has_comments(text) and not dialogs.confirm(
                self.window, "YAML formatieren",
                "Diese YAML-Datei enthält Kommentare. Beim " + ("Minimieren" if minify else "Formatieren") +
                " gehen Kommentare, Anker und die ursprüngliche Schreibweise verloren.",
                yes="Trotzdem " + ("minimieren" if minify else "formatieren"), no="Abbrechen", danger=True,
                informative="Rückgängig (Ctrl+Z) stellt den alten Text wieder her."):
            return
        try:
            new_text = structured.minify_text(text, kind) if minify else structured.format_text(text, kind, self._indent())
        except (ValueError, RecursionError) as failure:
            self._toast(str(failure), "triangle-alert")
            return
        if new_text == text:
            self._toast("Schon " + ("minimiert" if minify else "formatiert"), "check")
            return
        self.window.tabs.replace_text_keep_cursor(editor, new_text)
        self._toast(f"{kind.upper()} " + ("minimiert" if minify else f"formatiert (Einrückung {self._indent()})"), "check")

    def validate(self) -> None:
        editor, kind = self._need()
        if editor is None:
            return
        self.window.tabs.flush_data_views(editor)
        error = structured.validate(editor.toPlainText(), kind)
        self._results[str(editor.path)] = (editor.document().revision(), error)
        self._show(editor, kind, error, move_cursor=error is not None)
        self._toast(error.short(kind) if error else f"{kind.upper()} ist gültig", "triangle-alert" if error else "check")

    def copy_path(self) -> None:
        page = self.window.tabs.current_page()
        if page is None or page.view_mode != "tree" or page.data_view is None:
            self._toast("Pfad kopieren: erst mit Ctrl+Shift+V in die Baumansicht wechseln")
            return
        page.data_view.copy_path()
        if page.data_view.path_field.text():
            self._toast(f"Kopiert: {page.data_view.path_field.text()}", "copy")

    def jump_to_problem(self) -> None:
        editor, kind = self._current()
        if kind is None:
            return
        _revision, error = self._results.get(str(editor.path), (None, None))
        if error is not None:
            self._show(editor, kind, error, move_cursor=True)

    # ---- Prüfung beim Tippen und Anzeige ----------------------------------------------------------
    def refresh_status(self) -> None:
        """Aus _update_status: Ergebnis zeigen bzw. (verzögert) neu prüfen, wenn sich der Text geändert hat."""
        editor, kind = self._current()
        if kind is None:
            return
        document = editor.document()
        cached = self._results.get(str(editor.path))
        if cached is not None and cached[0] == document.revision():
            self._show(editor, kind, cached[1])
        elif document.characterCount() <= structured.MAX_LIVE_CHARS:
            if cached is not None:             # bis zur nächsten Prüfung das letzte Ergebnis zeigen (kein Flackern)
                self._show(editor, kind, cached[1])
            if not self._timer.isActive():     # nicht neu starten: beim Tippen höchstens alle 0,6 s prüfen,
                self._timer.start()            # und Status-Updates ohne Textänderung verschieben nichts
        else:
            self.window.status.set_problem("Große Datei – prüfen mit Shift+Alt+V", "ok")

    def _validate_current(self) -> None:
        editor, kind = self._current()
        if kind is None:
            return
        error = structured.validate(editor.toPlainText(), kind)
        self._results[str(editor.path)] = (editor.document().revision(), error)
        self._show(editor, kind, error)

    def _show(self, editor, kind: str, error: structured.ParseError | None, move_cursor: bool = False) -> None:
        for view in self.window.tabs.views_of(editor.path) if hasattr(self.window.tabs, "views_of") else [editor]:
            view.set_problem(error.position if error else None)
        if self.window.tabs.current_editor() is editor:
            if error is None:
                self.window.status.set_problem(f"{kind.upper()} gültig", "ok")
            else:
                self.window.status.set_problem(error.short(kind), "error",
                                               tooltip=error.short(kind) + "\nKlick springt zur Stelle")
        if move_cursor and error is not None:
            page = self.window.tabs.current_page()
            if page is not None and page.view_mode != "edit" and page.editor is editor:
                page.set_view_mode("edit")
            cursor = editor.textCursor()
            cursor.setPosition(min(error.position, editor.document().characterCount() - 1))
            editor.setTextCursor(cursor)
            editor.ensureCursorVisible()
            editor.setFocus()
