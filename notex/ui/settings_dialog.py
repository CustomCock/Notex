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

from notex.core.theme_model import (DENSITIES, PAPER_VARIANTS, PRESETS, SPEEDS, contrast_warnings, default_theme,
                                    theme_from_preset)
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
    CATEGORIES = ["Darstellung", "Blatt", "Schrift", "Editor", "Rechtschreibung", "Tastenkürzel"]
    CATEGORY_ICONS = ["palette", "file-text", "type", "text-cursor-input", "spell-check", "keyboard"]

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
                        self._build_spelling, self._build_shortcuts):
            page = builder()
            page.finish()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
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
        self.wrap_box = QCheckBox("Zeilenumbruch  (Alt+Z)")
        self.wrap_box.toggled.connect(self._wrap_toggled)
        page.row("", self.wrap_box)
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
        self.wrap_box.setChecked(cfg["word_wrap"])
        self.extensions_edit.setText(" ".join(cfg["extensions"]))
        self._refresh_theme_list()
        self._loading = False

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

    def _wrap_toggled(self, on: bool) -> None:
        if not self._loading and on != self.window_.tabs.word_wrap:
            self.window_.toggle_word_wrap()

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
        for key in ("paper_mode", "word_wrap", "extensions", "font_by_extension"):
            self.config[key] = self._snapshot_config[key]
        self.window_.tabs.apply_text_fonts()
        self.window_.tabs.set_paper_mode(self.config["paper_mode"])
        self.window_.paper_action.setChecked(self.config["paper_mode"])
        self.window_.tabs.set_word_wrap(self.config["word_wrap"])
        self.window_.wrap_action.setChecked(self.config["word_wrap"])
        self.window_.sidebar.tree.set_extensions(self.config["extensions"])
        self.window_.tabs.set_font_size(self._snapshot_config["font_size"])
        super().reject()
