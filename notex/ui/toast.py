"""Kurzer Hinweis unten rechts ("Gespeichert"), blendet ein und nach ~1,5 s wieder aus."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from notex.theme.icons import pixmap
from notex.theme.tokens import COLORS, DURATION, SPACING
from notex.ui import anim


class Toast(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.icon_label = QLabel()
        self.text_label = QLabel()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.lg, SPACING.sm)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)   # klein genug, dass der Effekt nichts kostet
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, icon_name: str = "check") -> None:
        self.icon_label.setPixmap(pixmap(icon_name, 16, COLORS.text, self.devicePixelRatioF()))
        self.text_label.setText(text)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        anim.animate(self, self._opacity.opacity(), 1.0, DURATION.toast_fade, self._opacity.setOpacity)
        self._timer.start(DURATION.toast)

    def _fade_out(self) -> None:
        anim.animate(self, self._opacity.opacity(), 0.0, DURATION.toast_fade, self._opacity.setOpacity, self.hide)

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = SPACING.xl
        self.move(parent.width() - self.width() - margin, parent.height() - self.height() - margin - SPACING.xl)
