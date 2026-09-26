import json
from pathlib import Path

from notex.core.theme_model import (DEFAULT_THEME, PAPER_VARIANTS, PRESETS, contrast_ratio, contrast_warnings,
                                    merge_theme, theme_from_preset)
from notex.core.theme_store import ThemeStore, safe_filename


def test_merge_of_garbage_gives_defaults() -> None:
    assert merge_theme(None) == DEFAULT_THEME
    assert merge_theme("kaputt") == DEFAULT_THEME
    assert merge_theme([1, 2]) == DEFAULT_THEME


def test_merge_keeps_valid_and_fixes_invalid_values() -> None:
    theme = merge_theme({
        "name": "  Mein Theme  ",
        "colors": {"bg": "#000000", "text": "rot", "accent": "#ABCDEF", "unbekannt": "#123456"},
        "paper": {"shadow": "ja", "shadow_strength": 500, "padding": -3, "max_columns": 100},
        "font": {"ui_size": "gross", "editor_size": 16, "line_height": 9},
        "shape": {"radius": 40, "density": "riesig"},
        "animation": {"enabled": False, "speed": "warp"},
    })
    assert theme["name"] == "Mein Theme"
    assert theme["colors"]["bg"] == "#000000"
    assert theme["colors"]["accent"] == "#abcdef"                      # normalisiert auf Kleinbuchstaben
    assert theme["colors"]["text"] == DEFAULT_THEME["colors"]["text"]  # ungültig -> Standard
    assert "unbekannt" not in theme["colors"]
    assert theme["paper"]["shadow"] is True and theme["paper"]["shadow_strength"] == 100
    assert theme["paper"]["padding"] == 8 and theme["paper"]["max_columns"] == 100
    assert theme["font"]["ui_size"] == 13 and theme["font"]["editor_size"] == 16 and theme["font"]["line_height"] == 2.2
    assert theme["shape"]["radius"] == 12 and theme["shape"]["density"] == "normal"
    assert theme["animation"]["enabled"] is False and theme["animation"]["speed"] == "normal"


def test_bool_is_not_a_number() -> None:
    theme = merge_theme({"paper": {"padding": True}, "font": {"ui_size": False}})
    assert theme["paper"]["padding"] == DEFAULT_THEME["paper"]["padding"]
    assert theme["font"]["ui_size"] == DEFAULT_THEME["font"]["ui_size"]


def test_presets_and_paper_variants_are_complete() -> None:
    for name in PRESETS:
        theme = theme_from_preset(name)
        assert theme["name"] == name
        assert set(theme["colors"]) == set(DEFAULT_THEME["colors"])
    for variant in PAPER_VARIANTS:
        theme = theme_from_preset("Matt", variant)
        assert theme["colors"]["paper"] == PAPER_VARIANTS[variant]["paper"]
    assert theme_from_preset("Mitternacht")["colors"]["bg"] != DEFAULT_THEME["colors"]["bg"]


def test_contrast_ratio_known_values() -> None:
    assert contrast_ratio("#000000", "#ffffff") == 21.0
    assert contrast_ratio("#ffffff", "#ffffff") == 1.0
    assert 4.5 < contrast_ratio("#d6d6d6", "#121212")


def test_contrast_warnings_flag_low_contrast_only() -> None:
    assert contrast_warnings(DEFAULT_THEME["colors"]) == {}
    bad = dict(DEFAULT_THEME["colors"], text="#333333")
    warnings = contrast_warnings(bad)
    assert "text" in warnings and warnings["text"] < 4.5
    assert "paper_text" not in warnings


def test_all_bundled_presets_pass_contrast() -> None:
    for name in PRESETS:
        for variant in PAPER_VARIANTS:
            theme = theme_from_preset(name, variant)
            assert contrast_warnings(theme["colors"]) == {}, (name, variant)


# ---- ThemeStore ----------------------------------------------------------------
def test_safe_filename() -> None:
    assert safe_filename('Mein: Theme/2?') == "Mein Theme2"
    assert safe_filename("   ") == "Theme"


def test_store_roundtrip_and_listing(tmp_path: Path) -> None:
    store = ThemeStore(tmp_path / "themes")
    assert store.names() == []
    theme = theme_from_preset("Warm")
    store.save(theme, "Abend")
    assert store.names() == ["Abend"]
    loaded = store.load("Abend")
    assert loaded["name"] == "Abend" and loaded["colors"] == theme["colors"]


def test_store_broken_file_does_not_crash(tmp_path: Path) -> None:
    folder = tmp_path / "themes"
    folder.mkdir()
    (folder / "Kaputt.json").write_text("{ nicht json", encoding="utf-8")
    (folder / "Halb.json").write_text(json.dumps({"colors": {"bg": "#101010"}}), encoding="utf-8")
    store = ThemeStore(folder)
    assert store.load("Kaputt")["name"] == "Kaputt"
    assert store.load("Kaputt")["colors"] == DEFAULT_THEME["colors"]
    halb = store.load("Halb")
    assert halb["colors"]["bg"] == "#101010" and halb["font"] == DEFAULT_THEME["font"]
    assert store.load("Gibtsnicht")["name"] == "Gibtsnicht"
    assert store.is_valid_file(folder / "Halb.json") and not store.is_valid_file(folder / "Kaputt.json")


def test_store_rename_duplicate_delete_import_export(tmp_path: Path) -> None:
    store = ThemeStore(tmp_path / "themes")
    store.save(theme_from_preset("Graphit"), "A")
    store.rename("A", "B")
    assert store.names() == ["B"]
    dup = store.duplicate("B")
    assert dup["name"] == "B Kopie" and set(store.names()) == {"B", "B Kopie"}
    store.duplicate("B")
    assert "B Kopie 2" in store.names()
    exported = tmp_path / "export.json"
    store.export_file(store.load("B"), exported)
    store.delete("B")
    assert "B" not in store.names()
    imported = store.import_file(exported)
    assert imported["name"] == "B" and "B" in store.names()


def test_old_theme_with_ui_family_is_ignored_and_empty_text_font_means_default() -> None:
    theme = merge_theme({"font": {"ui_family": "Comic Sans", "editor_family": "  "}})
    assert "ui_family" not in theme["font"]
    assert theme["font"]["editor_family"] == ""
    assert merge_theme({"font": {"editor_family": "JetBrains Mono"}})["font"]["editor_family"] == "JetBrains Mono"
