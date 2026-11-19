"""Check the quest parser against a saved copy of Discord's Quests page.

The fixture is the accessibility tree of the quest list only, captured from
the real client. Play quests and Launch Quest activities must be found, video
quests skipped, and "X on Roblox" must map to Roblox.
"""

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dqc.catalog import get_catalog                                     # noqa: E402
from dqc.discordui import ACTIVITY, PLAY, Node, _infer_year, match_quests, parse_quests  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'quest_home.json'

root = Node.from_dict(json.loads(FIXTURE.read_text(encoding='utf-8')))
scan = parse_quests(root, today=dt.date(2026, 11, 19))

# (kind, game or title) -> (reward, orbs, ends)
expected = {
    (PLAY, 'Delta Force'): ('840 Orbs', 840, dt.date(2026, 11, 19)),
    (PLAY, 'Call of Duty: Modern Warfare 4'): ('Weapons Blueprint', None, dt.date(2026, 11, 20)),
    (ACTIVITY, "Audible's Exoplanet"): ('840 Orbs', 840, dt.date(2026, 11, 21)),
    (PLAY, 'Where Winds Meet'): ('840 Orbs', 840, dt.date(2026, 11, 22)),
    (PLAY, 'Arknights: Endfield'): ('840 Orbs', 840, dt.date(2026, 11, 24)),
    (PLAY, 'Illegal Soccer on Roblox'): ('840 Orbs', 840, dt.date(2026, 11, 25)),
    (ACTIVITY, 'Blade Runner 2099'): ('840 Orbs', 840, dt.date(2026, 11, 27)),
    (PLAY, 'Honkai: Star Rail'): ('V4.7 Quest Bundle', None, dt.date(2026, 12, 1)),
}

failures = []
got = {(q.kind, q.game or q.title): (q.reward, q.orbs, q.ends) for q in scan.quests}
if not scan.ok:
    failures.append(f'scan not ok: {scan.reason}')
if got != expected:
    failures.append(f'mismatch:\n  got      {got}\n  expected {expected}')

# The fixture was captured before any quest was accepted.
by_game = {q.game: q for q in scan.quests if q.kind == PLAY}
if by_game['Delta Force'].accepted or by_game['Delta Force'].heading != 'NEW SEASON AURORA QUEST':
    failures.append('Delta Force should be unaccepted with its card heading kept')

# Matching against the real catalogue.
catalog = get_catalog()
entries, other = match_quests(scan.quests, catalog.exact)
runnable = {e['name'].lower(): e['title'] for e in entries}
if runnable.get('roblox') != 'Illegal Soccer on Roblox':
    failures.append(f'Illegal Soccer should run Roblox: {runnable}')
if len(entries) != 6:
    failures.append(f'expected 6 runnable quests, got {sorted(runnable)}')
if sorted(o['title'] for o in other) != ["Audible's Exoplanet", 'Blade Runner 2099']:
    failures.append(f'other quests: {[o["title"] for o in other]}')

# Progress comes from the ring on a started quest: "Quest progress: 52%".
started = Node.from_dict(json.loads(FIXTURE.read_text(encoding='utf-8')))
tile = next(n for n in started.walk() if n.name == 'NEW SEASON AURORA QUEST' and 'questTile_' in n.cls)
tile.children.append(Node('Quest progress: 52%', 'outer_x', 'ProgressBar'))
if next(q for q in parse_quests(started).quests if q.game == 'Delta Force').progress != 52:
    failures.append('progress ring not read')
if by_game['Delta Force'].progress is not None:
    failures.append('a quest that has not started should have no progress')

# An accepted card has a platform dropdown named after the current choice.
# Anything but Desktop means running the game on this PC will not count.
tile.children.append(Node('Xbox', 'container_x platformSelectorSecondary_x', 'Button'))
on_xbox = next(q for q in parse_quests(started).quests if q.game == 'Delta Force')
if on_xbox.platform != 'Xbox':
    failures.append(f'platform dropdown not read: {on_xbox.platform}')
entries_xbox, _ = match_quests([on_xbox], catalog.exact)
if entries_xbox[0].get('platform') != 'Xbox':
    failures.append('platform not passed on for saving')
if by_game['Delta Force'].platform is not None:
    failures.append('a card without a dropdown should have no platform')

# A page with no tiles must fail safe with a reason.
empty = parse_quests(Node('Quests - Discord', '', 'Window'))
if empty.ok or not empty.reason:
    failures.append('empty page should report a reason')

if _infer_year(1, 3, dt.date(2026, 12, 30)) != dt.date(2027, 1, 3):
    failures.append('Ends 1/3 seen on 12/30 should be next year')

for quest in scan.quests:
    print(f'  {quest.kind:8s} {(quest.game or quest.title):34s} orbs {quest.orbs!s:5s} ends {quest.ends}')
print(f'  runnable: {runnable}')
print('\nFAIL\n' + '\n'.join(failures) if failures else '\nOK')
sys.exit(1 if failures else 0)
