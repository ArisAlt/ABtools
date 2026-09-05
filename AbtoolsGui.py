#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py - v0.17 - 2025-09-11
"""
from __future__ import annotations

import json
import re
import sys, threading, queue, time
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font as tkfont
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
import importlib
import combobook, find_duplicates, restructure_for_audiobookshelf
tag_cli = importlib.import_module("ablib.cli.main")
from ablib.core import config as core_config
from ablib.core.constants import (
    DEFAULT_LLM_ENDPOINT as CLI_DEFAULT_LLM_ENDPOINT,
    DEFAULT_LLM_MODEL_NAME as CLI_DEFAULT_LLM_MODEL,
)

VERSION = "0.17"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

CONFIG = tag_cli.CONFIG

PAD_X = 12
PAD_Y = 8

DEFAULT_LLM_ENDPOINT = CONFIG.llm_endpoint or CLI_DEFAULT_LLM_ENDPOINT
DEFAULT_LLM_MODEL = CONFIG.llm_model_name or CLI_DEFAULT_LLM_MODEL

if "--version" in sys.argv:
    print(VERSION_INFO % {"prog": Path(sys.argv[0]).name})
    sys.exit(0)

root = tk.Tk()
root.title("ABtools GUI")
root.resizable(True, True)
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

# ───────────── themes ───────────────────────────────────────────────────────
# Palettes are data, and every colour the UI uses comes from the active one.
# apply_theme() rebinds the module-level names below and restyles live, so the
# theme can be changed from the dropdown without restarting.
#
# Keys: bg (window) / surface (cards) / field (inputs + log) / border /
#       fg / muted / accent (+hover,+active) / neutral (+hover) /
#       danger (+hover) / disabled / log_* semantic accents.
THEMES: dict[str, dict[str, str]] = {
    # Near-neutral surfaces, colour only in the accent. Ages best.
    "Neutral Slate": {
        "bg": "#0f1115", "surface": "#171a21", "field": "#1e222b", "border": "#2a2f3a",
        "fg": "#e6e8ee", "muted": "#8b93a3",
        "accent": "#3b82f6", "accent_hover": "#2f6fe0", "accent_active": "#2559b8",
        "neutral": "#232833", "neutral_hover": "#2e3440",
        "danger": "#f87171", "danger_hover": "#dc4c4c", "disabled": "#1a1d24",
        "log_green": "#4ade80", "log_red": "#f87171", "log_yellow": "#fbbf24",
        "log_blue": "#60a5fa", "log_cyan": "#22d3ee", "log_magenta": "#c084fc",
    },
    "Tokyo Night": {
        "bg": "#1a1b26", "surface": "#24283b", "field": "#1f2335", "border": "#363b54",
        # muted lifted from the canonical #565f89/#7982a9: those are tuned for
        # Tokyo Night's darker bg and fall under 4.5:1 on our card surface.
        "fg": "#c0caf5", "muted": "#8b94b6",
        "accent": "#7aa2f7", "accent_hover": "#6a92e7", "accent_active": "#5a82d7",
        "neutral": "#2f3549", "neutral_hover": "#3b4261",
        "danger": "#f7768e", "danger_hover": "#e05a73", "disabled": "#1e2030",
        "log_green": "#9ece6a", "log_red": "#f7768e", "log_yellow": "#e0af68",
        "log_blue": "#7aa2f7", "log_cyan": "#7dcfff", "log_magenta": "#bb9af7",
    },
    "Catppuccin Mocha": {
        "bg": "#1e1e2e", "surface": "#313244", "field": "#181825", "border": "#45475a",
        # muted lifted from Catppuccin's #9399b2 (subtext0), which lands just
        # under 4.5:1 on the #313244 surface.
        "fg": "#cdd6f4", "muted": "#9ba1b9",
        "accent": "#89b4fa", "accent_hover": "#74a3f0", "accent_active": "#5f92e6",
        "neutral": "#45475a", "neutral_hover": "#585b70",
        "danger": "#f38ba8", "danger_hover": "#e07396", "disabled": "#252537",
        "log_green": "#a6e3a1", "log_red": "#f38ba8", "log_yellow": "#f9e2af",
        "log_blue": "#89b4fa", "log_cyan": "#94e2d5", "log_magenta": "#cba6f7",
    },
    "Nord": {
        "bg": "#2e3440", "surface": "#3b4252", "field": "#434c5e", "border": "#4c566a",
        "fg": "#eceff4", "muted": "#aab3c2",
        "accent": "#88c0d0", "accent_hover": "#8fbcbb", "accent_active": "#5e81ac",
        "neutral": "#434c5e", "neutral_hover": "#4c566a",
        "danger": "#bf616a", "danger_hover": "#a54e57", "disabled": "#353b48",
        # log_red lifted from Nord's aurora red #bf616a, which is only 2.1:1
        # against Nord's comparatively light field colour.
        "log_green": "#a3be8c", "log_red": "#d4939a", "log_yellow": "#ebcb8b",
        "log_blue": "#81a1c1", "log_cyan": "#88c0d0", "log_magenta": "#b48ead",
    },
    "Gruvbox Dark": {
        "bg": "#1d2021", "surface": "#282828", "field": "#32302f", "border": "#504945",
        "fg": "#ebdbb2", "muted": "#a89984",
        "accent": "#fabd2f", "accent_hover": "#e6a800", "accent_active": "#d79921",
        "neutral": "#3c3836", "neutral_hover": "#504945",
        "danger": "#fb4934", "danger_hover": "#cc241", "disabled": "#252525",
        "log_green": "#b8bb26", "log_red": "#fb4934", "log_yellow": "#fabd2f",
        "log_blue": "#83a598", "log_cyan": "#8ec07c", "log_magenta": "#d3869b",
    },
    # Matches Dev/Bchips-main/gui.py.
    "Bchips Violet": {
        "bg": "#1a1b2e", "surface": "#252641", "field": "#2f3055", "border": "#2f3055",
        "fg": "#e2e8f0", "muted": "#8892a8",
        "accent": "#7c3aed", "accent_hover": "#6d28d9", "accent_active": "#5b21b6",
        "neutral": "#2f3055", "neutral_hover": "#3a3b66",
        "danger": "#ef4444", "danger_hover": "#dc2626", "disabled": "#232438",
        "log_green": "#22c55e", "log_red": "#ef4444", "log_yellow": "#f59e0b",
        "log_blue": "#60a5fa", "log_cyan": "#22d3ee", "log_magenta": "#a78bfa",
    },
    # Sampled from color-meanings.com's dark-palettes illustration.
    "Color-Meanings": {
        "bg": "#161638", "surface": "#302442", "field": "#1b435e", "border": "#563457",
        "fg": "#e9e7f2", "muted": "#9d94b8",
        "accent": "#38667e", "accent_hover": "#457a95", "accent_active": "#2c5266",
        "neutral": "#563457", "neutral_hover": "#6a4269",
        "danger": "#ff8f9c", "danger_hover": "#d9536a", "disabled": "#241d33",
        "log_green": "#5ddc9a", "log_red": "#ff8f9c", "log_yellow": "#f2c14e",
        "log_blue": "#7fb3e8", "log_cyan": "#6fd3e8", "log_magenta": "#c79ae8",
    },
}
DEFAULT_THEME = "Neutral Slate"
LOG_TAG_NAMES = ("red", "green", "yellow", "cyan", "magenta", "blue", "dim")
SETTINGS_PATH = Path.home() / ".abtools_gui.json"


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    chans = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _readable_on(background: str) -> str:
    """Black or white, whichever is legible on `background`.

    Picked per theme rather than hardcoded: a light accent like Nord's
    #88c0d0 needs dark text, while a deep one like #3b82f6 needs white.
    """
    return "#ffffff" if contrast("#ffffff", background) >= contrast("#101216", background) else "#101216"


# Populated by apply_theme() before any widget is built.
BG = SURFACE = FIELD = BORDER = FG = MUTED = ACCENT = ""
ACCENT_HOVER = ACCENT_ACTIVE = NEUTRAL = NEUTRAL_HOVER = ""
DANGER = DANGER_HOVER = DISABLED_BG = ON_ACCENT = ""
CURRENT_THEME = DEFAULT_THEME


def _pick_font(candidates: tuple[str, ...], fallback: str) -> str:
    """First installed family from `candidates`, else the Tk default.

    The previous hardcoded "Segoe UI" silently fell back to an arbitrary
    family on Linux and macOS.
    """
    available = set(tkfont.families())
    for name in candidates:
        if name in available:
            return name
    return tkfont.nametofont(fallback).actual("family")


UI_FAMILY = _pick_font(
    ("Inter", "Segoe UI", "SF Pro Text", "Cantarell", "Noto Sans", "Open Sans",
     "Ubuntu", "DejaVu Sans"),
    "TkDefaultFont",
)
MONO_FAMILY = _pick_font(
    ("Consolas", "JetBrains Mono", "Cascadia Mono", "SF Mono", "Source Code Pro",
     "Noto Sans Mono", "DejaVu Sans Mono", "Liberation Mono"),
    "TkFixedFont",
)
FONT_UI      = (UI_FAMILY, 10)
FONT_BOLD    = (UI_FAMILY, 10, "bold")
FONT_SECTION = (UI_FAMILY, 9, "bold")
FONT_MONO    = (MONO_FAMILY, 9)

style = ttk.Style(root)
# "clam" is the only stock theme that honours colour options properly; the
# default theme ignores most of them and keeps its 1990s bevels.
if "clam" in style.theme_names():
    style.theme_use("clam")


def _load_saved_theme() -> str:
    try:
        name = json.loads(SETTINGS_PATH.read_text()).get("theme")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_THEME
    return name if name in THEMES else DEFAULT_THEME


def _save_theme(name: str) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps({"theme": name}, indent=2))
    except OSError:
        pass          # a read-only home is not worth failing the UI over


def apply_theme(name: str, *, persist: bool = False) -> None:
    """Rebind the palette and restyle every widget in place."""
    global BG, SURFACE, FIELD, BORDER, FG, MUTED, ACCENT, ACCENT_HOVER
    global ACCENT_ACTIVE, NEUTRAL, NEUTRAL_HOVER, DANGER, DANGER_HOVER
    global DISABLED_BG, ON_ACCENT, CURRENT_THEME

    p = THEMES.get(name) or THEMES[DEFAULT_THEME]
    CURRENT_THEME = name if name in THEMES else DEFAULT_THEME
    BG, SURFACE, FIELD, BORDER = p["bg"], p["surface"], p["field"], p["border"]
    FG, MUTED, ACCENT = p["fg"], p["muted"], p["accent"]
    ACCENT_HOVER, ACCENT_ACTIVE = p["accent_hover"], p["accent_active"]
    NEUTRAL, NEUTRAL_HOVER = p["neutral"], p["neutral_hover"]
    DANGER, DANGER_HOVER, DISABLED_BG = p["danger"], p["danger_hover"], p["disabled"]
    ON_ACCENT = _readable_on(ACCENT)

    _style_widgets()
    _restyle_log(p)
    if persist:
        _save_theme(CURRENT_THEME)


def _restyle_log(p: dict[str, str]) -> None:
    """Recolour the log pane. No-op until it has been built."""
    text = globals().get("output_text")
    if text is None:
        return
    text.configure(background=FIELD, foreground=FG, insertbackground=FG,
                   highlightbackground=BORDER, highlightcolor=BORDER,
                   selectbackground=ACCENT, selectforeground=ON_ACCENT)
    for tag in LOG_TAG_NAMES:
        colour = MUTED if tag == "dim" else p[f"log_{tag}"]
        text.tag_configure(tag, foreground=colour)


def _style_widgets() -> None:
    root.configure(bg=BG)
    style.configure(".", background=SURFACE, foreground=FG, font=FONT_UI,
                    borderwidth=0, focuscolor=SURFACE)
    style.configure("TFrame", background=SURFACE)
    style.configure("App.TFrame", background=BG)
    style.configure("TLabel", background=SURFACE, foreground=FG)
    style.configure("Bg.TLabel", background=BG, foreground=MUTED)
    style.configure("TCheckbutton", background=SURFACE, foreground=FG,
                    indicatorcolor=FIELD, bordercolor=MUTED, focuscolor=SURFACE)
    style.map("TCheckbutton",
              background=[("active", SURFACE)],
              foreground=[("disabled", MUTED)],
              indicatorcolor=[("selected", ACCENT), ("!selected", FIELD)],
              bordercolor=[("selected", ACCENT), ("active", ACCENT)])

    # Cards: flat fill, hairline border, quiet section titles.
    style.configure("TLabelframe", background=SURFACE, bordercolor=BORDER,
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=SURFACE, foreground=MUTED,
                    font=FONT_SECTION)

    # Buttons share one padding so every action is the same height. The primary
    # and destructive actions are distinguished by colour, not by size.
    style.configure("TButton", background=NEUTRAL, foreground=FG, bordercolor=BORDER,
                    relief="flat", padding=(14, 8), font=FONT_UI, anchor="center")
    style.map("TButton",
              background=[("disabled", DISABLED_BG), ("pressed", BORDER), ("active", NEUTRAL_HOVER)],
              foreground=[("disabled", MUTED)],
              bordercolor=[("focus", ACCENT)])
    style.configure("Primary.TButton", background=ACCENT, foreground=ON_ACCENT,
                    bordercolor=ACCENT, font=FONT_BOLD)
    style.map("Primary.TButton",
              background=[("disabled", DISABLED_BG), ("pressed", ACCENT_ACTIVE), ("active", ACCENT_HOVER)],
              foreground=[("disabled", MUTED)])
    on_danger = _readable_on(DANGER)
    style.configure("Danger.TButton", background=NEUTRAL, foreground=DANGER)
    style.map("Danger.TButton",
              background=[("disabled", DISABLED_BG), ("pressed", DANGER_HOVER), ("active", DANGER)],
              foreground=[("disabled", MUTED), ("active", on_danger), ("pressed", on_danger)])

    for _cls in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(_cls, fieldbackground=FIELD, background=NEUTRAL, foreground=FG,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        insertcolor=FG, arrowcolor=MUTED, relief="flat", padding=5)
        style.map(_cls,
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)],
                  fieldbackground=[("disabled", DISABLED_BG), ("readonly", FIELD)],
                  foreground=[("disabled", MUTED)])
    style.map("TCombobox", arrowcolor=[("disabled", BORDER)])
    # option_add only affects widgets created afterwards, so an existing
    # dropdown list keeps its old colours until reopened -- acceptable.
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)

    # A slim accent bar reads as progress; the stock trough looked like an empty box.
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=NEUTRAL,
                    bordercolor=NEUTRAL, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
    style.configure("Vertical.TScrollbar", background=NEUTRAL_HOVER, troughcolor=SURFACE,
                    bordercolor=SURFACE, arrowcolor=MUTED, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", MUTED)])


apply_theme(_load_saved_theme())

# ───────────── tooltips ─────────────────────────────────────────────────────
class Tooltip:
    """Hover help, themed to match the palette.

    A plain `tk.Toplevel` is used rather than a ttk widget so the border can be
    faked with a 1px outer frame -- ttk gives no portable border on a Toplevel.
    """

    DELAY_MS = 450
    WRAP_PX = 340

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._after: str | None = None
        self._win: tk.Toplevel | None = None
        # add="+" so existing handlers on the widget are preserved.
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event: object = None) -> None:
        self._cancel()
        self._after = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self) -> None:
        if self._win is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 14
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        try:
            win = tk.Toplevel(self.widget)
            win.wm_overrideredirect(True)
            win.configure(bg=BORDER)
            tk.Label(
                win, text=self.text, justify="left", wraplength=self.WRAP_PX,
                bg=FIELD, fg=FG, font=FONT_UI, padx=10, pady=7,
            ).pack(padx=1, pady=1)

            # Keep it on screen. The bottom-row buttons sit near the lower edge,
            # where a tall tip would otherwise be cut off.
            win.update_idletasks()
            w, h = win.winfo_reqwidth(), win.winfo_reqheight()
            margin = 8
            x = min(x, win.winfo_screenwidth() - w - margin)
            x = max(margin, x)
            if y + h > win.winfo_screenheight() - margin:
                above = self.widget.winfo_rooty() - h - 6
                y = above if above >= margin else max(margin, win.winfo_screenheight() - h - margin)

            win.wm_geometry(f"+{x}+{y}")
            win.attributes("-topmost", True)
        except tk.TclError:
            return
        self._win = win

    def hide(self, _event: object = None) -> None:
        self._cancel()
        if self._win is not None:
            try:
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None


def tip(widget, text: str):
    """Attach hover help and return the widget, so it can be .grid()'d inline."""
    Tooltip(widget, text)
    return widget


main = ttk.Frame(root, padding=PAD_X, style="App.TFrame")
main.grid(row=0, column=0, sticky="nsew")
main.columnconfigure(0, weight=1)
for i in range(5):
    main.rowconfigure(i, weight=0)
main.rowconfigure(4, weight=1)

source_var = tk.StringVar()
dest_var = tk.StringVar()

def browse_src():
    path = filedialog.askdirectory()
    if path:
        source_var.set(path)

def browse_dst():
    path = filedialog.askdirectory()
    if path:
        dest_var.set(path)


paths_frame = ttk.LabelFrame(main, text="File Paths", padding=PAD_X)
paths_frame.grid(row=0, column=0, sticky="ew")
paths_frame.columnconfigure(1, weight=1)

TIP_SOURCE = (
    "Folder to read from. Tag and Move scan it for audiobook folders; "
    "Find Duplicates scans it for duplicate audio files.\n\n"
    "You can point it straight at a single book folder."
)
TIP_DEST = (
    "Library folder to write into. Move and Restructure place books here as "
    "Author/Title (Year).\n\n"
    "For Find Duplicates this is optional: set it to compare two folders "
    "against each other, or leave it empty to scan the source alone."
)

ttk.Label(paths_frame, text="Source:").grid(row=0, column=0, sticky="w", padx=(0, PAD_X), pady=(0, PAD_Y))
tip(ttk.Entry(paths_frame, textvariable=source_var), TIP_SOURCE).grid(row=0, column=1, sticky="ew", pady=(0, PAD_Y))
tip(ttk.Button(paths_frame, text="Browse", command=browse_src),
    "Pick the source folder.").grid(row=0, column=2, sticky="ew", padx=(PAD_X, 0), pady=(0, PAD_Y))

ttk.Label(paths_frame, text="Destination:").grid(row=1, column=0, sticky="w", padx=(0, PAD_X), pady=(0, PAD_Y))
tip(ttk.Entry(paths_frame, textvariable=dest_var), TIP_DEST).grid(row=1, column=1, sticky="ew", pady=(0, PAD_Y))
tip(ttk.Button(paths_frame, text="Browse", command=browse_dst),
    "Pick the destination folder.").grid(row=1, column=2, sticky="ew", padx=(PAD_X, 0), pady=(0, PAD_Y))


commit_var = tk.BooleanVar()
copy_var = tk.BooleanVar()
yes_var = tk.BooleanVar()
network_var = tk.BooleanVar()
timeout_var = tk.IntVar(value=30)
compare_by_var = tk.StringVar(value="hash")
threads_var = tk.IntVar(value=4)
recurse_var = tk.BooleanVar(value=True)
only_src_log_var = tk.BooleanVar()
llm_endpoint_var = tk.StringVar(value=DEFAULT_LLM_ENDPOINT)
llm_model_var = tk.StringVar(value=DEFAULT_LLM_MODEL)
use_llm_var = tk.BooleanVar(value=bool(DEFAULT_LLM_ENDPOINT))

operation_frame = ttk.LabelFrame(main, text="Operation Settings", padding=PAD_X)
operation_frame.grid(row=1, column=0, sticky="ew", pady=(PAD_Y, 0))
# Columns 0-3 hug their content; a trailing spacer absorbs the slack. Giving
# column 3 the weight stretched the Threads spinbox to the window edge.
for col in range(4):
    operation_frame.columnconfigure(col, weight=0)
operation_frame.columnconfigure(4, weight=1)

ttk.Label(operation_frame, text="Timeout (s):").grid(row=0, column=0, sticky="w")
timeout_spin = ttk.Spinbox(
    operation_frame,
    from_=0,
    to=600,
    textvariable=timeout_var,
    width=6,
    increment=5,
)
timeout_spin.grid(row=0, column=1, sticky="w", padx=(0, PAD_X * 2))

ttk.Label(operation_frame, text="Threads:").grid(row=0, column=2, sticky="w", padx=(0, PAD_X))
threads_spin = ttk.Spinbox(
    operation_frame,
    from_=1,
    to=64,
    textvariable=threads_var,
    width=5,
)
threads_spin.grid(row=0, column=3, sticky="w")

ttk.Label(operation_frame, text="Compare by:").grid(row=1, column=0, sticky="w", pady=(PAD_Y, 0))
compare_combo = ttk.Combobox(
    operation_frame,
    textvariable=compare_by_var,
    values=("hash", "name"),
    state="readonly",
    width=8,
)
compare_combo.grid(row=1, column=1, sticky="w", pady=(PAD_Y, 0))

Tooltip(timeout_spin,
        "Per-file read timeout, in seconds, while hashing for duplicates.\n\n"
        "Only applies when Network Mode is ticked. Use it to stop a flaky "
        "NAS from hanging the scan. 0 means no timeout.")
Tooltip(threads_spin,
        "How many files to hash in parallel during Find Duplicates.\n\n"
        "Higher is faster on local disks; lower is kinder to a network share. "
        "Does not affect tagging.")
Tooltip(compare_combo,
        "How duplicates are matched.\n\n"
        "hash - compares SHA1 contents. Accurate, and catches renamed files, "
        "but has to read every candidate.\n"
        "name - compares file names only. Much faster, but misses renames and "
        "can flag unrelated files that happen to share a name.")

checkbox_frame = ttk.Frame(operation_frame)
checkbox_frame.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(PAD_Y, 0))
for _c in range(4):
    checkbox_frame.columnconfigure(_c, weight=1, uniform="opts")

tip(ttk.Checkbutton(checkbox_frame, text="Commit", variable=commit_var),
    "Actually write the changes.\n\n"
    "Left unticked, Tag and Move only preview what they would do and no file "
    "is touched. Tick this once the preview looks right."
    ).grid(row=0, column=0, sticky="w", padx=(0, PAD_X))
tip(ttk.Checkbutton(checkbox_frame, text="Copy", variable=copy_var),
    "Copy books into the destination instead of moving them, leaving the "
    "source untouched. Needs Commit to have any effect."
    ).grid(row=0, column=1, sticky="w", padx=(0, PAD_X))
tip(ttk.Checkbutton(checkbox_frame, text="Yes", variable=yes_var),
    "Auto-accept every metadata match without asking.\n\n"
    "Faster for a big run, but a wrong match gets written without you seeing "
    "it. Leave off to confirm low-confidence matches yourself."
    ).grid(row=0, column=2, sticky="w", padx=(0, PAD_X))
tip(ttk.Checkbutton(checkbox_frame, text="Recurse", variable=recurse_var),
    "Search sub-folders as well as the top level.\n\n"
    "Applies to Find Duplicates when scanning a single folder."
    ).grid(row=0, column=3, sticky="w", padx=(0, PAD_X))
tip(ttk.Checkbutton(checkbox_frame, text="Network Mode", variable=network_var),
    "Treat the source as a network share and enforce the Timeout above on "
    "every file read.\n\nWithout this, Timeout is ignored and a stalled share "
    "can hang the scan indefinitely."
    ).grid(row=1, column=0, sticky="w", padx=(0, PAD_X), pady=(PAD_Y // 2, 0))
tip(ttk.Checkbutton(checkbox_frame, text="Only src log", variable=only_src_log_var),
    "Limit the duplicate scan to files already listed in the source's "
    "duplicate_log.txt, instead of walking the whole folder again.\n\n"
    "Useful for re-checking a previous run's findings quickly."
    ).grid(row=1, column=1, sticky="w", padx=(0, PAD_X), pady=(PAD_Y // 2, 0))

MODEL_CHOICES = (
    DEFAULT_LLM_MODEL,
    "llama-3-8b-instruct",
    "mixtral-8x7b-instruct",
    "phi-3-medium-4k-instruct",
)

llm_frame = ttk.LabelFrame(main, text="Model Configuration", padding=PAD_X)
llm_frame.grid(row=2, column=0, sticky="ew", pady=(PAD_Y, 0))
llm_frame.columnconfigure(1, weight=1)
llm_frame.columnconfigure(3, weight=1)

llm_controls: list[tk.Widget] = []

tip(ttk.Checkbutton(
    llm_frame,
    text="Enable LLM fallback",
    variable=use_llm_var,
    command=lambda: toggle_llm_controls(),
),
    "When the online providers cannot find a confident match, ask a local "
    "LLM to work the metadata out instead.\n\n"
    "Turn it off to rely on Audible/Goodreads/Open Library/Google Books alone; "
    "unmatched books then go to the review log."
).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, PAD_Y))

ttk.Label(llm_frame, text="Endpoint:").grid(row=1, column=0, sticky="e", padx=(0, PAD_X), pady=(0, PAD_Y))
endpoint_entry = ttk.Entry(llm_frame, textvariable=llm_endpoint_var)
endpoint_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0, PAD_Y))
llm_controls.append(endpoint_entry)

ttk.Label(llm_frame, text="Model:").grid(row=2, column=0, sticky="e", padx=(0, PAD_X), pady=(0, PAD_Y))
# Editable, and spanning the same columns as Endpoint above it. It was a
# half-width readonly box, yet the CLI accepts any model name -- and
# toggle_llm_controls() already flipped it to editable on the first toggle.
model_combo = ttk.Combobox(llm_frame, textvariable=llm_model_var, values=MODEL_CHOICES)
model_combo.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0, PAD_Y))
llm_controls.append(model_combo)

Tooltip(endpoint_entry,
        "URL of an OpenAI-compatible chat-completions endpoint, such as the "
        "local server LM Studio exposes.\n\n"
        f"Default: {DEFAULT_LLM_ENDPOINT}\n"
        "Set to 'none' to disable the fallback.")
Tooltip(model_combo,
        "Model to request from that endpoint. It must already be loaded there.\n\n"
        "The list is only a shortcut - you can type any model name.")



def toggle_llm_controls() -> None:
    state = "normal" if use_llm_var.get() else "disabled"
    for widget in llm_controls:
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass

# The tag colours themselves live in the active theme and are applied by
# _restyle_log(), so switching theme recolours existing log output too.
LOG_SUPPORTED_TAGS = set(LOG_TAG_NAMES) | {"bold"}
LOG_TAG_FONT_CACHE: dict[str, tkfont.Font] = {}
RICH_TAG_PATTERN = re.compile(r"\[(/?)([a-zA-Z0-9_+-]*)]")

output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
# Track whether the progress bar is running in indeterminate mode to avoid
# flicker from redundant determinate updates during cross-compare.
progress_is_indeterminate = False
current_worker: threading.Thread | None = None
stop_event = threading.Event()
action_buttons: list[ttk.Button] = []
stop_button: ttk.Button | None = None

def set_running(running: bool) -> None:
    global current_worker, progress_is_indeterminate
    state = "disabled" if running else "normal"
    for btn in action_buttons:
        try:
            btn.configure(state=state)
        except tk.TclError:
            pass
    if stop_button is not None:
        try:
            stop_button.configure(state="normal" if running else "disabled")
        except tk.TclError:
            pass
    if not running:
        current_worker = None
        stop_event.clear()
        try:
            progress.stop()
            progress.configure(mode="determinate")
        except Exception:
            pass
        progress_is_indeterminate = False

def start_worker(target: Callable[[], None]) -> None:
    global current_worker
    if current_worker is not None and current_worker.is_alive():
        return
    stop_event.clear()
    set_running(True)
    worker_thread = threading.Thread(target=target, daemon=True)
    current_worker = worker_thread
    worker_thread.start()

def stop_current() -> None:
    if current_worker is None or not current_worker.is_alive():
        return
    if stop_event.is_set():
        return
    stop_event.set()
    try:
        eta_var.set("Stopping...")
    except Exception:
        pass
    output_queue.put(("stdout", "\nStop requested. Waiting for current task to finish...\n"))

actions_frame = ttk.LabelFrame(main, text="Actions", padding=PAD_X)
actions_frame.grid(row=3, column=0, sticky="ew", pady=(PAD_Y, 0))
for i in range(5):
    actions_frame.columnconfigure(i, weight=1, uniform="actions")

log_frame = ttk.LabelFrame(main, text="Log", padding=PAD_X)
log_frame.grid(row=4, column=0, sticky="nsew", pady=(PAD_Y, 0))
log_frame.columnconfigure(0, weight=1)
log_frame.rowconfigure(0, weight=1)

output_text = tk.Text(
    log_frame,
    height=11,
    wrap="word",
    state="disabled",
    relief="flat",
    borderwidth=0,
    highlightthickness=1,
    highlightbackground=BORDER,
    highlightcolor=BORDER,
    background=FIELD,
    foreground=FG,
    insertbackground=FG,
    selectbackground=ACCENT,
    selectforeground="#ffffff",
    padx=10,
    pady=8,
    spacing1=1,
    spacing3=1,
)
output_text.grid(row=0, column=0, sticky="nsew")

scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=output_text.yview)
scrollbar.grid(row=0, column=1, sticky="ns", padx=(PAD_X // 2, 0))
output_text.configure(yscrollcommand=scrollbar.set)

# CLI output is column-aligned, so render the log monospaced.
_log_base_font = tkfont.Font(family=MONO_FAMILY, size=FONT_MONO[1])
output_text.configure(font=_log_base_font)
_bold_font = _log_base_font.copy()
_bold_font.configure(weight="bold")
LOG_TAG_FONT_CACHE["bold"] = _bold_font
output_text.tag_configure("bold", font=_bold_font)
# Colour tags come from the active theme now that the widget exists.
apply_theme(CURRENT_THEME)

progress_var = tk.IntVar(value=0)
progress = ttk.Progressbar(log_frame, variable=progress_var, maximum=100)
progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(PAD_Y, 0))

# ───────────── status row: theme picker (left) + ETA (right) ────────────────
status_row = ttk.Frame(main, style="App.TFrame")
status_row.grid(row=5, column=0, sticky="ew", pady=(PAD_Y, 0))
status_row.columnconfigure(1, weight=1)

theme_var = tk.StringVar(value=CURRENT_THEME)


def on_theme_change(_event: object = None) -> None:
    apply_theme(theme_var.get(), persist=True)


ttk.Label(status_row, text="Theme:", style="Bg.TLabel").grid(row=0, column=0, padx=(0, 6))
theme_combo = ttk.Combobox(
    status_row,
    textvariable=theme_var,
    values=list(THEMES),
    state="readonly",
    width=18,
)
theme_combo.grid(row=0, column=1, sticky="w")
theme_combo.bind("<<ComboboxSelected>>", on_theme_change)
Tooltip(theme_combo,
        "Colour theme for this window. Applies immediately and is remembered "
        "for next launch.\n\n"
        "Neutral Slate keeps the surfaces grey and puts colour only in the "
        "accent; the others tint the surfaces too.")

eta_var = tk.StringVar(value="ETA: --:--")
ttk.Label(status_row, textvariable=eta_var, style="Bg.TLabel").grid(
    row=0, column=2, sticky="e"
)

toggle_llm_controls()
root.update_idletasks()
root.minsize(root.winfo_reqwidth(), 620)

def gather_llm_settings() -> dict[str, object]:
    enabled = bool(use_llm_var.get())
    endpoint = (llm_endpoint_var.get() or "").strip()
    model = (llm_model_var.get() or "").strip()
    if not enabled:
        return {"enabled": False, "endpoint": "none", "model": ""}
    return {"enabled": True, "endpoint": endpoint, "model": model}


def apply_llm_settings(settings: dict[str, object]) -> None:
    enabled = bool(settings.get("enabled", True))
    endpoint_raw = str(settings.get("endpoint", "") or "").strip()
    model_raw = str(settings.get("model", "") or "").strip()

    if not enabled or endpoint_raw.lower() in {"none", "null", "off"}:
        CONFIG.llm_endpoint = None
    elif endpoint_raw:
        CONFIG.llm_endpoint = endpoint_raw
    else:
        CONFIG.llm_endpoint = DEFAULT_LLM_ENDPOINT

    if not enabled or model_raw.lower() in {"none", "null", "off"}:
        CONFIG.llm_model_name = None
    elif model_raw:
        CONFIG.llm_model_name = model_raw
    else:
        CONFIG.llm_model_name = DEFAULT_LLM_MODEL

    tagger_mod = getattr(combobook, "tagger", None)
    if tagger_mod is not None and hasattr(tagger_mod, "CONFIG"):
        tagger_mod.CONFIG.llm_endpoint = CONFIG.llm_endpoint
        tagger_mod.CONFIG.llm_model_name = CONFIG.llm_model_name


def _normalise_output_text(text: str) -> str:
    """Best-effort fix for mojibake sequences in captured CLI output."""
    if not text or "â" not in text:
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text


def _insert_segment(widget: tk.Text, segment: str, active_tags: list[str]) -> None:
    if not segment:
        return
    widget.insert(tk.END, segment.replace("\r", "\n"), tuple(active_tags))


def _render_markup(widget: tk.Text, text: str) -> None:
    if "[" not in text:
        _insert_segment(widget, text, [])
        return
    active: list[str] = []
    cursor = 0
    for match in RICH_TAG_PATTERN.finditer(text):
        start, end = match.span()
        if start > cursor:
            _insert_segment(widget, text[cursor:start], active)
        is_closing = match.group(1) == "/"
        tag_name = match.group(2).lower()
        if is_closing:
            if not tag_name:
                active.clear()
            else:
                for idx in range(len(active) - 1, -1, -1):
                    if active[idx] == tag_name:
                        del active[idx]
                        break
        else:
            if tag_name in LOG_SUPPORTED_TAGS:
                active.append(tag_name)
        cursor = end
    if cursor < len(text):
        _insert_segment(widget, text[cursor:], active)


def append_output(text: str) -> None:
    text = _normalise_output_text(text)
    output_text.configure(state="normal")
    _render_markup(output_text, text)
    output_text.see(tk.END)
    output_text.configure(state="disabled")

class QueueWriter:
    def __init__(self, q: queue.Queue[tuple[str, object]]):
        self.q = q

    def write(self, msg: str) -> None:
        if msg:
            self.q.put(("stdout", msg))

    def flush(self) -> None:  # pragma: no cover - required for file-like API
        pass

    def isatty(self) -> bool:
        """Mirror TTY interface so libraries that check stdout.isatty() do not crash."""
        return False

def poll_queue() -> None:
    global progress_is_indeterminate
    # Process a limited number of queued messages per tick so the Tk event
    # loop stays responsive even when a worker thread floods the queue with
    # progress updates (e.g. during a large duplicate scan).
    for _ in range(100):
        try:
            typ, msg = output_queue.get_nowait()
        except queue.Empty:
            break
        if typ == "stdout":
            append_output(msg)
        elif typ == "progress":
            idx, total, eta = msg
            # When in indeterminate mode, don't touch the determinate value/maximum
            # to prevent flicker; only update the ETA/elapsed label.
            if not progress_is_indeterminate:
                progress.configure(maximum=total if total else 1)
                progress_var.set(idx)
            if eta > 0:
                secs = int(eta)
                m, s = divmod(secs, 60)
                h, m = divmod(m, 60)
                eta_var.set(f"ETA: {h:02d}:{m:02d}:{s:02d}")
            elif eta < 0:
                secs = int(-eta)
                m, s = divmod(secs, 60)
                h, m = divmod(m, 60)
                eta_var.set(f"Elapsed: {h:02d}:{m:02d}:{s:02d}")
            else:
                eta_var.set("ETA: --:--")
        elif typ == "progress_mode":
            mode = msg
            if mode == "indeterminate":
                try:
                    progress_is_indeterminate = True
                    # Ensure sensible baseline so animation is visible and smooth
                    # Larger maximum + shorter interval -> smoother marquee
                    progress.configure(mode="indeterminate", maximum=300)
                    progress_var.set(0)
                    progress.start(35)
                except Exception:
                    pass
            elif mode == "determinate":
                try:
                    progress_is_indeterminate = False
                    progress.stop()
                    progress.configure(mode="determinate")
                except Exception:
                    pass
        elif typ == "prompt":
            # msg = (question, default, response_queue)
            question, default, resp_q = msg
            try:
                default_label = "Yes" if default else "No"
                ans = messagebox.askyesno(
                    "Confirm",
                    f"{question}\n\nDefault: {default_label}",
                )
            except Exception:
                ans = default
            try:
                resp_q.put(bool(ans))
            except Exception:
                pass
        elif typ == "status":
            if msg == "done":
                set_running(False)
                eta_var.set("ETA: --:--")
                try:
                    messagebox.showinfo("Done", "Processing finished")
                except Exception:
                    pass
            elif msg == "stopped":
                set_running(False)
                eta_var.set("Stopped")
                try:
                    messagebox.showinfo("Stopped", "Processing cancelled")
                except Exception:
                    pass
            elif msg.startswith("error:"):
                set_running(False)
                eta_var.set("Error")
                try:
                    messagebox.showerror("Error", msg[6:])
                except Exception:
                    pass
    root.after(100, poll_queue)

def _run_combobook(mode: str) -> None:
    if mode not in {"tag_move", "tag_only", "move_only"}:
        raise ValueError(f"Unsupported combobook mode: {mode}")
    src_str = (source_var.get() or "").strip()
    dst_str = (dest_var.get() or "").strip()
    if not src_str:
        messagebox.showerror("Error", "Source path is required")
        return
    src = Path(src_str).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
    if not dst_str:
        messagebox.showerror("Error", "Destination path is required")
        return
    dst = Path(dst_str).expanduser()
    dst.mkdir(parents=True, exist_ok=True)

    combobook.AUTO_YES = yes_var.get()
    llm_settings = gather_llm_settings()
    skip_move = mode == "tag_only"
    skip_tags = mode == "move_only"
    dry_run = skip_move or not commit_var.get()
    mode_label = {
        "tag_move": "Tag + Move",
        "tag_only": "Tag (no move)",
        "move_only": "Move (no retag)",
    }[mode]

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        original_write_tags = getattr(combobook, "WRITE_TAGS", True)
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(QueueWriter(output_queue)):
                apply_llm_settings(llm_settings)
                commit_flag = commit_var.get()
                copy_flag = copy_var.get()
                auto_yes_flag = yes_var.get()
                llm_endpoint = CONFIG.llm_endpoint or "disabled"
                llm_model = CONFIG.llm_model_name or "default"
                combobook.rprint(
                    f"[cyan]Starting {mode_label} run | commit={'yes' if commit_flag and not skip_move else 'no'} | "
                    f"copy={'yes' if copy_flag else 'no'} | auto-yes={'yes' if auto_yes_flag else 'no'} | dry-run={'yes' if dry_run else 'no'}[/]"
                )
                llm_state = "enabled" if llm_settings.get("enabled") else "disabled"
                combobook.rprint(
                    f"[cyan]Tagger LLM endpoint: {llm_endpoint} | model: {llm_model} | fallback={llm_state}[/]"
                )

                if skip_tags:
                    combobook.WRITE_TAGS = False

                def gui_confirm(question: str, default: bool = False) -> bool:
                    resp_q: queue.Queue[bool] = queue.Queue()
                    output_queue.put(("prompt", (question, default, resp_q)))
                    return bool(resp_q.get())

                try:
                    class _GuiConfirm:
                        @staticmethod
                        def ask(q: str, default: bool = False) -> bool:
                            return gui_confirm(q, default)
                    combobook.Confirm = _GuiConfirm  # type: ignore[attr-defined]
                except Exception:
                    pass

                if skip_tags:
                    combobook.rprint("[cyan]Tag writing disabled (move-only mode).[/]")
                elif skip_move:
                    combobook.rprint("[cyan]Moves are disabled (tag-only mode).[/]")

                leaves = combobook.leaf_dirs(src)
                total = len(leaves)
                combobook.rprint(f"[cyan]Discovered {total} leaf folder(s) to handle.[/]")
                summary: defaultdict[str, int] = defaultdict(int)
                start = time.time()
                for idx, leaf in enumerate(leaves, 1):
                    if stop_event.is_set():
                        combobook.rprint(f"\n[yellow]Stop requested; halting {mode_label} run.[/]")
                        output_queue.put(("status", "stopped"))
                        combobook.WRITE_TAGS = original_write_tags
                        return
                    try:
                        rel = leaf.relative_to(src)
                    except Exception:
                        rel = leaf
                    phase = "preview" if dry_run else "processing"
                    combobook.rprint(f"[cyan]({idx}/{total}) {phase}: {rel}[/]")
                    combobook.process(
                        leaf,
                        src,
                        dst,
                        dry=dry_run,
                        yes=yes_var.get(),
                        copy=copy_var.get(),
                        summary=summary,
                    )
                    elapsed = time.time() - start
                    rate = idx / elapsed if elapsed else 0.0
                    eta = (total - idx) / rate if rate else 0.0
                    output_queue.put(("progress", (idx, total, eta)))

                if stop_event.is_set():
                    combobook.rprint("\n[yellow]Stop requested; skipping summary.[/]")
                    output_queue.put(("status", "stopped"))
                    combobook.WRITE_TAGS = original_write_tags
                    return

                combobook.rprint(f"\n[bold]{mode_label} summary[/]")
                action_word = "copied" if copy_var.get() else "moved"
                combobook.rprint(f"  processed    : {summary['total']}")
                combobook.rprint(f"  {action_word:12}: {summary['moved']}")
                combobook.rprint(f"  would_move   : {summary['would_move']}")
                for key in ("exists", "skip", "unmatched"):
                    combobook.rprint(f"  {key:12}: {summary[key]}")
                if skip_move:
                    combobook.rprint("  moves skipped (tag-only mode)")
                if skip_tags:
                    combobook.rprint("  tags not updated (move-only mode)")
                combobook.WRITE_TAGS = original_write_tags
            output_queue.put(("status", "done"))
        except Exception as exc:
            try:
                combobook.WRITE_TAGS = original_write_tags
            except Exception:
                pass
            output_queue.put(("status", f"error:{exc}"))

    start_worker(worker)

def run() -> None:
    _run_combobook("tag_move")

def restructure() -> None:
    src_str = (source_var.get() or "").strip()
    dst_str = (dest_var.get() or "").strip()
    if not src_str:
        messagebox.showerror("Error", "Source path is required")
        return
    src = Path(src_str).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
    if not dst_str:
        messagebox.showerror("Error", "Destination path is required")
        return
    dst = Path(dst_str).expanduser()
    dst.mkdir(parents=True, exist_ok=True)

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(QueueWriter(output_queue)):
                # main() only accepts an argv list; call the library function
                # directly. Note restructure_library has no cancellation hook,
                # so Stop only takes effect once it returns.
                stats = restructure_for_audiobookshelf.restructure_library(
                    src,
                    dst,
                    dry=not commit_var.get(),
                    copy=copy_var.get(),
                )
                print(
                    f"Processed {stats['books']} books - moved: {stats['moved']}, "
                    f"skipped: {stats['skipped']}, dry-run: {stats['dry_run']}"
                )
            if stop_event.is_set():
                output_queue.put(("status", "stopped"))
            else:
                output_queue.put(("status", "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))

    start_worker(worker)

def tag_only() -> None:
    src_str = (source_var.get() or "").strip()
    if not src_str:
        messagebox.showerror("Error", "Source path is required")
        return
    src = Path(src_str).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return

    llm_settings = gather_llm_settings()

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(QueueWriter(output_queue)):
                apply_llm_settings(llm_settings)
                commit_flag = commit_var.get()
                auto_yes_flag = yes_var.get()
                endpoint = CONFIG.llm_endpoint or "disabled"
                model = CONFIG.llm_model_name or "default"
                fallback_state = "enabled" if llm_settings.get("enabled") else "disabled"
                tag_cli.rprint(
                    f"[cyan]Starting Tag run (providers + LM Studio + SequentialThinking) | commit={'yes' if commit_flag else 'no'} | auto-yes={'yes' if auto_yes_flag else 'no'}[/]"
                )
                tag_cli.rprint(
                    f"[cyan]LLM endpoint: {endpoint} | model: {model} | fallback={fallback_state}[/]"
                )

                def gui_confirm(question: str, default: bool = False) -> bool:
                    resp_q: queue.Queue[bool] = queue.Queue()
                    output_queue.put(("prompt", (question, default, resp_q)))
                    return bool(resp_q.get())

                try:
                    class _GuiConfirm:
                        @staticmethod
                        def ask(q: str, default: bool = False) -> bool:
                            return gui_confirm(q, default)
                        def __call__(self, q: str, default: bool = False) -> bool:
                            return gui_confirm(q, default)
                    tag_cli.Confirm = _GuiConfirm()  # type: ignore[attr-defined]
                except Exception:
                    pass

                base_for_logs = src if src.is_dir() else src.parent
                core_config.update_paths(base_for_logs)
                CONFIG.debug = False

                leaves = tag_cli.walk_leaves(src)
                args = SimpleNamespace(
                    commit=commit_var.get(),
                    yes=yes_var.get(),
                    no=False,
                    striptags=False,
                    llm_endpoint=CONFIG.llm_endpoint,
                    llm_model=CONFIG.llm_model_name,
                )

                total = len(leaves)
                tag_cli.rprint(f"[cyan]Scanning {total} leaf folder(s).[/]")
                start = time.time()
                for idx, leaf in enumerate(leaves, 1):
                    if stop_event.is_set():
                        tag_cli.rprint("\n[yellow]Stop requested; halting Tag Only run.[/]")
                        output_queue.put(("status", "stopped"))
                        return
                    try:
                        rel = leaf.relative_to(src)
                    except Exception:
                        rel = leaf
                    action = "Previewing" if not commit_flag else "Tagging"
                    tag_cli.rprint(f"[cyan]({idx}/{total}) {action} {rel}[/]")
                    if not commit_var.get():
                        tag_cli.rprint(f"[dim]preview:[/] {leaf}")
                    else:
                        tag_cli.process_leaf(leaf, args)
                    elapsed = time.time() - start
                    rate = idx / elapsed if elapsed else 0.0
                    eta = (total - idx) / rate if rate else 0.0
                    output_queue.put(("progress", (idx, total, eta)))
                if stop_event.is_set():
                    output_queue.put(("status", "stopped"))
                    return
            output_queue.put(("status", "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))

    start_worker(worker)

def find_dupes() -> None:
    src_str = (source_var.get() or "").strip()
    dst_str = (dest_var.get() or "").strip()
    if not src_str:
        messagebox.showerror("Error", "Source path is required")
        return
    src = Path(src_str).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
    dst = Path(dst_str).expanduser() if dst_str else None
    if dst is not None:
        dst.mkdir(parents=True, exist_ok=True)

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(QueueWriter(output_queue)):
                try:
                    net_timeout = float(timeout_var.get()) if network_var.get() else None
                except ValueError:
                    net_timeout = 30.0 if network_var.get() else None

                by = compare_by_var.get().strip().lower() or "hash"
                threads = max(1, int(threads_var.get() or 1))

                def on_file(stage: str, p: Path) -> None:
                    if "hash" in stage or "scan" in stage or "enum" in stage:
                        print(f"Checking: {p}")

                label = "name" if by == "name" else "SHA1"
                limit_set = None
                if only_src_log_var.get():
                    try:
                        log_path = src / find_duplicates.DUP_LOG.name
                        limit_set = find_duplicates._read_paths_from_log(log_path)  # type: ignore[attr-defined]
                        print(f"Using source log {log_path} with {len(limit_set)} paths\n")
                    except Exception:
                        limit_set = None

                if dst is not None:
                    print(f"Comparing {src} <-> {dst} by {by}...")
                    dupes = find_duplicates.find_cross_dupes(
                        src,
                        dst,
                        by=by,
                        hash_timeout=net_timeout,
                        on_file=on_file,
                        threads=threads,
                        limit_src=limit_set,
                        stop_event=stop_event,
                    )
                    if stop_event.is_set():
                        output_queue.put(("status", "stopped"))
                        return
                    if not dupes:
                        print("No duplicates found.")
                    else:
                        log_file = src / find_duplicates.DUP_LOG.name
                        find_duplicates._print_and_write_grouped(  # type: ignore[attr-defined]
                            dupes,
                            label,
                            log_file,
                            header=f"Cross-duplicates between {src} and {dst} (by {by})",
                        )
                        print(f"\n{sum(len(v) for v in dupes.values())} files logged to {log_file}")
                else:
                    print(f"Scanning {src} for duplicates by {by}...")
                    dupes = find_duplicates.find_dupes(
                        src,
                        by=by,
                        hash_timeout=net_timeout,
                        on_file=on_file,
                        threads=threads,
                        recursive=recurse_var.get(),
                        stop_event=stop_event,
                    )
                    if stop_event.is_set():
                        output_queue.put(("status", "stopped"))
                        return
                    if not dupes:
                        print("No duplicates found.")
                    else:
                        log_file = src / find_duplicates.DUP_LOG.name
                        find_duplicates._print_and_write_grouped(  # type: ignore[attr-defined]
                            dupes,
                            label,
                            log_file,
                        )
                        print(f"\n{sum(len(v) for v in dupes.values())} duplicate files logged to {log_file}")

                mode = "cross-compare" if dst is not None else "single-folder"
                print(f"\nMode: {mode} | by: {by}")
                if stop_event.is_set():
                    output_queue.put(("status", "stopped"))
                    return
            output_queue.put(("status", "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))

    start_worker(worker)
tag_button = ttk.Button(actions_frame, text="Tag", style="Primary.TButton", command=tag_only)
tag_button.grid(row=0, column=0, sticky="ew", padx=(0, PAD_X), pady=(0, PAD_Y))
move_button = ttk.Button(actions_frame, text="Move", command=run)
move_button.grid(row=0, column=1, sticky="ew", padx=(0, PAD_X), pady=(0, PAD_Y))
restructure_button = ttk.Button(actions_frame, text="Restructure", command=restructure)
restructure_button.grid(row=0, column=2, sticky="ew", padx=(0, PAD_X), pady=(0, PAD_Y))
dup_button = ttk.Button(actions_frame, text="Find Duplicates", command=find_dupes)
dup_button.grid(row=0, column=3, sticky="ew", pady=(0, PAD_Y))
stop_button = ttk.Button(actions_frame, text="Stop", style="Danger.TButton",
                         command=stop_current, state="disabled")
stop_button.grid(row=0, column=4, sticky="ew", padx=(PAD_X, 0), pady=(0, PAD_Y))
action_buttons.extend([tag_button, move_button, restructure_button, dup_button])

Tooltip(tag_button,
        "Look up metadata and write tags to the files where they are, without "
        "moving anything.\n\n"
        "Uses the online providers, falling back to the LLM if enabled. "
        "Respects Commit: unticked, it only previews.")
Tooltip(move_button,
        "Tag each book, then move it into the destination as "
        "Author/Title (Year), flattening any disc sub-folders.\n\n"
        "Tick Copy to leave the source in place. Respects Commit.")
Tooltip(restructure_button,
        "Reorganise a library that is already tagged into "
        "Author/Year - Title, using existing tags, metadata.json or the "
        "folder name.\n\nDoes no metadata lookup. Respects Commit and Copy.")
Tooltip(dup_button,
        "Find duplicate audio files, comparing by the Compare by setting.\n\n"
        "With a destination set, compares the two folders against each other; "
        "otherwise scans the source alone. Results are written to "
        "duplicate_log.txt and nothing is deleted.")
Tooltip(stop_button,
        "Ask the running job to stop.\n\n"
        "It finishes the file it is on before halting, so it may take a "
        "moment. Work already written is left as it is.")

if __name__ == "__main__":
    poll_queue()
    root.mainloop()
