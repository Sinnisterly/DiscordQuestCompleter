"""Check orb tracking, new-quest memory and the Start with Windows entry.

Orb and quest data go to a temporary folder. The startup check changes the
real registry value under your user's Run key, then puts back what was there.
"""

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='dqc-check-')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dqc import orbs, quests, startup  # noqa: E402

failures = []


def check(label, ok, detail=''):
    print(f'  {"ok  " if ok else "FAIL"} {label}{f": {detail}" if detail else ""}')
    if not ok:
        failures.append(label)


print('orbs')
now = dt.datetime(2026, 11, 19, 12, 0).timestamp()
day = 86400
check('empty summary', orbs.summary(now)['balance'] == -1)
orbs.record(100, now - 40 * day)   # before this month
orbs.record(100, now - 39 * day)   # unchanged: not stored
orbs.record(940, now - 10 * day)   # +840 earlier this month
orbs.record(640, now - 9 * day)    # spent 300
orbs.record(1480, now - 1 * day)   # +840 this week (Wednesday the 18th)
summary = orbs.summary(now)
check('rows stored only on change', len(orbs.history()) == 4, len(orbs.history()))
check('balance', summary['balance'] == 1480, summary['balance'])
check('earned this week', summary['week'] == 840, summary['week'])
check('earned this month', summary['month'] == 1680, summary['month'])
check('earned in total', summary['total'] == 1680, summary['total'])
check('spent', summary['spent'] == 300, summary['spent'])
check('30 day chart', len(summary['chart']) == 30 and summary['chart'][-1]['balance'] == 1480)

print('new quest alerts')
check('first scan is a baseline', quests.new_quests(['A QUEST', 'B QUEST']) == [])
check('nothing new', quests.new_quests(['A QUEST', 'B QUEST']) == [])
check('a new quest is reported', quests.new_quests(['A QUEST', 'C QUEST']) == ['C QUEST'])
check('a quest that returns is not reported again', quests.new_quests(['B QUEST']) == [])

print('reminders and quest time')
check('first reminder fires', quests.remind_once('ready:A QUEST'))
check('same reminder does not fire again', not quests.remind_once('ready:A QUEST'))
from dqc.duration import quest_seconds  # noqa: E402
check('30-minute quest runs 30m 30s', quest_seconds(30) == 1830)
check('unknown quest runs 15m 30s', quest_seconds(None) == 930)

print('updates')
from dqc import updates  # noqa: E402
check('newer release noticed', updates.is_newer('v2.6', '2.5.0'))
check('same release ignored', not updates.is_newer('v2.5', '2.5.0'))
check('older release ignored', not updates.is_newer('v2.1', '2.5.0'))

print('start with windows')
before = startup.is_enabled()
check('command uses --tray', startup.command().endswith(startup.TRAY_FLAG), startup.command())
check('turn on', startup.set_enabled(True) == '' and startup.is_enabled())
check('turn off', startup.set_enabled(False) == '' and not startup.is_enabled())
startup.set_enabled(before)
check('restored', startup.is_enabled() == before)

print('\nFAIL' if failures else '\nOK')
sys.exit(1 if failures else 0)
