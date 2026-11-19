"""The catalogue refresh must finish and report back on the UI thread.

    python tools/check_refresh.py            stubbed network
    python tools/check_refresh.py --network  also fetch the real list

The old interface lost the result: it called QTimer.singleShot from a plain
thread, which has no event loop, so the callback never ran.
"""

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QTimer       # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

qt = QApplication([])

from dqc.catalog import get_catalog                  # noqa: E402
from dqc.ui.backend import Backend                   # noqa: E402
from dqc.ui.theme_bridge import ThemeBridge          # noqa: E402

failures = []
catalog = get_catalog()
backend = Backend(catalog, ThemeBridge(), tray_available=False)
seen = {}


def on_toast(text, kind):
    seen['toast'] = (text, kind)
    seen['thread'] = threading.current_thread() is threading.main_thread()


backend.toast.connect(on_toast)


def run_until(predicate, timeout=90):
    loop = QEventLoop()
    end = time.time() + timeout

    def poll():
        if predicate() or time.time() > end:
            loop.quit()
        else:
            QTimer.singleShot(50, poll)

    QTimer.singleShot(50, poll)
    loop.exec()


# Stubbed: the worker returns quickly, the result must still arrive.
real_refresh = catalog.refresh
catalog.refresh = lambda timeout=30: (time.sleep(0.3), True)[1]
backend.refreshCatalog()
backend.refreshCatalog()  # a second click while running is ignored
run_until(lambda: 'toast' in seen, timeout=10)
print(f'stubbed : toast={seen.get("toast")} on_ui_thread={seen.get("thread")}')
if 'toast' not in seen:
    failures.append('refresh result never reached the UI thread')
if backend.refreshing:
    failures.append('refreshing flag stuck on')
if not seen.get('thread'):
    failures.append('result delivered off the UI thread')
catalog.refresh = real_refresh

if '--network' in sys.argv:
    before = catalog.generated
    seen.clear()
    time.sleep(1.1)  # generated has one-second resolution
    backend.refreshCatalog()
    run_until(lambda: 'toast' in seen)
    print(f'network : {seen.get("toast")} generated {before} -> {catalog.generated}')
    if catalog.generated <= before:
        failures.append('real refresh did not update the catalogue')

print('\nFAIL\n' + '\n'.join(failures) if failures else '\nOK')
sys.exit(1 if failures else 0)
