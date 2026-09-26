import pytest

from notex.core.actions import ActionRegistry
from notex.core.modules import BY_KEY, MODULES, ModuleRegistry, defaults


def feature(actions: ActionRegistry, calls: list):
    """Typischer Beitrag: Palette-Befehl einhängen, beim Abschalten wieder entfernen."""
    def activate():
        calls.append("an")
        actions.add("hex:open", "Als Hex öffnen", lambda: None)
        return lambda: (calls.append("aus"), actions.remove("hex:open"))
    return activate


def test_defaults_match_spec() -> None:
    on = {key for key, value in defaults().items() if value}
    assert on == {"variables", "hex", "ports", "ioc"}
    assert len(MODULES) == 15 and all(m.name and m.description and m.requires for m in MODULES)


def test_disabled_module_registers_nothing() -> None:
    config = {"modules": {"hex": False}}
    registry, actions, calls = ModuleRegistry(config), ActionRegistry(), []
    registry.contribute("hex", feature(actions, calls))
    assert calls == [] and actions.get("hex:open") is None and registry.active_contributions("hex") == 0


def test_toggle_without_restart() -> None:
    config: dict = {}
    registry, actions, calls = ModuleRegistry(config), ActionRegistry(), []
    registry.contribute("hex", feature(actions, calls))       # Standard an → sofort aktiv
    assert actions.get("hex:open") is not None
    registry.set_enabled("hex", False)
    assert actions.get("hex:open") is None and config["modules"]["hex"] is False
    registry.set_enabled("hex", True)
    assert actions.get("hex:open") is not None and calls == ["an", "aus", "an"]
    registry.set_enabled("hex", True)                          # keine Doppel-Aktivierung
    assert calls == ["an", "aus", "an"] and registry.active_contributions("hex") == 1


def test_listeners_and_invalid_config() -> None:
    config = {"modules": {"strings": "ja", "yara": True}}      # Unsinn wird auf den Standard gesetzt
    registry = ModuleRegistry(config)
    assert registry.enabled("strings") is False and registry.enabled("yara") is True
    seen = []
    registry.on_change(lambda key, on: seen.append((key, on)))
    registry.set_enabled("strings", True)
    assert seen == [("strings", True)]
    with pytest.raises(KeyError):
        registry.enabled("gibtsnicht")
    with pytest.raises(KeyError):
        registry.contribute("gibtsnicht", lambda: None)


def test_heavy_imports_only_when_active() -> None:
    """Ein abgeschaltetes Modul darf nichts importieren – der Aktivator läuft gar nicht."""
    config = {"modules": {"pcap": False}}
    registry, imported = ModuleRegistry(config), []
    registry.contribute("pcap", lambda: imported.append("dpkt") or None)
    assert imported == []
    registry.set_enabled("pcap", True)
    assert imported == ["dpkt"] and BY_KEY["pcap"].requires == "dpkt"


def test_shutdown_tears_everything_down() -> None:
    registry, actions, calls = ModuleRegistry({}), ActionRegistry(), []
    registry.contribute("hex", feature(actions, calls))
    registry.shutdown()
    assert actions.get("hex:open") is None and calls[-1] == "aus"


def test_show_all_files_follows_analysis_modules() -> None:
    from notex.core.modules import show_all_files
    config: dict = {}
    ModuleRegistry(config)
    assert not show_all_files(config)                        # Standard: nur die Endungen
    config["modules"]["entropy"] = True
    assert show_all_files(config)
    config["modules"]["entropy"] = False
    config["tree_show_all"] = True
    assert show_all_files(config)
