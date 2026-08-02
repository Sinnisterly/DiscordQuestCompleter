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

@dataclass
class Plan:
    """Where a session will write, decided before anything touches disk."""
    game: Game
    relative: Path
    root: Path          # top-level directory we create and later remove
    exe_path: Path
    anchored: bool      # True when placed inside a real Steam library
    warning: str | None = None

    @property
    def exe_name(self) -> str:
        return self.exe_path.name


def plan_session(game: Game, path: str | None = None, anchored: bool = False) -> Plan:
    chosen = path or game.primary
    if not chosen:
        raise EmulationError(f'No known executable path for {game.name}.')

    relative = to_relative(chosen)
    warning = None

    if anchored:
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
                f'Refusing to write there. Use sandbox placement instead.'
            )
        base = common
        root = common / top
        warning = 'Writing inside a real Steam library.'
    else:
        base = sandbox_root() / safe_name(game.name)
        root = base

    return Plan(game=game, relative=relative, root=root, exe_path=base / relative,
                anchored=anchored, warning=warning)


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
        if plan.exe_path.exists():
            raise EmulationError(
                f'{plan.exe_path} already exists. Another session may be running.'
            )

        # Journal before mutating, so a crash here is still recoverable.
        self.entry = journal.Entry(
            game=plan.game.name,
            created_root=plan.root,
            stub=plan.exe_path,
        )
        journal.record(self.entry)

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

        root = self.plan.root
        try:
            if self.plan.anchored:
                # Only remove what we created, never a directory that predates us.
                for path in reversed(self._created):
                    if path.is_file():
                        path.unlink(missing_ok=True)
                _prune_empty(self.plan.exe_path.parent, root)
            elif root.is_dir():
                shutil.rmtree(root, ignore_errors=True)
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
