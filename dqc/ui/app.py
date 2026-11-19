"""Start the Qt Quick interface, plus the tray icon that keeps it alive."""

from __future__ import annotations

import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..appdirs import bundled
from ..catalog import get_catalog
from .backend import Backend
from .images import ArtProvider
from .theme_bridge import ThemeBridge


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
        self.engine.load(QUrl.fromLocalFile(str(bundled('ui/qml/Main.qml'))))
        if not self.engine.rootObjects():
            raise RuntimeError('The interface failed to load:\n' + '\n'.join(qml_errors[:20]))
        self.window = self.engine.rootObjects()[0]

        if tray_ok:
            self._build_tray()

        self.backend.showWindowRequested.connect(self.show_window)
        self.backend.hideWindowRequested.connect(self.window.hide)
        self.backend.quitRequested.connect(self._quit)
        self.backend.notify.connect(self._notify)
        self.backend.statusChanged.connect(self._update_tray)
        self.backend.startup()

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
    app = App(qt_app)  # noqa: F841 - kept alive for the event loop
    return qt_app.exec()
