from pathlib import Path

from notex.core import tools


def test_categories_fixed_order() -> None:
    assert [c for c, _ in tools.CATEGORIES] == ["analyse", "netzwerk", "logs", "text", "doku"]
    # jedes Werkzeug hat eine gültige Kategorie
    valid = {c for c, _ in tools.CATEGORIES}
    assert all(t.category in valid for t in tools.TOOLS)


def test_file_kind() -> None:
    assert tools.file_kind("dump.pcap") == "pcap" and tools.file_kind("x.pcapng") == "pcap"
    assert tools.file_kind("auth.log") == "log" and tools.file_kind("C:/W/setupact.log") == "log"
    assert tools.file_kind("foto.JPG") == "image" and tools.file_kind("regel.yar") == "yara"
    assert tools.file_kind("daten.csv") == "data" and tools.file_kind("bericht.pdf") == "document"
    assert tools.file_kind("notiz.md") == "text" and tools.file_kind("blob.bin") == "binary"
    assert tools.file_kind(None) == "none"


def test_applies() -> None:
    pcap = tools.BY_COMMAND["pcap:open"]
    assert tools.applies(pcap, "pcap") and not tools.applies(pcap, "text") and not tools.applies(pcap, "none")
    scanner = tools.BY_COMMAND["scan:open"]
    assert tools.applies(scanner, "none") and tools.applies(scanner, "text")   # braucht keine Datei
    meta = tools.BY_COMMAND["analysis:metadata"]
    assert tools.applies(meta, "image") and tools.applies(meta, "document") and not tools.applies(meta, "log")


def test_grouped_respects_enabled_modules() -> None:
    enabled = {"hex", "ioc", "ports"}
    groups = dict((key, ts) for key, _label, ts in tools.grouped(enabled))
    analyse = {t.command for t in groups.get("analyse", [])}
    assert "file:hex" in analyse and "analysis:strings" not in analyse   # strings-Modul aus
    text = {t.command for t in groups.get("text", [])}
    assert "ioc:defang" in text and "data:format" in text                # data:format hat kein Modul → immer da
    assert "var:insert" not in text                                       # variables-Modul aus


def test_grouped_order_and_no_empty() -> None:
    groups = tools.grouped(set(t.module for t in tools.TOOLS if t.module))
    keys = [key for key, _l, _t in groups]
    assert keys == [k for k, _ in tools.CATEGORIES if k in keys] and all(ts for _k, _l, ts in groups)


def test_enabled_modules_from_config() -> None:
    assert "ports" in tools.enabled_modules({}) and "ioc" in tools.enabled_modules({})   # Standard an
    assert "scanner" not in tools.enabled_modules({})                                     # Standard aus
    assert "scanner" in tools.enabled_modules({"modules": {"scanner": True}})
