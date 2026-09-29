"""R4b: Einstellungen → Module: „Alle aktivieren/deaktivieren“ (Tri-State), sofort wirksam, gespeichert."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from notex.core.modules import MODULES  # noqa: E402
from uihelp import capture_toasts, open_tools_menu  # noqa: E402


@pytest.fixture
def settings(win):
    from notex.ui.settings_dialog import SettingsDialog
    dialog = SettingsDialog(win, win.theme_store)
    yield dialog
    dialog.close()


def test_all_off_then_on_immediately(win, settings):
    assert settings.modules_all.checkState() == Qt.CheckState.Checked          # Fixture: alle an
    assert not settings.modules_all_on.isEnabled() and settings.modules_all_off.isEnabled()
    settings.modules_all_off.click()
    assert all(not win.modules.enabled(m.key) for m in MODULES)
    assert all(not box.isChecked() for box in settings.module_boxes.values())
    assert settings.modules_all.checkState() == Qt.CheckState.Unchecked
    assert settings.modules_count.text() == f"0 von {len(MODULES)} aktiv"
    assert win.registry.get("scan:open") is None                                # sofort ausgehängt
    assert "Netzwerk-Scanner" not in open_tools_menu(win)
    settings.modules_all_on.click()
    assert all(win.modules.enabled(m.key) for m in MODULES)
    assert win.registry.get("scan:open") is not None                            # sofort wieder da
    assert all(win.config["modules"][m.key] is True for m in MODULES)           # für config.json


def test_partial_state_and_master_click(win, settings):
    settings.module_boxes["scanner"].setChecked(False)
    assert settings.modules_all.checkState() == Qt.CheckState.PartiallyChecked
    assert settings.modules_all_on.isEnabled() and settings.modules_all_off.isEnabled()
    settings.modules_all.click()                                                # teils → alle an
    assert settings.modules_all.checkState() == Qt.CheckState.Checked and win.modules.enabled("scanner")
    settings.modules_all.click()                                                # alle → aus
    assert settings.modules_all.checkState() == Qt.CheckState.Unchecked
    assert not any(win.modules.enabled(m.key) for m in MODULES)


def test_cancel_restores_previous_state(win, settings):
    settings.modules_all_off.click()
    settings.reject()
    assert all(win.modules.enabled(m.key) for m in MODULES)


def test_palette_commands(win, monkeypatch):
    messages = capture_toasts(win, monkeypatch)
    win.registry.get("modules:all_off").callback()
    assert not any(win.modules.enabled(m.key) for m in MODULES)
    assert messages[-1] == f"{len(MODULES)} Module deaktiviert"
    win.registry.get("modules:all_on").callback()
    assert all(win.modules.enabled(m.key) for m in MODULES)
    win.registry.get("modules:all_on").callback()
    assert messages[-1] == "Alle Module sind schon an"
