# Discord Quest Completer

Completes the "play a game" type of Discord quest without installing the game.

![The Quests page, showing quests read from Discord with their orb rewards and end dates](docs/showcase.png)

Discord decides which game you are playing by looking at the executable of each
running process. It keeps a public list of every game it can recognise, and for
most of them it checks the end of the path as well, so `Marvel Rivals` means a
process at `...\MarvelRivals\MarvelRivals_Launcher.exe`. This program builds
that folder structure, puts a small placeholder program at the end of it, and
runs it for as long as you choose. Discord sees the game running and the quest
progresses.

Nothing is downloaded from the game publisher, and none of your real games are
touched.

## Requirements

Windows 10 or later. Steam is not required.

## Getting it

Download `DiscordQuestCompleter.exe` from the
[latest release](../../releases/latest). It is a single file and needs no
installation.

Windows will most likely warn you the first time you run it, with a blue
"Windows protected your PC" box. Choose **More info**, then **Run anyway**.
This happens because the file is not signed with a paid code-signing
certificate, so SmartScreen has no reputation history for it. It is not a
judgement about what the program does, and the warning fades as a release
accumulates downloads. If you would rather not take that on trust, all the
source is here: run it with `python run.py`, or build the executable yourself
with `python build.py` and compare.

To run from source instead:

```
pip install -r requirements.txt
python run.py
```

## Using it

The window has five pages, listed on the left.

**Quests.** Open Discord and click **Quests** in its left sidebar. Back in
this app, press **Detect from Discord**. Every unfinished "play a game"
quest shows up as a card with its reward and end date. Press **Launch** on a
card to run it for the default 15 minutes 30 seconds with the best known
path. **Options** opens the game in the Library page. **Help** shows these
steps in the app.

**Launch all** runs every quest on the page at the same time. Discord
counts several games at once, so they all progress together. Any quest you
have not accepted yet is accepted for you first, as long as Discord's Quests
page is open. Where Discord asks which platform you will play on, Desktop is
picked. Each game runs its own stand-in, since Discord detects each one.
Discord only counts a game that has a window, so each stand-in has a tiny one
parked off-screen, and one countdown window covers the whole group. **Stop all** in that window ends every game
in it. Games that need extra steps, such as a real Steam install, are left
out and named, so you can launch them on their own.

**Library.** Search all 10,000 or so games Discord knows about. The list
opens on the games with community-confirmed paths. Pick one to choose its
executable path, placement and duration, then press **Launch**.

The duration field takes `20m`, `1h30m`, `25:00`, plain seconds like `900`,
and arithmetic like `10 * 60`. Leave it empty for 15 minutes 30 seconds. The
extra 30 seconds covers the time Discord and the stand-in take to sync.

**Sessions.** Running sessions with their progress and a **Stop** button.

**Themes** and **Settings** are covered below.

Each session opens a small countdown window. Leave it open, and check the
quest in Discord after a minute to confirm the progress is moving. The
countdown window carries the game's own icon and name and uses your theme's
colors. This is cosmetic only. Discord identifies a game by its executable
path and never looks at the icon.

Closing the countdown window only minimises it to the taskbar. The session
keeps running, because that window is the process Discord is watching. To end
a session early, press **Stop**, either in the countdown window or on the
Sessions page.

Everything the program created is removed when the session ends, whether it
finishes, you stop it, or the program is killed partway through.

### Running in the background

Closing the main window sends it to the system tray rather than quitting, so
sessions carry on and nothing is lost. The tray icon shows the time remaining,
and its menu reopens the window or quits properly. Quitting does stop running
sessions, and asks first.

When a session ends you get a notification saying whether it ran the full
duration or was stopped early. Both can be turned off on the Settings
page. If your desktop has no system tray, the
window closes normally and the option is disabled.

### If the quest does not progress

Some games accept more than one executable. The **Executable path** dropdown
lists every path known for that game, with community-confirmed ones marked
`[verified]`. Try the next one down.

If that does not help, work down the **Placement** options. They differ only in
where the stand-in is put: `Sandbox` uses the app's own folder and suits most
games, `Steam library` writes into your real `steamapps\common` for games
that check their folder came from Steam, and `Replace install` stands in for
the real executable of a game you have actually installed.

### Games that need the Steam version installed

A few quests, usually demos being promoted, will not register from a sandbox no
matter how correct the path is. These are marked **NEEDS STEAM INSTALL** in the
list.

The reason is in the data. Discord publishes the list of executables it watches
for, and for these titles that list is empty, so the only description of the
game reaches your client with the quest itself. In practice they are credited
only when the game is really installed through Steam. Try the demo first!

What works:

1. Install the game or demo from Steam. It has to finish. Pausing the download
   at one or two percent is **not** enough for these, whatever older guides say.
2. Select the game here. **Replace install** is chosen automatically once the
   install is detected, and the dropdown names the folder it found.
3. Press Launch and leave the countdown running.

While the session runs, the real executable is renamed with a `.dqc-backup`
suffix and the stand-in takes its place. The original is put back the moment the
session ends. If the program is killed partway through, it is restored on the
next launch instead. Steam must not be updating that game at the time, and the
game itself must not be running, or the rename fails. The program says so rather
than leaving anything half-done.

Confirmed working this way: **Shift at Midnight**. Also flagged as needing it:
**Storm Lancers**.

## Where the paths come from

Two sources, combined:

**Discord's detectable application list.** A public endpoint, no account or key
needed, listing every application Discord can recognise along with the
executables it looks for. This is the same data Discord's own client uses, so
it is authoritative rather than a guess. A copy ships inside the program and is
refreshed in the background once a day.

**The r/DiscordQuests path index.** Folder structures that people have
confirmed working. Where a game appears in both, this one wins. It also covers
a handful of games, Comet and Opera GX among them, that Discord lists with no
executables at all, so the community path is the only information there is.

Earlier versions of this program guessed at install paths using the Steam API,
which is why they often pointed at a launcher instead of the game and failed to
be detected. That guesswork is gone.

## What it writes to disk

By default, only inside:

```
%LOCALAPPDATA%\DiscordQuestCompleter\
```

That directory holds the fake game folders while a session runs, the cached
game list, and cached thumbnails. Administrator rights are not needed.

The other two placement modes are the exceptions, and both ask first.
`Steam library` placement creates folders in your real `steamapps\common` and
refuses to run if you already own the game in question. `Replace install`
renames one real executable for the length of the session and puts it back
afterwards.

Every change is written to a journal before it happens, so a crash, a power cut
or a killed process is undone the next time the program starts. A displaced
executable is always restored before anything else is tidied up.

## Finding your quests

The program never asks for your Discord account token. A token grants full
control of the account, and a tool that reads one has no way to prove it is
not stealing it.

Instead it reads the Quests page the same way a screen reader does. Discord's
desktop app exposes what it draws to Windows accessibility (UI Automation),
so when the Quests page is open, every card is there as plain text: "Play
Delta Force for 15 minutes and win 840 Orbs". The program reads the game
name, reward and end date from that text. Nothing is sent anywhere, and no
login is involved.

- **Detect from Discord** on the Quests page reads it once.
- **Watch Discord for quests** in Settings (on by default) checks every 10
  seconds whether the Quests page is open, and reads it when it is, at most
  once a minute. Checking only looks at window titles, so it costs nothing
  while the page is closed.

Once a quest has started, its card also shows the progress Discord reports,
read from the same page, and says when it is done and ready to claim. While
games are running the page is read every 20 seconds so this keeps up.

Each card shows how many orbs the quest pays, and the page header adds up the
orbs on offer. Quests that reward an in-game item instead of orbs name the
item and say "no orbs".

"Play" quests become cards you can launch. A quest for a game on a platform,
such as "Illegal Soccer on Roblox", runs the platform itself, since that is
what Discord counts.

Quests with a **Launch Quest** button in Discord are activities that run
inside Discord, so there is nothing for this app to stand in for. They are
listed under "Do these in Discord" with their orbs, so you can see everything
on offer in one place. Video quests and completed quests are left out.

If a Discord update changes the page, detection finds nothing and says so.
You can still mark quests by hand: pick a game in the Library and press
**Mark quest**. Marked games are kept in `my_quests.json` in the application
data folder.

There is also a shared list, `dqc/data/active_quests.json`, for anyone
maintaining a fork or a group of users. Point its `remote` field at a hosted
copy and the app pulls updates without a new release. It ships empty.

## Themes

The Themes page has six built-in themes: Midnight, Light, OLED Black, Forest,
Ember and Ocean. Click one to switch.

Any color can be changed in the editor below the themes, either by clicking
the swatch or by typing a hex value. Changes show immediately. Press **Save
theme** with a name to keep them. Built-in themes cannot be overwritten, so
save under a new name.

Saved themes are small JSON files in the `themes` folder of the application
data folder. **Export** writes the current theme to a file you can share, and
**Import** adds one.

## Building

```
python tools/build_snapshot.py   # refresh the bundled game list
python tools/make_icon.py        # regenerate the icon, only after changing it
python tools/make_showcase.py    # redraw docs/showcase.png after changing the interface
python build.py                  # produce dist/DiscordQuestCompleter.exe
```

Both data files are committed, so a plain `python build.py` is enough unless
you are changing them. The build stops with an explanation if either is
missing, or if a previous copy of the program is still running and holding its
own executable open.

Two executables are produced. `stub.exe` is the placeholder that gets copied
into the fake game folder, built separately so it stays around 11 MB rather
than carrying the whole interface with it. `DiscordQuestCompleter.exe` bundles
it along with the game data and the QML interface files.

To check a build:

```
dist\DiscordQuestCompleter.exe --self-test
```

This runs a full session without opening the interface and writes the result to
`%LOCALAPPDATA%\DiscordQuestCompleter\selftest.txt`.

## Layout

```
dqc/
  catalog.py    game list, search, community overrides
  discordui.py  reads quests from the Discord window
  emulator.py   builds the folder structure, runs and cleans up the placeholder
  journal.py    records changes before they happen so a crash can be undone
  quests.py     quest sources: detected, shared and marked
  themes.py     theme files: presets, saving, import and export
  settings.py   user preferences
  steamlibs.py  finds Steam libraries, used to avoid games you own
  duration.py   reads the duration field
  thumbs.py     artwork from Steam and Discord, cached to disk
  stub.py       the placeholder program
  ui/           the interface: Python bridge objects and QML pages
tools/          data builder and check scripts
```

The check scripts under `tools/` verify the game list, the catalogue refresh,
quest detection against a saved copy of the Quests page, themes, the
emulation and cleanup cycle, the interface, and that closing the countdown
window leaves the session running. Run them after changing anything.

## Contributing paths

If you find a working path that is not listed, add it to
`dqc/data/overrides.json` and open a pull request. Include the game name
exactly as Discord spells it, which is not always how the wiki spells it, and
note anything unusual about how you confirmed it.

## Credits and licence

This began as a rewrite of
[typedecker/DiscordQuestCompleter](https://github.com/typedecker/DiscordQuestCompleter),
which used Kivy for its interface and guessed install paths from the Steam API.
None of that code is used here. The interface, path resolution, emulation and
cleanup, and packaging are all new, and paths now come from Discord's own
detectable-application list rather than from guesswork.

Released under the GNU General Public License v3, the same licence as the
project it grew out of. See `LICENSE` for the full text.

    Discord Quest Completer
    Copyright (C) 2026 Sinnisterly

    This program is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by the Free
    Software Foundation, either version 3 of the License, or (at your option)
    any later version. It is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

The path index is maintained by the r/DiscordQuests community. Game artwork is
served by Steam and Discord and belongs to the respective publishers.

PySide6 is used under the LGPL v3, which is compatible with this licence.

## Disclaimer

This tool is provided for educational and research purposes.

It is not affiliated with or endorsed by Discord, any game developer, or their
parent companies. Simulating game activity may breach Discord's Terms of
Service, and using it may result in warnings, suspension, or a permanent ban.
The software comes with no warranty of any kind, and the authors accept no
liability for any account loss or other consequence of using it. You are
responsible for your own use of it.

If you do not agree, do not download or run it.
