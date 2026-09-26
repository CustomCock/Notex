"""Farbfeld für den Einstellungsdialog: Farbfläche (öffnet den Farbwähler) + Hex-Eingabe + Kontrast-Warnung."""
from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QRegularExpressionValidator
from PySide6.QtWidgets import QColorDialog, QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from notex.core.theme_model import MIN_CONTRAST, is_hex_color
from notex.theme.icons import pixmap
from notex.theme.tokens import COLORS, RADIUS, SPACING


class Swatch(QToolButton):
    def __init__(self) -> None:
        super().__init__()
        self.color = QColor("#000000")
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Farbe wählen")

    def set_color(self, hex_color: str) -> None:
        self.color = QColor(hex_color)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(COLORS.border))
        painter.setBrush(self.color)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), RADIUS.control, RADIUS.control)


class ColorField(QWidget):
    changed = Signal(str, str)   # key, "#rrggbb"

    def __init__(self, key: str, label: str) -> None:
        super().__init__()
        self.key = key
        self._color = "#000000"

        self.label = QLabel(label)
        self.swatch = Swatch()
        self.hex_edit = QLineEdit()
        self.hex_edit.setFixedWidth(84)
        self.hex_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"#?[0-9a-fA-F]{0,6}")))
        self.hex_edit.setToolTip("Hex-Farbe, z. B. #7a8a9e")
        self.warning = QLabel()
        self.warning.setFixedSize(18, 18)
        self.warning.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.warning)
        layout.addWidget(self.swatch)
        layout.addWidget(self.hex_edit)

        self.swatch.clicked.connect(self._pick)
        self.hex_edit.editingFinished.connect(self._from_text)

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, hex_color: str, emit: bool = False) -> None:
        if not is_hex_color(hex_color):
            return
        self._color = hex_color.lower()
        self.swatch.set_color(self._color)
        if self.hex_edit.text().lower() != self._color:
            self.hex_edit.setText(self._color)
        if emit:
            self.changed.emit(self.key, self._color)

    def set_warning(self, ratio: float | None) -> None:
        if ratio is None:
            self.warning.hide()
            return
        self.warning.setPixmap(pixmap("triangle-alert", 16, COLORS.text_muted, self.devicePixelRatioF()))
        self.warning.setToolTip(f"Kontrast {ratio:.1f}:1 – unter der Empfehlung von {MIN_CONTRAST}:1 (WCAG)")
        self.warning.show()

    def _from_text(self) -> None:
        text = self.hex_edit.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        if is_hex_color(text):
            self.set_color(text, emit=True)
        else:
            self.hex_edit.setText(self._color)

    def _pick(self) -> None:
        dialog = QColorDialog(QColor(self._color), self)
        dialog.setWindowTitle(self.label.text())
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)  # im App-Stil + Live-Vorschau
        before = self._color
        dialog.currentColorChanged.connect(lambda c: self.set_color(c.name(), emit=True))
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            self.set_color(before, emit=True)
