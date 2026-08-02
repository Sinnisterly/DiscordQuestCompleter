"""Building a fake game install and running the stand-in process.

Discord matches a running process by the tail of its executable path, which is
why the community index writes paths as ``..\\Game\\bin\\game.exe``. That tail
does not have to sit under ``steamapps/common``, so by default everything is
built inside the app's own directory: no administrator rights, and no way to
damage a game the user owns.

Steam-anchored placement is available for the few titles that seem to check for
Steam-created folders. It is opt-in and refuses to touch an existing install.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from . import journal, steamlibs
from .appdirs import bundled, data_dir, is_frozen
from .catalog import Game

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class EmulationError(RuntimeError):
    pass


def sandbox_root() -> Path:
    p = data_dir() / 'emulated'
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_name(name: str) -> str:
    cleaned = _UNSAFE.sub('_', (name or 'Game')).strip(' .')
    return cleaned or 'Game'


def expand(path: str) -> str:
    """Fill in placeholders such as Roblox's per-install version folder."""
    if '{version_hash}' in path:
        path = path.replace('{version_hash}', secrets.token_hex(8))
    return path


def to_relative(path: str) -> Path:
    """Normalise a catalogue path into a relative Path.

    Handles the mixed separators present in both data sources (Discord uses
    forward slashes, the wiki uses backslashes, one entry uses both).
    """
    cleaned = expand(path).replace('\\', '/').strip('/')
    parts = [p for p in cleaned.split('/') if p not in ('', '.', '..')]
    if not parts:
        raise EmulationError('empty executable path')
    return Path(*parts)


# ---------------------------------------------------------------- placement

SANDBOX = 'sandbox'
STEAM = 'steam'
INSTALLED = 'installed'


@dataclass
class Plan:
    """Where a session will write, decided before anything touches disk."""
    game: Game
    relative: Path
    exe_path: Path
    mode: str = SANDBOX
    root: Path | None = None      # directory tree we create and later remove
    backup: Path | None = None    # where a displaced original is kept
    warning: str | None = None

    @property
    def exe_name(self) -> str:
        return self.exe_path.name

    @property
    def anchored(self) -> bool:
        return self.mode != SANDBOX


def find_installed(game: Game, path: str | None = None) -> dict | None:
    """The user's real installation of this game, if Steam has one.

    The first component of a community path is usually the Steam install
    folder, which makes it a better clue than the catalogue name.
    """
    names = [game.name]
    chosen = path or game.primary
    if chosen:
        try:
            parts = to_relative(chosen).parts
        except EmulationError:
            parts = ()
        if len(parts) > 1:
            names.insert(0, parts[0])
    return steamlibs.find_install(app_id=game.steam_appid, names=names)


def _locate_real_exe(install: Path, relative: Path) -> Path | None:
    """Find the genuine executable inside an installed game.

    Tries the community path first, then searches by filename, since an
    install directory does not always match the first path component.
    """
    direct = install.parent / relative
    if direct.is_file():
        return direct

    inside = install / relative
    if inside.is_file():
        return inside

    wanted = relative.name.lower()
    try:
        for candidate in install.rglob('*.exe'):
            if candidate.name.lower() == wanted:
                return candidate
    except OSError:
        pass
    return None


def plan_session(game: Game, path: str | None = None, mode: str = SANDBOX) -> Plan:
    chosen = path or game.primary
    if not chosen:
        raise EmulationError(f'No known executable path for {game.name}.')

    relative = to_relative(chosen)

    if mode == INSTALLED:
        install = find_installed(game, chosen)
        if install is None:
            raise EmulationError(
                f'No Steam installation of {game.name} was found. '
                'Install it, or use sandbox placement.'
            )
        target = _locate_real_exe(install['path'], relative)
        if target is None:
            raise EmulationError(
                f'Found {install["path"]}, but no file named "{relative.name}" '
                'inside it. Pick a different executable path.'
            )
        return Plan(
            game=game, relative=relative, exe_path=target, mode=INSTALLED,
            backup=target.with_name(target.name + '.dqc-backup'),
            warning=(
                f'The real {target.name} will be renamed while the session runs '
                'and put back afterwards.'
            ),
        )

    if mode == STEAM:
        common = steamlibs.default_common()
        if common is None:
            raise EmulationError(
                'Steam-anchored placement needs a Steam installation, and none was found.'
            )
        top = relative.parts[0]
        owned = steamlibs.find_owned(top)
        if owned is not None:
            raise EmulationError(
                f'You already own something installed at "{owned}". '
                f'Refusing to write there. Use the installed copy instead.'
            )
        return Plan(
            game=game, relative=relative, exe_path=common / relative, mode=STEAM,
            root=common / top, warning='Writing inside a real Steam library.',
        )

    base = sandbox_root() / safe_name(game.name)
    return Plan(game=game, relative=relative, exe_path=base / relative,
                mode=SANDBOX, root=base)


# -------------------------------------------------------------------- stub

def _python_runtime() -> tuple[Path, Path]:
    """Interpreter and its core DLL, for the source-checkout stub."""
    exe = Path(sys.executable)
    dll = exe.parent / f'python{sys.version_info.major}{sys.version_info.minor}.dll'
    return exe, dll


def provision_stub(target: Path) -> list[Path]:
    """Put a runnable executable at ``target``. Returns every file created.

    Frozen builds copy the purpose-built stub binary. From a source checkout
    there is no such binary, so we copy the Python interpreter itself and let
    it run ``stub.py``; a renamed ``python.exe`` reports the new name as its
    process image, which is what Discord reads.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    if is_frozen():
        source = bundled('stub.exe')
        if not source.is_file():
            raise EmulationError('stub.exe is missing from this build.')
        shutil.copy2(source, target)
        created.append(target)
        return created

    exe, dll = _python_runtime()
    shutil.copy2(exe, target)
    created.append(target)
    if dll.is_file():
        side = target.parent / dll.name
        if not side.exists():
            shutil.copy2(dll, side)
            created.append(side)
    return created


def _stub_command(
    target: Path, seconds: int, title: str, icon: Path | None = None,
) -> tuple[list[str], dict]:
    env = os.environ.copy()
    extra = [str(icon)] if icon else []

    if is_frozen():
        return [str(target), str(seconds), title, *extra], env

    exe, _ = _python_runtime()
    env['PYTHONHOME'] = str(exe.parent)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    script = Path(__file__).resolve().parent / 'stub.py'
    return [str(target), str(script), str(seconds), title, *extra], env


# ----------------------------------------------------------------- session

class Session:
    """A running emulation. Cleans up exactly once, however it ends."""

    def __init__(self, plan: Plan, seconds: int, icon: Path | None = None):
        self.plan = plan
        self.seconds = seconds
        self.icon = icon
        self.process: subprocess.Popen | None = None
        self.entry: journal.Entry | None = None
        self._created: list[Path] = []
        self._cleaned = threading.Event()
        self._lock = threading.Lock()

    @property
    def game(self) -> Game:
        return self.plan.game

    def start(self) -> None:
        plan = self.plan

        if plan.mode == INSTALLED:
            if not plan.exe_path.is_file():
                raise EmulationError(f'{plan.exe_path} is missing.')
            if plan.backup is not None and plan.backup.exists():
                raise EmulationError(
                    f'A backup already exists at {plan.backup}. A previous '
                    'session may still be running, or it did not finish '
                    'cleanly. Restart the app to have it restored.'
                )
        elif plan.exe_path.exists():
            raise EmulationError(
                f'{plan.exe_path} already exists. Another session may be running.'
            )

        # Journal before mutating, so a crash here is still recoverable.
        self.entry = journal.Entry(
            game=plan.game.name,
            created_root=plan.root,
            backup=plan.backup,
            stub=plan.exe_path,
        )
        journal.record(self.entry)

        # Step aside from the real executable before writing over its name.
        if plan.mode == INSTALLED and plan.backup is not None:
            try:
                os.replace(plan.exe_path, plan.backup)
            except OSError as exc:
                self._cleanup()
                raise EmulationError(
                    f'Could not move the original {plan.exe_path.name} aside: {exc}. '
                    'Close the game and Steam, then try again.'
                ) from exc

        try:
            self._created = provision_stub(plan.exe_path)
        except (OSError, EmulationError) as exc:
            self._cleanup()
            raise EmulationError(f'Could not place the stand-in executable: {exc}') from exc

        command, env = _stub_command(
            plan.exe_path, self.seconds, plan.game.name, self.icon,
        )
        try:
            self.process = subprocess.Popen(
                command,
                env=env,
                cwd=str(plan.exe_path.parent),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except OSError as exc:
            self._cleanup()
            raise EmulationError(f'Could not start the stand-in process: {exc}') from exc

    def wait(self) -> int:
        """Block until the stub exits, then clean up. Returns its exit code."""
        code = 0
        try:
            if self.process is not None:
                code = self.process.wait()
        finally:
            self._cleanup()
        return code

    def stop(self) -> None:
        """Ask the stub to exit; cleanup happens in whoever called wait()."""
        process = self.process
        if process is None or process.poll() is not None:
            self._cleanup()
            return
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        except OSError:
            pass

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _cleanup(self) -> None:
        with self._lock:
            if self._cleaned.is_set():
                return
            self._cleaned.set()

        plan = self.plan
        try:
            if plan.mode == INSTALLED:
                # Putting the real executable back matters more than tidying,
                # so it happens first and on its own.
                for path in self._created:
                    if path != plan.backup and path.is_file():
                        path.unlink(missing_ok=True)
                if plan.backup is not None and plan.backup.is_file():
                    os.replace(plan.backup, plan.exe_path)
            elif plan.mode == STEAM:
                # Only remove what we created, never a directory that predates us.
                for path in reversed(self._created):
                    if path.is_file():
                        path.unlink(missing_ok=True)
                if plan.root is not None:
                    _prune_empty(plan.exe_path.parent, plan.root)
            elif plan.root is not None and plan.root.is_dir():
                shutil.rmtree(plan.root, ignore_errors=True)
        except OSError:
            pass

        if self.entry is not None:
            journal.clear(self.entry.id)


def _prune_empty(leaf: Path, stop: Path) -> None:
    """Walk up from ``leaf`` removing directories we emptied, never past ``stop``."""
    current = leaf
    try:
        stop = stop.resolve()
    except OSError:
        return
    while True:
        try:
            resolved = current.resolve()
        except OSError:
            return
        if not resolved.is_dir() or any(resolved.iterdir()):
            return
        try:
            resolved.rmdir()
        except OSError:
            return
        if resolved == stop or current.parent == current:
            return
        current = current.parent
