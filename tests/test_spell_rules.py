from notex.core.spell_rules import is_code_fence, should_check, tokenize


def words(line: str) -> list[str]:
    return [t.text for t in tokenize(line)]


def test_plain_words_with_positions() -> None:
    tokens = tokenize("Hallo schöne Welt")
    assert [(t.text, t.start, t.end) for t in tokens] == [("Hallo", 0, 5), ("schöne", 6, 12), ("Welt", 13, 17)]


def test_urls_emails_and_paths_are_skipped() -> None:
    assert words("Siehe https://example.com/pfad?x=1 und www.test.de bitte") == ["Siehe", "und", "bitte"]
    assert words("Mail an max.mustermann@example.org heute") == ["Mail", "an", "heute"]
    assert words(r"Datei C:\Users\max\notizen.txt öffnen") == ["Datei", "öffnen"]
    assert words("Pfad /usr/local/bin und ./relativ/datei.md sowie data/Projekte/x.txt") == ["Pfad", "und", "sowie"]


def test_hex_hashes_digits_and_uuid_are_skipped() -> None:
    assert words("Commit a631329f1 und 0xDEADBEEF fertig") == ["Commit", "und", "fertig"]
    assert words("Version v2 und abc123 sowie 42 Zeilen") == ["Version", "und", "sowie", "Zeilen"]
    assert words("Id 123e4567-e89b-12d3-a456-426614174000 ok") == ["Id", "ok"]


def test_abbreviations_camel_and_snake_case_are_skipped() -> None:
    assert words("Die GPL und HTTP sind ALLCAPS") == ["Die", "und", "sind"]
    assert words("notexApp und NotexApp bleiben, Notex wird geprüft") == ["und", "bleiben", "Notex", "wird", "geprüft"]
    assert words("snake_case_wort und _privat bleiben weg") == ["und", "bleiben", "weg"]


def test_inline_code_is_skipped() -> None:
    assert words("Ein `@dataclass` erzeugt `__init__` automatisch") == ["Ein", "erzeugt", "automatisch"]


def test_apostrophes_and_hyphens_stay_inside_words() -> None:
    assert words("Rock 'n' Roll, don't Grün-Blau") == ["Rock", "Roll", "don't", "Grün-Blau"]


def test_single_letters_are_skipped() -> None:
    assert words("a b Ähm") == ["Ähm"]
    assert should_check("x") is False


def test_code_fence_detection() -> None:
    assert is_code_fence("```python") and is_code_fence("   ~~~") and not is_code_fence("kein `code` hier")
