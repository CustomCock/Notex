"""Nachschlage-Karte: kleines Popover neben der Markierung mit Wikipedia- oder Wiktionary-Inhalt.

- Abrufe laufen in einem Worker-Thread (eine Anfrage nach der anderen), die UI friert nie ein.
- Die ganze Karte ist klickbar und öffnet Artikel/Eintrag im Standardbrowser; Links in der Karte (Quelle
  wechseln, Begriffsklärung, „mehr“, Websuche) haben Vorrang.
- Schließen: Esc, Klick daneben (Popup), ×. Fade-In respektiert „Animationen reduzieren“.
- Die Websuche öffnet nur den Browser – Notex ruft dabei nichts ab.
"""
from __future__ import annotations

import html
from typing import Callable

from PySide6.QtCore import QEvent, QRect, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from notex.core import lookup as lk
from notex.theme.tokens import COLORS, DURATION, SPACING
from notex.ui import anim
from notex.ui.widgets import IconButton

CARD_WIDTH = 392
BODY_MAX = 196          # ≈ 8 Zeilen, danach scrollt der Inhalt in der Karte
MAX_MEANINGS = 5
SOURCE_NAMES = {"wikipedia": "Wikipedia", "wiktionary": "Wiktionary"}


class _Worker(QThread):
    done = Signal(int, object, str, str)   # Generation, Ergebnis, Fehlerart, Fehlertext

    def __init__(self, generation: int, job: Callable[[], object]) -> None:
        super().__init__()
        self.generation, self.job = generation, job

    def run(self) -> None:
        try:
            self.done.emit(self.generation, self.job(), "", "")
        except lk.LookupError_ as error:
            self.done.emit(self.generation, None, error.kind, str(error))
        except Exception as error:  # noqa: BLE001 – nie abstürzen, nur in der Karte melden
            self.done.emit(self.generation, None, "error", str(error))


class LookupCard(QWidget):
    """Top-Level-Popup. Außen transparent (runde Ecken), innen QFrame#LookupCard."""

    def __init__(self, parent: QWidget, service: lk.LookupService, config: dict) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.service, self.config = service, config
        self._generation = 0
        self._workers: list[_Worker] = []
        self._browser_url = ""
        self._hovered: dict[int, str] = {}
        self._expanded = False
        self._result = None
        self.term = ""
        self.source = "wikipedia"
        self.langs: list[str] = ["de", "en"]
        self.anchor = QRect()

        self.card = QFrame(self)
        self.card.setObjectName("LookupCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.source_label = QLabel()
        self.source_label.setObjectName("LookupSource")
        self.close_button = IconButton("x", "Schließen  Esc")
        self.close_button.clicked.connect(self.close)
        self.thumb = QLabel()
        self.thumb.setFixedSize(64, 64)
        self.thumb.setScaledContents(False)
        self.thumb.hide()
        self.title = QLabel()
        self.title.setObjectName("LookupTitle")
        self.title.setWordWrap(True)
        self.description = QLabel()
        self.description.setObjectName("LookupDescription")
        self.description.setWordWrap(True)
        self.body = QLabel()
        self.body.setObjectName("LookupBody")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body.setOpenExternalLinks(False)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("LookupScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.body)
        self.skeleton = QWidget()
        skeleton_layout = QVBoxLayout(self.skeleton)
        skeleton_layout.setContentsMargins(0, SPACING.xs, 0, SPACING.xs)
        skeleton_layout.setSpacing(SPACING.sm)
        for width in (0.55, 1.0, 0.92, 0.97, 0.7):
            bar = QFrame()
            bar.setObjectName("LookupSkeleton")
            bar.setFixedSize(int((CARD_WIDTH - 2 * SPACING.lg) * width), 12)
            skeleton_layout.addWidget(bar)
        self.links = QLabel()
        self.links.setObjectName("LookupLinks")
        self.links.setTextFormat(Qt.TextFormat.RichText)
        self.links.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.open_hint = QLabel("Im Browser öffnen ↗")
        self.open_hint.setObjectName("LookupOpen")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.source_label)
        header.addStretch(1)
        header.addWidget(self.close_button)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self.title)
        title_col.addWidget(self.description)
        title_row.addLayout(title_col, 1)
        title_row.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self.links)
        footer.addStretch(1)
        footer.addWidget(self.open_hint)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(SPACING.lg, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.sm)
        layout.addLayout(header)
        layout.addLayout(title_row)
        layout.addWidget(self.skeleton)
        layout.addWidget(self.scroll)
        layout.addLayout(footer)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        for label in (self.body, self.links):
            label.linkActivated.connect(self._on_link)
            label.linkHovered.connect(lambda link, l=label: self._hovered.__setitem__(id(l), link))
        for widget in (self.card, self.body, self.scroll.viewport(), self.title, self.description, self.source_label,
                       self.open_hint, self.links, self.thumb, self.skeleton):
            widget.installEventFilter(self)
        self.setFixedWidth(CARD_WIDTH)

    # ---- Öffentlich ----------------------------------------------------------------------------
    def open(self, source: str, term: str, langs: list[str], anchor: QRect) -> None:
        self.term, self.langs, self.anchor = term, langs, anchor
        self._expanded = False
        self._load(source, term)
        self._fade_in()

    def show_result(self, source: str, term: str, result, anchor: QRect, langs: list[str] | None = None) -> None:
        """Ergebnis direkt anzeigen (Tests, Screenshots, Cache-Treffer)."""
        self.term, self.anchor, self.source = term, anchor, source
        self.langs = langs or self.langs
        self._render(result)
        self._fade_in()

    def show_error(self, source: str, term: str, kind: str, anchor: QRect) -> None:
        self.term, self.anchor, self.source = term, anchor, source
        self._render_error(kind, "")
        self._fade_in()

    # ---- Laden ---------------------------------------------------------------------------------
    def _load(self, source: str, term: str, article: bool = False) -> None:
        self.source = source
        self._generation += 1
        self._result = None
        name = SOURCE_NAMES.get(source, source)
        self.source_label.setText(f"{name.upper()} · {self.langs[0].upper()}")
        self.title.setText(html.escape(term))
        self.description.hide()
        self.thumb.hide()
        self.scroll.hide()
        self.skeleton.show()
        self._set_links()
        self._browser_url = (lk.wikipedia_search_url if source == "wikipedia" else lk.wiktionary_search_url)(self.langs[0], term)
        key = "wikipedia-article" if article else source
        cached = self.service.cached(key, term, self.langs)
        if cached is not None:
            self._render(cached)
            return
        generation = self._generation
        langs = list(self.langs)
        worker = _Worker(generation, lambda: self.service.lookup(key, term, langs))
        worker.done.connect(self._on_done)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(worker)
        worker.start()
        self._fit()

    def _on_done(self, generation: int, result, kind: str, message: str) -> None:
        if generation != self._generation:
            return   # veraltet: der Nutzer hat inzwischen etwas anderes geklickt
        if kind:
            self._render_error(kind, message)
        else:
            self._render(result)

    # ---- Darstellung -----------------------------------------------------------------------------
    def _render(self, result) -> None:
        self._result = result
        self.skeleton.hide()
        self.scroll.show()
        self.scroll.verticalScrollBar().setValue(0)
        source = "wikipedia" if isinstance(result, (lk.Summary, lk.Disambiguation)) else "wiktionary"
        self.source = source
        self.source_label.setText(f"{SOURCE_NAMES[source].upper()} · {result.lang.upper()}")
        self._browser_url = result.url
        muted = COLORS.text_muted
        if isinstance(result, lk.Summary):
            self.title.setText(html.escape(result.title))
            self.description.setText(html.escape(result.description))
            self.description.setVisible(bool(result.description))
            body = html.escape(result.extract or "Kein Auszug vorhanden.")
            self.body.setText(f'<p style="line-height:145%">{body}</p>')
            self._maybe_thumbnail(result.thumbnail)
        elif isinstance(result, lk.Disambiguation):
            self.title.setText(html.escape(result.title))
            self.description.setText("Begriffsklärung – bitte wählen:")
            self.description.show()
            rows = []
            for target, desc in result.options:
                link = f'<a href="article:{html.escape(target, quote=True)}" style="color:{COLORS.accent}">{html.escape(target)}</a>'
                rows.append(f"<li style='margin-bottom:4px'>{link}"
                            + (f'<span style="color:{muted}"> – {html.escape(desc)}</span>' if desc else "") + "</li>")
            self.body.setText("<ul style='margin-left:-24px'>" + "".join(rows) + "</ul>" if rows
                              else f'<p style="color:{muted}">Keine Optionen gefunden – im Browser öffnen.</p>')
        else:
            self.title.setText(html.escape(result.title))
            info = [result.language_name] if result.language_name else []
            if result.ipa:
                info.append(f"[{result.ipa}]" if not result.ipa.startswith(("/", "[")) else result.ipa)
            self.description.setText(html.escape(" · ".join(info)))
            self.description.setVisible(bool(info))
            self.body.setText(self._definition_html(result))
        self._set_links()
        self._fit()

    def _definition_html(self, d: lk.Definition) -> str:
        muted, accent = COLORS.text_muted, COLORS.accent
        shown = 0
        parts_html = []
        total = sum(len(p.meanings) for p in d.parts)
        for part in d.parts:
            items = []
            for number, meaning in enumerate(part.meanings, start=1):
                if not self._expanded and shown >= MAX_MEANINGS:
                    break
                items.append(f"<tr><td style='color:{muted}; padding-right:6px' valign='top'>{number}.</td>"
                             f"<td style='padding-bottom:3px'>{html.escape(meaning)}</td></tr>")
                shown += 1
            if items:
                parts_html.append(f"<p style='margin:6px 0 2px 0'><b>{html.escape(part.name)}</b></p>"
                                  f"<table cellspacing='0' cellpadding='0'>{''.join(items)}</table>")
        if total > shown:
            parts_html.append(f'<p><a href="more" style="color:{accent}">{total - shown} weitere Bedeutungen …</a></p>')
        if d.etymology:
            parts_html.append(f"<p style='margin-top:8px'><b>Herkunft</b><br><span style='color:{muted}'>"
                              f"{html.escape(d.etymology)}</span></p>")
        return "".join(parts_html)

    def _render_error(self, kind: str, message: str) -> None:
        self._result = None
        self.skeleton.hide()
        self.scroll.show()
        self.thumb.hide()
        self.description.hide()
        self.title.setText(html.escape(self.term))
        engine = self.config.get("lookup", {}).get("engine", "google")
        custom = self.config.get("lookup", {}).get("custom_url", "")
        text = lk.ERROR_TEXTS.get(kind, lk.ERROR_TEXTS["error"])
        if kind == "not_found":
            where = "auf Wikipedia" if self.source == "wikipedia" else "im Wiktionary"
            text = f"Zu „{html.escape(self.term)}“ gibt es {where} keinen Eintrag (Deutsch und Englisch geprüft)."
        extra = ""
        if kind == "not_found" and self.source == "wiktionary":
            extra = f'<a href="switch:wikipedia" style="color:{COLORS.accent}">Auf Wikipedia versuchen</a><br>'
        search = f'<a href="web" style="color:{COLORS.accent}">Bei {html.escape(lk.search_engine_name(engine, custom))} suchen ↗</a>'
        self.body.setText(f'<p style="line-height:145%">{text}</p><p>{extra}{search}</p>')
        self._browser_url = lk.search_url(self.term, engine, custom)
        self._set_links(with_web=False)   # der Ausweg „Bei … suchen“ steht schon im Text
        self._fit()

    def _set_links(self, with_web: bool = True) -> None:
        accent = COLORS.accent
        other = "wiktionary" if self.source == "wikipedia" else "wikipedia"
        engine = self.config.get("lookup", {}).get("engine", "google")
        custom = self.config.get("lookup", {}).get("custom_url", "")
        text = f'<a href="switch:{other}" style="color:{accent}">{SOURCE_NAMES[other]}</a>'
        if with_web:
            text += (f'&nbsp;&nbsp;·&nbsp;&nbsp;<a href="web" style="color:{accent}">'
                     f'{html.escape(lk.search_engine_name(engine, custom))} ↗</a>')
        self.links.setText(text)

    def _maybe_thumbnail(self, url: str) -> None:
        self.thumb.hide()
        if not url or not self.config.get("lookup", {}).get("thumbnails", False):
            return
        generation = self._generation
        worker = _Worker(generation, lambda: lk.fetch_bytes(url))
        worker.done.connect(self._on_thumbnail)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _on_thumbnail(self, generation: int, data, kind: str, _message: str) -> None:
        if generation != self._generation or kind or not data:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.thumb.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
            self.thumb.show()
            self._fit()

    # ---- Größe und Position ----------------------------------------------------------------------
    def _fit(self) -> None:
        self.body.setFixedWidth(CARD_WIDTH - 2 * SPACING.lg - 8)
        # isHidden statt isVisible: vor dem ersten show() ist nichts „sichtbar“, die Höhe muss trotzdem stimmen
        body_height = self.body.heightForWidth(self.body.width()) if not self.scroll.isHidden() else 0
        self.scroll.setFixedHeight(min(BODY_MAX, max(0, body_height)) if not self.scroll.isHidden() else 0)
        self.card.adjustSize()
        wanted = self.card.sizeHint().height()
        self._place(wanted)

    def _place(self, height: int) -> None:
        screen = QGuiApplication.screenAt(self.anchor.center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        window = self.parentWidget().window().frameGeometry() if self.parentWidget() else available
        bounds = window.intersected(available)
        if bounds.width() < CARD_WIDTH + 16 or bounds.height() < 200:
            bounds = available
        x, y, h = lk.place_card((self.anchor.x(), self.anchor.y(), self.anchor.width(), self.anchor.height()),
                                (CARD_WIDTH, height), (bounds.x(), bounds.y(), bounds.width(), bounds.height()))
        if h < height:   # gekürzt: der Textbereich gibt nach
            self.scroll.setFixedHeight(max(40, self.scroll.height() - (height - h)))
        self.setGeometry(x, y, CARD_WIDTH, h)

    def _fade_in(self) -> None:
        if not self.isVisible():
            self.setWindowOpacity(0.0 if anim.duration(DURATION.fade) else 1.0)
            self.show()
            if anim.duration(DURATION.fade):
                anim.animate(self, 0.0, 1.0, int(DURATION.fade * 1.5), self.setWindowOpacity)
        self.raise_()
        self.activateWindow()

    # ---- Klicks ------------------------------------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if isinstance(watched, QLabel) and self._hovered.get(id(watched)):
                return False               # Klick auf einen Link: der Label meldet linkActivated
            if self._browser_url:
                self._open_browser(self._browser_url)
                return True
        return super().eventFilter(watched, event)

    def _on_link(self, link: str) -> None:
        if link.startswith("switch:"):
            self._expanded = False
            self._load(link.split(":", 1)[1], self.term)
        elif link == "web":
            engine = self.config.get("lookup", {}).get("engine", "google")
            self._open_browser(lk.search_url(self.term, engine, self.config.get("lookup", {}).get("custom_url", "")))
        elif link.startswith("article:"):
            title = html.unescape(link.split(":", 1)[1])
            lang = self._result.lang if self._result is not None else self.langs[0]
            self.langs = [lang] + [l for l in self.langs if l != lang]
            self._load("wikipedia", title, article=True)
        elif link == "more" and isinstance(self._result, lk.Definition):
            self._expanded = True
            self.body.setText(self._definition_html(self._result))
            self._fit()

    def _open_browser(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url, QUrl.ParsingMode.StrictMode) if "%" in url else QUrl(url))
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._generation += 1      # laufende Abrufe verwerfen, ihre Ergebnisse landen im Cache
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._generation += 1
        for worker in list(self._workers):
            worker.wait(5500)
