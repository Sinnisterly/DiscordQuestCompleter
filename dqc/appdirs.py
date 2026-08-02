"""Filesystem locations the app owns. Everything user-writable lives here."""

import os
import sys
from pathlib import Path

APP_NAME = 'DiscordQuestCompleter'


def data_dir() -> Path:
    """Per-user writable directory for cache, journal and settings."""
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = data_dir() / 'cache'
    p.mkdir(parents=True, exist_ok=True)
    return p


def thumb_dir() -> Path:
    p = cache_dir() / 'thumbs'
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


def bundled(relative: str) -> Path:
    """Path to a read-only asset shipped with the app.

    Works both from source and from a PyInstaller bundle.
    """
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent / relative
