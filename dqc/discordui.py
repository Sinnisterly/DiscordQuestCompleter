"""Read the quests shown on the Quests page of the running Discord app.

Discord's quest API needs an account token, which this app never asks for.
The desktop client is a Chromium app, though, and it exposes what it draws
to Windows UI Automation, the interface screen readers use. When the user has
the Quests page open, every quest card is in that tree as plain text: the
game is a link inside "Play <game> for 15 minutes and win ...".

Two layers:

- find_quests_window() and snapshot() talk to Windows. snapshot() copies
  the window's accessibility tree into plain Node objects in one call.
- parse_quests() works only on Node objects, so it can be tested against
  a saved tree without Discord running.

Matching relies on class name prefixes such as "questTile_" and on the shape
of the text, never on the build-specific hash after the underscore, so a
Discord update is less likely to break it. If it does break, the result is
an empty list and a reason, not a crash.
"""

from __future__ import annotations

import ctypes
import datetime as dt
import re
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field

QUESTS_TITLE = 'Quests - Discord'
DISCORD_EXES = {'discord.exe', 'discordptb.exe', 'discordcanary.exe'}

# Chromium builds its accessibility tree on demand. The first request after
# a while returns only the window frame.
MIN_NODES = 50
WAKE_DELAY = 1.5

_CONTROL_TYPES = {
    50000: 'Button', 50002: 'CheckBox', 50003: 'ComboBox', 50004: 'Edit',
    50005: 'Hyperlink', 50006: 'Image', 50007: 'ListItem', 50008: 'List',
    50011: 'MenuItem', 50012: 'ProgressBar', 50013: 'RadioButton', 50019: 'TabItem', 50018: 'Tab',
    50020: 'Text', 50025: 'Custom', 50026: 'Group', 50030: 'Document',
    50032: 'Window', 50033: 'Pane',
}

_ENDS_RE = re.compile(r'^\s*Ends\s+(\d{1,2})/(\d{1,2})\s*$', re.IGNORECASE)
_BALANCE_RE = re.compile(r'orbs balance:\s*([\d,]+)\s*orbs?', re.IGNORECASE)
_PROGRESS_RE = re.compile(r'progress:\s*(\d{1,3})\s*%', re.IGNORECASE)
_MINUTES_RE = re.compile(r'\bfor\s+(\d+)\s+minutes?\b', re.IGNORECASE)
_WIN_RE = re.compile(r'\bwin\s+(.+?)[.!]?\s*$', re.IGNORECASE)
_ORBS_RE = re.compile(r'(\d[\d,]*)\s+orbs?\b', re.IGNORECASE)
_DONE_RE = re.compile(r'^(claim reward|claimed|completed|quest completed)$', re.IGNORECASE)


@dataclass
class Node:
    name: str
    cls: str
    type: str
    children: list['Node'] = field(default_factory=list)

    def walk(self):
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def to_dict(self) -> dict:
        out = {'n': self.name, 'c': self.cls, 't': self.type}
        if self.children:
            out['k'] = [child.to_dict() for child in self.children]
        return out

    @classmethod
    def from_dict(cls, data: dict) -> 'Node':
        return cls(
            name=data.get('n', ''),
            cls=data.get('c', ''),
            type=data.get('t', ''),
            children=[cls.from_dict(k) for k in data.get('k', [])],
        )


ACCEPT_LABEL = 'Accept Quest'

PLAY = 'play'          # "Play <game> for 15 minutes": a running program counts
ACTIVITY = 'activity'  # "Launch Quest": an activity that runs inside Discord


@dataclass
class DetectedQuest:
    title: str                    # card heading, tidied: "Audible's Exoplanet"
    kind: str = PLAY
    heading: str = ''             # card heading exactly as Discord has it
    accepted: bool = False        # no "Accept Quest" button left on the card
    progress: int | None = None   # percent done, from the ring on the card
    game: str = ''                # play quests only, as Discord spells it
    reward: str | None = None     # "840 Orbs", "Weapons Blueprint"
    orbs: int | None = None       # None when the reward is an item, not orbs
    ends: dt.date | None = None
    minutes: int | None = None


@dataclass
class Scan:
    quests: list[DetectedQuest]
    ok: bool                      # False when the page could not be read
    reason: str = ''
    balance: int | None = None    # orbs you hold, from the button at the top


# ------------------------------------------------------------------ parsing

def _infer_year(month: int, day: int, today: dt.date) -> dt.date | None:
    """Cards say "Ends 11/19" with no year. Pick the closest sensible one."""
    for year in (today.year, today.year + 1, today.year - 1):
        try:
            date = dt.date(year, month, day)
        except ValueError:
            return None
        if abs((date - today).days) <= 183:
            return date
    return None


def _play_link(tile: Node) -> tuple[str, str] | None:
    """Find "Play " + link + " for N minutes ..." and return (game, rest)."""
    for node in tile.walk():
        kids = node.children
        for i in range(len(kids) - 1):
            first, link = kids[i], kids[i + 1]
            if (
                first.type == 'Text'
                and first.name.strip().lower() == 'play'
                and link.type == 'Hyperlink'
                and link.name.strip()
            ):
                rest = kids[i + 2].name if i + 2 < len(kids) else ''
                return link.name.strip(), rest
    return None


def _claim_text(tile: Node) -> str | None:
    """The reward in the card header: "Claim " followed by "840 Orbs"."""
    for node in tile.walk():
        kids = node.children
        for i in range(len(kids) - 1):
            if kids[i].type == 'Text' and kids[i].name.strip().lower() == 'claim':
                text = kids[i + 1].name.strip()
                if text:
                    return text
    return None


def _tidy_reward(text: str) -> str:
    text = re.sub(r'^(a|an)\s+', '', text.strip().rstrip('.!'), flags=re.IGNORECASE)
    return text[:1].upper() + text[1:]


def _tidy_title(heading: str) -> str:
    """"AUDIBLE'S EXOPLANET QUEST" -> "Audible's Exoplanet"."""
    text = re.sub(r'\s+quest$', '', heading.strip(), flags=re.IGNORECASE)
    words = []
    for word in text.split():
        # Leave short all-caps tokens with digits alone ("V4.7", "2099").
        words.append(word if any(c.isdigit() for c in word) else word[:1].upper() + word[1:].lower())
    return ' '.join(words)


def _parse_tile(tile: Node, today: dt.date) -> DetectedQuest | None:
    buttons = [n.name.strip() for n in tile.walk() if n.type == 'Button']
    if any(_DONE_RE.match(b) for b in buttons):
        return None  # already completed

    found = _play_link(tile)
    if found is not None:
        kind, (game, rest) = PLAY, found
    elif any(b.lower() == 'launch quest' for b in buttons):
        kind, game, rest = ACTIVITY, '', ''
    else:
        return None  # a video quest, watched inside Discord

    ends = None
    progress = None
    for node in tile.walk():
        match = _ENDS_RE.match(node.name)
        if match and ends is None:
            ends = _infer_year(int(match.group(1)), int(match.group(2)), today)
        # The ring around the reward icon: "Quest progress: 52%". Discord
        # only draws it once the quest has started.
        match = _PROGRESS_RE.search(node.name)
        if match and progress is None:
            progress = max(0, min(100, int(match.group(1))))

    minutes = None
    match = _MINUTES_RE.search(rest)
    if match:
        minutes = int(match.group(1))

    # The header is the reward as Discord labels it. The description
    # ("... and win 840 Orbs.") is the fallback if the header is missing.
    reward = _claim_text(tile)
    if reward is None:
        match = _WIN_RE.search(rest)
        reward = match.group(1) if match else None
    reward = _tidy_reward(reward) if reward else None

    orbs = None
    match = _ORBS_RE.search(reward or '')
    if match:
        orbs = int(match.group(1).replace(',', ''))

    return DetectedQuest(
        title=_tidy_title(tile.name) or game, kind=kind, game=game,
        heading=tile.name,
        progress=progress,
        accepted=not any(b.lower() == ACCEPT_LABEL.lower() for b in buttons),
        reward=reward, orbs=orbs, ends=ends, minutes=minutes,
    )


def _claimed_tab_selected(root: Node) -> bool:
    for node in root.walk():
        if node.name.strip().lower() == 'claimed quests' and 'selected_' in node.cls:
            return True
    return False


def parse_quests(root: Node, today: dt.date | None = None) -> Scan:
    """Unfinished play and activity quests on the page.

    Video quests are left out: they are watched inside Discord and there is
    nothing for this app to show or do about them.
    """
    today = today or dt.date.today()
    if _claimed_tab_selected(root):
        return Scan([], ok=False, reason='Discord is showing Claimed Quests. Switch to All Quests.')

    tiles = [n for n in root.walk() if 'questTile_' in n.cls]
    if not tiles:
        return Scan([], ok=False, reason='No quest cards found on the page.')

    out: list[DetectedQuest] = []
    seen: set[str] = set()
    for tile in tiles:
        quest = _parse_tile(tile, today)
        if quest is None:
            continue
        key = (quest.game or quest.title).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(quest)
    return Scan(out, ok=True, balance=_balance(root))


def _balance(root: Node) -> int | None:
    """The orb balance from the button at the top of the Quests page,
    named like "Orbs balance: 460 orbs, new Orb challenge updates"."""
    for node in root.walk():
        match = _BALANCE_RE.search(node.name)
        if match:
            return int(match.group(1).replace(',', ''))
    return None


# ------------------------------------------------------------------ matching

_ON_PLATFORM_RE = re.compile(r'^(.+?)\s+on\s+(.+)$', re.IGNORECASE)

ACTIVITY_REASON = 'Runs inside Discord. Press Launch Quest on the card in Discord.'


def match_quests(found: list[DetectedQuest], exact) -> tuple[list[dict], list[dict]]:
    """Split detected quests into ones this app can run and ones it cannot.

    exact(name) returns the catalogue game for a name, or None. A quest such
    as "Illegal Soccer on Roblox" is credited for running the platform, so
    when the full name is unknown but the part after "on" is a known game,
    that game is used and the quest name is kept as the card title.

    Returns (entries, other) in the shapes quests.save_detected() takes.
    """
    entries, other, used = [], [], set()
    for quest in found:
        common = {
            'reward': quest.reward,
            'orbs': quest.orbs,
            'until': quest.ends.isoformat() if quest.ends else None,
            'accepted': quest.accepted,
            'heading': quest.heading,
            'progress': quest.progress,
        }
        if quest.kind == ACTIVITY:
            other.append({'title': quest.title, 'reason': ACTIVITY_REASON, **common})
            continue

        game, title = exact(quest.game), None
        if game is None:
            match = _ON_PLATFORM_RE.match(quest.game)
            if match and exact(match.group(2)) is not None:
                game, title = exact(match.group(2)), quest.game
        if game is None or game.name.lower() in used:
            other.append({
                'title': quest.game,
                'reason': f'{quest.game} is not in Discord\'s list of detectable games, '
                          'so this app cannot stand in for it.' if game is None
                          else f'Shares {game.name} with another quest above.',
                **common,
            })
            continue
        used.add(game.name.lower())
        entries.append({'name': game.name, 'title': title, **common})
    return entries, other


# ------------------------------------------------------------------ Windows

def _process_name(pid: int) -> str:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ''
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit('\\', 1)[-1].lower()
        return ''
    finally:
        kernel32.CloseHandle(handle)


def find_quests_window() -> int | None:
    """Handle of a Discord window showing the Quests page, or None.

    Only reads window titles, so it is cheap enough to poll.
    """
    if sys.platform != 'win32':
        return None
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length != len(QUESTS_TITLE):
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value != QUESTS_TITLE:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _process_name(pid.value) in DISCORD_EXES:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def _uia():
    """The UI Automation client, created for the calling thread."""
    import comtypes.client
    comtypes.client.GetModule('UIAutomationCore.dll')
    from comtypes.gen import UIAutomationClient as UIA
    automation = comtypes.client.CreateObject(
        UIA.CUIAutomation, interface=UIA.IUIAutomation,
    )
    return UIA, automation


def _copy(element, UIA) -> Node:
    """Convert a cached UIA element and its cached subtree into Nodes."""
    try:
        type_id = element.CachedControlType
    except Exception:  # noqa: BLE001 - COM raises assorted errors
        type_id = 0
    node = Node(
        name=(element.CachedName or ''),
        cls=(element.CachedClassName or ''),
        type=_CONTROL_TYPES.get(type_id, str(type_id)),
    )
    try:
        kids = element.GetCachedChildren()
    except Exception:  # noqa: BLE001
        kids = None
    if kids:  # a NULL pointer when the element has no children
        for i in range(kids.Length):
            node.children.append(_copy(kids.GetElement(i), UIA))
    return node


def _count(node: Node) -> int:
    return sum(1 for _ in node.walk())


def snapshot(hwnd: int) -> Node:
    """Copy the window's accessibility tree in one cross-process call."""
    import comtypes
    comtypes.CoInitialize()
    try:
        UIA, automation = _uia()
        request = automation.CreateCacheRequest()
        for prop in (
            UIA.UIA_NamePropertyId,
            UIA.UIA_ClassNamePropertyId,
            UIA.UIA_ControlTypePropertyId,
        ):
            request.AddProperty(prop)
        request.TreeScope = UIA.TreeScope_Subtree
        request.TreeFilter = automation.RawViewCondition
        request.AutomationElementMode = UIA.AutomationElementMode_None

        root = _copy(automation.ElementFromHandleBuildCache(hwnd, request), UIA)
        if _count(root) < MIN_NODES:
            time.sleep(WAKE_DELAY)
            root = _copy(automation.ElementFromHandleBuildCache(hwnd, request), UIA)
        return root
    finally:
        comtypes.CoUninitialize()


PLATFORM_CHOICE = 'Desktop'
# Buttons that close the platform picker once Desktop is chosen.
_CONFIRM_LABELS = {'accept quest', 'confirm', 'continue', 'accept', 'done', 'save'}
# Control types a picker option may use: menu item, radio, list item, button, custom.
_OPTION_TYPES = {50011, 50013, 50007, 50000, 50025}


def _tile_of(element, walker):
    """The quest card an element sits in, or None outside every card."""
    node = walker.GetParentElement(element)
    while node and 'questTile_' not in (node.CurrentClassName or ''):
        node = walker.GetParentElement(node)
    return node or None


def _press(element, UIA) -> bool:
    """Click an element the way a screen reader does. True if it worked."""
    for pattern_id, interface, action in (
        (UIA.UIA_InvokePatternId, UIA.IUIAutomationInvokePattern, 'Invoke'),
        (UIA.UIA_SelectionItemPatternId, UIA.IUIAutomationSelectionItemPattern, 'Select'),
        (UIA.UIA_LegacyIAccessiblePatternId, UIA.IUIAutomationLegacyIAccessiblePattern, 'DoDefaultAction'),
    ):
        try:
            pattern = element.GetCurrentPattern(pattern_id)
            if pattern:
                getattr(pattern.QueryInterface(interface), action)()
                return True
        except Exception:  # noqa: BLE001 - try the next way of pressing it
            continue
    return False


def _outside_tiles(window, automation, UIA, walker, names: set[str]) -> list:
    """Elements with one of these names (any case) that are not in a card."""
    conditions = [
        automation.CreatePropertyConditionEx(
            UIA.UIA_NamePropertyId, name, UIA.PropertyConditionFlags_IgnoreCase)
        for name in sorted(names)
    ]
    condition = conditions[0]
    for extra in conditions[1:]:
        condition = automation.CreateOrCondition(condition, extra)
    found = window.FindAll(UIA.TreeScope_Descendants, condition)
    out = []
    for i in range(found.Length if found else 0):
        element = found.GetElement(i)
        if _tile_of(element, walker) is None:
            out.append(element)
    return out


def _choose_platform(window, automation, UIA, walker) -> str:
    """Answer the platform picker some quests show after Accept Quest.

    Returns 'none' when no picker appeared (Roblox quests, for example),
    'chosen' when Desktop was picked, or 'stuck' when a picker seems open
    but could not be answered.
    """
    time.sleep(0.8)
    options = [
        e for e in _outside_tiles(window, automation, UIA, walker, {PLATFORM_CHOICE.lower()})
        if e.CurrentControlType in _OPTION_TYPES
    ]
    if not options:
        return 'none'
    if not _press(options[0], UIA):
        return 'stuck'
    time.sleep(0.5)
    for button in _outside_tiles(window, automation, UIA, walker, _CONFIRM_LABELS):
        if button.CurrentControlType == 50000 and _press(button, UIA):
            break
    time.sleep(0.6)
    return 'chosen'


def accept_quests(headings: set[str]) -> dict[str, str]:
    """Press Accept Quest on the cards with these headings.

    This is the same as clicking the button in Discord. It works through
    UI Automation, which screen readers use, so the window does not need to
    be in front and the mouse is not moved. Where Discord then asks which
    platform you will play on, Desktop is picked.

    Returns {heading: outcome}, where outcome is 'accepted', 'chosen'
    (accepted after picking Desktop) or 'stuck'. Check the result with a
    fresh scan(). Safe to call off the UI thread.
    """
    hwnd = find_quests_window()
    if hwnd is None or not headings:
        return {}
    import comtypes
    comtypes.CoInitialize()
    results: dict[str, str] = {}
    try:
        UIA, automation = _uia()
        window = automation.ElementFromHandle(hwnd)
        walker = automation.RawViewWalker
        wanted = automation.CreateAndCondition(
            automation.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50000),
            automation.CreatePropertyCondition(UIA.UIA_NamePropertyId, ACCEPT_LABEL),
        )
        # Press one card at a time and look again, since the page redraws.
        for heading in sorted(headings):
            found = window.FindAll(UIA.TreeScope_Descendants, wanted)
            for i in range(found.Length if found else 0):
                button = found.GetElement(i)
                tile = _tile_of(button, walker)
                if tile is None or tile.CurrentName != heading:
                    continue
                if not _press(button, UIA):
                    results[heading] = 'stuck'
                    break
                picked = _choose_platform(window, automation, UIA, walker)
                results[heading] = {'none': 'accepted'}.get(picked, picked)
                break
    finally:
        comtypes.CoUninitialize()
    return results


_PLATFORM_WORDS = {'desktop', 'console', 'mobile', 'pc', 'xbox', 'playstation'}


def save_debug_popup() -> None:
    """Record the platform picker's layout when accepting got stuck.

    Only the part of the window around a platform option, outside the quest
    cards, is saved, so nothing else from Discord ends up in the file. It
    goes to accept_debug.json in the app data folder, to fix the matching.
    """
    hwnd = find_quests_window()
    if hwnd is None:
        return
    try:
        root = snapshot(hwnd)
    except Exception:  # noqa: BLE001 - debugging aid only
        return

    parents: dict[int, Node] = {}
    for node in root.walk():
        for child in node.children:
            parents[id(child)] = node

    def in_tile(node: Node) -> bool:
        while node is not None:
            if 'questTile_' in node.cls:
                return True
            node = parents.get(id(node))
        return False

    found = []
    for node in root.walk():
        if node.name.strip().lower() in _PLATFORM_WORDS and not in_tile(node):
            area = node
            for _ in range(3):
                area = parents.get(id(area), area)
            found.append(area.to_dict())
    from .appdirs import data_dir
    import json
    try:
        (data_dir() / 'accept_debug.json').write_text(json.dumps(found, indent=1), encoding='utf-8')
    except OSError:
        pass


def scan() -> Scan:
    """Find the Quests page and read it. Safe to call off the UI thread."""
    hwnd = find_quests_window()
    if hwnd is None:
        return Scan([], ok=False, reason="Open the Quests page in Discord and try again.")
    try:
        root = snapshot(hwnd)
    except Exception as exc:  # noqa: BLE001 - COM and ctypes errors vary
        return Scan([], ok=False, reason=f'Could not read the Discord window: {exc}')
    return parse_quests(root)
