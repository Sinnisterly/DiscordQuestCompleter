"""User preferences, stored as JSON next to the cache.

Small enough that it is read and written whole each time. Unknown keys in the
file are preserved, so an older build will not discard settings written by a
newer one.
"""

from __future__ import annotations

import json
import os

from .appdirs import data_dir

FILE_NAME = 'settings.json'

DEFAULTS = {
    'minimise_to_tray': True,
    'notify_on_finish': True,
    # Set once the user has been told where the window went.
    'tray_explained': False,
}


def _path():
    return data_dir() / FILE_NAME


def load() -> dict:
    values = dict(DEFAULTS)
    try:
        stored = json.loads(_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return values
    if isinstance(stored, dict):
        values.update(stored)
    return values


def get(key: str, default=None):
    return load().get(key, DEFAULTS.get(key, default))


def set_value(key: str, value) -> None:
    values = load()
    values[key] = value
    target = _path()
    try:
        tmp = target.with_suffix('.tmp')
        tmp.write_text(json.dumps(values, indent=1), encoding='utf-8')
        os.replace(tmp, target)
    except OSError:
        pass
