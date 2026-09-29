import os

import pytest


@pytest.fixture
def win(tmp_path, monkeypatch):
    """Echtes Hauptfenster (offscreen, alle Module an). Modale Dialoge blockieren nie."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    import uihelp
    monkeypatch.setenv("NOTEX_ROOT", str(tmp_path))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    QApplication.instance() or QApplication([])
    window = uihelp.make_window(tmp_path)
    yield window
    uihelp.close_window(window)
