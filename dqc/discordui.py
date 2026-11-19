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
# A finished quest waiting to be claimed, and one already claimed.
_DONE_RE = re.compile(r'^(claim reward|claim|completed|quest completed)$', re.IGNORECASE)
_CLAIMED_RE = re.compile(r'^(claimed|reward claimed)$', re.IGNORECASE)


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
    platform: str | None = None   # what the card's platform dropdown says
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
    if any(_CLAIMED_RE.match(b) for b in buttons):
        return None  # claimed: nothing left to do or tell
    finished = any(_DONE_RE.match(b) for b in buttons)

    found = _play_link(tile)
    if found is not None:
        kind, (game, rest) = PLAY, found
    elif any(b.lower() == 'launch quest' for b in buttons):
        kind, game, rest = ACTIVITY, '', ''
    else:
        return None  # a video quest, watched inside Discord

    ends = None
    progress = None
    platform = None
    for node in tile.walk():
        match = _ENDS_RE.match(node.name)
        if match and ends is None:
            ends = _infer_year(int(match.group(1)), int(match.group(2)), today)
        # The ring around the reward icon: "Quest progress: 52%". Discord
        # only draws it once the quest has started.
        match = _PROGRESS_RE.search(node.name)
        if match and progress is None:
            progress = max(0, min(100, int(match.group(1))))
        # An accepted quest is tracked on one platform, chosen in a dropdown
        # on the card. Only Desktop counts a program running on this PC.
        if node.type == 'Button' and PLATFORM_CLASS in node.cls and platform is None:
            platform = node.name.strip() or None

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
        progress=100 if finished else progress,
        platform=platform,
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
            'platform': quest.platform,
            'minutes': quest.minutes,
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
# Class name prefix of the platform dropdown on an accepted card. Its name is
# the platform the quest is tracked on: "Desktop", "Xbox", "PlayStation".
PLATFORM_CLASS = 'platformSelector'
# Buttons that close a platform popup once Desktop is chosen.
_CONFIRM_LABELS = {'accept quest', 'confirm', 'continue', 'accept', 'done', 'save'}
# Control types a platform option may use: menu item, radio, list item,
# button, custom.
_OPTION_TYPES = {50011, 50013, 50007, 50000, 50025}
# The same, minus Button: inside a card, a button named Desktop is the
# dropdown itself, not an option in its list.
_LIST_OPTION_TYPES = {50011, 50013, 50007, 50025}


def _wait_for(check, timeout: float = 3.0, step: float = 0.2):
    """Poll until check() returns something truthy, or time runs out.

    Waiting for the change itself, rather than sleeping a fixed time, keeps
    this working on a slow machine or while Discord is busy.
    """
    end = time.monotonic() + timeout
    while True:
        try:
            value = check()
        except Exception:  # noqa: BLE001 - the page may be redrawing
            value = None
        if value or time.monotonic() >= end:
            return value
        time.sleep(step)


def _tile_of(element, walker):
    """The quest card an element sits in, or None outside every card."""
    node = walker.GetParentElement(element)
    while node and 'questTile_' not in (node.CurrentClassName or ''):
        node = walker.GetParentElement(node)
    return node or None


def _press(element, UIA, expand: bool = False) -> bool:
    """Click an element the way a screen reader does. True if it worked.

    expand opens a dropdown instead of clicking it, where it supports that.
    """
    ways = []
    if expand:
        ways.append((UIA.UIA_ExpandCollapsePatternId, UIA.IUIAutomationExpandCollapsePattern, 'Expand'))
    ways += [
        (UIA.UIA_InvokePatternId, UIA.IUIAutomationInvokePattern, 'Invoke'),
        (UIA.UIA_LegacyIAccessiblePatternId, UIA.IUIAutomationLegacyIAccessiblePattern, 'DoDefaultAction'),
        (UIA.UIA_SelectionItemPatternId, UIA.IUIAutomationSelectionItemPattern, 'Select'),
    ]
    for pattern_id, interface, action in ways:
        try:
            pattern = element.GetCurrentPattern(pattern_id)
            if pattern:
                getattr(pattern.QueryInterface(interface), action)()
                return True
        except Exception:  # noqa: BLE001 - try the next way of pressing it
            continue
    return False


def _named(root, automation, UIA, names: set[str]) -> list:
    """Elements under root with one of these names, ignoring case."""
    conditions = [
        automation.CreatePropertyConditionEx(
            UIA.UIA_NamePropertyId, name, UIA.PropertyConditionFlags_IgnoreCase)
        for name in sorted(names)
    ]
    condition = conditions[0]
    for extra in conditions[1:]:
        condition = automation.CreateOrCondition(condition, extra)
    found = root.FindAll(UIA.TreeScope_Descendants, condition)
    return [found.GetElement(i) for i in range(found.Length if found else 0)]


def _outside_tiles(window, automation, UIA, walker, names: set[str]) -> list:
    """Elements with one of these names that are not in any quest card."""
    return [e for e in _named(window, automation, UIA, names) if _tile_of(e, walker) is None]


def _find_tile(window, automation, UIA, heading: str):
    """The quest card with this heading, found fresh since cards redraw."""
    for element in _named(window, automation, UIA, {heading}):
        if 'questTile_' in (element.CurrentClassName or ''):
            return element
    return None


def _platform_dropdown(tile, automation, UIA):
    is_button = automation.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50000)
    found = tile.FindAll(UIA.TreeScope_Descendants, is_button)
    for i in range(found.Length if found else 0):
        button = found.GetElement(i)
        if PLATFORM_CLASS in (button.CurrentClassName or ''):
            return button
    return None


def _answer_popup(window, automation, UIA, walker) -> bool:
    """Pick Desktop in a platform popup, if one opened after Accept Quest."""
    options = _wait_for(lambda: [
        e for e in _outside_tiles(window, automation, UIA, walker, {PLATFORM_CHOICE.lower()})
        if e.CurrentControlType in _OPTION_TYPES
    ], timeout=1.5)
    if not options or not _press(options[0], UIA):
        return False
    time.sleep(0.4)
    for button in _outside_tiles(window, automation, UIA, walker, _CONFIRM_LABELS):
        if button.CurrentControlType == 50000 and _press(button, UIA):
            break
    return True


def _set_desktop(window, automation, UIA, walker, heading: str) -> str:
    """Set a card's platform dropdown to Desktop.

    Returns 'none' (the card has no dropdown, as with Roblox quests),
    'already' (it says Desktop), 'set' (changed and confirmed) or 'stuck'.
    """
    def current():
        tile = _find_tile(window, automation, UIA, heading)
        dropdown = _platform_dropdown(tile, automation, UIA) if tile else None
        return tile, dropdown

    tile, dropdown = current()
    if dropdown is None:
        return 'none'
    if (dropdown.CurrentName or '').strip().lower() == PLATFORM_CHOICE.lower():
        return 'already'

    for _attempt in range(2):
        tile, dropdown = current()
        if dropdown is None or not _press(dropdown, UIA, expand=True):
            continue

        # The list may open in a popup layer or inside the card.
        def option():
            outside = [
                e for e in _outside_tiles(window, automation, UIA, walker, {PLATFORM_CHOICE.lower()})
                if e.CurrentControlType in _OPTION_TYPES
            ]
            inside = [
                e for e in _named(tile, automation, UIA, {PLATFORM_CHOICE.lower()})
                if e.CurrentControlType in _LIST_OPTION_TYPES
            ] if tile else []
            return outside or inside

        choices = _wait_for(option, timeout=3.0)
        if not choices or not _press(choices[0], UIA):
            continue

        def confirmed():
            _tile, now = current()
            return now is not None and (now.CurrentName or '').strip().lower() == PLATFORM_CHOICE.lower()

        if _wait_for(confirmed, timeout=3.0):
            return 'set'
    return 'stuck'


def prepare_quests(accept: set[str], desktop: set[str]) -> dict[str, str]:
    """Accept quests and make sure they are tracked on Desktop.

    accept: card headings to press Accept Quest on.
    desktop: card headings whose platform dropdown should say Desktop. Every
    quest in accept is checked too, since accepting can set another platform.

    This is the same as clicking in Discord. It works through UI Automation,
    which screen readers use, so the window does not need to be in front and
    the mouse is not moved. Returns {heading: outcome}, where outcome is
    'ok' or 'stuck'. Confirm with a fresh scan(). Safe off the UI thread.
    """
    hwnd = find_quests_window()
    if hwnd is None or not (accept or desktop):
        return {}
    import comtypes
    comtypes.CoInitialize()
    results: dict[str, str] = {}
    try:
        UIA, automation = _uia()
        window = automation.ElementFromHandle(hwnd)
        walker = automation.RawViewWalker

        for heading in sorted(accept):
            tile = _find_tile(window, automation, UIA, heading)
            buttons = [
                b for b in (_named(tile, automation, UIA, {ACCEPT_LABEL}) if tile else [])
                if b.CurrentControlType == 50000
            ]
            if not buttons or not _press(buttons[0], UIA):
                results[heading] = 'stuck'
                continue

            def accepted(heading=heading):
                card = _find_tile(window, automation, UIA, heading)
                return card is not None and not any(
                    b.CurrentControlType == 50000
                    for b in _named(card, automation, UIA, {ACCEPT_LABEL}))

            if not _wait_for(accepted, timeout=4.0):
                # Some quests ask for a platform in a popup before they count.
                _answer_popup(window, automation, UIA, walker)
                if not _wait_for(accepted, timeout=3.0):
                    results[heading] = 'stuck'
                    continue
            results[heading] = 'ok'

        for heading in sorted(desktop | {h for h, r in results.items() if r == 'ok'}):
            if _set_desktop(window, automation, UIA, walker, heading) == 'stuck':
                results[heading] = 'stuck'
            else:
                results.setdefault(heading, 'ok')
    finally:
        comtypes.CoUninitialize()

    stuck = {h for h, r in results.items() if r == 'stuck'}
    if stuck:
        save_debug(stuck)
    return results


_PLATFORM_WORDS = {'desktop', 'console', 'mobile', 'pc', 'xbox', 'playstation'}


def save_debug(headings: set[str]) -> None:
    """Record what the platform controls looked like when setting one failed.

    Saves the quest cards in question and any platform options outside the
    cards, and nothing else from Discord. It goes to accept_debug.json in
    the app data folder, to fix the matching.
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

    found = {'cards': [], 'popups': []}
    for node in root.walk():
        if 'questTile_' in node.cls and node.name in headings:
            found['cards'].append(node.to_dict())
        elif node.name.strip().lower() in _PLATFORM_WORDS and not in_tile(node):
            area = node
            for _ in range(3):
                area = parents.get(id(area), area)
            found['popups'].append(area.to_dict())
    from .appdirs import data_dir
    import json
    try:
        (data_dir() / 'accept_debug.json').write_text(json.dumps(found, indent=1), encoding='utf-8')
    except OSError:
        pass


# ------------------------------------------------------------------ background check
#
# Discord only draws the Quests page while its window is on screen, and a
# background app can only get it there by bringing it to the front. So the
# background check opens the page, reads it, goes back to where Discord was,
# and hands focus back, and only does this while the user is away.

IDLE_SECONDS = 5 * 60


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]


def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input anywhere."""
    info = _LASTINPUTINFO(cbSize=ctypes.sizeof(_LASTINPUTINFO))
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0


def _fullscreen_in_front() -> bool:
    """A game or video filling its screen is in front."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd in (user32.GetDesktopWindow(), user32.GetShellWindow()):
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False

    class MONITORINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

    monitor = user32.MonitorFromWindow(hwnd, 2)  # nearest
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    screen = info.rcMonitor
    return (rect.left <= screen.left and rect.top <= screen.top
            and rect.right >= screen.right and rect.bottom >= screen.bottom)


def discord_window() -> int | None:
    """Handle of Discord's main window, whatever page it shows."""
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if not buf.value.endswith('Discord'):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _process_name(pid.value) in DISCORD_EXES and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def background_blocker() -> str:
    """Why a background check cannot run now, or '' if it can."""
    if sys.platform != 'win32':
        return 'Windows only'
    user32 = ctypes.windll.user32
    hwnd = discord_window()
    if hwnd is None:
        return 'Discord is not open'
    if user32.IsIconic(hwnd):
        return 'Discord is minimized'
    if user32.GetForegroundWindow() == hwnd:
        return 'Discord is in use'
    if idle_seconds() < IDLE_SECONDS:
        return 'you are using the PC'
    if _fullscreen_in_front():
        return 'a fullscreen app is in front'
    return ''


def _give_focus_back(hwnd) -> None:
    """Put a window back in front. Windows only allows this from the thread
    that has input, so join that thread for a moment."""
    user32 = ctypes.windll.user32
    if not hwnd or user32.GetForegroundWindow() == hwnd:
        return
    foreground = user32.GetForegroundWindow()
    theirs = user32.GetWindowThreadProcessId(foreground, None)
    mine = ctypes.windll.kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(mine, theirs, True)
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    finally:
        user32.AttachThreadInput(mine, theirs, False)


def _selected_link(window, automation, UIA, walker):
    """The sidebar link for the page Discord shows now, to come back to."""
    links = window.FindAll(UIA.TreeScope_Descendants, automation.CreatePropertyCondition(
        UIA.UIA_ControlTypePropertyId, 50005))
    for i in range(links.Length if links else 0):
        link = links.GetElement(i)
        parent = walker.GetParentElement(link)
        classes = (link.CurrentClassName or '') + ' ' + ((parent.CurrentClassName or '') if parent else '')
        if 'selected' in classes.lower():
            return link
    return None


def background_scan() -> Scan:
    """Open Discord's Quests page, read it, and put everything back.

    Call only when background_blocker() returns ''. Discord comes to the
    front for about a second, then the page it was on and the window you
    were in are restored. Safe to call off the UI thread.
    """
    hwnd = discord_window()
    if hwnd is None:
        return Scan([], ok=False, reason='Discord is not open.')
    if find_quests_window() is not None:
        return scan()   # already on the page: nothing to open or undo

    import comtypes
    comtypes.CoInitialize()
    user32 = ctypes.windll.user32
    previous = user32.GetForegroundWindow()
    try:
        UIA, automation = _uia()
        window = automation.ElementFromHandle(hwnd)
        walker = automation.RawViewWalker
        back_to = _wait_for(lambda: _selected_link(window, automation, UIA, walker), timeout=3.0)
        links = [e for e in _named(window, automation, UIA, {'quests'})
                 if e.CurrentControlType == 50005]   # hyperlink
        if not links or not _press(links[0], UIA):
            return Scan([], ok=False, reason='Could not find the Quests link in Discord.')
        try:
            if not _wait_for(find_quests_window, timeout=8.0):
                return Scan([], ok=False, reason='The Quests page did not open.')
            result = _wait_for(lambda: (lambda s: s if s.ok else None)(scan()), timeout=15.0, step=0.5)
            return result or Scan([], ok=False, reason='The Quests page did not finish loading.')
        finally:
            # Always try to leave Discord as it was, even after a failure.
            if back_to is not None:
                _press(back_to, UIA)
                _wait_for(lambda: find_quests_window() is None, timeout=5.0)
            _give_focus_back(previous)
    except Exception as exc:  # noqa: BLE001 - COM errors vary; report, never crash
        _give_focus_back(previous)
        return Scan([], ok=False, reason=f'Could not read Discord: {exc}')
    finally:
        comtypes.CoUninitialize()


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
