"""Hauptfenster: Seitenleiste links, Editor-Tabs rechts, Statusleiste, Menü und Shortcuts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QTextCursor
from PySide6.QtWidgets import QMainWindow, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from notex import APP_NAME
from notex.core.encoding import read_text_file
from notex.ui import dialogs
from notex.ui.editor_area import EditorArea
from notex.core import split_state
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
from notex.ui.link_index_service import LinkIndexService
from notex.ui.backlinks import BacklinksPanel
from notex.ui.completion import CompletionPopup
from notex.core.wikilinks import find_heading_line, link_name, rewrite_links, unlinked_mentions
from notex.core.encoding import read_text_file as _read_text_file
from notex.core.fileops import save_text_file
from notex.core.recent import add_recent, prune_recent
from notex.core.history import History, history_folder
from notex.core.winreg_assoc import SUPPORTED_EXTENSIONS, build_association, current_exe, is_temporary_location
from notex.ui.about_dialog import AboutDialog
from notex.ui.settings_dialog import SettingsDialog
from notex.ui.widgets import IconButton

QWIDGETSIZE_MAX = 16777215
from notex.ui.recent_dialog import RecentDialog
from notex.ui.winapi import apply_dark_titlebar, bring_to_front


def _register_viewers() -> None:
    """Viewer-Tabs (Bild, später Hex/PDF) bei den Tab-Gruppen anmelden."""
    from notex.ui.editor_tabs import EditorTabs
    from notex.ui.image_view import ImagePage
    EditorTabs.register_viewer("image", ImagePage)      # "hex" meldet das Modul „Hex & Dateianalyse“ an
    try:
        from notex.ui.pdf_view import PdfPage
    except ImportError:              # PySide6 ohne QtPdf: PDFs öffnen dann als Hex
        return
    EditorTabs.register_viewer("pdf", PdfPage)


class MainWindow(QMainWindow):
    def __init__(self, root: Path, config: dict[str, Any], on_save_config) -> None:
        super().__init__()
        _register_viewers()
        self.root = root
        self.config = config
        self._save_config = on_save_config
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.theme_store = ThemeStore(app_root() / "themes")
        config["recent_files"] = prune_recent(config["recent_files"])

        self.sidebar = Sidebar(root, config)
        self.tabs = EditorArea(root, config)   # eine oder zwei Tab-Gruppen, spricht wie ein EditorTabs
        self.tabs.font_size = config["font_size"]
        self.tabs.paper_mode = config["paper_mode"]
        self.links = LinkIndexService(root)
        self.tabs.resolve_link = self.links.resolve
        self.backlinks = BacklinksPanel()
        self._completions: dict[int, CompletionPopup] = {}
        self._relink_timer = QTimer(self)
        self._relink_timer.setSingleShot(True)
        self._relink_timer.setInterval(300)
        self._relink_timer.timeout.connect(self._after_index_update)
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
        self.tabs.set_corner_widget(self.sidebar_button)

        # Rechte Seite: Tabs oben, darunter (ausblendbar) die Suchen/Ersetzen-Leiste
        editor_area = QWidget()
        editor_layout = QVBoxLayout(editor_area)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        # Ohne offene Datei zeigt der Stack den Empty State statt der leeren Tab-Leiste
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.empty_state)
        self.editor_stack.addWidget(self.tabs)
        # Backlinks-Panel: unten (unter dem Blatt) oder rechts, per Einstellung
        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor_splitter.addWidget(self.editor_stack)
        self.editor_splitter.addWidget(self.backlinks)
        self.editor_splitter.setStretchFactor(0, 1)
        self.editor_splitter.setCollapsible(0, False)
        self.backlinks.setVisible(bool(config.get("backlinks_visible", False)))
        editor_layout.addWidget(self.editor_splitter, 1)
        editor_layout.addWidget(self.find_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(editor_area)
        self.splitter.setStretchFactor(0, 0)  # Seitenleiste behält ihre Breite
        self.splitter.setStretchFactor(1, 1)  # Editor bekommt den Rest
        self.splitter.setCollapsible(1, False)
        self.setCentralWidget(self.splitter)

        self.association = build_association()   # None im Dev-Modus oder außerhalb von Windows
        hist_cfg = config.get("history", {})
        self.history = History(history_folder(app_root()), max_bytes=int(hist_cfg.get("max_mb", 200)) * 1024 * 1024)
        self._snapshots_since_limit = 0
        QTimer.singleShot(5000, self._enforce_history_limit)
        self._update_worker = None
        from notex.core.lookup import LookupService, SendGuard
        self.lookup_service = LookupService()
        self.send_guard = SendGuard()
        self._card = None
        self._available_release = None
        QTimer.singleShot(8000, self.check_updates)   # nach dem Start, nie blockierend
        # Verschlüsselte Notizen nach Inaktivität sperren
        import time as _time
        self._last_activity = _time.monotonic()
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(15_000)
        self._lock_timer.timeout.connect(self._check_auto_lock)
        self._lock_timer.start()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        self.registry = ActionRegistry()
        self.registry.recent = list(config.get("recent_commands", []))
        self.file_index = FileIndexService(root, config)
        self.file_index.attach_tree(self.sidebar.tree)
        self.palette = PaletteOverlay(self, self.registry, self.file_index.index)
        self.palette.open_file.connect(self._open_from_palette)
        self.palette.goto_line.connect(lambda line: self._with_editor(lambda e: e.goto_line(line)))
        self.palette.run_command.connect(self._run_command)
        self._connect_signals()
        from notex.ui.structured_commands import StructuredCommands
        self.structured = StructuredCommands(self)
        self._build_menu()
        self._build_editor_actions()
        self._build_registry()
        from notex.core.modules import ModuleRegistry
        self.modules = ModuleRegistry(self.config)
        self._install_modules()
        self.modules.on_change(lambda _key, _on: self.apply_tree_filter())
        self.apply_tree_filter()
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
        tree.open_hex_requested.connect(self.open_as_hex)
        tree.checksums_requested.connect(self.show_checksums)
        tree.follow_requested.connect(self.toggle_live)
        self.tabs.view_mode_changed.connect(self._on_view_mode_changed)
        self.tabs.pdf_quote.connect(self._insert_pdf_quote)
        tree.path_deleted.connect(lambda p: (self.links.remove(self.tabs.relative(p)), self.file_index.request_rescan()))

        self.tabs.status_changed.connect(self._update_status)
        self.tabs.file_opened.connect(self._on_file_opened)
        self.tabs.link_activated.connect(self._on_link_activated)
        self.tabs.preview_link.connect(self._on_preview_link)
        self.tabs.completion_requested.connect(self._on_completion_requested)
        self.tabs.file_saved.connect(self._on_saved_for_links)
        self.tabs.file_saved.connect(lambda path: self._snapshot(path))
        self.tabs.file_opened.connect(lambda path: self._snapshot(path, label="geöffnet"))
        self.tabs.currentChanged.connect(lambda _i: self._refresh_backlinks())
        self.file_index.updated.connect(self._on_file_index_updated)
        self.links.updated.connect(lambda: self._relink_timer.start())
        self.backlinks.open_requested.connect(lambda rel, line: self.tabs.open_file(self.root / rel, line=line))
        self.backlinks.link_requested.connect(self._link_mention)
        self.backlinks.closed.connect(lambda: self.set_backlinks_visible(False))
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
        self.watcher.file_changed_externally.connect(lambda p: None if self.tabs.is_external(p) else self.links.update_path(self.tabs.relative(p)))
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
        file_menu.addAction(self._action("Versionsverlauf …", "Ctrl+Shift+Y", self.show_history))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Neue Datei aus Vorlage …", "Ctrl+Shift+T", lambda: self.new_from_template()))
        file_menu.addAction(self._action("Neue Woche", "Alt+W", lambda: self.new_week()))
        file_menu.addAction(self._action("Nächste Woche anlegen", None, lambda: self.new_week(next_week=True)))
        file_menu.addAction(self._action("Vorlagen-Ordner öffnen", None, self.open_templates_folder))
        file_menu.addAction(self._action("Unbenutzte Bilder finden …", None, self.find_unused_images))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Neue verschlüsselte Notiz …", "Ctrl+Shift+Alt+N", self.new_encrypted_note))
        file_menu.addAction(self._action("Datei verschlüsseln …", None, self.encrypt_current_file))
        file_menu.addAction(self._action("Passwort ändern …", None, self.change_note_password))
        file_menu.addAction(self._action("Verschlüsselte Notizen sperren", "Ctrl+Shift+L", lambda: self.lock_all(manual=True)))
        file_menu.addAction(self._action("Live verfolgen ein/aus", "Ctrl+Shift+Alt+F", lambda: self.toggle_live()))
        self._action("PDF: Markierung als Zitat einfügen", "Ctrl+Shift+Alt+Q", self.quote_from_pdf)
        self._module_anchor = file_menu.addSeparator()      # Module fügen ihre Einträge davor ein
        self.file_menu = file_menu
        file_menu.addAction(self._action("Speichern", QKeySequence.StandardKey.Save, self.tabs.save_current))
        file_menu.addAction(self._action("Speichern unter …", "Ctrl+Shift+Alt+S", self.tabs.save_current_as))
        file_menu.addAction(self._action("Alle speichern", "Ctrl+Shift+S", self.tabs.save_all))
        file_menu.addAction(self._action("Tab schließen", "Ctrl+W", self.tabs.close_current))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Einstellungen …", "Ctrl+,", self.open_settings))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Beenden", "Ctrl+Q", self.close))

        edit_menu = self.menuBar().addMenu("&Bearbeiten")
        self.edit_menu = edit_menu
        edit_menu.addAction(self._action("Suchen", QKeySequence.StandardKey.Find, lambda: self.open_find(False)))
        edit_menu.addAction(self._action("Ersetzen", "Ctrl+H", lambda: self.open_find(True)))
        edit_menu.addAction(self._action("Ersetzen in Dateien …", "Ctrl+Shift+H", self.open_replace_in_files))
        lookup_menu = edit_menu.addMenu("Nachschlagen")
        self.lookup_wikipedia_action = self._action("Wikipedia nachschlagen", "Ctrl+Alt+W", lambda: self.lookup_current("wikipedia"))
        self.lookup_wiktionary_action = self._action("Wiktionary nachschlagen", "Ctrl+Alt+T", lambda: self.lookup_current("wiktionary"))
        self.lookup_web_action = self._action("Im Web suchen (Browser)", "Ctrl+Alt+G", lambda: self.lookup_current("web"))
        for action in (self.lookup_wikipedia_action, self.lookup_wiktionary_action, self.lookup_web_action):
            lookup_menu.addAction(action)
        data_menu = edit_menu.addMenu("JSON/YAML")
        data_menu.addAction(self._action("Formatieren", "Shift+Alt+F", self.structured.format))
        data_menu.addAction(self._action("Minimieren", "Shift+Alt+M", self.structured.minify))
        data_menu.addAction(self._action("Prüfen", "Shift+Alt+V", self.structured.validate))
        data_menu.addSeparator()
        data_menu.addAction(self._action("Pfad kopieren (Baumansicht)", None, self.structured.copy_path))
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
        self.backlinks_action = self._action("Backlinks", "Ctrl+Shift+K", lambda: self.set_backlinks_visible(not self.backlinks.isVisible()), checkable=True)
        self.backlinks_action.setChecked(bool(self.config.get("backlinks_visible", False)))
        view_menu.addAction(self.backlinks_action)
        view_menu.addSeparator()
        self.split_action = self._action("Editor teilen", "Ctrl+\\", self.toggle_split, checkable=True)
        view_menu.addAction(self.split_action)
        view_menu.addAction(self._action("Teilung: nebeneinander / untereinander", "Ctrl+Alt+\\", self.toggle_split_orientation))
        view_menu.addAction(self._action("Tab in andere Gruppe verschieben", "Ctrl+Alt+Right", self.tabs.move_current_to_other_group))
        view_menu.addAction(self._action("Datei auch in anderer Gruppe öffnen", "Ctrl+Alt+Shift+Right", self.tabs.open_in_other_group))
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
        help_menu.addAction(self._action("Nach Updates suchen …", None, lambda: self.check_updates(manual=True)))
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
        for editor in self.tabs.views_of(new_path):
            self.tabs.refresh_tab_icon(editor)
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
        """Start aus dem Temp-Ordner warnen; wurde der Notex-Ordner verschoben, zeigt die Registrierung noch
        auf die alte EXE – dann einmal nachfragen, ob sie auf den neuen Pfad umgeschrieben werden soll."""
        exe = current_exe()
        if exe and is_temporary_location(exe):
            dialogs.warn(self, "Notex läuft aus einem temporären Ordner",
                         "Die Notex.exe wurde vermutlich direkt aus der ZIP gestartet.",
                         informative="Windows hat sie nach %TEMP% entpackt. Notizen (data/) und Einstellungen würden "
                                     "dort landen und beim nächsten Aufräumen verschwinden.\n\n"
                                     "Bitte die ZIP komplett entpacken (Rechtsklick → „Alle extrahieren…“), "
                                     "z. B. nach C:\\Apps\\Notex, und Notex.exe von dort starten.")
            return
        linux = self._linux_integration()
        if linux is not None:
            try:
                status = linux.status()
                if status.registered and not status.matches(linux.exe) and dialogs.confirm(
                        self, "Notex-Ordner verschoben", "Der Starter im Anwendungsmenü zeigt noch auf den alten Ort.",
                        yes="Neu registrieren", no="Später", informative=f"Registriert: {status.exe_path}\nJetzt hier: {linux.exe}"):
                    linux.install()
            except OSError:
                pass
            return
        if self.association is None:
            return
        try:
            status = self.association.status()
        except Exception:  # noqa: BLE001 – Registry-Zugriff darf den Start nie stören
            return
        if not status.registered or status.matches(self.association.exe_path):
            return
        where = "existiert nicht mehr" if not status.exe_exists else "ist eine andere Kopie"
        if dialogs.confirm(self, "Notex-Ordner verschoben",
                           "Die Dateizuordnung zeigt noch auf die alte Notex.exe.",
                           yes="Pfad aktualisieren", no="Später",
                           informative=f"Registriert: {status.exe_path} ({where}).\n"
                                       f"Jetzt hier: {self.association.exe_path}\n\n"
                                       "Solange der alte Pfad eingetragen ist, blendet Windows Notex unter „Öffnen mit“ "
                                       "und in den Standard-Apps aus. Aktualisieren schreibt nur die Pfade neu, die "
                                       "gewählten Endungen bleiben."):
            try:
                self.association.update_path()
                self.toast.show_message("Dateizuordnung auf den neuen Pfad gesetzt", "check")
            except OSError as error:
                dialogs.warn(self, "Pfad aktualisieren", str(error))
        else:
            self.toast.show_message("Später: Einstellungen > System > „Pfad aktualisieren“", "triangle-alert")

    def build_system_settings(self, page) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget
        from notex.ui.widgets import Chip
        from PySide6.QtWidgets import QCheckBox

        page.section("Updates")
        update_box = QCheckBox("Einmal täglich auf GitHub nach neuen Versionen sehen")
        update_box.setChecked(bool(self.config.get("update_check", {}).get("enabled", True)))
        update_box.toggled.connect(lambda on: self.config.setdefault("update_check", {}).__setitem__("enabled", on))
        page.add(update_box)
        check_now = QPushButton("Jetzt prüfen")
        check_now.clicked.connect(lambda: self.check_updates(manual=True))
        check_row = QHBoxLayout()
        check_row.setContentsMargins(0, 0, 0, 0)
        check_row.addWidget(check_now)
        check_row.addStretch(1)
        check_widget = QWidget()
        check_widget.setLayout(check_row)
        page.add(check_widget)
        page.note("Es wird nur die öffentliche Release-Liste abgerufen (api.github.com), ohne Kennung oder "
                  "Nutzungsdaten. Notex lädt und installiert nie etwas selbst – es zeigt nur einen Hinweis.")

        import sys as _sys
        if _sys.platform.startswith("linux"):
            self._build_linux_settings(page)
            return

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
                if same:
                    hint = ""
                elif status.exe_exists:
                    hint = "\nAchtung: zeigt auf eine andere Kopie von Notex. „Pfad aktualisieren“ trägt diese hier ein."
                else:
                    hint = ("\nAchtung: diese Notex.exe existiert nicht mehr (Ordner verschoben oder gelöscht). Windows "
                            "blendet Notex deshalb unter „Öffnen mit“ aus – „Pfad aktualisieren“ behebt das.")
                status_label.setText(f"Registriert: ja · Endungen: {', '.join(status.extensions) or '–'}\n"
                                     f"Pfad: {status.exe_path}{hint}")
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
        self.backlinks.retheme()
        self.tabs.relink_all()
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
        if old.parent != new.parent and new.suffix.lower() in (".md", ".markdown") and new.is_file():
            QTimer.singleShot(0, lambda: self._move_note_assets(old, new))
        if not self.tabs.is_external(new):
            try:
                self.history.rename(self.tabs.relative(old), self.tabs.relative(new))   # Verlauf zieht mit
            except OSError:
                pass
        QTimer.singleShot(0, lambda: self._update_links_after_rename(old, new))
        # Watcher auf die neuen Pfade umhängen
        for editor in self.tabs.editors():
            if editor.path == new or new in editor.path.parents:
                self.watcher.watch(editor.path)
        self.watcher.unwatch(old)
        self._update_status()

    def _on_external_change(self, path: Path) -> None:
        if any(page.view_mode == "live" and page.editor.path == path for page in self.tabs.pages()):
            return                                   # „Live verfolgen“ liest die Änderungen selbst – keine Rückfrage
        editor = self.tabs.editor_for(path)
        if editor is None:
            for viewer in self.tabs.viewers():       # Viewer (Hex, Bild …) lesen nur – still neu laden
                if viewer.path == path and hasattr(viewer, "reload"):
                    viewer.reload()
            self._update_status()
            return
        if editor.encrypted:
            self._on_external_change_encrypted(editor)
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
                self._snapshot(path, label="extern geändert")
            except OSError as error:
                dialogs.warn(self, "Neu laden fehlgeschlagen", str(error))
        else:
            editor.document().setModified(True)  # Inhalt weicht jetzt von der Platte ab
        self._update_status()

    def _on_external_change_encrypted(self, editor) -> None:
        """Verschlüsselte Datei wurde von außen geändert: gesperrt → nichts zu tun; entsperrt → mit Schlüssel neu laden."""
        from notex.core import crypto_notes
        group = self.tabs.group_of(editor)
        if editor.locked or group is None:
            if group is not None:
                page = group.page_for(editor)
                if page is not None:
                    group._show_locked(page)
            return
        if not dialogs.confirm(self, "Datei extern geändert",
                               f"„{editor.path.name}“ wurde außerhalb von {APP_NAME} geändert. Neu laden?",
                               yes="Neu laden", no="Behalten", danger=editor.is_dirty,
                               informative="Achtung: Deine ungespeicherten Änderungen gehen dabei verloren." if editor.is_dirty else ""):
            editor.document().setModified(True)
            return
        try:
            text = crypto_notes.open_with_key(editor.path.read_bytes(), editor.key)
        except (OSError, crypto_notes.NtxError) as error:
            editor.document().setModified(False)
            group.lock(editor, message=f"Neu laden mit dem bisherigen Schlüssel nicht möglich: {error}")
            return
        from notex.core.encoding import TextFile
        editor.replace_content(TextFile(text, "utf-8", "\n"))
        self._update_status()

    def _on_external_remove(self, path: Path) -> None:
        if any(page.view_mode == "live" and page.editor.path == path for page in self.tabs.pages()):
            return                                   # Rotation: die Live-Ansicht wartet auf die neue Datei
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
        if editor is not None and not self._in_data_view():
            func(editor)

    def _in_data_view(self) -> bool:
        """Tabelle/Baum sichtbar: Text-Befehle (Zeile duplizieren, Groß/klein …) würden den verdeckten Text ändern."""
        from notex.ui.paper import DATA_MODES
        page = self.tabs.current_page()
        return page is not None and page.view_mode in DATA_MODES

    def _current_file(self) -> Path | None:
        editor = self.tabs.current_editor()
        if editor is not None:
            return editor.path
        viewer = self.tabs.current_viewer()
        return viewer.path if viewer is not None else None

    # ---- Module ---------------------------------------------------------------------------------
    def apply_tree_filter(self) -> None:
        from notex.core.modules import show_all_files
        self.sidebar.tree.set_extensions(self.config["extensions"], show_all_files(self.config))

    def _install_modules(self) -> None:
        """Jedes Modul meldet einen Aktivator an; ausgeschaltete Module hängen nichts ein (siehe core/modules.py)."""
        self._editor_menu_providers: list = []
        self._analysis_dialogs: dict[str, list] = {}
        self.modules.contribute("hex", self._activate_hex)
        self.modules.contribute("variables", self._activate_variables)
        self.modules.contribute("strings", lambda: self._activate_analysis(
            "strings", "Strings extrahieren …", "Ctrl+Alt+S", "text-search", self.show_strings,
            "strings zeichenketten ascii utf-16 binär extrahieren"))
        self.modules.contribute("embedded", lambda: self._activate_analysis(
            "embedded", "Eingebettete Dateien finden …", "Ctrl+Alt+F", "file-search", self.show_embedded,
            "binwalk eingebettet carving extrahieren signatur versteckt anhang"))
        self.modules.contribute("entropy", lambda: self._activate_analysis(
            "entropy", "Entropie anzeigen …", "Ctrl+Alt+E", "activity", self.show_entropy,
            "entropie verschlüsselt komprimiert zufall kurve"))
        self.modules.contribute("metadata", lambda: self._activate_analysis(
            "metadata", "Metadaten anzeigen …", "Ctrl+Alt+M", "scan-eye", self.show_metadata,
            "metadaten exif gps kamera autor pdf office docx entfernen bereinigen xmp iptc"))
        self.modules.contribute("timeline", self._activate_timeline)
        self.modules.contribute("ioc", self._activate_ioc)
        self.modules.contribute("ports", self._activate_ports)
        self.modules.contribute("ip_conflicts", self._activate_ip_conflicts)
        self.modules.contribute("rdap", self._activate_rdap)
        self.modules.contribute("scanner", self._activate_scanner)
        self.modules.contribute("yara", self._activate_yara)

    def _module_action(self, text: str, shortcut: str | None, slot, menu=None) -> QAction:
        """QAction für ein Modul: mit Shortcut am Fenster, optional im Menü vor dem Modul-Anker."""
        action = self._action(text, shortcut, slot)
        if menu is not None:
            menu.insertAction(self._module_anchor, action)
        return action

    def _drop_actions(self, actions: list[QAction]) -> None:
        for action in actions:
            self.file_menu.removeAction(action)
            self.removeAction(action)
            action.deleteLater()

    def _activate_hex(self):
        from notex.ui.editor_tabs import EditorTabs
        from notex.ui.hex_view import HexPage
        EditorTabs.register_viewer("hex", HexPage)
        actions = [self._module_action("Als Hex öffnen", "Ctrl+Shift+Alt+H", lambda: self.open_as_hex(), self.file_menu),
                   self._module_action("Prüfsummen …", "Ctrl+Shift+Alt+C", lambda: self.show_checksums(), self.file_menu)]
        self.registry.add("file:hex", "Als Hex öffnen", lambda: self.open_as_hex(), category="Datei",
                          shortcut="Ctrl+Shift+Alt+H", keywords="hex binär bytes hexdump offset")
        self.registry.add("file:checksums", "Prüfsummen (MD5, SHA-1, SHA-256, SHA-512)", lambda: self.show_checksums(),
                          category="Datei", shortcut="Ctrl+Shift+Alt+C", keywords="hash prüfsumme checksum sha256 md5 vergleichen")

        def tree_entries(menu, path: Path) -> None:
            menu.addAction(icon("binary"), "Als Hex öffnen", lambda: self.open_as_hex(path))
            menu.addAction(icon("hash"), "Prüfsummen …", lambda: self.show_checksums(path))
        self.sidebar.tree.menu_providers.append(tree_entries)

        def undo() -> None:
            EditorTabs.VIEWERS.pop("hex", None)          # Binärdateien öffnen wieder im Texteditor
            for group in getattr(self.tabs, "groups", [self.tabs]):
                for viewer in list(group.viewers()):
                    if viewer.kind == "hex":
                        group._remove_viewer(viewer)
            self._drop_actions(actions)
            self.registry.remove("file:hex")
            self.registry.remove("file:checksums")
            if tree_entries in self.sidebar.tree.menu_providers:
                self.sidebar.tree.menu_providers.remove(tree_entries)
            self._update_status()
        return undo

    # ---- Modul: Variablen -----------------------------------------------------------------------
    def _activate_variables(self):
        from notex.paths import app_root
        from notex.ui.editor import Editor
        from notex.ui.variables_service import VariableService
        service = VariableService(app_root() / "variables.json", self.config)
        self.variable_service = service
        Editor.variables = service
        service.changed.connect(self._refresh_variables)
        self._refresh_variables()
        submenu = self.edit_menu.addMenu("Variablen")
        actions = [self._action("Variable einfügen", "Ctrl+Alt+V", self._insert_variable),
                   self._action("Variablen verwalten …", "Ctrl+Shift+Alt+V", lambda: self.open_settings("Variablen")),
                   self._action("Alle Variablen in dieser Datei durch Werte ersetzen", None, self._replace_all_variables),
                   self._action("Variablen in Auswahl entfernen", None, self._escape_selected_variables)]
        for action in actions:
            submenu.addAction(action)
        commands = {
            "var:insert": ("Variable einfügen", self._insert_variable, "Ctrl+Alt+V"),
            "var:manage": ("Variablen verwalten …", lambda: self.open_settings("Variablen"), "Ctrl+Shift+Alt+V"),
            "var:replace_all": ("Alle Variablen in dieser Datei durch Werte ersetzen", self._replace_all_variables, ""),
            "var:escape_selection": ("Variablen in Auswahl entfernen", self._escape_selected_variables, ""),
        }
        for key, (title, slot, shortcut) in commands.items():
            self.registry.add(key, title, slot, category="Variablen", shortcut=shortcut,
                              keywords="variable textbaustein platzhalter § token wert")
        self._editor_menu_providers.append(self._variable_menu)
        self.sidebar.variable_source = lambda: self.variable_service
        self.sidebar.in_values.setVisible(True)

        def undo() -> None:
            Editor.variables = None
            self.sidebar.variable_source = None
            self.sidebar.in_values.setVisible(False)
            service.changed.disconnect(self._refresh_variables)
            self.variable_service = None
            for action in actions:
                self.removeAction(action)
                action.deleteLater()
            self.edit_menu.removeAction(submenu.menuAction())
            submenu.deleteLater()
            for key in commands:
                self.registry.remove(key)
            if self._variable_menu in self._editor_menu_providers:
                self._editor_menu_providers.remove(self._variable_menu)
            self._refresh_variables()         # Tokens wieder als normaler Text
        return undo

    variable_service = None

    def _refresh_variables(self) -> None:
        """Werte/Präfix geändert oder Modul umgeschaltet: alle Editoren und Vorschauen neu zeichnen."""
        for editor in self.tabs.editors():
            if editor.highlighter is not None:
                editor.highlighter.reset()
            editor.viewport().update()
        for page in self.tabs.pages():
            if page.preview is not None and page.view_mode in ("preview", "split"):
                page._refresh_preview()

    def _insert_variable(self) -> None:
        editor = self.tabs.current_editor()
        if editor is not None and not self._in_data_view():
            editor.insert_variable_prefix()

    def _current_variable_editor(self):
        editor = self.tabs.current_editor()
        if editor is None or self.variable_service is None or self._in_data_view():
            return None
        if editor.isReadOnly() or getattr(editor, "locked", False):
            self.toast.show_message("Die Datei ist schreibgeschützt oder gesperrt", "lock")
            return None
        return editor

    def _replace_all_variables(self) -> None:
        from notex.core import variables as vb
        editor = self._current_variable_editor()
        if editor is None:
            return
        service = self.variable_service
        new_text, count = vb.replace_all(editor.toPlainText(), service.values, service.prefix)
        if not count:
            self.toast.show_message("Keine Variablen in dieser Datei", "info")
            return
        self.tabs.replace_text_keep_cursor(editor, new_text)
        self.toast.show_message(f"{count} Variable(n) durch Werte ersetzt – Ctrl+Z macht es rückgängig", "variable")

    def _escape_selected_variables(self) -> None:
        from notex.core import variables as vb
        editor = self._current_variable_editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            self.toast.show_message("Erst Text markieren", "info")
            return
        service = self.variable_service
        text = editor.toPlainText()
        new_text, count = vb.escape_all(text, service.values, service.prefix, cursor.selectionStart(), cursor.selectionEnd())
        if not count:
            self.toast.show_message("Keine Variablen in der Auswahl", "info")
            return
        self.tabs.replace_text_keep_cursor(editor, new_text)
        self.toast.show_message(f"{count} Variable(n) in normalen Text verwandelt", "variable")

    def _variable_menu(self, editor, menu) -> None:
        """Kontextmenü-Gruppe „Variable“ für das Vorkommen unter dem Rechtsklick."""
        from notex.core import variables as vb
        hit = getattr(editor, "_context_token", None)
        service = self.variable_service
        if hit is None or service is None:
            return
        token, block = hit
        writable = not editor.isReadOnly() and not getattr(editor, "locked", False)
        base = block.position()
        menu.addSeparator()
        title = menu.addAction(icon("variable"), f"Variable {service.prefix}{token.name}")
        title.setEnabled(False)

        def apply(new_line: str) -> None:
            cursor = QTextCursor(editor.document())
            cursor.setPosition(base)
            cursor.setPosition(base + len(block.text()), QTextCursor.MoveMode.KeepAnchor)
            editor._grouped(lambda: cursor.insertText(new_line))

        line = block.text()
        if token.escaped:
            menu.addAction("Wieder als Variable verwenden", lambda: apply(vb.unescape_token(line, token))).setEnabled(writable)
        else:
            menu.addAction("Variable entfernen (als normalen Text behalten)",
                           lambda: apply(vb.escape_token(line, token))).setEnabled(writable)
            menu.addAction("Durch Wert ersetzen",
                           lambda: apply(vb.replace_token(line, token, service.values))).setEnabled(writable)
        menu.addAction(icon("pencil"), "Variable bearbeiten …", lambda: self.edit_variable(token.name))

    def edit_variable(self, name: str) -> None:
        from notex.ui.variables_dialog import VariableEditDialog
        service = self.variable_service
        if service is None:
            return
        variable = service.get(name)
        dialog = VariableEditDialog(self, variable, [v.name for v in service.variables], service.prefix)
        if dialog.exec():
            service.upsert(dialog.result_variable(), old_name=name)

    # ---- Modul: Zeitleiste & Beweismittel --------------------------------------------------------
    def _activate_timeline(self):
        actions = [self._module_action("Zeitleiste anzeigen …", "Ctrl+Shift+Alt+Z", lambda: self.show_timeline(),
                                       self.file_menu),
                   self._action("Zur Zeitleiste hinzufügen …", "Ctrl+Alt+Z", lambda: self.add_to_timeline())]
        self.edit_menu.addAction(actions[1])
        keywords = "zeitleiste timeline forensik ereignis chronologie vorfall"
        evidence = "beweismittel chain of custody sicherstellung forensik"
        commands = {
            "timeline:show": ("Zeitleiste anzeigen", lambda: self.show_timeline(), "Ctrl+Shift+Alt+Z", keywords),
            "timeline:add": ("Zur Zeitleiste hinzufügen (aktuelle Zeile)", lambda: self.add_to_timeline(), "Ctrl+Alt+Z",
                             keywords),
            "timeline:new": ("Neue Zeitleiste", lambda: self.new_from_template("Zeitleiste.md"), "", keywords),
            "evidence:new": ("Beweismittel: neu (Chain of Custody)", lambda: self.new_from_template("Beweismittel.md"),
                             "", evidence),
            "evidence:hashes": ("Beweismittel: Prüfsummen einfügen …", lambda: self.insert_evidence_hashes(), "",
                                evidence + " prüfsumme hash sha256 md5"),
            "evidence:handover": ("Beweismittel: Übergabe eintragen", lambda: self.add_handover(), "",
                                  evidence + " übergabe"),
        }
        for key, (title, slot, shortcut, words) in commands.items():
            self.registry.add(key, title, slot, category="Zeitleiste & Beweismittel", shortcut=shortcut, keywords=words)
        self._editor_menu_providers.append(self._timeline_menu)
        dialogs_open: list = self._analysis_dialogs.setdefault("timeline", [])

        def undo() -> None:
            self.edit_menu.removeAction(actions[1])
            self._drop_actions(actions)
            for key in commands:
                self.registry.remove(key)
            if self._timeline_menu in self._editor_menu_providers:
                self._editor_menu_providers.remove(self._timeline_menu)
            for dialog in list(dialogs_open):
                dialog.close()
            dialogs_open.clear()
        return undo

    def _timeline_menu(self, editor, menu) -> None:
        from notex.core import timeline as tl
        action = menu.addAction(icon("clock-4"), "Zur Zeitleiste hinzufügen …\tCtrl+Alt+Z",
                                lambda: self.add_to_timeline(editor))
        if not tl.can_take_from(editor.path):
            action.setEnabled(False)
            action.setToolTip("Aus verschlüsselten Notizen wird nichts in eine unverschlüsselte Zeitleiste kopiert")

    def _timeline_candidates(self) -> list[Path]:
        from notex.core import timeline as tl
        found = tl.find_timelines(self.root)
        last = Path(self.config.get("timeline", {}).get("last", "") or ".")
        if last in found:
            found.remove(last)
            found.insert(0, last)
        return found

    def add_to_timeline(self, editor=None) -> None:
        """Aktuelle Zeile (bzw. erste Zeile der Auswahl) als Eintrag vorschlagen – Zeit aus der Zeile erkannt."""
        from notex.core import timeline as tl
        from notex.ui.timeline_dialog import EntryDialog
        editor = editor or self.tabs.current_editor()
        if editor is None:
            self.toast.show_message("Erst eine Datei öffnen und die Zeile anklicken", "info")
            return
        if not tl.can_take_from(editor.path):
            self.toast.show_message("Aus verschlüsselten Notizen wird nichts in eine Zeitleiste kopiert", "lock")
            return
        cursor = editor.textCursor()
        if cursor.hasSelection():
            line = cursor.selection().toPlainText().strip().split("\n")[0]
        else:
            line = cursor.block().text()
        is_timeline = tl.is_timeline(editor.toPlainText()[:4000])
        entry = tl.entry_from_line("" if is_timeline else line, "" if is_timeline else editor.path.name)
        candidates = self._timeline_candidates()
        if is_timeline and editor.path not in candidates:
            candidates.insert(0, editor.path)
        dialog = EntryDialog(self, entry, candidates, editor.path if is_timeline else None)
        if not dialog.exec():
            return
        target = dialog.target_path()
        if target is None:
            name = dialogs.ask_text(self, "Neue Zeitleiste", "Name:", "Zeitleiste")
            if not name:
                return
            target = self.root / (name if name.lower().endswith(".md") else f"{name}.md")
            if not fileops.is_within(target.resolve(), self.root.resolve()) or target.exists():
                dialogs.warn(self, "Neue Zeitleiste", f"„{target.name}“ gibt es schon oder liegt außerhalb von data/.")
                return
            try:
                fileops.atomic_write_bytes(target, tl.new_text(target.stem).encode("utf-8"))
            except OSError as error:
                dialogs.warn(self, "Neue Zeitleiste", str(error))
                return
            self.file_index.request_rescan()
        self.add_timeline_entry(target, dialog.entry())

    def add_timeline_entry(self, path: Path, entry) -> None:
        """In die Zeitleiste einfügen – offen: im Editor (ein Undo-Schritt), sonst direkt in die Datei."""
        from notex.core import timeline as tl
        self.config.setdefault("timeline", {})["last"] = str(path)
        editor = self.tabs.editor_for(path)
        if editor is not None:
            new, _line = tl.add_entry(editor.toPlainText(), entry)
            self.tabs.replace_text_keep_cursor(editor, new)
        else:
            try:
                from notex.core.encoding import encode_text
                original = read_text_file(path)
                new, _line = tl.add_entry(original.text, entry)
                fileops.atomic_write_bytes(path, encode_text(new, original.encoding, original.eol))
            except (OSError, UnicodeDecodeError) as error:
                dialogs.warn(self, "Zeitleiste", str(error))
                return
        self.toast.show_message(f"Eintrag in „{path.name}“ eingefügt ({tl.display(entry.time, 'utc')})", "clock-4")

    def show_timeline(self) -> None:
        from notex.core import timeline as tl
        from notex.ui.timeline_dialog import TimelineDialog
        editor = self.tabs.current_editor()
        if editor is None or not tl.is_timeline(editor.toPlainText()[:4000]):
            candidates = self._timeline_candidates()
            if not candidates:
                self.toast.show_message("Noch keine Zeitleiste – Palette „Neue Zeitleiste“", "info")
                return
            names = [str(p.relative_to(self.root)) if fileops.is_within(p, self.root) else str(p) for p in candidates]
            chosen = names[0] if len(names) == 1 else dialogs.choose(self, "Zeitleiste anzeigen", "Zeitleiste:", names)
            if chosen is None:
                return
            editor = self.tabs.open_file(candidates[names.index(chosen)])
            if editor is None:
                return
        dialog = TimelineDialog(self, editor)
        self._analysis_dialogs.setdefault("timeline", []).append(dialog)
        dialog.finished.connect(lambda _r, d=dialog: self._analysis_dialogs.get("timeline", []).remove(d)
                                if d in self._analysis_dialogs.get("timeline", []) else None)
        dialog.show()

    def _evidence_editor(self):
        editor = self.tabs.current_editor()
        if editor is None or self._in_data_view() or editor.isReadOnly() or getattr(editor, "locked", False):
            self.toast.show_message("Erst die Beweismittel-Notiz öffnen (beschreibbar)", "info")
            return None
        return editor

    def insert_evidence_hashes(self) -> None:
        """Datei wählen, MD5/SHA-1/SHA-256 im Hintergrund berechnen, als Zeilen in „## Prüfsummen“ einfügen."""
        from PySide6.QtWidgets import QFileDialog, QProgressDialog
        from notex.core import hashing
        from notex.ui.analysis_dialog import AnalysisWorker
        editor = self._evidence_editor()
        if editor is None:
            return
        chosen, _ = QFileDialog.getOpenFileName(self, "Prüfsummen berechnen für", str(self.root))
        if not chosen:
            return
        path = Path(chosen)
        progress = QProgressDialog(f"Prüfsummen für „{path.name}“ …", "Abbrechen", 0, 1000, self)
        progress.setWindowTitle("Beweismittel")
        progress.setMinimumDuration(400)
        worker = AnalysisWorker(lambda report, cancelled: hashing.hash_file(path, ("md5", "sha1", "sha256"),
                                                                            report, cancelled))
        worker.progress.connect(progress.setValue)
        progress.canceled.connect(lambda: setattr(worker, "cancel", True))

        def done(result, error: str) -> None:
            worker.wait()
            progress.close()
            self._hash_worker = None
            if result is None:
                if error:
                    dialogs.warn(self, "Prüfsummen", error)
                return
            self._insert_hash_rows(editor, path, result)
        worker.done.connect(done)
        self._hash_worker = worker
        worker.start()

    _hash_worker = None

    def _insert_hash_rows(self, editor, path: Path, digests: dict[str, str]) -> None:
        from notex.core import hashing
        from notex.core import timeline as tl
        text = editor.toPlainText()
        rows = [[hashing.LABELS[name], digests[name], path.name] for name in ("md5", "sha1", "sha256")]
        placed = True
        for row in rows:
            result = tl.append_row(text, "Prüfsummen", row)
            if result is None:
                placed = False
                break
            text = result[0]
        if placed:
            self.tabs.replace_text_keep_cursor(editor, text)
        else:                                     # keine Prüfsummen-Tabelle: an der Cursorposition einfügen
            table = "| Algorithmus | Wert | Datei |\n|---|---|---|\n" + "".join(
                "| " + " | ".join(tl.escape_cell(c) for c in row) + " |\n" for row in rows)
            cursor = editor.textCursor()
            editor._grouped(lambda: cursor.insertText(("\n" if cursor.positionInBlock() else "") + table))
        self.toast.show_message(f"MD5, SHA-1, SHA-256 von „{path.name}“ eingefügt", "hash")

    def add_handover(self) -> None:
        from datetime import datetime
        from notex.core import timeline as tl
        editor = self._evidence_editor()
        if editor is None:
            return
        now = datetime.now().astimezone().replace(second=0, microsecond=0)
        result = tl.append_row(editor.toPlainText(), "Übergaben", [tl.iso(now), "", "", "", ""])
        if result is None:
            self.toast.show_message("Keine Tabelle unter „## Übergaben“ – Vorlage „Beweismittel“ nutzen", "info")
            return
        text, line = result
        self.tabs.replace_text_keep_cursor(editor, text)
        row = text.split("\n")[line]
        editor.goto_line(line + 1, row.index(" | ", 2) + 3)          # Cursor in die Spalte „Von“

    # ---- Modul: YARA ----------------------------------------------------------------------------
    def _activate_yara(self):
        """Regel testen: aktuelle .yar-Datei (auch ungespeichert) gegen Datei/Ordner; Baum: Regel oder Ziel."""
        action = self._module_action("YARA-Regel testen …", "Ctrl+Alt+Y", lambda: self.test_yara(), self.file_menu)
        self.registry.add("yara:test", "YARA-Regel testen", lambda: self.test_yara(), category="Dateianalyse",
                          shortcut="Ctrl+Alt+Y", keywords="yara regel rule malware signatur prüfen scan")

        def file_entry(menu, path: Path) -> None:
            if path.suffix.lower() in (".yar", ".yara"):
                menu.addAction(icon("bug-play"), "YARA-Regel testen …", lambda: self.test_yara(rule=path))
            else:
                menu.addAction(icon("bug-play"), "Mit YARA-Regel prüfen …", lambda: self.test_yara(target=path))

        def folder_entry(menu, path: Path) -> None:
            menu.addAction(icon("bug-play"), "Mit YARA-Regel prüfen …", lambda: self.test_yara(target=path))
        tree = self.sidebar.tree
        tree.menu_providers.append(file_entry)
        tree.folder_menu_providers.append(folder_entry)
        dialogs_open: list = self._analysis_dialogs.setdefault("yara", [])

        def undo() -> None:
            self._drop_actions([action])
            self.registry.remove("yara:test")
            for providers, entry in ((tree.menu_providers, file_entry), (tree.folder_menu_providers, folder_entry)):
                if entry in providers:
                    providers.remove(entry)
            for dialog in list(dialogs_open):
                dialog.close()
            dialogs_open.clear()
        return undo

    def test_yara(self, rule: Path | None = None, target: Path | None = None) -> None:
        from PySide6.QtWidgets import QFileDialog
        from notex.core import yara_rules
        from notex.paths import data_dir
        from notex.ui.yara_dialog import RULE_SUFFIXES, YaraDialog
        if not yara_rules.available():
            self.toast.show_message("yara-python fehlt in diesem Build – YARA nicht verfügbar", "info")
            return
        editor = None
        if rule is None:
            current = self.tabs.current_editor()
            if current is not None and current.path.suffix.lower() in RULE_SUFFIXES:
                rule, editor = current.path, current
            else:
                last = Path(self.config.get("yara", {}).get("last_rule", "") or ".")
                if not (last.is_file() and last.suffix.lower() in RULE_SUFFIXES):
                    chosen = QFileDialog.getOpenFileName(self, "YARA-Regeln wählen", str(data_dir()),
                                                         "YARA-Regeln (*.yar *.yara)")[0]
                    if not chosen:
                        return
                    last = Path(chosen)
                rule = last
        if editor is None:
            editor = self.tabs.editor_for(rule)
        dialog = YaraDialog(self, rule, target, editor)
        self._analysis_dialogs.setdefault("yara", []).append(dialog)
        dialog.finished.connect(lambda _r, d=dialog: self._analysis_dialogs.get("yara", []).remove(d)
                                if d in self._analysis_dialogs.get("yara", []) else None)
        dialog.show()

    def mark_yara_error(self, editor, line: int | None) -> None:
        """Syntaxfehler der Regel im Editor rot unterwellen und hinspringen; None räumt auf."""
        if editor is None:
            return
        if getattr(editor, "_yara_error_hooked", False):
            editor.textChanged.disconnect(self._clear_yara_error)
            editor._yara_error_hooked = False
        if line is None:
            editor.set_problem(None)
            return
        block = editor.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            text = block.text()
            editor.set_problem(block.position() + len(text) - len(text.lstrip()))
            editor.goto_line(line)
            editor.textChanged.connect(self._clear_yara_error)
            editor._yara_error_hooked = True

    def _clear_yara_error(self) -> None:
        editor = self.sender()
        if editor is not None and getattr(editor, "_yara_error_hooked", False):
            editor.set_problem(None)
            editor.textChanged.disconnect(self._clear_yara_error)
            editor._yara_error_hooked = False

    # ---- Modul: Port-Infos ----------------------------------------------------------------------
    def _activate_ports(self):
        """Hover über Portangaben im Editor (offline) und „Port nachschlagen“."""
        from notex.core import ports
        from notex.ui.editor import Editor

        def hover(_editor, line: str, column: int):
            hit = ports.port_at(line, column)
            if hit is None:
                return None
            info = ports.lookup(hit[0])
            return ports.tooltip_html(info) if info else None
        Editor.hover_providers.append(hover)
        action = self._action("Port nachschlagen …", "Ctrl+Alt+P", lambda: self.lookup_port())
        self.edit_menu.addAction(action)
        self.registry.add("ports:lookup", "Port nachschlagen", lambda: self.lookup_port(), category="Netzwerk",
                          shortcut="Ctrl+Alt+P", keywords="port dienst service iana tcp udp rdp smb nummer")

        def undo() -> None:
            if hover in Editor.hover_providers:
                Editor.hover_providers.remove(hover)
            self.edit_menu.removeAction(action)
            self._drop_actions([action])
            self.registry.remove("ports:lookup")
        return undo

    def lookup_port(self) -> None:
        from notex.core import ports
        from notex.ui.ports_dialog import PortDialog
        term = ""
        editor = self.tabs.current_editor()
        if editor is not None and not getattr(editor, "locked", False):
            cursor = editor.textCursor()
            if cursor.hasSelection():
                term = cursor.selectedText().strip()[:40]
            else:
                hit = ports.port_at(cursor.block().text(), cursor.positionInBlock())
                term = str(hit[0]) if hit else ""
        PortDialog(self, term).show()

    # ---- Modul: IP-Konflikte --------------------------------------------------------------------
    ip_index = None

    def _activate_ip_conflicts(self):
        """IP-Zuordnungen aus data/ (ohne .ntx) sammeln: Übersicht, Konflikte im Editor unterwellt + Tooltip."""
        from notex.core import ipmap
        from notex.ui.editor import Editor
        self.ip_index = ipmap.IpIndex(self.root)
        self._ip_conflicts: dict = {}
        self._ip_timer = QTimer(self)
        self._ip_timer.setSingleShot(True)
        self._ip_timer.setInterval(800)
        self._ip_timer.timeout.connect(lambda: self._mark_ip_conflicts(only_current=True))
        action = self._module_action("IP-Übersicht …", "Ctrl+Shift+Alt+I", lambda: self.show_ip_overview(),
                                     self.file_menu)
        self.registry.add("ip:overview", "IP-Übersicht (Zuordnungen, Konflikte, freie Adressen)",
                          lambda: self.show_ip_overview(), category="Netzwerk", shortcut="Ctrl+Shift+Alt+I",
                          keywords="ip adresse konflikt subnetz netz frei dhcp host zuordnung")

        def hover(editor, line: str, column: int):
            if not ipmap.IpIndex.eligible(editor.path):
                return None
            for item in ipmap.extract(line, editor.path):
                start = line.find(item.ip)
                if item.ip in self._ip_conflicts and start <= column <= start + len(item.ip):
                    others = [f"{o.host} ({o.file.name}:{o.line + 1})" for o in self._ip_conflicts[item.ip]
                              if not (o.file == editor.path and o.host == item.host)]
                    import html
                    return (f"<b>IP-Konflikt {html.escape(item.ip)}</b><br>auch vergeben an: "
                            + html.escape(", ".join(others)))
            return None
        Editor.hover_providers.append(hover)
        self.tabs.status_changed.connect(self._ip_timer.start)
        self.tabs.file_saved.connect(self._ip_file_saved)
        self.tabs.file_opened.connect(self._ip_timer.start)
        self.refresh_ip_index(full=True)
        dialogs_open: list = self._analysis_dialogs.setdefault("ip_conflicts", [])

        def undo() -> None:
            if hover in Editor.hover_providers:
                Editor.hover_providers.remove(hover)
            self.tabs.status_changed.disconnect(self._ip_timer.start)
            self.tabs.file_saved.disconnect(self._ip_file_saved)
            self.tabs.file_opened.disconnect(self._ip_timer.start)
            self._ip_timer.stop()
            self._drop_actions([action])
            self.registry.remove("ip:overview")
            for editor in self.tabs.editors():
                editor.set_module_marks("ip_conflicts", [])
            for dialog in list(dialogs_open):
                dialog.close()
            dialogs_open.clear()
            self.ip_index = None
        return undo

    def refresh_ip_index(self, full: bool = False) -> None:
        """Abgleich im Hintergrund (liest nur geänderte Dateien), danach Übersicht und Markierungen aktualisieren."""
        from notex.core import ipmap
        from notex.ui.analysis_dialog import AnalysisWorker
        index = self.ip_index
        if index is None or getattr(self, "_ip_worker", None) is not None:
            return
        snapshot = dict(index.files)

        def job(_progress, _cancelled):
            copy = ipmap.IpIndex(index.root, index.limit)
            copy.files = snapshot
            copy.refresh()
            return copy.files

        def done(result, _error: str) -> None:
            worker.wait()
            self._ip_worker = None
            if result is not None and self.ip_index is index:
                index.files = result
                self._mark_ip_conflicts()
        worker = AnalysisWorker(job)
        worker.done.connect(done)
        self._ip_worker = worker
        worker.start()

    _ip_worker = None

    def _ip_file_saved(self, path: Path) -> None:
        if self.ip_index is not None and self.ip_index.update_file(path):
            self._mark_ip_conflicts()

    def _ip_assignments(self) -> list:
        """Index + ungespeicherter Text offener Editoren (nie .ntx)."""
        override = {e.path: e.toPlainText() for e in self.tabs.editors()
                    if e.document().isModified() and not getattr(e, "encrypted", False)}
        return self.ip_index.assignments(override)

    def _mark_ip_conflicts(self, only_current: bool = False) -> None:
        from notex.core import ipmap
        if self.ip_index is None:
            return
        assignments = self._ip_assignments()
        self._ip_conflicts = ipmap.conflicts(assignments)
        editors = [self.tabs.current_editor()] if only_current else list(self.tabs.editors())
        for editor in editors:
            if editor is None:
                continue
            if getattr(editor, "locked", False) or not ipmap.IpIndex.eligible(editor.path):
                editor.set_module_marks("ip_conflicts", [])
                continue
            spans = []
            document = editor.document()
            for item in ipmap.extract(editor.toPlainText(), editor.path):
                if item.ip in self._ip_conflicts:
                    block = document.findBlockByNumber(item.line)
                    column = block.text().find(item.ip)
                    if column >= 0:
                        spans.append((block.position() + column, len(item.ip)))
            editor.set_module_marks("ip_conflicts", spans)
        for dialog in self._analysis_dialogs.get("ip_conflicts", []):
            dialog.show_assignments(assignments)

    def show_ip_overview(self) -> None:
        from notex.ui.ip_dialog import IpOverviewDialog
        if self.ip_index is None:
            return
        dialog = IpOverviewDialog(self)
        self._analysis_dialogs.setdefault("ip_conflicts", []).append(dialog)
        dialog.finished.connect(lambda _r, d=dialog: self._analysis_dialogs.get("ip_conflicts", []).remove(d)
                                if d in self._analysis_dialogs.get("ip_conflicts", []) else None)
        dialog.show_assignments(self._ip_assignments())
        dialog.show()
        self.refresh_ip_index()

    # ---- Modul: RDAP/ASN -------------------------------------------------------------------------
    _rdap_client = None

    def _activate_rdap(self):
        """RDAP/ASN nur auf ausdrücklichen Klick: Palette/Kürzel und Kontextmenü für IP, Domain oder AS-Nummer."""
        action = self._action("RDAP / ASN abfragen …", "Ctrl+Alt+R", lambda: self.rdap_lookup())
        self.edit_menu.addAction(action)
        self.registry.add("rdap:lookup", "RDAP / ASN abfragen (IP, Domain, AS-Nummer)", lambda: self.rdap_lookup(),
                          category="Netzwerk", shortcut="Ctrl+Alt+R",
                          keywords="rdap whois asn inhaber netzblock abuse registrar ip domain")
        self._editor_menu_providers.append(self._rdap_menu)

        def undo() -> None:
            self.edit_menu.removeAction(action)
            self._drop_actions([action])
            self.registry.remove("rdap:lookup")
            if self._rdap_menu in self._editor_menu_providers:
                self._editor_menu_providers.remove(self._rdap_menu)
        return undo

    def _rdap_menu(self, editor, menu) -> None:
        from notex.core import rdap
        cursor = editor.textCursor()
        token = rdap.token_at(cursor.block().text(), cursor.positionInBlock()) if not cursor.hasSelection() else \
            cursor.selectedText().strip()[:120]
        if not token:
            return
        try:
            kind, value = rdap.classify(token)
        except rdap.RdapError:
            return
        reason = rdap.local_reason(value) if kind == "ip" else None
        label = f"RDAP: {token}" + (f" ({reason} – keine Abfrage)" if reason else "")
        action = menu.addAction(icon("globe-lock"), label + "\tCtrl+Alt+R", lambda: self.rdap_lookup(token, editor))
        action.setEnabled(reason is None)

    def rdap_lookup(self, query: str | None = None, editor=None) -> None:
        from notex.core import rdap
        from notex.ui.rdap_dialog import RdapDialog
        editor = editor or self.tabs.current_editor()
        if query is None and editor is not None and not getattr(editor, "locked", False):
            cursor = editor.textCursor()
            query = cursor.selectedText().strip()[:120] if cursor.hasSelection() else \
                (rdap.token_at(cursor.block().text(), cursor.positionInBlock()) or "")
        if query and editor is not None and rdap.needs_confirmation(editor.path):
            if not dialogs.confirm(self, "RDAP-Abfrage", f"„{query}“ stammt aus einer verschlüsselten Notiz und wird "
                                   "an öffentliche Registries (IANA, RIR, RIPEstat) gesendet. Trotzdem abfragen?"):
                return
        if self._rdap_client is None:
            self._rdap_client = rdap.Client()          # Sitzungs-Cache für die Laufzeit der App
        RdapDialog(self, self._rdap_client, query or "", editor).show()

    # ---- Modul: Netzwerk-Scanner ----------------------------------------------------------------
    def _activate_scanner(self):
        """Scanner nur auf ausdrücklichen Start; öffentliche Ziele verlangen eine Bestätigung."""
        action = self._module_action("Netzwerk-Scanner …", "Ctrl+Shift+Alt+P", lambda: self.open_scanner(),
                                     self.file_menu)
        self.registry.add("scan:open", "Netzwerk-Scanner (Hosts und offene Ports im eigenen Netz)",
                          lambda: self.open_scanner(), category="Netzwerk", shortcut="Ctrl+Shift+Alt+P",
                          keywords="scan scanner netzwerk port host offen tcp nmap discovery")
        dialogs_open: list = self._analysis_dialogs.setdefault("scanner", [])

        def undo() -> None:
            self._drop_actions([action])
            self.registry.remove("scan:open")
            for dialog in list(dialogs_open):
                dialog.close()
            dialogs_open.clear()
        return undo

    def open_scanner(self) -> None:
        from notex.ui.scan_dialog import ScanDialog
        dialog = ScanDialog(self)
        self._analysis_dialogs.setdefault("scanner", []).append(dialog)
        dialog.finished.connect(lambda _r, d=dialog: self._analysis_dialogs.get("scanner", []).remove(d)
                                if d in self._analysis_dialogs.get("scanner", []) else None)
        dialog.show()

    # ---- Modul: IOCs entschärfen ----------------------------------------------------------------
    def _activate_ioc(self):
        """Umwandeln: IOCs (URLs, Domains, IPs, E-Mails) in Auswahl oder Datei entschärfen bzw. scharf machen."""
        submenu = self.edit_menu.addMenu("Umwandeln")
        actions = [self._action("IOCs entschärfen", "Ctrl+Alt+D", lambda: self.convert_iocs(True)),
                   self._action("IOCs wieder scharf machen", "Ctrl+Shift+Alt+D", lambda: self.convert_iocs(False))]
        for action in actions:
            submenu.addAction(action)
        keywords = "ioc defang refang entschärfen hxxp url domain ip e-mail bericht ticket"
        self.registry.add("ioc:defang", "IOCs entschärfen (Auswahl oder Datei)", lambda: self.convert_iocs(True),
                          category="Umwandeln", shortcut="Ctrl+Alt+D", keywords=keywords)
        self.registry.add("ioc:refang", "IOCs wieder scharf machen (Auswahl oder Datei)", lambda: self.convert_iocs(False),
                          category="Umwandeln", shortcut="Ctrl+Shift+Alt+D", keywords=keywords)
        self._editor_menu_providers.append(self._ioc_menu)

        def undo() -> None:
            for action in actions:
                self.removeAction(action)
                action.deleteLater()
            self.edit_menu.removeAction(submenu.menuAction())
            submenu.deleteLater()
            self.registry.remove("ioc:defang")
            self.registry.remove("ioc:refang")
            if self._ioc_menu in self._editor_menu_providers:
                self._editor_menu_providers.remove(self._ioc_menu)
        return undo

    def _ioc_menu(self, editor, menu) -> None:
        writable = not editor.isReadOnly() and not getattr(editor, "locked", False)
        scope = "Auswahl" if editor.textCursor().hasSelection() else "Datei"
        submenu = menu.addMenu(icon("shield"), "Umwandeln")
        submenu.addAction(f"IOCs entschärfen ({scope})\tCtrl+Alt+D", lambda: self.convert_iocs(True, editor)).setEnabled(writable)
        submenu.addAction(f"IOCs wieder scharf machen ({scope})\tCtrl+Shift+Alt+D",
                          lambda: self.convert_iocs(False, editor)).setEnabled(writable)

    def convert_iocs(self, defang: bool, editor=None) -> None:
        """Auswahl (oder ganze Datei) umwandeln – ein Undo-Schritt, alles nur im Editor (auch bei .ntx nichts auf Platte)."""
        from notex.core import ioc
        editor = editor or self.tabs.current_editor()
        if editor is None or self._in_data_view():
            self.toast.show_message("Erst eine Textdatei öffnen", "info")
            return
        if editor.isReadOnly() or getattr(editor, "locked", False):
            self.toast.show_message("Die Datei ist schreibgeschützt oder gesperrt", "lock")
            return
        skip_code = bool(self.config.get("ioc", {}).get("skip_code", True))
        convert = ioc.defang if defang else ioc.refang
        cursor = editor.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            new, count = convert(cursor.selection().toPlainText(), skip_code=skip_code)
            if count:
                editor._grouped(lambda: cursor.insertText(new))
                cursor.setPosition(start)
                cursor.setPosition(start + len(new), QTextCursor.MoveMode.KeepAnchor)
                editor.setTextCursor(cursor)
        else:
            new, count = convert(editor.toPlainText(), skip_code=skip_code)
            if count:
                self.tabs.replace_text_keep_cursor(editor, new)
        if not count:
            self.toast.show_message("Keine IOCs gefunden" if defang else "Nichts Entschärftes gefunden", "info")
            return
        what = "entschärft" if defang else "wieder scharf gemacht"
        self.toast.show_message(f"{count} Stelle(n) {what} – Ctrl+Z macht es rückgängig", "shield")

    def _activate_analysis(self, key: str, title: str, shortcut: str, icon_name: str, opener, keywords: str):
        """Gemeinsamer Aktivator für Datei-Analysen: Menü Datei, Palette, Kürzel, Baum-Kontextmenü."""
        action = self._module_action(title, shortcut, lambda: opener(), self.file_menu)
        self.registry.add(f"analysis:{key}", title.replace(" …", ""), lambda: opener(), category="Dateianalyse",
                          shortcut=shortcut, keywords=keywords)

        def tree_entry(menu, path: Path) -> None:
            menu.addAction(icon(icon_name), title, lambda: opener(path))
        self.sidebar.tree.menu_providers.append(tree_entry)
        dialogs_open: list = self._analysis_dialogs.setdefault(key, [])

        def undo() -> None:
            self._drop_actions([action])
            self.registry.remove(f"analysis:{key}")
            if tree_entry in self.sidebar.tree.menu_providers:
                self.sidebar.tree.menu_providers.remove(tree_entry)
            for dialog in list(dialogs_open):          # „keine Panels“: offene Analysefenster schließen
                dialog.close()
            dialogs_open.clear()
        return undo

    def _open_analysis(self, key: str, factory, path: Path | None) -> None:
        target = self._analysis_target(path)
        if target is None:
            return
        dialog = factory(target)
        self._analysis_dialogs.setdefault(key, []).append(dialog)
        dialog.finished.connect(lambda _r, d=dialog: self._analysis_dialogs.get(key, []).remove(d)
                                if d in self._analysis_dialogs.get(key, []) else None)
        dialog.show()

    def show_strings(self, path: Path | None = None) -> None:
        from notex.ui.strings_dialog import StringsDialog
        self._open_analysis("strings", lambda target: StringsDialog(self, target, self.config), path)

    def show_embedded(self, path: Path | None = None) -> None:
        from notex.ui.embedded_dialog import EmbeddedDialog
        self._open_analysis("embedded", lambda target: EmbeddedDialog(self, target), path)

    def show_entropy(self, path: Path | None = None) -> None:
        from notex.ui.entropy_dialog import EntropyDialog
        self._open_analysis("entropy", lambda target: EntropyDialog(self, target), path)

    def show_metadata(self, path: Path | None = None) -> None:
        from notex.ui.metadata_dialog import MetadataDialog
        self._open_analysis("metadata", lambda target: MetadataDialog(self, target), path)

    def show_in_hex(self, path: Path, offset: int, length: int = 1) -> None:
        """Sprung aus Strings/Eingebettete Dateien/Entropie an eine Stelle der Datei (Modul Hex & Dateianalyse)."""
        if not self.modules.enabled("hex"):
            self.toast.show_message("Für die Hex-Ansicht das Modul „Hex & Dateianalyse“ einschalten", "info")
            return
        viewer = self.tabs.open_viewer(Path(path), "hex")
        if viewer is not None:
            viewer.select_range(offset, length)

    def _analysis_target(self, path: Path | None) -> Path | None:
        """Datei für ein Analyse-Werkzeug: übergeben, sonst der aktuelle Tab, sonst die Auswahl im Baum."""
        path = path or self._current_file() or self.sidebar.tree.selected_path()
        if path is None or not Path(path).is_file():
            self.toast.show_message("Erst eine Datei öffnen oder im Baum auswählen", "info")
            return None
        return Path(path)

    def open_as_hex(self, path: Path | None = None) -> None:
        """Beliebige Datei als Hex (nur lesen) – bei .ntx sieht man nur den Geheimtext von der Platte."""
        path = path or self._current_file()
        if path is None or not Path(path).is_file():
            self.toast.show_message("Keine Datei zum Anzeigen", "info")
            return
        self.tabs.open_viewer(Path(path), "hex")

    def _current_pdf(self):
        viewer = self.tabs.current_viewer() if self.tabs.current_editor() is None else None
        if viewer is None or getattr(viewer, "kind", "") != "pdf":
            for group in getattr(self.tabs, "groups", []):     # im Split: der PDF-Tab der anderen Gruppe
                candidate = group.current_viewer()
                if candidate is not None and getattr(candidate, "kind", "") == "pdf":
                    return candidate
            return None
        return viewer

    def quote_from_pdf(self) -> None:
        viewer = self._current_pdf()
        if viewer is None:
            self.toast.show_message("Kein PDF offen", "info")
        elif not viewer.canvas.selected_text():
            self.toast.show_message("Erst im PDF Text markieren", "info")
        else:
            viewer.quote()

    def toggle_pdf_outline(self) -> None:
        viewer = self._current_pdf()
        if viewer is not None and viewer.outline_button.isEnabled():
            viewer.outline_button.toggle()
        elif viewer is not None:
            self.toast.show_message("Dieses PDF hat keine Lesezeichen", "info")

    def _insert_pdf_quote(self, viewer, markdown: str) -> None:
        """Zitat aus dem PDF in die Notiz, die im ANDEREN Teil der geteilten Ansicht aktiv ist. Ohne Teilung:
        Zwischenablage (mit Hinweis) – nie irgendwo ungefragt hineinschreiben."""
        from PySide6.QtWidgets import QApplication
        target = None
        for group in getattr(self.tabs, "groups", []):
            if viewer not in group.viewers():
                target = group.current_editor() or target
        if target is None:
            QApplication.clipboard().setText(markdown)
            self.toast.show_message("Zitat in der Zwischenablage – zum direkten Einfügen die Ansicht teilen (Ctrl+\\) "
                                    "und im anderen Teil eine Notiz öffnen", "clipboard")
            return
        if target.locked or target.read_only or self.tabs.is_read_only(target.path):
            QApplication.clipboard().setText(markdown)
            self.toast.show_message("Notiz ist gesperrt oder schreibgeschützt – Zitat in der Zwischenablage", "lock")
            return
        cursor = target.textCursor()
        cursor.clearSelection()
        before = target.toPlainText()[:cursor.position()]
        prefix = "" if not before or before.endswith("\n\n") else ("\n" if before.endswith("\n") else "\n\n")
        target._grouped(lambda: cursor.insertText(prefix + markdown + "\n"))
        target.setTextCursor(cursor)
        target.ensureCursorVisible()
        self.toast.show_message(f"Zitat eingefügt in „{target.path.name}“", "quote")

    def _on_view_mode_changed(self, mode: str) -> None:
        """Nach „Live verfolgen“: Datei neu beobachten – nach einer Rotation ist es eine andere Datei."""
        editor = self.tabs.current_editor()
        if mode != "live" and editor is not None and editor.path.is_file() and not editor.encrypted:
            self.watcher.watch(editor.path)

    def toggle_live(self, path: Path | None = None) -> None:
        """„Live verfolgen“ ein/aus: neue Zeilen unten anhängen, nur lesend, Filter nur in der Anzeige."""
        if path is not None:
            if fileops.is_encrypted_path(path):
                self.toast.show_message("Verschlüsselte Notizen lassen sich nicht live verfolgen", "lock")
                return
            self.tabs.open_file(Path(path))
        page = self.tabs.current_page()
        if page is None:
            self.toast.show_message("Live verfolgen geht für Textdateien im Editor", "info")
            return
        if page.view_mode == "live":
            if path is None:
                page.set_view_mode("edit")
                self.toast.show_message("Live verfolgen beendet", "square")
            return
        if not page.supports_live:
            self.toast.show_message("Nicht für verschlüsselte oder ungespeicherte Dateien", "info")
            return
        if page.editor.is_dirty:
            self.toast.show_message("Erst speichern – live verfolgen zeigt die Datei auf der Platte", "info")
            return
        page.set_view_mode("live")
        self.toast.show_message("Live verfolgen – nur lesend", "activity")

    def show_checksums(self, path: Path | None = None) -> None:
        from notex.ui.hash_dialog import HashDialog
        path = path or self._current_file()
        if path is None or not Path(path).is_file():
            self.toast.show_message("Keine Datei für Prüfsummen", "info")
            return
        HashDialog(self, Path(path)).exec()

    def open_find(self, with_replace: bool) -> None:
        """Ctrl+F/Ctrl+H – in der Tabellen-/Baumansicht springt der Fokus in deren Filterfeld, im Hex-Tab ins Suchfeld."""
        viewer = self.tabs.current_viewer() if self.tabs.current_editor() is None else None
        if viewer is not None and hasattr(viewer, "focus_search"):
            viewer.focus_search()
            return
        if self._in_data_view():
            self.tabs.current_page().data_view.focus_filter()
            return
        self.find_bar.open(with_replace=with_replace)

    def _build_editor_actions(self) -> None:
        a, ed = self._editor_action, self._with_editor
        a("undo", "undo-2", "Rückgängig", None, lambda: ed(lambda e: e.undo())).setToolTip("Rückgängig  Ctrl+Z")
        a("redo", "redo-2", "Wiederholen", None, lambda: ed(lambda e: e.redo())).setToolTip("Wiederholen  Ctrl+Y")
        a("find", "search", "Suchen", None, lambda: self.open_find(False)).setToolTip("Suchen  Ctrl+F")
        a("replace", "replace", "Ersetzen", None, lambda: self.open_find(True)).setToolTip("Ersetzen  Ctrl+H")
        a("font_smaller", "minus", "Textgröße verkleinern (Ansicht, ändert nichts an der Datei)", None, lambda: self.tabs.zoom(-1))
        a("font_larger", "plus", "Textgröße vergrößern (Ansicht, ändert nichts an der Datei)", None, lambda: self.tabs.zoom(+1))
        a("zoom_reset", "rotate-ccw", "Zoom zurücksetzen", None, lambda: self.tabs.set_font_size(FONT_SIZE.editor)).setToolTip("Zoom zurücksetzen  Ctrl+0")
        self.paper_toolbar_action = a("paper_mode", "minimize-2", "Blatt-Modus / volle Breite", None, self.toggle_paper_mode, checkable=True)
        self.paper_toolbar_action.setToolTip("Blatt zentrieren / volle Breite  Alt+P")
        self.split_toolbar_action = a("split", "square-split-horizontal", "Editor teilen / Teilung aufheben", None,
                                      self.toggle_split, checkable=True)
        self.split_toolbar_action.setToolTip("Editor teilen  Ctrl+\\")
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
        self.preview_action = a("preview", "eye", "Ansicht umschalten (Markdown: Vorschau · CSV: Tabelle · JSON/YAML: Baum)",
                                "Ctrl+Shift+V", self.cycle_preview)
        self.preview_action.setToolTip("Markdown-Vorschau umschalten  Ctrl+Shift+V")
        self.spell_toolbar_action = a("spell", "spell-check", "Rechtschreibung", None, self.toggle_spellcheck, checkable=True)
        self.spell_toolbar_action.setToolTip("Rechtschreibung prüfen  F7")
        self.grammar_toolbar_action = a("grammar", "languages", "Grammatik (LanguageTool)", None, self.toggle_grammar, checkable=True)
        self.grammar_toolbar_action.setToolTip("Grammatik prüfen  Shift+F7")
        self.toolbar_action = self._action("Bearbeitungsleiste", "Ctrl+Shift+E", self.tabs.toggle_toolbar, checkable=True)
        self.toolbar_action.setChecked(self.tabs.toolbar_visible)
        self.menuBar().actions()[2].menu().addAction(self.toolbar_action)   # Menü „Ansicht“
        self.tabs.open_font_settings = lambda: self.open_settings("Schrift")
        self.tabs.context_menu_hook = self._extend_context_menu
        self.tabs.image_hook = self._insert_images

    # ---- Linux-Desktop-Integration ----------------------------------------------------------
    def _linux_integration(self):
        """DesktopIntegration für die laufende gebaute App, sonst None (Dev-Modus, anderes System)."""
        import sys as _sys
        from notex.core.linux_desktop import DesktopIntegration
        exe = current_exe()
        if not _sys.platform.startswith("linux") or exe is None:
            return None
        import notex
        return DesktopIntegration(exe, Path(notex.__file__).resolve().parent / "assets" / "notex.png")

    def _build_linux_settings(self, page) -> None:
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget
        page.section("Linux-Desktop-Integration")
        status_label = QLabel()
        status_label.setObjectName("SettingsNote")
        status_label.setWordWrap(True)
        page.add(status_label)
        register = QPushButton("Im Anwendungsmenü registrieren")
        remove = QPushButton("Registrierung entfernen")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(register)
        row.addWidget(remove)
        row.addStretch(1)
        buttons = QWidget()
        buttons.setLayout(row)
        page.add(buttons)
        page.note("Legt nur Dateien in ~/.local/share an (notex.desktop, MIME-Typ für .ntx, Icon) – kein root, "
                  "nichts systemweit. Danach steht Notex im Anwendungsmenü und unter „Öffnen mit“. Zum Standardprogramm "
                  "macht man es selbst, z. B. über die Dateieigenschaften oder `xdg-mime default notex.desktop text/plain`. "
                  "Nach dem Verschieben des Notex-Ordners einfach erneut registrieren.")

        def refresh() -> None:
            integration = self._linux_integration()
            if integration is None:
                status_label.setText("Nicht verfügbar: nur aus der gebauten App (Notex-Ordner mit ausführbarer Datei).")
                register.setEnabled(False)
                remove.setEnabled(False)
                return
            status = integration.status()
            if status.registered:
                moved = "" if status.matches(integration.exe) else "\nAchtung: zeigt auf einen anderen Ort – erneut registrieren."
                status_label.setText(f"Registriert: {integration.desktop_file}\nProgramm: {status.exe_path}{moved}")
            else:
                status_label.setText("Nicht registriert.")
            register.setText("Erneut registrieren" if status.registered else "Im Anwendungsmenü registrieren")
            remove.setEnabled(status.registered)

        def do_register() -> None:
            integration = self._linux_integration()
            try:
                integration.install()
            except OSError as error:
                dialogs.warn(self, "Registrieren", str(error))
                return
            refresh()
            self.toast.show_message("Notex im Anwendungsmenü registriert", "check")

        def do_remove() -> None:
            integration = self._linux_integration()
            try:
                integration.uninstall()
            except OSError as error:
                dialogs.warn(self, "Registrierung entfernen", str(error))
                return
            refresh()
            self.toast.show_message("Registrierung entfernt", "check")

        register.clicked.connect(do_register)
        remove.clicked.connect(do_remove)
        refresh()

    # ---- Bilder in Notizen ---------------------------------------------------------------------
    def _assets_folder_name(self) -> str:
        return str(self.config.get("images", {}).get("assets_folder", "assets"))

    def _insert_images(self, editor, image, paths: list[str]) -> bool:
        """Ctrl+V mit Bild bzw. Bilddateien auf eine .md ziehen: als Datei in assets/ ablegen und verlinken.
        True = erledigt (auch wenn abgelehnt), False = normal weiter (z. B. Dateien öffnen)."""
        import shutil
        from datetime import datetime
        from notex.core.images import asset_name, assets_dir, can_embed_images, markdown_image
        if not can_embed_images(editor.path):
            if getattr(editor, "encrypted", False):
                self.toast.show_message("Keine Bilder in verschlüsselten Notizen – das Bild läge unverschlüsselt daneben", "lock")
                return True
            if image is not None:
                self.toast.show_message("Bilder einfügen geht nur in Markdown-Notizen (.md)", "info")
                return True
            return False     # Bilddateien auf eine .txt gezogen: wie bisher öffnen
        if editor.isReadOnly():
            return True
        folder = assets_dir(editor.path, self._assets_folder_name())
        links = []
        try:
            folder.mkdir(parents=True, exist_ok=True)
            existing = {p.name.lower() for p in folder.iterdir()}
            if image is not None:
                name = asset_name(editor.path, datetime.now(), ".png", existing)
                target = folder / name
                tmp = folder / f".{name}.tmp"
                if not image.save(str(tmp), "PNG"):
                    raise OSError("Bild konnte nicht gespeichert werden")
                import os
                os.replace(tmp, target)
                links.append(markdown_image(editor.path, target, "Bild"))
            for source in map(Path, paths):
                target = folder / source.name
                if target.exists() and target.resolve() != source.resolve():
                    target = fileops.unique_path(folder, source.stem, source.suffix)
                if target.resolve() != source.resolve():
                    shutil.copy2(source, target)
                links.append(markdown_image(editor.path, target, source.stem))
        except OSError as error:
            dialogs.warn(self, "Bild einfügen", str(error))
            return True
        editor.insert_text("\n".join(links))
        self.file_index.request_rescan()
        self.toast.show_message(f"{len(links)} Bild(er) in {folder.name}/ abgelegt", "image")
        return True

    def _move_note_assets(self, old: Path, new: Path) -> None:
        """Notiz in einen anderen Ordner verschoben: ihre Bilder aus assets/ mitnehmen und Links anpassen?"""
        import shutil
        from notex.core.images import plan_assets_move
        editor = self.tabs.editor_for(new)
        try:
            text = editor.toPlainText() if editor is not None else _read_text_file(new).text
        except (OSError, UnicodeDecodeError):
            return
        others: dict[Path, str] = {}
        for sibling in old.parent.glob("*.md"):
            try:
                others[sibling] = _read_text_file(sibling).text
            except (OSError, UnicodeDecodeError):
                continue
        plan = plan_assets_move(old, new, text, others, self._assets_folder_name())
        if plan.empty:
            return
        detail = (f"{len(plan.moves)} Bild(er) verschieben" + (f", {len(plan.copies)} kopieren (andere Notizen nutzen sie auch)"
                                                                if plan.copies else ""))
        if not dialogs.confirm(self, "Bilder mitnehmen?", f"„{new.name}“ verlinkt Bilder aus dem alten assets-Ordner.",
                               yes="Mitnehmen", no="Nicht mitnehmen",
                               informative=f"{detail} und die Links in der Notiz anpassen?"):
            return
        try:
            for source, target in plan.moves + plan.copies:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    continue
                if (source, target) in plan.moves:
                    shutil.move(str(source), str(target))
                else:
                    shutil.copy2(source, target)
        except OSError as error:
            dialogs.warn(self, "Bilder mitnehmen", str(error))
            return
        if plan.new_text != text:
            if editor is not None:
                was_clean = not editor.is_dirty
                self.tabs.replace_text_keep_cursor(editor, plan.new_text)
                if was_clean:
                    self.tabs.group_of(editor).save_editor(editor)
            else:
                self._write_tracked(new, _read_text_file(new), plan.new_text, "vor Bilder-Umzug")
        self.file_index.request_rescan()
        self.toast.show_message("Bilder mitgenommen", "image")

    def find_unused_images(self) -> None:
        from notex.core.images import NOTE_SUFFIXES, find_unused_images
        from notex.ui.unused_images_dialog import UnusedImagesDialog
        texts: dict[Path, str] = {}
        skipped_ntx = 0
        for rel in self.file_index.index.files:
            path = self.root / rel
            if fileops.is_encrypted_path(path):
                skipped_ntx += 1        # Inhalt unbekannt – nie entschlüsseln, nur zählen
                continue
            if path.suffix.lower() in NOTE_SUFFIXES:
                editor = self.tabs.editor_for(path)
                try:
                    texts[path] = editor.toPlainText() if editor is not None else _read_text_file(path).text
                except (OSError, UnicodeDecodeError):
                    continue
        unused = find_unused_images(self.root, texts)
        dialog = UnusedImagesDialog(self, self.root, unused, skipped_ntx)
        dialog.trashed.connect(lambda _paths: self.file_index.request_rescan())
        dialog.exec()

    # ---- Nachschlagen ------------------------------------------------------------------------
    def _lookup_cfg(self) -> dict:
        return self.config.setdefault("lookup", {})

    def _lookup_langs(self, editor) -> list[str]:
        from notex.core.lookup import languages_for
        tab = editor.language or self.config.get("spellcheck", {}).get("language", "de")
        return languages_for(str(self._lookup_cfg().get("language", "auto")), tab)

    def _extend_context_menu(self, editor, menu, term: str) -> None:
        """Kontextmenü des Editors: Text-Aktionen (die der Bearbeitungsleiste) und Nachschlagen."""
        from notex.core import lookup as lk
        from notex.theme.icons import icon as _icon
        from PySide6.QtGui import QAction
        actions = self.tabs.editor_actions
        writable = not editor.isReadOnly()
        for provider in self._editor_menu_providers:        # Module (z. B. Variablen) hängen ihre Gruppe ein
            provider(editor, menu)
        menu.addSeparator()
        keys = ["upper", "lower", "title"] + (["md_bold", "md_italic", "md_code", "md_link"]
                                              if editor.path.suffix.lower() in (".md", ".markdown") else [])
        for key in keys:
            action = actions.get(key)
            if action is not None:
                action.setEnabled(writable)
                action.setShortcutVisibleInContextMenu(True)
                menu.addAction(action)
        menu.addSeparator()
        cfg = self._lookup_cfg()
        online = bool(cfg.get("online", True))
        label = lk.menu_label(term) if term else "–"

        def add(icon_name: str, text: str, shortcut: str, source: str, enabled: bool, tooltip: str = "") -> None:
            from PySide6.QtGui import QKeySequence
            native = QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)   # „Strg+Alt+W“ wie die anderen
            action = QAction(_icon(icon_name), f"{text}\t{native}", menu)
            action.setEnabled(enabled)
            if tooltip:
                action.setToolTip(tooltip)
            action.triggered.connect(lambda _c=False, e=editor, t=term, s=source: self.lookup_term(s, e, t))
            menu.addAction(action)

        off = "" if online else " (in den Einstellungen aus)"
        add("book-open", f"Wikipedia: {label}{off}", "Ctrl+Alt+W", "wikipedia", bool(term) and online)
        add("book-a", f"Wiktionary: {label}{off}", "Ctrl+Alt+T", "wiktionary", bool(term) and online)
        text = lk.search_menu_text(term, cfg.get("engine", "google"), cfg.get("custom_url", "")) if term else "Im Web suchen"
        add("globe", text, "Ctrl+Alt+G", "web", bool(term))
        menu.setToolTipsVisible(True)

    def lookup_current(self, source: str) -> None:
        editor = self.tabs.current_editor()
        if editor is None or editor.locked:
            self.toast.show_message("Erst eine Datei öffnen und etwas markieren", "info")
            return
        term = editor.lookup_term()
        if not term:
            self.toast.show_message("Nichts markiert – Wort markieren oder den Cursor in ein Wort setzen", "info")
            return
        self.lookup_term(source, editor, term)

    def _confirm_send(self, editor, service: str) -> bool:
        """Bei .ntx vor jedem Senden fragen (bis „In dieser Sitzung nicht mehr fragen“)."""
        from notex.core.lookup import confirmation_text
        if not self.send_guard.needs_confirmation(bool(getattr(editor, "encrypted", False))):
            return True
        from PySide6.QtWidgets import QCheckBox, QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("Aus verschlüsselter Notiz senden?")
        box.setText(confirmation_text(service))
        box.setInformativeText("Die Notiz ist verschlüsselt – der markierte Begriff verlässt Notex dabei unverschlüsselt.")
        box.setIcon(QMessageBox.Icon.Warning)
        remember = QCheckBox("In dieser Sitzung nicht mehr fragen")
        box.setCheckBox(remember)
        yes = box.addButton("Fortfahren", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return False
        if remember.isChecked():
            self.send_guard.remember()
        return True

    def lookup_term(self, source: str, editor, term: str) -> None:
        """Wikipedia/Wiktionary in der Karte, Websuche nur im Browser. Netz nur bei dieser ausdrücklichen Aktion."""
        from notex.core import lookup as lk
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        term = lk.prepare_term(term)
        if not term:
            return
        cfg = self._lookup_cfg()
        if source == "web":
            engine, custom = cfg.get("engine", "google"), cfg.get("custom_url", "")
            if self._confirm_send(editor, lk.search_engine_name(engine, custom)):
                QDesktopServices.openUrl(QUrl(lk.search_url(term, engine, custom)))
            return
        if not cfg.get("online", True):
            self.toast.show_message("Nachschlagen online ist ausgeschaltet (Einstellungen › Nachschlagen)", "info")
            return
        if not self._confirm_send(editor, "Wikipedia" if source == "wikipedia" else "Wiktionary"):
            return
        card = self._lookup_card()
        card.open(source, term, self._lookup_langs(editor), editor.term_rect())

    def _lookup_card(self):
        from notex.ui.lookup_card import LookupCard
        if getattr(self, "_card", None) is None:
            self._card = LookupCard(self, self.lookup_service, self.config)
        return self._card

    # ---- Update-Check ------------------------------------------------------------------------
    def check_updates(self, manual: bool = False) -> None:
        """Automatisch höchstens einmal pro Tag (abschaltbar), manuell jederzeit. Lädt nie etwas herunter."""
        from notex.core import update_check
        from notex.ui.update_service import UpdateWorker
        cfg = self.config.setdefault("update_check", {})
        if not manual and (not cfg.get("enabled", True) or not update_check.should_check(float(cfg.get("last_check", 0) or 0))):
            return
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        worker = UpdateWorker()
        worker.done.connect(lambda payload, error, m=manual: self._on_update_result(payload, error, m))
        worker.finished.connect(lambda w=worker: setattr(self, "_update_worker", None) if self._update_worker is w else None)
        self._update_worker = worker
        worker.start()
        if manual:
            self.toast.show_message("Suche nach Updates …", "refresh-cw")

    def _on_update_result(self, payload, error: str, manual: bool) -> None:
        import time as _time
        from notex import __version__
        from notex.core import update_check
        cfg = self.config.setdefault("update_check", {})
        if error:
            if manual:
                dialogs.warn(self, "Nach Updates suchen", "Die Release-Liste konnte nicht abgerufen werden.",
                             informative=f"{error}\n\nOffline oder Proxy? Die Seite {update_check.RELEASES_PAGE} "
                                         "lässt sich auch im Browser öffnen.")
            return
        cfg["last_check"] = _time.time()
        release = update_check.update_available(payload, __version__, "" if manual else str(cfg.get("skipped", "")))
        self._available_release = release
        if release is None:
            if manual:
                self.toast.show_message(f"{APP_NAME} {__version__} ist aktuell", "check")
            return
        if manual:
            self._show_update_dialog(release)
        else:
            self.toast.show_message(f"{APP_NAME} {release.version_text} verfügbar – Hilfe › Nach Updates suchen", "download")

    def _show_update_dialog(self, release) -> None:
        from notex.ui.update_service import UpdateDialog
        dialog = UpdateDialog(self, release)
        dialog.skip_requested.connect(lambda version: self.config.setdefault("update_check", {}).__setitem__("skipped", version))
        dialog.exec()

    # ---- Vorlagen ---------------------------------------------------------------------------
    def templates_folder(self) -> Path:
        from notex.core.templates import ensure_defaults
        folder = app_root() / "templates"
        try:
            installed = self.config.setdefault("templates", {}).setdefault("installed", [])
            ensure_defaults(folder, installed)
        except OSError:
            pass
        return folder

    def _create_from_text(self, path: Path, text: str, cursor: int | None) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fileops.atomic_write_bytes(path, text.encode("utf-8"))
        except OSError as error:
            dialogs.warn(self, "Neue Datei", str(error))
            return
        self.file_index.request_rescan()
        editor = self.tabs.open_file(path)
        self.sidebar.tree.select_path(path)
        if editor is not None and cursor is not None:
            c = editor.textCursor()
            c.setPosition(min(cursor, len(editor.toPlainText())))
            editor.setTextCursor(c)
            editor.center_cursor()

    def new_from_template(self, name: str | None = None) -> None:
        from datetime import datetime
        from notex.core.templates import default_file_name, list_templates, render
        folder = self.templates_folder()
        names = [p.name for p in list_templates(folder)]
        if name is None:
            if not names:
                self.toast.show_message("Keine Vorlagen – Vorlagen-Ordner öffnen und .md/.txt ablegen", "info")
                return
            name = dialogs.choose(self, "Neue Datei aus Vorlage", "Vorlage:", names)
            if name is None:
                return
        try:
            template = (folder / name).read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            from notex.core.templates import DEFAULT_TEMPLATES
            template = DEFAULT_TEMPLATES.get(name)
            if template is None:
                dialogs.warn(self, "Vorlage", f"Vorlage „{name}“ nicht gefunden")
                return
        except (OSError, UnicodeDecodeError) as error:
            dialogs.warn(self, "Vorlage", str(error))
            return
        now = datetime.now()
        tree = self.sidebar.tree
        target_folder = tree.folder_for(tree.selected_path())
        file_name = dialogs.ask_text(self, "Neue Datei aus Vorlage", "Dateiname:", default_file_name(name, now))
        if not file_name:
            return
        if "." not in file_name:
            file_name += Path(name).suffix or ".md"
        if fileops.is_encrypted_path(file_name):
            dialogs.warn(self, "Neue Datei aus Vorlage", "Vorlagen erzeugen Klartext – für .ntx „Neue verschlüsselte Notiz“ nutzen.")
            return
        path = target_folder / file_name
        if not fileops.is_within(path.resolve(), self.root.resolve()):
            dialogs.warn(self, "Neue Datei aus Vorlage", "Der Dateiname führt aus data/ heraus.")
            return
        if path.exists():
            dialogs.warn(self, "Neue Datei aus Vorlage", f"„{file_name}“ gibt es schon.")
            return
        rendered = render(template, now, title=Path(file_name).stem)
        self._create_from_text(path, rendered.text, rendered.cursor)

    def new_week(self, next_week: bool = False) -> None:
        """Wochenplan für die aktuelle (oder nächste) ISO-Woche anlegen – gibt es ihn schon, wird er geöffnet."""
        from datetime import datetime, timedelta
        from notex.core.templates import monday_of, render, render_name, template_text
        cfg = self.config.get("templates", {})
        now = datetime.now()
        monday = monday_of(now.date()) + timedelta(days=7 if next_week else 0)
        folder_name = str(cfg.get("week_folder", "Wochen")).strip().strip("/\\") or "Wochen"
        folder = (self.root / folder_name)
        if not fileops.is_within(folder, self.root):
            folder = self.root / "Wochen"
        name = render_name(str(cfg.get("week_name", "KW{{week}} {{year}}")), now, base=monday) + ".md"
        path = folder / name
        if path.exists():
            self.tabs.open_file(path)
            self.sidebar.tree.select_path(path)
            self.toast.show_message(f"{name} gibt es schon – geöffnet", "calendar-clock")
            return
        template = template_text(self.templates_folder(), str(cfg.get("week_template", "Woche.md"))) \
            or template_text(self.templates_folder(), "Woche.md") or ""
        rendered = render(template, now, title=Path(name).stem, base=monday)
        self._create_from_text(path, rendered.text, rendered.cursor)
        self.toast.show_message(f"{name} angelegt", "calendar-clock")

    def open_templates_folder(self) -> None:
        fileops.reveal_in_file_manager(self.templates_folder())

    def _refresh_template_commands(self) -> None:
        """Jede Vorlage als eigener Befehl in der Command Palette („Vorlage: Besprechung“)."""
        from notex.core.templates import list_templates
        for command in list(self.registry.all()):
            if command.id.startswith("template:"):
                self.registry.remove(command.id)
        for path in list_templates(self.templates_folder()):
            self.registry.add(f"template:{path.name}", f"Vorlage: {path.stem}", lambda n=path.name: self.new_from_template(n),
                              category="Datei", keywords="neu vorlage template")

    # ---- Verschlüsselte Notizen ------------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:
        from PySide6.QtCore import QEvent
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            import time as _time
            self._last_activity = _time.monotonic()
        return False

    def _check_auto_lock(self) -> None:
        import time as _time
        minutes = int(self.config.get("encryption", {}).get("auto_lock_minutes", 5))
        if minutes > 0 and _time.monotonic() - self._last_activity >= minutes * 60:
            if self.lock_all():
                self._last_activity = _time.monotonic()   # fehlgeschlagen: erst nach dem nächsten Intervall erneut (keine Warnflut)

    def lock_all(self, manual: bool = False) -> list[str]:
        """Alle entsperrten .ntx sperren. Gibt die Namen zurück, die nicht gesperrt werden konnten."""
        unlocked = [e for e in self.tabs.editors() if e.encrypted and not e.locked]
        failed = [e.path.name for e in unlocked if not self.tabs.group_of(e).lock(e)]
        if manual or (unlocked and not failed):
            if unlocked:
                self.toast.show_message(f"{len(unlocked) - len(failed)} verschlüsselte Notiz(en) gesperrt", "lock")
            elif manual:
                self.toast.show_message("Keine entsperrte verschlüsselte Notiz offen", "lock")
        if failed:
            dialogs.warn(self, "Sperren", "Nicht gesperrt, weil das Speichern fehlschlug: " + ", ".join(failed))
        return failed

    def new_encrypted_note(self) -> None:
        from notex.core import crypto_notes
        from notex.ui.lock_overlay import PasswordDialog
        tree = self.sidebar.tree
        folder = tree.folder_for(tree.selected_path())
        name = dialogs.ask_text(self, "Neue verschlüsselte Notiz", "Name:", fileops.unique_path(folder, "Geheim", ".ntx").name)
        if not name:
            return
        if not name.lower().endswith(".ntx"):
            name += ".ntx"
        path = folder / name
        if path.exists():
            dialogs.warn(self, "Neue verschlüsselte Notiz", f"„{name}“ gibt es schon.")
            return
        dialog = PasswordDialog(self, "Passwort festlegen", f"Passwort für „{name}“. Ohne dieses Passwort kommt niemand "
                                "an den Inhalt – auch Notex nicht. Es gibt keine Wiederherstellung.")
        if not dialog.exec():
            return
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            key = crypto_notes.new_key(dialog.password)
            fileops.atomic_write_bytes(path, crypto_notes.seal("", key))
        except OSError as error:
            QApplication.restoreOverrideCursor()
            dialogs.warn(self, "Neue verschlüsselte Notiz", str(error))
            return
        QApplication.restoreOverrideCursor()
        editor = self.tabs.open_file(path)
        if editor is not None:
            self.tabs.group_of(editor).unlock_with_key(editor, "", key)
        self.file_index.request_rescan()
        tree.select_path(path)

    def encrypt_current_file(self) -> None:
        """Aktuelle Klartext-Datei als .ntx verschlüsseln; Verlauf des Originals löschen, Original auf Wunsch in den Papierkorb."""
        from notex.core import crypto_notes
        from notex.ui.lock_overlay import PasswordDialog
        editor = self.tabs.current_editor()
        if editor is None or editor.encrypted:
            self.toast.show_message("Erst eine unverschlüsselte Datei öffnen", "lock")
            return
        source = editor.path
        target = fileops.unique_path(source.parent, source.stem, ".ntx")
        dialog = PasswordDialog(self, "Datei verschlüsseln", f"„{source.name}“ wird als „{target.name}“ verschlüsselt "
                                "gespeichert. Ohne das Passwort gibt es keinen Weg zurück.")
        if not dialog.exec():
            return
        text = editor.toPlainText()
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            key = crypto_notes.new_key(dialog.password)
            fileops.atomic_write_bytes(target, crypto_notes.seal(text, key))
        except OSError as error:
            QApplication.restoreOverrideCursor()
            dialogs.warn(self, "Datei verschlüsseln", str(error))
            return
        QApplication.restoreOverrideCursor()
        if not self.tabs.is_external(source):
            self.history.forget(self.tabs.relative(source))   # Klartext-Versionen des Originals entfernen
        for view in self.tabs.views_of(source):
            view.document().setModified(False)
            self.tabs.group_of(view).remove_page(self.tabs.group_of(view).page_for(view), ask=False)
        new_editor = self.tabs.open_file(target)
        if new_editor is not None:
            self.tabs.group_of(new_editor).unlock_with_key(new_editor, text, key)
        if dialogs.confirm(self, "Original entfernen?", f"„{source.name}“ liegt noch unverschlüsselt auf der Platte.",
                           yes="In den Papierkorb", no="Behalten",
                           informative="Danach den Papierkorb leeren. Auf SSDs und in Backups können Reste "
                                       "des Klartexts trotzdem noch eine Weile existieren."):
            try:
                fileops.move_to_trash(source)
                self.tabs.close_paths_under(source)
                self.links.remove(self.tabs.relative(source))
            except Exception as error:  # noqa: BLE001 – send2trash hat eigene Fehlertypen
                dialogs.warn(self, "Original entfernen", str(error))
        self.file_index.request_rescan()
        self.sidebar.tree.select_path(target)

    def change_note_password(self) -> None:
        from notex.ui.lock_overlay import PasswordDialog
        editor = self.tabs.current_editor()
        if editor is None or not editor.encrypted:
            self.toast.show_message("Erst eine verschlüsselte Notiz öffnen", "lock")
            return
        if editor.locked:
            self.toast.show_message("Erst entsperren", "lock")
            return
        dialog = PasswordDialog(self, "Passwort ändern", f"Neues Passwort für „{editor.path.name}“.", ask_current=True)
        if not dialog.exec():
            return
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        error = self.tabs.group_of(editor).change_password(editor, dialog.current_password, dialog.password)
        QApplication.restoreOverrideCursor()
        if error:
            dialogs.warn(self, "Passwort ändern", error)
        else:
            self.toast.show_message("Passwort geändert", "key-round")

    # ---- Versionshistorie ----------------------------------------------------------------
    def _history_enabled(self) -> bool:
        return bool(self.config.get("history", {}).get("enabled", True))

    def _snapshot(self, path: Path, text: str | None = None, label: str = "") -> None:
        """Schnappschuss nach Speichern/Öffnen/Neuladen. Nie für externe Dateien oder .ntx (Klartext!)."""
        if not self._history_enabled() or self.tabs.is_external(path) or path.suffix.lower() == ".ntx":
            return
        if text is None:
            editor = self.tabs.editor_for(path)
            if editor is None:
                return
            text = editor.toPlainText()
        try:
            if self.history.snapshot(self.tabs.relative(path), text, label=label) is not None:
                self._snapshots_since_limit += 1
                if self._snapshots_since_limit >= 50:
                    self._enforce_history_limit()
        except OSError:
            pass   # Historie darf Speichern nie blockieren

    def _write_tracked(self, path: Path, text_file, new_text: str, label: str) -> None:
        """Datei außerhalb des Editors neu schreiben – vorher den alten Stand in die Historie."""
        self._snapshot(path, text_file.text, label=label)
        save_text_file(path, new_text, text_file.encoding, text_file.eol)
        self._snapshot(path, new_text)

    def _enforce_history_limit(self) -> None:
        self._snapshots_since_limit = 0
        self.history.max_bytes = int(self.config.get("history", {}).get("max_mb", 200)) * 1024 * 1024
        try:
            self.history.enforce_limit()
        except OSError:
            pass

    def show_history(self) -> None:
        editor = self.tabs.current_editor()
        if editor is None:
            self.toast.show_message("Erst eine Datei öffnen", "info")
            return
        if editor.path.suffix.lower() == ".ntx":
            self.toast.show_message("Verschlüsselte Notizen haben keinen Verlauf (sonst läge Klartext auf der Platte)", "lock")
            return
        if self.tabs.is_external(editor.path):
            self.toast.show_message("Verlauf gibt es nur für Dateien in data/", "info")
            return
        from notex.ui.history_dialog import HistoryDialog
        dialog = HistoryDialog(self, self.history, self.tabs.relative(editor.path), editor.toPlainText())
        dialog.restore_requested.connect(lambda text, e=editor: self._restore_version(e, text))
        dialog.exec()

    def _restore_version(self, editor, text: str) -> None:
        self._snapshot(editor.path, label="vor Wiederherstellen")   # aktuellen Stand sichern, falls ungespeichert
        self.tabs.replace_text_keep_cursor(editor, text)
        self.toast.show_message("Version wiederhergestellt – Ctrl+Z nimmt es zurück, Ctrl+S speichert", "timer-reset")

    # ---- Ersetzen in Dateien -------------------------------------------------------------
    def open_replace_in_files(self) -> None:
        from notex.ui.replace_dialog import ReplaceInFilesDialog
        dialog = getattr(self, "_replace_dialog", None)
        if dialog is None:
            dialog = ReplaceInFilesDialog(self, self.root, self.config)
            dialog.apply_requested.connect(self._apply_replace_in_files)
            self._replace_dialog = dialog
        # offene, ungespeicherte Dateien: den Editor-Text nehmen, nicht die Platte
        dialog.overrides = {e.path: e.toPlainText() for e in self.tabs.editors()
                            if e.is_dirty and not e.encrypted and not self.tabs.is_external(e.path)}
        query = self.sidebar.search_field.text() if self.sidebar.search_field.text().strip() else dialog.find_field.text()
        dialog.prefill(query, self.sidebar.regex.isChecked(), self.sidebar.whole_word.isChecked())
        dialog.show()
        dialog.raise_()
        dialog.refresh()

    def _apply_replace_in_files(self, query, replacement: str, chosen: dict) -> None:
        from notex.core.search import apply_replace
        files = lines_total = 0
        failed: list[str] = []
        for path, line_numbers in chosen.items():
            views = self.tabs.views_of(path)
            editor = views[0] if views else None
            try:
                if editor is not None:
                    new_text, count = apply_replace(editor.toPlainText(), query, replacement, line_numbers)
                    if count:
                        was_clean = not editor.is_dirty
                        self.tabs.replace_text_keep_cursor(editor, new_text)
                        if was_clean:
                            self.tabs.group_of(editor).save_editor(editor)
                else:
                    text_file = _read_text_file(path)
                    new_text, count = apply_replace(text_file.text, query, replacement, line_numbers)
                    if count:
                        self._write_tracked(path, text_file, new_text, "vor Ersetzen")
                        if not self.tabs.is_external(path):
                            self.links.update_path(self.tabs.relative(path))
            except (OSError, UnicodeDecodeError) as error:
                failed.append(f"{path.name}: {error}")
                continue
            if count:
                files += 1
                lines_total += count
        if failed:
            dialogs.warn(self, "Ersetzen in Dateien", "Nicht alle Dateien konnten geschrieben werden:",
                         informative="\n".join(failed[:10]))
        self.toast.show_message(f"{lines_total} Zeilen in {files} Dateien ersetzt", "replace-all")
        self.file_index.request_rescan()

    # ---- Geteilter Editor ----------------------------------------------------------------
    def toggle_split(self) -> None:
        if self.tabs.current_editor() is None and self.tabs.current_viewer() is None and not self.tabs.is_split:
            self.toast.show_message("Erst eine Datei öffnen, dann teilen", "info")
            self.split_action.setChecked(False)
            return
        from_viewer = self.tabs.current_editor() is None
        split = self.tabs.toggle_split()
        self.split_action.setChecked(split)
        if split and from_viewer:    # z. B. PDF links, Notiz rechts – für „Als Zitat in Notiz einfügen“
            self.toast.show_message("Geteilt – im neuen Teil eine Notiz öffnen (Ctrl+P)", "square-split-horizontal")
            return
        self.toast.show_message("Editor geteilt – Tabs lassen sich zwischen den Gruppen ziehen" if split else "Teilung aufgehoben",
                                "square-split-horizontal")

    def toggle_split_orientation(self) -> None:
        orientation = self.tabs.toggle_orientation()
        self.toast.show_message("Gruppen untereinander" if orientation == "vertical" else "Gruppen nebeneinander",
                                "square-split-vertical" if orientation == "vertical" else "square-split-horizontal")

    # ---- Markdown-Vorschau -------------------------------------------------------------
    VIEW_MODE_NAMES = {"edit": "Bearbeiten", "preview": "Vorschau", "split": "Geteilte Ansicht", "table": "Tabelle",
                       "tree": "Baum"}
    VIEW_MODE_HINT = "Vorschau gibt es für Markdown (.md), die Tabelle für CSV/TSV, den Baum für JSON/YAML"

    def cycle_preview(self) -> None:
        mode = self.tabs.cycle_view_mode()
        if mode is None:
            self.toast.show_message(self.VIEW_MODE_HINT, "info")
            return
        page = self.tabs.current_page()
        name = "Text" if mode == "edit" and page is not None and not page.supports_preview else self.VIEW_MODE_NAMES[mode]
        self.toast.show_message(name, {"table": "table", "tree": "list-tree"}.get(mode, "eye"))

    def set_preview_mode(self, mode: str) -> None:
        if not self.tabs.set_view_mode(mode):
            self.toast.show_message(self.VIEW_MODE_HINT, "info")

    def _on_preview_link(self, editor, target: str) -> None:
        """Link aus der Vorschau: relativer Pfad (a/b.md#Ziel) oder Wiki-Name (Plan#Ziel)."""
        name, _, heading = target.partition("#")
        name = name.strip()
        if not name:
            return
        candidate = self.root / name
        if candidate.is_file() and fileops.is_within(candidate, self.root):
            rel = self.tabs.relative(candidate)
        else:
            rel = self.links.resolve(name)
        if rel is None:
            from notex.ui.spell_highlighter import LinkSpan
            self._on_link_activated(editor, LinkSpan(0, 0, name, heading or None, None))
            return
        opened = self.tabs.open_file(self.root / rel)
        if opened is not None and heading:
            line = find_heading_line(opened.toPlainText(), heading)
            if line:
                opened.goto_line(line)

    # ---- Wiki-Links und Backlinks ------------------------------------------------------
    def _on_file_index_updated(self) -> None:
        self.links.set_files(self.file_index.index.files)
        if not self.links.index.outgoing:
            self.links.rebuild(self.file_index.index.files)   # erster Aufbau im Hintergrund
        else:
            self._relink_timer.start()

    def _after_index_update(self) -> None:
        self.tabs.relink_all()
        self._refresh_backlinks()

    def _on_saved_for_links(self, path: Path) -> None:
        if not self.tabs.is_external(path):
            editor = self.tabs.editor_for(path)
            if editor is not None:
                self.links.update_text(self.tabs.relative(path), editor.toPlainText())

    def set_backlinks_visible(self, visible: bool) -> None:
        self.backlinks.setVisible(visible)
        self.backlinks_action.setChecked(visible)
        self.config["backlinks_visible"] = visible
        if visible:
            self._refresh_backlinks()

    def apply_backlinks_position(self) -> None:
        horizontal = self.config.get("backlinks_position") == "right"
        self.editor_splitter.setOrientation(Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical)
        total = self.editor_splitter.width() if horizontal else self.editor_splitter.height()
        self.editor_splitter.setSizes([int(total * 0.7), int(total * 0.3)])

    def _refresh_backlinks(self) -> None:
        if not self.backlinks.isVisible():
            return
        editor = self.tabs.current_editor()
        if editor is None or self.tabs.is_external(editor.path):
            self.backlinks.set_data([], [], "")
            return
        rel = self.tabs.relative(editor.path)
        backlinks = self.links.index.backlinks(rel)
        self.backlinks.set_data(backlinks, self._scan_mentions(rel), link_name(rel))

    def _scan_mentions(self, rel: str, limit_files: int = 400) -> list:
        """Unverlinkte Erwähnungen des Dateinamens in anderen Dateien (kleine Ordner synchron, gedeckelt)."""
        name = link_name(rel)
        result = []
        for other in self.file_index.index.files[:limit_files]:
            if other == rel or fileops.is_encrypted_path(other):
                continue
            editor = self.tabs.editor_for(self.root / other)
            try:
                text = editor.toPlainText() if editor is not None else _read_text_file(self.root / other).text
            except (OSError, UnicodeDecodeError):
                continue
            if name.lower() not in text.lower():
                continue
            lines = text.split("\n")
            for line, start, end in unlinked_mentions(text, name):
                result.append((other, line, start, end, lines[line - 1].strip()[:100]))
        return result

    def _link_mention(self, rel: Path, line: int, start: int, end: int) -> None:
        """Erwähnung in einer Datei in einen [[Link]] verwandeln (im offenen Tab oder direkt in der Datei)."""
        path = self.root / rel
        editor = self.tabs.editor_for(path)
        current = self.tabs.current_editor()
        target_name = link_name(self.tabs.relative(current.path)) if current else ""
        if editor is not None:
            block = editor.document().findBlockByNumber(line - 1)
            cursor = QTextCursor(editor.document())
            cursor.setPosition(block.position() + start)
            cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
            word = cursor.selectedText()
            editor._grouped(lambda: cursor.insertText(f"[[{target_name}|{word}]]" if word != target_name else f"[[{word}]]"))
        else:
            try:
                tf = _read_text_file(path)
                lines = tf.text.split("\n")
                word = lines[line - 1][start:end]
                lines[line - 1] = lines[line - 1][:start] + (f"[[{target_name}|{word}]]" if word != target_name else f"[[{word}]]") + lines[line - 1][end:]
                self._write_tracked(path, tf, "\n".join(lines), "vor Verlinken")
                self.links.update_text(str(rel).replace("\\", "/"), "\n".join(lines))
            except (OSError, IndexError) as error:
                dialogs.warn(self, "Verlinken", str(error))
                return
        self._refresh_backlinks()

    def _on_link_activated(self, editor, span) -> None:
        if span.resolved:
            target = self.tabs.open_file(self.root / span.resolved)
            if target is not None and span.heading:
                line = find_heading_line(target.toPlainText(), span.heading)
                if line:
                    target.goto_line(line)
            return
        # Kaputter Link: Datei anlegen, Ordner wählbar (Standard: Ordner der aktuellen Datei)
        default_folder = editor.path.parent if not self.tabs.is_external(editor.path) else self.root
        if not dialogs.confirm(self, "Link-Ziel anlegen", f"„{span.target}“ existiert noch nicht.",
                               yes="Datei anlegen", informative=f"Neue Datei {span.target}.md im Ordner {self.tabs.relative(default_folder) or 'data'}?"):
            return
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Ordner für die neue Datei", str(default_folder)) if False else str(default_folder)
        name = span.target.replace("\\", "/").rsplit("/", 1)[-1]
        new_path = Path(folder) / f"{name}.md"
        if "/" in span.target:
            new_path = self.root / f"{span.target}.md"
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            if not new_path.exists():
                new_path.write_text(f"# {name}\n\n", encoding="utf-8")
        except OSError as error:
            dialogs.warn(self, "Datei anlegen", str(error))
            return
        self.file_index.request_rescan()
        self.tabs.open_file(new_path)

    def _on_completion_requested(self, editor, kind: str, text: str) -> None:
        popup = self._completions.get(id(editor))
        if popup is None:
            popup = CompletionPopup(editor)
            popup.chosen.connect(lambda value, e=editor: e.complete_with(value))
            self._completions[id(editor)] = popup
        if kind == "variable":
            from notex.core.variables import completions
            service = self.variable_service
            if service is None:
                popup.hide()
                return
            entries = [(name, f"{service.prefix}{name}  –  {short}") for name, short in completions(text, service.variables)]
            popup.show_items(entries, "variable")
            return
        if kind == "file":
            hits = self.file_index.index.search(text, self.config.get("recent_files", []), limit=40)
            entries = [(link_name(h.relative) if self.links.resolve(link_name(h.relative)) == h.relative else h.relative.rsplit(".", 1)[0],
                        h.relative) for h in hits if not h.external]
            popup.show_items(entries, "file-text")
        else:
            target, _, prefix = text.partition("\x00")
            rel = self.links.resolve(target)
            if rel is None:
                popup.hide()
                return
            open_editor = self.tabs.editor_for(self.root / rel)
            try:
                content = open_editor.toPlainText() if open_editor else _read_text_file(self.root / rel).text
            except (OSError, UnicodeDecodeError):
                popup.hide()
                return
            from notex.core.wikilinks import headings
            from notex.core.fuzzy import match as fuzzy_match
            entries = [(title, title) for _line, title in headings(content) if fuzzy_match(prefix, title) is not None]
            popup.show_items(entries, "heading")

    def _update_links_after_rename(self, old: Path, new: Path) -> None:
        """Datei oder Ordner umbenannt/verschoben: betroffene Links in anderen Dateien anpassen (mit Nachfrage)."""
        if self.tabs.is_external(new) or self.tabs.is_external(old):
            return
        old_rel, new_rel = self.tabs.relative(old), self.tabs.relative(new)
        moved: list[tuple[str, str]] = []
        if new.is_dir():
            for rel in self.links.index.files:
                if rel.startswith(old_rel + "/"):
                    moved.append((rel, new_rel + rel[len(old_rel):]))
        else:
            moved.append((old_rel, new_rel))
        plan: dict[str, list[tuple[str, str]]] = {}
        for o, n in moved:
            for source, count in self.links.index.sources_linking_to(o).items():
                mapped = dict(moved).get(source, source)
                plan.setdefault(mapped, []).append((o, n))
        for o, n in moved:
            self.links.rename(o, n)
        self.file_index.request_rescan()
        if not plan:
            return
        total = sum(len(v) for v in plan.values())
        preview = "\n".join(f"• {source}" for source in sorted(plan)[:12]) + ("\n…" if len(plan) > 12 else "")
        if not dialogs.confirm(self, "Links anpassen", f"{total} Link(s) in {len(plan)} Datei(en) auf „{new.name}“ umschreiben?",
                               yes="Anpassen", no="So lassen", informative=preview):
            return
        files = list(self.links.index.files)
        for source, pairs in plan.items():
            path = self.root / source
            editor = self.tabs.editor_for(path)
            try:
                if editor is not None:
                    was_clean = not editor.is_dirty
                    text = editor.toPlainText()
                    for o, n in pairs:
                        text, _ = rewrite_links(text, files + [o], o, n)
                    if text != editor.toPlainText():
                        self.tabs.replace_text_keep_cursor(editor, text)
                        if was_clean:
                            self.tabs.save_editor(editor)   # gespeicherte Tabs bleiben gespeichert
                    self.links.update_text(source, text)
                else:
                    tf = _read_text_file(path)
                    text = tf.text
                    for o, n in pairs:
                        text, _ = rewrite_links(text, files + [o], o, n)
                    if text != tf.text:
                        self._write_tracked(path, tf, text, "vor Link-Anpassung")
                    self.links.update_text(source, text)
            except (OSError, UnicodeDecodeError) as error:
                dialogs.warn(self, "Links anpassen", f"{source}: {error}")
        self.toast.show_message(f"{total} Links in {len(plan)} Dateien angepasst", "link")

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
        for mode, title in (("edit", "Markdown: Bearbeiten"), ("preview", "Markdown: Vorschau"), ("split", "Markdown: Geteilte Ansicht")):
            self.registry.add(f"preview:{mode}", title, lambda m=mode: self.set_preview_mode(m), category="Ansicht",
                              keywords="markdown vorschau preview rendern")
        self.registry.add("view:table", "CSV/TSV: Als Tabelle anzeigen", lambda: self.set_preview_mode("table"),
                          category="Ansicht", shortcut="Ctrl+Shift+V", keywords="csv tsv tabelle spalten excel")
        self.registry.add("view:tree", "JSON/YAML: Als Baum anzeigen", lambda: self.set_preview_mode("tree"),
                          category="Ansicht", shortcut="Ctrl+Shift+V", keywords="json yaml baum tree struktur pfad")
        self.registry.add("data:format", "JSON/YAML: Formatieren", self.structured.format, category="Bearbeiten",
                          shortcut="Shift+Alt+F", keywords="json yaml einrücken pretty print beautify")
        self.registry.add("data:minify", "JSON/YAML: Minimieren", self.structured.minify, category="Bearbeiten",
                          shortcut="Shift+Alt+M", keywords="json yaml kompakt minify eine zeile")
        self.registry.add("data:validate", "JSON/YAML: Prüfen", self.structured.validate, category="Bearbeiten",
                          shortcut="Shift+Alt+V", keywords="json yaml validieren syntax fehler lint")
        self.registry.add("data:path", "JSON/YAML: Pfad kopieren", self.structured.copy_path, category="Bearbeiten",
                          keywords="json yaml jsonpath pfad kopieren baum")
        self.registry.add("file:live", "Live verfolgen (Log) ein/aus", lambda: self.toggle_live(), category="Datei",
                          shortcut="Ctrl+Shift+Alt+F", keywords="tail follow log live mitlesen logdatei")
        self.registry.add("pdf:quote", "PDF: Markierung als Zitat in Notiz einfügen", self.quote_from_pdf, category="PDF",
                          shortcut="Ctrl+Shift+Alt+Q", keywords="pdf zitat quote markierung notiz quelle")
        self.registry.add("pdf:outline", "PDF: Lesezeichen ein/aus", self.toggle_pdf_outline, category="PDF",
                          keywords="pdf lesezeichen inhaltsverzeichnis outline bookmarks")
        self.registry.add("view:text", "Ansicht: Als Text bearbeiten", lambda: self.set_preview_mode("edit"),
                          category="Ansicht", keywords="csv json yaml text roh quelltext")
        self.registry.add("nav:goto", "Gehe zu Zeile", lambda: (self.show_palette("files"), self.palette.field.setText(":")), category="Navigation")
        self._action("Quick Open", "Ctrl+P", lambda: self.show_palette("files"))
        self._action("Command Palette", "Ctrl+Shift+P", lambda: self.show_palette("commands"))

    def register_command(self, id: str, title: str, callback, category: str = "", shortcut: str = "", **kw) -> None:
        """Für neue Features: ein Befehl, der sofort in der Palette auftaucht."""
        self.registry.add(id, title, callback, category=category, shortcut=shortcut, **kw)

    def show_palette(self, mode: str) -> None:
        if mode == "commands":
            self._refresh_template_commands()
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
        self.split_toolbar_action.setChecked(self.tabs.is_split)
        self.split_action.setChecked(self.tabs.is_split)
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
        viewer = self.tabs.current_viewer() if editor is None else None
        if viewer is not None:
            relative = self.tabs.relative(viewer.path)
            self.status.update_for_viewer(relative, viewer.status_parts())
            if getattr(viewer, "warning", ""):
                self.status.set_problem("⚠ " + viewer.warning, "error",
                                        tooltip=f"Dateityp laut Inhalt: {viewer.ftype.name}\n{viewer.warning}")
            self.setWindowTitle(f"{relative} – {APP_NAME}")
            return
        if editor is None:
            self.status.update_for(None, "")
            self.setWindowTitle(APP_NAME)
            return
        relative = self.tabs.relative(editor.path)
        self.status.update_for(editor, relative)
        page = self.tabs.current_page()
        if page is not None and self._in_data_view():
            parts = [part for part in page.data_view.status_parts()[:2] if part]
            self.status.position_label.setText(page.data_view.position_text())
            self.status.chars_label.setText(" · ".join(parts))
        self.structured.refresh_status()
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
        self.apply_backlinks_position()
        self.sidebar.tree.restore_expanded(self.config["expanded_folders"])

        state = split_state.from_config(self.config, exists=lambda entry: self.tabs.resolve_saved(entry).is_file())
        self.tabs.restore_state(state)
        self.empty_state.set_recent(self.config["recent_files"])

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
        self.config.update(self.tabs.state().to_config())

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
        self.links.shutdown()
        self.tabs.shutdown()
        if self._card is not None:
            self._card.shutdown()
        self.save_state()
        event.accept()
