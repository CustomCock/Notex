import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from notex.core.update_check import (CHECK_INTERVAL, fetch_releases, is_newer, latest_release, parse_version,
                                     should_check, update_available)


def rel(tag, draft=False, pre=False, url=None, body="Neu: X"):
    return {"tag_name": tag, "name": f"Notex {tag}", "draft": draft, "prerelease": pre, "body": body,
            "html_url": url or f"https://github.com/CustomCock/Notex/releases/tag/{tag}",
            "published_at": "2026-09-26T10:00:00Z"}


def test_parse_version() -> None:
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.4") == (1, 4, 0)
    assert parse_version(" v10.0.1 ") == (10, 0, 1)
    for bad in ("main", "v1", "1.2.3-beta", "latest", ""):
        assert parse_version(bad) is None
    assert is_newer((1, 10, 0), (1, 9, 9)) and not is_newer((1, 3, 0), (1, 3, 0))


def test_latest_ignores_non_versions_drafts_prereleases_and_foreign_urls() -> None:
    payload = [rel("main"), rel("v1.1.0"), rel("v1.0.0"), rel("v2.0.0", draft=True), rel("v1.9.0", pre=True),
               rel("v1.8.0", url="https://evil.example/x"), "Müll", {"tag_name": 5}]
    best = latest_release(payload)
    assert best is not None and best.tag == "v1.1.0" and best.version_text == "1.1.0"
    assert latest_release({"message": "rate limited"}) is None
    assert latest_release([]) is None


def test_highest_version_wins_not_newest_date() -> None:
    payload = [rel("v1.2.1"), rel("v1.10.0"), rel("v1.9.0")]
    assert latest_release(payload).tag == "v1.10.0"


def test_update_available_current_and_skipped() -> None:
    payload = [rel("v1.5.0"), rel("v1.4.0")]
    assert update_available(payload, "1.4.0").tag == "v1.5.0"
    assert update_available(payload, "1.5.0") is None
    assert update_available(payload, "1.6.0") is None            # Entwicklerversion neuer als Release
    assert update_available(payload, "1.4.0", skipped="1.5.0") is None
    assert update_available(payload, "1.4.0", skipped="1.4.9").tag == "v1.5.0"
    assert update_available(payload, "kaputt") is None


def test_should_check_once_per_day() -> None:
    now = 1_800_000_000
    assert should_check(0, now)
    assert not should_check(now - 3600, now)
    assert should_check(now - CHECK_INTERVAL, now)
    assert should_check(now + 3600, now)                         # Uhr zurückgestellt


def test_notes_are_shortened() -> None:
    long_body = "\n".join(f"- Punkt {i}" for i in range(500))
    notes = latest_release([rel("v1.0.0", body=long_body)]).notes
    assert len(notes) <= 1210 and notes.endswith("…")


@pytest.fixture
def server():
    payload = json.dumps([rel("v9.9.9")]).encode()
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["ua"] = self.headers.get("User-Agent")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/releases", seen
    httpd.shutdown()


def test_fetch_against_fake_server(server) -> None:
    url, seen = server
    payload = fetch_releases("1.4.0", url=url, timeout=5)
    assert update_available(payload, "1.4.0").tag == "v9.9.9"
    assert seen["ua"] == "Notex/1.4.0"
