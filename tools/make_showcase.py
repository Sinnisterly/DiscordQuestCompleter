"""Render the Quests page for the README screenshot.

    python tools/make_showcase.py [theme name]

Fills the page with the quests in tools/fixtures/quest_home.json and saves
docs/showcase.png. Runs against a temporary data folder, so your own
settings, quests and themes are not read or changed. Needs a desktop session
(real fonts) and an internet connection for the game artwork.
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'tools' / 'fixtures' / 'quest_home.json'
OUT = ROOT / 'docs' / 'showcase.png'

# Must be set before dqc is imported: appdirs reads it for every path.
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='dqc-showcase-')
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer         # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle       # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from dqc import quests, settings                       # noqa: E402
from dqc.catalog import get_catalog                    # noqa: E402
from dqc.discordui import Node, match_quests, parse_quests  # noqa: E402


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    theme = sys.argv[1] if len(sys.argv) > 1 else 'Midnight'
    settings.set_value('theme', theme)
    settings.set_value('watch_quests', False)   # never read the real Discord

    # Dates in the fixture are relative to the day it was captured. Shift them
    # so the cards show sensible "Ends" labels whenever this runs.
    captured = dt.date(2026, 11, 19)
    shift = dt.date.today() - captured
    catalog = get_catalog()
    scan = parse_quests(Node.from_dict(json.loads(FIXTURE.read_text(encoding='utf-8'))), today=captured)
    for quest in scan.quests:
        if quest.ends:
            quest.ends += shift
        quest.accepted = True   # the usual state once you have picked your quests
    entries, other = match_quests(scan.quests, catalog.exact)
    quests.save_detected(entries, other)
    catalog.apply_quests()

    QQuickStyle.setStyle('Basic')
    qt = QApplication([])
    from dqc.ui.app import App
    app = App(qt)
    app.window.setProperty('width', 1180)
    app.window.setProperty("height", 900)
    app.window.setProperty('currentPage', 0)
    wait(6000)   # artwork downloads

    OUT.parent.mkdir(exist_ok=True)
    if not app.window.grabWindow().save(str(OUT)):
        print('could not save the screenshot')
        return 1
    print(f'saved {OUT}')
    app.art.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
