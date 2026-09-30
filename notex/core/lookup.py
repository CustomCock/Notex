"""Nachschlagen: Wikipedia und Wiktionary per API, Websuche nur als Browser-Link. Ohne Qt.

Keine KI, kein Scraping – nur die offiziellen Wikimedia-APIs:
  Wikipedia   REST  /api/rest_v1/page/summary/{Titel}            Titel, Kurzbeschreibung, Auszug, Bild
              Action /w/api.php?action=opensearch                 unscharfe Begriffe → bester Treffer
              Action /w/api.php?action=parse&prop=wikitext        Optionen einer Begriffsklärungsseite
  Wiktionary  Action /w/api.php?action=parse&prop=wikitext        für DE und EN (siehe unten)
              Action /w/api.php?action=opensearch                 Schreibvarianten

Warum für Wiktionary die Action-API mit Wikitext und nicht die REST-Definition-API?
  Die REST-API /page/definition gibt es nur auf en.wiktionary und sie liefert weder Herkunft noch Aussprache.
  action=parse gibt es auf jedem Wiki gleich (MediaWiki-Kern, stabil), folgt Weiterleitungen, und der
  Wikitext hat auf beiden Wikis feste, dokumentierte Abschnittsmuster:
    de: == Wort ({{Sprache|Deutsch}}) ==  /  === {{Wortart|Substantiv|Deutsch}} ===  /  {{Bedeutungen}} :[1] …
        {{Aussprache}} :{{IPA}} {{Lautschrift|…}}  /  {{Herkunft}} :…
    en: ==English==  /  ===Etymology===  /  ===Pronunciation=== * {{IPA|en|/…/}}  /  ===Noun=== # …
  Daraus liest je ein kleiner Parser Wortarten, Bedeutungen, IPA und Herkunft; clean_wikitext() macht aus dem
  Markup lesbaren Text (Vorlagen werden übersetzt oder entfernt, nie roh angezeigt).

Etikette (https://meta.wikimedia.org/wiki/User-Agent_policy): eigener User-Agent mit Kontakt-URL, eine Anfrage
nach der anderen, kein Vorladen, Ergebnisse pro Sitzung zwischengespeichert, Timeout 5 s.
"""
from __future__ import annotations

import json
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from notex import APP_NAME, REPO_URL, __version__

USER_AGENT = f"{APP_NAME}/{__version__} ({REPO_URL})"
TIMEOUT = 5.0
MAX_BYTES = 2 * 1024 * 1024
MAX_TERM = 200
LANGS = ("de", "en")
WIKIPEDIA_BASE = "https://{lang}.wikipedia.org"
WIKTIONARY_BASE = "https://{lang}.wiktionary.org"

SEARCH_ENGINES: dict[str, tuple[str, str]] = {
    "google": ("Google", "https://www.google.com/search?q={q}"),
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={q}"),
    "startpage": ("Startpage", "https://www.startpage.com/do/search?q={q}"),
}


# ---- Fehler --------------------------------------------------------------------------------------

class LookupError_(Exception):
    """Basis; `kind` steuert den Text in der Karte."""
    kind = "error"


class NotFound(LookupError_):
    kind = "not_found"


class RateLimited(LookupError_):
    kind = "rate_limit"


class Offline(LookupError_):
    kind = "offline"


class Timeout(LookupError_):
    kind = "timeout"


class InvalidResponse(LookupError_):
    kind = "invalid"


ERROR_TEXTS = {
    "not_found": "Nichts gefunden.",
    "rate_limit": "Zu viele Anfragen – der Dienst bittet um eine Pause. Bitte gleich noch einmal versuchen.",
    "offline": "Keine Verbindung. Offline oder blockiert ein Proxy den Zugriff?",
    "timeout": "Keine Antwort innerhalb von 5 Sekunden.",
    "invalid": "Die Antwort des Dienstes war nicht lesbar.",
    "error": "Nachschlagen fehlgeschlagen.",
}


# ---- Begriffe und URLs --------------------------------------------------------------------------

def prepare_term(text: str) -> str:
    """Markierung → Suchbegriff: Zeilenumbrüche zu Leerzeichen, Leerraum zusammenfassen, getrimmt, max. 200 Zeichen."""
    term = re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()
    if len(term) > MAX_TERM:
        term = term[:MAX_TERM].rstrip()
    return term


def menu_label(term: str, limit: int = 30) -> str:
    """Begriff für den Menütext: „Begriff“, bei Überlänge gekürzt mit …"""
    short = term if len(term) <= limit else term[: limit - 1].rstrip() + "…"
    return f"„{short}“"


def _title_path(title: str) -> str:
    return urllib.parse.quote(title.replace(" ", "_"), safe="")


def wikipedia_article_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{_title_path(title)}"


def wikipedia_search_url(lang: str, term: str) -> str:
    return f"https://{lang}.wikipedia.org/w/index.php?" + urllib.parse.urlencode({"search": term})


def wiktionary_url(lang: str, title: str) -> str:
    return f"https://{lang}.wiktionary.org/wiki/{_title_path(title)}"


def wiktionary_search_url(lang: str, term: str) -> str:
    return f"https://{lang}.wiktionary.org/w/index.php?" + urllib.parse.urlencode({"search": term})


def search_url(term: str, engine: str = "google", custom: str = "") -> str:
    """Browser-URL der Websuche. Eigene URL: {q} wird ersetzt, ohne {q} wird der Begriff angehängt."""
    q = urllib.parse.quote_plus(term)
    if engine == "custom" and custom.strip():
        template = custom.strip()
        if "{q}" in template:
            return template.replace("{q}", q)
        return template + q if template.endswith(("=", "/", "?", "&")) else template + ("&" if "?" in template else "?") + "q=" + q
    return SEARCH_ENGINES.get(engine, SEARCH_ENGINES["google"])[1].replace("{q}", q)


def search_engine_name(engine: str = "google", custom: str = "") -> str:
    if engine == "custom" and custom.strip():
        host = urllib.parse.urlsplit(custom.strip().replace("{q}", "x")).hostname or ""
        return host.removeprefix("www.") or "Web"
    return SEARCH_ENGINES.get(engine, SEARCH_ENGINES["google"])[0]


def search_menu_text(term: str, engine: str = "google", custom: str = "") -> str:
    name = search_engine_name(engine, custom)
    return f"Bei {name} suchen: {menu_label(term)}" if name != "Web" else f"Im Web suchen: {menu_label(term)}"


def languages_for(preference: str, tab_language: str | None) -> list[str]:
    """Reihenfolge der Sprachen: bevorzugte zuerst, dann die andere als Fallback."""
    first = preference if preference in LANGS else (tab_language if tab_language in LANGS else "de")
    return [first] + [lang for lang in LANGS if lang != first]


# ---- HTTP ---------------------------------------------------------------------------------------

Fetch = Callable[[str], Any]


def fetch_json(url: str, timeout: float = TIMEOUT) -> Any:
    """GET mit User-Agent; bildet Netzfehler auf die LookupError_-Arten ab."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Api-User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise NotFound(str(error)) from error
        if error.code == 429:
            raise RateLimited(str(error)) from error
        raise LookupError_(f"HTTP {error.code}") from error
    except (socket.timeout, TimeoutError) as error:
        raise Timeout(str(error)) from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise Timeout(str(error)) from error
        raise Offline(str(error.reason)) from error
    except OSError as error:
        raise Offline(str(error)) from error
    if len(data) > MAX_BYTES:
        raise InvalidResponse("Antwort zu groß")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise InvalidResponse(str(error)) from error


def fetch_bytes(url: str, timeout: float = TIMEOUT, limit: int = 512 * 1024) -> bytes:
    """Für Vorschaubilder (nur wenn in den Einstellungen erlaubt)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, OSError) as error:
        raise Offline(str(error)) from error
    if len(data) > limit:
        raise InvalidResponse("Bild zu groß")
    return data


# ---- Ergebnisse ---------------------------------------------------------------------------------

@dataclass
class Summary:
    source: str          # "wikipedia"
    lang: str
    title: str
    description: str
    extract: str
    url: str
    thumbnail: str = ""


@dataclass
class Disambiguation:
    source: str
    lang: str
    title: str
    options: list[tuple[str, str]]   # (Zieltitel, kurze Beschreibung)
    url: str


@dataclass
class PartOfSpeech:
    name: str
    meanings: list[str] = field(default_factory=list)


@dataclass
class Definition:
    source: str          # "wiktionary"
    lang: str
    title: str
    language_name: str   # Sprache des Eintrags („Deutsch“, „English“ …)
    parts: list[PartOfSpeech]
    ipa: str
    etymology: str
    url: str


# ---- Wiki-Markup bereinigen --------------------------------------------------------------------

_GENDER = {"m": "m", "f": "f", "n": "n", "mf": "m/f", "p": "Plural"}
_DE_ABBR = {"ugs.": "umgangssprachlich", "Pl.": "Plural", "Sg.": "Singular", "Gen.": "Genitiv", "fachspr.": "fachsprachlich",
            "veraltet": "veraltet", "übertr.": "übertragen", "va.": "veraltet", "reg.": "regional", "trans.": "transitiv",
            "intrans.": "intransitiv", "refl.": "reflexiv", "Dativ": "Dativ", "Akkusativ": "Akkusativ",
            "österr.": "österreichisch", "schweiz.": "schweizerisch", "südd.": "süddeutsch", "norddt.": "norddeutsch"}
_EN_LANG_ARG2 = {"inh", "der", "bor", "cog", "ncog", "lbor", "slbor", "uder", "calque", "affix", "af", "prefix", "suffix",
                 "compound", "blend", "etyl"}


def _args(inner: str) -> tuple[str, list[str], dict[str, str]]:
    parts = inner.split("|")
    name = parts[0].strip()
    positional, named = [], {}
    for part in parts[1:]:
        key, sep, value = part.partition("=")
        if sep and re.fullmatch(r"[\w\s-]+", key.strip()) and not key.strip().isdigit():
            named[key.strip()] = value.strip()
        else:
            positional.append(part.strip())
    return name, positional, named


def _template(inner: str) -> str:
    """Eine Vorlage (ohne {{ }}) in Text übersetzen; Unbekanntes verschwindet."""
    name, pos, named = _args(inner)
    low = name.lower().rstrip("+")          # {{inh+|…}}, {{bor+|…}}: gleiche Argumente wie ohne +
    if name in ("Lautschrift", "IPA-Text"):
        return pos[0] if pos else ""
    if low in ("ipa", "ipachar") and len(pos) >= 2:           # en: {{IPA|en|/haʊs/|/hɔʊs/}}
        return ", ".join(p for p in pos[1:] if p)
    if name == "IPA":                                          # de: {{IPA}} = Beschriftung
        return ""
    if low in ("lb", "lbl", "label", "lbe"):
        labels = [p for p in pos[1:] if p and p not in ("_", "and", "or")]
        return f"({', '.join(labels)})" if labels else ""
    if name == "K":                                            # de: {{K|ugs.|Tiere}} → (umgangssprachlich, Tiere):
        labels = [_DE_ABBR.get(p, p) for p in pos if p]
        return f"({', '.join(labels)}):" if labels else ""
    if low in ("gloss", "gl"):
        return f"({pos[0]})" if pos else ""
    if low in ("q", "qualifier", "i", "qual", "qf", "sense", "s"):
        return f"({', '.join(p for p in pos if p)})" if pos else ""
    if low in ("l", "m", "l-self", "ll", "mention", "link"):   # {{l|en|word|alt}} → alt oder word
        return (pos[2] if len(pos) > 2 and pos[2] else pos[1]) if len(pos) > 1 else ""
    if low in _EN_LANG_ARG2:                                   # {{inh|en|enm|hous}} → hous
        return pos[2] if len(pos) > 2 else ""
    if low in ("w", "wikipedia", "pedia"):
        return pos[-1] if pos else ""
    if name in ("Ü", "Üt", "Wikipedia", "W", "Ref-Duden"):
        return pos[1] if name in ("Ü", "Üt") and len(pos) > 1 else (pos[0] if name in ("Wikipedia", "W") and pos else "")
    if name in _GENDER:
        return _GENDER[name]
    if name in _DE_ABBR:
        return _DE_ABBR[name]
    if low in ("taxlink", "taxfmt", "vern"):
        return pos[0] if pos else ""
    if low in ("non-gloss definition", "n-g", "ngd", "non-gloss"):
        return pos[0] if pos else ""
    if low in ("form of", "plural of", "alternative form of", "alt form", "past participle of", "inflection of",
               "synonym of", "abbreviation of", "misspelling of", "obsolete form of"):
        target = pos[1] if len(pos) > 1 else ""
        return f"{name.replace(' of', '')} of {target}".strip()
    return ""


def clean_wikitext(text: str) -> str:
    """Wiki-Markup → lesbarer Text: Vorlagen übersetzen/entfernen (innen nach außen), Links, Fett/Kursiv, HTML."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>/]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    for _ in range(12):                                   # verschachtelte Vorlagen: innerste zuerst
        new = re.sub(r"\{\{([^{}]*)\}\}", lambda m: _template(m.group(1)), text)
        if new == text:
            break
        text = new
    text = re.sub(r"\{\{|\}\}", "", text)                 # Reste kaputter Vorlagen
    text = re.sub(r"\[\[(?:Datei|File|Bild|Image|Kategorie|Category):[^\]]*\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", "", text)
    text = re.sub(r"'{2,5}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip(" ,;")


# ---- Wikipedia ---------------------------------------------------------------------------------

class WikipediaClient:
    def __init__(self, fetch: Fetch = fetch_json, base: str = WIKIPEDIA_BASE) -> None:
        self.fetch, self.base = fetch, base

    def _api(self, lang: str, **params: str) -> str:
        return self.base.format(lang=lang) + "/w/api.php?" + urllib.parse.urlencode({**params, "format": "json"})

    def summary(self, title: str, lang: str) -> Summary | Disambiguation:
        data = self.fetch(self.base.format(lang=lang) + "/api/rest_v1/page/summary/" + _title_path(title) + "?redirect=true")
        if not isinstance(data, dict) or not data.get("title"):
            raise InvalidResponse("Antwort ohne Titel")
        real = str(data.get("title"))
        url = str(((data.get("content_urls") or {}).get("desktop") or {}).get("page") or wikipedia_article_url(lang, real))
        if data.get("type") == "disambiguation":
            return Disambiguation("wikipedia", lang, real, self.disambiguation_options(real, lang), url)
        return Summary("wikipedia", lang, real, str(data.get("description") or ""), str(data.get("extract") or ""), url,
                       str((data.get("thumbnail") or {}).get("source") or ""))

    def search(self, term: str, lang: str, limit: int = 5) -> list[str]:
        data = self.fetch(self._api(lang, action="opensearch", search=term, limit=str(limit), namespace="0",
                                    redirects="resolve"))
        if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
            raise InvalidResponse("opensearch: unerwartetes Format")
        return [str(t) for t in data[1] if t]

    def disambiguation_options(self, title: str, lang: str, limit: int = 15) -> list[tuple[str, str]]:
        try:
            data = self.fetch(self._api(lang, action="parse", page=title, prop="wikitext", formatversion="2", redirects="1"))
            wikitext = str(((data or {}).get("parse") or {}).get("wikitext") or "")
        except LookupError_:
            return []
        options: list[tuple[str, str]] = []
        for line in wikitext.splitlines():
            m = re.match(r"^\*+\s*(.*)$", line)
            if not m:
                continue
            link = re.search(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]", m.group(1))
            if not link or ":" in link.group(1):
                continue
            target = link.group(1).strip()
            rest = clean_wikitext(m.group(1)[link.end():]).strip(" ,–-:")
            if target and all(target != t for t, _ in options):
                options.append((target, rest[:140]))
            if len(options) >= limit:
                break
        return options

    def lookup(self, term: str, lang: str) -> Summary | Disambiguation:
        """Exakter Titel, sonst bester Treffer der Suche."""
        try:
            return self.summary(term, lang)
        except NotFound:
            pass
        hits = self.search(term, lang)
        if not hits:
            raise NotFound(term)
        return self.summary(hits[0], lang)


# ---- Wiktionary --------------------------------------------------------------------------------

DE_POS_RE = re.compile(r"^===\s*\{\{Wortart\|([^|}]+)")
DE_LANG_RE = re.compile(r"^==\s*[^=].*\{\{Sprache\|([^}]+)\}\}")
EN_POS = {"Noun", "Verb", "Adjective", "Adverb", "Pronoun", "Preposition", "Conjunction", "Interjection", "Numeral",
          "Article", "Determiner", "Particle", "Proper noun", "Phrase", "Prefix", "Suffix", "Proverb", "Idiom",
          "Contraction", "Abbreviation", "Initialism", "Acronym", "Symbol", "Letter", "Postposition", "Participle"}


def _de_block(lines: list[str], start: int) -> list[str]:
    """Zeilen eines {{Abschnitt}}-Blocks bis zum nächsten {{…}}-Blockkopf oder Überschrift."""
    out = []
    for line in lines[start + 1:]:
        if re.match(r"^\{\{[^}]+\}\}\s*$", line) or line.startswith("="):
            break
        out.append(line)
    return out


def parse_de_wiktionary(wikitext: str, prefer: str = "Deutsch") -> tuple[str, list[PartOfSpeech], str, str]:
    """(Sprache, Wortarten mit Bedeutungen, IPA, Herkunft) aus de.wiktionary-Wikitext."""
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in wikitext.splitlines():
        m = DE_LANG_RE.match(line)
        if m:
            current = []
            sections.append((m.group(1).strip(), current))
        elif current is not None:
            current.append(line)
    if not sections:
        return "", [], "", ""
    language, lines = next((s for s in sections if s[0] == prefer), sections[0])
    parts: list[PartOfSpeech] = []
    ipa = etymology = ""
    for index, line in enumerate(lines):
        if DE_POS_RE.match(line):
            names = [n.strip() for n in re.findall(r"\{\{Wortart\|([^|}]+)", line)]
            parts.append(PartOfSpeech(", ".join(dict.fromkeys(names))))
            continue
        stripped = line.strip()
        if stripped == "{{Bedeutungen}}" and parts:
            for entry in _de_block(lines, index):
                mm = re.match(r"^:+\s*\[([\d\w.,–-]*)\]\s*(.*)$", entry)
                if mm and mm.group(2).strip():
                    text = clean_wikitext(mm.group(2))
                    if text and entry.startswith(":") and not entry.startswith("::"):
                        parts[-1].meanings.append(text)
        elif stripped == "{{Aussprache}}" and not ipa:
            for entry in _de_block(lines, index):
                if "{{IPA}}" in entry:
                    ipa = clean_wikitext(entry.lstrip(":")).strip(" ,")
                    break
        elif stripped == "{{Herkunft}}" and not etymology:
            text = " ".join(clean_wikitext(e.lstrip(":")) for e in _de_block(lines, index) if e.strip())
            etymology = re.sub(r"^\[\d+\]\s*", "", text).strip()
    return language, [p for p in parts if p.meanings], ipa, etymology


def parse_en_wiktionary(wikitext: str, prefer: str = "English") -> tuple[str, list[PartOfSpeech], str, str]:
    """(Sprache, Wortarten mit Bedeutungen, IPA, Herkunft) aus en.wiktionary-Wikitext."""
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in wikitext.splitlines():
        m = re.match(r"^==\s*([^=][^=]*?)\s*==\s*$", line)
        if m:
            current = []
            sections.append((m.group(1).strip(), current))
        elif current is not None:
            current.append(line)
    if not sections:
        return "", [], "", ""
    language, lines = next((s for s in sections if s[0] == prefer), sections[0])
    parts: list[PartOfSpeech] = []
    ipa = etymology = ""
    heading = ""
    for line in lines:
        m = re.match(r"^(={3,6})\s*(.+?)\s*\1\s*$", line)
        if m:
            heading = re.sub(r"\s+\d+$", "", m.group(2))
            if heading in EN_POS:
                parts.append(PartOfSpeech(heading))
            continue
        if heading == "Etymology" and not etymology and line.strip() and not line.startswith(("*", "[[Datei", "[[File")):
            etymology = clean_wikitext(line)   # erste Zeile, die nach dem Bereinigen Text enthält ({{root|…}} fällt weg)
        elif heading == "Pronunciation" and not ipa and "{{IPA|" in line:
            ipa = clean_wikitext(re.sub(r"^\*+\s*", "", line))
        elif heading in EN_POS and parts and re.match(r"^#(?![:*#])", line):
            text = clean_wikitext(line.lstrip("#").strip())
            if text:
                parts[-1].meanings.append(text)
    return language, [p for p in parts if p.meanings], ipa, etymology


class WiktionaryClient:
    def __init__(self, fetch: Fetch = fetch_json, base: str = WIKTIONARY_BASE) -> None:
        self.fetch, self.base = fetch, base

    def _api(self, lang: str, **params: str) -> str:
        return self.base.format(lang=lang) + "/w/api.php?" + urllib.parse.urlencode({**params, "format": "json"})

    def _wikitext(self, title: str, lang: str) -> tuple[str, str] | None:
        data = self.fetch(self._api(lang, action="parse", page=title, prop="wikitext", formatversion="2", redirects="1"))
        if not isinstance(data, dict):
            raise InvalidResponse("parse: unerwartetes Format")
        if "error" in data:
            if (data["error"] or {}).get("code") in ("missingtitle", "invalidtitle"):
                return None
            raise LookupError_(str((data["error"] or {}).get("info") or "API-Fehler"))
        parse = data.get("parse") or {}
        return str(parse.get("title") or title), str(parse.get("wikitext") or "")

    def lookup(self, term: str, lang: str) -> Definition:
        candidates = [term]
        for variant in (term.lower(), term[:1].upper() + term[1:]):
            if variant not in candidates:
                candidates.append(variant)
        for title in candidates:
            found = self._wikitext(title, lang)
            if found is not None:
                definition = self._definition(found[0], found[1], lang)
                if definition is not None:
                    return definition
        # letzte Chance: Suche (Tippfehler, andere Schreibung) – nur der beste Treffer, eine Anfrage
        data = self.fetch(self._api(lang, action="opensearch", search=term, limit="1", namespace="0"))
        if isinstance(data, list) and len(data) > 1 and data[1] and data[1][0] not in candidates:
            found = self._wikitext(str(data[1][0]), lang)
            if found is not None:
                definition = self._definition(found[0], found[1], lang)
                if definition is not None:
                    return definition
        raise NotFound(term)

    def _definition(self, title: str, wikitext: str, lang: str) -> Definition | None:
        if lang == "de":
            language, parts, ipa, ety = parse_de_wiktionary(wikitext)
        else:
            language, parts, ipa, ety = parse_en_wiktionary(wikitext)
        if not parts:
            return None
        return Definition("wiktionary", lang, title, language, parts, ipa, ety[:600], wiktionary_url(lang, title))


# ---- Fallback, Cache, Dienst --------------------------------------------------------------------

def with_fallback(lookup: Callable[[str, str], Any], term: str, langs: list[str]) -> Any:
    """In der ersten Sprache nachschlagen, bei „nicht gefunden“ in der nächsten. Andere Fehler brechen ab."""
    last: LookupError_ = NotFound(term)
    for lang in langs:
        try:
            return lookup(term, lang)
        except NotFound as error:
            last = error
    raise last


class LookupService:
    """Clients + Sitzungs-Cache (Begriff + Sprachen + Quelle). Thread-sicher, eine Anfrage nach der anderen."""

    def __init__(self, fetch: Fetch = fetch_json, wikipedia_base: str = WIKIPEDIA_BASE,
                 wiktionary_base: str = WIKTIONARY_BASE) -> None:
        self.wikipedia = WikipediaClient(fetch, wikipedia_base)
        self.wiktionary = WiktionaryClient(fetch, wiktionary_base)
        self._cache: dict[tuple[str, str, str], Any] = {}
        self._lock = threading.Lock()
        self._request_lock = threading.Lock()   # kein paralleles Anfragen, auch bei schnellem Klicken

    def cached(self, source: str, term: str, langs: list[str]) -> Any | None:
        with self._lock:
            return self._cache.get((source, term.casefold(), ",".join(langs)))

    def lookup(self, source: str, term: str, langs: list[str]) -> Any:
        key = (source, term.casefold(), ",".join(langs))
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        with self._request_lock:
            if source == "wikipedia":
                result = with_fallback(self.wikipedia.lookup, term, langs)
            elif source == "wikipedia-article":        # Klick auf eine Option der Begriffsklärung
                result = self.wikipedia.summary(term, langs[0])
            else:
                result = with_fallback(self.wiktionary.lookup, term, langs)
        with self._lock:
            self._cache[key] = result
        return result


# ---- .ntx-Bestätigung ---------------------------------------------------------------------------

class SendGuard:
    """Vor dem Senden eines Begriffs aus einer verschlüsselten Notiz fragen – bis „nicht mehr fragen“."""

    def __init__(self) -> None:
        self.skip = False

    def needs_confirmation(self, encrypted: bool) -> bool:
        return encrypted and not self.skip

    def remember(self) -> None:
        self.skip = True


def confirmation_text(service: str) -> str:
    return f"Der Begriff wird an {service} gesendet und kann im Browserverlauf landen. Fortfahren?"


# ---- Kartenplatzierung --------------------------------------------------------------------------

def place_card(anchor: tuple[int, int, int, int], size: tuple[int, int], bounds: tuple[int, int, int, int],
               gap: int = 6, margin: int = 8, min_height: int = 120) -> tuple[int, int, int]:
    """Position (x, y) und Höhe der Karte neben der Markierung `anchor` = (x, y, w, h) innerhalb `bounds`.

    Unterhalb, wenn die Karte dort passt; sonst oberhalb; passt sie nirgends ganz, auf die Seite mit mehr Platz
    und in der Höhe gekürzt (Inhalt scrollt). Die Karte überdeckt die Markierung nie. x wird an den Rändern
    eingegrenzt."""
    ax, ay, aw, ah = anchor
    bx, by, bw, bh = bounds
    width, height = size
    below_space = (by + bh - margin) - (ay + ah + gap)
    above_space = (ay - gap) - (by + margin)
    if height <= below_space:
        y, h = ay + ah + gap, height
    elif height <= above_space:
        y, h = ay - gap - height, height
    elif below_space >= above_space:
        h = max(min(height, below_space), min(min_height, height))
        y = ay + ah + gap
    else:
        h = max(min(height, above_space), min(min_height, height))
        y = ay - gap - h
    x = max(bx + margin, min(ax, bx + bw - margin - width))
    return x, y, h
