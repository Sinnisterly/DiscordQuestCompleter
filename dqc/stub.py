"""The stand-in process.

This file is copied to the emulated path and renamed to the game's executable,
so it is what Discord sees running. It uses only the standard library (tkinter)
to keep the frozen build small and its startup fast.

    stub.exe <seconds> [window title] [icon png]
    stub.exe --group <seconds>          (game names in DQC_STUB_GROUP)

Draws a small always-on-top window with a countdown. Stop ends the session
early; the parent app notices the exit and cleans up. With DQC_STUB_QUIET set
it keeps a window Discord can see but out of your way, for games launched as
a group, and --group draws the one shared countdown for that group.
"""

import ctypes
import json
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

BG = '#1b1d24'
SURFACE = '#2a2d36'
BORDER = '#3a3e4a'
FG = '#e6e8ee'
MUTED = '#8b90a0'
ACCENT = '#5865f2'

# Matches dqc.duration.DEFAULT_SECONDS. This file is built as a standalone
# executable and cannot import from the package.
DEFAULT_SECONDS = 930


def _apply_theme() -> None:
    """Use the main app's theme colors when it passes them.

    They arrive as JSON in the DQC_STUB_THEME environment variable. Anything
    missing or malformed keeps the built-in palette.
    """
    global BG, SURFACE, BORDER, FG, MUTED, ACCENT
    try:
        colors = json.loads(os.environ.get('DQC_STUB_THEME') or '{}')
    except ValueError:
        return
    if not isinstance(colors, dict):
        return

    def pick(key, current):
        value = colors.get(key)
        if isinstance(value, str) and len(value) == 7 and value.startswith('#'):
            return value
        return current

    BG = pick('bg', BG)
    SURFACE = pick('surfaceHi', SURFACE)
    BORDER = pick('border', BORDER)
    FG = pick('text', FG)
    MUTED = pick('muted', MUTED)
    ACCENT = pick('accent', ACCENT)


def dark_titlebar(root: tk.Tk) -> bool:
    """Ask the desktop window manager to draw a dark title bar.

    This file is built as a standalone executable, so it cannot import the
    copy of this in dqc.winchrome. Fails quietly on anything but Windows.
    """
    if sys.platform != 'win32':
        return False
    try:
        root.update_idletasks()
        # winfo_id() gives the Tk child window; the frame above it is the one
        # the window manager decorates.
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        for attribute in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE, old and new
            value = ctypes.c_int(1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_int(attribute),
                ctypes.byref(value), ctypes.sizeof(value),
            ) == 0:
                # The title bar only repaints once the window is remapped.
                root.withdraw()
                root.deiconify()
                return True
    except (AttributeError, OSError, tk.TclError):
        pass
    return False


def human(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


class Stub:
    def __init__(
        self, total: int, title: str, icon_path: str | None = None,
        subtitle: str = 'Emulating game activity for Discord', stop_text: str = 'Stop',
    ):
        self.total = max(1, total)
        self.started = time.monotonic()
        # Tk drops images that are not referenced from Python.
        self.icon = None
        self.icon_small = None

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        # The close button minimises rather than quits. Ending the process here
        # would end the emulation, and the window being in the way is not a
        # reason to abandon the session. Stop is explicit instead.
        self.root.protocol('WM_DELETE_WINDOW', self.hide)

        frame = tk.Frame(self.root, bg=BG, padx=26, pady=22)
        frame.pack(fill='both', expand=True)

        self._load_icon(icon_path)

        header = tk.Frame(frame, bg=BG)
        header.pack(fill='x', pady=(0, 16))

        if self.icon_small is not None:
            tk.Label(header, image=self.icon_small, bg=BG).pack(
                side='left', padx=(0, 12),
            )

        titles = tk.Frame(header, bg=BG)
        titles.pack(side='left', fill='x', expand=True)

        tk.Label(
            titles, text=title, bg=BG, fg=FG,
            font=('Segoe UI Semibold', 13), anchor='w',
        ).pack(fill='x')

        tk.Label(
            titles, text=subtitle,
            bg=BG, fg=MUTED, font=('Segoe UI', 9), anchor='w', justify='left',
            wraplength=320,
        ).pack(fill='x', pady=(2, 0))

        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure(
            'Stub.Horizontal.TProgressbar',
            troughcolor=SURFACE, background=ACCENT,
            bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT,
            thickness=8,
        )

        self.bar = ttk.Progressbar(
            frame, style='Stub.Horizontal.TProgressbar',
            maximum=self.total, length=340,
        )
        self.bar.pack(fill='x')

        row = tk.Frame(frame, bg=BG)
        row.pack(fill='x', pady=(10, 0))
        self.pct = tk.Label(row, text='0%', bg=BG, fg=FG, font=('Segoe UI', 10))
        self.pct.pack(side='left')
        self.remaining = tk.Label(
            row, text=human(self.total) + ' left', bg=BG, fg=MUTED,
            font=('Segoe UI', 10),
        )
        self.remaining.pack(side='right')

        footer = tk.Frame(frame, bg=BG)
        footer.pack(fill='x', pady=(14, 0))

        tk.Label(
            footer, text='Closing this window only hides it.',
            bg=BG, fg=MUTED, font=('Segoe UI', 8), anchor='w',
        ).pack(side='left')

        tk.Button(
            footer, text=stop_text, command=self.stop,
            bg=SURFACE, fg=FG, activebackground=BORDER, activeforeground=FG,
            relief='flat', borderwidth=0, padx=14, pady=3,
            font=('Segoe UI', 9), cursor='hand2',
        ).pack(side='right')

        self.root.update_idletasks()
        dark_titlebar(self.root)
        self._centre()
        self.tick()

    def _load_icon(self, path: str | None) -> None:
        """Use the game's own artwork for the window and the header.

        Tk 8.6 reads PNG directly, so the cached Discord application icon can
        be used as-is. Only whole-number scaling is available, so the source is
        160 pixels and the header copy is a quarter of that.
        """
        if not path or not os.path.isfile(path):
            return
        try:
            self.icon = tk.PhotoImage(file=path)
            self.root.iconphoto(False, self.icon)
            factor = max(1, round(self.icon.width() / 40))
            self.icon_small = self.icon.subsample(factor, factor)
        except tk.TclError:
            self.icon = None
            self.icon_small = None

    def _centre(self) -> None:
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 3
        self.root.geometry(f'+{x}+{y}')

    def tick(self) -> None:
        elapsed = time.monotonic() - self.started
        if elapsed >= self.total:
            self.stop()
            return
        self.bar['value'] = elapsed
        self.pct.config(text=f'{min(100, elapsed / self.total * 100):.0f}%')
        self.remaining.config(text=human(self.total - elapsed) + ' left')
        self.root.after(250, self.tick)

    def hide(self) -> None:
        """Minimise to the taskbar, leaving the process running.

        Iconifying rather than withdrawing keeps a taskbar button, so the
        window can be brought back without going through the main app.
        """
        try:
            self.root.iconify()
        except tk.TclError:
            pass

    def stop(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        self.root.mainloop()


def run_quiet(total: int, title: str, mode: str) -> None:
    """Stay running for the duration without a countdown of its own.

    Used when several games launch together. Discord only counts a game
    process that owns a visible window, so each stand-in still has one, just
    out of the way. One group window shows the countdown for all of them.

    mode 'offscreen': a 1x1 tool window parked off-screen, no taskbar button.
    mode 'minimized': a normal window, minimized to the taskbar.
    """
    root = tk.Tk()
    root.title(title)
    if mode == 'offscreen':
        root.attributes('-toolwindow', True)
        root.geometry('1x1+-32000+-32000')
    else:
        root.geometry('1x1')
        root.iconify()
    root.protocol('WM_DELETE_WINDOW', lambda: None)
    root.after(int(total * 1000), root.destroy)
    root.mainloop()


def _seconds(text: str) -> int:
    try:
        return int(float(text))
    except ValueError:
        return DEFAULT_SECONDS


def main(argv: list[str]) -> int:
    _apply_theme()

    # stub --group <seconds>: one countdown for several games. The game names
    # come as a JSON list in DQC_STUB_GROUP. This process is not a game; it
    # is only the window. Closing it with Stop ends the whole group.
    if len(argv) > 1 and argv[1] == '--group':
        total = _seconds(argv[2]) if len(argv) > 2 else DEFAULT_SECONDS
        try:
            names = [str(n) for n in json.loads(os.environ.get('DQC_STUB_GROUP') or '[]')]
        except ValueError:
            names = []
        count = len(names)
        Stub(
            total, f'{count} game{"s" if count != 1 else ""} running',
            subtitle=', '.join(names) or 'Emulating game activity for Discord',
            stop_text='Stop all',
        ).run()
        return 0

    total = _seconds(argv[1]) if len(argv) > 1 else DEFAULT_SECONDS
    title = argv[2] if len(argv) > 2 else 'Game'
    quiet = os.environ.get('DQC_STUB_QUIET')
    if quiet:
        run_quiet(total, title, quiet)
        return 0
    icon = argv[3] if len(argv) > 3 else None
    Stub(total, title, icon).run()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
