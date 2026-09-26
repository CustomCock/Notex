"""Variablen im Editor: Wert statt Token anzeigen, Token als ein Zeichen behandeln, Hover, Kopieren.

Technik (Entscheidung, siehe PROGRESS.md): Die Datei enthält das Token (§gruss). Der Highlighter macht die
Token-Zeichen unsichtbar und gibt ihnen per Zeichenabstand genau die Breite des Werts; der Editor zeichnet den Wert
in diese Lücke. So stimmen Umbruch, Zeilenlänge und Klickpositionen, ohne den Dokumenttext anzufassen – Undo,
Suche, Speichern und Verlauf sehen weiterhin das Token. Der Cursor bleibt nie im Token stehen (einrasten an den
Rändern), Entf/Rücktaste löschen es ganz. Escapes (\\§gruss) zeigen „§gruss“; der Backslash hat keine Breite.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QTextCharFormat, QTextCursor

from notex.core import variables as vb
from notex.theme.tokens import COLORS

PAD = 2.0


# ---- Highlighter-Ebene --------------------------------------------------------------------------------
def token_formats(service, font: QFont, text: str) -> list[tuple[int, int, QTextCharFormat]]:
    """Formate für einen Block: (Start, Länge, Format). Tokens unsichtbar mit Wertbreite, Escape-Backslash ohne Breite."""
    metrics = QFontMetricsF(font)
    result = []
    for token in service.tokens(text):
        fmt = QTextCharFormat()
        fmt.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
        if token.escaped:
            fmt.setForeground(QColor(0, 0, 0, 0))
            fmt.setFontLetterSpacing(-metrics.horizontalAdvance(vb.ESCAPE))
            result.append((token.start, 1, fmt))
            continue
        raw = text[token.start:token.end]
        shown = vb.display_value(service.values[token.name])
        extra = metrics.horizontalAdvance(shown) + 2 * PAD - metrics.horizontalAdvance(raw)
        fmt.setForeground(QColor(0, 0, 0, 0))
        fmt.setFontLetterSpacing(extra / len(raw))
        result.append((token.start, token.length, fmt))
    return result


# ---- Zeichnen ---------------------------------------------------------------------------------------
def paint(editor, painter: QPainter) -> None:
    service = editor.variables
    if service is None:
        return
    document = editor.document()
    layout = document.documentLayout()
    scroll_y = editor.verticalScrollBar().value()
    scroll_x = editor.horizontalScrollBar().value()
    height = editor.viewport().height()
    block = editor.cursorForPosition(QPoint(0, 0)).block()
    font = editor.font()
    metrics = QFontMetricsF(font)
    painter.setFont(font)
    background = QColor(COLORS.accent)
    background.setAlpha(46)
    text_color = QColor(COLORS.paper_text)
    while block.isValid():
        rect = layout.blockBoundingRect(block)
        if rect.top() - scroll_y > height:
            break
        text = block.text()
        if service.prefix in text:
            text_layout = block.layout()
            for token in service.tokens(text):
                if token.escaped:
                    continue
                line = text_layout.lineForTextPosition(token.start)
                if not line.isValid():
                    continue
                x0 = line.cursorToX(token.start)[0]
                shown = vb.display_value(service.values[token.name])
                width = metrics.horizontalAdvance(shown) + 2 * PAD
                top = rect.top() + line.y() - scroll_y
                baseline = top + line.ascent()
                x = rect.left() + x0 - scroll_x
                pill = QRectF(x, baseline - metrics.ascent() - 1, width, metrics.ascent() + metrics.descent() + 2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(background)
                painter.drawRoundedRect(pill, 3, 3)
                painter.setPen(text_color)
                painter.drawText(QPointF(x + PAD, baseline), shown)
        block = block.next()


# ---- Cursor ------------------------------------------------------------------------------------------
def _zones(service, block) -> list[tuple[int, int]]:
    """Bereiche (absolut), in denen der Cursor nicht stehen darf: ganze Tokens bzw. der Escape-Backslash."""
    base = block.position()
    zones = []
    for token in service.tokens(block.text()):
        zones.append((base + token.start, base + (token.start + 1 if token.escaped else token.end)))
    return zones


def _snap(position: int, zones, direction: int) -> int:
    for start, end in zones:
        if start < position < end:
            if direction > 0:
                return end
            if direction < 0:
                return start
            return start if position - start <= end - position else end
    return position


def snap_cursor(editor, direction: int = 0) -> None:
    """Cursor (und Auswahl-Anker) aus Tokens heraus an den Rand schieben. direction: +1 rechts, -1 links, 0 nächster."""
    service = editor.variables
    if service is None:
        return
    cursor = editor.textCursor()
    position, anchor = cursor.position(), cursor.anchor()
    document = editor.document()
    zones = _zones(service, document.findBlock(position))
    if anchor != position:
        zones += _zones(service, document.findBlock(anchor))
        grow = 1 if position > anchor else -1           # Auswahl nach außen erweitern
        new_position = _snap(position, zones, direction or grow)
        new_anchor = _snap(anchor, zones, -grow)
    else:
        new_position = new_anchor = _snap(position, zones, direction)
    if (new_position, new_anchor) != (position, anchor):
        cursor.setPosition(new_anchor)
        cursor.setPosition(new_position, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)


def handle_delete(editor, event) -> bool:
    """Entf/Rücktaste an einem Token löschen es ganz (ein Undo-Schritt). True = erledigt."""
    service = editor.variables
    cursor = editor.textCursor()
    plain = event.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)
    if service is None or cursor.hasSelection() or not plain:
        return False
    key = event.key()
    if key not in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
        return False
    block = cursor.block()
    column = cursor.position() - block.position()
    for token in service.tokens(block.text()):
        if token.escaped:
            span = (token.start, token.start + 2)          # verborgener Backslash + sichtbares Präfix gemeinsam
        else:
            span = (token.start, token.end)
        hit = (key == Qt.Key.Key_Backspace and column == span[1]) or (key == Qt.Key.Key_Delete and column == span[0])
        if hit:
            edit = QTextCursor(editor.document())
            edit.setPosition(block.position() + span[0])
            edit.setPosition(block.position() + span[1], QTextCursor.MoveMode.KeepAnchor)
            editor._grouped(edit.removeSelectedText)
            return True
    return False


def token_at_point(editor, point) -> tuple[object, object] | None:
    """(Token, Block) unter einer Viewport-Position – für Hover und Kontextmenü."""
    service = editor.variables
    if service is None:
        return None
    cursor = editor.cursorForPosition(point)
    block = cursor.block()
    column = cursor.position() - block.position()
    tokens = service.tokens(block.text())
    token = vb.token_at(tokens, column, inclusive=True)
    if token is None:
        return None
    if not token.escaped:                                   # genauer: liegt der Punkt im gezeichneten Wert?
        start = editor.cursorRect(_cursor_at(editor, block.position() + token.start)).left()
        shown = vb.display_value(service.values[token.name])
        width = QFontMetricsF(editor.font()).horizontalAdvance(shown) + 2 * PAD
        if not start - 1 <= point.x() <= start + width + 1:
            others = [t for t in tokens if t is not token and t.start <= column <= t.end]
            return (others[0], block) if others else None
    return token, block


def _cursor_at(editor, position: int) -> QTextCursor:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    return cursor


def tooltip_text(editor, token) -> str:
    service = editor.variables
    value = service.values.get(token.name, "")
    head = f"{service.prefix}{token.name}" + ("  (entfernt – normaler Text)" if token.escaped else "")
    shown = value if len(value) <= 600 else value[:599] + "…"
    variable = service.get(token.name)
    description = f"\n\n{variable.description}" if variable is not None and variable.description else ""
    return f"{head}\n{shown}{description}"
