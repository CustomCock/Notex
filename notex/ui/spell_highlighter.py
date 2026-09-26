"""Markiert Rechtschreib- und Grammatikfehler im Editor (rote bzw. blaue Wellenlinie).

Leistung:
- QSyntaxHighlighter prüft von sich aus nur geänderte Blöcke neu.
- Beim Öffnen großer Dateien würde Qt trotzdem alle Blöcke durchlaufen. Deshalb prüft
  der Highlighter nur Blöcke im sichtbaren Bereich (plus Puffer); beim Scrollen werden
  die neu sichtbaren nachgeholt (kurz verzögert).
- Das Wort, das gerade getippt wird, bleibt bis zu einer Tipp-Pause unmarkiert.
- Jedes Wort wird pro Sprache nur einmal nachgeschlagen (Cache im SpellChecker).

Grammatik-Treffer kommen asynchron vom LanguageTool-Client und werden pro Block
gespeichert; beim nächsten Zeichnen des Blocks legt der Highlighter sie mit an.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextBlock, QTextBlockUserData, QTextCharFormat, QTextDocument

from notex.core.spell import SpellChecker
from notex.core.spell_rules import is_code_fence, tokenize
from notex.core.wikilinks import links_in_line
from notex.core import syntax
from notex.theme import tokens
from notex.theme.tokens import COLORS

STATE_NORMAL, STATE_IN_FENCE = 0, 1   # STATE_IN_FENCE nur ohne Syntax-Lexer; sonst tragen die Syntax-Zustände den Fence
TYPING_PAUSE_MS = 400
SCROLL_CHECK_MS = 120
VISIBLE_BUFFER = 20     # Blöcke über/unter dem sichtbaren Bereich mitprüfen


@dataclass
class Issue:
    start: int
    length: int
    kind: str                     # "spelling" | "grammar"
    word: str = ""
    message: str = ""
    replacements: list[str] = field(default_factory=list)
    rule: str = ""


@dataclass
class LinkSpan:
    start: int
    end: int
    target: str
    heading: str | None
    resolved: str | None      # relativer Pfad der Zieldatei oder None (kaputter Link)


class BlockIssues(QTextBlockUserData):
    """Hängt an jedem geprüften Block: die gefundenen Probleme und Links, für Kontextmenü und Ctrl+Klick."""

    def __init__(self) -> None:
        super().__init__()
        self.issues: list[Issue] = []
        self.links: list[LinkSpan] = []
        self.checked = False


class SpellHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument, editor, checker: SpellChecker, markdown: bool) -> None:
        super().__init__(document)
        self.editor = editor
        self.checker = checker
        self.markdown = markdown
        self.spelling_enabled = False
        self.grammar_enabled = False
        self.language: str | None = None          # None = globale Sprache des Checkers
        self.resolve_link = None                  # Callable[[str], str | None] – setzt das Hauptfenster
        self.links_enabled = True
        self.lexer: str | None = None             # Pygments-Lexername oder None (kein Syntax-Highlighting)
        self._grammar: dict[int, list[Issue]] = {}  # Blocknummer -> Grammatik-Treffer
        self._full_pass = False

        # Tipp-Pause: das aktuelle Wort erst prüfen, wenn kurz nichts mehr kommt
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(TYPING_PAUSE_MS)
        self._typing_timer.timeout.connect(self._recheck_cursor_block)
        self._typing = False
        # Beim Scrollen die neu sichtbaren Blöcke nachprüfen
        self._reset_timer = QTimer(self)          # Laden + Resolver setzen → nur EIN Durchlauf
        self._reset_timer.setSingleShot(True)
        self._reset_timer.setInterval(0)
        self._reset_timer.timeout.connect(self.reset)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(SCROLL_CHECK_MS)
        self._scroll_timer.timeout.connect(self.check_visible)
        self.views = [editor]                      # alle Editoren, die dieses Dokument zeigen (geteilter Editor)
        editor.verticalScrollBar().valueChanged.connect(lambda _v: self._scroll_timer.start())
        document.contentsChange.connect(self._on_contents_change)

    def add_view(self, editor) -> None:
        if editor not in self.views:
            self.views.append(editor)
            editor.verticalScrollBar().valueChanged.connect(lambda _v: self._scroll_timer.start())
            self._scroll_timer.start()

    def remove_view(self, editor) -> None:
        if editor in self.views and len(self.views) > 1:
            self.views.remove(editor)
            if self.editor is editor:
                self.editor = self.views[0]

    # ---- Steuerung -----------------------------------------------------------------
    def set_enabled(self, spelling: bool, grammar: bool) -> None:
        changed = (spelling, grammar) != (self.spelling_enabled, self.grammar_enabled)
        self.spelling_enabled, self.grammar_enabled = spelling, grammar
        if not grammar:
            self._grammar.clear()
        if changed:
            self.reset()

    def set_language(self, language: str | None) -> None:
        self.language = language
        self.reset()

    def schedule_reset(self) -> None:
        """reset() im nächsten Durchlauf der Ereignisschleife – mehrere Aufrufe ergeben einen Durchlauf."""
        self._reset_timer.start()

    def reset(self) -> None:
        """Alle Markierungen verwerfen und den sichtbaren Bereich neu prüfen."""
        self._reset_timer.stop()
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if isinstance(data, BlockIssues):
                data.checked = False
            block = block.next()
        self._full_pass = True     # Links und Syntax gelten für die ganze Datei, Rechtschreibung nur sichtbar
        self.rehighlight()
        self._full_pass = False
        if self.spelling_enabled or self.grammar_enabled:
            self.check_visible()

    def relink(self) -> None:
        """Nach Änderungen am Dateiindex: Links neu auflösen (nur der Link-Zustand ändert sich)."""
        self.reset()

    def mark_loaded(self) -> None:
        """Nach dem Laden einer Datei: das ist kein Tippen, also sofort alles prüfen."""
        self._typing_timer.stop()
        self._typing = False
        self._grammar.clear()
        self.schedule_reset()     # beim Öffnen folgen Resolver/Lexer noch – zusammen ein Durchlauf

    def set_grammar_issues(self, block_number: int, issues: list[Issue]) -> None:
        self._grammar[block_number] = issues
        block = self.document().findBlockByNumber(block_number)
        if block.isValid():
            self.rehighlightBlock(block)

    def clear_grammar(self) -> None:
        self._grammar.clear()
        self.reset()

    def link_at(self, block: QTextBlock, position_in_block: int) -> LinkSpan | None:
        data = block.userData()
        if not isinstance(data, BlockIssues):
            return None
        for span in data.links:
            if span.start <= position_in_block < span.end:
                return span
        return None

    def issues_at(self, block: QTextBlock, position_in_block: int) -> list[Issue]:
        data = block.userData()
        if not isinstance(data, BlockIssues):
            return []
        return [i for i in data.issues if i.start <= position_in_block <= i.start + i.length]

    # ---- Sichtbarer Bereich ----------------------------------------------------------
    def visible_block_range(self) -> tuple[int, int]:
        return self._range_of(self.editor)

    @staticmethod
    def _range_of(editor) -> tuple[int, int]:
        viewport = editor.viewport()
        first = editor.cursorForPosition(viewport.rect().topLeft()).blockNumber()
        last = editor.cursorForPosition(viewport.rect().bottomLeft()).blockNumber()
        return max(0, first - VISIBLE_BUFFER), last + VISIBLE_BUFFER

    def visible_ranges(self) -> list[tuple[int, int]]:
        """Sichtbare Bereiche aller Ansichten (geteilter Editor zeigt dasselbe Dokument zweimal)."""
        return [self._range_of(view) for view in self.views if view.isVisible()] or [self._range_of(self.editor)]

    def check_visible(self) -> None:
        if not (self.spelling_enabled or self.grammar_enabled):
            return
        for first, last in self.visible_ranges():
            block = self.document().findBlockByNumber(first)
            while block.isValid() and block.blockNumber() <= last:
                data = block.userData()
                if not (isinstance(data, BlockIssues) and data.checked):
                    self.rehighlightBlock(block)
                block = block.next()

    def _in_visible_range(self, block: QTextBlock) -> bool:
        number = block.blockNumber()
        return any(first <= number <= last for first, last in self.visible_ranges())

    # ---- Tippen -----------------------------------------------------------------------
    def _on_contents_change(self, position: int, removed: int, added: int) -> None:
        self._typing = True
        self._typing_timer.start()
        # Grammatik-Treffer des geänderten Blocks sind jetzt veraltet
        block = self.document().findBlock(position)
        if block.isValid():
            self._grammar.pop(block.blockNumber(), None)

    def _recheck_cursor_block(self) -> None:
        self._typing = False
        block = self.editor.textCursor().block()
        if block.isValid() and (self.spelling_enabled or self.grammar_enabled):
            self.rehighlightBlock(block)

    # ---- Das eigentliche Prüfen -------------------------------------------------------
    def in_code_fence(self, block: QTextBlock) -> bool:
        state = block.userState()
        return self.markdown and (state == STATE_IN_FENCE or state >= syntax.STATE_FENCE or is_code_fence(block.text()))

    suspended = False      # während Editor.load(): der Durchlauf nach dem Laden (reset) färbt alles

    def highlightBlock(self, text: str) -> None:
        if self.suspended:
            return
        service = getattr(self.editor, "variables", None)
        self._variable_spans = [(t.start, t.end) for t in service.tokens(text)] if service is not None else []
        self._highlight(text)
        if service is not None and self._variable_spans:
            # Letzte Ebene: Tokens unsichtbar mit der Breite des Werts (den zeichnet der Editor), Escapes ohne Backslash
            from notex.ui.variable_render import token_formats
            for start, length, fmt in token_formats(service, self.editor.font(), text):
                self.setFormat(start, length, fmt)

    _variable_spans: list = []

    def _highlight(self, text: str) -> None:
        block = self.currentBlock()
        previous_state = max(0, self.previousBlockState())
        if self.lexer is not None:
            # Syntax zuerst: Farben als Grundformat, danach Links und Wellenlinien obendrauf
            spans, state = syntax.lex_line(text, self.lexer, previous_state)
            for span in spans:
                color = tokens.SYNTAX.get(span.style)
                if color:
                    fmt = QTextCharFormat()
                    fmt.setForeground(QColor(color))
                    self.setFormat(span.start, span.end - span.start, fmt)
            self.setCurrentBlockState(state)
            in_fence = self.markdown and (state >= syntax.STATE_FENCE or previous_state >= syntax.STATE_FENCE)
            if self.markdown and is_code_fence(text):
                self._store(block, [])
                return
        else:
            in_fence = previous_state == STATE_IN_FENCE
            if self.markdown and is_code_fence(text):
                in_fence = not in_fence
                self.setCurrentBlockState(STATE_IN_FENCE if in_fence else STATE_NORMAL)
                self._store(block, [])
                return
            self.setCurrentBlockState(STATE_IN_FENCE if in_fence else STATE_NORMAL)

        links = self._link_spans(text, in_fence) if self.links_enabled else []
        self._paint_links(links)
        if not (self.spelling_enabled or self.grammar_enabled):
            self._store(block, [], links)
            return
        if not self._in_visible_range(block):
            self._store_links(block, links)
            return   # Rechtschreibung später, wenn der Block sichtbar wird

        issues: list[Issue] = []
        if self.spelling_enabled and not (self.markdown and in_fence):
            issues.extend(self._spell_issues(block, text))
        if self.grammar_enabled:
            issues.extend(self._grammar.get(block.blockNumber(), []))

        spell_format = QTextCharFormat()
        spell_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        spell_format.setUnderlineColor(QColor(COLORS.spell_underline))
        grammar_format = QTextCharFormat()
        grammar_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        grammar_format.setUnderlineColor(QColor(COLORS.grammar_underline))
        for issue in issues:
            # Vorhandenes Format (z. B. Link-Farbe) behalten, nur die Wellenlinie ergänzen
            base = spell_format if issue.kind == "spelling" else grammar_format
            for pos in range(issue.start, issue.start + issue.length):
                merged = QTextCharFormat(self.format(pos))
                merged.setUnderlineStyle(base.underlineStyle())
                merged.setUnderlineColor(base.underlineColor())
                self.setFormat(pos, 1, merged)
        self._store(block, issues, links)

    def _link_spans(self, text: str, in_fence: bool) -> list[LinkSpan]:
        spans = []
        for link in links_in_line(text, in_fence):
            resolved = self.resolve_link(link.target) if self.resolve_link else None
            spans.append(LinkSpan(link.start, link.end, link.target, link.heading, resolved))
        return spans

    def _paint_links(self, links: list[LinkSpan]) -> None:
        for span in links:
            fmt = QTextCharFormat()
            if span.resolved:
                fmt.setForeground(QColor(COLORS.accent))
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
                fmt.setUnderlineColor(QColor(COLORS.accent))
            else:
                fmt.setForeground(QColor(COLORS.paper_muted))
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)
                fmt.setUnderlineColor(QColor(COLORS.paper_muted))
            self.setFormat(span.start, span.end - span.start, fmt)

    def _store_links(self, block: QTextBlock, links: list[LinkSpan]) -> None:
        data = block.userData()
        if not isinstance(data, BlockIssues):
            data = BlockIssues()
            self.setCurrentBlockUserData(data)
        data.links = links

    def _spell_issues(self, block: QTextBlock, text: str) -> list[Issue]:
        # Das Wort unter dem Cursor auslassen, solange getippt wird
        cursor = self.editor.textCursor()
        skip_at = cursor.positionInBlock() if (self._typing and cursor.block() == block) else -1
        issues = []
        for token in tokenize(text, self.markdown):
            if skip_at >= 0 and token.start <= skip_at <= token.end:
                continue
            if any(start <= token.start < end or start < token.end <= end for start, end in self._variable_spans):
                continue                    # Variablen-Tokens (und ihre Namen) nie als Rechtschreibfehler
            if not self.checker.is_correct(token.text, self.language):
                issues.append(Issue(token.start, token.end - token.start, "spelling", word=token.text))
        return issues

    def _store(self, block: QTextBlock, issues: list[Issue], links: list[LinkSpan] | None = None) -> None:
        data = block.userData()
        if not isinstance(data, BlockIssues):
            data = BlockIssues()
            self.setCurrentBlockUserData(data)
        data.issues = issues
        if links is not None:
            data.links = links
        data.checked = True
