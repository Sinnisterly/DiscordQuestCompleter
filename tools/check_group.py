"""Launch two games as a group and check the group behaves.

Each game must run its own stand-in with an off-screen window (Discord only
counts games that have a window), one group window must show, and closing the group must stop and clean up both games.
Opens a real countdown window for a few seconds.
"""

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QTimer        # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

qt = QApplication([])

from dqc.catalog import get_catalog                   # noqa: E402
from dqc.ui.backend import Backend                    # noqa: E402
from dqc.ui.theme_bridge import ThemeBridge           # noqa: E402

user32 = ctypes.windll.user32
failures = []


def wait_until(predicate, timeout=20.0):
    loop = QEventLoop()
    end = time.time() + timeout

    def poll():
        if predicate() or time.time() > end:
            loop.quit()
        else:
            QTimer.singleShot(100, poll)

    QTimer.singleShot(100, poll)
    loop.exec()
    return predicate()


def visible_windows(pid: int) -> int:
    count = 0

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        nonlocal count
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            count += 1
        return True

    user32.EnumWindows(callback, 0)
    return count


def offscreen_windows(pid: int) -> int:
    """Visible windows of a stub process tree that sit off every screen."""
    count = 0
    pids = tree_pids(pid)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        nonlocal count
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        rect = wintypes.RECT()
        if owner.value in pids and user32.IsWindowVisible(hwnd) and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            if rect.right < 0 or rect.bottom < 0:
                count += 1
        return True

    user32.EnumWindows(callback, 0)
    return count


def tree_pids(pid: int) -> set[int]:
    """A process and its children: the built stub runs as launcher plus child."""
    import subprocess
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | ForEach-Object {{ $_.ProcessId }}"],
        capture_output=True, text=True).stdout.split()
    return {pid, *(int(p) for p in out if p.isdigit())}


def emulated_processes() -> int:
    import subprocess
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "@(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like '*DiscordQuestCompleter*emulated*' }).Count"],
        capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def check(label, ok, detail=''):
    print(f'  {"ok  " if ok else "FAIL"} {label}{f": {detail}" if detail else ""}')
    if not ok:
        failures.append(label)


catalog = get_catalog()
backend = Backend(catalog, ThemeBridge(), tray_available=False)
games = [catalog.exact('Where Winds Meet'), catalog.exact('Delta Force')]
backend._launch_group(games)

entries = list(backend.sessions.entries)
check('two sessions started', len(entries) == 2, len(entries))
check('both quiet', all(e.session.quiet == 'offscreen' for e in entries))
group = entries[0].group if entries else None
check('one shared group', group is not None and all(e.group is group for e in entries))

wait_until(lambda: group is not None and group.is_running and visible_windows(group.process.pid) > 0, 15)
check('group window visible', group is not None and visible_windows(group.process.pid) > 0)
time.sleep(1.5)
# Discord needs a visible window, so each stand-in keeps one, off-screen.
check('game stand-ins have a window, off-screen',
      all(offscreen_windows(e.session.process.pid) >= 1 for e in entries),
      [offscreen_windows(e.session.process.pid) for e in entries])
check('game stand-ins running', all(e.session.is_running for e in entries))

# Pressing Stop all in the group window ends the group process.
group.stop()
wait_until(lambda: all(e.ended for e in entries), 20)
check('closing the group stops both games', all(e.ended == 'stopped' for e in entries),
      [e.ended for e in entries])
wait_until(lambda: emulated_processes() == 0, 10)
check('no stand-in left running', emulated_processes() == 0, emulated_processes())
wait_until(lambda: all(not e.session.plan.root.exists() for e in entries), 10)
check('folders cleaned up', all(not e.session.plan.root.exists() for e in entries))

print('\nFAIL' if failures else '\nOK')
sys.exit(1 if failures else 0)
