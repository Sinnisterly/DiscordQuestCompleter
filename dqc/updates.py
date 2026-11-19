"""Check GitHub for a newer release.

Reads the public "latest release" record of the project's repository. No
account and no user data is sent; the request carries only the app name.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import __version__, net

REPO = 'Sinnisterly/DiscordQuestCompleter'
LATEST_URL = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPO}/releases/latest'
USER_AGENT = 'DiscordQuestCompleter'


def _parts(version: str) -> tuple[int, ...]:
    """'v2.5.0' -> (2, 5, 0). Anything after the numbers is ignored."""
    match = re.match(r'v?(\d+(?:\.\d+)*)', (version or '').strip())
    if not match:
        return ()
    return tuple(int(p) for p in match.group(1).split('.'))


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = _parts(candidate), _parts(current)
    if not a:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def latest(timeout: int = 10) -> tuple[str, str] | None:
    """(version, page url) of the newest release, or None if unreachable."""
    request = urllib.request.Request(LATEST_URL, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/vnd.github+json',
    })
    try:
        with net.urlopen(request, timeout=timeout) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, ValueError, OSError, TimeoutError):
        return None
    tag = data.get('tag_name') if isinstance(data, dict) else None
    if not isinstance(tag, str) or not _parts(tag):
        return None
    url = data.get('html_url')
    if not (isinstance(url, str) and url.startswith('https://github.com/')):
        url = RELEASES_PAGE
    return tag.lstrip('v'), url
