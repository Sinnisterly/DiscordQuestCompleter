"""Load the QML interface offscreen and exercise the backend behind it.

    python tools/check_ui.py [screenshot folder]

Fails on any QML warning or error. With a folder, saves a screenshot of every
page there (run without QT_QPA_PLATFORM=offscreen for real fonts).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PySide6.QtCore import QEventLoop, QTimer, qInstallMessageHandler  # noqa: E402

messages: list[str] = []
qInstallMessageHandler(lambda _mode, _ctx, msg: messages.append(msg))

from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402
from PySide6.QtWidgets import QApplication        # noqa: E402

QQuickStyle.setStyle('Basic')
qt = QApplication([])

from dqc import settings          # noqa: E402
from dqc.ui.app import App        # noqa: E402

failures: list[str] = []


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(label: str, ok: bool, detail='') -> None:
    print(f'  {"ok  " if ok else "FAIL"} {label}{f": {detail}" if detail else ""}')
    if not ok:
        failures.append(label)


before = dict(settings.load())
app = App(qt)
backend, window = app.backend, app.window
wait(800)

print('window')
check('loaded', window is not None)
check('frameless title', window.property('title') == 'Discord Quest Completer')

print('library')
check('default list has games', backend.library.rowCount() > 0, backend.library.rowCount())
for query, expect in [('zzz', 'Zenless Zone Zero'), ('where winds', 'Where Winds Meet')]:
    backend.search(query)
    top = backend.catalog.by_id(backend.library.idAt(0))
    check(f'search {query!r}', top is not None and top.name == expect, top.name if top else None)
backend.search('qqqqqq')
check('nonsense search is empty', backend.library.rowCount() == 0)

game = backend.catalog.exact('Where Winds Meet')
detail = backend.gameDetail(game.id)
check('detail has paths', len(detail['paths']) > 0)
check('detail has three placements', len(detail['placements']) == 3)
plan = backend.planPath(game.id, detail['paths'][0]['path'], 'sandbox')
check('sandbox plan resolves', plan['ok'], plan['text'])

print('duration')
check('blank is 15m 30s', backend.durationHint('')['text'] == 'Runs for 15m 30s (default)',
      backend.durationHint('')['text'])
check('20m accepted', backend.durationHint('20m')['ok'])
check('bogus rejected', not backend.durationHint('bogus')['ok'])

print('pages and themes')
pages = sys.argv[1] if len(sys.argv) > 1 else None
for index in range(6):
    window.setProperty('currentPage', index)
    wait(400)
    if pages:
        window.grabWindow().save(os.path.join(pages, f'page{index}.png'))
original = app.theme.name
for name in ('Light', 'OLED Black', original):
    app.theme.apply(name)
    wait(150)
check('theme switch', app.theme.name == original)

print('settings')
backend.notifyEnabled = False
backend.watchQuests = False
check('notify off saved', settings.get('notify_on_finish') is False)
check('watch off saved', settings.get('watch_quests') is False)
for key, value in before.items():
    settings.set_value(key, value)
if 'watch_quests' not in before:
    settings.set_value('watch_quests', True)

noise = [m for m in messages if 'Cannot find font directory' not in m and 'no longer ships fonts' not in m]
print('qml messages')
check('no QML warnings', not noise, '\n    '.join(noise[:10]))

app.art.shutdown()
print('\nFAIL' if failures else '\nOK')
sys.exit(1 if failures else 0)
