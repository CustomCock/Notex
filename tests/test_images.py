from datetime import datetime
from pathlib import Path

from notex.core.images import (asset_name, assets_dir, can_embed_images, find_unused_images, image_links, is_image,
                               markdown_image, plan_assets_move, relative_link)

NOW = datetime(2026, 9, 26, 14, 30, 5)


def test_embed_rules_including_ntx() -> None:
    assert can_embed_images("a/notiz.md") and can_embed_images("x.MARKDOWN")
    assert not can_embed_images("a/geheim.ntx")          # .ntx-Regel: Bild läge unverschlüsselt daneben
    assert not can_embed_images("a/text.txt")
    assert is_image("x.PNG") and is_image("a.svg") and not is_image("a.pdf")


def test_asset_name_and_collisions() -> None:
    note = Path("/d/Meine Notiz (1).md")
    assert asset_name(note, NOW) == "Meine-Notiz-1-20260926-143005.png"
    taken = {"meine-notiz-1-20260926-143005.png"}
    assert asset_name(note, NOW, ".png", taken) == "Meine-Notiz-1-20260926-143005-2.png"
    assert asset_name(Path("/d/---.md"), NOW, ".jpg").startswith("bild-")   # nichts Brauchbares im Namen


def test_assets_dir_is_sanitized(tmp_path: Path) -> None:
    note = tmp_path / "n.md"
    assert assets_dir(note) == tmp_path / "assets"
    assert assets_dir(note, "  bilder/ ") == tmp_path / "bilder"
    assert assets_dir(note, "../raus") == tmp_path / "assets"


def test_links_are_relative_and_encoded(tmp_path: Path) -> None:
    note = tmp_path / "ordner" / "n.md"
    image = tmp_path / "ordner" / "assets" / "mein bild ä.png"
    assert relative_link(note, image) == "assets/mein%20bild%20%C3%A4.png"
    assert markdown_image(note, image, "Screenshot") == "![Screenshot](assets/mein%20bild%20%C3%A4.png)"


def test_image_links_parsing() -> None:
    text = ('![a](assets/x.png) ![b](<assets/mit leer.png>) ![c](https://ex.org/y.png) '
            '![d](data:image/png;base64,AAA) <img src="assets/z.gif"> ![e](assets/q%20r.png "Titel")')
    assert image_links(text) == ["assets/x.png", "assets/mit leer.png", "assets/q r.png", "assets/z.gif"]


def test_plan_assets_move_moves_and_copies_and_rewrites(tmp_path: Path) -> None:
    old = tmp_path / "a" / "n.md"
    new = tmp_path / "b" / "n.md"
    text = "![x](assets/x.png)\n![y](assets/y.png)\n![fremd](../c/bild.png)\n![web](https://e.org/w.png)"
    other = {tmp_path / "a" / "andere.md": "![y](assets/y.png)"}
    plan = plan_assets_move(old, new, text, other)
    assert plan.moves == [(tmp_path / "a/assets/x.png", tmp_path / "b/assets/x.png")]
    assert plan.copies == [(tmp_path / "a/assets/y.png", tmp_path / "b/assets/y.png")]
    assert "![x](assets/x.png)" in plan.new_text and "![fremd](../c/bild.png)" in plan.new_text
    # gleicher Ordner (nur umbenannt): nichts zu tun
    assert plan_assets_move(old, tmp_path / "a" / "neu.md", text, other).empty


def test_plan_assets_move_to_nested_folder(tmp_path: Path) -> None:
    plan = plan_assets_move(tmp_path / "n.md", tmp_path / "tief" / "n.md", "![x](assets/x.png)", {})
    assert plan.moves == [(tmp_path / "assets/x.png", tmp_path / "tief/assets/x.png")]
    assert plan.new_text == "![x](assets/x.png)"


def test_find_unused_images(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    for name in ("used.png", "unused.jpg", "wiki.png", "link.gif"):
        (tmp_path / "assets" / name).write_bytes(b"x")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "x.png").write_bytes(b"x")
    texts = {tmp_path / "n.md": "![a](assets/used.png) [[wiki.png]] [Link](assets/link.gif)"}
    assert find_unused_images(tmp_path, texts) == [tmp_path / "assets" / "unused.jpg"]
