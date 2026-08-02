"""Which games currently have a Discord quest running.

Discord's own quest endpoint needs an account token, which this app
deliberately never asks for. Instead the list is data: bundled with the
release and optionally refreshed from a URL, so it can be corrected without
shipping a new build.

An empty or unreachable list is not an error. Everything still works, the UI
simply shows no quest badges.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .appdirs import bundled, cache_dir, data_dir

USER_AGENT = 'DiscordQuestCompleter/1.0'
CACHE_NAME = 'active_quests.json'
LOCAL_NAME = 'my_quests.json'


@dataclass
class Quest:
    name: str
    until: dt.date | None = None
    reward: str | None = None

    @property
    def expired(self) -> bool:
        return self.until is not None and dt.date.today() > self.until


def _parse_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse(payload: dict) -> tuple[dict[str, Quest], str | None]:
    quests: dict[str, Quest] = {}
    for raw in payload.get('entries') or []:
        name = (raw.get('name') or '').strip()
        if not name:
            continue
        quest = Quest(
            name=name,
            until=_parse_date(raw.get('until')),
            reward=raw.get('reward'),
        )
        if not quest.expired:
            quests[name.lower()] = quest
    return quests, payload.get('remote')


def _read(path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def local_load() -> set[str]:
    """Games the user marked as having a quest, lowercased."""
    payload = _read(data_dir() / LOCAL_NAME) or {}
    names = payload.get('marked')
    if not isinstance(names, list):
        return set()
    return {str(n).strip().lower() for n in names if str(n).strip()}


def local_set(name: str, active: bool) -> set[str]:
    """Add or remove a locally marked quest. Returns the updated set."""
    marked = local_load()
    key = (name or '').strip().lower()
    if not key:
        return marked

    if active:
        marked.add(key)
    else:
        marked.discard(key)

    target = data_dir() / LOCAL_NAME
    try:
        tmp = target.with_suffix('.tmp')
        tmp.write_text(
            json.dumps({'version': 1, 'marked': sorted(marked)}, indent=1),
            encoding='utf-8',
        )
        tmp.replace(target)
    except OSError:
        pass
    return marked


def load() -> dict[str, Quest]:
    """Active quests: the shared list, plus anything marked locally.

    The shared list ships empty because quest availability changes constantly.
    Local marks are what most people will actually use.
    """
    cached = _read(cache_dir() / CACHE_NAME)
    shipped = _read(bundled('data/active_quests.json'))
    payload = cached or shipped or {}
    quests, _ = _parse(payload)

    for key in local_load():
        if key not in quests:
            quests[key] = Quest(name=key, reward='marked by you')
    return quests


def remote_url() -> str | None:
    payload = _read(cache_dir() / CACHE_NAME) or _read(bundled('data/active_quests.json')) or {}
    url = payload.get('remote')
    return url if isinstance(url, str) and url.startswith('https://') else None


def refresh(timeout: int = 15) -> bool:
    """Fetch an updated list if one is configured. Safe off the UI thread."""
    url = remote_url()
    if not url:
        return False

    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, ValueError, OSError, TimeoutError):
        return False

    if not isinstance(payload, dict) or 'entries' not in payload:
        return False

    target = cache_dir() / CACHE_NAME
    try:
        tmp = target.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, indent=1), encoding='utf-8')
        tmp.replace(target)
    except OSError:
        return False
    return True
