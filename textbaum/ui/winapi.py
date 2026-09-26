"""Windows-spezifisches: dunkle Titelleiste über die DWM-API.

Auf anderen Systemen (oder alten Windows-Versionen) passiert einfach nichts.
"""
from __future__ import annotations

import sys

# Attribut-IDs aus dwmapi.h. 20 gilt ab Windows 10 20H1, 19 für ältere Insider-Builds.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_CAPTION_COLOR = 35  # erst ab Windows 11


def apply_dark_titlebar(window, caption_color: str = "#121212") -> bool:
    """Schaltet die Titelleiste des Fensters auf dunkel. Gibt True bei Erfolg zurück."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        dwm = ctypes.windll.dwmapi
        hwnd = wintypes.HWND(int(window.winId()))
        enabled = ctypes.c_int(1)

        ok = False
        for attribute in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            result = dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled))
            if result == 0:  # S_OK
                ok = True
                break

        # Windows 11 kann die Farbe der Titelleiste direkt setzen. COLORREF ist 0x00BBGGRR.
        r, g, b = int(caption_color[1:3], 16), int(caption_color[3:5], 16), int(caption_color[5:7], 16)
        colorref = wintypes.DWORD((b << 16) | (g << 8) | r)
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_CAPTION_COLOR, ctypes.byref(colorref), ctypes.sizeof(colorref))
        return ok
    except Exception:  # noqa: BLE001 – Fallback: normale Titelleiste, kein Crash
        return False
