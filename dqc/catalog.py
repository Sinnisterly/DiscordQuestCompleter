"""The game catalogue.

The primary source is Discord's public detectable-application list, the same
table its client uses to decide which running process counts as which game.
The community path index is layered on top and wins where present, since those
structures are confirmed working.

None of this needs a Steam API key, a login, or a Discord token.
"""

from __future__ import annotations

import gzip
import json
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import quests
from .appdirs import bundled, cache_dir

DETECTABLE_URL = 'https://discord.com/api/v9/applications/detectable'
USER_AGENT = 'DiscordQuestCompleter/1.0'
REFRESH_AFTER = 24 * 60 * 60  # seconds

_WORD_RE = re.compile(r'[a-z0-9]+')


def normalise(text: str) -> str:
    return ''.join(ch for ch in (text or '').lower() if ch.isalnum())


def tokens(text: str) -> list[str]:
    return _WORD_RE.findall((text or '').lower())


@dataclass
class Game:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    exes: list[str] = field(default_factory=list)
    launchers: list[str] = field(default_factory=list)
    steam_appid: str | None = None
    icon_hash: str | None = None

    # Filled in from the community index when a match exists.
    verified: list[str] = field(default_factory=list)
    note: str | None = None
    is_template: bool = False

    # Filled in from the active-quest list, which is usually empty.
    quest_reward: str | None = None
    has_quest: bool = False

    @property
    def is_verified(self) -> bool:
        return bool(self.verified)

    @property
    def candidates(self) -> list[str]:
        """Every path worth trying, best first, de-duplicated.

        Community-verified structures lead. Real executables come before
        launchers, since a launcher process is less reliably credited.
        """
        seen: set[str] = set()
        out: list[str] = []
        for path in [*self.verified, *self.exes, *self.launchers]:
            key = path.replace('\\', '/').lower()
            if key not in seen:
                seen.add(key)
                out.append(path)
        return out

    @property
    def primary(self) -> str | None:
        paths = self.candidates
        return paths[0] if paths else None


# Shorthand people actually type. Discord's own aliases are unreliable here --
# its Zenless Zone Zero entry is aliased "Honkai Star Rail".
ABBREVIATIONS = {
    'zzz': 'Zenless Zone Zero',
    'hsr': 'Honkai: Star Rail',
    'wuwa': 'Wuthering Waves',
    'wwm': 'Where Winds Meet',
    'poe2': 'Path of Exile 2',
    'osrs': 'Old School RuneScape',
    'lol': 'League of Legends',
    'wow': 'World of Warcraft',
    'eso': 'The Elder Scrolls Online',
    'pubg': 'PUBG: BATTLEGROUNDS',
    'bf6': 'Battlefield 6',
    'ror2': 'Risk of Rain 2',
    'md': 'Yu-Gi-Oh! Master Duel',
    'df': 'Delta Force',
}


def _load_overrides() -> dict[str, dict]:
    path = bundled('data/overrides.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    out = {}
    for entry in data.get('entries') or []:
        name = entry.get('name')
        if name and entry.get('path'):
            out[normalise(name)] = entry
    return out


def _game_from_override(entry: dict) -> Game:
    """Build a catalogue entry that exists only in the community index.

    Discord lists some apps (Comet, Opera GX, Enginefall, Shift at Midnight)
    with no executables at all, so the community path is the only data there
    is. Those titles must still be launchable.
    """
    return Game(
        id=f'override:{normalise(entry["name"])}',
        name=entry['name'],
        aliases=list(entry.get('aliases') or []),
        verified=[entry['path'], *(entry.get('alts') or [])],
        note=entry.get('note'),
        is_template=bool(entry.get('template')),
    )


def _read_snapshot(path: Path) -> dict | None:
    try:
        if path.suffix == '.gz':
            with gzip.open(path, 'rb') as fh:
                return json.loads(fh.read().decode('utf-8'))
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, EOFError):
        return None


class Catalog:
    """Loaded once at startup; refreshed in the background."""

    def __init__(self):
        self.games: list[Game] = []
        self.generated: int = 0
        self._by_norm: dict[str, Game] = {}
        self._lock = threading.Lock()

    # -- loading ---------------------------------------------------------

    @property
    def _cache_file(self) -> Path:
        return cache_dir() / 'detectable.json.gz'

    def load(self) -> None:
        """Load the freshest snapshot available without touching the network."""
        payload = None
        cached = _read_snapshot(self._cache_file)
        shipped = _read_snapshot(bundled('data/detectable.json.gz'))

        if cached and shipped:
            payload = cached if cached.get('generated', 0) >= shipped.get('generated', 0) else shipped
        else:
            payload = cached or shipped

        if not payload:
            self.games = []
            return

        overrides = _load_overrides()
        active = quests.load()
        matched: set[str] = set()
        games = []
        for raw in payload.get('games') or []:
            if not raw.get('id') or not raw.get('name'):
                continue
            game = Game(
                id=raw['id'],
                name=raw['name'],
                aliases=raw.get('aliases') or [],
                exes=raw.get('exes') or [],
                launchers=raw.get('launchers') or [],
                steam_appid=raw.get('steam'),
                icon_hash=raw.get('icon'),
            )
            key = normalise(game.name)
            override = overrides.get(key)
            if override:
                game.verified = [override['path'], *(override.get('alts') or [])]
                game.note = override.get('note')
                game.is_template = bool(override.get('template'))
                for alias in override.get('aliases') or []:
                    if alias not in game.aliases:
                        game.aliases.append(alias)
                matched.add(key)
            games.append(game)

        # Community entries with no counterpart in Discord's list still need
        # to be launchable.
        for key, entry in overrides.items():
            if key not in matched:
                games.append(_game_from_override(entry))

        for game in games:
            quest = active.get(game.name.lower())
            if quest is not None:
                game.has_quest = True
                game.quest_reward = quest.reward

        with self._lock:
            self.games = games
            self.generated = int(payload.get('generated') or 0)
            self._by_norm = {}
            for game in games:
                for name in (game.name, *game.aliases):
                    self._by_norm.setdefault(normalise(name), game)

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.generated) > REFRESH_AFTER

    def refresh(self, timeout: int = 30) -> bool:
        """Fetch a fresh list from Discord. Safe to call off the UI thread."""
        request = urllib.request.Request(
            DETECTABLE_URL, headers={'User-Agent': USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                raw = json.load(resp)
        except (urllib.error.URLError, ValueError, OSError, TimeoutError):
            return False

        if not isinstance(raw, list) or len(raw) < 100:
            return False  # implausible payload; keep what we have

        games = []
        for app in raw:
            exes, launchers = [], []
            for entry in app.get('executables') or []:
                if entry.get('os') != 'win32':
                    continue
                name = (entry.get('name') or '').strip().lstrip('/\\')
                if name:
                    (launchers if entry.get('is_launcher') else exes).append(name)
            if not exes and not launchers:
                continue
            steam = next(
                (s.get('id') for s in app.get('third_party_skus') or []
                 if s.get('distributor') == 'steam' and s.get('id')),
                None,
            )
            games.append({
                'id': app.get('id'),
                'name': app.get('name'),
                'aliases': [a for a in (app.get('aliases') or []) if a],
                'exes': exes,
                'launchers': launchers,
                'steam': steam,
                'icon': app.get('icon_hash'),
            })

        payload = {'generated': int(time.time()), 'games': games}
        target = self._cache_file
        tmp = target.with_suffix('.tmp')
        try:
            with gzip.open(tmp, 'wb', compresslevel=6) as fh:
                fh.write(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
            tmp.replace(target)
        except OSError:
            return False

        self.load()
        return True

    # -- lookup ----------------------------------------------------------

    def exact(self, name: str) -> Game | None:
        return self._by_norm.get(normalise(name))

    def search(self, query: str, limit: int = 40) -> list[Game]:
        """Rank games against a query.

        Deliberately conservative: a loose substring match scores low so the
        UI shows it as one option among several rather than silently picking
        it. Naive fuzzy matching maps 'Opera' onto 'ArmA 2: Operation
        Arrowhead' and 'Summoners War' onto 'N++'.
        """
        query = (query or '').strip()
        if not query:
            # No query: community-verified titles, live quests at the top.
            verified = [g for g in self.games if g.is_verified or g.has_quest]
            verified.sort(key=lambda g: (not g.has_quest, g.name.lower()))
            return verified[:limit]

        norm_q = normalise(query)
        expanded = ABBREVIATIONS.get(norm_q)
        if expanded:
            norm_q = normalise(expanded)
            query = expanded
        tok_q = tokens(query)
        results: list[tuple[float, Game]] = []

        for game in self.games:
            best = 0.0
            for candidate in (game.name, *game.aliases):
                norm_c = normalise(candidate)
                if not norm_c:
                    continue
                is_alias = candidate is not game.name

                if norm_c == norm_q:
                    score = 100.0
                elif norm_c.startswith(norm_q):
                    # Shorter names are the better match for a prefix.
                    score = 80.0 - min(len(norm_c) - len(norm_q), 30) * 0.5
                elif norm_q in norm_c:
                    score = 55.0 - min(len(norm_c) - len(norm_q), 30) * 0.5
                else:
                    tok_c = tokens(candidate)
                    if tok_q and all(any(t == c or c.startswith(t) for c in tok_c) for t in tok_q):
                        score = 45.0
                    else:
                        continue

                if is_alias:
                    score -= 3.0
                best = max(best, score)

            if best <= 0:
                continue
            if game.has_quest:
                best += 25.0  # a live quest is what the user is here for
            if game.is_verified:
                best += 12.0  # community-confirmed entries outrank guesses
            if not game.exes and game.launchers:
                best -= 5.0   # launcher-only is a weaker target
            results.append((best, game))

        results.sort(key=lambda pair: (-pair[0], pair[1].name.lower()))
        return [game for _, game in results[:limit]]


_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
        _catalog.load()
    return _catalog
