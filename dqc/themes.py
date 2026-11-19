"""Color themes.

A theme is a small JSON file:

    {"name": "Midnight", "radius": 10,
     "colors": {"bg": "#15171d", "surface": "#1b1e26", ...}}

Presets ship in data/themes and cannot be changed or deleted. User themes
live in the app data folder under themes/, one file per theme, so they can be
shared by copying the file. A file with missing or invalid colors still loads:
each bad value falls back to the Midnight preset.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .appdirs import bundled, data_dir

DEFAULT = 'Midnight'

# Every color a theme defines, in the order the editor shows them.
KEYS = (
    'bg', 'surface', 'surfaceHi', 'border', 'text', 'muted',
    'accent', 'accentHi', 'good', 'warn', 'bad',
)
LABELS = {
    'bg': 'Background',
    'surface': 'Panel',
    'surfaceHi': 'Raised panel',
    'border': 'Border',
    'text': 'Text',
    'muted': 'Secondary text',
    'accent': 'Accent',
    'accentHi': 'Accent hover',
    'good': 'Success',
    'warn': 'Warning',
    'bad': 'Error',
}

_FALLBACK = {
    'bg': '#15171d', 'surface': '#1b1e26', 'surfaceHi': '#232733',
    'border': '#2c313d', 'text': '#e8eaf0', 'muted': '#8b91a3',
    'accent': '#5865f2', 'accentHi': '#6b76f5', 'good': '#3ba55d',
    'warn': '#e0a33e', 'bad': '#ed4245',
}
_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_SLUG_RE = re.compile(r'[^a-z0-9]+')


class ThemeError(ValueError):
    pass


@dataclass
class Theme:
    name: str
    colors: dict[str, str] = field(default_factory=lambda: dict(_FALLBACK))
    radius: int = 10
    preset: bool = False

    def to_dict(self) -> dict:
        return {'name': self.name, 'colors': dict(self.colors), 'radius': self.radius}


def _slug(name: str) -> str:
    return _SLUG_RE.sub('-', name.lower()).strip('-') or 'theme'


def _user_dir() -> Path:
    path = data_dir() / 'themes'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _preset_dir() -> Path:
    return bundled('data/themes')


def from_dict(data, preset: bool = False) -> Theme:
    """Build a theme, replacing anything invalid with the default value."""
    if not isinstance(data, dict):
        raise ThemeError('Not a theme file.')
    name = str(data.get('name') or '').strip()
    if not name:
        raise ThemeError('The theme has no name.')
    raw = data.get('colors') if isinstance(data.get('colors'), dict) else {}
    colors = {}
    for key in KEYS:
        value = raw.get(key)
        colors[key] = value.lower() if isinstance(value, str) and _HEX_RE.match(value) else _FALLBACK[key]
    radius = data.get('radius')
    radius = int(radius) if isinstance(radius, (int, float)) and 0 <= radius <= 24 else 10
    return Theme(name=name[:40], colors=colors, radius=radius, preset=preset)


def _read(path: Path, preset: bool) -> Theme | None:
    try:
        return from_dict(json.loads(path.read_text(encoding='utf-8')), preset=preset)
    except (OSError, ValueError):
        return None


def list_themes() -> list[Theme]:
    """Presets first, then user themes, each group sorted by name.

    A user theme with the same name as a preset is skipped, so presets
    cannot be shadowed.
    """
    presets = [t for t in (_read(p, True) for p in sorted(_preset_dir().glob('*.json'))) if t]
    presets.sort(key=lambda t: (t.name != DEFAULT, t.name.lower()))
    taken = {t.name.lower() for t in presets}
    users = []
    for path in sorted(_user_dir().glob('*.json')):
        theme = _read(path, False)
        if theme and theme.name.lower() not in taken:
            taken.add(theme.name.lower())
            users.append(theme)
    users.sort(key=lambda t: t.name.lower())
    return presets + users


def load(name: str | None) -> Theme:
    """The named theme, or the default when it no longer exists."""
    wanted = (name or DEFAULT).lower()
    themes = list_themes()
    for theme in themes:
        if theme.name.lower() == wanted:
            return theme
    for theme in themes:
        if theme.name.lower() == DEFAULT.lower():
            return theme
    return Theme(name=DEFAULT, preset=True)


def is_preset(name: str) -> bool:
    return any(t.preset and t.name.lower() == name.lower() for t in list_themes())


def save(theme: Theme) -> Theme:
    """Write a user theme. Raises ThemeError for a preset's name."""
    theme = from_dict(theme.to_dict())
    if is_preset(theme.name):
        raise ThemeError(f'"{theme.name}" is a built-in theme. Choose another name.')
    target = _user_dir() / f'{_slug(theme.name)}.json'
    tmp = target.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(theme.to_dict(), indent=1), encoding='utf-8')
        tmp.replace(target)
    except OSError as exc:
        raise ThemeError(f'Could not save the theme: {exc}') from exc
    return theme


def delete(name: str) -> bool:
    if is_preset(name):
        return False
    for path in _user_dir().glob('*.json'):
        theme = _read(path, False)
        if theme and theme.name.lower() == name.lower():
            try:
                path.unlink()
            except OSError:
                return False
            return True
    return False


def import_file(path: str | Path) -> Theme:
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ThemeError(f'Could not read {Path(path).name}: {exc}') from exc
    theme = from_dict(data)
    if is_preset(theme.name):
        theme.name = f'{theme.name} (imported)'
    return save(theme)


def export_file(theme: Theme, path: str | Path) -> None:
    try:
        Path(path).write_text(json.dumps(theme.to_dict(), indent=1), encoding='utf-8')
    except OSError as exc:
        raise ThemeError(f'Could not write {Path(path).name}: {exc}') from exc
