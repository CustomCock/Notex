"""Trefferliste, die den Baum ersetzt, solange im Suchfeld etwas steht."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette, QTextDocument
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem

from textbaum.core.search import FileMatch, LineMatch, NameMatch
from textbaum.theme.icons import file_icon
from textbaum.theme.theme import COLORS

ROLE_PATH = Qt.ItemDataRole.UserRole + 1
ROLE_LINE = Qt.ItemDataRole.UserRole + 2     # (line_no, column, length) oder None


def _highlight(text: str, start: int, end: int) -> str:
    """Escaped Text mit hervorgehobenem Bereich – als kleines HTML-Fragment."""
    return (
        html.escape(text[:start])
        + f'<span style="background:{COLORS["selection"]}; color:{COLORS["text"]}; font-weight:bold">'
        + html.escape(text[start:end])
        + "</span>"
        + html.escape(text[end:])
    )


def _muted(text: str) -> str:
    return f'<span style="color:{COLORS["text_muted"]}">{html.escape(text)}</span>'


class HtmlDelegate(QStyledItemDelegate):
    """Zeichnet den Item-Text als HTML, damit Treffer hervorgehoben werden können."""

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else None
        text, opt.text = opt.text, ""
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setDocumentMargin(2)
        doc.setHtml(text)
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget) if style else opt.rect
        painter.save()
        painter.translate(text_rect.topLeft())
        painter.setClipRect(text_rect.translated(-text_rect.topLeft()))
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.ColorRole.Text, opt.palette.color(QPalette.ColorRole.Text))
        doc.documentLayout().draw(painter, context)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setDocumentMargin(2)
        doc.setHtml(opt.text)
        return QSize(int(doc.idealWidth()), int(doc.size().height()))


class SearchResults(QTreeWidget):
    open_requested = Signal(Path, object)   # Pfad, (line, column, length) oder None

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setItemDelegate(HtmlDelegate(self))
        self.setRootIsDecorated(True)
        self.itemClicked.connect(self._on_item_clicked)
        self.itemActivated.connect(self._on_item_clicked)
        self._name_header: QTreeWidgetItem | None = None
        self._text_header: QTreeWidgetItem | None = None

    def clear_results(self) -> None:
        self.clear()
        self._name_header = self._text_header = None

    def _header(self, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([_muted(title)])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # nicht anklickbar
        self.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    def add_name_match(self, match: NameMatch, with_headers: bool) -> None:
        if with_headers and self._name_header is None:
            self._name_header = self._header("Dateinamen")
        folder = match.relative.rsplit("/", 1)[0] + "/" if "/" in match.relative else ""
        item = QTreeWidgetItem([_highlight(match.path.name, match.start, match.end) + "  " + _muted(folder)])
        item.setIcon(0, file_icon())
        item.setData(0, ROLE_PATH, str(match.path))
        item.setData(0, ROLE_LINE, None)
        item.setToolTip(0, match.relative)
        (self._name_header or self.invisibleRootItem()).addChild(item)

    def add_file_match(self, match: FileMatch, with_headers: bool) -> None:
        if with_headers and self._text_header is None:
            self._text_header = self._header("Volltext")
        parent = QTreeWidgetItem([html.escape(match.relative) + "  " + _muted(f"({len(match.lines)})")])
        parent.setIcon(0, file_icon())
        parent.setData(0, ROLE_PATH, str(match.path))
        parent.setData(0, ROLE_LINE, None)
        for line in match.lines:
            child = QTreeWidgetItem([_muted(f"{line.line_no}:") + "  " + _highlight(line.snippet, line.start, line.end)])
            child.setData(0, ROLE_PATH, str(match.path))
            child.setData(0, ROLE_LINE, (line.line_no, line.column, line.length))
            child.setToolTip(0, f"Zeile {line.line_no}")
            parent.addChild(child)
        (self._text_header or self.invisibleRootItem()).addChild(parent)
        parent.setExpanded(True)

    def show_message(self, text: str) -> None:
        self.clear_results()
        item = QTreeWidgetItem([_muted(text)])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.addTopLevelItem(item)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, ROLE_PATH)
        if path:
            self.open_requested.emit(Path(path), item.data(0, ROLE_LINE))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentItem():
            self._on_item_clicked(self.currentItem(), 0)
            return
        super().keyPressEvent(event)
