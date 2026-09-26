import configparser
from pathlib import Path

from notex.core.linux_desktop import (NTX_MIME, DesktopIntegration, data_home, desktop_entry, exec_path_of, mime_xml,
                                      quote_exec)


def test_quote_exec() -> None:
    assert quote_exec("/opt/Notex/Notex") == "/opt/Notex/Notex"
    assert quote_exec("/home/p/Mein Ordner/Notex") == '"/home/p/Mein Ordner/Notex"'
    assert quote_exec('/x/"$a`\\/N') == '"/x/\\"\\$a\\`\\\\/N"'


def test_desktop_entry_is_valid_ini_and_roundtrips_path() -> None:
    for exe in ("/opt/Notex/Notex", "/home/p/Mein Ordner/Notex", "/home/p/$weird`\\\"/Notex"):
        text = desktop_entry(exe)
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string(text)
        entry = parser["Desktop Entry"]
        assert entry["Type"] == "Application" and entry["Icon"] == "notex" and entry["Terminal"] == "false"
        assert NTX_MIME in entry["MimeType"] and entry["MimeType"].endswith(";")
        assert entry["Exec"].endswith(" %F")
        assert exec_path_of(text) == exe


def test_mime_xml_contains_glob_and_magic() -> None:
    text = mime_xml()
    assert 'glob pattern="*.ntx"' in text and 'value="NOTEXENC"' in text and NTX_MIME in text
    from xml.dom import minidom
    assert minidom.parseString(text.encode()).documentElement.tagName == "mime-info"


def test_install_status_uninstall(tmp_path: Path) -> None:
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"\x89PNG fake")
    calls = []
    integration = DesktopIntegration("/opt/Notex/Notex", icon, base=tmp_path / "share", runner=calls.append)
    assert not integration.status().registered
    integration.install()
    assert integration.desktop_file.is_file() and integration.mime_file.is_file()
    assert integration.icon_file.read_bytes() == b"\x89PNG fake"
    status = integration.status()
    assert status.registered and status.matches("/opt/Notex/Notex") and not status.matches("/neu/Notex")
    assert [c[0] for c in calls] == ["update-desktop-database", "update-mime-database"]
    # verschoben: erneut registrieren überschreibt den Pfad
    DesktopIntegration("/neu/Notex", icon, base=tmp_path / "share", runner=calls.append).install()
    assert integration.status().exe_path == "/neu/Notex"
    integration.uninstall()
    assert not integration.desktop_file.exists() and not integration.mime_file.exists() and not integration.icon_file.exists()
    integration.uninstall()   # zweimal entfernen ist kein Fehler
    # nie ein Default setzen
    assert not any("xdg-mime" in c[0] for c in calls)


def test_data_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert data_home() == tmp_path
    monkeypatch.setenv("XDG_DATA_HOME", "relativ/pfad")          # relative Werte sind laut Spec ungültig
    assert data_home() == Path.home() / ".local" / "share"
