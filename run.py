"""Entry point.

    python run.py              start the application
    python run.py --self-test  run a headless check and exit

The self-test covers the code paths that only apply to a frozen build, above
all copying the bundled stub into place. A windowed build has no console, so
the report is also written to selftest.txt in the application data directory.
"""

import sys


def self_test() -> int:
    import subprocess
    import time

    from dqc import emulator, journal, quests, thumbs
    from dqc.appdirs import bundled, data_dir, is_frozen
    from dqc.catalog import Catalog, get_catalog
    from dqc.duration import parse_duration

    lines: list[str] = []

    def out(text: str = '') -> None:
        lines.append(text)
        print(text)

    out(f'frozen        : {is_frozen()}')

    stub = bundled('stub.exe')
    out(f'bundled stub  : {stub.is_file()}  ({stub})')

    qml = bundled('ui/qml/Main.qml')
    out(f'interface     : {qml.is_file()}  ({qml})')

    try:
        from dqc import discordui
        discordui._uia()
        uia = True
    except Exception as exc:  # noqa: BLE001 - report whatever went wrong
        uia = False
        out(f'ui automation : failed ({exc})')
    else:
        out('ui automation : True')

    catalog = get_catalog()
    verified = [g for g in catalog.games if g.is_verified]
    out(f'catalogue     : {len(catalog.games)} games, {len(verified)} verified')

    ok = bool(catalog.games) and qml.is_file() and uia
    if ok:
        out(f'duration parse: {parse_duration("15m")}s from "15m"')
        out(f'recovered     : {journal.recover() or "nothing pending"}')

        game = catalog.exact('Where Winds Meet') or verified[0]

        # Marking a quest must survive a catalogue reload.
        was_marked = game.name.lower() in quests.local_load()
        quests.local_set(game.name, True)
        probe = Catalog()
        probe.load()
        marked = bool(probe.exact(game.name) and probe.exact(game.name).has_quest)
        quests.local_set(game.name, was_marked)
        out(f'quest marking : {marked}')

        icon = thumbs.ensure_icon(game)
        out(f'game icon     : {icon is not None} ({icon.name if icon else "none"})')

        plan = emulator.plan_session(game)
        out(f'plan          : {plan.exe_path}')

        session = emulator.Session(plan, seconds=3, icon=icon)
        session.start()
        time.sleep(1.5)

        placed = plan.exe_path.is_file()
        size = plan.exe_path.stat().st_size / 1e6 if placed else 0
        out(f'stub placed   : {placed} ({size:.1f} MB)')
        out(f'process alive : {session.is_running}')

        ok = placed and session.is_running and marked
        session.wait()

        cleaned = not plan.root.exists()
        out(f'cleaned up    : {cleaned}')
        ok = ok and cleaned

        # Stopping must end the whole stand-in. The built stub runs as a
        # launcher plus a child, and ending only the launcher once left the
        # child running with the game's name.
        session = emulator.Session(emulator.plan_session(game), seconds=60, quiet='offscreen')
        session.start()
        time.sleep(2.0)
        session.stop()
        session.wait()
        time.sleep(0.5)
        exe = session.plan.exe_path.name.lower()
        leftover = [
            line for line in subprocess.run(
                ['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            ).stdout.lower().splitlines()
            if line.startswith(f'"{exe}"')
        ]
        stopped = not leftover and not session.plan.root.exists()
        out(f'stop ends all : {stopped}')
        ok = ok and stopped
    else:
        out('catalogue is empty')

    out('')
    out('PASS' if ok else 'FAIL')

    try:
        (data_dir() / 'selftest.txt').write_text('\n'.join(lines), encoding='utf-8')
    except OSError:
        pass
    return 0 if ok else 1


def main() -> int:
    if '--self-test' in sys.argv:
        return self_test()
    try:
        from dqc.ui.app import run
        return run()
    except Exception:
        # A windowed build has no console, so keep the details somewhere.
        import traceback
        from dqc.appdirs import data_dir
        try:
            (data_dir() / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        except OSError:
            pass
        raise


if __name__ == '__main__':
    sys.exit(main())
