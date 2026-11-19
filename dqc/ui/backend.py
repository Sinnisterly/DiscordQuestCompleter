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

import datetime as dt
import itertools
import threading
import time

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .. import __version__, discordui, emulator, journal, orbs, quests, settings, startup, thumbs, updates
from ..appdirs import data_dir
from ..catalog import Catalog, Game
from ..duration import DEFAULT_SECONDS, DurationError, format_duration, parse_duration, quest_seconds
from .models import GameListModel, SessionEntry, SessionModel, ends_label
from .theme_bridge import ThemeBridge

WATCH_INTERVAL_MS = 10_000      # how often to look for the Quests page
WATCH_MIN_GAP = 60              # seconds between automatic scans
WATCH_RUNNING_GAP = 20          # the same while sessions are running
BACKGROUND_GAP = 60 * 60        # background check: at most once an hour
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
    orbsChanged = Signal()            # a new orb balance was recorded
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
    _acceptDone = Signal(object, object)   # job details, fresh Scan
    _updateDone = Signal(object)           # (version, url) or None
    updateChanged = Signal()

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
        self._last_background = 0.0
        self._groups: dict = {}   # GroupWindow -> (watcher, entries)
        self._quitting = False

        self._refreshDone.connect(self._on_refresh_done)
        self._scanDone.connect(self._on_scan_done)
        self._acceptDone.connect(self._on_accept_done)
        self._updateDone.connect(self._on_update_done)
        self._update: tuple[str, str] | None = None

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
        self._clock.timeout.connect(self.orbsChanged.emit)
        self.catalogChanged.connect(self.orbsChanged.emit)  # available orbs change with quests
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
        self._check_updates()

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

    def _get_alerts(self) -> bool:
        return bool(settings.get('quest_alerts', True))

    def _set_alerts(self, value: bool) -> None:
        settings.set_value('quest_alerts', bool(value))
        self.settingsChanged.emit()

    def _get_startup(self) -> bool:
        return startup.is_enabled()

    def _set_startup(self, value: bool) -> None:
        error = startup.set_enabled(bool(value))
        if error:
            self.toast.emit(error, 'bad')
        self.settingsChanged.emit()

    def _orb_summary(self) -> dict:
        data = orbs.summary()
        data['available'] = self._quest_orbs() + self._other_orbs()
        data['updatedText'] = _ago(data['updated']) if data['updated'] else ''
        data['sinceText'] = (
            dt.date.fromtimestamp(data['since']).strftime('%B %d, %Y').replace(' 0', ' ')
            if data['since'] else ''
        )
        return data

    def _get_background(self) -> bool:
        return bool(settings.get('background_check', False))

    def _set_background(self, value: bool) -> None:
        settings.set_value('background_check', bool(value))
        self.settingsChanged.emit()

    def _get_auto_launch(self) -> bool:
        return bool(settings.get('auto_launch', False))

    def _set_auto_launch(self, value: bool) -> None:
        settings.set_value('auto_launch', bool(value))
        self.settingsChanged.emit()

    def _get_check_updates(self) -> bool:
        return bool(settings.get('check_updates', True))

    def _set_check_updates(self, value: bool) -> None:
        settings.set_value('check_updates', bool(value))
        self.settingsChanged.emit()
        if value:
            self._check_updates(force=True)

    def _update_version(self) -> str:
        return self._update[0] if self._update else ''

    def _update_url(self) -> str:
        return self._update[1] if self._update else ''

    backgroundCheck = Property(bool, _get_background, _set_background, notify=settingsChanged)
    autoLaunch = Property(bool, _get_auto_launch, _set_auto_launch, notify=settingsChanged)
    checkUpdates = Property(bool, _get_check_updates, _set_check_updates, notify=settingsChanged)
    updateVersion = Property(str, _update_version, notify=updateChanged)
    updateUrl = Property(str, _update_url, notify=updateChanged)
    alertsEnabled = Property(bool, _get_alerts, _set_alerts, notify=settingsChanged)
    startWithWindows = Property(bool, _get_startup, _set_startup, notify=settingsChanged)
    orbSummary = Property('QVariantMap', _orb_summary, notify=orbsChanged)
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

    @staticmethod
    def _seconds_for(game: Game | None) -> int:
        """The quest's own time plus the sync margin, or the default."""
        return quest_seconds(game.quest_minutes if game else None)

    @Slot(str, str, result='QVariantMap')
    def durationHint(self, text: str, game_id: str = '') -> dict:
        game = self.catalog.by_id(game_id) if game_id else None
        try:
            seconds = parse_duration(text, default=self._seconds_for(game))
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
            seconds = parse_duration(duration, default=self._seconds_for(game))
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
        if (game.quest_progress or 0) >= 100:
            self.toast.emit(f'{game.quest_title or game.name} is already done. Claim it in Discord.', 'info')
            return
        needs_prep = game.wrong_platform or game.quest_accepted is False
        if needs_prep and game.quest_heading and discordui.find_quests_window() is not None:
            # Accept it and set it to Desktop first, then launch, as Launch all does.
            self._launch_quests([game])
            return
        if game.wrong_platform:
            self._ask(
                'Set this quest to Desktop',
                f'{game.quest_title or game.name} is set to {game.quest_platform} in Discord, so running '
                'it on this PC will not count. Open the Quests page in Discord and press Retry, and '
                'the app will switch it to Desktop for you. Or change the dropdown next to '
                'Quest Accepted yourself.',
                'Retry', lambda: self.quickLaunch(game_id), cancel='Close',
            )
            return
        mode = self._default_mode(game, emulator.find_installed(game))
        try:
            plan = emulator.plan_session(game, None, mode=mode)
        except emulator.EmulationError as exc:
            self.toast.emit(str(exc), 'bad')
            return
        self._confirm_and_start(game, plan, self._seconds_for(game))

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
                self._ask('Could not start', str(exc), 'Retry',
                          lambda: self._retry_plan(plan.game, seconds), cancel='Close')
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
        """Quest games with a known path, not running and not done yet."""
        running = {e.session.game.id for e in self.sessions.running}
        return [g for g in self.catalog.quest_games()
                if g.candidates and g.id not in running and (g.quest_progress or 0) < 100]

    @Slot()
    def launchAll(self) -> None:  # noqa: N802
        """Get every quest ready in Discord, then run them all at once.

        Ready means accepted and tracked on Desktop. While Discord's Quests
        page is open, quests not yet accepted are accepted and any quest set
        to another platform is switched to Desktop. Each game runs its own
        stand-in, with its window off-screen, since Discord detects each
        process, and one window counts down for all of them.
        """
        if self._launching_all:
            return
        games = self._launchable()
        if not games:
            self.toast.emit('Nothing to launch. Every quest is running, done or has no known path.', 'info')
            return
        self._launch_quests(games)

    def _launch_quests(self, games: list[Game]) -> None:
        """Get these quests ready in Discord where needed, then run them together."""
        to_accept = {g.quest_heading for g in games if g.quest_accepted is False and g.quest_heading}
        to_fix = {g.quest_heading for g in games if g.wrong_platform and g.quest_heading}
        if not (to_accept or to_fix) or discordui.find_quests_window() is None:
            note = ''
            if to_accept or to_fix:
                note = 'Open the Quests page in Discord to have quests accepted and set to Desktop for you.'
            self._launch_group(games, note)
            return

        self._launching_all = True
        self.statusChanged.emit()

        def work():
            try:
                outcome = discordui.prepare_quests(to_accept, to_fix)
                time.sleep(0.8)
                result = discordui.scan()
            except Exception as exc:  # noqa: BLE001 - report it rather than lose the thread
                outcome, result = {}, discordui.Scan([], ok=False, reason=str(exc))
            self._acceptDone.emit({'accept': to_accept, 'fix': to_fix, 'outcome': outcome,
                                   'ids': [g.id for g in games]}, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_accept_done(self, job: dict, result) -> None:
        self._launching_all = False
        if result.ok:
            self._apply_scan(result, auto=False)
        by_heading = {g.quest_heading: g for g in self.catalog.quest_games() if g.quest_heading}
        accepted = [h for h in job['accept'] if by_heading.get(h) and by_heading[h].quest_accepted]
        fixed = [h for h in (job['accept'] | job['fix'])
                 if by_heading.get(h) and by_heading[h].quest_accepted and not by_heading[h].wrong_platform]
        notes = []
        if accepted:
            notes.append(f'Accepted {len(accepted)} quest{"s" if len(accepted) != 1 else ""} in Discord.')
        switched = [h for h in job['fix'] if h in fixed]
        if switched:
            notes.append(f'Set {len(switched)} quest{"s" if len(switched) != 1 else ""} to Desktop.')
        wanted = set(job['ids'])
        self._launch_group([g for g in self._launchable() if g.id in wanted], ' '.join(notes))

    def _launch_group(self, games: list[Game], note: str = '') -> None:
        plans, skipped, not_ready = [], [], []
        for game in games:
            # Running a game only counts for a quest that is accepted and
            # tracked on Desktop, so the others are named instead of run.
            if game.wrong_platform:
                not_ready.append(f'{game.quest_title or game.name} is set to {game.quest_platform}')
                continue
            if game.quest_accepted is False:
                not_ready.append(f'{game.quest_title or game.name} is not accepted')
                continue
            mode = self._default_mode(game, emulator.find_installed(game))
            # Games that need a confirmation are left for a single launch.
            if (not game.detectable or game.requires) and mode != emulator.INSTALLED:
                skipped.append(game.name)
                continue
            try:
                plans.append((emulator.plan_session(game, None, mode=mode), self._seconds_for(game)))
            except emulator.EmulationError:
                skipped.append(game.name)

        if not_ready:
            self._message(
                'Some quests were not launched',
                'Running these on this PC would not count yet:\n\n'
                + '\n'.join(f'- {line}' for line in not_ready)
                + '\n\nIn Discord, accept the quest and set the dropdown on its card to Desktop, '
                'then launch it again.',
            )
        if not plans:
            self.toast.emit(f'No quests could be launched. {note}'.strip(), 'bad')
            return
        if len(plans) == 1:
            plan, seconds = plans[0]
            if self._start(plan, seconds) and note:
                self.toast.emit(note, 'good')
            return

        # Each game runs for its own quest's time. The shared countdown runs
        # to the longest one, and each game stops on its own when its time is up.
        longest = max(seconds for _plan, seconds in plans)
        group = emulator.GroupWindow([p.game.quest_title or p.game.name for p, _s in plans],
                                     longest, self.theme.colors)
        entries = [e for e in (self._start(p, seconds, group) for p, seconds in plans) if e]
        if not entries:
            self.toast.emit(f'No quests could be launched. {note}'.strip(), 'bad')
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

        text = f'Running {len(entries)} quest{"s" if len(entries) != 1 else ""}, up to {format_duration(longest)}.'
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

    def _retry_plan(self, game: Game, seconds: int) -> None:
        """Start a game again with a fresh plan and the same run time."""
        mode = self._default_mode(game, emulator.find_installed(game))
        try:
            plan = emulator.plan_session(game, None, mode=mode)
        except emulator.EmulationError as exc:
            self.toast.emit(str(exc), 'bad')
            return
        self._start(plan, seconds)

    @Slot(int)
    def retrySession(self, session_id: int) -> None:  # noqa: N802
        for entry in list(self.sessions.entries):
            if entry.id == session_id and entry.ended is not None:
                self._remove_entry(entry)
                game = self.catalog.by_id(entry.session.game.id) or entry.session.game
                if game.wrong_platform or game.quest_accepted is False:
                    self.quickLaunch(game.id)   # fixes the quest in Discord first
                else:
                    self._retry_plan(game, entry.session.seconds)

    @Slot(int)
    def dismissSession(self, session_id: int) -> None:  # noqa: N802
        for entry in list(self.sessions.entries):
            if entry.id == session_id and entry.ended is not None:
                self._remove_entry(entry)

    @Slot(int)
    def stopSession(self, session_id: int) -> None:  # noqa: N802
        for entry in self.sessions.entries:
            if entry.id == session_id:
                threading.Thread(target=entry.session.stop, daemon=True).start()

    def _session_finished(self, entry: SessionEntry) -> None:
        entry.ended = 'finished' if entry.completed or entry.discord_done else 'stopped'
        self.sessions.changed(entry)
        self.statusChanged.emit()
        if entry.ended == 'finished':
            QTimer.singleShot(REMOVE_FINISHED_AFTER_MS, lambda: self._remove_entry(entry))
        # A run that stopped early stays on the Sessions page with Retry and
        # Dismiss, so it is not lost.
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

    def _check_updates(self, force: bool = False) -> None:
        """Look for a newer release on GitHub, at most twice a day."""
        if not self._get_check_updates():
            return
        last = settings.get('update_checked') or 0
        if not force and isinstance(last, (int, float)) and time.time() - last < 12 * 3600:
            return
        settings.set_value('update_checked', int(time.time()))
        threading.Thread(target=lambda: self._updateDone.emit(updates.latest()), daemon=True).start()

    def _on_update_done(self, found) -> None:
        if not found or not updates.is_newer(found[0]):
            return
        self._update = found
        self.updateChanged.emit()
        if quests.remind_once(f'update:{found[0]}'):
            self.notify.emit('Update available',
                             f'Discord Quest Completer {found[0]} is out. Open Settings to download it.')

    def _maybe_refresh(self) -> None:
        # Runs hourly: also the moment to remind about quests ending today,
        # using what was last read, even if Discord's page is closed.
        self._remind_ending()
        self._check_updates()
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
        self._maybe_background()
        if not self._get_watch() or self._detecting:
            return
        # Read more often while games run, so the progress on the cards keeps up.
        gap = WATCH_RUNNING_GAP if self.sessions.running else WATCH_MIN_GAP
        if time.time() - self._last_auto_scan < gap:
            return
        if discordui.find_quests_window() is None:
            return
        self._start_scan(manual=False)

    def _maybe_background(self) -> None:
        """Read the Quests page while it is closed, at most once an hour.

        Only while the user is away: Discord has to come to the front for
        about a second to draw the page. See discordui.background_scan.
        """
        if not self._get_background() or self._detecting or self._launching_all:
            return
        last = max(quests.detected_at(), self._last_background)
        if time.time() - last < BACKGROUND_GAP:
            return
        if discordui.background_blocker():
            return
        self._last_background = time.time()
        self._detecting = True
        self.statusChanged.emit()

        def work():
            try:
                result = discordui.background_scan()
            except Exception as exc:  # noqa: BLE001 - never let the thread die silently
                result = discordui.Scan([], ok=False, reason=f'Could not read Discord: {exc}')
            self._scanDone.emit(result, False)

        threading.Thread(target=work, daemon=True).start()

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

    def _apply_scan(self, result: discordui.Scan, auto: bool = True) -> tuple[list, list]:
        """Save a successful scan and redraw the quest lists.

        auto is False when the scan is part of a launch already under way,
        so new quests found then are not launched a second time.
        """
        entries, other = discordui.match_quests(result.quests, self.catalog.exact)
        quests.save_detected(entries, other)
        if result.balance is not None and orbs.record(result.balance):
            self.orbsChanged.emit()
        fresh = self._alert_new(entries, other)
        self._badges_changed()
        self._alert_ready()
        self._remind_ending()
        self._stop_finished()
        if auto and fresh and self._get_auto_launch():
            # After this scan has been fully applied, start the new ones.
            names = {e['name'] for e in fresh}
            QTimer.singleShot(0, lambda: self._auto_launch(names))
        self.statusChanged.emit()
        return entries, other

    def _auto_launch(self, names: set[str]) -> None:
        games = [g for g in self._launchable() if g.name in names]
        if not games or self._launching_all:
            return
        self.notify.emit(
            'Starting new quests',
            f'Auto-launch is starting {len(games)} new quest{"s" if len(games) != 1 else ""}: '
            + ', '.join(g.quest_title or g.name for g in games[:4]) + '.',
        )
        self._launch_quests(games)

    def _alerts_on(self) -> bool:
        return bool(settings.get('quest_alerts', True))

    def _alert_ready(self) -> None:
        """Say once when a quest reaches 100% and can be claimed."""
        for game in self.catalog.quest_games():
            if (game.quest_progress or 0) < 100 or not game.quest_heading:
                continue
            if quests.remind_once(f'ready:{game.quest_heading}') and self._alerts_on():
                reward = f'{game.quest_orbs:,} orbs' if game.quest_orbs else (game.quest_reward or 'your reward')
                self.notify.emit('Quest ready to claim',
                                 f'{game.quest_title or game.name} is done. Claim {reward} in Discord.')

    def _remind_ending(self) -> None:
        """Say once when an unfinished quest ends today."""
        today = dt.date.today().isoformat()
        pending = [
            (g.quest_heading, g.quest_title or g.name, g.quest_orbs)
            for g in self.catalog.quest_games()
            if g.quest_ends == today and (g.quest_progress or 0) < 100 and g.quest_heading
        ] + [
            (q.get('heading'), q['title'], q.get('orbs'))
            for q in quests.load_other()
            if q.get('until') == today and q.get('heading')
        ]
        fresh = [(name, orb) for heading, name, orb in pending
                 if quests.remind_once(f'ending:{heading}:{today}')]
        if not fresh or not self._alerts_on():
            return
        if len(fresh) == 1:
            name, orb = fresh[0]
            extra = f' It is worth {orb:,} orbs.' if orb else ''
            self.notify.emit('Quest ends today', f'{name} ends today and is not done yet.{extra}')
        else:
            names = ', '.join(name for name, _orb in fresh[:4])
            self.notify.emit(f'{len(fresh)} quests end today', f'Not done yet: {names}.')

    def _stop_finished(self) -> None:
        """Stop any game whose quest Discord already shows as done."""
        for entry in self.sessions.running:
            game = self.catalog.by_id(entry.session.game.id)
            if game is not None and (game.quest_progress or 0) >= 100 and not entry.discord_done:
                entry.discord_done = True
                threading.Thread(target=entry.session.stop, daemon=True).start()

    def _alert_new(self, entries: list[dict], other: list[dict]) -> list[dict]:
        """Tell the user about quests that were not on the page before.

        Returns the new quests this app can run, for auto-launch, whether or
        not alerts are turned on.
        """
        def key(q):
            return q.get('heading') or q.get('title') or q.get('name')

        found = [*entries, *other]
        fresh = set(quests.new_quests([key(q) for q in found]))
        runnable = [q for q in entries if key(q) in fresh]
        if not fresh or not self._alerts_on():
            return runnable
        new = [q for q in found if key(q) in fresh]
        names = [q.get('title') or q.get('name') for q in new]
        total = sum(q.get('orbs') or 0 for q in new)
        if len(new) == 1:
            quest = new[0]
            reward = f'{quest["orbs"]:,} orbs' if quest.get('orbs') else (quest.get('reward') or 'a reward')
            body = f'{names[0]}: {reward}.'
            if quest.get('until'):
                ends = dt.date.fromisoformat(quest['until'])
                body += f' Ends {ends.month}/{ends.day}.'
            self.notify.emit('New Discord quest', body)
        else:
            body = ', '.join(names[:4]) + (f' and {len(names) - 4} more' if len(names) > 4 else '') + '.'
            if total:
                body += f' {total:,} orbs in all.'
            self.notify.emit(f'{len(new)} new Discord quests', body)
        self.toast.emit(f'New quest{"s" if len(new) != 1 else ""}: {", ".join(names[:4])}', 'info')
        return runnable

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
