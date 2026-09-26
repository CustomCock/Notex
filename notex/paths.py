"""Ermittelt, wo die App liegt – und damit, wo data/ und config.json hingehören.

Grundprinzip der portablen App: alles liegt relativ zum App-Ordner.
Nichts in AppData, nichts in der Registry.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Der Ordner, in dem die App liegt.

    - Gebaut (PyInstaller setzt `sys.frozen`): der Ordner der Notex.exe.
    - Dev-Modus: der Projektordner, also der Ordner über diesem Paket.
    - NOTEX_ROOT (Umgebungsvariable): nur für Tests und Screenshots.
    """
    override = os.environ.get("NOTEX_ROOT")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """data/ neben der App. Wird angelegt, falls es fehlt."""
    path = app_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_root() / "config.json"
