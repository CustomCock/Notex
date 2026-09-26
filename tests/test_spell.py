from pathlib import Path

import pytest

from notex.core.spell import DICT_DIR, SpellChecker, load_backend


@pytest.fixture(scope="module")
def checker() -> SpellChecker:
    sc = SpellChecker()
    sc.set_language("both")
    sc.preload()
    if sc.load_error:
        pytest.skip(f"kein Backend: {sc.load_error}")
    return sc


def test_dictionaries_are_bundled() -> None:
    for lang in ("de_DE", "en_US"):
        assert (DICT_DIR / f"{lang}.dic").exists() and (DICT_DIR / f"{lang}.aff").exists()


def test_german_and_english(checker: SpellChecker) -> None:
    assert checker.is_correct("Haus", "de")
    assert checker.is_correct("Rechtschreibprüfung", "de")
    assert not checker.is_correct("Rechtschreibprüfunk", "de")
    assert checker.is_correct("house", "en")
    assert not checker.is_correct("hause", "en")


def test_both_languages_accept_either(checker: SpellChecker) -> None:
    assert checker.is_correct("Haus", "both")
    assert checker.is_correct("house", "both")
    assert not checker.is_correct("Hausse123x", "both")


def test_suggestions(checker: SpellChecker) -> None:
    suggestions = checker.suggestions("Fehlerr", limit=5, language="de")
    assert 1 <= len(suggestions) <= 5
    assert "Fehler" in suggestions


def test_user_dictionary_and_session_ignore(tmp_path: Path) -> None:
    path = tmp_path / "user_dictionary.txt"
    sc = SpellChecker(user_dictionary=path)
    sc.set_language("de")
    sc.preload()
    if sc.load_error:
        pytest.skip(sc.load_error)
    assert not sc.is_correct("Notexwort")
    sc.add_to_dictionary("Notexwort")
    assert sc.is_correct("Notexwort")
    assert path.read_text(encoding="utf-8").strip() == "Notexwort"
    # neue Instanz liest die Datei
    sc2 = SpellChecker(user_dictionary=path)
    assert "Notexwort" in list(sc2.user_words())
    sc.ignore_for_session("Blubberwort")
    assert sc.is_correct("Blubberwort")


def test_missing_backend_never_marks(monkeypatch: pytest.MonkeyPatch) -> None:
    sc = SpellChecker(prefer_backend="gibtsnicht")
    assert sc.is_correct("Xyzzy") is True   # ohne Wörterbuch lieber nichts anstreichen
    assert sc.load_error


def test_spylls_backend_directly() -> None:
    pytest.importorskip("spylls")
    backend = load_backend("en", prefer="spylls")
    assert backend.check("house") and not backend.check("hause")
    assert "house" in backend.suggest("hause", 5)
