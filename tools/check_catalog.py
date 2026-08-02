"""Sanity checks for the catalogue: override linkage and search quality."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dqc.appdirs import bundled          # noqa: E402
from dqc.catalog import get_catalog, normalise  # noqa: E402

cat = get_catalog()
print(f'catalogue: {len(cat.games)} games, generated={cat.generated}')

overrides = json.loads(bundled('data/overrides.json').read_text(encoding='utf-8'))['entries']
linked = [g for g in cat.games if g.is_verified]
print(f'overrides: {len(overrides)} entries -> {len(linked)} linked\n')

unlinked = [e['name'] for e in overrides if not cat.exact(e['name'])]
if unlinked:
    print('UNLINKED (name does not match any Discord entry):')
    for name in unlinked:
        print(f'  - {name}')
    print()

print('search behaviour:')
for query in ['where winds', 'valorant', 'opera', 'summoners war', 'runescape', 'fc 26', 'zzz']:
    hits = cat.search(query, limit=3)
    rendered = ', '.join(f'{g.name}{"*" if g.is_verified else ""}' for g in hits)
    print(f'  {query:16s} -> {rendered or "(nothing)"}')

print('\nresolved primary paths:')
for name in ['Where Winds Meet', 'VALORANT', 'PUBG: BATTLEGROUNDS', 'Vindictus', 'Roblox']:
    game = cat.exact(name)
    print(f'  {name:24s} -> {game.primary if game else "MISSING"}')

sys.exit(1 if unlinked else 0)
