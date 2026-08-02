"""Closing the stub window must not end the session.

Starts a real session, sends the stub window a genuine WM_CLOSE the way the
title bar button does, and checks the process survives. Then stops it properly
through the app and checks it exits and cleans up.
"""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dqc import emulator                     # noqa: E402
from dqc.catalog import get_catalog          # noqa: E402

WM_CLOSE = 0x0010
user32 = ctypes.windll.user32

ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def windows_for(pid: int) -> list[int]:
    found = []

    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(ENUM_PROC(callback), 0)
    return found


def main() -> int:
    catalog = get_catalog()
    game = catalog.exact('Where Winds Meet')
    plan = emulator.plan_session(game)

    session = emulator.Session(plan, seconds=120)
    session.start()
    print(f'started        : pid={session.process.pid}')

    handles = []
    for _ in range(40):
        time.sleep(0.25)
        handles = windows_for(session.process.pid)
        if handles:
            break
    print(f'stub window    : {bool(handles)} ({len(handles)} visible)')
    if not handles:
        session.stop()
        session.wait()
        print('FAIL: never found the stub window')
        return 1

    for hwnd in handles:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    print('sent WM_CLOSE  : yes')

    time.sleep(1.5)
    alive = session.is_running
    still_placed = plan.exe_path.is_file()
    # A minimised window keeps WS_VISIBLE set, so IsWindowVisible stays true.
    # IsIconic is what actually reports the minimised state.
    minimised = all(user32.IsIconic(h) for h in handles)
    print(f'session alive  : {alive}')
    print(f'window minimised: {minimised}')
    print(f'stub still on disk: {still_placed}')

    session.stop()
    session.wait()
    stopped = not session.is_running
    cleaned = not plan.root.exists()
    print(f'stop works     : {stopped}')
    print(f'cleaned up     : {cleaned}')

    ok = alive and minimised and still_placed and stopped and cleaned
    print('\nPASS' if ok else '\nFAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
