"""Start with Windows.

Adds or removes one value under the current user's Run key, the same place
the Startup apps list in Windows Settings reads. No administrator rights are
needed, and it can also be turned off from Windows Settings > Apps > Startup.

The entry starts the app with --tray, so it opens in the tray without
showing its window.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .appdirs import APP_NAME, is_frozen

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
TRAY_FLAG = '--tray'


def command() -> str:
    """What Windows should run at sign-in."""
    if is_frozen():
        return f'"{sys.executable}" {TRAY_FLAG}'
    # From a source checkout: the windowless Python, so no console appears.
    exe = Path(sys.executable)
    pythonw = exe.with_name('pythonw.exe')
    runner = pythonw if pythonw.is_file() else exe
    script = Path(__file__).resolve().parent.parent / 'run.py'
    return f'"{runner}" "{script}" {TRAY_FLAG}'


def _registry():
    if sys.platform != 'win32':
        return None
    import winreg
    return winreg


def is_enabled() -> bool:
    winreg = _registry()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, APP_NAME)
    except OSError:
        return False
    return bool(value)


def set_enabled(enabled: bool) -> str:
    """Turn it on or off. Returns an error message, or '' on success."""
    winreg = _registry()
    if winreg is None:
        return 'Start with Windows is only available on Windows.'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        return f'Could not change the startup setting: {exc}'
    return ''


def refresh() -> None:
    """Keep the entry pointing at this copy of the app if it was moved."""
    winreg = _registry()
    if winreg is None or not is_enabled():
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, APP_NAME)
    except OSError:
        return
    if value != command():
        set_enabled(True)
