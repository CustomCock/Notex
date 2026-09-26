"""IOCs entschärfen und wieder scharf machen – URLs, Domains, IPv4/IPv6, E-Mails. Ohne Qt.

Entschärfen (übliche Schreibweise in Berichten und Tickets):
  http://evil.example.com/a.php → hxxp://evil[.]example[.]com/a.php     (Punkte nur im Host, nicht im Pfad)
  evil.example.com → evil[.]example[.]com      192.168.1.10:445 → 192[.]168[.]1[.]10:445
  2001:db8::1 → 2001[:]db8[:][:]1              admin@example.org → admin[@]example[.]org
Scharf machen kehrt das um und versteht auch andere verbreitete Schreibweisen ([dot], (.), {.}, [at], hxxps, fxp).

Keine Domain sind Dateinamen wie „setup.py“, „readme.md“ oder „bericht.pdf“: Die Endung muss eine Top-Level-Domain
sein; mehrdeutige Endungen (.md, .py, .sh, .so …) zählen erst ab drei Teilen (sub.example.md). Bereits entschärfte
Werte bleiben unverändert. Code-Blöcke (``` und `inline`) lassen sich ausnehmen.
"""
from __future__ import annotations

import ipaddress
import re

GENERIC_TLDS = {
    "com", "net", "org", "info", "biz", "edu", "gov", "mil", "int", "arpa", "io", "co", "app", "dev", "xyz",
    "online", "site", "top", "club", "shop", "store", "tech", "cloud", "live", "pro", "me", "tv", "cc", "ws",
    "mobi", "name", "asia", "tel", "travel", "jobs", "museum", "aero", "coop", "cat", "post", "onion", "eu", "icu",
    "vip", "win", "bid", "loan", "work", "click", "link", "space", "website", "fun", "life", "world", "today",
    "news", "blog", "email", "digital", "network", "systems", "services", "solutions", "support", "security",
    "zip", "mov", "page", "run", "one", "ltd", "gmbh", "berlin", "bayern", "hamburg", "wien", "swiss", "global",
    "biz", "rest", "bar", "best", "buzz", "cyou", "monster", "quest", "sbs", "cfd", "lol", "mom", "ink", "wtf",
    "local", "internal", "lan", "home", "corp",
}
# Zweibuchstabige Länderdomains, die zugleich übliche Dateiendungen sind: erst ab drei Teilen als Domain
AMBIGUOUS_TLDS = {"md", "py", "sh", "rs", "pl", "ps", "so", "in", "am", "ac", "mk", "ai", "cs", "db", "gz", "js",
                  "ts", "cc", "ms", "sc", "sv", "hs", "ml", "rb", "mo", "ko", "bz", "vc", "gs", "st", "tf", "ls",
                  "lo", "co", "go", "is", "it", "to", "me", "tv", "ws"}
# Häufige Dateiendungen, die nie als Domain gelten (zusätzlich zu den nicht-TLD-Endungen)
FILE_EXTENSIONS = {"exe", "dll", "sys", "bat", "cmd", "ps1", "vbs", "txt", "log", "pdf", "doc", "docx", "xls",
                   "xlsx", "ppt", "pptx", "png", "jpg", "jpeg", "gif", "bmp", "json", "xml", "yaml", "yml", "ini",
                   "cfg", "conf", "csv", "tsv", "html", "htm", "php", "asp", "aspx", "jsp", "zip", "rar", "tar",
                   "bin", "dat", "tmp", "bak", "old", "lnk", "iso", "img", "msi", "jar", "apk", "elf", "ntx"}

_CODE = re.compile(r"```.*?(?:```|\Z)|`[^`\n]+`", re.S)
_URL = re.compile(r"\b(?:https?|ftp|hxxps?|fxp|h\[xx\]ps?)(?:://|\[://\]|\[:\]//)[^\s<>\"'`\])}]+", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@(?:[a-z0-9-]+\.)+[a-z]{2,24}\b", re.I)
_IPV4 = re.compile(r"(?<![\w.\[])(?:\d{1,3}\.){3}\d{1,3}(?![\w\]]|\.\d)")
_IPV6 = re.compile(r"(?<![\w:\[])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?:%\w+)?(?![\w\]])", re.I)
_DOMAIN = re.compile(r"(?<![\w.@/\\\[-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?![\w\]]|\.\w)", re.I)


def _is_domain(host: str) -> bool:
    labels = host.lower().rstrip(".").split(".")
    if len(labels) < 2:
        return False
    tld = labels[-1]
    if tld in FILE_EXTENSIONS:
        return False
    if tld in AMBIGUOUS_TLDS:
        return len(labels) >= 3
    return tld in GENERIC_TLDS or (len(tld) == 2 and tld.isalpha())


def _defang_host(host: str) -> str:
    return host.replace(".", "[.]")


def _defang_url(url: str) -> str:
    lower = url.lower()
    if lower.startswith(("hxxp", "fxp", "h[xx]p")) or "[.]" in url:
        return url                                      # schon entschärft
    scheme, _, rest = url.partition("://")
    new_scheme = {"http": "hxxp", "https": "hxxps", "ftp": "fxp"}.get(scheme.lower(), scheme)
    host_end = len(rest)
    for sep in "/?#":
        index = rest.find(sep)
        if index >= 0:
            host_end = min(host_end, index)
    host, path = rest[:host_end], rest[host_end:]
    userinfo, at, hostport = host.rpartition("@")
    return f"{new_scheme}://{userinfo + '[@]' if at else ''}{_defang_host(hostport)}{path}"


def _spans(text: str, skip_code: bool) -> list[tuple[int, int, str]]:
    """IOC-Fundstellen (Start, Ende, Art), nicht überlappend, Code ausgenommen, falls gewünscht."""
    blocked: list[tuple[int, int]] = [(m.start(), m.end()) for m in _CODE.finditer(text)] if skip_code else []
    found: list[tuple[int, int, str]] = []

    def free(start: int, end: int) -> bool:
        return not any(s < end and start < e for s, e in blocked) and not any(s < end and start < e for s, e, _k in found)

    for match in _URL.finditer(text):
        if free(match.start(), match.end()):
            found.append((match.start(), match.end(), "url"))
    for match in _EMAIL.finditer(text):
        if free(match.start(), match.end()) and _is_domain(match.group().split("@")[1]):
            found.append((match.start(), match.end(), "email"))
    for match in _IPV6.finditer(text):
        candidate = match.group().split("%")[0]
        if candidate.count(":") >= 2 and free(match.start(), match.end()):
            try:
                ipaddress.IPv6Address(candidate)
            except ValueError:
                continue
            found.append((match.start(), match.end(), "ipv6"))
    for match in _IPV4.finditer(text):
        if free(match.start(), match.end()):
            try:
                ipaddress.IPv4Address(match.group())
            except ValueError:
                continue
            found.append((match.start(), match.end(), "ipv4"))
    for match in _DOMAIN.finditer(text):
        if free(match.start(), match.end()) and _is_domain(match.group()):
            found.append((match.start(), match.end(), "domain"))
    return sorted(found)


def find(text: str, skip_code: bool = False) -> list[tuple[str, str]]:
    """(Art, Wert) aller erkannten IOCs – für Anzeige und Tests."""
    return [(kind, text[start:end]) for start, end, kind in _spans(text, skip_code)]


def defang(text: str, skip_code: bool = False) -> tuple[str, int]:
    """Alle IOCs entschärfen. Gibt (neuer Text, Anzahl geänderter Stellen) zurück."""
    out, last, count = [], 0, 0
    for start, end, kind in _spans(text, skip_code):
        value = text[start:end]
        if kind == "url":
            new = _defang_url(value)
        elif kind == "email":
            user, _, host = value.partition("@")
            new = f"{user}[@]{_defang_host(host)}"
        elif kind == "ipv6":
            new = value.replace(":", "[:]")
        else:
            new = _defang_host(value)
        out.append(text[last:start])
        out.append(new)
        count += new != value
        last = end
    out.append(text[last:])
    return "".join(out), count


_REFANG = [
    (re.compile(r"\bhxxp(s?)(?=\[?:)", re.I), r"http\1"),
    (re.compile(r"\bh\[xx\]p(s?)(?=\[?:)", re.I), r"http\1"),
    (re.compile(r"\bfxp(?=\[?:)", re.I), "ftp"),
    (re.compile(r"\[://\]"), "://"),
    (re.compile(r"\[:\]//"), "://"),
    (re.compile(r"\[\.\]|\(\.\)|\{\.\}|\[dot\]|\(dot\)", re.I), "."),
    (re.compile(r"\[@\]|\[at\]|\(at\)", re.I), "@"),
    (re.compile(r"\[:\]"), ":"),
]


def refang(text: str, skip_code: bool = False) -> tuple[str, int]:
    """Entschärfte Schreibweisen zurückverwandeln. Gibt (neuer Text, Anzahl Ersetzungen) zurück."""
    if skip_code:
        parts, last, total = [], 0, 0
        for match in _CODE.finditer(text):
            segment, count = refang(text[last:match.start()])
            parts += [segment, match.group()]
            total += count
            last = match.end()
        segment, count = refang(text[last:])
        return "".join(parts) + segment, total + count
    total = 0
    for pattern, replacement in _REFANG:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total
