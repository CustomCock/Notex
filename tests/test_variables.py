import json
from pathlib import Path

from notex.core import variables as vb
from notex.core.variables import Token, Variable, find_tokens, resolve

VALUES = {"23": "Mit freundlichen Grüßen", "234": "Zweihundertvierunddreißig", "gruss": "Viele Grüße",
          "grüße": "Herzliche Grüße", "firma_tel": "+49 30 123", "adresse": "Musterweg 1\n12345 Berlin"}


def names(text: str, prefix: str = "§") -> list[tuple[str, bool]]:
    return [(t.name, t.escaped) for t in find_tokens(text, VALUES, prefix)]


def test_longest_name_and_boundaries() -> None:
    assert names("§23 und §234.") == [("23", False), ("234", False)]
    assert names("§2345 §23a §23_x") == []                  # Token endet erst am Nicht-Namenszeichen → undefiniert
    assert names("(§gruss), §firma_tel!") == [("gruss", False), ("firma_tel", False)]
    assert names("Absatz§23") == [("23", False)]


def test_umlauts_prefix_edge_cases() -> None:
    assert names("§grüße") == [("grüße", False)]
    assert names("Ende §\nneue Zeile") == []                # Präfix am Zeilenende
    assert names("§§23") == [("23", False)]                 # doppeltes Präfix: das zweite zählt
    assert names("§99 ist nicht definiert") == []
    assert names("§") == [] and names("") == []
    assert names("{{gruss}} und {{23", "{{") == [("gruss", False), ("23", False)]   # anderes Präfix


def test_escape_and_positions() -> None:
    text = r"A \§23 B §23"
    tokens = find_tokens(text, VALUES)
    assert tokens == [Token(2, 6, "23", True), Token(9, 12, "23", False)]
    assert names(r"\§99") == []                             # Escape eines undefinierten Namens: normaler Text


def test_resolve_values_escapes_no_recursion() -> None:
    values = dict(VALUES, rek="siehe §gruss")
    assert resolve("Gruß: §gruss, Tel §firma_tel", values) == "Gruß: Viele Grüße, Tel +49 30 123"
    assert resolve(r"Paragraph \§23 bleibt", values) == "Paragraph §23 bleibt"
    assert resolve("§rek", values) == "siehe §gruss"        # keine Rekursion
    assert resolve("§adresse", values, single_line=True) == "Musterweg 1 12345 Berlin"
    assert resolve("ohne Tokens", values) == "ohne Tokens"


def test_escape_roundtrip() -> None:
    text = "Gruß §23 und §23"
    first = find_tokens(text, VALUES)[0]
    escaped = vb.escape_token(text, first)
    assert escaped == r"Gruß \§23 und §23"
    again = find_tokens(escaped, VALUES)[0]
    assert again.escaped and vb.unescape_token(escaped, again) == text
    assert vb.escape_token(escaped, again) == escaped        # doppelt entfernen ändert nichts


def test_replace_and_escape_ranges() -> None:
    text = r"§23 §gruss \§23 §99"
    assert vb.replace_all(text, VALUES) == (r"Mit freundlichen Grüßen Viele Grüße \§23 §99", 2)
    assert vb.replace_all(text, VALUES, start=4) == (r"§23 Viele Grüße \§23 §99", 1)
    assert vb.escape_all(text, VALUES) == (r"\§23 \§gruss \§23 §99", 2)
    assert vb.escape_all(text, VALUES, start=0, end=2) == (r"\§23 §gruss \§23 §99", 1)   # angeschnitten zählt
    token = find_tokens("x §gruss y", VALUES)[0]
    assert vb.replace_token("x §gruss y", token, VALUES) == "x Viele Grüße y"


def test_token_at() -> None:
    tokens = find_tokens("ab §gruss cd", VALUES)
    assert vb.token_at(tokens, 3) is None and vb.token_at(tokens, 4).name == "gruss"
    assert vb.token_at(tokens, 3, inclusive=True).name == "gruss" and vb.token_at(tokens, 9, inclusive=True)


def test_completions_and_typed_name() -> None:
    variables = [Variable(n, v) for n, v in VALUES.items()]
    assert [n for n, _ in vb.completions("gr", variables)] == ["gruss", "grüße"]   # gleiche Länge → alphabetisch
    assert [n for n, _ in vb.completions("2", variables)][:2] == ["23", "234"]
    assert vb.completions("adr", variables)[0] == ("adresse", "Musterweg 1 ⏎ 12345 Berlin")
    assert vb.typed_name_before("Hallo §gr", 9) == "gr" and vb.typed_name_before("Hallo §", 7) == ""
    assert vb.typed_name_before(r"Hallo \§gr", 10) is None and vb.typed_name_before("Hallo", 5) is None


def test_display_value() -> None:
    assert vb.display_value("a\nb") == "a ⏎ b"
    assert len(vb.display_value("x" * 200)) == vb.DISPLAY_LIMIT and vb.display_value("x" * 200).endswith("…")


def test_storage_roundtrip_and_import(tmp_path: Path) -> None:
    path = tmp_path / "variables.json"
    items = [Variable("gruss", "Viele Grüße", "Brief"), Variable("adresse", "Zeile 1\nZeile 2")]
    vb.save_variables(path, items)
    assert {v.name: v.value for v in vb.load_variables(path)} == {"gruss": "Viele Grüße", "adresse": "Zeile 1\nZeile 2"}
    assert "Grüße" in path.read_text(encoding="utf-8")        # UTF-8, lesbar
    assert vb.parse_variables({"a": "1", "b c": "ungültig", "d": 5}) == [Variable("a", "1")]
    assert vb.load_variables(tmp_path / "fehlt.json") == []
    (tmp_path / "kaputt.json").write_text("{", encoding="utf-8")
    assert vb.load_variables(tmp_path / "kaputt.json") == []
    assert list(tmp_path.glob(".variables-*")) == []          # keine Temp-Reste


def test_file_stays_byte_identical_and_ntx_rule(tmp_path: Path) -> None:
    """Öffnen/Anzeigen löst nur im Speicher auf – der Dateitext bleibt unverändert (auch bei .ntx)."""
    from notex.core.encoding import decode_bytes
    from notex.core.fileops import save_text_file
    raw = "Gruß §23\r\n\\§23 bleibt\r\n".encode("utf-8")
    path = tmp_path / "brief.txt"
    path.write_bytes(raw)
    tf = decode_bytes(raw)
    shown = resolve(tf.text, VALUES)                         # Anzeige/Kopie
    assert "Mit freundlichen Grüßen" in shown and "§23" in tf.text
    save_text_file(path, tf.text, tf.encoding, tf.eol)
    assert path.read_bytes() == raw
    store = tmp_path / "variables.json"
    vb.save_variables(store, [Variable("23", VALUES["23"])])
    secret = "geheimer Klartext aus .ntx"
    resolve(f"{secret} §23", VALUES)                        # Auflösen schreibt nirgends hin
    assert secret not in store.read_text(encoding="utf-8")
    assert json.loads(store.read_text(encoding="utf-8"))["variables"][0]["name"] == "23"


def test_resolve_with_line_map_for_preview() -> None:
    text = "# Brief\n§adresse\n- [ ] Aufgabe\n\\§23"
    out, mapping = vb.resolve_with_line_map(text, VALUES)
    assert out == "# Brief\nMusterweg 1\n12345 Berlin\n- [ ] Aufgabe\n§23"
    assert mapping == [0, 1, 1, 2, 3]            # Aufgabe steht im Ergebnis in Zeile 3, im Original in Zeile 2
