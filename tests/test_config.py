import json
from pathlib import Path

from notex.core.config import DEFAULTS, load_config, save_config


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path / "nicht-da.json") == DEFAULTS


def test_broken_json_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{ das ist kein json", encoding="utf-8")
    assert load_config(path) == DEFAULTS


def test_wrong_types_fall_back_per_key(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "window": {"width": "breit", "height": 500, "x": True},
        "font_size": "gross",
        "word_wrap": "ja",
        "open_tabs": "nur ein String",
        "extensions": [".txt"],
        "unbekannt": 123,
    }), encoding="utf-8")
    cfg = load_config(path)
    assert cfg["window"]["width"] == DEFAULTS["window"]["width"]   # falscher Typ -> Default
    assert cfg["window"]["height"] == 500                           # richtiger Typ -> übernommen
    assert cfg["window"]["x"] is None                               # bool ist kein int
    assert cfg["font_size"] == DEFAULTS["font_size"]
    assert cfg["word_wrap"] is False
    assert cfg["open_tabs"] == []
    assert cfg["extensions"] == [".txt"]
    assert "unbekannt" not in cfg


def test_top_level_not_an_object_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_config(path) == DEFAULTS


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cfg = load_config(path)
    cfg["font_size"] = 14
    cfg["window"]["x"] = 10
    cfg["expanded_folders"] = ["a/b"]
    save_config(path, cfg)
    assert load_config(path) == cfg
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]  # keine Temp-Datei übrig


def test_defaults_are_not_mutated(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "x.json")
    cfg["extensions"].append(".xyz")
    assert ".xyz" not in DEFAULTS["extensions"]


def test_open_mapping_accepts_new_keys_and_rejects_bad_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"font_by_extension": {".py": "Consolas", ".rs": "JetBrains Mono", ".bad": 5}}), encoding="utf-8")
    cfg = load_config(path)
    assert cfg["font_by_extension"][".py"] == "Consolas"       # überschrieben
    assert cfg["font_by_extension"][".rs"] == "JetBrains Mono"  # neuer Schlüssel bleibt
    assert ".bad" not in cfg["font_by_extension"]               # falscher Typ verworfen
    assert cfg["font_by_extension"][".json"] == DEFAULTS["font_by_extension"][".json"]
