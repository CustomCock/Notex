from datetime import datetime

from notex.core import text_ops as ops


def test_line_operations() -> None:
    assert ops.duplicate_lines(["a", "b"]) == ["a", "b", "a", "b"]
    assert ops.sort_lines(["b", "A", "c"]) == ["A", "b", "c"]
    assert ops.unique_lines(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
    assert ops.strip_trailing_whitespace(["x  ", "y\t", "  z"]) == ["x", "y", "  z"]


def test_move_lines_up_and_down_with_bounds() -> None:
    lines = ["1", "2", "3", "4"]
    assert ops.move_lines(lines, 1, 3, -1) == (["2", "3", "1", "4"], 0, 2)
    assert ops.move_lines(lines, 1, 3, +1) == (["1", "4", "2", "3"], 2, 4)
    assert ops.move_lines(lines, 0, 1, -1) == (lines, 0, 1)      # oben: nichts
    assert ops.move_lines(lines, 3, 4, +1) == (lines, 3, 4)      # unten: nichts


def test_case_operations() -> None:
    assert ops.to_upper("äöü test") == "ÄÖÜ TEST"
    assert ops.to_lower("ÄÖÜ Test") == "äöü test"
    assert ops.to_title("hallo schöne welt don't") == "Hallo Schöne Welt Don't"


def test_date_stamp() -> None:
    assert ops.date_time_stamp(datetime(2026, 9, 26, 7, 5)) == "26.09.2026 07:05"


def test_markdown_toggles_roundtrip() -> None:
    assert ops.toggle_bold("Wort") == "**Wort**" and ops.toggle_bold("**Wort**") == "Wort"
    assert ops.toggle_italic("Wort") == "*Wort*" and ops.toggle_italic("*Wort*") == "Wort"
    assert ops.toggle_code("x") == "`x`" and ops.toggle_code("`x`") == "x"
    assert ops.toggle_code("a\nb") == "```\na\nb\n```" and ops.toggle_code("```\na\nb\n```") == "a\nb"
    assert ops.toggle_link("Notex") == "[Notex](https://)" and ops.toggle_link("[Notex](https://x.de)") == "Notex"
    assert ops.toggle_bold("") == "**Fett**"


def test_markdown_heading_and_lists() -> None:
    assert ops.toggle_heading("Titel") == "## Titel"
    assert ops.toggle_heading("## Titel") == "Titel"
    assert ops.toggle_heading("# Titel", level=2) == "## Titel"
    assert ops.toggle_list(["a", "  b", ""]) == ["- a", "  - b", ""]
    assert ops.toggle_list(["- a", "  - b", ""]) == ["a", "  b", ""]
    assert ops.toggle_list(["1. a", "2. b"]) == ["a", "b"]
    assert ops.toggle_checkbox(["a", "- b", "- [ ] c", "- [x] d"]) == ["- [ ] a", "- [ ] b", "- [x] c", "- [ ] d"]


def test_hanging_prefix() -> None:
    assert ops.hanging_prefix("- Punkt") == "- "
    assert ops.hanging_prefix("  * Punkt") == "  * "
    assert ops.hanging_prefix("1. Punkt") == "1. "
    assert ops.hanging_prefix("- [ ] Aufgabe") == "- [ ] "
    assert ops.hanging_prefix("    eingerückt") == "    "
    assert ops.hanging_prefix("normal") == ""
