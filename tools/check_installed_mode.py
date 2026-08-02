"""Replacing an installed executable must always give it back.

Uses a fake Steam-style install under the app's own data directory, so a real
game is never touched by the test. Covers the clean path and a hard kill.
"""

import hashlib
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dqc import emulator, journal          # noqa: E402
from dqc.appdirs import data_dir           # noqa: E402
from dqc.catalog import Game               # noqa: E402

FAKE = data_dir() / 'test_install' / 'Shift At Midnight Demo'
ORIGINAL = b'PRETEND THIS IS THE REAL GAME EXECUTABLE' * 64


def digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def build_install() -> Path:
    shutil.rmtree(FAKE.parent, ignore_errors=True)
    FAKE.mkdir(parents=True)
    exe = FAKE / 'ShiftAtMidnight.exe'
    exe.write_bytes(ORIGINAL)
    return exe


def make_plan(exe: Path) -> emulator.Plan:
    game = Game(id='test', name='Shift At Midnight Demo')
    return emulator.Plan(
        game=game,
        relative=Path('ShiftAtMidnight.exe'),
        exe_path=exe,
        mode=emulator.INSTALLED,
        backup=exe.with_name(exe.name + '.dqc-backup'),
    )


def main() -> int:
    ok = True

    print('-- clean run')
    exe = build_install()
    before = digest(exe)
    print(f'   original digest : {before}')

    session = emulator.Session(make_plan(exe), seconds=3)
    session.start()
    time.sleep(1.5)

    swapped = digest(exe) != before
    backed_up = session.plan.backup.is_file()
    print(f'   swapped for stub: {swapped}')
    print(f'   original saved  : {backed_up}')
    print(f'   process alive   : {session.is_running}')

    session.wait()
    restored = exe.is_file() and digest(exe) == before
    gone = not session.plan.backup.exists()
    print(f'   restored        : {restored}')
    print(f'   backup removed  : {gone}')
    ok = ok and swapped and backed_up and restored and gone

    print('\n-- hard kill, then recovery on next launch')
    exe = build_install()
    session = emulator.Session(make_plan(exe), seconds=120)
    session.start()
    time.sleep(1.0)
    session.process.kill()
    session.process.wait()

    displaced = digest(exe) != before
    print(f'   original displaced: {displaced}')
    print(f'   journal rows      : {len(journal._read_all())}')

    notes = journal.recover()
    healed = exe.is_file() and digest(exe) == before
    print(f'   recover()         : {notes}')
    print(f'   original back     : {healed}')
    ok = ok and displaced and healed

    print('\n-- refuses to start on top of an existing backup')
    exe = build_install()
    plan = make_plan(exe)
    plan.backup.write_bytes(b'stale')
    try:
        emulator.Session(plan, seconds=5).start()
        print('   ACCEPTED (should have refused)')
        ok = False
    except emulator.EmulationError as exc:
        print(f'   refused: {str(exc)[:66]}...')

    shutil.rmtree(FAKE.parent, ignore_errors=True)
    journal.recover()
    print('\nPASS' if ok else '\nFAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
