"""End-to-end check: place a stand-in, run it, confirm it cleans up."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dqc import emulator, journal            # noqa: E402
from dqc.catalog import get_catalog          # noqa: E402
from dqc.duration import parse_duration      # noqa: E402

print('-- duration parsing')
for text in ['', '900', '15m', '1h30m', '25:00', '10 * 60', '(3 * 60) + 20']:
    print(f'   {text!r:16s} -> {parse_duration(text)}s')
for bad in ['abc', '__import__("os")', '-5', '99h']:
    try:
        parse_duration(bad)
        print(f'   {bad!r:16s} -> ACCEPTED (should have failed)')
    except Exception as exc:
        print(f'   {bad!r:16s} -> rejected: {type(exc).__name__}')

print('\n-- recover any leftovers from a previous run')
print('  ', journal.recover() or 'nothing pending')

cat = get_catalog()
game = cat.exact('Where Winds Meet')
plan = emulator.plan_session(game)
print(f'\n-- plan for {game.name}')
print(f'   relative: {plan.relative}')
print(f'   exe     : {plan.exe_path}')
print(f'   root    : {plan.root}')
print(f'   anchored: {plan.anchored}')

session = emulator.Session(plan, seconds=4)
session.start()
time.sleep(1.5)

exists = plan.exe_path.is_file()
size = plan.exe_path.stat().st_size if exists else 0
print(f'\n-- while running')
print(f'   stub on disk : {exists}  ({size / 1024:.0f} KB)')
print(f'   process alive: {session.is_running}  pid={session.process.pid}')
print(f'   journal rows : {len(journal._read_all())}')

code = session.wait()
print(f'\n-- after exit (code {code})')
print(f'   stub removed : {not plan.exe_path.exists()}')
print(f'   root removed : {not plan.root.exists()}')
print(f'   journal rows : {len(journal._read_all())}')

print('\n-- crash simulation: start, kill hard, recover on next launch')
plan2 = emulator.plan_session(cat.exact('VALORANT'))
s2 = emulator.Session(plan2, seconds=120)
s2.start()
time.sleep(1.0)
s2.process.kill()
s2.process.wait()
print(f'   left behind  : {plan2.exe_path.exists()}')
print(f'   journal rows : {len(journal._read_all())}')
notes = journal.recover()
print(f'   recover()    : {notes}')
print(f'   cleaned up   : {not plan2.root.exists()}')
