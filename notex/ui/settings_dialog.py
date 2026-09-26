"""Einstellungen (Ctrl+,): links Kategorien, rechts Optionen. Alles wirkt sofort als Vorschau.

Abbrechen stellt den Zustand beim Öffnen wieder her, Übernehmen behält ihn und
speichert die Config. Das Theme wird als Arbeitskopie (dict) gehalten und bei
jeder Änderung über den ThemeManager angewendet.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from notex.core.theme_model import (DENSITIES, PAPER_VARIANTS, PRESETS, SPEEDS, SYNTAX_CLASSES, contrast_warnings,
                                    default_theme, theme_from_preset)
from notex.core.syntax import LEXERS
from notex.core.theme_store import ThemeStore
from notex.theme.fonts import STANDARD, STANDARD_LABEL, available_families, sf_available
from notex.theme.icons import icon
from notex.theme.manager import theme_manager
from notex.theme.tokens import SPACING
from notex.ui import dialogs
from notex.ui.color_field import ColorField

UI_COLOR_LABELS = [
    ("bg", "Hintergrund"), ("sidebar", "Seitenleiste"), ("surface", "Flächen"), ("hover", "Hover"),
    ("selection", "Auswahl"), ("border", "Rahmen"), ("text", "Text"), ("text_muted", "Gedämpfter Text"),
    ("accent", "Akzent"), ("spell_underline", "Rechtschreib-Markierung"), ("grammar_underline", "Grammatik-Markierung"),
]
PAPER_COLOR_LABELS = [
    ("paper", "Blatt"), ("paper_text", "Text"), ("paper_muted", "Zeilennummern"), ("paper_selection", "Auswahl"),
    ("paper_line", "Aktuelle Zeile"), ("paper_match", "Suchtreffer"),
]
DENSITY_LABELS = {"kompakt": "Kompakt", "normal": "Normal", "luftig": "Luftig"}
SPEED_LABELS = {"langsam": "Langsam", "normal": "Normal", "schnell": "Schnell"}


class SettingsPage(QWidget):
    """Eine Kategorie: vertikale Liste aus Abschnitten und Formularzeilen."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SettingsPage")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(SPACING.xl, SPACING.lg, SPACING.xl, SPACING.xl)
        self.layout_.setSpacing(SPACING.sm)
        self.form: QFormLayout | None = None

    def section(self, title: str) -> None:
        if self.layout_.count():
            self.layout_.addSpacing(SPACING.md)
        label = QLabel(title)
        label.setObjectName("SettingsSection")
        self.layout_.addWidget(label)
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(SPACING.lg)
        self.form.setVerticalSpacing(SPACING.sm)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout_.addLayout(self.form)

    def row(self, label: str, widget: QWidget) -> None:
        assert self.form is not None
        self.form.addRow(label, widget)

    def add(self, widget: QWidget) -> None:
        self.layout_.addWidget(widget)

    def note(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("SettingsNote")
        label.setWordWrap(True)
        self.layout_.addWidget(label)

    def finish(self) -> None:
        self.layout_.addStretch(1)


class SettingsDialog(QDialog):
    CATEGORIES = ["Darstellung", "Blatt", "Schrift", "Editor", "Rechtschreibung", "System", "Tastenkürzel"]
    CATEGORY_ICONS = ["palette", "file-text", "type", "text-cursor-input", "spell-check", "sliders-horizontal", "keyboard"]

    def __init__(self, window, store: ThemeStore) -> None:
        super().__init__(window)
        self.window_ = window
        self.config = window.config
        self.store = store
        self.manager = theme_manager()
        self.setWindowTitle("Einstellungen")
        self.setObjectName("SettingsDialog")
        self.resize(920, 660)

        # Arbeitskopie + Schnappschuss für Abbrechen
        self.theme: dict[str, Any] = self.manager.current()
        self._snapshot_theme = copy.deepcopy(self.theme)
        self._snapshot_config = copy.deepcopy(self.config)
        self._loading = False    # verhindert Rückkopplung beim Befüllen der Controls
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(30)
        self._preview_timer.timeout.connect(self._apply_preview)
        self.color_fields: dict[str, ColorField] = {}

        self.categories = QListWidget()
        self.categories.setObjectName("SettingsCategories")
        self.categories.setFixedWidth(180)
        for name, icon_name in zip(self.CATEGORIES, self.CATEGORY_ICONS):
            self.categories.addItem(QListWidgetItem(icon(icon_name), name))
        self.pages = QStackedWidget()
        for builder in (self._build_appearance, self._build_paper, self._build_font, self._build_editor,
                        self._build_spelling, self._build_system, self._build_shortcuts):
            page = builder()
            page.finish()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)   # nie seitlich scrollen
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self.categories.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.categories.setCurrentRow(0)

        reset = QPushButton("Auf Standard zurücksetzen")
        reset.clicked.connect(self._reset_defaults)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        apply = QPushButton("Übernehmen")
        apply.setDefault(True)
        apply.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(SPACING.lg, SPACING.sm, SPACING.lg, SPACING.md)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(apply)
        footer = QFrame()
        footer.setObjectName("SettingsFooter")
        footer.setLayout(buttons)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.categories)
        body.addWidget(self.pages, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(body, 1)
        layout.addWidget(footer)

        self._load_controls()

    def show_category(self, name: str) -> None:
        if name in self.CATEGORIES:
            self.categories.setCurrentRow(self.CATEGORIES.index(name))

    # ---- Seiten -------------------------------------------------------------------
    def _build_appearance(self) -> SettingsPage:
        page = SettingsPage()
        page.section("Preset")
        self.preset_box = QComboBox()
        self.preset_box.addItems(list(PRESETS))
        self.preset_box.setToolTip("Setzt die Oberflächenfarben; Blatt, Schrift und Form bleiben")
        self.preset_box.activated.connect(self._preset_chosen)
        page.row("Oberfläche", self.preset_box)

        page.section("Gespeicherte Themes")
        self.theme_list = QListWidget()
        self.theme_list.setFixedHeight(110)
        self.theme_list.itemDoubleClicked.connect(lambda _i: self._load_saved())
        page.add(self.theme_list)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(SPACING.xs)
        for text, slot in (("Laden", self._load_saved), ("Speichern als …", self._save_as),
                           ("Duplizieren", self._duplicate), ("Umbenennen", self._rename),
                           ("Löschen", self._delete), ("Import …", self._import), ("Export …", self._export)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        wrapper = QWidget()
        wrapper.setLayout(actions)
        page.add(wrapper)
        page.note("Themes liegen als JSON in themes/ neben der App und wandern mit dem Ordner mit.")

        page.section("Farben")
        for key, label in UI_COLOR_LABELS:
            page.add(self._color_field(key, label))

        page.section("Form")
        self.radius_slider = QSlider(Qt.Orientation.Horizontal)
        self.radius_slider.setRange(0, 12)
        self.radius_value = QLabel()
        self.radius_value.setFixedWidth(40)
        radius_row = QHBoxLayout()
        radius_row.setContentsMargins(0, 0, 0, 0)
        radius_row.addWidget(self.radius_slider, 1)
        radius_row.addWidget(self.radius_value)
        radius_widget = QWidget()
        radius_widget.setLayout(radius_row)
        self.radius_slider.valueChanged.connect(self._radius_changed)
        page.row("Eckenradius", radius_widget)
        self.density_box = QComboBox()
        for key in DENSITIES:
            self.density_box.addItem(DENSITY_LABELS[key], key)
        self.density_box.currentIndexChanged.connect(lambda i: self._set(("shape", "density"), self.density_box.itemData(i)))
        page.row("Dichte", self.density_box)

        page.section("Animationen")
        self.anim_box = QCheckBox("Animationen aktiv")
        self.anim_box.toggled.connect(lambda on: self._set(("animation", "enabled"), on))
        page.row("", self.anim_box)
        self.speed_box = QComboBox()
        for key in SPEEDS:
            self.speed_box.addItem(SPEED_LABELS[key], key)
        self.speed_box.currentIndexChanged.connect(lambda i: self._set(("animation", "speed"), self.speed_box.itemData(i)))
        page.row("Geschwindigkeit", self.speed_box)
        return page

    def _build_paper(self) -> SettingsPage:
        page = SettingsPage()
        page.section("Variante")
        self.paper_box = QComboBox()
        self.paper_box.addItems(list(PAPER_VARIANTS))
        self.paper_box.setToolTip("Setzt die Blattfarben")
        self.paper_box.activated.connect(self._paper_variant_chosen)
        page.row("Blatt", self.paper_box)

        page.section("Farben")
        for key, label in PAPER_COLOR_LABELS:
            page.add(self._color_field(key, label))

        page.section("Schatten und Abstände")
        self.shadow_box = QCheckBox("Schatten unter dem Blatt")
        self.shadow_box.toggled.connect(lambda on: self._set(("paper", "shadow"), on))
        page.row("", self.shadow_box)
        self.shadow_slider = QSlider(Qt.Orientation.Horizontal)
        self.shadow_slider.setRange(0, 100)
        self.shadow_slider.valueChanged.connect(lambda v: self._set(("paper", "shadow_strength"), v))
        page.row("Schattenstärke", self.shadow_slider)
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(8, 120)
        self.padding_spin.setSuffix(" px")
        self.padding_spin.valueChanged.connect(lambda v: self._set(("paper", "padding"), v))
        page.row("Innenabstand", self.padding_spin)

        page.section("Syntax-Farben")
        self.syntax_scheme_box = QComboBox()
        self.syntax_scheme_box.addItem("Helles Blatt (Weiß, Papier, Sepia)", "light")
        self.syntax_scheme_box.addItem("Dunkles Blatt", "dark")
        self.syntax_scheme_box.currentIndexChanged.connect(lambda _i: self._load_syntax_fields())
        page.row("Schema", self.syntax_scheme_box)
        self.syntax_fields: dict[str, ColorField] = {}
        labels = {"keyword": "Schlüsselwörter", "string": "Strings", "comment": "Kommentare", "number": "Zahlen",
                  "function": "Funktionen/Klassen", "operator": "Operatoren", "tag": "Tags", "attribute": "Attribute",
                  "log_error": "Log: Fehler", "log_warn": "Log: Warnung", "log_info": "Log: Info", "log_debug": "Log: Debug",
                  "log_time": "Log: Zeitstempel", "log_ip": "Log: IP-Adresse", "log_path": "Log: Pfad"}
        for key in SYNTAX_CLASSES:
            field = ColorField(key, labels.get(key, key))
            field.changed.connect(self._syntax_color_changed)
            self.syntax_fields[key] = field
            page.add(field)

        page.section("Breite")
        self.paper_mode_box = QCheckBox("Blatt zentrieren (Blatt-Modus)")
        self.paper_mode_box.setToolTip("Aus = volle Breite  Alt+P")
        self.paper_mode_box.toggled.connect(self._paper_mode_toggled)
        page.row("", self.paper_mode_box)
        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(40, 200)
        self.columns_spin.setSuffix(" Zeichen")
        self.columns_spin.valueChanged.connect(lambda v: self._set(("paper", "max_columns"), v))
        page.row("Maximale Textbreite", self.columns_spin)
        return page

    def _build_font(self) -> SettingsPage:
        page = SettingsPage()
        page.section("Oberfläche")
        self.ui_size_spin = QSpinBox()
        self.ui_size_spin.setRange(9, 20)
        self.ui_size_spin.setSuffix(" px")
        self.ui_size_spin.valueChanged.connect(lambda v: self._set(("font", "ui_size"), v))
        page.row("Größe", self.ui_size_spin)
        sf_note = "SF Pro aus fonts/user/ ist aktiv." if sf_available() else \
            "Aktiv ist Inter. Lege SF Pro (oder andere Schriften) nach fonts/user/ neben der App, sie werden beim Start geladen."
        page.note(f"Die Schrift der Oberfläche ist fest: SF Pro → Inter → Segoe UI. {sf_note}")

        page.section("Textinhalt")
        self.editor_font_box = QComboBox()
        self.editor_font_box.setToolTip("Ansichts-Einstellung für alle Dateien – ändert nichts an der Datei")
        self._fill_font_box(self.editor_font_box)
        self.editor_font_box.currentIndexChanged.connect(
            lambda i: self._set(("font", "editor_family"), self.editor_font_box.itemData(i) or STANDARD))
        page.row("Schrift", self.editor_font_box)
        self.editor_size_spin = QSpinBox()
        self.editor_size_spin.setRange(8, 40)
        self.editor_size_spin.setSuffix(" px")
        self.editor_size_spin.valueChanged.connect(lambda v: self._set(("font", "editor_size"), v))
        page.row("Größe", self.editor_size_spin)
        self.line_height_spin = QDoubleSpinBox()
        self.line_height_spin.setRange(1.0, 2.2)
        self.line_height_spin.setSingleStep(0.1)
        self.line_height_spin.setDecimals(1)
        self.line_height_spin.valueChanged.connect(lambda v: self._set(("font", "line_height"), round(v, 2)))
        page.row("Zeilenhöhe", self.line_height_spin)

        page.section("Schrift je Dateiendung")
        self.ext_font_boxes: dict[str, QComboBox] = {}
        for ext in self.config["extensions"]:
            box = QComboBox()
            self._fill_font_box(box, standard_label="Wie Textinhalt")
            box.currentIndexChanged.connect(lambda i, e=ext, b=box: self._ext_font_changed(e, b.itemData(i) or ""))
            self.ext_font_boxes[ext] = box
            page.row(ext, box)
        page.note("Textdateien haben keine Formatierung. Schrift und Größe sind Ansichts-Einstellungen "
                  "und ändern nichts am Inhalt. Gebündelt: Inter und JetBrains Mono; alles aus fonts/user/ "
                  "und alle installierten Schriften stehen ebenfalls zur Wahl.")
        return page

    def _fill_font_box(self, box: QComboBox, standard_label: str = STANDARD_LABEL) -> None:
        box.addItem(standard_label, STANDARD)
        for family in available_families():
            box.addItem(family, family)

    @staticmethod
    def _select_font(box: QComboBox, family: str) -> None:
        index = box.findData(family or STANDARD)
        box.setCurrentIndex(index if index >= 0 else 0)

    def _syntax_ext_toggled(self, ext: str, on: bool) -> None:
        if self._loading:
            return
        exts = set(self.config.get("syntax_extensions", []))
        exts.add(ext) if on else exts.discard(ext)
        self.config["syntax_extensions"] = [e for e in LEXERS if e in exts]
        self.window_.tabs.relink_all()

    def _ext_font_changed(self, ext: str, family: str) -> None:
        if self._loading:
            return
        mapping = dict(self.config.get("font_by_extension", {}))
        if family:
            mapping[ext] = family
        else:
            mapping.pop(ext, None)
        self.config["font_by_extension"] = mapping
        self.window_.tabs.apply_text_fonts()

    def _build_editor(self) -> SettingsPage:
        page = SettingsPage()
        page.section("Text")
        page.note("Zeilen werden immer an der Blattbreite umgebrochen, auch lange URLs oder Hashes. "
                  "Horizontal scrollen gibt es nicht – der Text ist immer vollständig sichtbar.")
        page.section("Syntax-Highlighting")
        self.syntax_box = QCheckBox("Code und Logs farbig hervorheben (Pygments)")
        self.syntax_box.toggled.connect(lambda on: (self.config.__setitem__("syntax_highlighting", on),
                                                    self.window_.tabs.relink_all()) if not self._loading else None)
        page.row("", self.syntax_box)
        syntax_row = QHBoxLayout()
        syntax_row.setContentsMargins(0, 0, 0, 0)
        self.syntax_chips = {}
        from notex.ui.widgets import Chip
        for ext in LEXERS:
            chip = Chip(ext, f"Syntax-Highlighting für {ext}")
            chip.toggled.connect(lambda on, e=ext: self._syntax_ext_toggled(e, on))
            self.syntax_chips[ext] = chip
            syntax_row.addWidget(chip)
        syntax_row.addStretch(1)
        syntax_widget = QWidget()
        syntax_widget.setLayout(syntax_row)
        page.row("Endungen", syntax_widget)
        page.note("Nur sichtbare Blöcke werden gefärbt; Dateien über 2 MB bleiben ohne Highlighting. "
                  "In .md-Dateien werden ```python-Blöcke usw. mit dem passenden Lexer gefärbt.")

        page.section("Markdown-Vorschau")
        self.markdown_view_box = QComboBox()
        self.markdown_view_box.addItem("Bearbeiten", "edit")
        self.markdown_view_box.addItem("Vorschau", "preview")
        self.markdown_view_box.addItem("Geteilt (Blatt + Vorschau)", "split")
        self.markdown_view_box.currentIndexChanged.connect(
            lambda i: self.config.__setitem__("markdown_view", self.markdown_view_box.itemData(i)) if not self._loading else None)
        page.row(".md öffnen als", self.markdown_view_box)
        self.sync_scroll_box = QCheckBox("Vorschau scrollt mit dem Editor (geteilte Ansicht)")
        self.sync_scroll_box.toggled.connect(lambda on: (self.config.__setitem__("preview_sync_scroll", on),
                                                         self.window_.tabs.apply_preview_settings()) if not self._loading else None)
        page.row("", self.sync_scroll_box)
        page.note("Ctrl+Shift+V wechselt Bearbeiten → Vorschau → Geteilt. Die Vorschau lädt nie von selbst aus dem "
                  "Internet: externe Bilder erscheinen als „Bild laden“, externe Links öffnen den Browser erst auf Klick.")

        page.section("Versionshistorie")
        self.history_box = QCheckBox("Bei jedem Speichern einen Schnappschuss in history/ ablegen")
        self.history_box.toggled.connect(lambda on: self.config.setdefault("history", {}).__setitem__("enabled", on)
                                         if not self._loading else None)
        page.row("", self.history_box)
        self.history_spin = QSpinBox()
        self.history_spin.setRange(10, 5000)
        self.history_spin.setSingleStep(50)
        self.history_spin.setSuffix(" MB")
        self.history_spin.valueChanged.connect(lambda v: self.config.setdefault("history", {}).__setitem__("max_mb", v)
                                               if not self._loading else None)
        page.row("Höchstens", self.history_spin)
        history_row = QHBoxLayout()
        history_row.setContentsMargins(0, 0, 0, 0)
        self.history_size = QLabel()
        self.history_size.setObjectName("SettingsNote")
        clear_history = QPushButton("Verlauf leeren …")
        clear_history.clicked.connect(self._clear_history)
        history_row.addWidget(self.history_size, 1)
        history_row.addWidget(clear_history)
        history_widget = QWidget()
        history_widget.setLayout(history_row)
        page.add(history_widget)
        page.note("Ctrl+Shift+Y zeigt die Versionen der aktuellen Datei mit Unterschieden. Ältere Versionen werden "
                  "ausgedünnt (24 h alles, dann stündlich, täglich, wöchentlich). Verschlüsselte Notizen (.ntx) "
                  "bekommen nie einen Verlauf.")

        page.section("Vorlagen")
        self.week_folder_edit = QLineEdit()
        self.week_folder_edit.setToolTip("Ordner in data/, in dem „Neue Woche“ (Alt+W) die Wochenpläne anlegt")
        self.week_folder_edit.editingFinished.connect(
            lambda: self.config.setdefault("templates", {}).__setitem__("week_folder", self.week_folder_edit.text().strip() or "Wochen"))
        page.row("Wochen-Ordner", self.week_folder_edit)
        self.week_name_edit = QLineEdit()
        self.week_name_edit.setToolTip("Dateiname ohne .md, Platzhalter wie in Vorlagen: {{week}} {{year}} {{date:%Y-%m-%d}}")
        self.week_name_edit.editingFinished.connect(
            lambda: self.config.setdefault("templates", {}).__setitem__("week_name", self.week_name_edit.text().strip() or "KW{{week}} {{year}}"))
        page.row("Wochen-Dateiname", self.week_name_edit)
        templates_button = QPushButton("Vorlagen-Ordner öffnen")
        templates_button.clicked.connect(lambda: getattr(self.window_, "open_templates_folder", lambda: None)())
        page.row("", templates_button)
        page.note("Vorlagen sind .md/.txt-Dateien in templates/ neben der App. Platzhalter: {{date}} {{time}} {{weekday}} "
                  "{{week}} {{year}} {{title}} {{cursor}}, Versätze wie {{date+1}} und Formate wie {{date:%Y-%m-%d}}. "
                  "Ctrl+Shift+T: neue Datei aus Vorlage, Alt+W: Neue Woche.")

        page.section("Verschlüsselte Notizen")
        self.autolock_spin = QSpinBox()
        self.autolock_spin.setRange(0, 240)
        self.autolock_spin.setSuffix(" min")
        self.autolock_spin.setSpecialValueText("nie")
        self.autolock_spin.valueChanged.connect(
            lambda v: self.config.setdefault("encryption", {}).__setitem__("auto_lock_minutes", v) if not self._loading else None)
        page.row("Automatisch sperren nach", self.autolock_spin)
        page.note(".ntx-Dateien sind mit AES-256-GCM verschlüsselt, der Schlüssel entsteht per Argon2id aus dem "
                  "Passwort. Klartext liegt nie auf der Platte: kein Verlauf, keine Suche, keine Grammatikprüfung, "
                  "kein Wörterbuch-Eintrag. Ctrl+Shift+L sperrt sofort. Details: docs/ENCRYPTION.md")

        page.section("Geteilter Editor")
        self.split_box = QComboBox()
        self.split_box.addItem("Nebeneinander", "horizontal")
        self.split_box.addItem("Untereinander", "vertical")
        self.split_box.currentIndexChanged.connect(
            lambda i: self.window_.tabs.set_orientation(self.split_box.itemData(i)) if not self._loading else None)
        page.row("Gruppen anordnen", self.split_box)
        page.note("Ctrl+\\ teilt den Editor in zwei Tab-Gruppen; Tabs lassen sich per Drag zwischen den Gruppen "
                  "ziehen, dieselbe Datei kann in beiden offen sein (ein Dokument, zwei Ansichten).")

        page.section("Wiki-Links")
        self.wiki_box = QCheckBox("[[Links]] hervorheben und auflösen (Ctrl+Klick öffnet)")
        self.wiki_box.toggled.connect(lambda on: (self.config.__setitem__("wiki_links", on), self.window_.tabs.relink_all()) if not self._loading else None)
        page.row("", self.wiki_box)
        self.backlinks_box = QComboBox()
        self.backlinks_box.addItem("Unter dem Blatt", "bottom")
        self.backlinks_box.addItem("Rechts neben dem Blatt", "right")
        self.backlinks_box.currentIndexChanged.connect(
            lambda i: (self.config.__setitem__("backlinks_position", self.backlinks_box.itemData(i)),
                       self.window_.apply_backlinks_position()) if not self._loading else None)
        page.row("Backlinks-Panel", self.backlinks_box)
        page.section("Baum")
        self.extensions_edit = QLineEdit()
        self.extensions_edit.setToolTip("Dateiendungen, die im Baum erscheinen, mit Leerzeichen getrennt")
        self.extensions_edit.editingFinished.connect(self._extensions_changed)
        page.row("Dateiendungen", self.extensions_edit)
        return page

    def _build_spelling(self) -> SettingsPage:
        page = SettingsPage()
        self.spelling_page = page
        if hasattr(self.window_, "build_spelling_settings"):
            self.window_.build_spelling_settings(page)
        else:
            page.section("Rechtschreibung")
            page.note("Noch nicht verfügbar.")
        return page

    def _build_system(self) -> SettingsPage:
        page = SettingsPage()
        if hasattr(self.window_, "build_system_settings"):
            self.window_.build_system_settings(page)
        return page

    def _build_shortcuts(self) -> SettingsPage:
        page = SettingsPage()
        page.section("Tastenkürzel")
        for text, shortcut in self.window_.shortcut_list():
            label = QLabel(shortcut)
            label.setObjectName("EmptyKey")
            page.row(text, label)
        return page

    # ---- Controls befüllen ----------------------------------------------------------
    def _color_field(self, key: str, label: str) -> ColorField:
        field = ColorField(key, label)
        field.changed.connect(self._color_changed)
        self.color_fields[key] = field
        return field

    def _load_controls(self) -> None:
        """Alle Controls aus self.theme + config befüllen, ohne Vorschau auszulösen."""
        self._loading = True
        theme, cfg = self.theme, self.config
        for key, field in self.color_fields.items():
            field.set_color(theme["colors"][key])
        self._update_contrast()
        self.preset_box.setCurrentText(theme["name"] if theme["name"] in PRESETS else "Matt")
        self.radius_slider.setValue(theme["shape"]["radius"])
        self.radius_value.setText(f"{theme['shape']['radius']} px")
        self.density_box.setCurrentIndex(DENSITIES.index(theme["shape"]["density"]))
        self.anim_box.setChecked(theme["animation"]["enabled"])
        self.speed_box.setCurrentIndex(SPEEDS.index(theme["animation"]["speed"]))
        self.shadow_box.setChecked(theme["paper"]["shadow"])
        self.shadow_slider.setValue(theme["paper"]["shadow_strength"])
        self.padding_spin.setValue(theme["paper"]["padding"])
        self.paper_mode_box.setChecked(cfg["paper_mode"])
        self.columns_spin.setValue(theme["paper"]["max_columns"])
        self.ui_size_spin.setValue(theme["font"]["ui_size"])
        self._select_font(self.editor_font_box, theme["font"]["editor_family"])
        for ext, box in self.ext_font_boxes.items():
            self._select_font(box, cfg.get("font_by_extension", {}).get(ext, ""))
        self.editor_size_spin.setValue(theme["font"]["editor_size"])
        self.line_height_spin.setValue(theme["font"]["line_height"])
        self.extensions_edit.setText(" ".join(cfg["extensions"]))
        self.wiki_box.setChecked(bool(cfg.get("wiki_links", True)))
        self.markdown_view_box.setCurrentIndex(max(0, self.markdown_view_box.findData(cfg.get("markdown_view", "edit"))))
        tpl = cfg.get("templates", {})
        self.week_folder_edit.setText(str(tpl.get("week_folder", "Wochen")))
        self.week_name_edit.setText(str(tpl.get("week_name", "KW{{week}} {{year}}")))
        self.autolock_spin.setValue(int(cfg.get("encryption", {}).get("auto_lock_minutes", 5)))
        hist = cfg.get("history", {})
        self.history_box.setChecked(bool(hist.get("enabled", True)))
        self.history_spin.setValue(int(hist.get("max_mb", 200)))
        self._update_history_size()
        self.split_box.setCurrentIndex(max(0, self.split_box.findData(cfg.get("split", {}).get("orientation", "horizontal"))))
        self.sync_scroll_box.setChecked(bool(cfg.get("preview_sync_scroll", True)))
        self.syntax_box.setChecked(bool(cfg.get("syntax_highlighting", True)))
        for ext, chip in self.syntax_chips.items():
            chip.setChecked(ext in cfg.get("syntax_extensions", []))
        from notex.core.theme_model import relative_luminance
        self.syntax_scheme_box.setCurrentIndex(1 if relative_luminance(theme["colors"]["paper"]) < 0.4 else 0)
        self._load_syntax_fields()
        self.backlinks_box.setCurrentIndex(max(0, self.backlinks_box.findData(cfg.get("backlinks_position", "bottom"))))
        self._refresh_theme_list()
        self._loading = False

    def _update_history_size(self) -> None:
        history = getattr(self.window_, "history", None)
        if history is None:
            self.history_size.setText("")
            return
        size = history.object_bytes()
        self.history_size.setText(f"Belegt: {size / 1024 / 1024:.1f} MB in {len(history.tracked_paths())} Dateien")

    def _clear_history(self) -> None:
        from notex.ui import dialogs
        history = getattr(self.window_, "history", None)
        if history is not None and dialogs.confirm(self, "Verlauf leeren", "Alle gespeicherten Versionen löschen?",
                                                   yes="Löschen", danger=True,
                                                   informative="Die Dateien selbst bleiben unverändert."):
            history.clear()
            self._update_history_size()

    def _refresh_theme_list(self) -> None:
        self.theme_list.clear()
        for name in self.store.names():
            self.theme_list.addItem(QListWidgetItem(icon("palette"), name))

    def _update_contrast(self) -> None:
        warnings = contrast_warnings(self.theme["colors"])
        for key, field in self.color_fields.items():
            field.set_warning(warnings.get(key))

    # ---- Änderungen -> Vorschau ------------------------------------------------------
    def _set(self, path: tuple[str, str], value: Any) -> None:
        if self._loading:
            return
        section, key = path
        self.theme[section][key] = value
        self._schedule_preview()

    def _load_syntax_fields(self) -> None:
        scheme = self.syntax_scheme_box.currentData() or "light"
        loading = self._loading
        self._loading = True
        for key, field in self.syntax_fields.items():
            field.set_color(self.theme["syntax"][scheme][key])
        self._loading = loading

    def _syntax_color_changed(self, key: str, value: str) -> None:
        if self._loading:
            return
        scheme = self.syntax_scheme_box.currentData() or "light"
        self.theme["syntax"][scheme][key] = value
        self._schedule_preview()

    def _radius_changed(self, value: int) -> None:
        self.radius_value.setText(f"{value} px")
        self._set(("shape", "radius"), value)

    def _color_changed(self, key: str, value: str) -> None:
        if self._loading:
            return
        self.theme["colors"][key] = value
        self._update_contrast()
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _apply_preview(self) -> None:
        self.theme = self.manager.apply(self.theme)
        self.window_.tabs.set_font_size(self.theme["font"]["editor_size"])
        self.window_.tabs.relink_all()   # Syntax-Farben neu anlegen

    def _preset_chosen(self, index: int) -> None:
        preset = theme_from_preset(self.preset_box.itemText(index))
        for key in preset["colors"]:
            if not key.startswith("paper"):
                self.theme["colors"][key] = preset["colors"][key]
        self.theme["name"] = preset["name"]
        self._load_controls()
        self._schedule_preview()

    def _paper_variant_chosen(self, index: int) -> None:
        self.theme["colors"].update(PAPER_VARIANTS[self.paper_box.itemText(index)])
        self._load_controls()
        self._schedule_preview()

    def _paper_mode_toggled(self, on: bool) -> None:
        if not self._loading and on != self.window_.tabs.paper_mode:
            self.window_.toggle_paper_mode()

    def _extensions_changed(self) -> None:
        if self._loading:
            return
        parts = [p if p.startswith(".") else "." + p for p in self.extensions_edit.text().split() if p.strip(".")]
        if parts:
            self.config["extensions"] = sorted(set(p.lower() for p in parts))
            self.window_.sidebar.tree.set_extensions(self.config["extensions"])
        self.extensions_edit.setText(" ".join(self.config["extensions"]))

    def _reset_defaults(self) -> None:
        self.theme = default_theme()
        self._load_controls()
        self._schedule_preview()

    # ---- Gespeicherte Themes ---------------------------------------------------------
    def _selected_name(self) -> str | None:
        item = self.theme_list.currentItem()
        return item.text() if item else None

    def _load_saved(self) -> None:
        name = self._selected_name()
        if name:
            self.theme = self.store.load(name)
            self._load_controls()
            self._schedule_preview()
            self._toast(f"Theme „{name}“ geladen", "palette")

    def _save_as(self) -> None:
        name = dialogs.ask_text(self, "Theme speichern", "Name:", self.theme["name"])
        if not name:
            return
        if self.store.exists(name) and not dialogs.confirm(self, "Theme speichern", f"„{name}“ existiert bereits. Überschreiben?",
                                                          yes="Überschreiben", danger=True):
            return
        self.theme["name"] = name
        self.store.save(self.theme)
        self._refresh_theme_list()
        self._toast(f"Theme „{name}“ gespeichert", "check")

    def _duplicate(self) -> None:
        name = self._selected_name()
        if name:
            copy_ = self.store.duplicate(name)
            self._refresh_theme_list()
            self._toast(f"Kopie „{copy_['name']}“ angelegt", "copy")

    def _rename(self) -> None:
        name = self._selected_name()
        if not name:
            return
        new = dialogs.ask_text(self, "Theme umbenennen", "Neuer Name:", name)
        if new and new != name:
            self.store.rename(name, new)
            self._refresh_theme_list()

    def _delete(self) -> None:
        name = self._selected_name()
        if name and dialogs.confirm(self, "Theme löschen", f"Theme „{name}“ löschen?", yes="Löschen", danger=True):
            self.store.delete(name)
            self._refresh_theme_list()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Theme importieren", "", "Theme (*.json)")
        if not path:
            return
        if not self.store.is_valid_file(Path(path)):
            self._toast("Datei ist kein gültiges Theme", "triangle-alert")
            return
        theme = self.store.import_file(Path(path))
        self._refresh_theme_list()
        self._toast(f"Theme „{theme['name']}“ importiert", "download")

    def _export(self) -> None:
        name = self._selected_name()
        theme = self.store.load(name) if name else self.theme
        path, _ = QFileDialog.getSaveFileName(self, "Theme exportieren", f"{theme['name']}.json", "Theme (*.json)")
        if path:
            try:
                self.store.export_file(theme, Path(path))
                self._toast(f"Theme nach {Path(path).name} exportiert", "upload")
            except OSError as error:
                self._toast(f"Export fehlgeschlagen: {error}", "triangle-alert")

    def _toast(self, text: str, icon_name: str) -> None:
        self.window_.toast.show_message(text, icon_name)

    # ---- Abschluss -----------------------------------------------------------------
    def accept(self) -> None:
        self._preview_timer.stop()
        self.theme = self.manager.apply(self.theme)
        self.config["theme"] = copy.deepcopy(self.theme)
        self.window_.save_state()
        super().accept()

    def reject(self) -> None:
        """Abbrechen: Theme und Config-Werte von vor dem Öffnen wiederherstellen."""
        self._preview_timer.stop()
        self.manager.apply(self._snapshot_theme)
        for key in ("paper_mode", "extensions", "font_by_extension"):
            self.config[key] = self._snapshot_config[key]
        self.window_.tabs.apply_text_fonts()
        self.window_.tabs.set_paper_mode(self.config["paper_mode"])
        self.window_.paper_action.setChecked(self.config["paper_mode"])
        self.window_.sidebar.tree.set_extensions(self.config["extensions"])
        self.window_.tabs.set_font_size(self._snapshot_config["font_size"])
        super().reject()
