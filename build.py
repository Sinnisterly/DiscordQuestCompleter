"""Build the release binaries.

    python build.py

Produces two executables in dist/:

    stub.exe                    the stand-in process, copied at launch time
    DiscordQuestCompleter.exe   the application, with stub.exe bundled inside

The stub is built first because the main app embeds it as a data file. It is
kept separate, and free of PySide6, so that the file copied into an emulated
game folder stays small.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / 'dist'
BUILD = ROOT / 'build'
STUB = DIST / 'stub.exe'
ICON = ROOT / 'dqc' / 'data' / 'icon.ico'
APP_NAME = 'DiscordQuestCompleter'


def clear(path: Path) -> None:
    """Delete a build directory, saying plainly why if it cannot be deleted.

    The usual cause is the application still being open, which holds a lock on
    its own executable. Ignoring that failure leaves the stale binary in place
    and PyInstaller fails later with a bare access-denied error.
    """
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        sys.exit(
            f'could not clear {path}\n  {exc}\n'
            '  Close DiscordQuestCompleter.exe and any running stub window, '
            'then build again.'
        )


def run(args: list[str]) -> None:
    print('  $', ' '.join(args))
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f'command failed with exit code {result.returncode}')


def build_stub() -> None:
    print('\n[1/2] building stub.exe')
    run([
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean',
        '--onefile', '--windowed',
        '--name', 'stub',
        '--icon', str(ICON),
        # Nothing here should pull in the GUI framework or a HTTP stack.
        '--exclude-module', 'PySide6',
        '--exclude-module', 'shiboken6',
        '--exclude-module', 'requests',
        '--exclude-module', 'urllib3',
        '--exclude-module', 'numpy',
        '--exclude-module', 'unittest',
        '--exclude-module', 'pydoc',
        str(ROOT / 'dqc' / 'stub.py'),
    ])
    if not STUB.is_file():
        sys.exit('stub.exe was not produced')
    print(f'  stub.exe: {STUB.stat().st_size / 1e6:.1f} MB')


def build_app() -> None:
    print('\n[2/2] building the application')
    separator = ';' if sys.platform == 'win32' else ':'
    run([
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean',
        '--onefile', '--windowed',
        '--name', APP_NAME,
        '--icon', str(ICON),
        '--add-data', f'{ROOT / "dqc" / "data"}{separator}data',
        '--add-data', f'{STUB}{separator}.',
        '--exclude-module', 'tkinter',
        '--exclude-module', 'PySide6.QtQml',
        '--exclude-module', 'PySide6.QtQuick',
        '--exclude-module', 'PySide6.QtWebEngineCore',
        '--exclude-module', 'PySide6.Qt3DCore',
        '--exclude-module', 'PySide6.QtMultimedia',
        '--exclude-module', 'PySide6.QtCharts',
        '--exclude-module', 'unittest',
        str(ROOT / 'run.py'),
    ])
    app = DIST / f'{APP_NAME}.exe'
    if not app.is_file():
        sys.exit(f'{APP_NAME}.exe was not produced')
    print(f'  {APP_NAME}.exe: {app.stat().st_size / 1e6:.1f} MB')


def main() -> int:
    if not (ROOT / 'dqc' / 'data' / 'detectable.json.gz').is_file():
        sys.exit('missing dqc/data/detectable.json.gz, run tools/build_snapshot.py first')
    if not ICON.is_file():
        sys.exit('missing dqc/data/icon.ico, run tools/make_icon.py first')

    for path in (BUILD, DIST):
        clear(path)

    build_stub()
    build_app()

    print('\ndone. Ship dist/DiscordQuestCompleter.exe')
    return 0


if __name__ == '__main__':
    sys.exit(main())
