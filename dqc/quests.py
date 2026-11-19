"""Which games currently have a Discord quest running.

Discord's own quest endpoint needs an account token, which this app never
asks for. Three sources are combined instead:

- detected: read from the Quests page of the running Discord app (see
  discordui.py) and saved here as a snapshot.
- shared: a list bundled with the release, optionally refreshed from a URL.
- marked: games the user marked by hand.

An empty or unreachable source is not an error. The UI shows fewer badges.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .appdirs import bundled, cache_dir, data_dir

USER_AGENT = 'DiscordQuestCompleter/1.0'
CACHE_NAME = 'active_quests.json'
LOCAL_NAME = 'my_quests.json'
DETECTED_NAME = 'detected_quests.json'

# A detected quest with no readable end date is dropped after this long.
DETECTED_TTL = 7 * 24 * 60 * 60


@dataclass
class Quest:
    name: str
    until: dt.date | None = None
    reward: str | None = None
    orbs: int | None = None
    title: str | None = None      # shown instead of the game name when set
    accepted: bool | None = None  # known only for quests read from Discord
    heading: str | None = None    # the card heading in Discord, for accepting
    progress: int | None = None   # percent done, as Discord's ring shows it
    source: str = 'shared'

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


def _write_json(path, payload) -> bool:
    try:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, indent=1), encoding='utf-8')
        tmp.replace(path)
    except OSError:
        return False
    return True


def save_detected(entries: list[dict], other: list[dict] | None = None) -> bool:
    """Replace the detected set with a new snapshot.

    entries are quests this app can run. Each has 'name' (the catalogue
    name), and optionally 'title' (shown instead of the name, as in
    "Illegal Soccer on Roblox"), 'reward', 'orbs' (absent for item rewards)
    and 'until' (ISO date).

    other are quests it cannot run, kept so the page can still list them.
    Each has 'title', 'reason', and optionally 'reward', 'orbs' and 'until'.

    Both may also carry 'accepted' and 'heading' (the card heading in
    Discord, used to press Accept Quest on it later).

    The Quests page lists everything on offer, so a quest missing from a new
    scan has ended and is dropped.
    """
    payload = {
        'version': 1,
        'detected_at': int(time.time()),
        'entries': [e for e in entries if e.get('name')],
        'other': [o for o in (other or []) if o.get('title')],
    }
    return _write_json(cache_dir() / DETECTED_NAME, payload)


SEEN_NAME = 'seen_quests.json'


def new_quests(keys: list[str]) -> list[str]:
    """Which of these quests have never been seen before, then remember them.

    Keys are the card headings from Discord. The first call ever only takes
    note of what is on the page and returns nothing, so the first scan does
    not announce every quest that already existed.
    """
    target = data_dir() / SEEN_NAME
    payload = _read(target)
    first_time = not isinstance(payload, dict)
    seen = set(payload.get('seen') or []) if not first_time else set()
    fresh = [k for k in keys if k and k not in seen]
    if fresh or first_time:
        # Old keys are kept for a while so a quest that drops off the page
        # for one scan is not announced again when it comes back.
        merged = list(dict.fromkeys([*(payload or {}).get('seen', []), *keys]))[-500:]
        _write_json(target, {'version': 1, 'seen': merged})
    return [] if first_time else fresh


def _fresh_detected() -> dict:
    """The saved snapshot, or {} when it is too old to trust."""
    payload = _read(cache_dir() / DETECTED_NAME) or {}
    stamp = payload.get('detected_at') or 0
    if not isinstance(stamp, (int, float)) or time.time() - stamp > DETECTED_TTL:
        return {}
    return payload


def load_other() -> list[dict]:
    """Detected quests this app cannot run, minus any that have ended."""
    out = []
    for raw in _fresh_detected().get('other') or []:
        until = _parse_date(raw.get('until'))
        if until is not None and dt.date.today() > until:
            continue
        out.append({
            'title': str(raw.get('title') or ''),
            'reason': str(raw.get('reason') or ''),
            'reward': raw.get('reward') or '',
            'orbs': raw.get('orbs') if isinstance(raw.get('orbs'), int) else 0,
            'until': until.isoformat() if until else None,
        })
    return out


def detected_at() -> int:
    """Unix time of the last successful scan, or 0."""
    payload = _read(cache_dir() / DETECTED_NAME) or {}
    value = payload.get('detected_at')
    return int(value) if isinstance(value, (int, float)) else 0


def load_detected() -> dict[str, Quest]:
    out: dict[str, Quest] = {}
    for raw in _fresh_detected().get('entries') or []:
        name = (raw.get('name') or '').strip()
        if not name:
            continue
        quest = Quest(
            name=name,
            until=_parse_date(raw.get('until')),
            reward=raw.get('reward'),
            orbs=raw.get('orbs') if isinstance(raw.get('orbs'), int) else None,
            title=raw.get('title') or None,
            accepted=raw.get('accepted') if isinstance(raw.get('accepted'), bool) else None,
            heading=raw.get('heading') or None,
            progress=raw.get('progress') if isinstance(raw.get('progress'), int) else None,
            source='discord',
        )
        if not quest.expired:
            out[name.lower()] = quest
    return out


def load() -> dict[str, Quest]:
    """Active quests from every source, keyed by lowercased game name.

    Detected quests win, since they carry the real reward and end date.
    """
    cached = _read(cache_dir() / CACHE_NAME)
    shipped = _read(bundled('data/active_quests.json'))
    payload = cached or shipped or {}
    quests, _ = _parse(payload)
    quests.update(load_detected())

    for key in local_load():
        if key not in quests:
            quests[key] = Quest(name=key, reward='Marked by you', source='marked')
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
