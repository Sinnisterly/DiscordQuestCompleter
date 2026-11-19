"""List models the QML pages bind to."""

from __future__ import annotations

import datetime as dt
import time

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal, Slot, Property

from ..catalog import Game
from ..duration import format_duration


def ends_label(iso: str | None) -> str:
    if not iso:
        return ''
    try:
        date = dt.date.fromisoformat(iso)
    except ValueError:
        return ''
    days = (date - dt.date.today()).days
    if days <= 0:
        return 'Ends today'
    if days == 1:
        return 'Ends tomorrow'
    return f'Ends {date.month}/{date.day}'


class GameListModel(QAbstractListModel):
    """Games shown in the library list or as quest cards."""

    countChanged = Signal()

    _ROLES = {
        Qt.UserRole + 1: b'gameId',
        Qt.UserRole + 2: b'name',
        Qt.UserRole + 3: b'path',
        Qt.UserRole + 4: b'verified',
        Qt.UserRole + 5: b'hasQuest',
        Qt.UserRole + 6: b'reward',
        Qt.UserRole + 7: b'endsLabel',
        Qt.UserRole + 8: b'needsSteam',
        Qt.UserRole + 9: b'pathCount',
        Qt.UserRole + 10: b'questSource',
        Qt.UserRole + 11: b'orbs',
        Qt.UserRole + 12: b'title',
        Qt.UserRole + 13: b'accepted',   # 1 yes, 0 no, -1 unknown
        Qt.UserRole + 14: b'progress',   # percent from Discord, -1 unknown
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._games: list[Game] = []

    def roleNames(self):  # noqa: N802 - Qt naming
        return self._ROLES

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self._games)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._games):
            return None
        game = self._games[index.row()]
        name = self._ROLES.get(role)
        if name == b'gameId':
            return game.id
        if name == b'name':
            return game.name
        if name == b'path':
            return game.primary or ''
        if name == b'verified':
            return game.is_verified
        if name == b'hasQuest':
            return game.has_quest
        if name == b'reward':
            return game.quest_reward or ''
        if name == b'endsLabel':
            return ends_label(game.quest_ends)
        if name == b'needsSteam':
            return not game.detectable
        if name == b'pathCount':
            return len(game.candidates)
        if name == b'questSource':
            return game.quest_source or ''
        if name == b'orbs':
            return game.quest_orbs or 0
        if name == b'title':
            return game.quest_title or game.name
        if name == b'progress':
            return -1 if game.quest_progress is None else game.quest_progress
        if name == b'accepted':
            return -1 if game.quest_accepted is None else int(game.quest_accepted)
        return None

    def set_games(self, games: list[Game]) -> None:
        self.beginResetModel()
        self._games = list(games)
        self.endResetModel()
        self.countChanged.emit()

    def refresh(self) -> None:
        """Redraw every row after badges changed in place."""
        if self._games:
            self.dataChanged.emit(self.index(0), self.index(len(self._games) - 1))

    @Slot(str, result=int)
    def indexOf(self, game_id: str) -> int:  # noqa: N802
        for row, game in enumerate(self._games):
            if game.id == game_id:
                return row
        return -1

    @Slot(int, result=str)
    def idAt(self, row: int) -> str:  # noqa: N802
        return self._games[row].id if 0 <= row < len(self._games) else ''

    def _count(self) -> int:
        return len(self._games)

    count = Property(int, _count, notify=countChanged)


class SessionEntry:
    def __init__(self, session_id: int, session, watcher):
        self.id = session_id
        self.session = session
        self.watcher = watcher       # keeps the watcher thread's QObject alive
        self.started = time.monotonic()
        self.ended: str | None = None   # 'finished' or 'stopped'
        self.group = None               # GroupWindow when launched with others

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def completed(self) -> bool:
        """True when the session ran its full duration.

        Measured from elapsed time rather than a flag, so closing the
        countdown window counts as stopping early just as Stop does.
        """
        return self.elapsed >= self.session.seconds - 2


class SessionModel(QAbstractListModel):
    countChanged = Signal()

    _ROLES = {
        Qt.UserRole + 1: b'sessionId',
        Qt.UserRole + 2: b'name',
        Qt.UserRole + 3: b'path',
        Qt.UserRole + 4: b'progress',
        Qt.UserRole + 5: b'status',
        Qt.UserRole + 6: b'state',
        Qt.UserRole + 7: b'gameId',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[SessionEntry] = []

    def roleNames(self):  # noqa: N802
        return self._ROLES

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        entry = self.entries[index.row()]
        total = entry.session.seconds
        name = self._ROLES.get(role)
        if name == b'sessionId':
            return entry.id
        if name == b'gameId':
            return entry.session.game.id
        if name == b'name':
            return entry.session.game.name
        if name == b'path':
            return str(entry.session.plan.exe_path)
        if name == b'progress':
            if entry.ended == 'finished':
                return 1.0
            return min(1.0, entry.elapsed / total) if total else 1.0
        if name == b'status':
            if entry.ended == 'finished':
                return 'Finished'
            if entry.ended == 'stopped':
                return 'Stopped early'
            return f'{format_duration(max(0, total - entry.elapsed))} left'
        if name == b'state':
            return entry.ended or 'running'
        return None

    def add(self, entry: SessionEntry) -> None:
        row = len(self.entries)
        self.beginInsertRows(QModelIndex(), row, row)
        self.entries.append(entry)
        self.endInsertRows()
        self.countChanged.emit()

    def remove(self, entry: SessionEntry) -> None:
        if entry not in self.entries:
            return
        row = self.entries.index(entry)
        self.beginRemoveRows(QModelIndex(), row, row)
        self.entries.pop(row)
        self.endRemoveRows()
        self.countChanged.emit()

    def changed(self, entry: SessionEntry) -> None:
        if entry in self.entries:
            row = self.entries.index(entry)
            self.dataChanged.emit(self.index(row), self.index(row))

    def tick(self) -> None:
        if self.entries:
            self.dataChanged.emit(self.index(0), self.index(len(self.entries) - 1))

    @property
    def running(self) -> list[SessionEntry]:
        return [e for e in self.entries if e.ended is None and e.session.is_running]

    def _count(self) -> int:
        return len(self.entries)

    count = Property(int, _count, notify=countChanged)
