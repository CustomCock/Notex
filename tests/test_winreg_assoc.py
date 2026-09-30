import sys

import pytest

from notex import APP_NAME, EXE_FILE, PROG_ID, REG_KEY
from notex.core.winreg_assoc import (DEFAULT_EXTENSIONS, FileAssociation, MemoryRegistry, WinRegistry,
                                     is_temporary_location)

EXE = r"C:\Apps\Notex\Notex.exe"


def test_register_creates_progid_openwith_and_capabilities() -> None:
    reg = MemoryRegistry()
    reg.set_value(r"Software\Classes\.txt", None, "txtfile")   # fremde Standard-Zuordnung
    assoc = FileAssociation(reg, EXE)
    assoc.register([".txt", ".md"])
    assert reg.get_value(rf"Software\Classes\{PROG_ID}\shell\open\command", None) == f'"{EXE}" "%1"'
    assert reg.get_value(rf"Software\Classes\{PROG_ID}\DefaultIcon", None) == f"{EXE},0"
    assert reg.get_value(r"Software\Classes\.txt\OpenWithProgids", PROG_ID) == ""
    assert reg.get_value(r"Software\Classes\.md\OpenWithProgids", PROG_ID) == ""
    assert reg.get_value(rf"Software\Classes\Applications\{EXE_FILE}\SupportedTypes", ".md") == ""
    assert reg.get_value(rf"Software\Classes\Applications\{EXE_FILE}", "FriendlyAppName") == APP_NAME
    # stabile interne Schlüssel (REG_KEY) – ändern sich bei einer Umbenennung nicht, Anzeigename schon
    assert REG_KEY == "Notex"
    assert reg.get_value(r"Software\Notex\Capabilities\FileAssociations", ".txt") == PROG_ID
    assert reg.get_value(r"Software\Notex\Capabilities", "ApplicationName") == APP_NAME
    assert reg.get_value(r"Software\RegisteredApplications", "Notex") == r"Notex\Capabilities"
    assert reg.get_value(r"Software\Classes\.txt", None) == "txtfile"   # unangetastet
    assert reg.get_value(r"Software\Classes\SystemFileAssociations\.txt\shell\Notex", None) == f"Mit {APP_NAME} öffnen"
    assert reg.get_value(r"Software\Classes\SystemFileAssociations\.md\shell\Notex\command", None) == f'"{EXE}" "%1"'


def test_status_and_reregister_changes_extensions() -> None:
    reg = MemoryRegistry()
    assoc = FileAssociation(reg, EXE)
    assert assoc.status().registered is False
    assoc.register([".txt", ".log"])
    status = assoc.status()
    assert status.registered and status.exe_path == EXE and status.extensions == [".txt", ".log"]
    assert status.matches(EXE.lower())
    assoc.register([".md"])
    assert assoc.status().extensions == [".md"]
    assert reg.get_value(r"Software\Classes\.txt\OpenWithProgids", PROG_ID) is None
    assert not reg.exists(r"Software\Classes\SystemFileAssociations\.txt\shell\Notex")


def test_unregister_removes_everything_but_foreign_keys() -> None:
    reg = MemoryRegistry()
    reg.set_value(r"Software\Classes\.txt\OpenWithProgids", "Fremd.TextFile", "")
    assoc = FileAssociation(reg, EXE)
    assoc.register([".txt", ".json"])
    assoc.unregister()
    own_keys = [k for k in reg.data if "notex" in k or EXE_FILE.lower() in k]
    assert own_keys == []
    assert reg.get_value(r"Software\Classes\.txt\OpenWithProgids", "Fremd.TextFile") == ""
    assert assoc.status().registered is False


def test_update_path_after_move() -> None:
    reg = MemoryRegistry()
    FileAssociation(reg, EXE).register([".txt"])
    moved = FileAssociation(reg, r"D:\Stick\Notex\Notex.exe")
    assert not moved.status().matches(moved.exe_path)
    moved.update_path()
    assert moved.status().matches(moved.exe_path) and moved.status().extensions == [".txt"]


def test_status_reports_missing_exe(tmp_path) -> None:
    reg = MemoryRegistry()
    exe = tmp_path / "Notex.exe"
    exe.write_bytes(b"MZ")
    assoc = FileAssociation(reg, str(exe))
    assoc.register([".txt"])
    assert assoc.status().exe_exists
    exe.unlink()   # Ordner gelöscht → Windows blendet Notex in „Öffnen mit“ aus
    assert assoc.status().registered and not assoc.status().exe_exists
    assert not FileAssociation(MemoryRegistry(), str(exe)).status().exe_exists


def test_temporary_location_detection() -> None:
    temp = [r"C:\Users\me\AppData\Local\Temp"]
    assert is_temporary_location(r"C:\Users\me\AppData\Local\Temp\Temp1_Notex-v1.1.0.zip\Notex\Notex.exe", temp)
    assert is_temporary_location(r"c:\users\me\appdata\local\temp\x\Notex.exe", temp)   # Groß/Klein egal
    assert is_temporary_location(r"D:\Downloads\Temp1_Notex-v1.1.0.zip\Notex\Notex.exe", [])   # ZIP-Vorschau ohne TEMP-Treffer
    assert not is_temporary_location(r"C:\Apps\Notex\Notex.exe", temp)
    assert not is_temporary_location(r"C:\Users\me\AppData\Local\Temporary Files\Notex.exe", temp)   # nur echte Unterordner
    assert not is_temporary_location("", temp)


def test_unknown_extensions_fall_back_to_default() -> None:
    reg = MemoryRegistry()
    assoc = FileAssociation(reg, EXE)
    assoc.register([".exe", ".bat"])
    assert assoc.status().extensions == DEFAULT_EXTENSIONS


@pytest.mark.skipif(sys.platform != "win32", reason="echte Registry nur unter Windows")
def test_real_registry_under_test_prefix() -> None:
    reg = WinRegistry()
    prefix = r"Software\NotexTests\Prefix"
    assoc = FileAssociation(reg, EXE, prefix=prefix)
    try:
        assoc.register([".txt"])
        assert assoc.status().registered and assoc.status().extensions == [".txt"]
        assoc.unregister()
        assert assoc.status().registered is False
    finally:
        reg.delete_tree(r"Software\NotexTests")


def test_rename_cleans_legacy_exe_entry_and_keeps_stable_keys() -> None:
    """Umbenennung (Notex.exe → neuer Name): der alte „Öffnen mit“-Eintrag verschwindet beim Neu-Registrieren,
    „Registrierung entfernen“ findet weiterhin alles."""
    reg = MemoryRegistry()
    reg.set_value(r"Software\Classes\Applications\Notex.exe", "FriendlyAppName", "Notex")        # alte Version
    reg.set_value(r"Software\Classes\Applications\Notex.exe\shell\open\command", None, '"C:\\alt\\Notex.exe" "%1"')
    assoc = FileAssociation(reg, rf"C:\Apps\{APP_NAME}\{EXE_FILE}")
    assoc.register([".txt"])
    if EXE_FILE != "Notex.exe":
        assert not reg.exists(r"Software\Classes\Applications\Notex.exe")
    assoc.unregister()
    assert [k for k in reg.data if "notex" in k or EXE_FILE.lower() in k] == []
