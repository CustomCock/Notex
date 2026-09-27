from pathlib import Path

import pytest

from notex.core import yara_rules as yr

yara = pytest.importorskip("yara")

RULES = '''
rule Boese_Domain : c2
{
    meta:
        author = "Test"
    strings:
        $d = "evil.example.com" ascii wide nocase
        $mz = { 4D 5A }
    condition:
        $d or $mz at 0
}

rule Immer_Leer
{
    condition:
        filesize == 0
}
'''


def test_compile_errors_have_line_numbers() -> None:
    with pytest.raises(yr.RuleError) as info:
        yr.compile_rules("rule a {\n strings: $x = \"a\"\n condition: $y\n}")
    assert info.value.line == 4 and "undefined string" in info.value.message
    with pytest.raises(yr.RuleError) as info:
        yr.compile_rules("rule a { condition: true }\n\nrule a { condition: true }")
    assert info.value.line == 3 and str(info.value).startswith("Zeile 3:")
    assert yr.parse_error("regel.yar(12): syntax error").line == 12
    assert yr.parse_error("kaputt").line is None


def test_includes_relative_to_rule_folder(tmp_path: Path) -> None:
    (tmp_path / "gemeinsam.yar").write_text('rule Geteilt { strings: $a = "XYZ" condition: $a }', encoding="utf-8")
    rules = yr.compile_rules('include "gemeinsam.yar"\nrule Eigene { condition: true }', tmp_path)
    target = tmp_path / "x.bin"
    target.write_bytes(b"..XYZ..")
    assert {h.rule for h in yr.scan(rules, target).hits} == {"Geteilt", "Eigene"}
    with pytest.raises(yr.RuleError) as info:
        yr.compile_rules('include "fehlt.yar"', tmp_path)
    assert info.value.line == 1


def test_scan_folder_recursive_with_offsets(tmp_path: Path) -> None:
    rules = yr.compile_rules(RULES)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "tief.txt").write_bytes(b"xx EVIL.example.com yy evil.example.com")
    (tmp_path / "prog.exe").write_bytes(b"MZ\x90\x00" + bytes(100))
    (tmp_path / "harmlos.txt").write_text("nichts", encoding="utf-8")
    (tmp_path / "wide.bin").write_bytes("evil.example.com".encode("utf-16-le"))
    (tmp_path / "leer.bin").write_bytes(b"")
    seen = []
    result = yr.scan(rules, tmp_path, progress=lambda d, t: seen.append((d, t)))
    by_file = {(h.file.name, h.identifier, h.offset) for h in result.hits}
    assert ("tief.txt", "$d", 3) in by_file and ("tief.txt", "$d", 23) in by_file
    assert ("prog.exe", "$mz", 0) in by_file and ("wide.bin", "$d", 0) in by_file
    assert result.files == 5 and result.matched_files == 3 and seen[-1] == (5, 5)
    hit = next(h for h in result.hits if h.file.name == "tief.txt")
    assert hit.rule == "Boese_Domain" and hit.tags == ["c2"] and hit.meta == {"author": "Test"}
    assert yr.preview(hit.data) == "EVIL.example.com" and yr.preview(b"MZ\x90") == "4D 5A 90"
    flat = yr.scan(rules, tmp_path, recursive=False)
    assert "tief.txt" not in {h.file.name for h in flat.hits}


def test_rule_without_strings_and_cancel(tmp_path: Path) -> None:
    rules = yr.compile_rules("rule Alles { condition: filesize > 0 }")
    (tmp_path / "x.bin").write_bytes(b"a")
    hits = yr.scan(rules, tmp_path).hits
    assert len(hits) == 1 and hits[0].offset == -1 and hits[0].identifier == ""
    with pytest.raises(yr.Cancelled):
        yr.scan(rules, tmp_path, cancelled=lambda: True)


def test_rule_names() -> None:
    assert yr.rule_names(RULES) == ["Boese_Domain", "Immer_Leer"]
    assert yr.rule_names("private rule A { condition: true }\nglobal rule B { condition: true }") == ["A", "B"]
