import json

import pytest

from notex.core import structured as st


def test_kind_for() -> None:
    assert st.kind_for("a.json") == "json" and st.kind_for("B.YML") == "yaml" and st.kind_for("c.yaml") == "yaml"
    assert st.kind_for("geheim.json.ntx") is None and st.kind_for("x.txt") is None


def test_json_errors_have_line_and_column() -> None:
    text = '{\n  "a": 1,\n  "b": \n}\n'
    error = st.validate(text, "json")
    assert error is not None and (error.line, error.column) == (4, 1)
    assert error.message == "Wert erwartet" and text[error.position] == "}"
    assert "Z 4, S 1" in error.short("json")
    assert st.validate('{"a": [1, 2,]}', "json") is not None
    assert st.validate('{"a": 1}', "json") is None
    assert st.validate("", "json") is not None


def test_format_json_keeps_literals_exactly() -> None:
    text = '{"b":1.10,"a":[1e5,-0.0,"\\u00e4\\n",true,null],"leer":{},"l":[]}'
    out = st.format_json(text, 2)
    assert json.loads(out) == json.loads(text)
    assert "1.10" in out and "1e5" in out and "\\u00e4\\n" in out           # nichts normalisiert
    assert out.index('"b"') < out.index('"a"')                            # Reihenfolge bleibt
    assert '"leer": {}' in out and '"l": []' in out
    assert out.splitlines()[1] == '  "b": 1.10,'
    assert st.format_json(text, 4).splitlines()[1] == '    "b": 1.10,'
    assert st.minify_json(out) == text


def test_format_json_trailing_newline_and_invalid() -> None:
    assert st.format_json('{"a":1}\n').endswith("}\n")
    assert not st.format_json('{"a":1}').endswith("\n")
    with pytest.raises(ValueError, match="Z 1"):
        st.format_json('{"a":}')


def test_format_json_strings_with_brackets_and_colons() -> None:
    text = '{"u":"http://x/{a}[b],c:d","q":"say \\"hi\\""}'
    out = st.format_json(text)
    assert json.loads(out) == json.loads(text)
    assert '"http://x/{a}[b],c:d"' in out


def test_yaml_errors_have_line_and_column() -> None:
    text = "a: 1\nb: [1, 2\nc: 3\n"
    error = st.validate(text, "yaml")
    assert error is not None and error.line >= 2 and error.column >= 1
    assert st.validate("a: 1\n", "yaml") is None
    assert st.validate("", "yaml") is None


def test_yaml_safe_only() -> None:
    evil = "!!python/object/apply:os.system ['echo boom']\n"
    error = st.validate(evil, "yaml")
    assert error is not None                               # safe_load lehnt Python-Tags ab
    with pytest.raises(ValueError):
        st.format_yaml(evil)


def test_format_yaml_keeps_order_and_unicode() -> None:
    text = "zeta: 1\nalpha:\n    - ä\n    - {x: 1}\n"
    out = st.format_yaml(text, 2)
    assert out.index("zeta") < out.index("alpha") and "ä" in out
    assert st.minify_yaml(text).strip() == "{zeta: 1, alpha: [ä, {x: 1}]}"


def test_yaml_multi_document() -> None:
    text = "a: 1\n---\nb: 2\n"
    out = st.format_yaml(text)
    assert out.count("---") == 2 and "a: 1" in out and "b: 2" in out


def test_yaml_comment_detection() -> None:
    assert st.yaml_has_comments("# Kopf\na: 1\n")
    assert st.yaml_has_comments("a: 1  # hinten\n")
    assert not st.yaml_has_comments("a: 'kein # Kommentar'\nb: \"auch # nicht\"\nurl: http://x/#anker\n")


def test_path_string_and_tree_helpers() -> None:
    assert st.path_string(["users", 3, "name"]) == "$.users[3].name"
    assert st.path_string(["a b", 0]) == '$["a b"][0]'
    assert st.path_string([]) == "$"
    value = {"users": [{"name": "Ada"}], "ok": True, "n": None}
    assert [k for k, _v in st.children(value)] == ["users", "ok", "n"]
    assert st.children(value["users"]) == [(0, {"name": "Ada"})]
    assert st.preview(value) == "{ 3 }" and st.preview([1, 2]) == "[ 2 ]"
    assert st.preview(True) == "true" and st.preview(None) == "null" and st.preview("a\nb") == '"a\\nb"'
    assert st.type_name(1.5) == "Zahl" and st.type_name(False) == "Wahrheitswert"
