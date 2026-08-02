"""Main application window."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import emulator, journal, quests, settings, thumbs, winchrome
from .appdirs import bundled
from .catalog import Game, get_catalog
from .duration import DurationError, format_duration, parse_duration
from .theme import ACCENT, BAD, BG, GOOD, MUTED, STYLESHEET, WARN

CAPSULE_W, CAPSULE_H = 154, 58


# ------------------------------------------------------------ async loading

class _Signals(QObject):
    done = Signal(str, object)


class _IconJob(QRunnable):
    """Downloads the square icon the stub window uses for the game."""

    def __init__(self, game: Game):
        super().__init__()
        self.game = game

    def run(self) -> None:
        thumbs.ensure_icon(self.game)


class _ThumbJob(QRunnable):
    def __init__(self, game: Game, large: bool, signals: _Signals):
        super().__init__()
        self.game = game
        self.large = large
        self.signals = signals

    def run(self) -> None:
        data = thumbs.fetch_for(self.game, large=self.large)
        key = f'{self.game.id}:{"L" if self.large else "S"}'
        try:
            self.signals.done.emit(key, data)
        except RuntimeError:
            pass  # window closed while this download was still in flight


class ThumbLoader(QObject):
    """Fetches artwork off the UI thread and hands back pixmaps."""

    ready = Signal(str, QPixmap)

    def __init__(self):
        super().__init__()
        # Hero art is requested one image at a time in response to a click, so
        # it gets its own pool rather than queueing behind a list of row art.
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(6)
        self._hero_pool = QThreadPool()
        self._hero_pool.setMaxThreadCount(2)

        self._cache: dict[str, QPixmap] = {}
        self._pending: set[str] = set()
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)

    @staticmethod
    def key_for(game: Game, large: bool) -> str:
        return f'{game.id}:{"L" if large else "S"}'

    def cached(self, game: Game, large: bool = False) -> QPixmap | None:
        return self._cache.get(self.key_for(game, large))

    def request(self, game: Game, large: bool = False) -> QPixmap | None:
        key = self.key_for(game, large)
        if key in self._cache:
            return self._cache[key]
        if key not in self._pending:
            self._pending.add(key)
            pool = self._hero_pool if large else self._pool
            pool.start(_ThumbJob(game, large, self._signals))
        return None

    def prefetch_icon(self, game: Game) -> None:
        """Warm the icon cache so a launch can use it straight away."""
        if thumbs.icon_url(game) and thumbs.icon_path(game) is None:
            self._hero_pool.start(_IconJob(game))

    def shutdown(self) -> None:
        """Drop queued downloads and let running ones finish before teardown."""
        for pool in (self._pool, self._hero_pool):
            pool.clear()
            pool.waitForDone(2000)

    def _on_done(self, key: str, data) -> None:
        self._pending.discard(key)
        if not data:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self._cache[key] = pixmap
            self.ready.emit(key, pixmap)


class SessionWatcher(QObject):
    """Bridges a blocking Session.wait() into a Qt signal."""

    finished = Signal(object)

    def __init__(self, session: emulator.Session):
        super().__init__()
        self.session = session
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self) -> None:
        self.session.wait()
        self.finished.emit(self.session)


# ----------------------------------------------------------------- widgets

class GameRow(QWidget):
    """One search result: capsule art, name, and provenance."""

    def __init__(self, game: Game, loader: ThumbLoader):
        super().__init__()
        self.game = game
        self.key = f'{game.id}:S'

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 10, 7)
        layout.setSpacing(12)

        self.art = QLabel()
        self.art.setFixedSize(CAPSULE_W, CAPSULE_H)
        self.art.setStyleSheet(
            f'background: #232733; border-radius: 6px; color: {MUTED}; font-size: 11px;'
        )
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setText('...')
        layout.addWidget(self.art)

        text = QVBoxLayout()
        text.setSpacing(3)
        name = QLabel(game.name)
        name.setStyleSheet('font-size: 14px; font-weight: 600;')
        name.setWordWrap(True)
        text.addWidget(name)

        path = ElidedLabel(game.primary or 'no known path')
        path.setProperty('role', 'mono')
        path.setStyleSheet(f'color: {MUTED}; font-size: 11px;')
        text.addWidget(path)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        if game.has_quest:
            badges.addWidget(_badge('QUEST LIVE', WARN))
        if not game.detectable:
            badges.addWidget(_badge('NEEDS STEAM INSTALL', WARN))
        elif game.requires:
            badges.addWidget(_badge('NEEDS EXTRA STEP', WARN))
        elif game.is_verified:
            badges.addWidget(_badge('COMMUNITY VERIFIED', GOOD))
        elif game.exes:
            badges.addWidget(_badge('FROM DISCORD', ACCENT))
        else:
            badges.addWidget(_badge('LAUNCHER ONLY', WARN))
        if len(game.candidates) > 1:
            badges.addWidget(_badge(f'{len(game.candidates)} PATHS', MUTED))
        badges.addStretch(1)
        text.addLayout(badges)

        layout.addLayout(text, 1)

        pixmap = loader.request(game, large=False)
        if pixmap is not None:
            self.set_art(pixmap)
        loader.ready.connect(self._maybe_set)

    def _maybe_set(self, key: str, pixmap: QPixmap) -> None:
        if key == self.key:
            self.set_art(pixmap)

    def set_art(self, pixmap: QPixmap) -> None:
        self.art.setPixmap(pixmap.scaled(
            CAPSULE_W, CAPSULE_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
        ))
        self.art.setText('')


class ActiveSession(QFrame):
    """Live progress for one running emulation."""

    stop_requested = Signal(object)

    def __init__(self, session: emulator.Session):
        super().__init__()
        self.session = session
        self.started = time.monotonic()
        self.setProperty('role', 'card')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        name = QLabel(session.game.name)
        name.setStyleSheet('font-weight: 600; font-size: 14px;')
        head.addWidget(name)
        head.addStretch(1)
        self.remaining = QLabel()
        self.remaining.setStyleSheet(f'color: {MUTED};')
        head.addWidget(self.remaining)
        stop = QPushButton('Stop')
        stop.setProperty('role', 'ghost')
        stop.setFixedWidth(70)
        stop.clicked.connect(lambda: self.stop_requested.emit(self.session))
        head.addWidget(stop)
        layout.addLayout(head)

        self.bar = QProgressBar()
        self.bar.setMaximum(session.seconds)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

        path = ElidedLabel(str(session.plan.exe_path))
        path.setProperty('role', 'mono')
        path.setStyleSheet(f'color: {MUTED}; font-size: 11px;')
        layout.addWidget(path)

        self.tick()

    def tick(self) -> None:
        elapsed = min(self.session.seconds, time.monotonic() - self.started)
        self.bar.setValue(int(elapsed))
        left = max(0, self.session.seconds - elapsed)
        self.remaining.setText(f'{format_duration(left)} left')

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def completed(self) -> bool:
        """True when the session ran its full duration.

        Measured from elapsed time rather than a flag, so closing the stub
        window counts as stopping early just as the Stop button does.
        """
        return self.elapsed >= self.session.seconds - 2

    def mark_finished(self) -> None:
        self.bar.setValue(self.session.seconds)
        self.remaining.setText('finished' if self.completed else 'stopped early')


class HeroLabel(QLabel):
    """Shows the game artwork whole, without cropping.

    Sources differ in shape: Steam headers are 460x215, Discord icons are
    square. Scaling to fill would crop a header top and bottom and reduce an
    icon to a middle strip, so the image is fitted and centred instead. The
    source pixmap is kept so resizing rescales from the original.
    """

    def __init__(self):
        super().__init__()
        self._source = QPixmap()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(112)

    def set_source(self, pixmap: QPixmap) -> None:
        self._source = pixmap
        self._rescale()

    def clear_source(self, message: str = '') -> None:
        self._source = QPixmap()
        super().setPixmap(QPixmap())
        self.setText(message)

    def has_source(self) -> bool:
        return not self._source.isNull()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._source.isNull():
            return
        target = self.size()
        if target.width() <= 0 or target.height() <= 0:
            return
        super().setPixmap(self._source.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        ))
        self.setText('')


class ElidedLabel(QLabel):
    """A label that truncates with an ellipsis instead of forcing the row wider.

    Without this the long executable paths widen every row and the list grows
    a horizontal scrollbar.
    """

    def __init__(self, text: str = ''):
        super().__init__()
        self._full = text
        self.setToolTip(text)
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full = text
        self.setToolTip(text)
        super().setText(text)
        self._elide()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        metrics = QFontMetrics(self.font())
        super().setText(metrics.elidedText(self._full, Qt.ElideMiddle, max(0, self.width())))


def _badge(text: str, colour: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f'color: {colour}; border: 1px solid {colour}; border-radius: 4px;'
        f'padding: 1px 5px; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;'
    )
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
    return label


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setProperty('role', 'section')
    return label


# ------------------------------------------------------------------ window

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Discord Quest Completer')
        self.resize(1080, 720)
        self.setMinimumSize(920, 600)

        self.catalog = get_catalog()
        self.loader = ThumbLoader()
        self.loader.ready.connect(self._art_arrived)
        self.selected: Game | None = None
        self.rows: list[ActiveSession] = []
        self.settings = settings.load()
        self.tray: QSystemTrayIcon | None = None
        self._quitting = False

        self._build()
        self._build_tray()
        self._restore_notes()
        self._search('')
        self._maybe_refresh()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)

    # -- layout ----------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel('Discord Quest Completer')
        title.setProperty('role', 'title')
        header.addWidget(title)
        header.addStretch(1)
        self.catalog_label = QLabel()
        self.catalog_label.setProperty('role', 'subtitle')
        header.addWidget(self.catalog_label)
        refresh = QPushButton('Refresh catalogue')
        refresh.setProperty('role', 'ghost')
        refresh.clicked.connect(self._refresh_clicked)
        self.refresh_button = refresh
        header.addWidget(refresh)
        outer.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addLayout(self._build_left(), 5)
        body.addLayout(self._build_right(), 4)
        outer.addLayout(body, 1)

        self._update_catalog_label()

    def _build_left(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Search games. Try "where winds", "zzz", "valorant"')
        self.search.textChanged.connect(self._search)
        column.addWidget(self.search)

        self.count_label = QLabel()
        self.count_label.setProperty('role', 'subtitle')
        column.addWidget(self.count_label)

        self.results = QListWidget()
        self.results.setSpacing(0)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.results.currentItemChanged.connect(self._selection_changed)
        column.addWidget(self.results, 1)
        return column

    def _build_right(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        self.detail = QFrame()
        self.detail.setProperty('role', 'card')
        # Keep the card at its natural height. Left as Preferred it gets
        # compressed when a session row appears below it, which shifts every
        # child upward mid-paint and leaves the panel visibly torn.
        self.detail.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(10)

        self.hero = HeroLabel()
        self.hero.setFixedHeight(124)
        self.hero.setStyleSheet(
            f'background: #232733; border-radius: 8px; color: {MUTED};'
        )
        detail_layout.addWidget(self.hero)

        self.detail_name = QLabel('Select a game')
        self.detail_name.setStyleSheet('font-size: 17px; font-weight: 600;')
        self.detail_name.setWordWrap(True)
        detail_layout.addWidget(self.detail_name)

        self.detail_note = QLabel()
        self.detail_note.setProperty('role', 'subtitle')
        self.detail_note.setWordWrap(True)
        self.detail_note.hide()
        detail_layout.addWidget(self.detail_note)

        detail_layout.addWidget(_section('Executable path'))
        self.path_box = QComboBox()
        self.path_box.currentIndexChanged.connect(self._path_changed)
        detail_layout.addWidget(self.path_box)

        # Elided rather than wrapped: a wrapped path is height-for-width, so
        # its height changes with the panel width and the card cannot settle.
        self.resolved = ElidedLabel()
        self.resolved.setProperty('role', 'mono')
        detail_layout.addWidget(self.resolved)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        duration_col = QVBoxLayout()
        duration_col.setSpacing(5)
        duration_col.addWidget(_section('Duration'))
        self.duration = QLineEdit()
        self.duration.setPlaceholderText('15m / 900 / 10 * 60')
        self.duration.textChanged.connect(self._duration_changed)
        duration_col.addWidget(self.duration)
        controls.addLayout(duration_col, 1)

        placement_col = QVBoxLayout()
        placement_col.setSpacing(5)
        placement_col.addWidget(_section('Placement'))
        self.placement = QComboBox()
        self.placement.addItem('Sandbox (recommended)', emulator.SANDBOX)
        self.placement.addItem('Inside Steam library', emulator.STEAM)
        self.placement.addItem('Replace installed copy', emulator.INSTALLED)
        self.placement.currentIndexChanged.connect(self._path_changed)
        placement_col.addWidget(self.placement)
        controls.addLayout(placement_col, 1)

        detail_layout.addLayout(controls)

        self.duration_hint = QLabel()
        self.duration_hint.setProperty('role', 'subtitle')
        detail_layout.addWidget(self.duration_hint)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.launch = QPushButton('Launch')
        self.launch.setProperty('role', 'primary')
        self.launch.setEnabled(False)
        self.launch.clicked.connect(self._launch)
        actions.addWidget(self.launch, 1)

        self.quest_button = QPushButton('Mark quest running')
        self.quest_button.setProperty('role', 'ghost')
        self.quest_button.setCheckable(True)
        self.quest_button.setToolTip(
            'Discord does not expose your quest list without an account token, '
            'which this app never asks for. Mark quests yourself and they are '
            'badged and sorted to the top.'
        )
        self.quest_button.clicked.connect(self._toggle_quest)
        actions.addWidget(self.quest_button)

        detail_layout.addLayout(actions)

        column.addWidget(self.detail)

        column.addWidget(_section('Active sessions'))

        # The session list scrolls inside whatever space is left over. Without
        # this it grows without limit and squeezes the card above it, which
        # repositions that card's children while it is being painted.
        holder = QWidget()
        self.sessions_box = QVBoxLayout(holder)
        self.sessions_box.setContentsMargins(0, 0, 0, 0)
        self.sessions_box.setSpacing(8)
        self.sessions_box.addStretch(1)

        self.sessions_scroll = QScrollArea()
        self.sessions_scroll.setWidget(holder)
        self.sessions_scroll.setWidgetResizable(True)
        self.sessions_scroll.setFrameShape(QFrame.NoFrame)
        self.sessions_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sessions_scroll.setMinimumHeight(80)
        column.addWidget(self.sessions_scroll, 1)

        self.idle_label = QLabel('Nothing running.')
        self.idle_label.setProperty('role', 'subtitle')
        self.sessions_box.insertWidget(0, self.idle_label)

        divider = QFrame()
        divider.setProperty('role', 'divider')
        column.addWidget(divider)

        self.tray_check = QCheckBox('Keep running in the tray when closed')
        self.tray_check.setChecked(bool(self.settings.get('minimise_to_tray', True)))
        self.tray_check.toggled.connect(self._setting_changed)
        column.addWidget(self.tray_check)

        self.notify_check = QCheckBox('Notify me when a session ends')
        self.notify_check.setChecked(bool(self.settings.get('notify_on_finish', True)))
        self.notify_check.toggled.connect(self._setting_changed)
        column.addWidget(self.notify_check)

        self.tray_note = QLabel()
        self.tray_note.setProperty('role', 'subtitle')
        self.tray_note.setWordWrap(True)
        column.addWidget(self.tray_note)
        self._duration_changed('')
        return column

    # -- tray ------------------------------------------------------------

    def _build_tray(self) -> None:
        """Set up the tray icon, if the desktop provides one."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_note.setText(
                'No system tray available, so the window cannot be hidden.'
            )
            self.tray_check.setEnabled(False)
            return

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip('Discord Quest Completer')

        menu = QMenu()
        self.tray_status = QAction('Nothing running', menu)
        self.tray_status.setEnabled(False)
        menu.addAction(self.tray_status)
        menu.addSeparator()

        show = QAction('Show window', menu)
        show.triggered.connect(self._restore)
        menu.addAction(show)

        quit_action = QAction('Quit', menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._restore)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore()

    def _restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self._quitting = True
        self.close()

    def _notify(self, title: str, body: str) -> None:
        if self.tray is not None and self.settings.get('notify_on_finish', True):
            self.tray.showMessage(title, body, app_icon(), 8000)

    def _hides_to_tray(self) -> bool:
        return self.tray is not None and bool(self.settings.get('minimise_to_tray', True))

    def _setting_changed(self) -> None:
        self.settings['minimise_to_tray'] = self.tray_check.isChecked()
        self.settings['notify_on_finish'] = self.notify_check.isChecked()
        settings.set_value('minimise_to_tray', self.tray_check.isChecked())
        settings.set_value('notify_on_finish', self.notify_check.isChecked())

    def _update_tray_status(self) -> None:
        if self.tray is None:
            return
        running = [r for r in self.rows if r.session.is_running]
        if not running:
            text = 'Nothing running'
        elif len(running) == 1:
            row = running[0]
            left = format_duration(max(0, row.session.seconds - row.elapsed))
            text = f'{row.session.game.name}: {left} left'
        else:
            text = f'{len(running)} sessions running'
        self.tray_status.setText(text)
        self.tray.setToolTip(f'Discord Quest Completer\n{text}')

    # -- catalogue -------------------------------------------------------

    def _update_catalog_label(self) -> None:
        count = len(self.catalog.games)
        if self.catalog.generated:
            age = max(0, time.time() - self.catalog.generated)
            days = age / 86400
            when = 'today' if days < 1 else f'{int(days)}d ago'
        else:
            when = 'unknown'
        self.catalog_label.setText(f'{count:,} games, updated {when}')

    def _maybe_refresh(self) -> None:
        if self.catalog.is_stale:
            self._refresh_clicked(silent=True)

    def _refresh_clicked(self, silent: bool = False) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText('Refreshing')

        def work():
            ok = self.catalog.refresh()
            QTimer.singleShot(0, lambda: self._refresh_done(ok, silent))

        threading.Thread(target=work, daemon=True).start()

    def _refresh_done(self, ok: bool, silent: bool) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText('Refresh catalogue')
        self._update_catalog_label()
        self._search(self.search.text())
        if not ok and not silent:
            QMessageBox.warning(
                self, 'Refresh failed',
                'Could not reach Discord. The bundled catalogue is still in use.',
            )

    def _restore_notes(self) -> None:
        notes = journal.recover()
        if notes:
            QMessageBox.information(
                self, 'Recovered from a previous run',
                'Leftovers from an interrupted session were cleaned up:\n\n'
                + '\n'.join(f'- {n}' for n in notes),
            )

    # -- search ----------------------------------------------------------

    def _search(self, text: str) -> None:
        self.results.clear()
        games = self.catalog.search(text, limit=60)

        if not text.strip():
            self.count_label.setText(
                f'{len(games)} community-verified games. '
                f'Start typing to search all {len(self.catalog.games):,}.'
            )
        else:
            self.count_label.setText(f'{len(games)} result{"s" if len(games) != 1 else ""}')

        for game in games:
            item = QListWidgetItem()
            row = GameRow(game, self.loader)
            item.setSizeHint(row.sizeHint())
            item.setData(Qt.UserRole, game.id)
            self.results.addItem(item)
            self.results.setItemWidget(item, row)

        if games:
            self.results.setCurrentRow(0)
        else:
            self._show_game(None)

    def _selection_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            self._show_game(None)
            return
        row = self.results.itemWidget(current)
        self._show_game(row.game if isinstance(row, GameRow) else None)

    # -- detail ----------------------------------------------------------

    def _show_game(self, game: Game | None) -> None:
        self.selected = game
        self.path_box.blockSignals(True)
        self.path_box.clear()

        if game is None:
            self.detail_name.setText('Select a game')
            self.detail_note.hide()
            self.hero.setPixmap(QPixmap())
            self.hero.setText('')
            self.resolved.setText('')
            self.launch.setEnabled(False)
            self.path_box.blockSignals(False)
            return

        self.detail_name.setText(game.name)

        note_parts = []
        warn = False
        if not game.detectable:
            note_parts.append(
                'Discord publishes no executable for this app. It still gets '
                'detected, but in practice only when the game is installed '
                'through Steam and Replace installed copy is used. A sandbox '
                'is unlikely to register.'
            )
            warn = True
        if game.requires:
            note_parts.append(game.requires)
            warn = True
        if game.requires_url:
            note_parts.append(game.requires_url)
        if game.has_quest and game.quest_reward:
            note_parts.append(f'Quest running: {game.quest_reward}')
        if game.note:
            note_parts.append(game.note)
        if game.is_template:
            note_parts.append('A unique folder id is generated for each launch.')

        if note_parts:
            self.detail_note.setText(' '.join(note_parts))
            self.detail_note.setStyleSheet(f'color: {BAD};' if warn else '')
            self.detail_note.show()
        else:
            self.detail_note.hide()

        # Show the row capsule upscaled straight away if we already have it,
        # so there is never an empty panel while the larger header downloads.
        self.loader.prefetch_icon(game)

        # Replacing a real install is the only thing that works for titles
        # Discord cannot match by process, so offer it when one is present and
        # pick it automatically when nothing else can succeed.
        install = emulator.find_installed(game)
        index = self.placement.findData(emulator.INSTALLED)
        if index >= 0:
            label = (
                f'Replace installed copy ({install["installdir"]})'
                if install else 'Replace installed copy (none found)'
            )
            self.placement.setItemText(index, label)
            self.placement.model().item(index).setEnabled(install is not None)
        if install is not None and not game.detectable:
            self.placement.setCurrentIndex(index)
        elif self.placement.currentData() == emulator.INSTALLED and install is None:
            self.placement.setCurrentIndex(0)
        self.quest_button.setChecked(game.has_quest)
        self.quest_button.setText(
            'Quest running' if game.has_quest else 'Mark quest running'
        )

        placeholder = self.loader.cached(game, large=False)
        pixmap = self.loader.request(game, large=True)
        if pixmap is not None:
            self._set_hero(pixmap)
        elif placeholder is not None:
            self._set_hero(placeholder)
        else:
            self.hero.clear_source('loading artwork')

        for path in game.candidates:
            label = path
            if path in game.verified:
                label = f'[verified]  {path}'
            self.path_box.addItem(label, path)
        self.path_box.blockSignals(False)

        self.launch.setEnabled(bool(game.candidates))
        self._path_changed()

    def _art_arrived(self, key: str, pixmap: QPixmap) -> None:
        """Swap in artwork that finished downloading for the current selection."""
        game = self.selected
        if game is None:
            return
        if key == ThumbLoader.key_for(game, large=True):
            self._set_hero(pixmap)
        elif key == ThumbLoader.key_for(game, large=False) and not self.hero.has_source():
            self._set_hero(pixmap)  # capsule arrived first; better than nothing

    def _set_hero(self, pixmap: QPixmap) -> None:
        self.hero.set_source(pixmap)

    def _path_changed(self, _index: int = 0) -> None:
        game = self.selected
        if game is None or not game.candidates:
            self.resolved.setText('')
            return
        chosen = self.path_box.currentData()
        try:
            plan = emulator.plan_session(game, chosen, mode=self.placement.currentData())
        except emulator.EmulationError as exc:
            self.resolved.setText(str(exc))
            self.resolved.setStyleSheet(f'color: {BAD};')
            self.launch.setEnabled(False)
            return
        self.resolved.setText(str(plan.exe_path))
        self.resolved.setStyleSheet(f'color: {MUTED};')
        self.launch.setEnabled(True)

    def _duration_changed(self, text: str) -> None:
        try:
            seconds = parse_duration(text)
        except DurationError as exc:
            self.duration_hint.setText(str(exc))
            self.duration_hint.setStyleSheet(f'color: {BAD};')
            return
        default = ' (default)' if not text.strip() else ''
        self.duration_hint.setText(f'Runs for {format_duration(seconds)}{default}')
        self.duration_hint.setStyleSheet(f'color: {MUTED};')

    # -- launching -------------------------------------------------------

    def _launch(self) -> None:
        game = self.selected
        if game is None:
            return
        try:
            seconds = parse_duration(self.duration.text())
        except DurationError as exc:
            QMessageBox.warning(self, 'Invalid duration', str(exc))
            return

        try:
            plan = emulator.plan_session(
                game, self.path_box.currentData(), mode=self.placement.currentData(),
            )
        except emulator.EmulationError as exc:
            QMessageBox.warning(self, 'Cannot launch', str(exc))
            return

        # Warn before the user spends the full duration finding out. Replacing
        # a real install is the arrangement these titles are known to accept,
        # so there is nothing to warn about in that case.
        risky = (not game.detectable or game.requires) and plan.mode != emulator.INSTALLED
        if risky:
            reasons = []
            if not game.detectable:
                reasons.append(
                    'Discord publishes no executable for this app. Titles like '
                    'this normally register only when the game is installed '
                    'through Steam and you pick Replace installed copy.'
                )
            if game.requires:
                reasons.append(game.requires)
            if game.requires_url:
                reasons.append(game.requires_url)

            confirm = QMessageBox.question(
                self, 'This one may not register',
                '\n\n'.join(reasons) + '\n\nStart anyway?',
            )
            if confirm != QMessageBox.Yes:
                return

        if plan.warning:
            confirm = QMessageBox.question(
                self, 'Write inside your Steam library?',
                f'{plan.warning}\n\n{plan.exe_path}\n\n'
                'Only needed for games that check for Steam-created folders. '
                'Continue?',
            )
            if confirm != QMessageBox.Yes:
                return

        session = emulator.Session(plan, seconds, icon=thumbs.icon_path(game))
        try:
            session.start()
        except emulator.EmulationError as exc:
            QMessageBox.critical(self, 'Launch failed', str(exc))
            return

        row = ActiveSession(session)
        row.stop_requested.connect(self._stop_session)
        self.idle_label.hide()
        # Before the trailing stretch, so rows stack from the top.
        self.sessions_box.insertWidget(self.sessions_box.count() - 1, row)
        self.rows.append(row)

        watcher = SessionWatcher(session)
        watcher.finished.connect(self._session_finished)
        row.watcher = watcher  # keep a reference alive

    def _toggle_quest(self) -> None:
        game = self.selected
        if game is None:
            self.quest_button.setChecked(False)
            return

        active = self.quest_button.isChecked()
        quests.local_set(game.name, active)
        game.has_quest = active
        game.quest_reward = 'marked by you' if active else None
        self.quest_button.setText('Quest running' if active else 'Mark quest running')

        # Redraw the list so the badge and ordering follow the change.
        current = game.id
        self._search(self.search.text())
        for row in range(self.results.count()):
            if self.results.item(row).data(Qt.UserRole) == current:
                self.results.setCurrentRow(row)
                break

    def _stop_session(self, session: emulator.Session) -> None:
        session.stop()

    def _session_finished(self, session: emulator.Session) -> None:
        for row in list(self.rows):
            if row.session is session:
                row.mark_finished()
                name = session.game.name
                if row.completed:
                    self._notify(
                        'Session finished',
                        f'{name} ran for the full '
                        f'{format_duration(session.seconds)}. '
                        'Check the quest in Discord.',
                    )
                else:
                    self._notify(
                        'Session stopped early',
                        f'{name} ran for {format_duration(row.elapsed)} '
                        f'of {format_duration(session.seconds)}.',
                    )
                QTimer.singleShot(2500, lambda r=row: self._remove_row(r))
        self._update_tray_status()

    def _remove_row(self, row: ActiveSession) -> None:
        if row in self.rows:
            self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        if not self.rows:
            self.idle_label.show()

    def _tick(self) -> None:
        for row in self.rows:
            if row.session.is_running:
                row.tick()
        self._update_tray_status()

    # -- shutdown --------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Darken the title bar once the native window handle exists."""
        super().showEvent(event)
        if not getattr(self, '_chrome_done', False):
            self._chrome_done = True
            winchrome.apply_dark_titlebar(self, background=BG)

    def closeEvent(self, event) -> None:
        # Hiding to the tray keeps every session running and the timer ticking,
        # so nothing is lost by closing the window mid-session.
        if self._hides_to_tray() and not self._quitting:
            event.ignore()
            self.hide()
            # Explained once ever, not once per launch. This is not a
            # notification, so it ignores the notification setting: without it
            # the window appears to have vanished.
            if not self.settings.get('tray_explained'):
                self.settings['tray_explained'] = True
                settings.set_value('tray_explained', True)
                self.tray.showMessage(
                    'Still running',
                    'Sessions carry on in the background. Use the tray icon to '
                    'reopen the window or quit.',
                    app_icon(), 6000,
                )
            return

        running = [r.session for r in self.rows if r.session.is_running]
        if running:
            confirm = QMessageBox.question(
                self, 'Sessions still running',
                f'{len(running)} session(s) are still running. '
                'Quitting will stop them and clean up. Continue?',
            )
            if confirm != QMessageBox.Yes:
                self._quitting = False
                event.ignore()
                return

        for session in running:
            session.stop()
        self.loader.shutdown()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
        QApplication.quit()


def app_icon() -> QIcon:
    path = bundled('data/icon.ico')
    return QIcon(str(path)) if path.is_file() else QIcon()


def run() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())

    # Hiding the window to the tray must not be treated as the app exiting.
    # closeEvent calls quit() explicitly when the user really means to leave.
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()
    return app.exec()
