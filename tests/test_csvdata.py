from notex.core.csvdata import (filter_indices, parse, serialize, sniff, sorted_indices, table_supported,
                                to_number)


def test_table_supported_never_for_ntx() -> None:
    assert table_supported("a.csv") and table_supported("B.TSV")
    assert not table_supported("geheim.ntx") and not table_supported("a.txt")


def test_sniff_delimiters() -> None:
    assert sniff("a,b,c\n1,2,3\n4,5,6\n").delimiter == ","
    assert sniff("Name;Preis;Menge\nApfel;1,20;3\nBirne;0,99;5\n").delimiter == ";"
    assert sniff("a\tb\n1\t2\n", "x.tsv").delimiter == "\t"
    assert sniff("a|b|c\n1|2|3\n").delimiter == "|"
    assert sniff("einspaltig\nwert\n").delimiter in (",", ";", "\t", "|")    # kein Absturz


def test_header_detection() -> None:
    assert sniff("Name,Alter\nAnna,31\nBen,45\n").has_header
    assert not sniff("1,2,3\n4,5,6\n7,8,9\n").has_header


def test_parse_quotes_embedded_delimiter_and_newline() -> None:
    text = 'Name,Notiz\n"Müller, Anna","Zeile 1\nZeile 2"\nBen,"sagt ""Hallo"""\n'
    d = sniff(text)
    rows = parse(text, d)
    assert rows == [["Name", "Notiz"], ["Müller, Anna", "Zeile 1\nZeile 2"], ["Ben", 'sagt "Hallo"']]
    assert parse(serialize(rows, d), d) == rows


def test_roundtrip_keeps_quoting_style_and_trailing_newline() -> None:
    minimal = "a,b\n1,x y\n"
    d = sniff(minimal)
    assert d.quoting == "minimal" and serialize(parse(minimal, d), d) == minimal
    quoted = '"a";"b"\n"1";"2"\n'
    d = sniff(quoted)
    assert d.quoting == "all" and d.delimiter == ";" and serialize(parse(quoted, d), d) == quoted
    no_nl = "a,b\n1,2"
    d = sniff(no_nl)
    assert not d.trailing_newline and serialize(parse(no_nl, d), d) == no_nl


def test_to_number() -> None:
    assert to_number("1234") == 1234 and to_number("-2e3") == -2000
    assert to_number("1.234,56") == 1234.56 and to_number("1,234.56") == 1234.56
    assert to_number("3,5") == 3.5 and to_number("12 %") == 12 and to_number("1.234.567") == 1234567
    for bad in ("abc", "", "1a", "2026-09-26", "+"):
        assert to_number(bad) is None, bad


def test_sort_numeric_and_text_view_only() -> None:
    rows = [["10"], ["9"], ["100"], [""], ["2,5"]]
    order = sorted_indices(rows, list(range(5)), 0)
    assert [rows[i][0] for i in order] == ["2,5", "9", "10", "100", ""]
    assert [rows[i][0] for i in sorted_indices(rows, list(range(5)), 0, descending=True)][0] == ""
    text_rows = [["birne"], ["Apfel"], ["äpfel"], ["Zitrone"]]
    assert [text_rows[i][0] for i in sorted_indices(text_rows, [0, 1, 2, 3], 0)][:2] == ["Apfel", "birne"]
    assert rows[0] == ["10"]                          # Daten selbst unverändert


def test_filter_all_columns_case_insensitive() -> None:
    rows = [["Anna", "Berlin"], ["Ben", "München"], ["Carla", "berlin"]]
    assert filter_indices(rows, [0, 1, 2], "BERLIN") == [0, 2]
    assert filter_indices(rows, [1, 2], "") == [1, 2]


def test_large_file_speed() -> None:
    import time
    text = "id,name,wert\n" + "".join(f"{i},Name {i},{i * 1.5}\n" for i in range(100_000))
    t = time.perf_counter()
    d = sniff(text)
    rows = parse(text, d)
    order = sorted_indices(rows, list(range(1, len(rows))), 2, descending=True)
    out = serialize(rows, d)
    assert len(rows) == 100_001 and rows[order[0]][0] == "99999" and out == text
    assert time.perf_counter() - t < 5
