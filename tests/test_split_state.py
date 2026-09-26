from notex.core.split_state import SplitState, from_config, merge_groups, move_entry


def test_roundtrip_single_group_keeps_legacy_keys() -> None:
    state = SplitState(groups=[["a.md", "b.txt"]], active_tabs=[1])
    cfg = state.to_config()
    assert cfg["open_tabs"] == ["a.md", "b.txt"] and cfg["active_tab"] == 1
    assert cfg["split"] == {"enabled": False, "open_tabs": [], "active_tab": 0, "active_group": 0, "orientation": "horizontal"}
    back = from_config(cfg, exists=lambda _p: True)
    assert back.groups == [["a.md", "b.txt"]] and back.active_tabs == [1] and not back.is_split


def test_roundtrip_split_with_shared_document() -> None:
    state = SplitState(groups=[["a.md", "b.txt"], ["a.md", "c.md"]], active_tabs=[0, 1], active_group=1, orientation="vertical")
    back = from_config(state.to_config(), exists=lambda _p: True)
    assert back.is_split and back.groups == [["a.md", "b.txt"], ["a.md", "c.md"]]
    assert back.active_tabs == [0, 1] and back.active_group == 1 and back.orientation == "vertical"


def test_cleanup_removes_missing_and_duplicates_and_clamps() -> None:
    cfg = {"open_tabs": ["a.md", "a.md", "weg.md", 7, ""], "active_tab": 99,
           "split": {"enabled": True, "open_tabs": ["weg.md"], "active_tab": -3, "active_group": 1, "orientation": "schräg"}}
    state = from_config(cfg, exists=lambda p: p != "weg.md")
    assert state.groups == [["a.md"]] and state.active_tabs == [0]
    assert not state.is_split and state.active_group == 0 and state.orientation == "horizontal"


def test_garbage_config_gives_empty_state() -> None:
    state = from_config({"open_tabs": "x", "split": "y"}, exists=lambda _p: True)
    assert state.groups == [[]] and state.active_tabs == [0]
    state = from_config({}, exists=lambda _p: False)
    assert state.groups == [[]]


def test_move_entry_between_groups() -> None:
    groups = [["a", "b"], ["c"]]
    assert move_entry(groups, 0, 1, 1) == [["a"], ["c", "b"]]
    assert groups == [["a", "b"], ["c"]]              # Eingabe bleibt unverändert
    assert move_entry(groups, 0, 0, 0) is None         # gleiche Gruppe
    assert move_entry(groups, 0, 5, 1) is None         # ungültiger Index
    assert move_entry([["a"], ["a"]], 0, 0, 1) is None  # Ziel hat den Pfad schon
    assert move_entry(groups, 2, 0, 1) is None


def test_merge_groups_keeps_order_and_drops_duplicates() -> None:
    assert merge_groups([["a", "b"], ["b", "c"]]) == ["a", "b", "c"]
    assert merge_groups([[]]) == []
