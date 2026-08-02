"""Construct the window offscreen and exercise its interactions."""

import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Console here is not UTF-8; keep the check readable regardless of codepage.
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PySide6.QtCore import Qt                                  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon    # noqa: E402

from dqc import settings, winchrome          # noqa: E402
from dqc.theme import STYLESHEET             # noqa: E402
from dqc.window import MainWindow            # noqa: E402

app = QApplication([])
app.setStyleSheet(STYLESHEET)

window = MainWindow()
window.show()
print(f'window built: {window.windowTitle()}')
print(f'default list : {window.results.count()} rows')
print(f'selected     : {window.selected.name if window.selected else None}')
print(f'resolved     : {window.resolved.text()}')
print(f'duration hint: {window.duration_hint.text()}')
print(f'launch enabled: {window.launch.isEnabled()}')

for query in ['zzz', 'valorant', 'opera', 'qqqqqq']:
    window.search.setText(query)
    top = window.selected.name if window.selected else None
    print(f'  search {query!r:10s} -> {window.results.count():3d} rows, top={top!r}')

window.search.setText('where winds')
print(f'\npaths offered: {[window.path_box.itemText(i) for i in range(window.path_box.count())]}')

window.duration.setText('bogus')
print(f'bad duration : {window.duration_hint.text()}')
window.duration.setText('20m')
print(f'good duration: {window.duration_hint.text()}')

window.placement.setCurrentIndex(1)
print(f'steam mode   : {window.resolved.text()}')
window.placement.setCurrentIndex(0)
print(f'sandbox mode : {window.resolved.text()}')

print(f'\nh-scrollbar off: {window.results.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff}')
print(f'dark titlebar  : {winchrome.apply_dark_titlebar(window)}')

print('\ntray and notifications:')
print(f'  tray available : {QSystemTrayIcon.isSystemTrayAvailable()}')
print(f'  tray created   : {window.tray is not None}')
print(f'  hides to tray  : {window._hides_to_tray()}')
print(f'  quest button   : {window.quest_button.text()!r}')

# Both toggles must survive a round trip through the settings file.
before = dict(settings.load())
window.notify_check.setChecked(False)
window.tray_check.setChecked(False)
print(f'  notify off     : {settings.get("notify_on_finish") is False}')
print(f'  tray off       : {settings.get("minimise_to_tray") is False}')
print(f'  hides now      : {window._hides_to_tray()}')
window.notify_check.setChecked(bool(before.get('notify_on_finish', True)))
window.tray_check.setChecked(bool(before.get('minimise_to_tray', True)))
print(f'  restored       : {settings.load() == before}')

# With notifications off, _notify must be a no-op rather than raising.
window.settings['notify_on_finish'] = False
window._notify('should not appear', 'suppressed')
print('  suppressed ok  : True')

window.loader.shutdown()
print('\nOK')
