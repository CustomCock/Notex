"""Hauptfenster: Seitenleiste links, Editor-Tabs rechts, Statusleiste, Menü und Shortcuts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QMainWindow, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from notex import APP_NAME
from notex.core.encoding import read_text_file
from notex.ui import dialogs
from notex.ui.editor_tabs import EditorTabs
from notex.ui.empty_state import EmptyState
from notex.ui.toast import Toast
from notex.ui.file_watcher import OpenFileWatcher
from notex.ui.find_bar import FindBar
from notex.ui.sidebar import Sidebar
from notex.ui.status_bar import StatusBar
from notex.theme.icons import icon
from notex.theme.tokens import DURATION, FONT_SIZE, SPACING
from notex.ui import anim
from notex.core.theme_store import ThemeStore
from notex.paths import app_root
from notex.theme.manager import theme_manager
from notex.core import fileops
from notex.core import text_ops as ops
from notex.core.actions import ActionRegistry
from notex.core.config import config_digest
from notex.core.theme_model import PAPER_VARIANTS, PRESETS, apply_paper_variant, theme_from_preset
from notex.ui.file_index_service import FileIndexService
from notex.ui.palette import PaletteOverlay
from notex.core.recent import add_recent, prune_recent
from notex.core.winreg_assoc import SUPPORTED_EXTENSIONS, build_association, current_exe
from notex.ui.about_dialog import AboutDialog
from notex.ui.settings_dialog import SettingsDialog
from notex.ui.widgets import IconButton

QWIDGETSIZE_MAX = 16777215
from notex.ui.recent_dialog import RecentDialog
from notex.ui.winapi import apply_dark_titlebar, bring_to_front


class MainWindow(QMainWindow):
    def __init__(self, root: Path, config: dict[str, Any], on_save_config) -> None:
        super().__init__()
        self.root = root
        self.config = config
        self._save_config = on_save_config
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.theme_store = ThemeStore(app_root() / "themes")
        config["recent_files"] = prune_recent(config["recent_files"])

        self.sidebar = Sidebar(root, config)
        self.tabs = EditorTabs(root, config)
        self.tabs.font_size = config["font_size"]
        self.tabs.paper_mode = config["paper_mode"]
        self.find_bar = FindBar(self.tabs.current_editor)
        self.empty_state = EmptyState()
        self.toast = Toast(self)
        self.status = StatusBar()
        self.setStatusBar(self.status)
        self.watcher = OpenFileWatcher()

        # Kleiner Button links neben den Tabs, der die Seitenleiste ein-/ausklappt.
        # Er sitzt bewusst außerhalb der Seitenleiste, damit er auch sichtbar ist, wenn sie weg ist.
        self.sidebar_button = IconButton("panel-left", "Seitenleiste ein-/ausblenden  Ctrl+B")
        self.sidebar_button.clicked.connect(self.toggle_sidebar)
        self._sidebar_anim = None
        self.tabs.setCornerWidget(self.sidebar_button, Qt.Corner.TopLeftCorner)

        # Rechte Seite: Tabs oben, darunter (ausblendbar) die Suchen/Ersetzen-Leiste
        editor_area = QWidget()
        editor_layout = QVBoxLayout(editor_area)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        # Ohne offene Datei zeigt der Stack den Empty State statt der leeren Tab-Leiste
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.empty_state)
        self.editor_stack.addWidget(self.tabs)
        editor_layout.addWidget(self.editor_stack, 1)
        editor_layout.addWidget(self.find_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(editor_area)
        self.splitter.setStretchFactor(0, 0)  # Seitenleiste behält ihre Breite
        self.splitter.setStretchFactor(1, 1)  # Editor bekommt den Rest
        self.splitter.setCollapsible(1, False)
        self.setCentralWidget(self.splitter)

        self.association = build_association()   # None im Dev-Modus oder außerhalb von Windows
        self.registry = ActionRegistry()
        self.registry.recent = list(config.get("recent_commands", []))
        self.file_index = FileIndexService(root, config)
        self.file_index.attach_tree(self.sidebar.tree)
        self.palette = PaletteOverlay(self, self.registry, self.file_index.index)
        self.palette.open_file.connect(self._open_from_palette)
        self.palette.goto_line.connect(lambda line: self._with_editor(lambda e: e.goto_line(line)))
        self.palette.run_command.connect(self._run_command)
        self._connect_signals()
        self._build_menu()
        self._build_editor_actions()
        self._build_registry()
        self.file_index.request_rescan()
        QTimer.singleShot(1500, self._check_association_path)
        # Zustand regelmäßig sichern: Absturz oder Neustart kostet höchstens die letzte Sekunde
        self._last_saved_state = ""
        self._autosave = QTimer(self)
        self._autosave.setInterval(1000)
        self._autosave.timeout.connect(self._autosave_config)
        self._autosave.start()
        self._restore_window_state()
        theme_manager().changed.connect(self.retheme)

    def _connect_signals(self) -> None:
        tree = self.sidebar.tree
        self.sidebar.open_requested.connect(self._open_from_sidebar)
        self.sidebar.settings_requested.connect(self.open_settings)
        tree.path_renamed.connect(self._on_path_renamed)
        tree.path_deleted.connect(self.tabs.close_paths_under)

        self.tabs.status_changed.connect(self._update_status)
        self.tabs.file_opened.connect(self._on_file_opened)
        self.tabs.files_dropped.connect(lambda paths: self.open_external([Path(p) for p in paths]))
        self.tabs.file_closed.connect(lambda _p: self._refresh_open_files())
        self.sidebar.open_files.activated.connect(lambda path: self.tabs.open_file(path))
        self.sidebar.open_files.copy_requested.connect(lambda path: self._import_external(path, move=False))
        self.sidebar.open_files.move_requested.connect(lambda path: self._import_external(path, move=True))
        self.sidebar.open_files.reveal_requested.connect(fileops.reveal_in_file_manager)
        self.empty_state.recent_chosen.connect(lambda path: self.open_external([path]))
        self.tabs.currentChanged.connect(lambda _i: self.find_bar.refresh_highlight())
        self.tabs.font_size_changed.connect(lambda size: self.config.__setitem__("font_size", size))
        self.tabs.file_opened.connect(self.watcher.watch)
        self.tabs.file_closed.connect(self.watcher.unwatch)
        self.tabs.file_saved.connect(self.watcher.mark_saved)
        self.tabs.file_saved.connect(lambda path: self.toast.show_message(f"Gespeichert · {path.name}"))
        self.watcher.file_changed_externally.connect(self._on_external_change)
        self.watcher.file_removed_externally.connect(self._on_external_remove)
        self.status.spell_toggled.connect(self.toggle_spellcheck)
        self.status.grammar_toggled.connect(self.toggle_grammar)
        self.status.language_chosen.connect(self._set_tab_language)

    # ---- Menü & Shortcuts ---------------------------------------------------
    def _action(self, text: str, shortcut, slot, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self.addAction(action)  # damit der Shortcut auch ohne offenes Menü greift
        return action

    def _build_menu(self) -> None:
        tree = self.sidebar.tree
        file_menu = self.menuBar().addMenu("&Datei")
        file_menu.addAction(self._action("Neue Datei", "Ctrl+N", lambda: tree.create_file(tree.folder_for(tree.selected_path()))))
        file_menu.addAction(self._action("Neuer Ordner", "Ctrl+Shift+N", lambda: tree.create_folder(tree.folder_for(tree.selected_path()))))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Datei öffnen …", "Ctrl+O", self.open_file_dialog))
        file_menu.addAction(self._action("Zuletzt geöffnet …", "Ctrl+R", self.show_recent))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Speichern", QKeySequence.StandardKey.Save, self.tabs.save_current))
        file_menu.addAction(self._action("Speichern unter …", "Ctrl+Shift+Alt+S", self.tabs.save_current_as))
        file_menu.addAction(self._action("Alle speichern", "Ctrl+Shift+S", self.tabs.save_all))
        file_menu.addAction(self._action("Tab schließen", "Ctrl+W", self.tabs.close_current))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Einstellungen …", "Ctrl+,", self.open_settings))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Beenden", "Ctrl+Q", self.close))

        edit_menu = self.menuBar().addMenu("&Bearbeiten")
        edit_menu.addAction(self._action("Suchen", QKeySequence.StandardKey.Find, lambda: self.find_bar.open(with_replace=False)))
        edit_menu.addAction(self._action("Ersetzen", "Ctrl+H", lambda: self.find_bar.open(with_replace=True)))
        edit_menu.addSeparator()
        self.spell_action = self._action("Rechtschreibung prüfen", "F7", self.toggle_spellcheck, checkable=True)
        self.spell_action.setChecked(self.config["spellcheck"]["enabled"])
        edit_menu.addAction(self.spell_action)
        self.grammar_action = self._action("Grammatik prüfen (LanguageTool)", "Shift+F7", self.toggle_grammar, checkable=True)
        self.grammar_action.setChecked(self.config["grammar"]["enabled"])
        edit_menu.addAction(self.grammar_action)

        view_menu = self.menuBar().addMenu("&Ansicht")
        self.sidebar_action = self._action("Seitenleiste", "Ctrl+B", self.toggle_sidebar, checkable=True)
        view_menu.addAction(self.sidebar_action)
        view_menu.addAction(self._action("Suche in Dateien", "Ctrl+Shift+F", self.focus_search))
        view_menu.addSeparator()
        self.paper_action = self._action("Blatt zentrieren", "Alt+P", self.toggle_paper_mode, checkable=True)
        self.paper_action.setChecked(self.config["paper_mode"])
        view_menu.addAction(self.paper_action)
        self.anim_action = self._action("Animationen reduzieren", None, self.toggle_animations, checkable=True)
        self.anim_action.setChecked(not self.config["theme"]["animation"]["enabled"])
        view_menu.addAction(self.anim_action)
        view_menu.addSeparator()
        view_menu.addAction(self._action("Vergrößern", QKeySequence.StandardKey.ZoomIn, lambda: self.tabs.zoom(+1)))
        view_menu.addAction(self._action("Verkleinern", QKeySequence.StandardKey.ZoomOut, lambda: self.tabs.zoom(-1)))
        view_menu.addAction(self._action("Zoom zurücksetzen", "Ctrl+0", lambda: self.tabs.set_font_size(FONT_SIZE.editor)))
        help_menu = self.menuBar().addMenu("&Hilfe")
        help_menu.addAction(self._action(f"Über {APP_NAME}", None, lambda: AboutDialog(self).exec()))
        # Ctrl+Plus liegt je nach Tastatur auf "Ctrl+=" – beides abdecken
        self._action("Vergrößern (Alternative)", "Ctrl+=", lambda: self.tabs.zoom(+1))

    def toggle_animations(self) -> None:
        theme = theme_manager().current()
        theme["animation"]["enabled"] = not theme["animation"]["enabled"]
        self.config["theme"] = theme_manager().apply(theme)
        self.anim_action.setChecked(not theme["animation"]["enabled"])

    # ---- Dateien von außen ------------------------------------------------------------
    def open_external(self, paths: list[Path], bring_front: bool = False) -> None:
        """Dateien aus Kommandozeile, zweiter Instanz, Drag & Drop oder „Zuletzt geöffnet“ öffnen."""
        opened = None
        for path in paths:
            path = Path(path)
            if path.is_file():
                opened = self.tabs.open_file(path) or opened
            else:
                self.toast.show_message(f"Nicht gefunden: {path.name}", "triangle-alert")
        if bring_front:
            bring_to_front(self)
        if opened is not None:
            self.editor_stack.setCurrentWidget(self.tabs)

    def open_file_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, "Datei öffnen", str(self.root),
                                                "Textdateien (*.txt *.md *.log *.csv *.json *.py *.ini);;Alle Dateien (*)")
        if paths:
            self.open_external([Path(p) for p in paths])

    def show_recent(self) -> None:
        self.config["recent_files"] = prune_recent(self.config["recent_files"])
        dialog = RecentDialog(self.config["recent_files"], self)
        if dialog.exec() == RecentDialog.DialogCode.Accepted and dialog.chosen is not None:
            self.open_external([dialog.chosen])

    def _on_file_opened(self, path: Path) -> None:
        self.config["recent_files"] = add_recent(self.config["recent_files"], path)
        self.empty_state.set_recent(self.config["recent_files"])
        self._refresh_open_files()

    def _refresh_open_files(self) -> None:
        self.sidebar.open_files.set_files(self.tabs.external_files())

    def _import_external(self, path: Path, move: bool) -> None:
        """Externe Datei nach data/ kopieren oder verschieben; der Tab zeigt danach auf die neue Datei."""
        import shutil
        new_path = fileops.unique_path(self.root, path.stem, path.suffix)   # nie überschreiben: „Name (2).txt“
        try:
            if move:
                editor = self.tabs.editor_for(path)
                if editor is not None and editor.is_dirty and not self.tabs.save_editor(editor):
                    return
                shutil.move(str(path), str(new_path))
                self.tabs.rename_open_file(path, new_path)
                self.watcher.unwatch(path)
                self.watcher.watch(new_path)
            else:
                shutil.copy2(path, new_path)
        except OSError as error:
            dialogs.warn(self, "Nach data/ übernehmen", str(error))
            return
        index = self.tabs.indexOf(self.tabs.page_for(self.tabs.editor_for(new_path))) if self.tabs.editor_for(new_path) else -1
        if index >= 0:
            from PySide6.QtGui import QIcon
            self.tabs.setTabIcon(index, QIcon())
        self._refresh_open_files()
        self.toast.show_message(f"{'Verschoben' if move else 'Kopiert'} nach data/ · {new_path.name}", "check")
        self.sidebar.tree.select_path(new_path)
        self._update_status()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        self.open_external([p for p in paths if p.is_file()])
        event.acceptProposedAction()

    # ---- Rechtschreibung / Grammatik --------------------------------------------
    def toggle_spellcheck(self) -> None:
        self.config["spellcheck"]["enabled"] = not self.config["spellcheck"]["enabled"]
        self.spell_action.setChecked(self.config["spellcheck"]["enabled"])
        self.tabs.apply_spell_settings()
        self._update_status()

    def toggle_grammar(self) -> None:
        self.config["grammar"]["enabled"] = not self.config["grammar"]["enabled"]
        self.grammar_action.setChecked(self.config["grammar"]["enabled"])
        self.tabs.apply_spell_settings()
        self._update_status()

    def _set_tab_language(self, language) -> None:
        editor = self.tabs.current_editor()
        if editor is not None:
            editor.set_language(language)
            self._update_status()

    def build_spelling_settings(self, page) -> None:
        """Seite „Rechtschreibung“ im Einstellungsdialog (wird vom Dialog aufgerufen)."""
        from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QWidget
        from notex.core.spell import LANGUAGE_LABELS
        from notex.ui.widgets import Chip

        cfg = self.config["spellcheck"]
        page.section("Rechtschreibung")
        enabled = QCheckBox("Rechtschreibung prüfen  (F7)")
        enabled.setChecked(cfg["enabled"])
        enabled.toggled.connect(lambda on: (cfg.__setitem__("enabled", on), self.spell_action.setChecked(on),
                                            self.tabs.apply_spell_settings(), self._update_status()))
        page.row("", enabled)
        language = QComboBox()
        for key in ("de", "en", "both"):
            language.addItem(LANGUAGE_LABELS[key], key)
        language.setCurrentIndex(("de", "en", "both").index(cfg["language"]))
        language.currentIndexChanged.connect(lambda i: (cfg.__setitem__("language", language.itemData(i)),
                                                         self.tabs.apply_spell_settings(), self._update_status()))
        page.row("Sprache", language)

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        for ext in self.config["extensions"]:
            chip = Chip(ext, f"Rechtschreibung für {ext}-Dateien")
            chip.setChecked(ext in cfg["extensions"])

            def toggled(on: bool, e=ext) -> None:
                exts = set(cfg["extensions"])
                exts.add(e) if on else exts.discard(e)
                cfg["extensions"] = sorted(exts)
                self.tabs.apply_spell_settings()
                self._update_status()

            chip.toggled.connect(toggled)
            chips_row.addWidget(chip)
        chips_row.addStretch(1)
        chips = QWidget()
        chips.setLayout(chips_row)
        page.row("Dateiendungen", chips)
        backend = self.tabs.checker.backend_name()
        words = len(list(self.tabs.checker.user_words()))
        page.note(f"Wörterbücher de_DE und en_US (LibreOffice) liegen in notex/dictionaries/. "
                  f"Backend: {backend}. Eigene Wörter: {words} in user_dictionary.txt.")

        gcfg = self.config["grammar"]
        page.section("Grammatik (LanguageTool)")
        genabled = QCheckBox("Grammatik prüfen  (Shift+F7)")
        genabled.setChecked(gcfg["enabled"])
        genabled.toggled.connect(lambda on: (gcfg.__setitem__("enabled", on), self.grammar_action.setChecked(on),
                                             self.tabs.apply_spell_settings(), self._update_status()))
        page.row("", genabled)
        url = QLineEdit(gcfg["server_url"])
        url.setPlaceholderText("http://localhost:8081")
        url.editingFinished.connect(lambda: (gcfg.__setitem__("server_url", url.text().strip() or "http://localhost:8081"),
                                             self.tabs.apply_spell_settings()))
        page.row("Server-URL", url)
        public = QCheckBox("Öffentliche API (api.languagetool.org) erlauben")
        public.setChecked(gcfg["allow_public"])
        public.toggled.connect(lambda on: (gcfg.__setitem__("allow_public", on), self.tabs.apply_spell_settings()))
        page.row("", public)
        page.note("Achtung: Bei der öffentlichen API wird der Text jedes geprüften Absatzes an einen externen "
                  "Server von LanguageTool geschickt. Standard ist ein lokaler Server (siehe README), "
                  "dann bleibt alles auf deinem Rechner.")

    # ---- Windows-Dateizuordnung ----------------------------------------------------
    def _check_association_path(self) -> None:
        """Wurde der Notex-Ordner verschoben, zeigt die Registrierung noch auf die alte EXE."""
        if self.association is None:
            return
        try:
            status = self.association.status()
        except Exception:  # noqa: BLE001 – Registry-Zugriff darf den Start nie stören
            return
        if status.registered and not status.matches(self.association.exe_path):
            self.toast.show_message("Notex-Ordner verschoben – Einstellungen > System > „Pfad aktualisieren“", "triangle-alert")

    def build_system_settings(self, page) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget
        from notex.ui.widgets import Chip

        page.section("Windows-Dateizuordnung")
        status_label = QLabel()
        status_label.setObjectName("SettingsNote")
        status_label.setWordWrap(True)
        page.add(status_label)

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        chosen = set(self.config.get("association_extensions", [".txt"]))
        for ext in SUPPORTED_EXTENSIONS:
            chip = Chip(ext, f"{ext}-Dateien mit Notex öffnen")
            chip.setChecked(ext in chosen)

            def toggled(on: bool, e=ext) -> None:
                exts = set(self.config.get("association_extensions", []))
                exts.add(e) if on else exts.discard(e)
                self.config["association_extensions"] = [x for x in SUPPORTED_EXTENSIONS if x in exts]

            chip.toggled.connect(toggled)
            chips_row.addWidget(chip)
        chips_row.addStretch(1)
        chips = QWidget()
        chips.setLayout(chips_row)
        page.row("Dateitypen", chips)

        register = QPushButton("Notex für Dateitypen registrieren")
        update = QPushButton("Pfad aktualisieren")
        remove = QPushButton("Registrierung entfernen")
        defaults = QPushButton("Windows-Standard-Apps öffnen")
        defaults.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("ms-settings:defaultapps")))
        from PySide6.QtWidgets import QGridLayout
        buttons = QGridLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setHorizontalSpacing(SPACING.sm)
        buttons.setVerticalSpacing(SPACING.sm)
        for i, button in enumerate((register, update, remove, defaults)):
            buttons.addWidget(button, i // 2, i % 2)   # zwei Reihen, damit nichts seitlich überläuft
        buttons.setColumnStretch(2, 1)
        row = QWidget()
        row.setLayout(buttons)
        page.add(row)

        def refresh() -> None:
            if self.association is None:
                reason = ("Nur aus der gebauten Notex.exe möglich, nicht im Dev-Modus." if current_exe() is None
                          else "Nur unter Windows verfügbar.")
                status_label.setText(f"Nicht verfügbar: {reason}")
                for button in (register, update, remove):
                    button.setEnabled(False)
                    button.setToolTip(reason)
                return
            status = self.association.status()
            if status.registered:
                same = status.matches(self.association.exe_path)
                status_label.setText(f"Registriert: ja · Endungen: {', '.join(status.extensions) or '–'}\n"
                                     f"Pfad: {status.exe_path}" + ("" if same else "\nAchtung: zeigt auf eine andere Notex.exe (Ordner verschoben?)"))
            else:
                status_label.setText("Registriert: nein. Die Registrierung schreibt nur in HKCU (kein Admin) und "
                                     "überschreibt keine bestehende Zuordnung – Notex erscheint unter „Öffnen mit“ "
                                     "und in den Standard-Apps.")
            update.setEnabled(status.registered and not status.matches(self.association.exe_path))
            remove.setEnabled(status.registered)

        def do_register() -> None:
            try:
                self.association.register(self.config.get("association_extensions", [".txt"]))
            except OSError as error:
                dialogs.warn(self, "Registrierung", str(error))
                return
            refresh()
            if dialogs.confirm(self, "Registriert",
                               "Notex ist jetzt bei Windows bekannt und erscheint unter „Öffnen mit“ sowie im "
                               "Kontextmenü („Mit Notex öffnen“).",
                               yes="Standard-Apps öffnen", no="Später",
                               informative="Damit ein Doppelklick Notex startet, wähle es in den Windows-Einstellungen "
                                           "unter Standard-Apps für .txt (und die anderen Endungen) aus. Windows lässt "
                                           "das nur dich selbst festlegen."):
                QDesktopServices.openUrl(QUrl("ms-settings:defaultapps"))

        def do_remove() -> None:
            if dialogs.confirm(self, "Registrierung entfernen", "Alle Notex-Einträge aus der Registry entfernen?",
                               yes="Entfernen", danger=True):
                self.association.unregister()
                refresh()
                self.toast.show_message("Registrierung entfernt", "check")

        def do_update() -> None:
            self.association.update_path()
            refresh()
            self.toast.show_message("Pfad aktualisiert", "check")

        register.clicked.connect(do_register)
        remove.clicked.connect(do_remove)
        update.clicked.connect(do_update)
        refresh()
        page.note("Der Kontextmenü-Eintrag „Mit Notex öffnen“ erscheint unter Windows 11 im klassischen Menü "
                  "(„Weitere Optionen anzeigen“). Notex bleibt portabel: Wird der Ordner verschoben, meldet sich "
                  "beim Start ein Hinweis, und „Pfad aktualisieren“ schreibt den neuen Pfad.")

    def open_settings(self, category: str | None = None) -> None:
        dialog = SettingsDialog(self, self.theme_store)
        if category:
            dialog.show_category(category)
        dialog.exec()

    def shortcut_list(self) -> list[tuple[str, str]]:
        """Alle Menüaktionen mit Tastenkürzel, für die Anzeige in den Einstellungen."""
        result = []
        for action in self.actions():
            if action.shortcut().isEmpty() or "(Alternative)" in action.text():
                continue
            result.append((action.text().replace("&", "").replace(" …", ""), action.shortcut().toString()))
        result += [("Umbenennen (im Baum)", "F2"), ("In den Papierkorb (im Baum)", "Entf"),
                   ("Suche leeren", "Esc"), ("Zoom", "Ctrl+Mausrad")]
        return result

    def retheme(self) -> None:
        """Nach einem Theme-Wechsel: alles nachziehen, was Farben/Icons/Abstände selbst hält."""
        self.sidebar_button.setIcon(icon("panel-left"))
        for action in self.tabs.editor_actions.values():
            action.setIcon(icon(action.data()))
        self.sidebar.retheme()
        self.tabs.retheme()
        self.find_bar.retheme()
        self.status.retheme()
        self.sidebar.open_files.retheme()
        self.anim_action.setChecked(anim.reduced())
        self.sidebar.tree.setAnimated(not anim.reduced())
        self._update_status()

    def toggle_paper_mode(self) -> None:
        enabled = not self.tabs.paper_mode
        self.tabs.set_paper_mode(enabled)
        self.paper_action.setChecked(enabled)
        self.config["paper_mode"] = enabled
        self._sync_editor_actions()


    def focus_search(self) -> None:
        if not self.sidebar.isVisible():
            self.set_sidebar_visible(True)
        self.sidebar.focus_search()

    def _open_from_sidebar(self, path: Path, location) -> None:
        """Öffnet eine Datei aus Baum oder Trefferliste; `location` = (Zeile, Spalte, Länge) oder None."""
        if location is None:
            self.tabs.open_file(path)
        else:
            line, column, length = location
            self.tabs.open_file(path, line=line, column=column, length=length)

    # ---- Seitenleiste ---------------------------------------------------------
    def toggle_sidebar(self) -> None:
        self.set_sidebar_visible(not self.sidebar.isVisible())

    def set_sidebar_visible(self, visible: bool, animate: bool = True) -> None:
        """Seitenleiste ein-/ausklappen, auf Wunsch animiert (Breite gleitet, ~200 ms)."""
        if self._sidebar_anim is not None:
            self._sidebar_anim.stop()
            self._sidebar_anim = None
        currently_visible = self.sidebar.isVisible() and self.splitter.sizes()[0] > 0
        if not visible and currently_visible:
            self.config["sidebar"]["width"] = self.splitter.sizes()[0]  # Breite merken, bevor sie auf 0 geht
        width = self.config["sidebar"]["width"]
        self.sidebar_action.setChecked(visible)
        self.config["sidebar"]["visible"] = visible

        if not animate or anim.duration(DURATION.sidebar) == 0 or visible == currently_visible:
            self.sidebar.setMaximumWidth(QWIDGETSIZE_MAX)
            self.sidebar.setVisible(visible)
            if visible:
                self._apply_sidebar_width(width)
            return

        # Animation: die Maximalbreite der Seitenleiste fährt hoch/runter, der Splitter folgt.
        start, end = (0, width) if visible else (width, 0)
        if visible:
            self.sidebar.setMaximumWidth(0)
            self.sidebar.setVisible(True)

        def step(value: float) -> None:
            self.sidebar.setMaximumWidth(int(value))
            self._apply_sidebar_width(int(value))

        def done() -> None:
            self._sidebar_anim = None
            if visible:
                self.sidebar.setMaximumWidth(QWIDGETSIZE_MAX)
                self._apply_sidebar_width(width)
            else:
                self.sidebar.setVisible(False)
                self.sidebar.setMaximumWidth(QWIDGETSIZE_MAX)

        self._sidebar_anim = anim.animate(self, start, end, DURATION.sidebar, step, done)

    def _apply_sidebar_width(self, width: int) -> None:
        total = sum(self.splitter.sizes()) or self.width()
        self.splitter.setSizes([width, max(200, total - width)])

    # ---- Reaktionen auf Baum / Watcher -----------------------------------------
    def _on_path_renamed(self, old: Path, new: Path) -> None:
        self.tabs.rename_open_file(old, new)
        # Watcher auf die neuen Pfade umhängen
        for editor in self.tabs.editors():
            if editor.path == new or new in editor.path.parents:
                self.watcher.watch(editor.path)
        self.watcher.unwatch(old)
        self._update_status()

    def _on_external_change(self, path: Path) -> None:
        editor = self.tabs.editor_for(path)
        if editor is None:
            return
        hint = "Achtung: Deine ungespeicherten Änderungen gehen dabei verloren." if editor.is_dirty else ""
        reload = dialogs.confirm(
            self, "Datei extern geändert",
            f"„{self.tabs.relative(path)}“ wurde außerhalb von {APP_NAME} geändert. Neu laden?",
            yes="Neu laden", no="Behalten", informative=hint, danger=editor.is_dirty,
        )
        if reload:
            try:
                editor.replace_content(read_text_file(path))
            except OSError as error:
                dialogs.warn(self, "Neu laden fehlgeschlagen", str(error))
        else:
            editor.document().setModified(True)  # Inhalt weicht jetzt von der Platte ab
        self._update_status()

    def _on_external_remove(self, path: Path) -> None:
        editor = self.tabs.editor_for(path)
        if editor is None:
            return
        editor.document().setModified(True)  # Speichern legt die Datei wieder an
        self.status.showMessage(f"„{self.tabs.relative(path)}“ wurde extern gelöscht oder verschoben.", 8000)
        self._update_status()

    # ---- Aktionen der Bearbeitungsleiste -----------------------------------------
    def _editor_action(self, key: str, icon_name: str, text: str, shortcut: str | None, slot, checkable: bool = False) -> QAction:
        action = QAction(icon(icon_name), text, self)
        action.setData(icon_name)   # für den Icon-Refresh beim Theme-Wechsel
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setToolTip(f"{text}  {shortcut}")
        else:
            action.setToolTip(text)
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self.addAction(action)
        self.tabs.editor_actions[key] = action
        return action

    def _with_editor(self, func) -> None:
        editor = self.tabs.current_editor()
        if editor is not None:
            func(editor)

    def _build_editor_actions(self) -> None:
        a, ed = self._editor_action, self._with_editor
        a("undo", "undo-2", "Rückgängig", None, lambda: ed(lambda e: e.undo())).setToolTip("Rückgängig  Ctrl+Z")
        a("redo", "redo-2", "Wiederholen", None, lambda: ed(lambda e: e.redo())).setToolTip("Wiederholen  Ctrl+Y")
        a("find", "search", "Suchen", None, lambda: self.find_bar.open(with_replace=False)).setToolTip("Suchen  Ctrl+F")
        a("replace", "replace", "Ersetzen", None, lambda: self.find_bar.open(with_replace=True)).setToolTip("Ersetzen  Ctrl+H")
        a("font_smaller", "minus", "Textgröße verkleinern (Ansicht, ändert nichts an der Datei)", None, lambda: self.tabs.zoom(-1))
        a("font_larger", "plus", "Textgröße vergrößern (Ansicht, ändert nichts an der Datei)", None, lambda: self.tabs.zoom(+1))
        a("zoom_reset", "rotate-ccw", "Zoom zurücksetzen", None, lambda: self.tabs.set_font_size(FONT_SIZE.editor)).setToolTip("Zoom zurücksetzen  Ctrl+0")
        self.paper_toolbar_action = a("paper_mode", "minimize-2", "Blatt-Modus / volle Breite", None, self.toggle_paper_mode, checkable=True)
        self.paper_toolbar_action.setToolTip("Blatt zentrieren / volle Breite  Alt+P")
        self.line_numbers_action = a("line_numbers", "hash", "Zeilennummern", "Ctrl+Alt+N",
                                     lambda: self.tabs.set_line_numbers(not self.tabs.line_numbers), checkable=True)
        a("dup_line", "copy-plus", "Zeile duplizieren", "Ctrl+D", lambda: ed(lambda e: e.apply_line_op(ops.duplicate_lines)))
        a("move_up", "arrow-up", "Zeile(n) nach oben", "Alt+Up", lambda: ed(lambda e: e.move_lines(-1)))
        a("move_down", "arrow-down", "Zeile(n) nach unten", "Alt+Down", lambda: ed(lambda e: e.move_lines(+1)))
        a("sort_lines", "arrow-down-a-z", "Zeilen sortieren", "F9", lambda: ed(lambda e: e.apply_line_op(ops.sort_lines)))
        a("unique_lines", "list-minus", "Doppelte Zeilen entfernen", "Ctrl+Shift+D", lambda: ed(lambda e: e.apply_line_op(ops.unique_lines)))
        a("strip_ws", "eraser", "Leerzeichen am Zeilenende entfernen", None, lambda: ed(lambda e: e.apply_line_op(ops.strip_trailing_whitespace)))
        a("upper", "case-upper", "GROSSBUCHSTABEN", "Ctrl+Shift+U", lambda: ed(lambda e: e.apply_text_op(ops.to_upper)))
        a("lower", "case-lower", "kleinbuchstaben", "Ctrl+U", lambda: ed(lambda e: e.apply_text_op(ops.to_lower)))
        a("title", "case-sensitive", "Wortanfänge Groß", "Ctrl+Alt+U", lambda: ed(lambda e: e.apply_text_op(ops.to_title)))
        a("datetime", "calendar-clock", "Datum/Uhrzeit einfügen", "F5", lambda: ed(lambda e: e.insert_text(ops.date_time_stamp())))
        a("md_bold", "bold", "Fett", "Ctrl+Alt+B", lambda: ed(lambda e: e.apply_text_op(ops.toggle_bold)))
        a("md_italic", "italic", "Kursiv", "Ctrl+Alt+I", lambda: ed(lambda e: e.apply_text_op(ops.toggle_italic)))
        a("md_heading", "heading", "Überschrift", "Ctrl+Alt+H",
          lambda: ed(lambda e: e.apply_line_op(lambda ls: [ops.toggle_heading(l) for l in ls])))
        a("md_list", "list", "Liste", "Ctrl+Alt+L", lambda: ed(lambda e: e.apply_line_op(ops.toggle_list)))
        a("md_checkbox", "square-check", "Checkbox", "Ctrl+Alt+X", lambda: ed(lambda e: e.apply_line_op(ops.toggle_checkbox)))
        a("md_code", "code", "Code", "Ctrl+Alt+C", lambda: ed(lambda e: e.apply_text_op(ops.toggle_code)))
        a("md_link", "link", "Link", "Ctrl+K", lambda: ed(lambda e: e.apply_text_op(ops.toggle_link)))
        self.spell_toolbar_action = a("spell", "spell-check", "Rechtschreibung", None, self.toggle_spellcheck, checkable=True)
        self.spell_toolbar_action.setToolTip("Rechtschreibung prüfen  F7")
        self.grammar_toolbar_action = a("grammar", "languages", "Grammatik (LanguageTool)", None, self.toggle_grammar, checkable=True)
        self.grammar_toolbar_action.setToolTip("Grammatik prüfen  Shift+F7")
        self.toolbar_action = self._action("Bearbeitungsleiste", "Ctrl+Shift+E", self.tabs.toggle_toolbar, checkable=True)
        self.toolbar_action.setChecked(self.tabs.toolbar_visible)
        self.menuBar().actions()[2].menu().addAction(self.toolbar_action)   # Menü „Ansicht“
        self.tabs.open_font_settings = lambda: self.open_settings("Schrift")

    # ---- Command Palette / Quick Open --------------------------------------------------
    def _build_registry(self) -> None:
        """Alle QActions des Fensters plus Themes/Presets/Einstellungen als Befehle anmelden."""
        categories = {}
        for menu_action in self.menuBar().actions():
            menu = menu_action.menu()
            if menu is None:
                continue
            for action in menu.actions():
                categories[action] = menu_action.text().replace("&", "")
        toolbar_categories = {"undo": "Bearbeiten", "redo": "Bearbeiten", "find": "Bearbeiten", "replace": "Bearbeiten"}
        for key, action in self.tabs.editor_actions.items():
            categories.setdefault(action, toolbar_categories.get(key, "Editor"))
        for action in self.actions():
            text = action.text().replace("&", "").replace(" …", "").strip()
            if not text or action.isSeparator() or "(Alternative)" in text:
                continue
            category = categories.get(action, "Ansicht")
            self.registry.add(
                f"action:{id(action)}", text, action.trigger, category=category,
                shortcut=action.shortcut().toString(),
                is_checked=(lambda a=action: a.isChecked()) if action.isCheckable() else None,
            )
        for name in PRESETS:
            self.registry.add(f"preset:{name}", f"Preset {name}", lambda n=name: self._apply_preset(n),
                              category="Theme", keywords="farben oberfläche")
        for name in PAPER_VARIANTS:
            self.registry.add(f"paper:{name}", f"Blatt {name}", lambda n=name: self._apply_paper_variant(n),
                              category="Theme", keywords="blatt papier farbe")
        for name in SettingsDialog.CATEGORIES:
            self.registry.add(f"settings:{name}", f"Einstellungen: {name}", lambda n=name: self.open_settings(n),
                              category="Einstellungen")
        self.registry.add("palette:files", "Quick Open", lambda: self.show_palette("files"), category="Navigation", shortcut="Ctrl+P")
        self.registry.add("palette:commands", "Command Palette", lambda: self.show_palette("commands"), category="Navigation", shortcut="Ctrl+Shift+P")
        self.registry.add("nav:goto", "Gehe zu Zeile", lambda: (self.show_palette("files"), self.palette.field.setText(":")), category="Navigation")
        self._action("Quick Open", "Ctrl+P", lambda: self.show_palette("files"))
        self._action("Command Palette", "Ctrl+Shift+P", lambda: self.show_palette("commands"))

    def register_command(self, id: str, title: str, callback, category: str = "", shortcut: str = "", **kw) -> None:
        """Für neue Features: ein Befehl, der sofort in der Palette auftaucht."""
        self.registry.add(id, title, callback, category=category, shortcut=shortcut, **kw)

    def show_palette(self, mode: str) -> None:
        self.palette.recent_files = [self.tabs.relative(Path(p)) if not self.tabs.is_external(Path(p)) else p
                                     for p in self.config.get("recent_files", [])]
        self.file_index.set_externals([p for p in self.config.get("recent_files", []) if self.tabs.is_external(Path(p))])
        self.palette.open(mode)

    def _open_from_palette(self, path: Path, line) -> None:
        full = path if path.is_absolute() else self.root / path
        if full.is_file():
            self.tabs.open_file(full, line=int(line) if line else None)
            self.editor_stack.setCurrentWidget(self.tabs)

    def _run_command(self, command_id: str) -> None:
        self.registry.run(command_id)
        self.config["recent_commands"] = list(self.registry.recent)

    def _apply_preset(self, name: str) -> None:
        current = theme_manager().current()
        preset = theme_from_preset(name)
        for key, value in preset["colors"].items():
            if not key.startswith("paper"):
                current["colors"][key] = value
        current["name"] = name
        self.config["theme"] = theme_manager().apply(current)
        self.toast.show_message(f"Preset {name}", "palette")

    def _apply_paper_variant(self, name: str) -> None:
        self.config["theme"] = theme_manager().apply(apply_paper_variant(theme_manager().current(), name))
        self.toast.show_message(f"Blatt {name}", "palette")

    def _sync_editor_actions(self) -> None:
        """Checkbare Toolbar-Aktionen an den aktuellen Zustand angleichen."""
        editor = self.tabs.current_editor()
        self.paper_toolbar_action.setChecked(self.tabs.paper_mode)
        self.line_numbers_action.setChecked(self.tabs.line_numbers)
        self.toolbar_action.setChecked(self.tabs.toolbar_visible)
        if editor is not None:
            self.spell_toolbar_action.setChecked(self.tabs.spell_enabled_for(editor.path))
            self.grammar_toolbar_action.setChecked(self.tabs.grammar_enabled_for(editor.path))
        self.tabs.sync_toolbars()

    def _update_status(self) -> None:
        self.editor_stack.setCurrentWidget(self.tabs if self.tabs.count() else self.empty_state)
        if not self.tabs.count():
            self.find_bar.hide()
        editor = self.tabs.current_editor()
        if editor is None:
            self.status.update_for(None, "")
            self.setWindowTitle(APP_NAME)
            return
        relative = self.tabs.relative(editor.path)
        self.status.update_for(editor, relative)
        self._sync_editor_actions()
        self.status.set_spell_state(
            self.tabs.spell_enabled_for(editor.path), self.tabs.grammar_enabled_for(editor.path),
            editor.language or self.config["spellcheck"]["language"], editor.language is not None,
            self.tabs.grammar_note() if hasattr(self.tabs, "grammar_note") else "")
        self.setWindowTitle(f"{'● ' if editor.is_dirty else ''}{relative} – {APP_NAME}")

    # ---- Zustand ----------------------------------------------------------
    def _restore_window_state(self) -> None:
        win = self.config["window"]
        self.resize(win["width"], win["height"])
        if win["x"] is not None and win["y"] is not None:
            self.move(win["x"], win["y"])
        if win["maximized"]:
            self.showMaximized()

        side = self.config["sidebar"]
        self.splitter.setSizes([side["width"], max(200, win["width"] - side["width"])])
        self.set_sidebar_visible(side["visible"])
        self.sidebar.tree.restore_expanded(self.config["expanded_folders"])

        for entry in self.config["open_tabs"]:
            path = self.tabs.resolve_saved(entry)
            if path.is_file():
                self.tabs.open_file(path)
        self.empty_state.set_recent(self.config["recent_files"])
        if 0 <= self.config["active_tab"] < self.tabs.count():
            self.tabs.setCurrentIndex(self.config["active_tab"])

    def _collect_window_state(self) -> None:
        win = self.config["window"]
        win["maximized"] = self.isMaximized()
        if not self.isMaximized():
            geo = self.normalGeometry()  # Größe/Position im nicht-maximierten Zustand
            win["x"], win["y"], win["width"], win["height"] = geo.x(), geo.y(), geo.width(), geo.height()
        if self.sidebar.isVisible():
            sizes = self.splitter.sizes()
            if sizes and sizes[0] > 0:
                self.config["sidebar"]["width"] = sizes[0]
        self.config["sidebar"]["visible"] = self.sidebar.isVisible()
        self.config["expanded_folders"] = self.sidebar.tree.expanded_folders()
        self.config["open_tabs"] = self.tabs.open_paths()
        self.config["active_tab"] = max(0, self.tabs.currentIndex())

    def save_state(self) -> None:
        self._collect_window_state()
        self._save_config(self.config)
        self._last_saved_state = config_digest(self.config)

    def _autosave_config(self) -> None:
        """Schreibt config.json nur, wenn sich seit dem letzten Mal etwas geändert hat (atomar)."""
        if not self.isVisible():
            return
        self._collect_window_state()
        digest = config_digest(self.config)
        if digest != self._last_saved_state:
            try:
                self._save_config(self.config)
                self._last_saved_state = digest
            except OSError:
                pass   # z. B. Stick abgezogen – beim nächsten Tick erneut versuchen

    # ---- Qt-Events --------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_dark_titlebar(self)  # das HWND existiert erst, wenn das Fenster sichtbar wird
        self._update_status()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast._place()
        self.palette.resize_to_parent()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.tabs.confirm_close_all():
            event.ignore()
            return
        self.sidebar.stop_search()
        self.file_index.shutdown()
        self.tabs.shutdown()
        self.save_state()
        event.accept()
