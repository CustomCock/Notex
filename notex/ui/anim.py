"""Animations-Helfer. Alles kurz, alles abschaltbar (Theme: animation.enabled).

Bei reduzierten Animationen liefern die Helfer sofort den Endzustand – der
UI-Code muss dafür nichts Besonderes tun.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation, Signal

_reduced = False


def set_reduced(reduced: bool) -> None:
    global _reduced
    _reduced = reduced


def reduced() -> bool:
    return _reduced


def duration(ms: int) -> int:
    return 0 if _reduced else ms


def animate(parent: QObject, start: float, end: float, ms: int, on_value: Callable[[float], None],
            on_finished: Callable[[], None] | None = None,
            easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic) -> QVariantAnimation:
    """Fährt einen Wert von start nach end und ruft on_value bei jedem Schritt auf."""
    anim = QVariantAnimation(parent)
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setDuration(duration(ms))
    anim.setEasingCurve(easing)
    anim.valueChanged.connect(lambda v: on_value(float(v)))
    if on_finished is not None:
        anim.finished.connect(on_finished)
    anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


class HoverFade(QObject):
    """Ein Wert 0..1, der weich zwischen "nicht gehovert" und "gehovert" wechselt.

    Wer ihn benutzt, zeichnet seine Hover-Fläche mit Deckkraft = value und ruft
    bei Änderungen update() auf – deshalb das Signal `changed`.
    """

    changed = Signal()

    def __init__(self, parent: QObject, ms: int) -> None:
        super().__init__(parent)
        self._ms = ms
        self.value = 0.0
        self._anim: QVariantAnimation | None = None

    def fade_to(self, hovered: bool) -> None:
        target = 1.0 if hovered else 0.0
        if self._anim is not None:
            self._anim.stop()
        if duration(self._ms) == 0:
            self.value = target
            self.changed.emit()
            return
        self._anim = animate(self, self.value, target, self._ms, self._set_value)

    def _set_value(self, value: float) -> None:
        self.value = value
        self.changed.emit()
