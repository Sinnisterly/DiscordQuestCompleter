"""Start the Qt Quick interface, plus the tray icon that keeps it alive."""

from __future__ import annotations

import getpass
import sys

from PySide6.QtCore import QMetaObject, QPoint, QRect, QUrl
from PySide6.QtGui import QAction, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import settings, startup
from ..appdirs import bundled
from ..catalog import get_catalog
from .backend import Backend
from .images import ArtProvider
from .theme_bridge import ThemeBridge


# One copy of the app per Windows user. A second launch hands over to the
# first one and exits.
INSTANCE_NAME = f'DiscordQuestCompleter-{getpass.getuser()}'


def already_running(show: bool) -> bool:
    """True if another copy is running. With show, it is asked to open its window."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_NAME)
    if not socket.waitForConnected(500):
        return False
    if show:
        socket.write(b'show')
        socket.flush()
        socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def app_icon() -> QIcon:
    path = bundled('data/icon.ico')
    return QIcon(str(path)) if path.is_file() else QIcon()


def icon_font() -> str:
    """Windows' own icon font: Fluent on Windows 11, MDL2 on Windows 10."""
    families = set(QFontDatabase.families())
    for name in ('Segoe Fluent Icons', 'Segoe MDL2 Assets'):
        if name in families:
            return name
    return 'Segoe MDL2 Assets'


class App:
    def __init__(self, qt_app: QApplication):
        self.qt = qt_app
        self.catalog = get_catalog()
        self.theme = ThemeBridge()
        self.tray: QSystemTrayIcon | None = None
        tray_ok = QSystemTrayIcon.isSystemTrayAvailable()

        self.backend = Backend(self.catalog, self.theme, tray_available=tray_ok)
        self.art = ArtProvider(self.catalog)

        self.engine = QQmlApplicationEngine()
        qml_errors: list[str] = []
        self.engine.warnings.connect(
            lambda warnings: qml_errors.extend(w.toString() for w in warnings)
        )
        self.engine.addImageProvider('art', self.art)
        context = self.engine.rootContext()
        context.setContextProperty('Theme', self.theme)
        context.setContextProperty('Backend', self.backend)
        context.setContextProperty('LibraryModel', self.backend.library)
        context.setContextProperty('QuestModel', self.backend.quests)
        context.setContextProperty('SessionModel', self.backend.sessions)
        context.setContextProperty('IconFont', icon_font())
        # Started by Windows at sign-in: stay in the tray until opened.
        context.setContextProperty('StartHidden', tray_ok and startup.TRAY_FLAG in sys.argv)
        startup.refresh()
        self.engine.load(QUrl.fromLocalFile(str(bundled('ui/qml/Main.qml'))))
        if not self.engine.rootObjects():
            raise RuntimeError('The interface failed to load:\n' + '\n'.join(qml_errors[:20]))
        self.window = self.engine.rootObjects()[0]

        if tray_ok:
            self._build_tray()

        self.backend.showWindowRequested.connect(self.show_window)
        self.backend.hideWindowRequested.connect(self.hide_window)
        self.backend.quitRequested.connect(self._quit)
        self.backend.notify.connect(self._notify)
        self.backend.statusChanged.connect(self._update_tray)
        self._restore_geometry()
        self._listen()
        self.backend.startup()

    # -- single instance ------------------------------------------------

    def _listen(self) -> None:
        self.server = QLocalServer()
        # A crashed copy can leave its name behind; clear it first.
        QLocalServer.removeServer(INSTANCE_NAME)
        self.server.listen(INSTANCE_NAME)
        self.server.newConnection.connect(self._handover)

    def _handover(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.waitForReadyRead(500)
            if bytes(socket.readAll()).startswith(b'show'):
                self.show_window()
            socket.disconnectFromServer()

    # -- window position ------------------------------------------------

    def _restore_geometry(self) -> None:
        """Put the window back where it was, if that spot is still on a screen."""
        saved = settings.get('window')
        if not (isinstance(saved, list) and len(saved) == 5):
            return
        x, y, width, height, maximized = saved
        if not all(isinstance(v, int) for v in (x, y, width, height)):
            return
        centre = QPoint(x + width // 2, y + 20)
        if QGuiApplication.screenAt(centre) is None:
            return  # that monitor is gone; keep the default spot
        self.window.setGeometry(QRect(x, y, max(width, 960), max(height, 620)))
        if maximized:
            QMetaObject.invokeMethod(self.window, 'toggleMaximize')

    def save_geometry(self) -> None:
        window = self.window
        maximized = bool(window.property('maximized'))
        if maximized:
            rect = window.property('normalGeometry')
            x, y, width, height = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        else:
            x, y, width, height = window.x(), window.y(), window.width(), window.height()
        if width > 0 and height > 0:
            settings.set_value('window', [x, y, width, height, maximized])

    def hide_window(self) -> None:
        self.save_geometry()
        self.window.hide()

    def _build_tray(self) -> None:
        tray = QSystemTrayIcon(app_icon())
        tray.setToolTip('Discord Quest Completer')
        menu = QMenu()
        self.tray_status = QAction('Nothing running', menu)
        self.tray_status.setEnabled(False)
        menu.addAction(self.tray_status)
        menu.addSeparator()
        show = QAction('Show window', menu)
        show.triggered.connect(self.show_window)
        menu.addAction(show)
        launch_all = QAction('Launch all', menu)
        launch_all.triggered.connect(self.backend.launchAll)
        menu.addAction(launch_all)
        detect = QAction('Detect from Discord', menu)
        detect.triggered.connect(self.backend.detectQuests)
        menu.addAction(detect)
        menu.addSeparator()
        quit_action = QAction('Quit', menu)
        quit_action.triggered.connect(self.backend.quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.messageClicked.connect(self.show_window)
        tray.show()
        self.tray, self.tray_menu = tray, menu

        # The countdown text changes every second; refresh the tooltip on the
        # session tick rather than on status changes alone.
        self.backend._tick_timer.timeout.connect(self._update_tray)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def _notify(self, title: str, body: str) -> None:
        if self.tray is not None:
            self.tray.showMessage(title, body, app_icon(), 8000)

    def _update_tray(self) -> None:
        if self.tray is None:
            return
        text = self.backend.tray_status()
        self.tray_status.setText(text)
        self.tray.setToolTip(f'Discord Quest Completer\n{text}')

    def _quit(self) -> None:
        if self.window.isVisible():
            self.save_geometry()
        self.server.close()
        self.art.shutdown()
        if self.tray is not None:
            self.tray.hide()
        self.qt.quit()


def run() -> int:
    QQuickStyle.setStyle('Basic')
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setApplicationName('Discord Quest Completer')
    qt_app.setWindowIcon(app_icon())
    # Hiding to the tray must not count as the app exiting.
    qt_app.setQuitOnLastWindowClosed(False)
    if already_running(show=startup.TRAY_FLAG not in sys.argv):
        return 0
    app = App(qt_app)  # noqa: F841 - kept alive for the event loop
    return qt_app.exec()
