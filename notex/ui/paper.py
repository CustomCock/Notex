"""Das Blatt: weiße, abgerundete Fläche mit weichem Schatten auf dem dunklen Tisch.

EditorPage ist der Inhalt eines Tabs. Es zentriert das PaperFrame (mit dem Editor)
und zeichnet darunter den Schatten selbst – ein QGraphicsDropShadowEffect würde
den Editor bei jedem Tastendruck komplett neu rastern und blurren.

Blatt-Modus: maximale Textbreite (~90 Zeichen), Blatt zentriert.
Volle Breite: das Blatt füllt den Bereich.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from notex.core.markdown import toggle_task_line
from notex.theme.tokens import LAYOUT, RADIUS, SPACING
from notex.ui.editor import Editor
from notex.ui.preview import MarkdownPreview
from notex.ui.toolbar import EditorToolbar

VIEW_MODES = ("edit", "preview", "split")
DATA_MODES = ("table", "tree", "live")   # Datenansicht statt Vorschau: CSV/TSV → Tabelle, JSON/YAML → Baum,
                                          # „live“ = Datei verfolgen (jede Textdatei, nicht im Ctrl+Shift+V-Zyklus)
ALL_MODES = VIEW_MODES + DATA_MODES
PREVIEW_DEBOUNCE_MS = 300

SHADOW_BLUR = 28      # wie weit der Schatten nach außen reicht
SHADOW_OFFSET_Y = 8
QWIDGETSIZE_MAX = 16777215


class PaperFrame(QFrame):
    """Die weiße Fläche. Das QSS malt Hintergrund + Radius, der Editor ist transparent."""

    def __init__(self, editor: Editor) -> None:
        super().__init__()
        self.setObjectName("PaperFrame")
        self.editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(editor)


def _shadow_pixmap(width: int, height: int, dpr: float) -> QPixmap:
    """Weicher Schatten als gestapelte, immer kleinere abgerundete Rechtecke.

    Jede Schicht ist fast durchsichtig; übereinander ergeben sie einen sanften Verlauf
    von außen (kaum sichtbar) nach innen (dunkler). Kein echter Gauß-Blur, sieht aber
    bei 28 Schichten genauso weich aus und kostet beim Malen nichts.
    """
    pixmap = QPixmap(int(width * dpr), int(height * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    layers = SHADOW_BLUR
    for i in range(layers):
        inset = i
        # quadratisch ansteigende Deckkraft: außen sehr schwach, innen deutlicher
        alpha = LAYOUT.paper_shadow_alpha * ((i + 1) / layers) ** 2 / layers * 2
        painter.setBrush(QColor(0, 0, 0, max(1, int(alpha))))
        rect = QRectF(inset, inset + SHADOW_OFFSET_Y, width - 2 * inset, height - 2 * inset)
        painter.drawRoundedRect(rect, RADIUS.panel + (layers - i) * 0.5, RADIUS.panel + (layers - i) * 0.5)
    painter.end()
    return pixmap


class PreviewFrame(QFrame):
    """Zweites Blatt für die Markdown-Vorschau, gleiche Optik wie PaperFrame."""

    def __init__(self, preview: MarkdownPreview) -> None:
        super().__init__()
        self.setObjectName("PaperFrame")
        self.preview = preview
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(preview)


class DataFrame(QFrame):
    """Blatt für die Datenansicht (Tabelle/Baum) – eigene Werkzeugzeile oben, deshalb ohne Editor-Leiste."""

    def __init__(self, view: QWidget) -> None:
        super().__init__()
        self.setObjectName("DataFrame")
        self.view = view
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)


class EditorPage(QWidget):
    link_requested = Signal(str)       # Ziel aus der Vorschau: "rel/pfad#Überschrift" oder Wiki-Name
    view_mode_changed = Signal(str)
    data_status_changed = Signal()     # Datenansicht: Auswahl/Filter geändert → Statusleiste
    reencode_requested = Signal(str)   # Datenansicht: Datei mit anderem Encoding neu lesen

    def __init__(self, editor: Editor, paper_mode: bool, toolbar: EditorToolbar | None = None,
                 root: Path | None = None) -> None:
        super().__init__()
        self.setObjectName("EditorPage")
        self.editor = editor
        self.frame = PaperFrame(editor)
        self.toolbar = toolbar
        self.root = root or editor.path.parent
        self.preview: MarkdownPreview | None = None
        self.preview_frame: PreviewFrame | None = None
        self.data_view = None              # CsvView / DataTreeView, erst beim ersten Umschalten gebaut
        self.data_frame: DataFrame | None = None
        self._flushing = False
        self._data_hooked = False
        self._data_reload = QTimer(self)
        self._data_reload.setSingleShot(True)
        self._data_reload.setInterval(PREVIEW_DEBOUNCE_MS)
        self._data_reload.timeout.connect(self._reload_data_view)
        self.view_mode = "edit"
        self.sync_scroll = True
        self._shadow: QPixmap | None = None
        self._shadow_key: tuple = ()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._syncing = False

        # Spalte: Bearbeitungsleiste oben, darunter Blatt (+ Vorschau-Blatt daneben) – gleich breit
        self.column = QWidget()
        column_layout = QVBoxLayout(self.column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        if toolbar is not None:
            column_layout.addWidget(toolbar)
            self.frame.setProperty("attached", True)   # oben eckig, weil die Leiste den Radius trägt
            toolbar.visibility_changed.connect(lambda _v: self.update())
        self.body = QSplitter(Qt.Orientation.Horizontal)
        self.body.setObjectName("PreviewSplitter")
        self.body.setHandleWidth(SPACING.sm)
        self.body.setChildrenCollapsible(False)
        self.body.addWidget(self.frame)
        column_layout.addWidget(self.body, 1)

        margin = LAYOUT.paper_margin
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin - SHADOW_OFFSET_Y // 2, margin, margin)
        layout.addStretch(1)
        layout.addWidget(self.column, 0)
        layout.addStretch(1)
        self._layout = layout
        self.set_paper_mode(paper_mode)

    def set_paper_mode(self, enabled: bool) -> None:
        self.paper_mode = enabled
        if enabled:
            # Maximale Textbreite in Zeichen + Zeilennummern + rechter Rand + Scrollbar.
            # Das ist ein Maximum: wird das Fenster schmaler, schrumpft das Blatt mit.
            # Geteilte Ansicht: zwei Blätter nebeneinander, also doppelt so breit.
            text_width = int(LAYOUT.paper_max_columns * self.editor.char_width())
            width = text_width + self.editor.gutter_width() + SPACING.xl + LAYOUT.scrollbar + SPACING.sm
            if self.view_mode == "split":
                width = 2 * width + self.body.handleWidth()
            self.column.setMaximumWidth(width if self.view_mode not in DATA_MODES else QWIDGETSIZE_MAX)
        else:
            self.column.setMaximumWidth(QWIDGETSIZE_MAX)
        # Das Blatt bekommt (fast) allen Platz bis zu seiner Maximalbreite, der Rest
        # verteilt sich gleichmäßig auf beide Seiten -> zentriert
        self._layout.setStretch(0, 1)
        self._layout.setStretch(1, 1000)
        self._layout.setStretch(2, 1)
        self.update()

    def retheme(self) -> None:
        self._fit_padding()
        self._shadow = None
        self.editor.retheme()
        if self.preview is not None:
            self.preview.set_fonts(self.editor.font().family(), self.editor.font_size)
            self.preview.retheme()
        self.refresh_width()
        self.update()

    # ---- Markdown-Vorschau ---------------------------------------------------------
    @property
    def supports_preview(self) -> bool:
        return self.editor.path.suffix.lower() in (".md", ".markdown")

    @property
    def data_kind(self) -> str | None:
        """"table" (CSV/TSV), "tree" (JSON/YAML) oder None. Nie für .ntx."""
        from notex.core import csvdata, structured
        if getattr(self.editor, "encrypted", False):
            return None
        if csvdata.table_supported(self.editor.path):
            return "table"
        if structured.kind_for(self.editor.path):
            return "tree"
        return None

    @property
    def view_modes(self) -> tuple[str, ...]:
        if self.supports_preview:
            return VIEW_MODES
        kind = self.data_kind
        return ("edit", kind) if kind else ("edit",)

    @property
    def supports_live(self) -> bool:
        """„Live verfolgen“ für jede Textdatei auf der Platte – nie für .ntx (Klartext nur im Editor)."""
        from notex.core.tail import can_follow
        return not getattr(self.editor, "encrypted", False) and can_follow(self.editor.path)

    @property
    def supports_alt_view(self) -> bool:
        return len(self.view_modes) > 1

    def set_view_mode(self, mode: str) -> None:
        """"edit" (nur Blatt), "preview" (nur Vorschau), "split" (beides nebeneinander) – bei CSV/TSV "table",
        bei JSON/YAML "tree". Nicht passende Modi fallen auf "edit" zurück."""
        if mode not in self.view_modes and not (mode == "live" and self.supports_live):
            mode = "edit"
        if self.view_mode in DATA_MODES and mode != self.view_mode:
            self.flush_data_view()
        if self.view_mode == "live" and mode != "live":
            self._stop_live()
        if mode in ("preview", "split") and self.preview is None:
            self._create_preview()
        if mode in DATA_MODES:
            self._show_data_view(mode)
        self.view_mode = mode
        self.frame.setVisible(mode not in ("preview",) + DATA_MODES)
        if self.preview_frame is not None:
            self.preview_frame.setVisible(mode in ("preview", "split"))
        if self.data_frame is not None:
            self.data_frame.setVisible(mode in DATA_MODES)
        if self.toolbar is not None:
            self.toolbar.setVisible(mode not in DATA_MODES)
        if mode in ("preview", "split"):
            self._preview_timer.stop()
            self._refresh_preview()
            if mode == "split":
                self.body.setSizes([1, 1])
        self.refresh_width()
        if mode in DATA_MODES:
            self.data_view.setFocus()
        else:
            (self.preview if mode == "preview" and self.preview is not None else self.editor).setFocus()
        self.view_mode_changed.emit(mode)

    def cycle_view_mode(self) -> str:
        modes = self.view_modes
        index = modes.index(self.view_mode) if self.view_mode in modes else 0
        self.set_view_mode(modes[(index + 1) % len(modes)])
        return self.view_mode

    # ---- Datenansicht (Tabelle/Baum) -------------------------------------------------
    def _show_data_view(self, mode: str) -> None:
        if self.data_view is None or getattr(self.data_view, "kind", None) != mode:
            self._create_data_view(mode)
        self._load_data_view()

    def _create_data_view(self, mode: str) -> None:
        if self.data_frame is not None:
            self.data_frame.setParent(None)
            self.data_frame.deleteLater()
        if mode == "tree":
            from notex.ui.tree_view import DataTreeView
            view = DataTreeView()
            view.jump_requested.connect(self._jump_to_error)
        elif mode == "live":
            from notex.ui.log_view import LogView
            view = LogView()
            view.set_font(self.editor.font())
            view.stop_requested.connect(lambda: self.set_view_mode("edit"))
        else:
            from notex.ui.csv_view import CsvView
            view = CsvView()
        view._reparse = self._reparse_table
        view._reencode = self.reencode_requested.emit
        view.changed.connect(self._on_data_edited)
        view.status_changed.connect(self.data_status_changed)
        self.data_view = view
        self.data_frame = DataFrame(view)
        self.body.addWidget(self.data_frame)
        if not self._data_hooked:
            self._data_hooked = True
            self.editor.document().contentsChanged.connect(self._on_text_changed_for_data)
            self.editor.document().modificationChanged.connect(self._on_modification_for_data)

    def _load_data_view(self, dialect=None) -> None:
        view = self.data_view
        if view.kind == "live":
            view.load_text("", self.editor.path.name, None, self.editor.encoding, path=self.editor.path)
            return
        keep = dialect or (view.dialect if view.overridden else None)
        view.load_text(self.editor.toPlainText(), self.editor.path.name, keep, self.editor.encoding)

    def _stop_live(self) -> None:
        """Live beendet: Tailer anhalten, Editor zeigt den aktuellen Stand der Datei (ungespeicherte Änderungen
        gibt es nicht – live startet nur bei gespeichertem Tab)."""
        if self.data_view is not None and self.data_view.kind == "live":
            self.data_view.stop()
        if not self.editor.is_dirty:
            from notex.core.encoding import read_text_file
            try:
                self.editor.replace_content(read_text_file(self.editor.path))
            except OSError:
                pass

    def _jump_to_error(self, position: int) -> None:
        self.set_view_mode("edit")
        cursor = self.editor.textCursor()
        cursor.setPosition(min(position, self.editor.document().characterCount() - 1))
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.editor.setFocus()

    def _reparse_table(self, dialect) -> None:
        """Anderes Trennzeichen gewählt: ungespeicherte Tabellenänderungen erst in den Text, dann neu lesen."""
        self.flush_data_view()
        self._load_data_view(dialect)

    def _on_data_edited(self) -> None:
        self.editor.document().setModified(True)

    def _on_text_changed_for_data(self) -> None:
        """Text wurde anderswo geändert (zweite Ansicht, Neu laden): Tabelle nachziehen – außer sie hat eigene
        ungespeicherte Änderungen, dann gewinnt die Tabelle beim nächsten Zurückschreiben."""
        if self._flushing or self.view_mode not in DATA_MODES or self.data_view is None or self.data_view.dirty:
            return
        if self.view_mode == "live":
            return                       # liest selbst von der Platte
        self._data_reload.start()

    def _on_modification_for_data(self, modified: bool) -> None:
        """Dokument wieder „unverändert“, obwohl die Tabelle noch Änderungen hat → es wurde neu geladen
        (extern geändert, anderes Encoding). Gespeichert kann es nicht sein, das schreibt vorher zurück."""
        if not modified and not self._flushing and self.data_view is not None and self.data_view.dirty:
            self.data_view.dirty = False
            self._data_reload.start()

    def _reload_data_view(self) -> None:
        if self.view_mode in DATA_MODES and self.data_view is not None and not self.data_view.dirty:
            self._load_data_view()

    def flush_data_view(self) -> bool:
        """Änderungen aus der Tabelle als EIN Undo-Schritt in den Editor schreiben (vor Speichern/Umschalten).
        True, wenn etwas geschrieben wurde."""
        view = self.data_view
        if view is None or not view.dirty:
            return False
        from PySide6.QtGui import QTextCursor
        new_text = view.text()
        view.dirty = False
        if new_text == self.editor.toPlainText():
            return False
        self._flushing = True
        try:
            cursor = QTextCursor(self.editor.document())
            cursor.select(QTextCursor.SelectionType.Document)
            self.editor._grouped(lambda: cursor.insertText(new_text))
        finally:
            self._flushing = False
        return True

    def _create_preview(self) -> None:
        self.preview = MarkdownPreview(self.root)
        self.preview_frame = PreviewFrame(self.preview)
        if self.toolbar is not None:
            self.preview_frame.setProperty("attached", True)   # wie das Blatt: oben eckig unter der Leiste
        self.body.addWidget(self.preview_frame)
        self.preview.set_fonts(self.editor.font().family(), self.editor.font_size)
        self.preview.set_padding(self.editor._padding)
        self.preview.open_requested.connect(self.link_requested)
        self.preview.toggle_requested.connect(self._toggle_task)
        self.preview.scrolled.connect(self._on_preview_scrolled)
        self.editor.textChanged.connect(self._schedule_preview)
        self.editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)

    def _schedule_preview(self) -> None:
        if self.view_mode != "edit":
            self._preview_timer.start()

    def _refresh_preview(self) -> None:
        if self.preview is not None and self.view_mode != "edit":
            text = self.editor.toPlainText()
            service = self.editor.variables
            self._preview_lines = None
            if service is not None and service.prefix in text:     # Vorschau zeigt Werte, Escapes als normales §name
                from notex.core.variables import resolve_with_line_map
                text, self._preview_lines = resolve_with_line_map(text, service.values, service.prefix)
            self.preview.set_source(text, self.editor.path)

    _preview_lines: list[int] | None = None

    def _toggle_task(self, line: int) -> None:
        if self._preview_lines is not None and 0 <= line < len(self._preview_lines):
            line = self._preview_lines[line]           # Zeile der Vorschau → Zeile im Original (mehrzeilige Werte)
        new_text = toggle_task_line(self.editor.toPlainText(), line)
        if new_text is None:
            return
        new_line = new_text.split("\n")[line]
        self.editor._grouped(lambda: self.editor._replace_blocks(line, line, [new_line]))
        self._preview_timer.stop()
        self._refresh_preview()

    def _on_editor_scrolled(self, value: int) -> None:
        if self._syncing or not self.sync_scroll or self.view_mode != "split" or self.preview is None:
            return
        bar = self.editor.verticalScrollBar()
        if bar.maximum():
            self._syncing = True
            self.preview.set_scroll_fraction(value / bar.maximum())
            self._syncing = False

    def _on_preview_scrolled(self, fraction: float) -> None:
        if self._syncing or not self.sync_scroll or self.view_mode != "split":
            return
        bar = self.editor.verticalScrollBar()
        self._syncing = True
        bar.setValue(round(fraction * bar.maximum()))
        self._syncing = False

    def refresh_width(self) -> None:
        """Nach Zoom: die maximale Breite hängt von der Zeichenbreite ab."""
        self.set_paper_mode(self.paper_mode)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_padding()
        if self.lock_overlay is not None:
            self.lock_overlay.setGeometry(self.rect())

    # ---- Sperrbildschirm (verschlüsselte Notizen) -------------------------------------
    lock_overlay = None

    def show_lock(self, mode: str = "unlock", message: str = "", info: str = "") -> None:
        from notex.ui.lock_overlay import LockOverlay
        if self.lock_overlay is None:
            self.lock_overlay = LockOverlay(self, self.editor.path.name)
        self.lock_overlay.set_mode(mode, message, info)
        self.lock_overlay.setGeometry(self.rect())
        self.lock_overlay.raise_()
        self.lock_overlay.show()
        self.lock_overlay.focus_password()

    def hide_lock(self) -> None:
        if self.lock_overlay is not None:
            self.lock_overlay.hide()

    def _fit_padding(self) -> None:
        """Bei wenig Platz Innenabstand und Rand herunterskalieren (Minimum 16 px innen, 8 px außen)."""
        width = self.width()
        full, tight = 760, 420      # ab `full` Pixeln volle Abstände, bei `tight` die Minima
        t = min(1.0, max(0.0, (width - tight) / (full - tight)))
        margin = round(SPACING.sm + (LAYOUT.paper_margin - SPACING.sm) * t)
        padding = round(SPACING.lg + (LAYOUT.paper_padding - SPACING.lg) * t)
        self._layout.setContentsMargins(margin, max(SPACING.sm, margin - SHADOW_OFFSET_Y // 2), margin, margin)
        self.editor.set_padding(padding)
        if self.preview is not None:
            self.preview.set_padding(max(SPACING.lg, padding))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        geo: QRect = self.column.geometry()   # Leiste + Blatt werfen einen gemeinsamen Schatten
        if geo.isEmpty() or not LAYOUT.paper_shadow or LAYOUT.paper_shadow_alpha <= 0:
            return
        width, height = geo.width() + 2 * SHADOW_BLUR, geo.height() + 2 * SHADOW_BLUR
        dpr = self.devicePixelRatioF()
        key = (width, height, dpr, LAYOUT.paper_shadow_alpha, RADIUS.panel)
        if self._shadow is None or self._shadow_key != key:
            self._shadow = _shadow_pixmap(width, height, dpr)
            self._shadow_key = key
        painter = QPainter(self)
        painter.drawPixmap(geo.left() - SHADOW_BLUR, geo.top() - SHADOW_BLUR, self._shadow)
