"""Orb balance over time.

Every time the Quests page is read, the balance shown at the top of it is
passed to record(). A new row is stored only when the balance changes, so
the file stays small. Rises count as orbs earned and drops as orbs spent.

The app can only see the balance while Discord's Quests page is open, so
the history has gaps. Earnings are worked out from the change between
readings, which is right however long the gap was.
"""

from __future__ import annotations

import datetime as dt
import json
import time

from .appdirs import data_dir

FILE_NAME = 'orbs.json'
MAX_ROWS = 5000


def _path():
    return data_dir() / FILE_NAME


def history() -> list[tuple[int, int]]:
    """[(unix time, balance), ...] oldest first."""
    try:
        rows = json.loads(_path().read_text(encoding='utf-8')).get('history') or []
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for row in rows:
        if (isinstance(row, list) and len(row) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) for v in row)):
            out.append((row[0], row[1]))
    return out


def record(balance: int, now: float | None = None) -> bool:
    """Store a reading if the balance changed. Returns True if stored."""
    if balance is None or balance < 0:
        return False
    rows = history()
    if rows and rows[-1][1] == balance:
        return False
    rows.append((int(now if now is not None else time.time()), int(balance)))
    rows = rows[-MAX_ROWS:]
    target = _path()
    try:
        tmp = target.with_suffix('.tmp')
        tmp.write_text(json.dumps({'version': 1, 'history': rows}), encoding='utf-8')
        tmp.replace(target)
    except OSError:
        return False
    return True


def _earned_since(rows: list[tuple[int, int]], since: float) -> int:
    earned = 0
    for (_t0, b0), (t1, b1) in zip(rows, rows[1:]):
        if t1 >= since and b1 > b0:
            earned += b1 - b0
    return earned


def summary(now: float | None = None) -> dict:
    """Numbers for the Orbs page. Every value is 0 or empty with no history."""
    now = now if now is not None else time.time()
    rows = history()
    today = dt.date.fromtimestamp(now)
    week_start = today - dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def stamp(day: dt.date) -> float:
        return dt.datetime.combine(day, dt.time()).timestamp()

    spent = sum(b0 - b1 for (_t0, b0), (_t1, b1) in zip(rows, rows[1:]) if b1 < b0)

    # Closing balance for each of the last 30 days, carried forward.
    chart = []
    if rows:
        index, balance = 0, None
        for offset in range(29, -1, -1):
            day = today - dt.timedelta(days=offset)
            end = stamp(day + dt.timedelta(days=1))
            while index < len(rows) and rows[index][0] < end:
                balance = rows[index][1]
                index += 1
            chart.append({'day': f'{day.month}/{day.day}', 'balance': balance if balance is not None else -1})

    return {
        'balance': rows[-1][1] if rows else -1,
        'updated': rows[-1][0] if rows else 0,
        'since': rows[0][0] if rows else 0,
        'week': _earned_since(rows, stamp(week_start)),
        'month': _earned_since(rows, stamp(month_start)),
        'total': _earned_since(rows, 0),
        'spent': spent,
        'chart': chart,
    }
