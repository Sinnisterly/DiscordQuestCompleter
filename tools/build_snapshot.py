"""Rebuild the bundled detectable-games snapshot.

Downloads Discord's public detectable-application list, strips it to the
fields the app actually uses, and writes a gzipped snapshot into the package.

    python tools/build_snapshot.py

The app refreshes this from the network at runtime; the snapshot is only the
offline fallback and the first-launch experience.
"""

import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

URL = 'https://discord.com/api/v9/applications/detectable'
OUT = Path(__file__).resolve().parent.parent / 'dqc' / 'data' / 'detectable.json.gz'

# Discord answers 403 to urllib's default User-Agent.
UA = 'DiscordQuestCompleter/1.0 (+https://github.com/Sinnisterly/DiscordQuestCompleter)'


def slim(raw: list) -> list:
    games = []
    for app in raw:
        exes, launchers = [], []
        for entry in app.get('executables') or []:
            if entry.get('os') != 'win32':
                continue
            name = (entry.get('name') or '').strip().lstrip('/\\')
            if not name:
                continue
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
    return games


def main() -> int:
    print(f'fetching {URL} ...')
    request = urllib.request.Request(URL, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=60) as resp:
        raw = json.load(resp)
    print(f'  {len(raw)} applications')

    games = slim(raw)
    print(f'  {len(games)} with win32 executables')

    payload = {'generated': int(time.time()), 'games': games}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    with gzip.open(OUT, 'wb', compresslevel=9) as fh:
        fh.write(blob)

    print(f'wrote {OUT}  ({len(blob) / 1e6:.1f} MB raw, {OUT.stat().st_size / 1e6:.2f} MB gzipped)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
