"""Crash-safe record of filesystem changes.

Each change is written to disk before it happens, so a crash, a power cut or a
killed process can be undone on the next launch. Sandbox placement rarely needs
this; Steam-anchored placement does, and journalling everything costs almost
nothing.
"""

import json
import os
import shutil
import time
import uuid
from pathlib import Path

from .appdirs import data_dir

_JOURNAL_NAME = 'pending.json'


def _journal_path() -> Path:
    return data_dir() / _JOURNAL_NAME


def _read_all() -> list[dict]:
    path = _journal_path()
    if not path.is_file():
        return []
    try:
        content = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return content if isinstance(content, list) else []


def _write_all(entries: list[dict]) -> None:
    path = _journal_path()
    tmp = path.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(entries, indent=1), encoding='utf-8')
        os.replace(tmp, path)
    except OSError:
        pass


class Entry:
    """One in-flight emulation session."""

    def __init__(self, game: str, created_root=None, backup=None, stub=None):
        self.id = uuid.uuid4().hex
        self.game = game
        self.created_root = str(created_root) if created_root else None
        self.backup = str(backup) if backup else None
        self.stub = str(stub) if stub else None
        self.started = time.time()

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'game': self.game,
            'created_root': self.created_root,
            'backup': self.backup,
            'stub': self.stub,
            'started': self.started,
        }


def record(entry: Entry) -> None:
    entries = _read_all()
    entries.append(entry.to_dict())
    _write_all(entries)


def clear(entry_id: str) -> None:
    _write_all([e for e in _read_all() if e.get('id') != entry_id])


def _rollback_one(entry: dict) -> str | None:
    """Undo a single entry. Returns a human-readable note, or None if clean."""
    stub = entry.get('stub')
    backup = entry.get('backup')
    created_root = entry.get('created_root')

    # Restoring a displaced original always takes priority over tidying.
    if backup:
        backup_path = Path(backup)
        target = Path(stub) if stub else None
        if backup_path.is_file() and target is not None:
            try:
                if target.is_file():
                    target.unlink()
                os.replace(backup_path, target)
                return f'restored {target.name}'
            except OSError as exc:
                return f'could not restore {target.name}: {exc}'

    if created_root:
        root = Path(created_root)
        if root.is_dir():
            try:
                shutil.rmtree(root)
                return f'removed leftover {root.name}'
            except OSError as exc:
                return f'could not remove {root}: {exc}'

    if stub and not backup:
        stub_path = Path(stub)
        if stub_path.is_file():
            try:
                stub_path.unlink()
                return f'removed leftover {stub_path.name}'
            except OSError:
                return None
    return None


def recover() -> list[str]:
    """Roll back anything left behind by a previous run.

    Called once at startup. Returns notes worth surfacing to the user.
    """
    entries = _read_all()
    if not entries:
        return []

    notes = []
    for entry in entries:
        note = _rollback_one(entry)
        if note:
            notes.append(note)

    _write_all([])
    return notes
