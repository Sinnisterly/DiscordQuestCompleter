"""Artwork fetching, cached to disk.

Steam's capsule art is the same asset SteamDB shows, served straight from the
CDN with no key and no login. Titles without a Steam SKU fall back to their
Discord application icon.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request

from . import net
from .appdirs import thumb_dir
from .catalog import Game

USER_AGENT = 'DiscordQuestCompleter/1.0'

# Steam answers 200 with a blank placeholder rather than 404 for titles whose
# art is not published yet. The placeholder has the right dimensions, so only
# its size gives it away: a real capsule runs to 10 KB or more, the blank one
# to well under 1 KB. Discord icons are legitimately small, so this floor
# applies to Steam alone.
STEAM_MIN_BYTES = 2500

# How long to remember that a URL gave us nothing usable.
MISS_TTL = 7 * 24 * 60 * 60

STEAM_CAPSULE = 'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/capsule_231x87.jpg'
STEAM_HEADER = 'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg'
DISCORD_ICON = 'https://cdn.discordapp.com/app-icons/{app_id}/{icon}.png?size=160'


def urls_for(game: Game, large: bool = False) -> list[str]:
    """Candidate artwork URLs, best first."""
    out = []
    if game.steam_appid:
        template = STEAM_HEADER if large else STEAM_CAPSULE
        out.append(template.format(appid=game.steam_appid))
    if game.icon_hash and not game.id.startswith('override:'):
        out.append(DISCORD_ICON.format(app_id=game.id, icon=game.icon_hash))
    return out


def _cache_path(url: str):
    digest = hashlib.sha1(url.encode('utf-8')).hexdigest()[:20]
    suffix = '.jpg' if '.jpg' in url else '.png'
    return thumb_dir() / f'{digest}{suffix}'


def _miss_path(url: str):
    return _cache_path(url).with_suffix('.miss')


def _min_bytes(url: str) -> int:
    return STEAM_MIN_BYTES if 'steamstatic.com' in url else 0


def _is_missing(url: str) -> bool:
    """True if this URL recently gave us nothing worth showing."""
    marker = _miss_path(url)
    try:
        if (time.time() - marker.stat().st_mtime) < MISS_TTL:
            return True
        marker.unlink(missing_ok=True)   # stale, worth another try
    except OSError:
        pass
    return False


def _mark_missing(url: str) -> None:
    try:
        _miss_path(url).write_bytes(b'')
    except OSError:
        pass


def fetch(url: str, timeout: int = 15) -> bytes | None:
    """Return image bytes, from disk if we have them. Safe off the UI thread.

    Returns None for anything too small to be real artwork, so the caller can
    move on to the next source.
    """
    minimum = _min_bytes(url)
    if _is_missing(url):
        return None

    path = _cache_path(url)
    if path.is_file():
        try:
            data = path.read_bytes()
            if data and len(data) >= minimum:
                return data
            path.unlink(missing_ok=True)  # a placeholder cached by an older build
        except OSError:
            pass

    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with net.urlopen(request, timeout=timeout) as resp:
            if resp.status != 200:
                _mark_missing(url)
                return None
            data = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None      # transient, so do not record a miss

    if not data or len(data) < minimum:
        _mark_missing(url)
        return None

    try:
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError:
        pass
    return data


def fetch_for(game: Game, large: bool = False) -> bytes | None:
    """Try each artwork source in turn."""
    for url in urls_for(game, large=large):
        data = fetch(url)
        if data:
            return data
    return None


def icon_url(game: Game) -> str | None:
    """Square artwork for the game, suitable for a window icon.

    Discord's application icon is square. The Steam capsule is a wide banner,
    so it is no use here.
    """
    if game.icon_hash and not game.id.startswith('override:'):
        return DISCORD_ICON.format(app_id=game.id, icon=game.icon_hash)
    return None


def icon_path(game: Game):
    """Path to the cached square icon, or None if it is not downloaded yet."""
    url = icon_url(game)
    if not url:
        return None
    path = _cache_path(url)
    return path if path.is_file() else None


def ensure_icon(game: Game):
    """Download the square icon if needed and return its path. Blocking."""
    url = icon_url(game)
    if not url:
        return None
    if fetch(url) is None:
        return None
    path = _cache_path(url)
    return path if path.is_file() else None
