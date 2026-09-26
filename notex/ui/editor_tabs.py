"""Tab-Bereich rechts: mehrere Dateien gleichzeitig offen, Dirty-State pro Tab."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMessageBox, QTabWidget, QWidget

from notex.core.encoding import read_text_file
from notex.core import fileops
from notex.core.fileops import save_text_file
from notex.ui.editor import Editor

DIRTY_MARK = " ●"
MIN_FONT_SIZE, MAX_FONT_SIZE = 6, 40


class EditorTabs(QTabWidget):
    # Wird bei allem gefeuert, was die Statusleiste interessiert (Tabwechsel, Cursor, Dirty)
    status_changed = Signal()
    file_saved = Signal(Path)
    file_opened = Signal(Path)
    file_closed = Signal(Path)
    font_size_changed = Signal(int)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.font_size = 11
        self.word_wrap = False
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.tabCloseRequested.connect(self.close_tab)
        self.currentChanged.connect(lambda _index: self.status_changed.emit())

    # ---- Zugriff ----------------------------------------------------------
    def editors(self) -> list[Editor]:
        return [self.widget(i) for i in range(self.count()) if isinstance(self.widget(i), Editor)]

    def current_editor(self) -> Editor | None:
        widget = self.currentWidget()
        return widget if isinstance(widget, Editor) else None

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
            editor = Editor(path, text_file, self.font_size)
            editor.set_word_wrap(self.word_wrap)
            editor.document().modificationChanged.connect(lambda _m, e=editor: self._refresh_title(e))
            editor.cursorPositionChanged.connect(self.status_changed.emit)
            editor.textChanged.connect(self.status_changed.emit)
            editor.zoom_requested.connect(self.zoom)
            index = self.addTab(editor, path.name)
            self.setTabToolTip(index, self.relative(path))
            self.file_opened.emit(path)
        self.setCurrentWidget(editor)
        if line is not None:
            editor.goto_line(line, column, length)
        else:
            editor.setFocus()
        self.status_changed.emit()
        return editor

    def close_tab(self, index: int) -> bool:
        editor = self.widget(index)
        if isinstance(editor, Editor) and editor.is_dirty and not self._ask_save(editor):
            return False
        self.removeTab(index)
        if isinstance(editor, Editor):
            self.file_closed.emit(editor.path)
            editor.deleteLater()
        self.status_changed.emit()
        return True

    def close_current(self) -> None:
        if self.count():
            self.close_tab(self.currentIndex())

    def close_paths_under(self, path: Path) -> None:
        """Nach Löschen im Baum: Tabs der Datei bzw. aller Dateien im Ordner ohne Nachfrage schließen."""
        for editor in self.editors():
            if editor.path == path or fileops.is_within(editor.path, path):
                self.removeTab(self.indexOf(editor))
                self.file_closed.emit(editor.path)
                editor.deleteLater()
        self.status_changed.emit()

    def confirm_close_all(self) -> bool:
        """Vor dem Beenden: für jeden ungespeicherten Tab nachfragen. False = Abbruch."""
        for editor in self.editors():
            if editor.is_dirty:
                self.setCurrentWidget(editor)
                if not self._ask_save(editor):
                    return False
        return True

    def _ask_save(self, editor: Editor) -> bool:
        """Fragt: Speichern / Verwerfen / Abbrechen. Gibt False zurück, wenn abgebrochen."""
        box = QMessageBox(self)
        box.setWindowTitle("Ungespeicherte Änderungen")
        box.setText(f"„{editor.path.name}“ wurde geändert.\nÄnderungen speichern?")
        save = box.addButton("Speichern", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Verwerfen", QMessageBox.ButtonRole.DestructiveRole)
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
        index = self.indexOf(editor)
        if index >= 0:
            self.setTabText(index, editor.path.name + (DIRTY_MARK if editor.is_dirty else ""))
            self.setTabToolTip(index, self.relative(editor.path))
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
        for editor in self.editors():
            editor.set_font_size(self.font_size)
        self.font_size_changed.emit(self.font_size)

    def zoom(self, direction: int) -> None:
        self.set_font_size(self.font_size + direction)

    def set_word_wrap(self, enabled: bool) -> None:
        self.word_wrap = enabled
        for editor in self.editors():
            editor.set_word_wrap(enabled)

    def open_paths(self) -> list[str]:
        return [self.relative(editor.path) for editor in self.editors()]
