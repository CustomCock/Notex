"""Nachschlagen: Clients gegen einen lokalen Fake-Server, Markup-Bereinigung, URLs, Platzierung, .ntx-Schutz."""
import functools
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from notex import APP_NAME

from notex.core.lookup import (Definition, Disambiguation, InvalidResponse, LookupService, NotFound, Offline,
                               RateLimited, SendGuard, Summary, Timeout, WikipediaClient, WiktionaryClient,
                               clean_wikitext, confirmation_text, fetch_json, languages_for, menu_label, place_card,
                               prepare_term, search_engine_name, search_menu_text, search_url, wikipedia_article_url,
                               wikipedia_search_url, wiktionary_url, with_fallback)

DE_HAUS = """{{Siehe auch|[[haus]]}}
== Haus ({{Sprache|Deutsch}}) ==
=== {{Wortart|Substantiv|Deutsch}}, {{n}} ===
{{Deutsch Substantiv Übersicht
|Genus=n
|Nominativ Singular=Haus
}}
{{Worttrennung}}
:Haus, {{Pl.}} Häu·ser
{{Aussprache}}
:{{IPA}} {{Lautschrift|haʊ̯s}}, {{Pl.}} {{Lautschrift|ˈhɔɪ̯zɐ}}
:{{Hörbeispiele}} {{Audio|De-Haus.ogg}}
{{Bedeutungen}}
:[1] [[Gebäude]], das [[Mensch]]en zum [[Wohnen]] dient<ref>{{Ref-Duden|Haus}}</ref>
:[2] {{K|übertr.}} alle [[Bewohner]] eines Hauses
::[2a] Unterbedeutung, die nicht zählt
:[3] {{K|Astrologie}} einer der zwölf Abschnitte des Tierkreises
:[4] Dynastie, [[Adelsgeschlecht]]
:[5] ''Theater:'' Spielstätte
:[6] Firma, Unternehmen
{{Herkunft}}
:[[mittelhochdeutsch]] ''{{Ü|gmh|hūs}}'', [[althochdeutsch]] ''{{Ü|goh|hūs}}''<ref>Kluge</ref>
{{Synonyme}}
:[1] [[Gebäude]]
== Haus ({{Sprache|Englisch}}) ==
=== {{Wortart|Substantiv|Englisch}} ===
{{Bedeutungen}}
:[1] englisch
"""

EN_HOUSE = """{{also|House}}
==English==
{{wikipedia}}
===Etymology 1===
From {{inh|en|enm|hous}}, from {{inh|en|ang|hūs||dwelling}}.

===Pronunciation===
* {{IPA|en|/haʊs/|[hɐʊs]}}
* {{audio|en|en-us-house.ogg}}

====Noun====
{{en-noun|houses}}

# {{lb|en|countable}} A [[structure]] built or serving as an [[abode]] of [[human]] beings.
#: {{ux|en|This is my '''house'''.}}
# The [[people]] who live in a house; a [[household]].
#* {{quote-book|en|year=1900}}
# {{lb|en|figurative}} A [[building]] used for something.

====Verb====
{{en-verb|hous}}

# {{lb|en|transitive}} To keep within a structure or [[container]].
==Dutch==
===Noun===
# niederländisch
"""

WP_BANK = """'''Bank''' steht für:
* [[Bank (Möbel)|Sitzmöbel]], eine Sitzgelegenheit für mehrere Personen
* [[Bank (Kreditinstitut)]], ein Unternehmen, das Geldgeschäfte betreibt
* [[Sandbank]], eine Erhebung im Meer
* [[Datei:Bank.jpg|mini]] Bildzeile
* [[Kategorie:Begriffsklärung]]
{{Begriffsklärung}}
"""


def summary(title, extract="Auszug.", kind="standard", description="Beschreibung", lang="de"):
    return {"type": kind, "title": title, "description": description, "extract": extract,
            "content_urls": {"desktop": {"page": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"}},
            "thumbnail": {"source": "https://upload.wikimedia.org/x.jpg"}}


SUMMARIES = {
    ("de", "Haus"): summary("Haus", "Ein Haus ist ein Gebäude."),
    ("de", "Bank"): summary("Bank", kind="disambiguation"),
    ("de", "Bank_(Kreditinstitut)"): summary("Bank (Kreditinstitut)", "Eine Bank ist ein Kreditinstitut."),
    ("de", "AC/DC"): summary("AC/DC", "Band."),
    ("en", "Serendipity"): summary("Serendipity", "Serendipity is an unplanned fortunate discovery.", lang="en"),
}
OPENSEARCH = {("de", "häuser"): ["Haus"], ("de", "serendipity"): [], ("en", "serendipity"): ["Serendipity"]}
WT_PARSE = {("de", "Haus"): DE_HAUS, ("en", "house"): EN_HOUSE}
WT_SEARCH = {("de", "hauss"): ["Haus"]}


class Handler(BaseHTTPRequestHandler):
    requests: list[str] = []

    def log_message(self, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Handler.requests.append(self.path)
        Handler.agent = self.headers.get("User-Agent")
        parsed = urllib.parse.urlsplit(self.path)
        prefix, _, rest = parsed.path.lstrip("/").partition("/")
        lang, site = prefix[:2], prefix[2:]
        query = dict(urllib.parse.parse_qsl(parsed.query))
        if rest.startswith("api/rest_v1/page/summary/"):
            title = urllib.parse.unquote(rest.split("/")[-1])
            if title == "Limit":
                return self._json({"title": "x"}, 429)
            if title == "Kaputt":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{kein json")
                return
            if title == "Langsam":
                time.sleep(1.5)
            data = SUMMARIES.get((lang, title))
            return self._json(data, 200) if data else self._json({"type": "not_found"}, 404)
        if rest == "w/api.php":
            action = query.get("action")
            if action == "opensearch":
                table = OPENSEARCH if site == "wp" else WT_SEARCH
                hits = table.get((lang, query["search"].lower()), [])
                return self._json([query["search"], hits, [], []])
            if action == "parse":
                page = query["page"]
                text = WP_BANK if site == "wp" and page == "Bank" else WT_PARSE.get((lang, page)) if site == "wt" else None
                if text is None:
                    return self._json({"error": {"code": "missingtitle", "info": "The page doesn't exist."}})
                return self._json({"parse": {"title": page, "wikitext": text}})
        self._json({}, 404)


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}/{{lang}}wp", f"http://127.0.0.1:{port}/{{lang}}wt"
    httpd.shutdown()


# ---- Wikipedia --------------------------------------------------------------------------------

def test_wikipedia_exact_hit(server) -> None:
    wp = WikipediaClient(base=server[0])
    result = wp.lookup("Haus", "de")
    assert isinstance(result, Summary) and result.title == "Haus" and result.extract == "Ein Haus ist ein Gebäude."
    assert result.url == "https://de.wikipedia.org/wiki/Haus" and result.lang == "de"
    assert Handler.agent.startswith(f"{APP_NAME}/") and "github.com/CustomCock/fckNotes" in Handler.agent


def test_wikipedia_fuzzy_term_uses_search(server) -> None:
    result = WikipediaClient(base=server[0]).lookup("Häuser", "de")
    assert isinstance(result, Summary) and result.title == "Haus"


def test_wikipedia_disambiguation_lists_options(server) -> None:
    result = WikipediaClient(base=server[0]).lookup("Bank", "de")
    assert isinstance(result, Disambiguation)
    assert result.options[:3] == [("Bank (Möbel)", "eine Sitzgelegenheit für mehrere Personen"),
                                  ("Bank (Kreditinstitut)", "ein Unternehmen, das Geldgeschäfte betreibt"),
                                  ("Sandbank", "eine Erhebung im Meer")]
    assert all(not t.startswith(("Datei:", "Kategorie:")) for t, _ in result.options)
    chosen = WikipediaClient(base=server[0]).summary(result.options[1][0], "de")
    assert isinstance(chosen, Summary) and chosen.title == "Bank (Kreditinstitut)"


def test_wikipedia_not_found_and_language_fallback(server) -> None:
    wp = WikipediaClient(base=server[0])
    with pytest.raises(NotFound):
        wp.lookup("Serendipity", "de")
    result = with_fallback(wp.lookup, "Serendipity", ["de", "en"])
    assert result.lang == "en" and result.title == "Serendipity"
    with pytest.raises(NotFound):
        with_fallback(wp.lookup, "Gibtsnicht", ["de", "en"])


def test_rate_limit_timeout_broken_json(server) -> None:
    with pytest.raises(RateLimited):
        WikipediaClient(base=server[0]).summary("Limit", "de")
    with pytest.raises(InvalidResponse):
        WikipediaClient(base=server[0]).summary("Kaputt", "de")
    slow = WikipediaClient(fetch=functools.partial(fetch_json, timeout=0.3), base=server[0])
    with pytest.raises(Timeout):
        slow.summary("Langsam", "de")
    # Rate-Limit ist kein „nicht gefunden“: der Fallback bricht ab statt die andere Sprache zu fragen
    with pytest.raises(RateLimited):
        with_fallback(lambda t, l: WikipediaClient(base=server[0]).summary("Limit", l), "x", ["de", "en"])


def test_offline() -> None:
    wp = WikipediaClient(fetch=functools.partial(fetch_json, timeout=1), base="http://127.0.0.1:9/{lang}")
    with pytest.raises((Offline, Timeout)):
        wp.summary("Haus", "de")


def test_title_encoding_in_requests(server) -> None:
    Handler.requests.clear()
    WikipediaClient(base=server[0]).summary("AC/DC", "de")
    assert Handler.requests[-1].startswith("/dewp/api/rest_v1/page/summary/AC%2FDC")


# ---- Wiktionary --------------------------------------------------------------------------------

def test_wiktionary_de(server) -> None:
    result = WiktionaryClient(base=server[1]).lookup("Haus", "de")
    assert isinstance(result, Definition) and result.language_name == "Deutsch" and result.title == "Haus"
    assert [p.name for p in result.parts] == ["Substantiv"]
    meanings = result.parts[0].meanings
    assert meanings[0] == "Gebäude, das Menschen zum Wohnen dient"
    assert meanings[1] == "(übertragen): alle Bewohner eines Hauses"
    assert len(meanings) == 6 and not any("Unterbedeutung" in m for m in meanings)
    assert result.ipa == "haʊ̯s, Plural ˈhɔɪ̯zɐ"
    assert result.etymology == "mittelhochdeutsch hūs, althochdeutsch hūs"
    assert result.url == "https://de.wiktionary.org/wiki/Haus"
    for text in [result.ipa, result.etymology, *meanings]:
        assert "{{" not in text and "}}" not in text and "[[" not in text and "<ref" not in text


def test_wiktionary_en_and_case_variant(server) -> None:
    result = WiktionaryClient(base=server[1]).lookup("House", "en")    # Titel ist „house“: Variante klein
    assert result.title == "house" and result.language_name == "English"
    assert [p.name for p in result.parts] == ["Noun", "Verb"]
    assert result.parts[0].meanings[0] == "(countable) A structure built or serving as an abode of human beings."
    assert result.parts[0].meanings[1] == "The people who live in a house; a household."
    assert len(result.parts[0].meanings) == 3                          # Beispiele/Zitate (#: #*) zählen nicht
    assert result.ipa == "/haʊs/, [hɐʊs]"
    assert result.etymology == "From hous, from hūs."


def test_wiktionary_search_not_found_and_fallback(server) -> None:
    wt = WiktionaryClient(base=server[1])
    assert wt.lookup("Hauss", "de").title == "Haus"                    # Tippfehler → Suche
    with pytest.raises(NotFound):
        wt.lookup("Gibtsnicht", "de")
    result = with_fallback(wt.lookup, "house", ["de", "en"])
    assert result.lang == "en"


def test_service_caches_per_source_term_language(server) -> None:
    service = LookupService(wikipedia_base=server[0], wiktionary_base=server[1])
    Handler.requests.clear()
    first = service.lookup("wikipedia", "Haus", ["de", "en"])
    count = len(Handler.requests)
    assert service.lookup("wikipedia", "haus", ["de", "en"]) is first   # Cache, keine neue Anfrage
    assert len(Handler.requests) == count
    service.lookup("wiktionary", "Haus", ["de", "en"])
    assert len(Handler.requests) > count                               # andere Quelle = eigener Eintrag
    assert service.cached("wikipedia", "HAUS", ["de", "en"]) is first
    assert service.cached("wikipedia", "Haus", ["en", "de"]) is None


# ---- Markup ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,clean", [
    ("[[Gebäude]], das [[Mensch]]en", "Gebäude, das Menschen"),
    ("[[Bank (Möbel)|Sitzmöbel]] und '''fett''' und ''kursiv''", "Sitzmöbel und fett und kursiv"),
    ("{{K|ugs.|Tiere}} [[Hund]]", "(umgangssprachlich, Tiere): Hund"),
    ("{{lb|en|transitive|_|figurative}} To [[house]]", "(transitive, figurative) To house"),
    ("{{l|en|word|Wort}} {{m|en|x}} {{gloss|Erklärung}}", "Wort x (Erklärung)"),
    ("Text<ref name=a>{{cite|x}}</ref> weiter<ref name=b/>.", "Text weiter."),
    ("{{unbekannt|{{verschachtelt|x}}|y}}Rest", "Rest"),
    ("<!-- Kommentar -->sichtbar &nbsp;&amp; mehr", "sichtbar & mehr"),
    ("[https://example.org Beispiel] und [https://x.org]", "Beispiel und"),
    ("[[Datei:Bild.jpg|mini|Text]]Wort", "Wort"),
    ("{{Lautschrift|haʊ̯s}}", "haʊ̯s"),
    ("{{IPA|en|/a/|/b/}}", "/a/, /b/"),
    ("kaputt {{offen", "kaputt offen"),
])
def test_clean_wikitext(raw: str, clean: str) -> None:
    assert clean_wikitext(raw) == clean


# ---- Begriffe, URLs, Suchmaschinen ---------------------------------------------------------------

def test_prepare_term_and_menu_label() -> None:
    assert prepare_term("  Haus\n  und Hof \t ") == "Haus und Hof"
    assert len(prepare_term("x" * 500)) == 200
    assert prepare_term("   ") == ""
    assert menu_label("Haus") == "„Haus“"
    long = menu_label("Donaudampfschifffahrtsgesellschaftskapitän")
    assert long.endswith("…“") and len(long) == 32


def test_urls_are_encoded() -> None:
    assert wikipedia_article_url("de", "Bank (Kreditinstitut)") == "https://de.wikipedia.org/wiki/Bank_%28Kreditinstitut%29"
    assert wikipedia_article_url("de", "Äpfel & Birnen") == "https://de.wikipedia.org/wiki/%C3%84pfel_%26_Birnen"
    assert wikipedia_article_url("en", "C#") == "https://en.wikipedia.org/wiki/C%23"
    assert wikipedia_article_url("en", "C++") == "https://en.wikipedia.org/wiki/C%2B%2B"
    assert wikipedia_search_url("de", "a&b #c") == "https://de.wikipedia.org/w/index.php?search=a%26b+%23c"
    assert wiktionary_url("de", "Straße") == "https://de.wiktionary.org/wiki/Stra%C3%9Fe"


def test_search_engines_and_custom_urls() -> None:
    assert search_url("C++ & Co #1") == "https://www.google.com/search?q=C%2B%2B+%26+Co+%231"
    assert search_url("Ä ö", "duckduckgo") == "https://duckduckgo.com/?q=%C3%84+%C3%B6"
    assert search_url("x", "startpage") == "https://www.startpage.com/do/search?q=x"
    assert search_url("a b", "custom", "https://search.example.org/?s={q}&lang=de") == "https://search.example.org/?s=a+b&lang=de"
    assert search_url("a b", "custom", "https://search.example.org/find?q=") == "https://search.example.org/find?q=a+b"
    assert search_url("a b", "custom", "https://search.example.org/find") == "https://search.example.org/find?q=a+b"
    assert search_url("a b", "custom", "https://s.example.org/?lang=de") == "https://s.example.org/?lang=de&q=a+b"
    assert search_url("x", "custom", "") == "https://www.google.com/search?q=x"          # leer → Standard
    assert search_url("x", "unbekannt") == "https://www.google.com/search?q=x"
    assert search_engine_name("custom", "https://www.search.example.org/?q={q}") == "search.example.org"
    assert search_menu_text("Haus") == "Bei Google suchen: „Haus“"
    assert search_menu_text("Haus", "duckduckgo") == "Bei DuckDuckGo suchen: „Haus“"


def test_languages_for() -> None:
    assert languages_for("auto", "en") == ["en", "de"]
    assert languages_for("auto", "both") == ["de", "en"]
    assert languages_for("auto", None) == ["de", "en"]
    assert languages_for("de", "en") == ["de", "en"]
    assert languages_for("en", "de") == ["en", "de"]


# ---- .ntx und Karte -------------------------------------------------------------------------------

def test_send_guard_for_encrypted_notes() -> None:
    guard = SendGuard()
    assert not guard.needs_confirmation(encrypted=False)
    assert guard.needs_confirmation(encrypted=True)
    guard.remember()
    assert not guard.needs_confirmation(encrypted=True)
    assert "Wikipedia" in confirmation_text("Wikipedia") and "Browserverlauf" in confirmation_text("Google")


def test_place_card_below_above_and_edges() -> None:
    bounds = (0, 0, 1280, 800)
    # genug Platz unten
    assert place_card((100, 100, 80, 20), (400, 300), bounds) == (100, 126, 300)
    # unten zu wenig, oben genug → oberhalb, ohne die Markierung zu überdecken
    x, y, h = place_card((100, 600, 80, 20), (400, 300), bounds)
    assert (y, h) == (294, 300) and y + h <= 600
    # rechter Rand: nach links eingegrenzt
    x, y, h = place_card((1200, 100, 60, 20), (400, 300), bounds)
    assert x == 1280 - 8 - 400
    # linker Rand
    assert place_card((-50, 100, 60, 20), (400, 300), bounds)[0] == 8
    # nirgends ganz Platz: Seite mit mehr Platz, Höhe gekürzt, Markierung frei
    x, y, h = place_card((100, 330, 80, 20), (400, 700), bounds)
    assert h < 700 and (y >= 350 or y + h <= 330)


def test_real_world_variants() -> None:
    from notex.core.lookup import parse_de_wiktionary, parse_en_wiktionary
    de = """== schön ({{Sprache|Deutsch}}) ==
=== {{Wortart|Adjektiv|Deutsch}}, {{Wortart|Adverb|Deutsch}} ===
{{Bedeutungen}}
:[1] {{K|Ästhetik}} angenehm für die Sinne
:[1a] besonders hübsch
"""
    language, parts, ipa, ety = parse_de_wiktionary(de)
    assert parts[0].name == "Adjektiv, Adverb" and parts[0].meanings == ["(Ästhetik): angenehm für die Sinne", "besonders hübsch"]
    en = """==English==
===Etymology===
{{root|en|ine-pro|*reyH-}}
{{inh+|en|enm|rinnen}}, from {{der|en|ang|rinnan}}.
===Verb===
# {{lb|en|intransitive}} To [[move]] swiftly.
## subsense zählt nicht
# {{plural of|en|house}}
"""
    language, parts, ipa, ety = parse_en_wiktionary(en)
    assert ety == "rinnen, from rinnan."
    assert parts[0].meanings == ["(intransitive) To move swiftly.", "plural of house"]
