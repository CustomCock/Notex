"""Rechtschreibprüfung, ohne Qt: Wörterbücher, Cache, Benutzerwörterbuch, Sitzungs-Ignorierliste.

Backend-Wahl (siehe README): pyenchant mit nativem Hunspell, wenn es sich laden lässt –
das Windows-Wheel bringt enchant + hunspell mit, die Wörterbücher liegen gebündelt in
notex/dictionaries/ und werden über ENCHANT_CONFIG_DIR gefunden. Fällt das aus
(z. B. Linux ohne libenchant), übernimmt spylls, eine reine Python-Implementierung
von Hunspell: gleiche Ergebnisse, aber langsamer, vor allem bei Vorschlägen auf Deutsch.
"""
from __future__ import annotations

import itertools
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Protocol

DICT_DIR = Path(__file__).resolve().parent.parent / "dictionaries"
LANGUAGES = {"de": "de_DE", "en": "en_US"}
LANGUAGE_LABELS = {"de": "Deutsch", "en": "Englisch", "both": "Deutsch + Englisch"}


class Backend(Protocol):
    name: str

    def check(self, word: str) -> bool: ...
    def suggest(self, word: str, limit: int) -> list[str]: ...


# ---- Backend 1: pyenchant / Hunspell ----------------------------------------------
def _prepare_enchant_config() -> Path:
    """Enchant erwartet ENCHANT_CONFIG_DIR/hunspell/<lang>.dic – wir legen die Struktur im Temp an."""
    target = Path(tempfile.gettempdir()) / "notex-enchant" / "hunspell"
    target.mkdir(parents=True, exist_ok=True)
    for source in DICT_DIR.glob("*.*"):
        if source.suffix in (".dic", ".aff"):
            destination = target / source.name
            if not destination.exists() or destination.stat().st_size != source.stat().st_size:
                shutil.copyfile(source, destination)
    return target.parent


class EnchantBackend:
    name = "hunspell"

    def __init__(self, lang: str) -> None:
        os.environ.setdefault("ENCHANT_CONFIG_DIR", str(_prepare_enchant_config()))
        import enchant  # erst jetzt importieren, damit die Umgebungsvariable schon gesetzt ist

        broker = enchant.Broker()
        broker.set_ordering("*", "hunspell,myspell,aspell")
        self._dict = broker.request_dict(LANGUAGES[lang])

    def check(self, word: str) -> bool:
        return bool(self._dict.check(word))

    def suggest(self, word: str, limit: int) -> list[str]:
        return list(self._dict.suggest(word))[:limit]


# ---- Backend 2: spylls (reines Python) ----------------------------------------------
class SpyllsBackend:
    name = "spylls"

    def __init__(self, lang: str) -> None:
        from spylls.hunspell import Dictionary

        self._dict = Dictionary.from_files(str(DICT_DIR / LANGUAGES[lang]))

    def check(self, word: str) -> bool:
        return bool(self._dict.lookup(word))

    def suggest(self, word: str, limit: int) -> list[str]:
        return list(itertools.islice(self._dict.suggest(word), limit))


def load_backend(lang: str, prefer: str | None = None) -> Backend:
    """Erst Hunspell (enchant), dann spylls. `prefer` erzwingt eines der beiden (für Tests)."""
    errors = []
    order = [prefer] if prefer else ["hunspell", "spylls"]
    for name in order:
        try:
            if name == "hunspell":
                return EnchantBackend(lang)
            if name == "spylls":
                return SpyllsBackend(lang)
            raise ValueError(f"unbekanntes Backend {name!r}")
        except Exception as error:  # noqa: BLE001 – Import- oder Ladefehler: nächstes Backend
            errors.append(f"{name}: {error}")
    raise RuntimeError("Kein Rechtschreib-Backend verfügbar: " + "; ".join(errors))


# ---- Die Prüfung selbst -------------------------------------------------------------
class SpellChecker:
    """Prüft Wörter gegen ein oder zwei Sprachen, mit Cache und Benutzerwörterbuch.

    language: "de", "en" oder "both". Ein Wort gilt als richtig, wenn es in irgendeiner
    der aktiven Sprachen richtig ist.
    """

    def __init__(self, user_dictionary: Path | None = None, prefer_backend: str | None = None) -> None:
        self.user_dictionary = user_dictionary
        self._prefer = prefer_backend
        self._backends: dict[str, Backend] = {}
        self._cache: dict[tuple[str, str], bool] = {}
        self._user_words: set[str] = set()
        self._session_ignored: set[str] = set()
        self.language = "de"
        self.load_error: str | None = None
        self._load_user_words()

    # ---- Sprachen / Backends ---------------------------------------------------------
    def set_language(self, language: str) -> None:
        if language in ("de", "en", "both"):
            self.language = language

    def active_languages(self, language: str | None = None) -> list[str]:
        language = language or self.language
        return ["de", "en"] if language == "both" else [language]

    def _backend(self, lang: str) -> Backend | None:
        if lang not in self._backends:
            try:
                self._backends[lang] = load_backend(lang, self._prefer)
            except RuntimeError as error:
                self.load_error = str(error)
                self._backends[lang] = None  # type: ignore[assignment]
        return self._backends[lang]

    def backend_name(self) -> str:
        for backend in self._backends.values():
            if backend is not None:
                return backend.name
        return "-"

    def preload(self, language: str | None = None) -> None:
        for lang in self.active_languages(language):
            self._backend(lang)

    # ---- Prüfen ---------------------------------------------------------------------
    def is_correct(self, word: str, language: str | None = None) -> bool:
        if word in self._session_ignored or word in self._user_words or word.lower() in self._user_words:
            return True
        language = language or self.language
        key = (language, word)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = False
        for lang in self.active_languages(language):
            backend = self._backend(lang)
            if backend is None:
                result = True   # ohne Wörterbuch lieber nichts anstreichen
                break
            try:
                if backend.check(word):
                    result = True
                    break
            except Exception:  # noqa: BLE001 – Encoding-Sonderfälle im Backend
                result = True
                break
        self._cache[key] = result
        return result

    def suggestions(self, word: str, limit: int = 5, language: str | None = None) -> list[str]:
        seen: list[str] = []
        for lang in self.active_languages(language):
            backend = self._backend(lang)
            if backend is None:
                continue
            try:
                for suggestion in backend.suggest(word, limit):
                    if suggestion not in seen:
                        seen.append(suggestion)
            except Exception:  # noqa: BLE001
                continue
            if len(seen) >= limit:
                break
        return seen[:limit]

    # ---- Benutzerwörterbuch / Ignorieren ---------------------------------------------
    def _load_user_words(self) -> None:
        if self.user_dictionary and self.user_dictionary.exists():
            try:
                lines = self.user_dictionary.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            self._user_words = {line.strip() for line in lines if line.strip() and not line.startswith("#")}

    def add_to_dictionary(self, word: str) -> None:
        word = word.strip()
        if not word:
            return
        self._user_words.add(word)
        self._forget(word)
        if self.user_dictionary:
            try:
                self.user_dictionary.parent.mkdir(parents=True, exist_ok=True)
                with open(self.user_dictionary, "a", encoding="utf-8", newline="\n") as handle:
                    handle.write(word + "\n")
            except OSError:
                pass

    def ignore_for_session(self, word: str) -> None:
        self._session_ignored.add(word)
        self._forget(word)

    def user_words(self) -> Iterable[str]:
        return sorted(self._user_words)

    def _forget(self, word: str) -> None:
        for key in [k for k in self._cache if k[1] == word]:
            del self._cache[key]
