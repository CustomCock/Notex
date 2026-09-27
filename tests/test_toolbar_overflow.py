"""L2-Regression: Das Überlaufmenü der Bearbeitungsleiste darf beim Encoding-Wechsel nicht abstürzen.

Ursache war: dieselben QAction-Objekte lagen im Encoding-Button-Menü UND im Überlaufmenü, und ein
Encoding-Wechsel löste ein Relayout mit overflow_menu.clear() aus, während die Aktion noch verarbeitet wurde.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QAction          # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from notex.ui.toolbar import ENCODINGS, EditorToolbar  # noqa: E402


class FakeEditor:
    encoding = "utf-8"
    eol = "\n"
    font_family = ""
    font_size = 14


class FakeTabs:
    def __init__(self) -> None:
        self.editor = FakeEditor()
        self.encodings_set: list[str] = []
        self.eols_set: list[str] = []

    def current_editor(self):
        return self.editor

    def set_encoding(self, value: str) -> None:
        self.encodings_set.append(value)
        self.editor.encoding = value

    def set_eol(self, value: str) -> None:
        self.eols_set.append(value)
        self.editor.eol = value

    def set_text_font(self, *_a):
        pass

    def set_font_size(self, *_a):
        pass

    def open_font_settings(self):
        pass


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _actions() -> dict[str, QAction]:
    keys = ["undo", "redo", "find", "replace", "font_smaller", "font_larger", "zoom_reset", "paper_mode",
            "line_numbers", "split", "dup_line", "move_up", "move_down", "sort_lines", "unique_lines", "strip_ws",
            "upper", "lower", "title", "datetime", "md_bold", "md_italic", "md_heading", "md_list", "md_checkbox",
            "md_code", "md_link", "preview", "spell", "grammar"]
    return {key: QAction(key) for key in keys}


def test_overflow_encoding_does_not_share_actions_and_survives_toggles(qapp) -> None:
    tabs = FakeTabs()
    bar = EditorToolbar(_actions(), tabs, is_markdown=True)
    bar.resize(360, 40)                       # sehr schmal → „Datei“-Gruppe wandert ins Überlaufmenü
    bar._relayout()
    assert any(name == "Datei" for name, _a in bar._hidden)

    bar._build_overflow_menu()
    # Eigene QActions im Button-Menü bleiben vollständig erhalten (werden nicht ins Überlaufmenü verschoben)
    assert len(bar.encoding_button.menu_.actions()) == len(ENCODINGS)

    # Encoding-Untermenü im Überlaufmenü finden und mehrfach auslösen – kein Absturz, kein Verlust der Button-Aktionen
    submenu = next(a.menu() for a in bar.overflow_menu.actions() if a.menu() and "Encoding" in a.text())
    enc_actions = submenu.actions()
    assert enc_actions[0] not in bar.encoding_button.menu_.actions()      # eigene, nicht geteilte Aktionen
    for _ in range(3):
        for action in enc_actions:
            action.trigger()
        bar._build_overflow_menu()            # erneuter Aufbau (wie aboutToShow) muss stabil bleiben
    assert tabs.encodings_set and len(bar.encoding_button.menu_.actions()) == len(ENCODINGS)
