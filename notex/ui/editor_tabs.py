"""Tab-Bereich rechts: mehrere Dateien gleichzeitig offen, Dirty-State pro Tab.

Jeder Tab enthält eine EditorPage (Blatt + Schatten), die den eigentlichen Editor hält.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QMessageBox, QTabWidget, QWidget

from notex.core import fileops
from notex.core.encoding import read_text_file
from notex.core.fileops import save_text_file
from notex.core.spell import SpellChecker
from notex.paths import app_root
from notex.theme import tokens
from notex.theme.tokens import COLORS, DURATION, FONT_SIZE
from notex.ui import anim
from notex.ui.editor import Editor
from notex.ui.grammar_service import GrammarService
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
    dirty_changed = Signal(int, bool)   # Tab-Index, dirty

    def __init__(self, root: Path, config: dict | None = None) -> None:
        super().__init__()
        self.root = root
        self.config = config if config is not None else {}
        self.checker = SpellChecker(user_dictionary=app_root() / "user_dictionary.txt")
        self.checker.set_language(self.config.get("spellcheck", {}).get("language", "de"))
        self.grammar = GrammarService(self.config)
        self.grammar.state_changed.connect(lambda _n: self.status_changed.emit())
        if self.config.get("grammar", {}).get("enabled"):
            self.grammar.restart()
        self.font_size = FONT_SIZE.editor
        self.paper_mode = True
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

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    # ---- Öffnen / Schließen ------------------------------------------------
    def open_file(self, path: Path, line: int | None = None, column: int = 0, length: int = 0) -> Editor | None:
        path = Path(path)
        editor = self.editor_for(path)
        if editor is None:
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
            page = EditorPage(editor, self.paper_mode)
            index = self.addTab(page, path.name)
            self.setTabToolTip(index, self.relative(path))
            self.file_opened.emit(path)
        self.setCurrentWidget(self.page_for(editor))
        if line is not None:
            editor.goto_line(line, column, length)
        else:
            editor.setFocus()
        self.status_changed.emit()
        return editor

    def _remove(self, editor: Editor) -> None:
        self.grammar.detach(editor)
        page = self.page_for(editor)
        if page is not None:
            self.removeTab(self.indexOf(page))
            page.deleteLater()
        self.file_closed.emit(editor.path)

    def close_tab(self, index: int) -> bool:
        page = self.widget(index)
        if not isinstance(page, EditorPage):
            return False
        editor = page.editor
        if editor.is_dirty and not self._ask_save(editor):
            return False
        self._remove(editor)
        self.status_changed.emit()
        return True

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
        for editor in self.editors():
            if editor.is_dirty:
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
        try:
            save_text_file(editor.path, editor.toPlainText(), editor.encoding, editor.eol)
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

    def save_all(self) -> None:
        for editor in self.editors():
            if editor.is_dirty:
                self.save_editor(editor)

    # ---- Darstellung -------------------------------------------------------
    def _refresh_title(self, editor: Editor) -> None:
        page = self.page_for(editor)
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
        self.set_font_size(self.font_size + direction)

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

    def grammar_note(self) -> str:
        return self.grammar.note if self.config.get("grammar", {}).get("enabled") else ""

    def shutdown(self) -> None:
        self.grammar.shutdown()

    def open_paths(self) -> list[str]:
        return [self.relative(editor.path) for editor in self.editors()]
