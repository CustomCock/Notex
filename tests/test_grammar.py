"""Tests für den LanguageTool-Client gegen einen kleinen Fake-Server im selben Prozess."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from notex.core.grammar import GrammarClient, GrammarUnavailable, is_public_url, parse_matches

SAMPLE_RESPONSE = {
    "matches": [
        {"offset": 4, "length": 3, "message": "Möglicher Tippfehler gefunden.",
         "replacements": [{"value": "das"}, {"value": "dass"}],
         "rule": {"id": "GERMAN_SPELLER_RULE", "category": {"name": "Rechtschreibung"}}},
        {"offset": 20, "length": 5, "message": "Doppeltes Leerzeichen", "replacements": [],
         "rule": {"id": "WHITESPACE"}},
        {"kaputt": True},
    ]
}


class FakeHandler(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = parse_qs(self.rfile.read(length).decode("utf-8"))
        FakeHandler.received.append(body)
        payload = json.dumps(SAMPLE_RESPONSE).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"[]")

    def log_message(self, *args):  # Ruhe im Testlauf
        pass


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_parse_matches_ignores_broken_entries() -> None:
    matches = parse_matches(SAMPLE_RESPONSE)
    assert len(matches) == 2
    assert matches[0].offset == 4 and matches[0].length == 3
    assert matches[0].replacements == ["das", "dass"]
    assert matches[0].rule == "GERMAN_SPELLER_RULE" and matches[0].category == "Rechtschreibung"
    assert parse_matches({}) == [] and parse_matches("unsinn") == []


def test_check_sends_text_and_language(server: str) -> None:
    client = GrammarClient(server)
    FakeHandler.received.clear()
    matches = client.check("Ich weiß daß es geht.", "de")
    assert len(matches) == 2
    assert FakeHandler.received[0]["text"] == ["Ich weiß daß es geht."]
    assert FakeHandler.received[0]["language"] == ["de-DE"]
    assert client.check("   ", "de") == []   # leerer Text wird nicht gesendet
    assert client.ping() is True


def test_rate_limit_waits_between_requests(server: str) -> None:
    client = GrammarClient(server)
    client.min_interval = 0.2
    start = time.monotonic()
    client.check("eins", "de")
    client.check("zwei", "de")
    assert time.monotonic() - start >= 0.2


def test_unreachable_server_raises_unavailable() -> None:
    client = GrammarClient("http://127.0.0.1:9", timeout=0.5)
    with pytest.raises(GrammarUnavailable):
        client.check("Text", "de")
    assert client.ping() is False


def test_public_api_requires_consent() -> None:
    assert is_public_url("https://api.languagetool.org") and not is_public_url("http://localhost:8081")
    client = GrammarClient("https://api.languagetool.org", allow_public=False)
    assert client.min_interval >= 3.0
    with pytest.raises(GrammarUnavailable):
        client.check("Text", "en")
