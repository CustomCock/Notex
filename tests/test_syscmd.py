"""R1: Ausgabe von Windows-Konsolenbefehlen (OEM-Codepage cp850) darf nie beim Dekodieren abstürzen.

Reproduktion des Fehlers: Deutsche `ping`-Ausgabe enthält „für" → in cp850 das Byte 0x81, das in cp1252
(Pythons Annahme bei text=True) undefiniert ist → UnicodeDecodeError bei jedem Ping.
"""
import subprocess
import sys

import pytest

from notex.core import netdetect, scan, syscmd

PING_DE = ("\r\nPing wird ausgeführt für 192.168.178.1 mit 32 Bytes Daten:\r\n"
           "Antwort von 192.168.178.1: Bytes=32 Zeit=3ms TTL=64\r\n\r\n"
           "Ping-Statistik für 192.168.178.1:\r\n"
           "    Pakete: Gesendet = 1, Empfangen = 1, Verloren = 0\r\n    (0% Verlust),\r\n")
PING_DE_TIMEOUT = ("\r\nPing wird ausgeführt für 10.9.9.9 mit 32 Bytes Daten:\r\n"
                   "Zeitüberschreitung der Anforderung.\r\n\r\nPing-Statistik für 10.9.9.9:\r\n"
                   "    Pakete: Gesendet = 1, Empfangen = 0, Verloren = 1\r\n    (100% Verlust),\r\n")
IPCONFIG_DE = ("\r\nWindows-IP-Konfiguration\r\n\r\nEthernet-Adapter Ethernet:\r\n\r\n"
               "   Verbindungsspezifisches DNS-Suffix: fritz.box\r\n"
               "   Temporäre IPv6-Adresse. . . . . . : 2001:db8::5\r\n"
               "   IPv4-Adresse  . . . . . . . . . . : 192.168.178.20\r\n"
               "   Subnetzmaske  . . . . . . . . . . : 255.255.255.0\r\n"
               "   Standardgateway . . . . . . . . . : 192.168.178.1\r\n")


def test_reproduce_cp1252_crash():
    """So stürzte es vorher ab (Windows: text=True → cp1252)."""
    with pytest.raises(UnicodeDecodeError):
        PING_DE.encode("cp850").decode("cp1252")


def test_decode_cp850_german_output():
    text = syscmd.decode(PING_DE.encode("cp850"), "cp850")
    assert "Ping-Statistik für" in text
    assert scan.ping_alive(text, 0) is True
    assert scan.ping_alive(syscmd.decode(PING_DE_TIMEOUT.encode("cp850"), "cp850"), 1) is False


def test_decode_wrong_codepage_never_raises():
    text = syscmd.decode(PING_DE.encode("cp850"), "cp1252")     # falsche Annahme → Ersatzzeichen, kein Absturz
    assert "Ping-Statistik f" in text and scan.ping_alive(text, 0) is True


def test_decode_unknown_codec_and_empty():
    assert syscmd.decode(b"abc", "gibt-es-nicht") == "abc"
    assert syscmd.decode(b"") == "" and syscmd.decode(None) == ""


def test_console_encoding_per_platform():
    assert syscmd.console_encoding("win32") == "oem"
    assert syscmd.console_encoding("linux")


def test_ipconfig_german_through_decoder():
    adapters = netdetect.parse_ipconfig(syscmd.decode(IPCONFIG_DE.encode("cp850"), "cp850"))
    assert [(a.ip, a.cidr) for a in adapters] == [("192.168.178.20", "192.168.178.0/24")]


def test_run_real_process_with_cp850_bytes(monkeypatch):
    """Echter Kindprozess schreibt cp850-Bytes; mit „falscher" Codepage darf run() trotzdem nicht werfen."""
    monkeypatch.setattr(syscmd, "console_encoding", lambda platform=None: "cp1252")
    code, text = syscmd.run([sys.executable, "-c",
                             "import sys; sys.stdout.buffer.write('Ping-Statistik für'.encode('cp850'))"])
    assert code == 0 and text.startswith("Ping-Statistik f")


def test_system_ping_survives_decode_errors():
    def broken(_command):
        raise UnicodeDecodeError("charmap", b"\x81", 0, 1, "undefined")
    assert scan.system_ping("10.0.0.1", runner=broken) is False


def test_missing_program_raises_oserror_only():
    with pytest.raises((OSError, subprocess.SubprocessError)):
        syscmd.run(["notex-gibt-es-nicht-xyz"])
