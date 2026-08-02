"""Steam library discovery.

Emulation does not need Steam, since Discord matches on the tail of the
executable path and the sandbox works anywhere. This module covers two narrower
jobs: avoiding games the user actually owns, and supporting the Steam-anchored
fallback for titles that require folders inside a real ``steamapps/common``.
"""

import os
import re
from pathlib import Path

_TOKEN_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text: str) -> dict:
    """Parse Valve's KeyValues text format into nested dicts.

    Small hand-rolled reader so the app has no dependency on the ``vdf``
    package. Duplicate keys keep the last value, matching Steam's behaviour.
    """
    root: dict = {}
    stack = [root]
    pending_key = None

    for match in _TOKEN_RE.finditer(text):
        literal, brace = match.group(1), match.group(2)

        if brace == '{':
            if pending_key is None:
                continue  # malformed; ignore stray block
            child: dict = {}
            stack[-1][pending_key] = child
            stack.append(child)
            pending_key = None
        elif brace == '}':
            if len(stack) > 1:
                stack.pop()
            pending_key = None
        else:
            value = literal.replace('\\\\', '\\').replace('\\"', '"')
            if pending_key is None:
                pending_key = value
            else:
                stack[-1][pending_key] = value
                pending_key = None

    return root


def steam_root() -> Path | None:
    """Locate the Steam installation, preferring the registry."""
    try:
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
            (winreg.HKEY_LOCAL_MACHINE, r'Software\WOW6432Node\Valve\Steam'),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    for value in ('SteamPath', 'InstallPath'):
                        try:
                            path = Path(winreg.QueryValueEx(handle, value)[0])
                        except OSError:
                            continue
                        if path.is_dir():
                            return path
            except OSError:
                continue
    except ImportError:
        pass  # not on Windows

    for guess in (
        r'C:\Program Files (x86)\Steam',
        r'C:\Program Files\Steam',
    ):
        if Path(guess).is_dir():
            return Path(guess)
    return None


def library_roots() -> list[Path]:
    """Every ``steamapps`` directory Steam knows about, in Steam's own order."""
    root = steam_root()
    if root is None:
        return []

    vdf_path = root / 'steamapps' / 'libraryfolders.vdf'
    if not vdf_path.is_file():
        return [root / 'steamapps'] if (root / 'steamapps').is_dir() else []

    try:
        data = parse_vdf(vdf_path.read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return []

    folders = data.get('libraryfolders') or data.get('LibraryFolders') or {}
    roots: list[Path] = []
    for key, entry in folders.items():
        if not key.isdigit() or not isinstance(entry, dict):
            continue
        raw = entry.get('path')
        if not raw:
            continue
        steamapps = Path(raw) / 'steamapps'
        if steamapps.is_dir():
            roots.append(steamapps)

    return roots


def common_dirs() -> list[Path]:
    """``steamapps/common`` for each library, created lazily by Steam."""
    return [r / 'common' for r in library_roots()]


def installed_dirs() -> dict[str, Path]:
    """Map lowercased install-folder name -> real path, across all libraries.

    Used to detect that the user genuinely owns a title so emulation can
    refuse to write anywhere near it.
    """
    found: dict[str, Path] = {}
    for common in common_dirs():
        try:
            entries = list(common.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                found.setdefault(entry.name.lower(), entry)
    return found


def find_owned(install_dir_name: str) -> Path | None:
    """Return the real install path if the user already owns this game."""
    if not install_dir_name:
        return None
    return installed_dirs().get(install_dir_name.strip().lower())


def default_common() -> Path | None:
    """Preferred ``steamapps/common`` for Steam-anchored placement."""
    dirs = common_dirs()
    if not dirs:
        return None
    for candidate in dirs:
        if candidate.is_dir():
            return candidate
    return dirs[0]


def free_space(path: Path) -> int:
    try:
        return os.statvfs(path).f_bavail * os.statvfs(path).f_frsize  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        try:
            import shutil

            return shutil.disk_usage(path).free
        except OSError:
            return 0
