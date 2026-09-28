"""Formatierte (WYSIWYG-)Bearbeitung von Markdown: fett wird als fett gezeigt, keine Sternchen im Blick.

Baut das Qt-freie Blockmodell (core/richmd) in ein QTextDocument und liest es wieder aus. Eine Symbolleiste und
Tastenkürzel formatieren; ein Umschalter „Formatiert | Quelltext (Markdown)" zeigt bei Bedarf die rohe Syntax.
Variablen (§name) und Platzhalter bleiben in beiden Ansichten Text und werden nicht zerstört.

Tabellen und Codeblöcke werden formatiert angezeigt; für Feinarbeit an ihnen ist die Quelltext-Ansicht gedacht.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (QColor, QFont, QKeySequence, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextFormat,
                           QTextListFormat, QTextTableFormat, QAction)
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QPushButton, QStackedWidget, QTextEdit, QToolButton,
                               QVBoxLayout, QWidget)

from notex.core import richmd
from notex.theme.icons import icon
from notex.theme.tokens import COLORS, SPACING

BLOCK_TYPE = QTextFormat.Property.UserProperty + 1
BLOCK_LEVEL = QTextFormat.Property.UserProperty + 2
BLOCK_ORDERED = QTextFormat.Property.UserProperty + 3
BLOCK_CHECK = QTextFormat.Property.UserProperty + 4
CODE_INFO = QTextFormat.Property.UserProperty + 5

MONO = "JetBrains Mono"


class RichMarkdownEditor(QWidget):
    """Formatierte Markdown-Bearbeitung mit Symbolleiste und Quelltext-Umschalter."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)

        self.toolbar = QHBoxLayout()
        self.toolbar.setContentsMargins(SPACING.sm, SPACING.xs, SPACING.sm, 0)
        self._build_toolbar()
        layout.addLayout(self.toolbar)

        self.stack = QStackedWidget()
        self.rich = QTextEdit()
        self.rich.setAcceptRichText(False)
        self.rich.setObjectName("RichEditor")
        self.rich.textChanged.connect(self.changed)
        self.source = QPlainTextEdit()
        self.source.setObjectName("SourceEditor")
        font = QFont(MONO)
        self.source.setFont(font)
        self.source.textChanged.connect(self.changed)
        self.stack.addWidget(self.rich)
        self.stack.addWidget(self.source)
        layout.addWidget(self.stack, 1)

        self._install_shortcuts()

    # ---- Symbolleiste ---------------------------------------------------------------------------
    def _tool(self, icon_name: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon(icon_name))
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(slot)
        self.toolbar.addWidget(button)
        return button

    def _build_toolbar(self) -> None:
        self._tool("bold", "Fett  (Ctrl+B)", lambda: self._toggle_inline("bold"))
        self._tool("italic", "Kursiv  (Ctrl+I)", lambda: self._toggle_inline("italic"))
        self._tool("strikethrough" if _has_icon("strikethrough") else "eraser", "Durchgestrichen",
                   lambda: self._toggle_inline("strike"))
        self._tool("code", "Inline-Code", lambda: self._toggle_inline("code"))
        self._tool("heading", "Überschrift H2  (Ctrl+2)", lambda: self._set_heading(2))
        self._tool("list", "Aufzählung", lambda: self._make_list(False))
        self._tool("list-checks" if _has_icon("list-checks") else "list", "Nummerierte Liste",
                   lambda: self._make_list(True))
        self._tool("list-todo" if _has_icon("list-todo") else "square-check", "Aufgabe (Checkbox)",
                   lambda: self._make_task())
        self._tool("quote", "Zitat", lambda: self._set_block("quote"))
        self._tool("minus", "Trennlinie", self._insert_hr)
        self._tool("link", "Link einfügen", self._insert_link)
        self.toolbar.addStretch(1)
        self.toggle_button = QPushButton("Quelltext")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_button.toggled.connect(self._toggle_source)
        self.toolbar.addWidget(self.toggle_button)

    def _install_shortcuts(self) -> None:
        for key, slot in (("Ctrl+B", lambda: self._toggle_inline("bold")),
                          ("Ctrl+I", lambda: self._toggle_inline("italic")),
                          ("Ctrl+1", lambda: self._set_heading(1)),
                          ("Ctrl+2", lambda: self._set_heading(2)),
                          ("Ctrl+3", lambda: self._set_heading(3)),
                          ("Ctrl+0", lambda: self._set_block("para"))):
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(slot)
            self.addAction(action)

    # ---- Laden / Speichern ----------------------------------------------------------------------
    def set_markdown(self, md: str) -> None:
        self._build(richmd.parse(md))
        self.source.blockSignals(True)
        self.source.setPlainText(md)
        self.source.blockSignals(False)

    def to_markdown(self) -> str:
        if self.stack.currentIndex() == 1:               # Quelltext-Ansicht ist maßgeblich
            return self.source.toPlainText()
        return richmd.to_markdown(self._read())

    # ---- Umschalter -----------------------------------------------------------------------------
    def _toggle_source(self, on: bool) -> None:
        if on:
            self.source.blockSignals(True)
            self.source.setPlainText(richmd.to_markdown(self._read()))
            self.source.blockSignals(False)
            self.stack.setCurrentIndex(1)
            self.toggle_button.setText("Formatiert")
        else:
            self._build(richmd.parse(self.source.toPlainText()))
            self.stack.setCurrentIndex(0)
            self.toggle_button.setText("Quelltext")

    # ---- Aufbau QTextDocument aus dem Modell -----------------------------------------------------
    def _build(self, doc: richmd.Document) -> None:
        self.rich.blockSignals(True)
        qdoc = self.rich.document()
        qdoc.clear()
        cursor = QTextCursor(qdoc)
        first = True
        for block in doc.blocks:
            if block.type == "table":
                self._insert_table(cursor, block, first)
                first = False
                continue
            if not first:
                cursor.insertBlock()
            first = False
            self._apply_block(cursor, block)
            if block.type == "code":
                lines = block.text.split("\n")
                for idx, line in enumerate(lines):
                    if idx:
                        cursor.insertBlock(cursor.blockFormat(), cursor.charFormat())
                    cursor.insertText(line, _mono_format())
            elif block.type == "hr":
                cursor.insertText("─" * 24)
            else:
                self._insert_runs(cursor, block.runs)
        self.rich.moveCursor(QTextCursor.MoveOperation.Start)
        self.rich.blockSignals(False)

    def _apply_block(self, cursor: QTextCursor, block: richmd.Block) -> None:
        fmt = QTextBlockFormat()
        fmt.setProperty(BLOCK_TYPE, block.type)
        if block.type == "heading":
            fmt.setProperty(BLOCK_LEVEL, block.level)
            fmt.setHeadingLevel(block.level)
        elif block.type == "li":
            fmt.setProperty(BLOCK_LEVEL, block.level)
            fmt.setProperty(BLOCK_ORDERED, block.ordered)
            if block.checked is not None:
                fmt.setProperty(BLOCK_CHECK, block.checked)
            fmt.setIndent(block.level + 1)
        elif block.type == "quote":
            fmt.setIndent(1)
        elif block.type == "code":
            fmt.setProperty(CODE_INFO, block.info)
            fmt.setNonBreakableLines(True)
        cursor.setBlockFormat(fmt)
        if block.type == "li":
            style = QTextListFormat.Style.ListDecimal if block.ordered else QTextListFormat.Style.ListDisc
            list_fmt = QTextListFormat()
            list_fmt.setStyle(style)
            list_fmt.setIndent(block.level + 1)
            cursor.createList(list_fmt)
            if block.checked is not None:
                cursor.insertText("☑ " if block.checked else "☐ ")

    def _insert_runs(self, cursor: QTextCursor, runs) -> None:
        for run in runs:
            cursor.insertText(run.text, _run_format(run))

    def _insert_table(self, cursor: QTextCursor, block: richmd.Block, first: bool) -> None:
        if not first:
            cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())   # sauberer Absatz, keine geerbte Formatierung
        cols = max(len(block.header), 1)
        rows = 1 + len(block.rows)
        table_fmt = QTextTableFormat()
        table_fmt.setCellPadding(4)
        table_fmt.setCellSpacing(0)
        table_fmt.setBorder(1)
        table = cursor.insertTable(rows, cols, table_fmt)
        table.blockFormat = None  # kein Effekt, nur Klarheit
        for col, head in enumerate(block.header):
            c = table.cellAt(0, col).firstCursorPosition()
            bold = [richmd.Run(r.text, True, r.italic, r.strike, r.code, r.link) for r in head]
            self._insert_runs(c, bold)
        for r, row in enumerate(block.rows, start=1):
            for col, cell in enumerate(row):
                if col < cols:
                    self._insert_runs(table.cellAt(r, col).firstCursorPosition(), cell)
        cursor.movePosition(QTextCursor.MoveOperation.End)

    # ---- Auslesen QTextDocument → Modell ---------------------------------------------------------
    def _read(self) -> richmd.Document:
        doc = richmd.Document()
        qdoc = self.rich.document()
        frame = qdoc.rootFrame()
        it = frame.begin()
        pending_code: list[str] = []
        code_info = ""
        while not it.atEnd():
            child = it.currentFrame()
            block = it.currentBlock()
            if _is_table(child):
                self._flush_code(doc, pending_code, code_info); pending_code = []; code_info = ""
                doc.blocks.append(_read_table(child))
                it += 1
                continue
            if block.isValid():
                btype = block.blockFormat().property(BLOCK_TYPE) or "para"
                if btype == "code":
                    pending_code.append(block.text())
                    code_info = block.blockFormat().property(CODE_INFO) or code_info
                    it += 1
                    continue
                self._flush_code(doc, pending_code, code_info); pending_code = []; code_info = ""
                doc.blocks.append(self._read_block(block, btype))
            it += 1
        self._flush_code(doc, pending_code, code_info)
        # Leere Zitat-/Absatz-Blöcke entfernen (entstehen an Tabellen-/Blockgrenzen)
        doc.blocks = [b for b in doc.blocks if not (b.type == "quote" and not _has_text(b.runs))]
        while doc.blocks and doc.blocks[-1].type == "para" and not _has_text(doc.blocks[-1].runs):
            doc.blocks.pop()
        return doc

    @staticmethod
    def _flush_code(doc, lines, info) -> None:
        if lines:
            doc.blocks.append(richmd.Block("code", text="\n".join(lines), info=info or ""))

    def _read_block(self, block, btype) -> richmd.Block:
        text = block.text()
        if btype == "hr" or set(text.strip()) == {"─"} and text.strip():
            return richmd.Block("hr")
        runs = _read_runs(block)
        fmt = block.blockFormat()
        if btype == "heading":
            return richmd.Block("heading", runs=runs, level=int(fmt.property(BLOCK_LEVEL) or fmt.headingLevel() or 1))
        if btype == "li" or block.textList() is not None:
            checked = fmt.property(BLOCK_CHECK)
            ordered = bool(fmt.property(BLOCK_ORDERED))
            level = int(fmt.property(BLOCK_LEVEL) or 0)
            runs = _strip_checkbox(runs) if checked is not None else runs
            # Falls Checkbox-Zeichen ohne gesetztes Property (vom Nutzer getippt)
            if checked is None:
                checked, runs = _detect_checkbox(runs)
            return richmd.Block("li", runs=runs, level=level, ordered=ordered, checked=checked)
        if btype == "quote":
            return richmd.Block("quote", runs=runs)
        return richmd.Block("para", runs=runs)

    # ---- Formatier-Aktionen ---------------------------------------------------------------------
    def _toggle_inline(self, kind: str) -> None:
        cursor = self.rich.textCursor()
        fmt = QTextCharFormat()
        current = cursor.charFormat()
        if kind == "bold":
            fmt.setFontWeight(QFont.Weight.Normal if current.fontWeight() > QFont.Weight.Normal
                              else QFont.Weight.Bold)
        elif kind == "italic":
            fmt.setFontItalic(not current.fontItalic())
        elif kind == "strike":
            fmt.setFontStrikeOut(not current.fontStrikeOut())
        elif kind == "code":
            mono = current.fontFamilies() and MONO in current.fontFamilies()
            fmt.setFontFamilies([] if mono else [MONO])
            fmt.setFontFixedPitch(not mono)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.rich.mergeCurrentCharFormat(fmt)
        self.rich.setFocus()

    def _set_heading(self, level: int) -> None:
        cursor = self.rich.textCursor()
        fmt = cursor.blockFormat()
        current = fmt.property(BLOCK_TYPE)
        if current == "heading" and int(fmt.property(BLOCK_LEVEL) or 0) == level:
            self._set_block("para")
            return
        fmt.setProperty(BLOCK_TYPE, "heading")
        fmt.setProperty(BLOCK_LEVEL, level)
        fmt.setHeadingLevel(level)
        cursor.setBlockFormat(fmt)
        char = QTextCharFormat()
        char.setFontWeight(QFont.Weight.Bold)
        char.setFontPointSize(18 - 2 * level)
        block_cursor = QTextCursor(cursor.block())
        block_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        block_cursor.mergeCharFormat(char)
        self.rich.setFocus()

    def _set_block(self, btype: str) -> None:
        cursor = self.rich.textCursor()
        fmt = QTextBlockFormat()
        fmt.setProperty(BLOCK_TYPE, btype)
        if btype == "quote":
            fmt.setIndent(1)
        cursor.setBlockFormat(fmt)
        self.rich.setFocus()

    def _make_list(self, ordered: bool) -> None:
        cursor = self.rich.textCursor()
        fmt = cursor.blockFormat()
        fmt.setProperty(BLOCK_TYPE, "li")
        fmt.setProperty(BLOCK_ORDERED, ordered)
        cursor.setBlockFormat(fmt)
        list_fmt = QTextListFormat()
        list_fmt.setStyle(QTextListFormat.Style.ListDecimal if ordered else QTextListFormat.Style.ListDisc)
        cursor.createList(list_fmt)
        self.rich.setFocus()

    def _make_task(self) -> None:
        cursor = self.rich.textCursor()
        fmt = cursor.blockFormat()
        fmt.setProperty(BLOCK_TYPE, "li")
        fmt.setProperty(BLOCK_ORDERED, False)
        fmt.setProperty(BLOCK_CHECK, False)
        cursor.setBlockFormat(fmt)
        list_fmt = QTextListFormat()
        list_fmt.setStyle(QTextListFormat.Style.ListDisc)
        cursor.createList(list_fmt)
        cursor.insertText("☐ ")
        self.rich.setFocus()

    def _insert_hr(self) -> None:
        cursor = self.rich.textCursor()
        cursor.insertBlock()
        fmt = QTextBlockFormat()
        fmt.setProperty(BLOCK_TYPE, "hr")
        cursor.setBlockFormat(fmt)
        cursor.insertText("─" * 24)
        cursor.insertBlock(QTextBlockFormat())
        self.rich.setFocus()

    def _insert_link(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "Link", "Adresse (URL):")
        if not ok or not url.strip():
            return
        cursor = self.rich.textCursor()
        text = cursor.selectedText() or url.strip()
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url.strip())
        fmt.setForeground(QColor(COLORS.accent) if hasattr(COLORS, "accent") else Qt.GlobalColor.blue)
        cursor.insertText(text, fmt)
        self.rich.setFocus()


# ---- Hilfen (Format ↔ Run) ------------------------------------------------------------------------

class RichMarkdownDialog(QWidget):
    """Eigenständiges Fenster, um eine Markdown-Datei formatiert zu bearbeiten und zu speichern."""

    def __init__(self, window, path) -> None:
        super().__init__(window, Qt.WindowType.Window)
        from pathlib import Path
        self.window_ = window
        self.path = Path(path)
        self.setWindowTitle(f"Formatiert bearbeiten – {self.path.name}")
        self.resize(860, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        self.editor = RichMarkdownEditor(self)
        try:
            self.editor.set_markdown(self.path.read_text(encoding="utf-8"))
        except OSError:
            self.editor.set_markdown("")
        layout.addWidget(self.editor, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        save = QPushButton("Speichern")
        save.clicked.connect(self._save)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        footer.addWidget(save)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _save(self) -> None:
        try:
            self.path.write_text(self.editor.to_markdown(), encoding="utf-8")
            self.window_.toast.show_message(f"Gespeichert · {self.path.name}", "check")
        except OSError as error:
            from notex.ui import dialogs
            dialogs.warn(self, "Speichern", str(error))


def _has_text(runs) -> bool:
    return any(r.text.strip() for r in runs)


def _run_format(run: richmd.Run) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if run.bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if run.italic:
        fmt.setFontItalic(True)
    if run.strike:
        fmt.setFontStrikeOut(True)
    if run.code:
        fmt.setFontFamilies([MONO])
        fmt.setFontFixedPitch(True)
    if run.link:
        fmt.setAnchor(True)
        fmt.setAnchorHref(run.link)
    return fmt


def _mono_format() -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setFontFamilies([MONO])
    fmt.setFontFixedPitch(True)
    return fmt


def _read_runs(block) -> list:
    runs = []
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        if fragment.isValid():
            fmt = fragment.charFormat()
            mono = bool(fmt.fontFixedPitch()) or (fmt.fontFamilies() and MONO in fmt.fontFamilies())
            runs.append(richmd.Run(
                fragment.text(),
                bold=fmt.fontWeight() > QFont.Weight.Normal,
                italic=fmt.fontItalic(),
                strike=fmt.fontStrikeOut(),
                code=bool(mono),
                link=fmt.anchorHref() or ""))
        it += 1
    return richmd._merge(runs)


def _strip_checkbox(runs):
    if runs and runs[0].text[:2] in ("☑ ", "☐ "):
        first = runs[0]
        runs = [richmd.Run(first.text[2:], first.bold, first.italic, first.strike, first.code, first.link)] + runs[1:]
    return [r for r in runs if r.text]


def _detect_checkbox(runs):
    if runs and runs[0].text[:1] in ("☑", "☐"):
        checked = runs[0].text[0] == "☑"
        rest = runs[0].text[1:].lstrip()
        runs = [richmd.Run(rest, runs[0].bold, runs[0].italic, runs[0].strike, runs[0].code, runs[0].link)] + runs[1:]
        return checked, [r for r in runs if r.text]
    return None, runs


def _is_table(frame) -> bool:
    from PySide6.QtGui import QTextTable
    return isinstance(frame, QTextTable)


def _read_table(table) -> richmd.Block:
    block = richmd.Block("table")
    cols = table.columns()
    for col in range(cols):
        block.header.append(_cell_runs(table, 0, col))
        block.aligns.append("")
    for r in range(1, table.rows()):
        block.rows.append([_cell_runs(table, r, col) for col in range(cols)])
    return block


def _cell_runs(table, r, col) -> list:
    cell = table.cellAt(r, col)
    runs = []
    it = cell.begin()
    while not it.atEnd():
        b = it.currentBlock()
        if b.isValid():
            runs.extend(_read_runs(b))
        it += 1
    # Kopf-Fettung nicht ins Markdown übernehmen
    return [richmd.Run(x.text, False, x.italic, x.strike, x.code, x.link) if r == 0 else x for x in runs]


def _has_icon(name: str) -> bool:
    import notex
    from pathlib import Path
    return (Path(notex.__file__).resolve().parent / "assets" / "icons" / f"{name}.svg").exists()
