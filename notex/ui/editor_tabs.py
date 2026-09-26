"""Tab-Bereich rechts: mehrere Dateien gleichzeitig offen, Dirty-State pro Tab.

Jeder Tab enthält eine EditorPage (Blatt + Schatten), die den eigentlichen Editor hält.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QTextCursor
from PySide6.QtWidgets import QMessageBox, QTabWidget, QWidget

from notex.core import fileops
from notex.core.encoding import read_text_file
from notex.core.fileops import save_text_file
from notex.core.spell import SpellChecker
from notex.paths import app_root
from notex.theme import tokens
from notex.theme.icons import icon
from notex.theme.tokens import COLORS, DURATION, FONT_SIZE
from notex.ui import anim
from notex.ui.editor import Editor
from notex.ui.grammar_service import GrammarService
from notex.ui.toolbar import EditorToolbar
from notex.ui.paper import EditorPage
from notex.ui.widgets import EditorTabBar

DIRTY_MARK = " ●"
MIN_FONT_SIZE, MAX_FONT_SIZE = 8, 40


class FadeOverlay(QWidget):
    """Liegt kurz über dem Editorbereich und blendet von Hintergrundfarbe zu durchsichtig."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.alpha = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

    def run(self, rect) -> None:
        if anim.duration(DURATION.fade) == 0:
            return
        self.setGeometry(rect)
        self.alpha = 1.0
        self.raise_()
        self.show()
        anim.animate(self, 1.0, 0.0, DURATION.fade, self._step, self.hide)

    def _step(self, value: float) -> None:
        self.alpha = value
        self.update()

    def paintEvent(self, event) -> None:
        color = QColor(COLORS.bg)
        color.setAlphaF(self.alpha)
        QPainter(self).fillRect(self.rect(), color)


class EditorTabs(QTabWidget):
    # Wird bei allem gefeuert, was die Statusleiste interessiert (Tabwechsel, Cursor, Dirty)
    status_changed = Signal()
    file_saved = Signal(Path)
    file_opened = Signal(Path)
    file_closed = Signal(Path)
    font_size_changed = Signal(int)
    text_font_changed = Signal(str)     # Familie ("" = Standard)
    files_dropped = Signal(list)        # Dateien aufs Blatt gezogen
    link_activated = Signal(object, object)     # Editor, LinkSpan
    preview_link = Signal(object, str)          # Editor, Ziel aus der Markdown-Vorschau
    view_mode_changed = Signal(str)             # "edit" | "preview" | "split" des aktuellen Tabs
    completion_requested = Signal(object, str, str)   # Editor, Art, Text
    dirty_changed = Signal(int, bool)   # Tab-Index, dirty
    tabs_emptied = Signal()             # letzter Tab dieser Gruppe geschlossen
    tab_drop = Signal(int, int, object, bool)   # Quellgruppe, Index, Zielgruppe, „neue Gruppe gewünscht“

    def __init__(self, root: Path, config: dict | None = None, shared: "EditorTabs | None" = None) -> None:
        """`shared`: zweite Gruppe des geteilten Editors – teilt Checker, Grammatikdienst und Ansichtszustand."""
        super().__init__()
        self.root = root
        self.config = config if config is not None else {}
        self.area = None                         # EditorArea, wenn es mehrere Gruppen geben kann
        if shared is not None:
            self.checker = shared.checker
            self.grammar = shared.grammar
            self.font_size = shared.font_size
            self.paper_mode = shared.paper_mode
            self.editor_actions = shared.editor_actions
            self.resolve_link = shared.resolve_link
            self.open_font_settings = shared.open_font_settings
            self.toolbar_visible = shared.toolbar_visible
            self.line_numbers = shared.line_numbers
        else:
            self.checker = SpellChecker(user_dictionary=app_root() / "user_dictionary.txt")
            self.checker.set_language(self.config.get("spellcheck", {}).get("language", "de"))
            self.grammar = GrammarService(self.config)
            self.grammar.state_changed.connect(lambda _n: self.status_changed.emit())
            if self.config.get("grammar", {}).get("enabled"):
                self.grammar.restart()
            self.font_size = FONT_SIZE.editor
            self.paper_mode = True
            self.editor_actions: dict = {}          # QActions aus dem Hauptfenster für die Bearbeitungsleiste
            self.resolve_link = lambda target: None  # setzt das Hauptfenster (Link-Index)
            self.open_font_settings = lambda: None  # setzt das Hauptfenster
            self.toolbar_visible = bool(self.config.get("toolbar_visible", True))
            self.line_numbers = bool(self.config.get("line_numbers", True))
        self.setAcceptDrops(True)
        self.tab_bar = EditorTabBar()
        self.setTabBar(self.tab_bar)
        self.tab_bar.close_requested.connect(self.close_tab)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.dirty_changed.connect(self.tab_bar.set_dirty)
        self._fade = FadeOverlay(self)
        self._last_index = -1
        self.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, index: int) -> None:
        # Kurzer Fade nur bei echtem Wechsel zwischen zwei offenen Tabs
        if index >= 0 and self._last_index >= 0 and index != self._last_index and self.currentWidget():
            self._fade.run(self.currentWidget().geometry())
        self._last_index = index
        self.currentChanged.connect(lambda _index: self.status_changed.emit())

    # ---- Zugriff ----------------------------------------------------------
    def pages(self) -> list[EditorPage]:
        return [self.widget(i) for i in range(self.count()) if isinstance(self.widget(i), EditorPage)]

    def editors(self) -> list[Editor]:
        return [page.editor for page in self.pages()]

    def current_editor(self) -> Editor | None:
        widget = self.currentWidget()
        return widget.editor if isinstance(widget, EditorPage) else None

    def page_for(self, editor: Editor) -> EditorPage | None:
        for page in self.pages():
            if page.editor is editor:
                return page
        return None

    def editor_for(self, path: Path) -> Editor | None:
        for editor in self.editors():
            if editor.path == path:
                return editor
        return None

    def is_external(self, path: Path) -> bool:
        return not fileops.is_within(path, self.root)

    def external_files(self) -> list[Path]:
        return [e.path for e in self.editors() if self.is_external(e.path)]

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def resolve_saved(self, entry: str) -> Path:
        """Eintrag aus open_tabs: relativ zu data/ oder absolut (externe Datei)."""
        path = Path(entry)
        return path if path.is_absolute() else self.root / entry

    @staticmethod
    def is_read_only(path: Path) -> bool:
        return path.exists() and not os.access(path, os.W_OK)

    # ---- Öffnen / Schließen ------------------------------------------------
    def open_file(self, path: Path, line: int | None = None, column: int = 0, length: int = 0,
                  share_from: Editor | None = None) -> Editor | None:
        """`share_from`: zweite Ansicht eines schon offenen Editors (gleiches Dokument, geteilter Editor)."""
        path = Path(path)
        editor = self.editor_for(path)
        if editor is None:
            if share_from is not None and share_from.path == path:
                from notex.core.encoding import TextFile
                text_file = TextFile("", share_from.encoding, share_from.eol)
                editor = Editor(path, text_file, self.font_size, checker=self.checker, share_with=share_from)
            else:
                try:
                    text_file = read_text_file(path)
                except OSError as error:
                    QMessageBox.warning(self, "Öffnen fehlgeschlagen", f"{self.relative(path)}\n\n{error}")
                    return None
                editor = Editor(path, text_file, self.font_size, checker=self.checker)
            editor.set_text_font(self.font_family_for(path))
            self.grammar.attach(editor)
            self._apply_spell_to(editor)
            editor.document().modificationChanged.connect(lambda _m, e=editor: self._refresh_title(e))
            editor.cursorPositionChanged.connect(self.status_changed.emit)
            editor.textChanged.connect(self.status_changed.emit)
            editor.zoom_requested.connect(self.zoom)
            editor.files_dropped.connect(self.files_dropped)
            editor.link_activated.connect(lambda span, e=editor: self.link_activated.emit(e, span))
            editor.completion_requested.connect(lambda kind, text, e=editor: self.completion_requested.emit(e, kind, text))
            if editor.highlighter is not None:
                editor.highlighter.resolve_link = self.resolve_link
                editor.highlighter.links_enabled = bool(self.config.get("wiki_links", True))
                editor.highlighter.lexer = self.lexer_for(path)
                editor.highlighter.relink()   # der erste Durchlauf lief noch ohne Resolver und Lexer
            toolbar = EditorToolbar(self.editor_actions, self, is_markdown=path.suffix.lower() == ".md")
            toolbar.set_expanded(self.toolbar_visible, animate=False)
            toolbar.visibility_changed.connect(self._on_toolbar_toggled)
            editor.set_line_numbers(self.line_numbers)
            page = EditorPage(editor, self.paper_mode, toolbar, root=self.root)
            page.sync_scroll = bool(self.config.get("preview_sync_scroll", True))
            page.link_requested.connect(lambda target, e=editor: self.preview_link.emit(e, target))
            page.view_mode_changed.connect(lambda mode, pg=page: self.view_mode_changed.emit(mode) if pg is self.currentWidget() else None)
            index = self.addTab(page, path.name)
            if page.supports_preview and self.config.get("markdown_view", "edit") != "edit":
                page.set_view_mode(self.config.get("markdown_view", "edit"))
            self.setTabToolTip(index, self.relative(path))
            if self.is_external(path):
                self.setTabIcon(index, icon("external-link"))   # dezentes Kennzeichen: außerhalb von data/
            editor.read_only = self.is_read_only(path)
            self.file_opened.emit(path)
        self.setCurrentWidget(self.page_for(editor))
        if line is not None:
            editor.goto_line(line, column, length)
        else:
            editor.setFocus()
        self.status_changed.emit()
        return editor

    def _other_views(self, editor: Editor) -> list[Editor]:
        """Weitere Ansichten desselben Dokuments in anderen Gruppen (geteilter Editor)."""
        if self.area is None:
            return []
        return [e for e in self.area.views_of(editor.path) if e is not editor]

    def _remove(self, editor: Editor) -> None:
        self.grammar.detach(editor)
        if editor.highlighter is not None and self._other_views(editor):
            editor.highlighter.remove_view(editor)
        page = self.page_for(editor)
        if page is not None:
            self.removeTab(self.indexOf(page))
            if page.preview is not None:
                page.preview.shutdown()
            page.deleteLater()
        self.file_closed.emit(editor.path)
        if self.count() == 0:
            self.tabs_emptied.emit()

    def remove_page(self, page: EditorPage, ask: bool = True) -> bool:
        editor = page.editor
        if ask and editor.is_dirty and not self._other_views(editor) and not self._ask_save(editor):
            return False
        self._remove(editor)
        self.status_changed.emit()
        return True

    def close_tab(self, index: int) -> bool:
        page = self.widget(index)
        if not isinstance(page, EditorPage):
            return False
        return self.remove_page(page, ask=True)

    def close_current(self) -> None:
        if self.count():
            self.close_tab(self.currentIndex())

    def close_paths_under(self, path: Path) -> None:
        """Nach Löschen im Baum: Tabs der Datei bzw. aller Dateien im Ordner ohne Nachfrage schließen."""
        for editor in self.editors():
            if editor.path == path or fileops.is_within(editor.path, path):
                self._remove(editor)
        self.status_changed.emit()

    def confirm_close_all(self) -> bool:
        """Vor dem Beenden: für jeden ungespeicherten Tab nachfragen. False = Abbruch."""
        asked: set[int] = set()
        for editor in self.editors():
            if editor.is_dirty and id(editor.document()) not in asked:
                asked.add(id(editor.document()))
                self.setCurrentWidget(self.page_for(editor))
                if not self._ask_save(editor):
                    return False
        return True

    def _ask_save(self, editor: Editor) -> bool:
        """Fragt: Speichern / Verwerfen / Abbrechen. Gibt False zurück, wenn abgebrochen."""
        box = QMessageBox(self)
        box.setWindowTitle("Ungespeicherte Änderungen")
        box.setText(f"„{editor.path.name}“ wurde geändert.")
        box.setInformativeText("Änderungen speichern?")
        save = box.addButton("Speichern", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Verwerfen", QMessageBox.ButtonRole.DestructiveRole)
        discard.setObjectName("Danger")
        cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() == cancel:
            return False
        if box.clickedButton() == save:
            return self.save_editor(editor)
        return True

    # ---- Speichern ---------------------------------------------------------
    def save_editor(self, editor: Editor) -> bool:
        if getattr(editor, "read_only", False) or self.is_read_only(editor.path):
            return self.save_editor_as(editor, reason="Die Datei ist schreibgeschützt.")
        try:
            save_text_file(editor.path, editor.toPlainText(), editor.encoding, editor.eol)
        except PermissionError:
            return self.save_editor_as(editor, reason="Keine Schreibrechte für diese Datei.")
        except OSError as error:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", f"{self.relative(editor.path)}\n\n{error}")
            return False
        editor.document().setModified(False)
        self.file_saved.emit(editor.path)
        self.status_changed.emit()
        return True

    def save_current(self) -> None:
        editor = self.current_editor()
        if editor is not None:
            self.save_editor(editor)

    def save_editor_as(self, editor: Editor, reason: str = "") -> bool:
        """„Speichern unter …“: neuer Pfad, Tab zieht mit, Watcher wird über file_closed/file_opened umgehängt."""
        from PySide6.QtWidgets import QFileDialog
        if reason:
            from notex.ui import dialogs
            if not dialogs.confirm(self, "Speichern unter", reason, yes="Speichern unter …", no="Abbrechen",
                                   informative="Unter einem anderen Namen oder Ort speichern?"):
                return False
        start = str(editor.path if not self.is_external(editor.path) else editor.path)
        target, _ = QFileDialog.getSaveFileName(self, "Speichern unter", start, "Textdateien (*.txt *.md *.log *.csv *.json *.ini);;Alle Dateien (*)")
        if not target:
            return False
        new_path = Path(target)
        try:
            save_text_file(new_path, editor.toPlainText(), editor.encoding, editor.eol)
        except OSError as error:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", f"{new_path}\n\n{error}")
            return False
        old = editor.path
        self.file_closed.emit(old)
        editor.path = new_path
        editor.read_only = False
        editor.document().setModified(False)
        self._refresh_title(editor)
        index = self.indexOf(self.page_for(editor))
        self.setTabIcon(index, icon("external-link") if self.is_external(new_path) else QIcon())
        self.file_opened.emit(new_path)
        self.file_saved.emit(new_path)
        self.status_changed.emit()
        return True

    def save_current_as(self) -> None:
        editor = self.current_editor()
        if editor is not None:
            self.save_editor_as(editor)

    def save_all(self) -> None:
        for editor in self.editors():
            if editor.is_dirty:
                self.save_editor(editor)

    # ---- Darstellung -------------------------------------------------------
    def _refresh_title(self, editor: Editor) -> None:
        page = self.page_for(editor)
        if page is None and self.area is not None:
            owner = self.area.group_of(editor)
            if owner is not None and owner is not self:
                owner._refresh_title(editor)
                return
        index = self.indexOf(page) if page else -1
        if index >= 0:
            self.setTabText(index, editor.path.name)
            self.setTabToolTip(index, self.relative(editor.path))
            self.dirty_changed.emit(index, editor.is_dirty)
        self.status_changed.emit()

    def rename_open_file(self, old: Path, new: Path) -> None:
        """Wenn eine offene Datei im Baum umbenannt/verschoben wurde, Tab nachziehen."""
        old, new = Path(old), Path(new)
        for editor in self.editors():
            try:
                rel = editor.path.relative_to(old)
            except ValueError:
                continue
            editor.path = new / rel if editor.path != old else new
            self._refresh_title(editor)

    def set_font_size(self, size: int) -> None:
        self.font_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))
        for page in self.pages():
            page.editor.set_font_size(self.font_size)
            page.refresh_width()
        self.font_size_changed.emit(self.font_size)

    def zoom(self, direction: int) -> None:
        if self.area is not None:
            self.area.zoom(direction)
        else:
            self.set_font_size(self.font_size + direction)

    def refresh_icon(self, editor: Editor) -> None:
        page = self.page_for(editor)
        if page is not None:
            self.setTabIcon(self.indexOf(page), icon("external-link") if self.is_external(editor.path) else QIcon())

    # ---- Tabs per Drag zwischen Gruppen -------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(EditorTabBar.TAB_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(EditorTabBar.TAB_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(EditorTabBar.TAB_MIME):
            super().dropEvent(event)
            return
        try:
            group_key, index = (int(x) for x in bytes(event.mimeData().data(EditorTabBar.TAB_MIME)).decode().split(":"))
        except ValueError:
            return
        # Ohne Teilung: Ablegen im rechten/unteren Viertel legt eine neue Gruppe an
        pos = event.position().toPoint()
        wants_split = pos.x() > self.width() * 0.75 or pos.y() > self.height() * 0.75
        event.acceptProposedAction()
        self.tab_drop.emit(group_key, index, self, wants_split)

    # ---- Textschrift (Ansichts-Einstellung, gilt für alle Dateien) --------------
    def font_family_for(self, path: Path) -> str:
        """Schrift je Dateiendung aus der Config, sonst die Textschrift des Themes."""
        by_ext = self.config.get("font_by_extension", {})
        return by_ext.get(path.suffix.lower()) or tokens.TEXT_FONT_FAMILY

    def apply_text_fonts(self) -> None:
        for page in self.pages():
            page.editor.set_text_font(self.font_family_for(page.editor.path))
            page.refresh_width()
        self.text_font_changed.emit(tokens.TEXT_FONT_FAMILY)

    def set_text_font(self, family: str) -> None:
        """Textschrift des Themes setzen (Toolbar und Einstellungen rufen dasselbe auf)."""
        from notex.theme.manager import theme_manager
        theme = theme_manager().current()
        if theme["font"]["editor_family"] != family:
            theme["font"]["editor_family"] = family
            self.config["theme"] = theme_manager().apply(theme)

    def set_paper_mode(self, enabled: bool) -> None:
        self.paper_mode = enabled
        for page in self.pages():
            page.set_paper_mode(enabled)

    def retheme(self) -> None:
        for page in self.pages():
            page.editor.set_text_font(self.font_family_for(page.editor.path))
            page.retheme()
            if page.toolbar is not None:
                page.toolbar.retheme()
            if page.editor.highlighter is not None:
                page.editor.highlighter.reset()   # Wellenlinien in neuen Theme-Farben
        self.tab_bar.update()
        self.text_font_changed.emit(tokens.TEXT_FONT_FAMILY)

    # ---- Rechtschreibung / Grammatik -------------------------------------------
    def spell_enabled_for(self, path: Path) -> bool:
        cfg = self.config.get("spellcheck", {})
        return bool(cfg.get("enabled", True)) and path.suffix.lower() in cfg.get("extensions", [])

    def grammar_enabled_for(self, path: Path) -> bool:
        cfg = self.config.get("grammar", {})
        return bool(cfg.get("enabled", False)) and path.suffix.lower() in self.config.get("spellcheck", {}).get("extensions", [])

    def _apply_spell_to(self, editor: Editor) -> None:
        grammar_on = self.grammar_enabled_for(editor.path)
        editor.set_spellcheck(self.spell_enabled_for(editor.path), grammar_on)
        if grammar_on:
            self.grammar.schedule(id(editor))

    def apply_spell_settings(self) -> None:
        """Nach Änderung in Config/Einstellungen: alle Tabs neu einstellen."""
        self.checker.set_language(self.config.get("spellcheck", {}).get("language", "de"))
        if self.config.get("grammar", {}).get("enabled"):
            self.grammar.restart()
        else:
            self.grammar.shutdown()
        for editor in self.editors():
            if editor.highlighter is not None:
                editor.highlighter.clear_grammar()
            self._apply_spell_to(editor)

    # ---- Bearbeitungsleiste ---------------------------------------------------------
    def _on_toolbar_toggled(self, expanded: bool) -> None:
        if expanded != self.toolbar_visible:
            self.toolbar_visible = expanded
            self.config["toolbar_visible"] = expanded
            for page in self.pages():
                if page.toolbar is not None and page.toolbar.expanded != expanded:
                    page.toolbar.set_expanded(expanded)

    def toggle_toolbar(self) -> None:
        self._on_toolbar_toggled(not self.toolbar_visible)

    def sync_toolbars(self) -> None:
        page = self.currentWidget()
        if isinstance(page, EditorPage) and page.toolbar is not None:
            page.toolbar.sync(page.editor)

    def set_line_numbers(self, visible: bool) -> None:
        self.line_numbers = visible
        self.config["line_numbers"] = visible
        for page in self.pages():
            page.editor.set_line_numbers(visible)
            page.refresh_width()

    def set_encoding(self, encoding: str) -> None:
        editor = self.current_editor()
        if editor is not None:
            editor.set_encoding(encoding)
            self.status_changed.emit()

    def set_eol(self, eol: str) -> None:
        editor = self.current_editor()
        if editor is not None:
            editor.set_eol(eol)
            self.status_changed.emit()

    SYNTAX_MAX_BYTES = 2 * 1024 * 1024   # größere Dateien bekommen kein Syntax-Highlighting (Ladezeit)

    def lexer_for(self, path: Path) -> str | None:
        from notex.core.syntax import lexer_for_extension
        if not self.config.get("syntax_highlighting", True) or path.suffix.lower() not in self.config.get("syntax_extensions", []):
            return None
        try:
            if path.stat().st_size > self.SYNTAX_MAX_BYTES:
                return None
        except OSError:
            pass
        return lexer_for_extension(path.suffix)

    def relink_all(self) -> None:
        """Nach Änderungen an Index oder Einstellungen: Links, Syntax und Farben neu zeichnen."""
        for editor in self.editors():
            if editor.highlighter is not None:
                editor.highlighter.links_enabled = bool(self.config.get("wiki_links", True))
                editor.highlighter.lexer = self.lexer_for(editor.path)
                editor.highlighter.relink()

    def replace_text_keep_cursor(self, editor: Editor, new_text: str) -> None:
        """Ganzen Text ersetzen (z. B. Link-Umschreibung) als ein Undo-Schritt, Cursor bleibt möglichst."""
        position = editor.textCursor().position()
        cursor = QTextCursor(editor.document())
        cursor.select(QTextCursor.SelectionType.Document)
        editor._grouped(lambda: cursor.insertText(new_text))
        c = editor.textCursor()
        c.setPosition(min(position, len(new_text)))
        editor.setTextCursor(c)

    # ---- Markdown-Vorschau ---------------------------------------------------------
    def current_page(self) -> EditorPage | None:
        widget = self.currentWidget()
        return widget if isinstance(widget, EditorPage) else None

    def view_mode(self) -> str:
        page = self.current_page()
        return page.view_mode if page is not None else "edit"

    def set_view_mode(self, mode: str) -> bool:
        """Ansicht des aktuellen Tabs; False, wenn die Datei keine Vorschau hat (kein Markdown)."""
        page = self.current_page()
        if page is None or not page.supports_preview:
            return False
        page.set_view_mode(mode)
        self.status_changed.emit()
        return True

    def cycle_view_mode(self) -> str | None:
        page = self.current_page()
        if page is None or not page.supports_preview:
            return None
        mode = page.cycle_view_mode()
        self.status_changed.emit()
        return mode

    def apply_preview_settings(self) -> None:
        for page in self.pages():
            page.sync_scroll = bool(self.config.get("preview_sync_scroll", True))

    def grammar_note(self) -> str:
        return self.grammar.note if self.config.get("grammar", {}).get("enabled") else ""

    def shutdown(self) -> None:
        self.grammar.shutdown()
        for page in self.pages():
            if page.preview is not None:
                page.preview.shutdown()

    def open_paths(self) -> list[str]:
        """Für config.json: relativ innerhalb von data/, absolut für externe Dateien."""
        return [self.relative(editor.path) if not self.is_external(editor.path) else str(editor.path)
                for editor in self.editors()]
