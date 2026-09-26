import pytest

from notex.core import ioc
from notex.core.ioc import defang, find, refang


@pytest.mark.parametrize("text,expected", [
    ("http://evil.example.com/a.b/c.php?x=1.2", "hxxp://evil[.]example[.]com/a.b/c.php?x=1.2"),
    ("https://user@login.example.org:8443/x", "hxxps://user[@]login[.]example[.]org:8443/x"),
    ("ftp://files.example.net/pub", "fxp://files[.]example[.]net/pub"),
    ("Besuche evil.example.com heute.", "Besuche evil[.]example[.]com heute."),
    ("C2 auf 192.168.1.10:445 und 10.0.0.1.", "C2 auf 192[.]168[.]1[.]10:445 und 10[.]0[.]0[.]1."),
    ("v6 2001:db8::1 und ::1", "v6 2001[:]db8[:][:]1 und [:][:]1"),
    ("Mail an admin@example.org!", "Mail an admin[@]example[.]org!"),
    ("fe80::1%eth0", "fe80[:][:]1%eth0"),
])
def test_defang(text: str, expected: str) -> None:
    assert defang(text)[0] == expected


@pytest.mark.parametrize("text", [
    "Siehe setup.py, readme.md, bericht.pdf, config.json, run.sh und libc.so.6",
    "Version 1.2.3 und 10.0.19045.2006 sowie 999.1.1.1",
    "Zeit 14:03:11, Uhr 9:30",
    "Pfad C:\\temp\\evil.example.com.bak und /var/log/syslog.1",
    "Datei evil.exe und notiz.txt",
])
def test_no_false_positives(text: str) -> None:
    assert defang(text) == (text, 0)


def test_ambiguous_tld_needs_three_labels() -> None:
    assert find("cdn.evil.md") == [("domain", "cdn.evil.md")]
    assert find("readme.md") == []
    assert find("example.de") == [("domain", "example.de")]


def test_already_defanged_is_left_alone() -> None:
    text = "hxxp://evil[.]example[.]com/x und 192[.]168[.]1[.]1 und admin[@]example[.]org"
    assert defang(text) == (text, 0)
    once, _ = defang("http://a.example.com")
    assert defang(once)[0] == once


def test_refang_roundtrip_and_variants() -> None:
    original = "Siehe http://evil.example.com/p.php, 192.168.1.10:445, 2001:db8::1, a@b.example.org."
    defanged, count = defang(original)
    assert count == 4 and refang(defanged)[0] == original
    assert refang("hxxps[://]evil(.)com und x[at]y[dot]org und h[xx]p://a{.}b")[0] == \
        "https://evil.com und x@y.org und http://a.b"


def test_code_blocks_can_be_skipped() -> None:
    text = "evil.example.com\n```\ncurl http://evil.example.com\n```\n`8.8.8.8` und 1.1.1.1"
    out, count = defang(text, skip_code=True)
    assert out == "evil[.]example[.]com\n```\ncurl http://evil.example.com\n```\n`8.8.8.8` und 1[.]1[.]1[.]1"
    assert count == 2
    assert refang(out, skip_code=True)[0] == text.replace("evil[.]", "evil.")
    assert defang(text)[1] == 4


def test_find_kinds() -> None:
    kinds = [kind for kind, _v in find("http://x.example.com a@b.example.org 1.2.3.4 ::1 c.example.net")]
    assert kinds == ["url", "email", "ipv4", "ipv6", "domain"]
    assert ioc._is_domain("example.com") and not ioc._is_domain("example.exe")
