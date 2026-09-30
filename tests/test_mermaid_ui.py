"""Mermaid in der Oberfläche: Vorschau zeichnet das Diagramm, Speichern als PNG/SVG, PDF-Export, Palette, Einstellung."""
import pytest

pytest.importorskip("PySide6")

import uihelp  # noqa: E402
from PySide6.QtCore import QUrl  # noqa: E402

MD = "# Plan\n\n```mermaid\nflowchart LR\n  A[Start] --> B{Frage}\n  B -- Ja --> C[Ende]\n```\n\nText danach.\n"


def _preview_page(win, text=MD):
    path = win.files["md"]
    path.write_text(text, encoding="utf-8")
    win.tabs.open_file(path)
    page = win.tabs.current_page()
    page.set_view_mode("preview")
    assert uihelp.wait_for(lambda: page.preview is not None and page.preview._diagrams)
    return page


def test_preview_draws_diagram_image(win):
    preview = _preview_page(win).preview
    key = next(iter(preview._diagrams))
    image = preview._diagram_image(key)
    assert not image.isNull() and image.width() > 50 and image.height() > 20
    assert not preview.loadResource(2, QUrl(f"notex-mermaid:{key}")).isNull()
    assert "Text danach" in preview.toPlainText()


def test_save_diagram_png_and_svg(win, tmp_path):
    from PySide6.QtGui import QImage
    preview = _preview_page(win).preview
    key = next(iter(preview._diagrams))
    assert preview.save_diagram(key, "png", str(tmp_path / "d.png"))
    assert not QImage(str(tmp_path / "d.png")).isNull()
    assert preview.save_diagram(key, "svg", str(tmp_path / "d.svg"))
    assert (tmp_path / "d.svg").read_text(encoding="utf-8").startswith("<svg")
    assert not preview.save_diagram("gibtsnicht", "png", str(tmp_path / "x.png"))


def test_setting_off_shows_code_instead(win):
    page = _preview_page(win)
    win.config["preview_mermaid"] = False
    win.tabs.apply_preview_settings()
    assert not page.preview._diagrams and "flowchart LR" in page.preview.toPlainText()
    win.config["preview_mermaid"] = True
    win.tabs.apply_preview_settings()
    assert page.preview._diagrams


def test_pdf_export_with_diagram(win, tmp_path):
    from notex.core import export
    from notex.ui import export_service
    out = tmp_path / "plan.pdf"
    export_service.export_pdf(out, MD, "markdown", export.ExportMeta(title="Plan"), name="plan.md")
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"/Image" in data


def test_palette_command_inserts_example(win):
    assert win.registry.get("md:mermaid") is not None
    path = win.files["md"]
    win.tabs.open_file(path)
    editor = win.tabs.current_editor()
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    assert win.insert_mermaid("gantt")
    assert "```mermaid\ngantt" in editor.toPlainText()


def test_palette_command_refuses_non_markdown(win):
    win.tabs.open_file(win.files["log"])
    assert not win.insert_mermaid("pie")
    assert "```mermaid" not in win.tabs.current_editor().toPlainText()


def test_save_from_encrypted_note_needs_confirmation(win, tmp_path, monkeypatch):
    from notex.ui import dialogs
    preview = _preview_page(win).preview
    key = next(iter(preview._diagrams))
    preview._path = tmp_path / "geheim.ntx"
    asked = []
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: asked.append(a) or False)
    assert not preview.save_diagram(key, "png")
    assert asked
