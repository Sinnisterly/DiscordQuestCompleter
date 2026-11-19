"""Everything the QML interface can ask for, exposed as `Backend`.

QML never touches the catalogue, emulator or quest files directly. It calls
slots here and redraws when the signals fire.

Background work (catalogue refresh, quest scans, waiting on sessions) runs
on plain threads and reports back through Qt signals. A signal emitted from
another thread is queued onto the UI thread, which is what makes the
hand-off safe. The old interface used QTimer.singleShot from a plain thread
instead; that thread has no event loop, so the callback never ran and the
refresh never finished.
"""

from __future__ import annotations

import itertools
import threading
import time

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .. import __version__, discordui, emulator, journal, quests, settings, thumbs
from ..appdirs import data_dir
from ..catalog import Catalog, Game
from ..duration import DEFAULT_SECONDS, DurationError, format_duration, parse_duration
from .models import GameListModel, SessionEntry, SessionModel, ends_label
from .theme_bridge import ThemeBridge

WATCH_INTERVAL_MS = 10_000      # how often to look for the Quests page
WATCH_MIN_GAP = 60              # seconds between automatic scans
WATCH_RUNNING_GAP = 20          # the same while sessions are running
STALE_CHECK_MS = 60 * 60 * 1000  # hourly check for an outdated catalogue
REMOVE_FINISHED_AFTER_MS = 4000

PLACEMENTS = [
    (emulator.SANDBOX, 'Sandbox'),
    (emulator.STEAM, 'Steam library'),
    (emulator.INSTALLED, 'Replace install'),
]


def _ago(stamp: float) -> str:
    seconds = max(0, time.time() - stamp)
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f'{minutes} min ago'
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f'{hours} hr ago'
    days = int(seconds // 86400)
    return f'{days} day{"s" if days != 1 else ""} ago'


class _SessionWatcher(QObject):
    """Bridges a blocking Session.wait() into a Qt signal."""

    finished = Signal(object)

    def __init__(self, session: emulator.Session):
        super().__init__()
        self.session = session
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        self.session.wait()
        self.finished.emit(self.session)


class Backend(QObject):
    # To QML
    statusChanged = Signal()          # catalogue and quest status text
    catalogChanged = Signal()         # games or badges changed; re-read details
    settingsChanged = Signal()
    toast = Signal(str, str)          # text, kind: info / good / bad
    dialogRequested = Signal(int, str, str, str, str)  # token, title, body, ok, cancel
    showWindowRequested = Signal()
    hideWindowRequested = Signal()
    quitRequested = Signal()          # the app should exit now
    notify = Signal(str, str)         # tray notification: title, body

    # From worker threads, queued onto the UI thread
    _refreshDone = Signal(bool, bool)
    _scanDone = Signal(object, bool)
    _acceptDone = Signal(object, object)   # {heading: outcome}, fresh Scan

    def __init__(self, catalog: Catalog, theme: ThemeBridge, tray_available: bool):
        super().__init__()
        self.catalog = catalog
        self.theme = theme
        self.tray_available = tray_available
        self.library = GameListModel(self)
        self.quests = GameListModel(self)
        self.sessions = SessionModel(self)

        self._query = ''
        self._refreshing = False
        self._refresh_failed = False
        self._detecting = False
        self._last_auto_scan = 0.0
        self._dialogs: dict[int, callable] = {}
        self._tokens = itertools.count(1)
        self._session_ids = itertools.count(1)
        self._launching_all = False
        self._groups: dict = {}   # GroupWindow -> (watcher, entries)
        self._quitting = False

        self._refreshDone.connect(self._on_refresh_done)
        self._scanDone.connect(self._on_scan_done)
        self._acceptDone.connect(self._on_accept_done)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(500)

        self._stale_timer = QTimer(self)
        self._stale_timer.timeout.connect(self._maybe_refresh)
        self._stale_timer.start(STALE_CHECK_MS)

        self._watch_timer = QTimer(self)
        self._watch_timer.timeout.connect(self._watch)
        self._watch_timer.start(WATCH_INTERVAL_MS)

        # Status text such as "5 min ago" goes stale on its own.
        self._clock = QTimer(self)
        self._clock.timeout.connect(self.statusChanged.emit)
        self._clock.start(30_000)

        self.search('')
        self._reload_quests()

    # ------------------------------------------------------------ startup

    @Slot()
    def startup(self) -> None:
        """Called once the window is up."""
        notes = journal.recover()
        if notes:
            self._message(
                'Cleaned up an earlier session',
                'These were left behind by a session that did not end normally '
                'and have been put back:\n\n' + '\n'.join(f'- {n}' for n in notes),
            )
        self._maybe_refresh()
        self._watch()

    # ------------------------------------------------------------ properties

    def _catalog_status(self) -> str:
        if self._refreshing:
            return 'Updating the game list'
        count = len(self.catalog.games)
        if self.catalog.generated:
            age = max(0, time.time() - self.catalog.generated)
            when = 'today' if age < 86400 else f'{int(age // 86400)} days ago'
        else:
            when = 'never'
        text = f'{count:,} games, updated {when}'
        if self._refresh_failed:
            text += '. Last update failed'
        return text

    def _quest_status(self) -> str:
        if self._detecting:
            return 'Reading Discord'
        stamp = quests.detected_at()
        return f'Checked Discord {_ago(stamp)}' if stamp else 'Not checked yet'

    def _is_refreshing(self) -> bool:
        return self._refreshing

    def _is_detecting(self) -> bool:
        return self._detecting

    def _other_quests(self) -> list:
        """Quests on the Discord page that this app cannot run."""
        out = []
        for quest in quests.load_other():
            out.append({**quest, 'endsLabel': ends_label(quest['until'])})
        return out

    def _other_orbs(self) -> int:
        return sum(q['orbs'] for q in quests.load_other())

    def _running_count(self) -> int:
        return len(self.sessions.running)

    def _default_duration(self) -> str:
        return format_duration(DEFAULT_SECONDS)

    def _game_count(self) -> int:
        return len(self.catalog.games)

    def _quest_orbs(self) -> int:
        """Orbs on offer across every live quest that pays in orbs."""
        return sum(g.quest_orbs or 0 for g in self.catalog.quest_games())

    questOrbs = Property(int, _quest_orbs, notify=catalogChanged)

    def _version(self) -> str:
        return __version__

    def _data_folder(self) -> str:
        return str(data_dir())

    version = Property(str, _version, constant=True)
    dataFolder = Property(str, _data_folder, constant=True)

    catalogStatus = Property(str, _catalog_status, notify=statusChanged)
    questStatus = Property(str, _quest_status, notify=statusChanged)
    refreshing = Property(bool, _is_refreshing, notify=statusChanged)
    detecting = Property(bool, _is_detecting, notify=statusChanged)

    def _is_launching_all(self) -> bool:
        return self._launching_all

    launchingAll = Property(bool, _is_launching_all, notify=statusChanged)
    otherQuests = Property('QVariantList', _other_quests, notify=catalogChanged)
    otherOrbs = Property(int, _other_orbs, notify=catalogChanged)
    runningCount = Property(int, _running_count, notify=statusChanged)
    defaultDuration = Property(str, _default_duration, constant=True)
    gameCount = Property(int, _game_count, notify=catalogChanged)

    def _get_tray(self) -> bool:
        return self.tray_available and bool(settings.get('minimise_to_tray'))

    def _set_tray(self, value: bool) -> None:
        settings.set_value('minimise_to_tray', bool(value))
        self.settingsChanged.emit()

    def _get_notify(self) -> bool:
        return bool(settings.get('notify_on_finish'))

    def _set_notify(self, value: bool) -> None:
        settings.set_value('notify_on_finish', bool(value))
        self.settingsChanged.emit()

    def _get_watch(self) -> bool:
        return bool(settings.get('watch_quests', True))

    def _set_watch(self, value: bool) -> None:
        settings.set_value('watch_quests', bool(value))
        self.settingsChanged.emit()
        if value:
            self._watch()

    def _get_tray_available(self) -> bool:
        return self.tray_available

    trayEnabled = Property(bool, _get_tray, _set_tray, notify=settingsChanged)
    notifyEnabled = Property(bool, _get_notify, _set_notify, notify=settingsChanged)
    watchQuests = Property(bool, _get_watch, _set_watch, notify=settingsChanged)
    trayAvailable = Property(bool, _get_tray_available, constant=True)

    # ------------------------------------------------------------ dialogs

    def _ask(self, title: str, body: str, ok: str, on_yes, cancel: str = 'Cancel') -> None:
        token = next(self._tokens)
        self._dialogs[token] = on_yes
        self.showWindowRequested.emit()
        self.dialogRequested.emit(token, title, body, ok, cancel)

    def _message(self, title: str, body: str) -> None:
        self._ask(title, body, 'OK', None, cancel='')

    @Slot(int, bool)
    def answer(self, token: int, accepted: bool) -> None:
        callback = self._dialogs.pop(token, None)
        if accepted and callback is not None:
            callback()

    # ------------------------------------------------------------ library

    @Slot(str)
    def search(self, text: str) -> None:
        self._query = text or ''
        self.library.set_games(self.catalog.search(self._query, limit=80))

    def _reload_quests(self) -> None:
        self.quests.set_games(self.catalog.quest_games())

    def _badges_changed(self) -> None:
        """Quest state changed: re-sort the lists and tell QML."""
        self.catalog.apply_quests()
        self.search(self._query)
        self._reload_quests()
        self.catalogChanged.emit()

    @Slot(str, result='QVariantMap')
    def gameDetail(self, game_id: str) -> dict:
        game = self.catalog.by_id(game_id)
        if game is None:
            return {}

        notes, warn = [], False
        if not game.detectable:
            notes.append(
                'Discord lists no executable for this game. It usually only '
                'registers when the game is installed through Steam and you '
                'pick Replace install.'
            )
            warn = True
        if game.requires:
            notes.append(game.requires)
            warn = True
        if game.requires_url:
            notes.append(game.requires_url)
        if game.note:
            notes.append(game.note)
        if game.is_template:
            notes.append('A new folder id is made for each launch.')

        install = emulator.find_installed(game)
        placements = []
        for mode, label in PLACEMENTS:
            enabled = True
            if mode == emulator.INSTALLED:
                label = (
                    f'Replace install ({install["installdir"]})'
                    if install else 'Replace install (not installed)'
                )
                enabled = install is not None
            placements.append({'mode': mode, 'label': label, 'enabled': enabled})

        # Warm the square icon so the countdown window can use it.
        if thumbs.icon_url(game) and thumbs.icon_path(game) is None:
            threading.Thread(target=thumbs.ensure_icon, args=(game,), daemon=True).start()

        return {
            'id': game.id,
            'name': game.name,
            'notes': ' '.join(notes),
            'warn': warn,
            'paths': [
                {'path': p, 'verified': p in game.verified} for p in game.candidates
            ],
            'placements': placements,
            'defaultMode': self._default_mode(game, install),
            'hasQuest': game.has_quest,
            'questSource': game.quest_source or '',
            'reward': game.quest_reward or '',
            'orbs': game.quest_orbs or 0,
        }

    @staticmethod
    def _default_mode(game: Game, install=None) -> str:
        """Replacing a real install is the only thing that works for titles
        Discord cannot match by process, so pick it when one is present."""
        if not game.detectable and install is not None:
            return emulator.INSTALLED
        return emulator.SANDBOX

    @Slot(str, str, str, result='QVariantMap')
    def planPath(self, game_id: str, path: str, mode: str) -> dict:
        game = self.catalog.by_id(game_id)
        if game is None or not game.candidates:
            return {'ok': False, 'text': 'No executable path is known for this game.'}
        try:
            plan = emulator.plan_session(game, path or None, mode=mode or emulator.SANDBOX)
        except emulator.EmulationError as exc:
            return {'ok': False, 'text': str(exc)}
        return {'ok': True, 'text': str(plan.exe_path)}

    @Slot(str, result='QVariantMap')
    def durationHint(self, text: str) -> dict:
        try:
            seconds = parse_duration(text)
        except DurationError as exc:
            return {'ok': False, 'text': str(exc).capitalize() + '.'}
        suffix = ' (default)' if not (text or '').strip() else ''
        return {'ok': True, 'text': f'Runs for {format_duration(seconds)}{suffix}'}

    @Slot(str, bool)
    def setQuestMarked(self, game_id: str, marked: bool) -> None:  # noqa: N802
        game = self.catalog.by_id(game_id)
        if game is None:
            return
        quests.local_set(game.name, marked)
        self._badges_changed()

    # ------------------------------------------------------------ launching

    @Slot(str, str, str, str)
    def launch(self, game_id: str, path: str, mode: str, duration: str) -> None:
        game = self.catalog.by_id(game_id)
        if game is None:
            return
        try:
            seconds = parse_duration(duration)
        except DurationError as exc:
            self.toast.emit(str(exc).capitalize() + '.', 'bad')
            return
        try:
            plan = emulator.plan_session(game, path or None, mode=mode or emulator.SANDBOX)
        except emulator.EmulationError as exc:
            self.toast.emit(str(exc), 'bad')
            return
        self._confirm_and_start(game, plan, seconds)

    @Slot(str)
    def quickLaunch(self, game_id: str) -> None:  # noqa: N802
        """Launch with the best path, automatic placement and the default time."""
        game = self.catalog.by_id(game_id)
        if game is None:
            return
        if not game.candidates:
            self.toast.emit(f'No executable path is known for {game.name}.', 'bad')
            return
        mode = self._default_mode(game, emulator.find_installed(game))
        try:
            plan = emulator.plan_session(game, None, mode=mode)
        except emulator.EmulationError as exc:
            self.toast.emit(str(exc), 'bad')
            return
        self._confirm_and_start(game, plan, DEFAULT_SECONDS)

    def _confirm_and_start(self, game: Game, plan, seconds: int) -> None:
        def steam_step():
            if plan.warning:
                self._ask(
                    'Write inside your Steam library?',
                    f'{plan.warning}\n\n{plan.exe_path}\n\nOnly some games need '
                    'this, when they check that their folder came from Steam.',
                    'Continue', lambda: self._start(plan, seconds),
                )
            else:
                self._start(plan, seconds)

        # Warn before the user spends the whole duration finding out. Replacing
        # a real install is what these titles accept, so skip the warning then.
        risky = (not game.detectable or game.requires) and plan.mode != emulator.INSTALLED
        if risky:
            reasons = []
            if not game.detectable:
                reasons.append(
                    'Discord lists no executable for this game. Games like this '
                    'usually only register when installed through Steam and '
                    'launched with Replace install.'
                )
            if game.requires:
                reasons.append(game.requires)
            if game.requires_url:
                reasons.append(game.requires_url)
            self._ask(
                'This one may not register',
                '\n\n'.join(reasons) + '\n\nStart anyway?',
                'Start anyway', steam_step,
            )
        else:
            steam_step()

    def _start(self, plan, seconds: int, group=None) -> SessionEntry | None:
        """Start one session.

        In a group, its window is a 1x1 tool window parked off-screen. Discord
        only counts a game that owns a visible window, so it needs one, but
        the group window shows the countdown instead.
        """
        session = emulator.Session(
            plan, seconds, icon=thumbs.icon_path(plan.game), theme=self.theme.colors,
            quiet='offscreen' if group is not None else None,
        )
        try:
            session.start()
        except emulator.EmulationError as exc:
            if group is None:
                self._message('Could not start', str(exc))
            return None
        watcher = _SessionWatcher(session)
        entry = SessionEntry(next(self._session_ids), session, watcher)
        entry.group = group
        watcher.finished.connect(lambda _s, e=entry: self._session_finished(e))
        self.sessions.add(entry)
        self.statusChanged.emit()
        if group is None:
            self.toast.emit(f'{plan.game.name} is running for {format_duration(seconds)}.', 'good')
        return entry

    # ------------------------------------------------------------ launch all

    def _launchable(self) -> list[Game]:
        """Quest games with a known path that are not already running."""
        running = {e.session.game.id for e in self.sessions.running}
        return [g for g in self.catalog.quest_games() if g.candidates and g.id not in running]

    @Slot()
    def launchAll(self) -> None:  # noqa: N802
        """Accept any quests not yet accepted, then run every quest at once.

        Accepting only happens when Discord's Quests page is open, and only
        for quests read from it. Each game runs its own stand-in, with its window off-screen,
        since Discord detects each process, and one window counts down for
        all of them.
        """
        if self._launching_all:
            return
        games = self._launchable()
        if not games:
            self.toast.emit('Nothing to launch. Every quest is running or has no known path.', 'info')
            return

        to_accept = {g.quest_heading for g in games if g.quest_accepted is False and g.quest_heading}
        if not to_accept or discordui.find_quests_window() is None:
            note = ''
            if to_accept:
                note = (f'{len(to_accept)} not accepted yet. Open the Quests page in Discord '
                        'to have them accepted for you.')
            self._launch_group(games, note)
            return

        self._launching_all = True
        self.statusChanged.emit()

        def work():
            try:
                outcome = discordui.accept_quests(to_accept)
                time.sleep(1.0)
                result = discordui.scan()
            except Exception as exc:  # noqa: BLE001 - report it rather than lose the thread
                outcome, result = {}, discordui.Scan([], ok=False, reason=str(exc))
            self._acceptDone.emit(outcome, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_accept_done(self, outcome: dict, result) -> None:
        self._launching_all = False
        if result.ok:
            self._apply_scan(result)
        accepted = sum(1 for g in self.catalog.quest_games() if g.quest_heading in outcome and g.quest_accepted)
        stuck = [h for h in outcome if not any(
            g.quest_heading == h and g.quest_accepted for g in self.catalog.quest_games())]
        if stuck:
            discordui.save_debug_popup()
        note = f'Accepted {accepted} quest{"s" if accepted != 1 else ""} in Discord.' if accepted else ''
        if stuck:
            note += (f' {len(stuck)} could not be accepted. Finish accepting '
                     f'{"it" if len(stuck) == 1 else "them"} in Discord.')
        self._launch_group(self._launchable(), note.strip())

    def _launch_group(self, games: list[Game], note: str = '') -> None:
        plans, skipped = [], []
        for game in games:
            mode = self._default_mode(game, emulator.find_installed(game))
            # Games that need a confirmation are left for a single launch.
            if (not game.detectable or game.requires) and mode != emulator.INSTALLED:
                skipped.append(game.name)
                continue
            try:
                plans.append(emulator.plan_session(game, None, mode=mode))
            except emulator.EmulationError:
                skipped.append(game.name)

        group = emulator.GroupWindow([p.game.quest_title or p.game.name for p in plans],
                                     DEFAULT_SECONDS, self.theme.colors)
        entries = [e for e in (self._start(p, DEFAULT_SECONDS, group) for p in plans) if e]
        if not entries:
            self.toast.emit('No quests could be launched. ' + note, 'bad')
            return
        group.names = [e.session.game.quest_title or e.session.game.name for e in entries]
        try:
            group.start()
        except emulator.EmulationError as exc:
            self.toast.emit(str(exc), 'bad')
        else:
            watcher = _SessionWatcher(group)
            watcher.finished.connect(lambda _g, g=group: self._group_closed(g))
            self._groups[group] = (watcher, entries)

        text = f'Running {len(entries)} quest{"s" if len(entries) != 1 else ""} for {format_duration(DEFAULT_SECONDS)}.'
        if skipped:
            text += f' Skipped {", ".join(skipped)}: launch {"it" if len(skipped) == 1 else "them"} on its own.'
        self.toast.emit(f'{text} {note}'.strip(), 'good')

    def _group_closed(self, group) -> None:
        """Stop all in the group window, or its time ran out: end the group."""
        _watcher, entries = self._groups.pop(group, (None, []))
        for entry in entries:
            if entry.ended is None and entry.session.is_running:
                threading.Thread(target=entry.session.stop, daemon=True).start()

    def _group_finished(self, group) -> None:
        """Every game in the group has ended: close its window and report once."""
        if group in self._groups:
            _watcher, entries = self._groups[group]
        else:
            entries = [e for e in self.sessions.entries if e.group is group]
        if any(e.ended is None for e in entries):
            return
        group.stop()
        done = sum(1 for e in entries if e.ended == 'finished')
        total = format_duration(group.seconds)
        if done == len(entries):
            self._notify('Quests finished', f'{done} games ran for the full {total}. Check the quests in Discord.')
        else:
            self._notify('Quests stopped early', f'{done} of {len(entries)} games ran for the full {total}.')

    @Slot(int)
    def stopSession(self, session_id: int) -> None:  # noqa: N802
        for entry in self.sessions.entries:
            if entry.id == session_id:
                threading.Thread(target=entry.session.stop, daemon=True).start()

    def _session_finished(self, entry: SessionEntry) -> None:
        entry.ended = 'finished' if entry.completed else 'stopped'
        self.sessions.changed(entry)
        self.statusChanged.emit()
        QTimer.singleShot(REMOVE_FINISHED_AFTER_MS, lambda: self._remove_entry(entry))
        if entry.group is not None:
            self._group_finished(entry.group)  # one notification for the group
            return
        name = entry.session.game.name
        total = format_duration(entry.session.seconds)
        if entry.ended == 'finished':
            self._notify('Session finished', f'{name} ran for the full {total}. Check the quest in Discord.')
        else:
            self._notify('Session stopped early', f'{name} ran for {format_duration(entry.elapsed)} of {total}.')

    def _remove_entry(self, entry: SessionEntry) -> None:
        self.sessions.remove(entry)
        self.statusChanged.emit()

    def _notify(self, title: str, body: str) -> None:
        if settings.get('notify_on_finish'):
            self.notify.emit(title, body)

    def _tick(self) -> None:
        if self.sessions.entries:
            self.sessions.tick()

    def tray_status(self) -> str:
        running = self.sessions.running
        if not running:
            return 'Nothing running'
        if len(running) == 1:
            entry = running[0]
            left = format_duration(max(0, entry.session.seconds - entry.elapsed))
            return f'{entry.session.game.name}: {left} left'
        return f'{len(running)} sessions running'

    # ------------------------------------------------------------ catalogue

    def _maybe_refresh(self) -> None:
        if self.catalog.is_stale:
            self._start_refresh(silent=True)

    @Slot()
    def refreshCatalog(self) -> None:  # noqa: N802
        self._start_refresh(silent=False)

    def _start_refresh(self, silent: bool) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.statusChanged.emit()

        def work():
            ok = False
            try:
                ok = self.catalog.refresh()
                quests.refresh()   # the optional shared list; failure is fine
            finally:
                self._refreshDone.emit(ok, silent)

        threading.Thread(target=work, daemon=True).start()

    def _on_refresh_done(self, ok: bool, silent: bool) -> None:
        self._refreshing = False
        self._refresh_failed = not ok
        if ok:
            self.catalog.apply_quests()
            self.search(self._query)
            self._reload_quests()
            self.catalogChanged.emit()
        self.statusChanged.emit()
        if not silent:
            if ok:
                self.toast.emit(f'Game list updated. {len(self.catalog.games):,} games.', 'good')
            else:
                self.toast.emit('Could not reach Discord. Using the saved game list.', 'bad')

    # ------------------------------------------------------------ quest detection

    @Slot()
    def detectQuests(self) -> None:  # noqa: N802
        self._start_scan(manual=True)

    def _watch(self) -> None:
        if not self._get_watch() or self._detecting:
            return
        # Read more often while games run, so the progress on the cards keeps up.
        gap = WATCH_RUNNING_GAP if self.sessions.running else WATCH_MIN_GAP
        if time.time() - self._last_auto_scan < gap:
            return
        if discordui.find_quests_window() is None:
            return
        self._start_scan(manual=False)

    def _start_scan(self, manual: bool) -> None:
        if self._detecting:
            return
        self._detecting = True
        if not manual:
            self._last_auto_scan = time.time()
        self.statusChanged.emit()

        def work():
            try:
                result = discordui.scan()
            except Exception as exc:  # noqa: BLE001 - never let the thread die silently
                result = discordui.Scan([], ok=False, reason=f'Could not read Discord: {exc}')
            self._scanDone.emit(result, manual)

        threading.Thread(target=work, daemon=True).start()

    def _apply_scan(self, result: discordui.Scan) -> tuple[list, list]:
        """Save a successful scan and redraw the quest lists."""
        entries, other = discordui.match_quests(result.quests, self.catalog.exact)
        quests.save_detected(entries, other)
        self._badges_changed()
        self.statusChanged.emit()
        return entries, other

    def _on_scan_done(self, result: discordui.Scan, manual: bool) -> None:
        self._detecting = False
        if not result.ok:
            if manual:
                self.toast.emit(result.reason, 'bad')
            self.statusChanged.emit()
            return

        entries, other = self._apply_scan(result)
        if manual:
            found = len(entries)
            text = f'Found {found} quest{"s" if found != 1 else ""} this app can run.'
            if other:
                text += f' {len(other)} more can only be done in Discord.'
            self.toast.emit(text, 'good' if found else 'info')

    # ------------------------------------------------------------ window

    @Slot(int, int, result=QRect)
    def availableGeometry(self, x: int, y: int) -> QRect:  # noqa: N802
        """Work area of the screen under a point, for maximizing a frameless window."""
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    @Slot()
    def closeWindow(self) -> None:  # noqa: N802
        """The window's close button or Alt+F4."""
        if self._get_tray() and not self._quitting:
            self.hideWindowRequested.emit()
            if not settings.get('tray_explained'):
                settings.set_value('tray_explained', True)
                self.notify.emit(
                    'Still running',
                    'Sessions keep running in the background. Use the tray icon '
                    'to open the window or quit.',
                )
            return
        self.quit()

    @Slot()
    def quit(self) -> None:
        running = self.sessions.running
        if running:
            count = len(running)
            self._ask(
                'Sessions still running',
                f'{count} session{"s are" if count != 1 else " is"} still running. '
                'Quitting stops them and cleans up.',
                'Quit', self._shutdown,
            )
            return
        self._shutdown()

    def _shutdown(self) -> None:
        self._quitting = True
        for group in list(self._groups):
            group.stop()
        for entry in self.sessions.running:
            entry.session.stop()
        self.quitRequested.emit()
