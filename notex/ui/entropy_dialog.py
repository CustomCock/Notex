"""Entropie: Kurve über die Datei (QPainter), Bereiche hoch/niedrig markiert, Hover mit Wert, Klick → Hex-Ansicht.

Eine Serie, eine Achse (0–8 Bit/Byte). Linie in der Akzentfarbe, Raster zurückhaltend, Schwelle 7,5 gestrichelt,
auffällige Bereiche als dezente Bänder mit Legende; die Bereichsliste darunter ist die Tabellenansicht.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QToolTip, QWidget

from notex.core import entropy as en
from notex.theme.fonts import ui_font
from notex.theme.tokens import COLORS, FONT_SIZE
from notex.ui.analysis_dialog import AnalysisDialog
from notex.ui.viewer_page import human_size

LEFT, RIGHT, TOP, BOTTOM = 44, 16, 28, 30


def _alpha(color: str, alpha: int) -> QColor:
    result = QColor(color)
    result.setAlpha(alpha)
    return result


class EntropyChart(QWidget):
    clicked = Signal(int)            # Offset des angeklickten Blocks

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("EntropyChart")
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self.profile: en.Profile | None = None
        self.hover: int | None = None

    def set_profile(self, profile: en.Profile) -> None:
        self.profile = profile
        self.hover = None
        self.update()

    def _plot(self) -> QRectF:
        return QRectF(LEFT, TOP, max(10, self.width() - LEFT - RIGHT), max(10, self.height() - TOP - BOTTOM))

    def _x(self, index: int) -> float:
        plot, count = self._plot(), max(1, len(self.profile.values))
        return plot.left() + plot.width() * (index + 0.5) / count

    def _y(self, value: float) -> float:
        plot = self._plot()
        return plot.bottom() - plot.height() * value / 8.0

    def _index_at(self, x: float) -> int | None:
        if not self.profile or not self.profile.values:
            return None
        plot = self._plot()
        if not plot.left() <= x <= plot.right():
            return None
        return max(0, min(len(self.profile.values) - 1, int((x - plot.left()) / plot.width() * len(self.profile.values))))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(COLORS.surface))
        painter.setFont(ui_font(FONT_SIZE.small))
        plot = self._plot()
        muted, faint = QColor(COLORS.text_muted), _alpha(COLORS.text_faint, 110)
        for value in range(0, 9, 2):                       # zurückhaltendes Raster + Achsenbeschriftung
            y = self._y(value)
            painter.setPen(QPen(faint, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(muted)
            painter.drawText(QRectF(0, y - 8, LEFT - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             str(value))
        if not self.profile or not self.profile.values:
            painter.setPen(muted)
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Noch keine Daten")
            return
        prof = self.profile
        count = len(prof.values)
        for start, end, kind in en.regions(prof):          # Bänder hinter der Linie
            x0 = plot.left() + plot.width() * (start / prof.block_size) / count
            x1 = plot.left() + plot.width() * min(count, -(-end // prof.block_size)) / count
            color = _alpha(COLORS.warning, 46) if kind == "high" else _alpha(COLORS.text_faint, 70)
            painter.fillRect(QRectF(x0, plot.top(), max(1.0, x1 - x0), plot.height()), color)
        threshold = QPen(_alpha(COLORS.warning, 170), 1, Qt.PenStyle.DashLine)
        painter.setPen(threshold)
        painter.drawLine(QPointF(plot.left(), self._y(en.HIGH)), QPointF(plot.right(), self._y(en.HIGH)))
        path = QPainterPath()
        for index, value in enumerate(prof.values):
            point = QPointF(self._x(index), self._y(value))
            path.moveTo(point) if index == 0 else path.lineTo(point)
        painter.setPen(QPen(QColor(COLORS.accent), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        if count == 1:
            painter.setBrush(QColor(COLORS.accent))
            painter.drawEllipse(QPointF(self._x(0), self._y(prof.values[0])), 4, 4)
        painter.setPen(muted)                               # X-Achse: Offsets am Anfang/Mitte/Ende
        for fraction, align in ((0, Qt.AlignmentFlag.AlignLeft), (0.5, Qt.AlignmentFlag.AlignHCenter),
                                (1, Qt.AlignmentFlag.AlignRight)):
            x = plot.left() + plot.width() * fraction
            rect = QRectF(x - (0 if fraction == 0 else 120 if fraction == 1 else 60), plot.bottom() + 6, 120, 16)
            painter.drawText(rect, align | Qt.AlignmentFlag.AlignTop, human_size(int(prof.size * fraction)))
        self._legend(painter, plot)
        if self.hover is not None:                          # Fadenkreuz + Punkt
            x, y = self._x(self.hover), self._y(prof.values[self.hover])
            painter.setPen(QPen(_alpha(COLORS.text_muted, 160), 1))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QPen(QColor(COLORS.surface), 2))
            painter.setBrush(QColor(COLORS.accent))
            painter.drawEllipse(QPointF(x, y), 5, 5)
        painter.end()

    def _legend(self, painter: QPainter, plot: QRectF) -> None:
        x = plot.left()
        entries = [(QColor(COLORS.accent), "Entropie je Block", "line"),
                   (_alpha(COLORS.warning, 90), f"≥ {en.format_value(en.HIGH)} komprimiert/verschlüsselt", "band"),
                   (_alpha(COLORS.text_faint, 140), f"< {en.format_value(en.LOW)} leer/gleichförmig", "band")]
        for color, text, kind in entries:
            if kind == "line":
                painter.setPen(QPen(color, 2))
                painter.drawLine(QPointF(x, 12), QPointF(x + 14, 12))
            else:
                painter.fillRect(QRectF(x, 6, 14, 12), color)
            painter.setPen(QColor(COLORS.text_muted))
            width = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText(QPointF(x + 20, 16), text)
            x += 20 + width + 18

    def mouseMoveEvent(self, event) -> None:
        index = self._index_at(event.position().x())
        if index != self.hover:
            self.hover = index
            self.update()
        if index is not None:
            prof = self.profile
            start = prof.offset_of(index)
            end = min(prof.size, start + prof.block_size)
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"0x{start:X} – 0x{end:X}\n{en.format_value(prof.values[index])} Bit/Byte\nKlick: Hex-Ansicht",
                              self)

    def leaveEvent(self, _event) -> None:
        self.hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        index = self._index_at(event.position().x())
        if index is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.profile.offset_of(index))


class EntropyDialog(AnalysisDialog):
    def __init__(self, window, path: Path) -> None:
        super().__init__(window, path, "Entropie")
        self.block = QComboBox()
        self.block.addItem("Blockgröße automatisch", 0)
        for size in en.BLOCK_SIZES:
            self.block.addItem(human_size(size), size)
        run = QPushButton("Neu berechnen")
        run.clicked.connect(self.run)
        options = QHBoxLayout()
        options.addWidget(self.block)
        options.addStretch(1)
        options.addWidget(run)
        self.summary = QLabel()
        self.summary.setObjectName("EntropySummary")
        self.summary.setWordWrap(True)
        self.chart = EntropyChart()
        self.chart.clicked.connect(lambda offset: self.jump(offset, self._block_length()))
        self.region_list = QListWidget()
        self.region_list.setMaximumHeight(150)
        self.region_list.itemActivated.connect(self._region_jump)
        self.region_list.itemDoubleClicked.connect(self._region_jump)
        self.body.addLayout(options)
        self.body.addWidget(self.summary)
        self.body.addWidget(self.chart, 1)
        self.body.addWidget(self.region_list)
        self.finish_layout()
        self.run()

    def _block_length(self) -> int:
        return min(self.chart.profile.block_size, 1 << 20) if self.chart.profile else 1

    def run(self) -> None:
        block, path = self.block.currentData() or None, self.path
        self.start(lambda progress, cancelled: en.profile(path, block, progress=progress, cancelled=cancelled))

    def show_result(self, prof: en.Profile) -> None:
        self.chart.set_profile(prof)
        self.summary.setText(f"Gesamtentropie {en.format_value(prof.total)} Bit/Byte – {en.assess(prof)}")
        self.region_list.clear()
        for start, end, kind in en.regions(prof):
            label = "hoch (komprimiert/verschlüsselt?)" if kind == "high" else "niedrig (leer/gleichförmig)"
            item = QListWidgetItem(f"0x{start:08X} – 0x{end:08X}  ·  {human_size(end - start)}  ·  {label}")
            item.setData(Qt.ItemDataRole.UserRole, (start, end))
            self.region_list.addItem(item)
        regions = self.region_list.count()
        self.status.setText(f"{len(prof.values)} Blöcke zu {human_size(prof.block_size)} · "
                            f"{regions} auffällige Bereiche · Klick in die Kurve oder Doppelklick auf einen Bereich "
                            f"springt in die Hex-Ansicht")

    def _region_jump(self, item: QListWidgetItem) -> None:
        start, end = item.data(Qt.ItemDataRole.UserRole)
        self.jump(start, min(end - start, 1 << 20))
