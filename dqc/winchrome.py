"""Native window decoration tweaks on Windows.

Qt styles the client area but not the title bar, which the desktop window
manager owns. These calls ask DWM to draw it dark so it matches the rest of
the window. Every call degrades to a no-op on unsupported builds.
"""

from __future__ import annotations

import ctypes
import sys

# Documented DWMWINDOWATTRIBUTE values.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19   # builds 18985 and earlier
DWMWA_CAPTION_COLOR = 35                 # Windows 11 (build 22000+) only
DWMWA_BORDER_COLOR = 34


def _to_colorref(hex_colour: str) -> int:
    """'#15171d' -> 0x00BBGGRR, the byte order DWM expects."""
    value = hex_colour.lstrip('#')
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return (b << 16) | (g << 8) | r


def _set(hwnd: int, attribute: int, value: int) -> bool:
    try:
        data = ctypes.c_int(value)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), ctypes.c_int(attribute),
            ctypes.byref(data), ctypes.sizeof(data),
        )
        return result == 0
    except (AttributeError, OSError):
        return False


def apply_dark_titlebar(widget, background: str | None = None) -> bool:
    """Darken the title bar of an already-shown widget.

    Returns True if the dark-mode attribute was accepted. The caption colour
    is attempted too, but Windows 10 ignores it, so its failure is not
    treated as an error.
    """
    if sys.platform != 'win32':
        return False

    try:
        hwnd = int(widget.winId())
    except (TypeError, ValueError):
        return False

    ok = _set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
    if not ok:
        ok = _set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)

    if background:
        colour = _to_colorref(background)
        _set(hwnd, DWMWA_CAPTION_COLOR, colour)
        _set(hwnd, DWMWA_BORDER_COLOR, colour)

    return ok
