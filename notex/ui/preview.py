"""Markdown-Vorschau neben/statt dem Editor: QTextBrowser mit dem HTML aus core.markdown.

Sicherheit: setOpenLinks(False) – kein Link öffnet sich von selbst. Externe Links gehen erst auf
Klick an den System-Browser, externe Bilder werden nur nach Klick auf „Bild laden“ geholt
(eigener Thread, Größenlimit). loadResource() liefert ausschließlich lokale Bilder aus dem
Notizordner und bereits freigegebene externe Bilder – alles andere bleibt leer.
Mermaid-Diagramme (```mermaid) rendert der Kern offline zu SVG; hier werden sie nur als Bild gezeichnet
(notex-mermaid:<Schlüssel>), passend zur Breite verkleinert und per Rechtsklick als PNG/SVG speicherbar.
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QImage, QTextCursor, QTextDocument
from PySide6.QtWidgets import QFileDialog, QFrame, QTextBrowser

from notex import APP_NAME
from notex.core import fileops
from notex.core.markdown import RenderOptions, render, stylesheet
from notex.theme import tokens
from notex.theme.fonts import MONO_FAMILIES
from notex.theme.tokens import COLORS, LAYOUT, SPACING

MAX_IMAGE_BYTES = 8 * 1024 * 1024
FETCH_TIMEOUT = 15


class ImageFetcher(QThread):
    """Holt ein externes Bild – nur auf ausdrücklichen Klick, nie automatisch."""
    fetched = Signal(str, bytes)
    failed = Signal(str, str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            request = urllib.request.Request(self.url, headers={"User-Agent": f"{APP_NAME}"})
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                content_type = response.headers.get("Content-Type", "")
                if not content_type.startswith("image/"):
                    raise ValueError(f"kein Bild ({content_type or 'unbekannter Typ'})")
                data = response.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("Bild größer als 8 MB")
            self.fetched.emit(self.url, data)
        except Exception as error:  # noqa: BLE001 – jede Ursache landet als Text in der Vorschau
            self.failed.emit(self.url, str(error))


class MarkdownPreview(QTextBrowser):
    open_requested = Signal(str)     # "rel/pfad#Überschrift" aus notex-open:
    toggle_requested = Signal(int)   # 0-basierte Zeile einer Aufgabe
    scrolled = Signal(float)         # Scroll-Anteil 0..1 (für Sync mit dem Editor)
    mermaid_enabled = True           # Einstellung „Mermaid-Diagramme anzeigen“ (für alle Vorschauen)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.setObjectName("Preview")
        self.root = root
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.document().setDocumentMargin(SPACING.xs)
        self._text = ""
        self._path: Path | None = None
        self._base_dir = ""
        self._font_family = ""
        self._font_size = tokens.FONT_SIZE.editor
        self._padding = LAYOUT.paper_padding
        self._syncing = False
        self._images: dict[str, QImage] = {}
        self._errors: dict[str, str] = {}
        self._fetchers: list[ImageFetcher] = []
        self._diagrams: dict = {}                     # Schlüssel → mermaid.Diagram (aktueller Stand)
        self._diagram_images: dict[str, QImage] = {}
        self._rendered_width = 0
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self.render_now)
        self.anchorClicked.connect(self._on_anchor)
        self.verticalScrollBar().valueChanged.connect(self._on_scrolled)
        self._update_margins()

    # ---- Inhalt --------------------------------------------------------------------------
    def set_source(self, text: str, path: Path) -> None:
        self._text = text
        self._path = path
        try:
            self._base_dir = path.parent.relative_to(self.root).as_posix() if fileops.is_within(path, self.root) else ""
        except ValueError:
            self._base_dir = ""
        if self._base_dir == ".":
            self._base_dir = ""
        self.render_now()

    def set_fonts(self, family: str, size: int) -> None:
        self._font_family, self._font_size = family, size
        self.render_now()

    def set_padding(self, padding: int) -> None:
        if padding != self._padding:
            self._padding = padding
            self._update_margins()

    def _update_margins(self) -> None:
        top = max(SPACING.md, round(self._padding * 0.85))
        self.setViewportMargins(self._padding, top, max(SPACING.lg, self._padding // 2), top)

    def colors(self) -> dict[str, str]:
        c = {"text": COLORS.paper_text, "muted": COLORS.paper_muted, "accent": COLORS.accent,
             "code_bg": COLORS.paper_line, "border": COLORS.paper_muted, "danger": COLORS.danger,
             "bg": COLORS.paper}
        c.update(tokens.SYNTAX)
        return c

    def render_now(self) -> None:
        bar = self.verticalScrollBar()
        fraction = bar.value() / bar.maximum() if bar.maximum() else 0.0
        self._rendered_width = self._diagram_width()
        options = RenderOptions(colors=self.colors(), loaded_images=set(self._images), base_dir=self._base_dir,
                                diagrams=MarkdownPreview.mermaid_enabled, max_diagram_width=self._rendered_width)
        result = render(self._text, options)
        self._diagrams = result.diagrams
        self._diagram_images = {k: v for k, v in self._diagram_images.items() if k in self._diagrams}
        body = result.html
        for url, error in self._errors.items():
            body = body.replace('>Bild laden</a>', f'>Bild laden</a> <span style="color:{COLORS.danger}">({error})</span>', 1) \
                if url in result.external_images else body
        self.document().setDefaultStyleSheet(stylesheet(self.colors(), self._font_family, self._font_size, MONO_FAMILIES[0]))
        self._syncing = True
        self.setHtml(body)
        bar.setValue(round(fraction * bar.maximum()))
        self._syncing = False

    def retheme(self) -> None:
        self.render_now()
        self.viewport().update()

    # ---- Ressourcen: nur lokale Bilder aus dem Notizordner und freigegebene externe -----------
    def _diagram_width(self) -> int:
        return max(160, self.viewport().width() - 2 * round(self.document().documentMargin()) - 12)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._diagrams and abs(self._diagram_width() - self._rendered_width) > 16:
            self._resize_timer.start()           # breite Diagramme an die neue Breite anpassen

    def loadResource(self, type_: int, name: QUrl):
        key = name.toString()
        if key.startswith("notex-mermaid:"):
            return self._diagram_image(key[len("notex-mermaid:"):])
        if key.startswith("notex-file:"):
            path = self.root / key[len("notex-file:"):]
            if fileops.is_within(path, self.root) and path.is_file():
                try:
                    if path.stat().st_size <= MAX_IMAGE_BYTES:
                        image = QImage(str(path))
                        if not image.isNull():
                            return image
                except OSError:
                    pass
            return QImage()
        if key in self._images:
            return self._images[key]
        return QImage()   # nichts anderes wird je geladen (kein http, kein file:, kein qrc:)

    def _diagram_image(self, key: str) -> QImage:
        from notex.ui.diagram_image import svg_to_image
        diagram = self._diagrams.get(key)
        if diagram is None:
            return QImage()
        if key not in self._diagram_images:
            scale = max(1.0, self.devicePixelRatioF())
            self._diagram_images[key] = svg_to_image(diagram.svg, diagram.width, diagram.height, scale)
        return self._diagram_images[key]

    # ---- Diagramm speichern (Rechtsklick) --------------------------------------------------
    def diagram_at(self, pos) -> str | None:
        cursor = self.cursorForPosition(pos)
        for _ in range(2):
            fmt = cursor.charFormat()
            if fmt.isImageFormat():
                name = fmt.toImageFormat().name()
                if name.startswith("notex-mermaid:"):
                    return name[len("notex-mermaid:"):]
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
        return None

    def contextMenuEvent(self, event) -> None:
        menu = self.createStandardContextMenu(event.pos())
        key = self.diagram_at(event.pos())
        if key and key in self._diagrams:
            first = menu.actions()[0] if menu.actions() else None
            png = menu.addAction("Diagramm als PNG speichern …")
            svg = menu.addAction("Diagramm als SVG speichern …")
            png.triggered.connect(lambda: self.save_diagram(key, "png"))
            svg.triggered.connect(lambda: self.save_diagram(key, "svg"))
            if first is not None:
                menu.removeAction(png)
                menu.removeAction(svg)
                menu.insertAction(first, png)
                menu.insertAction(first, svg)
                menu.insertSeparator(first)
        menu.exec(event.globalPos())

    def save_diagram(self, key: str, kind: str, path: str | None = None) -> bool:
        from notex.ui.diagram_image import svg_to_image
        diagram = self._diagrams.get(key)
        if diagram is None:
            return False
        if path is None:
            if self._path is not None and fileops.is_encrypted_path(self._path):
                from notex.ui import dialogs
                if not dialogs.confirm(self, "Diagramm aus verschlüsselter Notiz speichern",
                                       "Das Bild zeigt Inhalt dieser verschlüsselten Notiz und wird unverschlüsselt "
                                       "gespeichert.", informative="Nur fortfahren, wenn der Zielort sicher ist.",
                                       yes="Trotzdem speichern", danger=True):
                    return False
            stem = re.sub(r'[\\/:*?"<>|]+', "-", diagram.title or "diagramm").strip(" .-") or "diagramm"
            suggestion = str(self.root / f"{stem}.{kind}")
            path, _ = QFileDialog.getSaveFileName(self, "Diagramm speichern", suggestion,
                                                  "PNG-Bild (*.png)" if kind == "png" else "SVG-Grafik (*.svg)")
            if not path:
                return False
        try:
            if kind == "svg":
                Path(path).write_text(diagram.svg, encoding="utf-8")
                return True
            return svg_to_image(diagram.svg, diagram.width, diagram.height, 2.0, COLORS.paper).save(path, "PNG")
        except OSError:
            return False

    # ---- Klicks ----------------------------------------------------------------------------
    def _on_anchor(self, url: QUrl) -> None:
        text = url.toString()
        if text.startswith("notex-open:"):
            self.open_requested.emit(text[len("notex-open:"):])
        elif text.startswith("notex-toggle:"):
            try:
                self.toggle_requested.emit(int(text[len("notex-toggle:"):]))
            except ValueError:
                pass
        elif text.startswith("notex-load:"):
            self._fetch(text[len("notex-load:"):])
        elif url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)   # nur auf Klick, nie automatisch
        elif text.startswith("#"):
            self.scrollToAnchor(text[1:])

    def _fetch(self, url: str) -> None:
        if url in self._images or any(f.url == url for f in self._fetchers):
            return
        fetcher = ImageFetcher(url)
        fetcher.fetched.connect(self._on_fetched)
        fetcher.failed.connect(self._on_failed)
        fetcher.finished.connect(lambda f=fetcher: self._fetchers.remove(f) if f in self._fetchers else None)
        self._fetchers.append(fetcher)
        fetcher.start()

    def _on_fetched(self, url: str, data: bytes) -> None:
        image = QImage.fromData(data)
        if image.isNull():
            self._on_failed(url, "Bildformat nicht lesbar")
            return
        self._errors.pop(url, None)
        self._images[url] = image
        self.document().addResource(QTextDocument.ResourceType.ImageResource.value, QUrl(url), image)
        self.render_now()

    def _on_failed(self, url: str, error: str) -> None:
        self._errors[url] = error
        self.render_now()

    # ---- Scroll-Sync -----------------------------------------------------------------------
    def _on_scrolled(self, value: int) -> None:
        bar = self.verticalScrollBar()
        if not self._syncing and bar.maximum():
            self.scrolled.emit(value / bar.maximum())

    def set_scroll_fraction(self, fraction: float) -> None:
        bar = self.verticalScrollBar()
        self._syncing = True
        bar.setValue(round(max(0.0, min(1.0, fraction)) * bar.maximum()))
        self._syncing = False

    def shutdown(self) -> None:
        for fetcher in self._fetchers:
            fetcher.wait(100)
