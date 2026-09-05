#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py - v0.17 - 2025-09-11
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit, urlunsplit

import requests
import sys, threading, queue, time
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import messagebox, ttk, font as tkfont
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
import importlib
import combobook, find_duplicates, restructure_for_audiobookshelf
import flatten_discs, repair_m4b, ab_encode
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

PAD_X = 14
PAD_Y = 10

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
FONT_TITLE   = (UI_FAMILY, 17, "bold")
FONT_STATE   = (UI_FAMILY, 12, "bold")
FONT_DOT     = (UI_FAMILY, 15)

style = ttk.Style(root)
# "clam" is the only stock theme that honours colour options properly; the
# default theme ignores most of them and keeps its 1990s bevels.
if "clam" in style.theme_names():
    style.theme_use("clam")


SETTINGS_VERSION = 1
MAX_RECENT_MODELS = 10


def load_settings() -> dict:
    """Read the settings document, tolerating a missing or corrupt file."""
    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(**changes: object) -> None:
    """Merge `changes` into the settings file. Never raises.

    One file for all GUI state -- a read-only home is not worth failing the
    UI over, so write errors are swallowed.
    """
    data = load_settings()
    data.update(changes)
    data["version"] = SETTINGS_VERSION
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def _load_saved_theme() -> str:
    name = load_settings().get("theme")
    return name if name in THEMES else DEFAULT_THEME


def _save_theme(name: str) -> None:
    save_settings(theme=name)


def recent_models() -> list[str]:
    """Models used before, most recent first. Seeds the dropdown offline."""
    values = load_settings().get("recent_models")
    return [m for m in values if isinstance(m, str)] if isinstance(values, list) else []


def remember_model(name: str) -> None:
    """Push `name` to the front of the MRU list, de-duplicated and capped."""
    name = (name or "").strip()
    if not name:
        return
    ordered = [name] + [m for m in recent_models() if m != name]
    save_settings(recent_models=ordered[:MAX_RECENT_MODELS], llm_model=name)


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
    style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Bg.TCheckbutton", background=BG, foreground=MUTED)
    style.map("Bg.TCheckbutton", background=[("active", BG)],
              foreground=[("active", FG)],
              indicatorcolor=[("selected", ACCENT), ("!selected", FIELD)])
    # Bchips-style elements: flat cards with a small muted heading instead of a
    # bordered LabelFrame, a big app title, and a status strip.
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("CardHeading.TLabel", background=SURFACE, foreground=MUTED,
                    font=FONT_SECTION)
    style.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_TITLE)
    style.configure("Subtle.TLabel", background=BG, foreground=MUTED)
    style.configure("Dot.TLabel", background=SURFACE, foreground=MUTED, font=FONT_DOT)
    style.configure("State.TLabel", background=SURFACE, foreground=FG, font=FONT_STATE)
    style.configure("Badge.TLabel", background=FIELD, foreground=FG, font=FONT_MONO,
                    padding=(8, 3))
    style.configure("Divider.TFrame", background=BORDER)

    # Folder picker list.
    style.configure("Treeview", background=FIELD, fieldbackground=FIELD,
                    foreground=FG, borderwidth=0, rowheight=26, font=FONT_UI)
    style.map("Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", ON_ACCENT)])
    style.configure("Treeview.Heading", background=NEUTRAL, foreground=MUTED,
                    relief="flat", font=FONT_SECTION)
    style.map("Treeview.Heading", background=[("active", NEUTRAL_HOVER)])

    # Notebook: tabs sit on the window background and the selected one takes the
    # card surface, so it reads as physically connected to the panel below.
    style.configure("TNotebook", background=BG, borderwidth=0,
                    tabmargins=(0, 0, 0, 0), padding=0)
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                    padding=(18, 10), borderwidth=0, font=FONT_UI)
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE), ("active", NEUTRAL)],
              foreground=[("selected", FG), ("active", FG)],
              expand=[("selected", (0, 0, 0, 0))])
    # Drop the dotted focus ring clam draws inside a selected tab.
    try:
        style.layout("TNotebook.Tab", [
            ("Notebook.tab", {"sticky": "nswe", "children": [
                ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
                    ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
    except tk.TclError:
        pass
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
                    relief="flat", padding=(14, 10), font=FONT_BOLD, anchor="center")
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
                        insertcolor=FG, arrowcolor=MUTED, relief="flat", padding=(8, 6))
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
                    bordercolor=SURFACE, arrowcolor=MUTED, relief="flat", width=12)
    style.map("Vertical.TScrollbar", background=[("active", MUTED)])
    # A bare trough + thumb. clam's stepper arrows at each end are the most
    # dated widget in the stock theme.
    try:
        style.layout("Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    except tk.TclError:
        pass


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
for i in range(6):
    main.rowconfigure(i, weight=0)
main.rowconfigure(4, weight=1)          # the log takes the slack

source_var = tk.StringVar()
dest_var = tk.StringVar()

def choose_directory(title: str, initial: str = "") -> str:
    """A themed replacement for filedialog.askdirectory().

    Tk's own chooser is drawn with classic widgets that ignore ttk styling, so
    it always arrived in the system palette with an unreadable path bar. This
    one is an ordinary Toplevel and therefore follows the active theme.
    Returns "" if cancelled.
    """
    start = Path(initial).expanduser() if initial else Path.home()
    while not start.is_dir() and start != start.parent:
        start = start.parent
    if not start.is_dir():
        start = Path.home()

    chosen = {"path": ""}
    current = {"path": start}

    win = tk.Toplevel(root)
    win.title(title)
    win.transient(root)
    win.configure(bg=BG)
    win.geometry("660x470")
    win.minsize(460, 320)
    win.columnconfigure(0, weight=1)
    win.rowconfigure(2, weight=1)

    bar = ttk.Frame(win, style="App.TFrame", padding=(PAD_X, PAD_Y))
    bar.grid(row=0, column=0, sticky="ew")
    bar.columnconfigure(1, weight=1)
    ttk.Label(bar, text="Folder:", style="Subtle.TLabel").grid(row=0, column=0, padx=(0, PAD_X))
    path_var = tk.StringVar(value=str(start))
    path_entry = ttk.Entry(bar, textvariable=path_var)
    path_entry.grid(row=0, column=1, sticky="ew")

    nav = ttk.Frame(win, style="App.TFrame", padding=(PAD_X, 0))
    nav.grid(row=1, column=0, sticky="ew")
    nav.columnconfigure(3, weight=1)
    show_hidden = tk.BooleanVar(value=False)

    listing = ttk.Frame(win, style="App.TFrame", padding=(PAD_X, PAD_Y))
    listing.grid(row=2, column=0, sticky="nsew")
    listing.columnconfigure(0, weight=1)
    listing.rowconfigure(0, weight=1)
    tree = ttk.Treeview(listing, show="tree", selectmode="browse")
    tree.grid(row=0, column=0, sticky="nsew")
    bar2 = ttk.Scrollbar(listing, orient="vertical", command=tree.yview)
    bar2.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=bar2.set)

    def populate(path: Path) -> None:
        current["path"] = path
        path_var.set(str(path))
        tree.delete(*tree.get_children())
        try:
            entries = sorted(
                (c for c in path.iterdir() if c.is_dir()),
                key=lambda c: c.name.lower(),
            )
        except (PermissionError, OSError) as exc:
            tree.insert("", "end", text=f"  cannot open: {exc}", tags=("err",))
            return
        if path.parent != path:
            tree.insert("", "end", iid="..", text="  \u2191  ..")
        for child in entries:
            if not show_hidden.get() and child.name.startswith("."):
                continue
            tree.insert("", "end", iid=str(child), text=f"  \U0001F4C1  {child.name}")

    def descend(_event: object = None) -> None:
        sel = tree.focus()
        if not sel:
            return
        target = current["path"].parent if sel == ".." else Path(sel)
        if target.is_dir():
            populate(target)

    def go_typed(_event: object = None) -> None:
        candidate = Path(path_var.get()).expanduser()
        if candidate.is_dir():
            populate(candidate)

    def accept(_event: object = None) -> None:
        chosen["path"] = str(current["path"])
        win.destroy()

    tree.bind("<Double-1>", descend)
    tree.bind("<Return>", descend)
    path_entry.bind("<Return>", go_typed)
    win.bind("<Escape>", lambda _e: win.destroy())

    ttk.Button(nav, text="\u2191  Up", cursor="hand2",
               command=lambda: populate(current["path"].parent)).grid(row=0, column=0)
    ttk.Button(nav, text="\u2302  Home", cursor="hand2",
               command=lambda: populate(Path.home())).grid(row=0, column=1, padx=(PAD_X, 0))
    ttk.Button(nav, text="Open", cursor="hand2",
               command=descend).grid(row=0, column=2, padx=(PAD_X, 0))
    ttk.Checkbutton(nav, text="Show hidden", variable=show_hidden,
                    command=lambda: populate(current["path"]),
                    style="Bg.TCheckbutton").grid(row=0, column=4, sticky="e")

    foot = ttk.Frame(win, style="App.TFrame", padding=(PAD_X, PAD_Y))
    foot.grid(row=3, column=0, sticky="ew")
    foot.columnconfigure(0, weight=1)
    ttk.Button(foot, text="Cancel", cursor="hand2",
               command=win.destroy).grid(row=0, column=1)
    ttk.Button(foot, text="Select folder", style="Primary.TButton", cursor="hand2",
               command=accept).grid(row=0, column=2, padx=(PAD_X, 0))

    populate(start)
    win.update_idletasks()
    win.geometry(f"+{root.winfo_rootx() + 60}+{root.winfo_rooty() + 60}")
    path_entry.focus_set()
    win.grab_set()
    win.wait_window()
    return chosen["path"]


def browse_src():
    path = choose_directory("Choose source folder", source_var.get())
    if path:
        source_var.set(path)
        save_settings(source=path)

def browse_dst():
    path = choose_directory("Choose destination folder", dest_var.get())
    if path:
        dest_var.set(path)
        save_settings(dest=path)


def card(parent, heading: str, row: int, *, sticky: str = "ew", pady=(PAD_Y, 0)):
    """A flat surface with a small muted heading.

    Replaces ttk.LabelFrame, whose engraved border and inline title read as
    heavier and older than the rest of the UI.
    """
    holder = ttk.Frame(parent, style="Card.TFrame", padding=PAD_X)
    holder.grid(row=row, column=0, sticky=sticky, pady=pady)
    ttk.Label(holder, text=heading, style="CardHeading.TLabel").grid(
        row=0, column=0, columnspan=6, sticky="w", pady=(0, PAD_Y)
    )
    body = ttk.Frame(holder, style="Card.TFrame")
    body.grid(row=1, column=0, sticky="nsew")
    holder.columnconfigure(0, weight=1)
    holder.rowconfigure(1, weight=1)
    return holder, body


def divider(parent, row: int, columnspan: int = 6):
    """The 1px rule Bchips uses to separate groups inside a card."""
    ttk.Frame(parent, style="Divider.TFrame", height=1).grid(
        row=row, column=0, columnspan=columnspan, sticky="ew", pady=PAD_Y
    )


# ── app header ──────────────────────────────────────────────────────────────
header = ttk.Frame(main, style="App.TFrame")
header.grid(row=0, column=0, sticky="ew", pady=(0, PAD_Y))
header.columnconfigure(1, weight=1)
ttk.Label(header, text="\U0001F3A7  ABtools", style="Title.TLabel").grid(row=0, column=0, sticky="w")
ttk.Label(header, text=f"v{VERSION}", style="Subtle.TLabel").grid(row=0, column=2, sticky="e")

# ── status strip ────────────────────────────────────────────────────────────
status_strip = ttk.Frame(main, style="Card.TFrame", padding=(PAD_X, PAD_Y))
status_strip.grid(row=1, column=0, sticky="ew", pady=(0, PAD_Y))
status_strip.columnconfigure(3, weight=1)
ttk.Label(status_strip, text="Status", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
state_dot = ttk.Label(status_strip, text="\u25cf", style="Dot.TLabel")
state_dot.grid(row=0, column=1, padx=(PAD_X, 4))
state_label = ttk.Label(status_strip, text="IDLE", style="State.TLabel")
state_label.grid(row=0, column=2, sticky="w")
operation_badge = ttk.Label(status_strip, text="ready", style="Badge.TLabel")
operation_badge.grid(row=0, column=4, sticky="e")


def LOG_BLUE_FOR_STATE() -> str:
    return THEMES[CURRENT_THEME]["log_blue"]


def set_state(text: str, colour: str = "", operation: str = "") -> None:
    """Update the status strip. Called only from the UI thread."""
    state_label.configure(text=text.upper())
    state_dot.configure(foreground=colour or MUTED)
    if operation:
        operation_badge.configure(text=operation)


paths_holder, paths_frame = card(main, "File Paths", 2, pady=(0, 0))
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
# Flags that previously existed only on the command line.
no_var = tk.BooleanVar()                       # search_and_tag --no
llm_threshold_var = tk.IntVar(value=85)        # search_and_tag --llm-threshold
debug_var = tk.BooleanVar()                    # search_and_tag --debug
show_files_var = tk.BooleanVar()               # find_duplicates --show-files
overwrite_var = tk.BooleanVar()                # repair_m4b --overwrite
bitrate_var = tk.StringVar(value="64k")        # ab_encode -b
channels_var = tk.StringVar(value="1")         # ab_encode -c
workers_var = tk.IntVar(value=4)               # ab_encode -w
cleanup_var = tk.BooleanVar()                  # ab_encode --cleanup
api_key_var = tk.StringVar(value=CONFIG.llm_api_key or "")   # --llm-api-key
provider_var = tk.StringVar(value="LM Studio") # proposal.md Phase 3

def models_url(endpoint: str) -> str:
    """Derive the /v1/models URL from a chat-completions endpoint.

    urlsplit rather than string surgery, because people type all of
    ".../v1/chat/completions", a trailing slash, a bare ".../v1", a bare host,
    and path-prefixed deployments.
    """
    parts = urlsplit((endpoint or "").strip().rstrip("/"))
    path = parts.path
    for suffix in ("/chat/completions", "/completions"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    if not path.endswith("/v1"):
        path = path.rstrip("/") + "/v1"
    return urlunsplit((parts.scheme or "http", parts.netloc, path + "/models", "", ""))


def probe_models(endpoint: str) -> None:
    """Ask the server which models it has loaded, off the UI thread.

    Tkinter is not thread-safe, so the worker must not touch model_combo. It
    posts to output_queue and poll_queue applies the result on the UI thread.
    """
    if not endpoint:
        return
    url = models_url(endpoint)
    # Snapshot the key here, on the UI thread.
    headers = {}
    key = (api_key_var.get() or "").strip() or (CONFIG.llm_api_key or "")
    if key:
        headers["Authorization"] = f"Bearer {key}"

    def work() -> None:
        try:
            response = requests.get(url, headers=headers, timeout=4)
            response.raise_for_status()
            payload = response.json()
            names = sorted(
                str(item["id"])
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            )
            output_queue.put(("models", (names, None)))
        except Exception as exc:                      # offline is normal, not fatal
            output_queue.put(("models", (None, f"{type(exc).__name__}: {exc}")))

    threading.Thread(target=work, daemon=True).start()


def toggle_llm_controls() -> None:
    state = "normal" if use_llm_var.get() else "disabled"
    for widget in llm_controls:
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass


# ───────────── tabbed operations ────────────────────────────────────────────
# One tab per operation family. Previously every setting was shown at once even
# though most apply to a single operation (Timeout/Threads only affect Find
# Duplicates), which is what the tooltips had to keep explaining.
notebook = ttk.Notebook(main)
notebook.grid(row=3, column=0, sticky="ew", pady=(PAD_Y, 0))

tag_tab = ttk.Frame(notebook, padding=PAD_X)
organise_tab = ttk.Frame(notebook, padding=PAD_X)
dupes_tab = ttk.Frame(notebook, padding=PAD_X)
encode_tab = ttk.Frame(notebook, padding=PAD_X)
for _tab, _label in ((tag_tab, "Tag & Move"), (organise_tab, "Organise"),
                     (dupes_tab, "Duplicates"), (encode_tab, "Encode")):
    notebook.add(_tab, text=f"  {_label}  ")
    _tab.columnconfigure(3, weight=1)

def _fit_notebook(_event: object = None) -> None:
    """Size the notebook to the tab actually shown.

    ttk.Notebook otherwise reserves the height of its tallest tab, leaving a
    large dead area below the short ones (Organise needs 143px but was given
    the 447px that Tag & Move requires).
    """
    try:
        tab = notebook.nametowidget(notebook.select())
    except (tk.TclError, KeyError):
        return
    tab.update_idletasks()
    notebook.configure(height=max(tab.winfo_reqheight(), 140))


notebook.bind("<<NotebookTabChanged>>", _fit_notebook)


# ── Tag & Move ──────────────────────────────────────────────────────────────
tag_opts = ttk.Frame(tag_tab)
tag_opts.grid(row=0, column=0, columnspan=4, sticky="ew")
for _c in range(4):
    tag_opts.columnconfigure(_c, weight=1, uniform="tagopts")

tip(ttk.Checkbutton(tag_opts, text="Commit", variable=commit_var),
    "Actually write the changes.\n\nLeft unticked, Tag and Move run a full "
    "preview: they look everything up and print exactly what they would write, "
    "without touching a file."
    ).grid(row=0, column=0, sticky="w")
tip(ttk.Checkbutton(tag_opts, text="Copy", variable=copy_var),
    "Copy books into the destination instead of moving them, leaving the "
    "source untouched. Needs Commit."
    ).grid(row=0, column=1, sticky="w")
tip(ttk.Checkbutton(tag_opts, text="Auto-accept", variable=yes_var),
    "Accept every metadata match without asking (--yes).\n\nFaster for a big "
    "run, but a wrong match is written without you seeing it."
    ).grid(row=0, column=2, sticky="w")
tip(ttk.Checkbutton(tag_opts, text="Auto-decline", variable=no_var),
    "Decline every match that would otherwise prompt (--no).\n\nUse it to "
    "sweep a library and collect the uncertain books in the review log "
    "instead of answering each one."
    ).grid(row=0, column=3, sticky="w")

ttk.Label(tag_tab, text="LLM threshold:").grid(row=1, column=0, sticky="w", pady=(PAD_Y, 0))
threshold_spin = ttk.Spinbox(tag_tab, from_=80, to=100, textvariable=llm_threshold_var, width=6)
threshold_spin.grid(row=1, column=1, sticky="w", pady=(PAD_Y, 0))
Tooltip(threshold_spin,
        "Provider matches scoring below this are sent to the LLM, and if that "
        "cannot help you are asked to confirm.\n\nHigher means more checking "
        "and more prompts. Clamped to 80-100.")
tip(ttk.Checkbutton(tag_tab, text="Debug output", variable=debug_var),
    "Print full tracebacks and LLM diagnostics to the log."
    ).grid(row=1, column=2, sticky="w", pady=(PAD_Y, 0))

divider(tag_tab, 2, columnspan=4)
llm_frame = ttk.Frame(tag_tab)
llm_frame.grid(row=3, column=0, columnspan=4, sticky="ew")
llm_frame.columnconfigure(1, weight=1)
llm_frame.columnconfigure(3, weight=1)
ttk.Label(llm_frame, text="Model", style="CardHeading.TLabel").grid(
    row=0, column=0, columnspan=4, sticky="w", pady=(0, PAD_Y))

llm_controls: list[tk.Widget] = []

ttk.Checkbutton(
    llm_frame,
    text="Enable LLM fallback",
    variable=use_llm_var,
    command=lambda: toggle_llm_controls(),
).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, PAD_Y))

# proposal.md Phase 3 -- local runners only, per the local-only scope decision.
PROVIDER_PRESETS = {
    "LM Studio": "http://127.0.0.1:1234/v1/chat/completions",
    "LM Studio (ABtools default)": "http://127.0.0.1:8888/v1/chat/completions",
    "Ollama": "http://127.0.0.1:11434/v1/chat/completions",
    "vLLM": "http://127.0.0.1:8000/v1/chat/completions",
    # Hosted. Needs an API key; everything above ignores one.
    "OpenRouter": "https://openrouter.ai/api/v1/chat/completions",
}
REMOTE_PROVIDERS = {"OpenRouter"}

ttk.Label(llm_frame, text="Provider:").grid(row=2, column=0, sticky="e", padx=(0, PAD_X), pady=(0, PAD_Y))
provider_combo = ttk.Combobox(llm_frame, textvariable=provider_var,
                              values=list(PROVIDER_PRESETS), state="readonly")
provider_combo.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0, PAD_Y))
llm_controls.append(provider_combo)

ttk.Label(llm_frame, text="Endpoint:").grid(row=3, column=0, sticky="e", padx=(0, PAD_X), pady=(0, PAD_Y))
endpoint_entry = ttk.Entry(llm_frame, textvariable=llm_endpoint_var)
endpoint_entry.grid(row=3, column=1, columnspan=3, sticky="ew", pady=(0, PAD_Y))
llm_controls.append(endpoint_entry)

ttk.Label(llm_frame, text="Model:").grid(row=4, column=0, sticky="e", padx=(0, PAD_X), pady=(0, PAD_Y))
# Seeded from previously-used models so the dropdown is useful before any
# probe returns, and replaced by the server's real list once one does.
model_combo = ttk.Combobox(llm_frame, textvariable=llm_model_var,
                           values=recent_models() or [DEFAULT_LLM_MODEL])
model_combo.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(0, PAD_Y))
llm_controls.append(model_combo)

refresh_button = ttk.Button(llm_frame, text="\u21bb", width=3,
                            command=lambda: refresh_models(explicit=True))
refresh_button.grid(row=4, column=3, sticky="e", padx=(PAD_X // 2, 0), pady=(0, PAD_Y))
llm_controls.append(refresh_button)

endpoint_status = tk.StringVar(value="")
ttk.Label(llm_frame, textvariable=endpoint_status, style="Muted.TLabel").grid(
    row=5, column=1, columnspan=3, sticky="w"
)

ttk.Label(llm_frame, text="API key:").grid(row=6, column=0, sticky="e", padx=(0, PAD_X), pady=(PAD_Y, 0))
api_key_entry = ttk.Entry(llm_frame, textvariable=api_key_var, show="\u2022")
api_key_entry.grid(row=6, column=1, columnspan=3, sticky="ew", pady=(PAD_Y, 0))
llm_controls.append(api_key_entry)
Tooltip(api_key_entry,
        "Bearer token for a hosted endpoint such as OpenRouter. Local servers "
        "(LM Studio, Ollama, vLLM) ignore it and can be left blank.\n\n"
        "Deliberately NOT saved to disk. Pre-filled from ABTOOLS_LLM_API_KEY or "
        "OPENROUTER_API_KEY if either is set, which is the safer way to supply it.")


def refresh_models(*, explicit: bool = False) -> None:
    """Ask the configured endpoint for its model list."""
    if not use_llm_var.get():
        return
    endpoint = (llm_endpoint_var.get() or "").strip()
    if not endpoint or endpoint.lower() in {"none", "null", "off"}:
        return
    if explicit:
        endpoint_status.set("checking...")
    probe_models(endpoint)


def _endpoint_changed(_event: object = None) -> None:
    """Probe when focus leaves the endpoint field, not on every keystroke."""
    endpoint = (llm_endpoint_var.get() or "").strip()
    if endpoint and endpoint != getattr(_endpoint_changed, "_last", None):
        _endpoint_changed._last = endpoint
        save_settings(llm_endpoint=endpoint)
        refresh_models()


def _provider_changed(_event: object = None) -> None:
    """Fill in the chosen provider's endpoint and probe it."""
    name = provider_var.get()
    endpoint = PROVIDER_PRESETS.get(name)
    if not endpoint:
        return
    llm_endpoint_var.set(endpoint)
    save_settings(llm_endpoint=endpoint, provider=name)
    if name in REMOTE_PROVIDERS and not (api_key_var.get() or "").strip():
        endpoint_status.set("hosted provider - an API key is required")
        api_key_entry.focus_set()
    refresh_models(explicit=True)


endpoint_entry.bind("<FocusOut>", _endpoint_changed, add="+")
provider_combo.bind("<<ComboboxSelected>>", _provider_changed)
Tooltip(provider_combo,
        "Fills in the endpoint for a known local runner and checks it.\n\n"
        "Local servers only - ABtools sends no authentication, so hosted "
        "providers are not supported.")
Tooltip(endpoint_entry,
        "URL of an OpenAI-compatible chat-completions endpoint.\n\n"
        f"Default: {DEFAULT_LLM_ENDPOINT}\nSet to 'none' to disable the fallback.")
Tooltip(model_combo,
        "Model to request from that endpoint. It must already be loaded there.\n\n"
        "The list is filled from the server when it can be reached, and falls "
        "back to models you have used before. You can always type a name.")
Tooltip(refresh_button,
        "Ask the endpoint which models it currently has loaded.\n\n"
        "Runs automatically when you finish editing the endpoint. If the "
        "server cannot be reached the list keeps your recent models.")

# ── Organise ────────────────────────────────────────────────────────────────
ttk.Label(organise_tab,
          text="Reshape an already-tagged library. None of these consult a provider.",
          style="Muted.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, PAD_Y))
tip(ttk.Checkbutton(organise_tab, text="Commit", variable=commit_var),
    "Shared with the Tag & Move tab. Unticked, every action here only "
    "reports what it would do."
    ).grid(row=1, column=0, sticky="w")
tip(ttk.Checkbutton(organise_tab, text="Copy", variable=copy_var),
    "Copy rather than move when restructuring."
    ).grid(row=1, column=1, sticky="w")
tip(ttk.Checkbutton(organise_tab, text="Overwrite originals", variable=overwrite_var),
    "Repair M4B only: rewrite the broken file in place, keeping a .bak "
    "alongside it.\n\nLeft off, a separate ' - fixed.m4b' is written and the "
    "original is untouched."
    ).grid(row=1, column=2, sticky="w")

# ── Duplicates ──────────────────────────────────────────────────────────────
ttk.Label(dupes_tab, text="Compare by:").grid(row=0, column=0, sticky="w")
compare_combo = ttk.Combobox(dupes_tab, textvariable=compare_by_var,
                             values=("hash", "name"), state="readonly", width=8)
compare_combo.grid(row=0, column=1, sticky="w", padx=(0, PAD_X * 2))
Tooltip(compare_combo,
        "hash - compares SHA1 contents. Accurate and catches renamed files, "
        "but must read every candidate.\n"
        "name - file names only. Much faster, but misses renames and can flag "
        "unrelated files that share a name.")

ttk.Label(dupes_tab, text="Threads:").grid(row=0, column=2, sticky="w", padx=(0, PAD_X))
threads_spin = ttk.Spinbox(dupes_tab, from_=1, to=64, textvariable=threads_var, width=5)
threads_spin.grid(row=0, column=3, sticky="w")
Tooltip(threads_spin,
        "How many files to hash in parallel.\n\nHigher is faster on local "
        "disks, kinder to a network share when lower.")

ttk.Label(dupes_tab, text="Timeout (s):").grid(row=1, column=0, sticky="w", pady=(PAD_Y, 0))
timeout_spin = ttk.Spinbox(dupes_tab, from_=0, to=600, textvariable=timeout_var,
                           width=6, increment=5)
timeout_spin.grid(row=1, column=1, sticky="w", pady=(PAD_Y, 0))
Tooltip(timeout_spin,
        "Per-file read timeout while hashing.\n\nOnly applies when Network "
        "Mode is ticked. 0 means no timeout.")

dupe_opts = ttk.Frame(dupes_tab)
dupe_opts.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(PAD_Y, 0))
for _c in range(4):
    dupe_opts.columnconfigure(_c, weight=1, uniform="dupeopts")
tip(ttk.Checkbutton(dupe_opts, text="Recurse", variable=recurse_var),
    "Search sub-folders as well as the top level."
    ).grid(row=0, column=0, sticky="w")
tip(ttk.Checkbutton(dupe_opts, text="Network Mode", variable=network_var),
    "Treat the source as a network share and enforce the Timeout above.\n\n"
    "Without this a stalled share can hang the scan indefinitely."
    ).grid(row=0, column=1, sticky="w")
tip(ttk.Checkbutton(dupe_opts, text="Only src log", variable=only_src_log_var),
    "Limit the scan to files already listed in the source's "
    "duplicate_log.txt, instead of walking the folder again."
    ).grid(row=0, column=2, sticky="w")
tip(ttk.Checkbutton(dupe_opts, text="Show files", variable=show_files_var),
    "Print every file as it is checked. Useful on a slow share to see "
    "progress; noisy on a large library."
    ).grid(row=0, column=3, sticky="w")

# ── Encode ──────────────────────────────────────────────────────────────────
ttk.Label(encode_tab,
          text="Combine each folder's audio into a single .m4b (needs ffmpeg).",
          style="Muted.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, PAD_Y))

ttk.Label(encode_tab, text="Bitrate:").grid(row=1, column=0, sticky="w")
bitrate_combo = ttk.Combobox(encode_tab, textvariable=bitrate_var,
                             values=("32k", "48k", "64k", "96k", "128k"), width=8)
bitrate_combo.grid(row=1, column=1, sticky="w", padx=(0, PAD_X * 2))
Tooltip(bitrate_combo,
        "AAC bitrate for re-encoding. 64k mono is ample for speech.\n\n"
        "Ignored when the sources are already AAC, which are copied losslessly.")

ttk.Label(encode_tab, text="Channels:").grid(row=1, column=2, sticky="w", padx=(0, PAD_X))
channels_combo = ttk.Combobox(encode_tab, textvariable=channels_var,
                              values=("1", "2"), state="readonly", width=4)
channels_combo.grid(row=1, column=3, sticky="w")
Tooltip(channels_combo, "1 = mono (right for almost all audiobooks), 2 = stereo.")

ttk.Label(encode_tab, text="Workers:").grid(row=2, column=0, sticky="w", pady=(PAD_Y, 0))
workers_spin = ttk.Spinbox(encode_tab, from_=1, to=16, textvariable=workers_var, width=5)
workers_spin.grid(row=2, column=1, sticky="w", pady=(PAD_Y, 0))
Tooltip(workers_spin, "How many folders to encode at once.")

tip(ttk.Checkbutton(encode_tab, text="Delete sources after verify", variable=cleanup_var),
    "DANGER: removes the original audio files once the .m4b has been written "
    "and verified by ffprobe.\n\nLeave off unless you have a backup."
    ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(PAD_Y, 0))

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
    if running:
        set_state("running", LOG_BLUE_FOR_STATE())
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


log_holder, log_frame = card(main, "Log", 4, sticky="nsew")
log_frame.columnconfigure(0, weight=1)
log_frame.rowconfigure(0, weight=1)

output_text = tk.Text(
    log_frame,
    height=9,
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
    padx=12,
    pady=10,
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
    row=0, column=2, sticky="e", padx=(0, PAD_X)
)

# Stop lives here rather than on a tab: a run started from one tab must be
# stoppable from any of them.
stop_button = ttk.Button(status_row, text="\u23f9  Stop", style="Danger.TButton",
                         command=stop_current, state="disabled")
stop_button.grid(row=0, column=3, sticky="e")
Tooltip(stop_button,
        "Ask the running job to stop.\n\nIt finishes the file it is on first, "
        "so it may take a moment. Work already written is left as it is.")

toggle_llm_controls()
root.update_idletasks()
root.minsize(660, 640)

def gather_llm_settings() -> dict[str, object]:
    enabled = bool(use_llm_var.get())
    endpoint = (llm_endpoint_var.get() or "").strip()
    model = (llm_model_var.get() or "").strip()
    # debug/api_key are read here, on the UI thread: apply_llm_settings() is
    # called from inside a worker, and a tk variable read there raises
    # "main thread is not in main loop".
    extra = {"debug": bool(debug_var.get()), "api_key": (api_key_var.get() or "").strip()}
    if not enabled:
        return {"enabled": False, "endpoint": "none", "model": "", **extra}
    return {"enabled": True, "endpoint": endpoint, "model": model, **extra}


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

    CONFIG.debug = bool(settings.get("debug", False))
    # An empty box leaves whatever the environment supplied.
    _key = str(settings.get("api_key", "") or "").strip()
    if _key:
        CONFIG.llm_api_key = _key

    # Record the model actually used, so it seeds the dropdown next launch even
    # if the server is unreachable then.
    if enabled and CONFIG.llm_model_name:
        remember_model(CONFIG.llm_model_name)

    # No propagation needed: ablib.core.config.config is a module-level
    # singleton, so CONFIG here, combobook.tagger.CONFIG and ablib.cli.main
    # .CONFIG are all the same object (id-verified). The block that used to
    # copy values across was assigning the object's attributes to themselves.


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
        elif typ == "models":
            # Applied here, on the UI thread: the probe runs in a worker and
            # Tkinter is not thread-safe.
            names, error = msg
            if names:
                model_combo["values"] = names
                note = f"{len(names)} model(s) available"
                if llm_model_var.get() not in names:
                    note = f"{len(names)} available - '{llm_model_var.get()}' not among them"
                # OpenRouter serves its model list without auth, so a successful
                # probe says nothing about whether completions will work. Keep
                # the missing-key warning visible rather than letting the model
                # count overwrite it.
                if (provider_var.get() in REMOTE_PROVIDERS
                        and not (api_key_var.get() or "").strip()):
                    note += "  \u2022  API key required to run"
                endpoint_status.set(note)
            else:
                fallback = recent_models()
                if fallback:
                    model_combo["values"] = fallback
                endpoint_status.set("endpoint unreachable")
                if CONFIG.debug and error:
                    append_output(f"[dim]model probe failed: {error}[/]\n")
        elif typ == "status":
            if msg == "done":
                set_running(False)
                set_state("done", THEMES[CURRENT_THEME]["log_green"])
                eta_var.set("ETA: --:--")
                try:
                    messagebox.showinfo("Done", "Processing finished")
                except Exception:
                    pass
            elif msg == "stopped":
                set_running(False)
                set_state("stopped", THEMES[CURRENT_THEME]["log_yellow"])
                eta_var.set("Stopped")
                try:
                    messagebox.showinfo("Stopped", "Processing cancelled")
                except Exception:
                    pass
            elif msg.startswith("error:"):
                set_running(False)
                set_state("error", THEMES[CURRENT_THEME]["log_red"])
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
    # Snapshot on the UI thread -- see the note in find_dupes().
    commit_flag = commit_var.get()
    copy_flag = copy_var.get()
    auto_yes_flag = yes_var.get()
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
                        yes=auto_yes_flag,
                        copy=copy_flag,
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
                action_word = "copied" if copy_flag else "moved"
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

    # Snapshot on the UI thread -- see the note in find_dupes().
    commit_flag = commit_var.get()
    copy_flag = copy_var.get()

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
                    dry=not commit_flag,
                    copy=copy_flag,
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
    # Snapshot on the UI thread -- see the note in find_dupes().
    commit_flag = commit_var.get()
    auto_yes_flag = yes_var.get()
    tag_args = SimpleNamespace(
        commit=commit_flag, yes=auto_yes_flag, no=no_var.get(), striptags=False,
        llm_endpoint=None, llm_model=None,
        llm_threshold=llm_threshold_var.get(), debug=debug_var.get(),
    )

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
                args = tag_args
                args.llm_endpoint = CONFIG.llm_endpoint
                args.llm_model = CONFIG.llm_model_name

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
                    # process_leaf previews when args.commit is False: it still
                    # runs the lookups and prints what it *would* write.
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

    # Snapshot every setting on the UI thread. Reading a tk variable from a
    # worker raises "main thread is not in main loop" -- on_file in particular
    # runs deep inside find_duplicates, on the worker.
    show_files = show_files_var.get()
    net_timeout = float(timeout_var.get()) if network_var.get() else None
    by = (compare_by_var.get() or "hash").strip().lower() or "hash"
    threads = max(1, int(threads_var.get() or 1))
    recursive = recurse_var.get()
    only_src_log = only_src_log_var.get()

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(QueueWriter(output_queue)):

                def on_file(stage: str, p: Path) -> None:
                    # Quiet unless asked: on a large library this is thousands
                    # of lines and drowns the result. `show_files` is captured
                    # on the UI thread -- see _snapshot below.
                    if show_files and ("hash" in stage or "scan" in stage):
                        print(f"Checking: {p}")

                label = "name" if by == "name" else "SHA1"
                limit_set = None
                if only_src_log:
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
                        recursive=recursive,
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
def _require_source() -> Path | None:
    """Validate the Source field once, instead of in every handler."""
    text = (source_var.get() or "").strip()
    if not text:
        messagebox.showerror("Error", "Source path is required")
        return None
    path = Path(text).expanduser()
    if not path.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return None
    return path


def _begin_run(operation: str = "") -> None:
    """Clear the log and reset progress before a run."""
    if operation:
        set_state("running", LOG_BLUE_FOR_STATE(), operation)
    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")


def _run_in_worker(job: Callable[[], None]) -> None:
    """Run `job` with stdout/stderr piped into the log pane."""
    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(QueueWriter(output_queue)):
                job()
            output_queue.put(("status", "stopped" if stop_event.is_set() else "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))
    start_worker(worker)


def strip_tags_run() -> None:
    """search_and_tag --striptags, which had no GUI equivalent at all."""
    src = _require_source()
    if src is None:
        return
    if commit_var.get() and not messagebox.askyesno(
        "Strip tags",
        "This deletes ALL tags from every audio file under:\n\n"
        f"{src}\n\nThis cannot be undone. Continue?",
    ):
        return
    _begin_run("strip tags")
    args = SimpleNamespace(commit=commit_var.get(), yes=True, no=False, striptags=True,
                           llm_endpoint=None, llm_model=None,
                           llm_threshold=llm_threshold_var.get(), debug=debug_var.get())

    def job() -> None:
        leaves = tag_cli.walk_leaves(src)
        tag_cli.rprint(f"[cyan]Stripping tags in {len(leaves)} folder(s).[/]")
        for idx, leaf in enumerate(leaves, 1):
            if stop_event.is_set():
                tag_cli.rprint("\n[yellow]Stop requested.[/]")
                return
            tag_cli.process_leaf(leaf, args)
            output_queue.put(("progress", (idx, len(leaves), 0)))
    _run_in_worker(job)


def flatten_run() -> None:
    """flatten_discs.py -- merges Disc 01/Disc 02 folders into one book."""
    src = _require_source()
    if src is None:
        return
    _begin_run("flatten discs")
    # Snapshot on the UI thread: reading a tk variable from a worker raises
    # "main thread is not in main loop".
    commit = commit_var.get()

    def job() -> None:
        print(f"{'Flattening' if commit else 'Previewing'} disc folders under {src}")
        flatten_discs.main(src, commit=commit, auto_yes=True)
    _run_in_worker(job)


def repair_run() -> None:
    """repair_m4b.py -- rewrites M4B files mutagen cannot parse."""
    src = _require_source()
    if src is None:
        return
    _begin_run("repair m4b")
    overwrite = overwrite_var.get()          # snapshot on the UI thread

    def job() -> None:
        targets = list(repair_m4b.iter_targets(src))
        print(f"Checking {len(targets)} .m4b/.mp4 file(s)...")
        repaired = clean = failed = 0
        for idx, path in enumerate(targets, 1):
            if stop_event.is_set():
                print("\nStop requested.")
                break
            try:
                outcome = repair_m4b.repair_file(path, overwrite=overwrite)
                if outcome.get("status") == "repaired":
                    repaired += 1
                    print(f"[FIXED] {path}: {outcome.get('message','')}")
                else:
                    clean += 1
            except RuntimeError as exc:
                failed += 1
                print(f"[ERROR] {path}: {exc}")
            output_queue.put(("progress", (idx, len(targets), 0)))
        print(f"\nRepaired: {repaired}, clean: {clean}, failed: {failed}")
    _run_in_worker(job)


def encode_run() -> None:
    """ab_encode.py -- builds one .m4b per folder."""
    src = _require_source()
    if src is None:
        return
    if cleanup_var.get() and not messagebox.askyesno(
        "Delete sources",
        "'Delete sources after verify' is on: the original audio files will be "
        "removed once each .m4b is written and verified.\n\nContinue?",
    ):
        return
    _begin_run("encode m4b")
    # Snapshot every setting on the UI thread before the worker starts.
    bitrate, channels = bitrate_var.get(), channels_var.get()
    workers, cleanup = max(1, workers_var.get()), cleanup_var.get()

    def job() -> None:
        import os
        folders = [r for r, _, files in os.walk(src)
                   if any(f.lower().endswith(ab_encode.EXTENSIONS) for f in files)]
        print(f"Encoding {len(folders)} folder(s) at {bitrate}, "
              f"{'mono' if channels == '1' else 'stereo'}")
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(ab_encode.process_folder, f,
                                   bitrate=bitrate,
                                   channels=channels,
                                   cleanup=cleanup): f for f in folders}
            for future in as_completed(futures):
                if stop_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    print("\nStop requested.")
                    break
                result = future.result()
                done += 1
                print(f"  [{done}/{len(folders)}] {result['status']} - {result['folder']}")
                output_queue.put(("progress", (done, len(folders), 0)))
    _run_in_worker(job)


# ── action buttons, each on the tab it belongs to ───────────────────────────
def _actions(parent, row, buttons):
    """Lay out a tab's action buttons in one evenly-sized row."""
    bar = ttk.Frame(parent)
    bar.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(PAD_Y * 2, 0))
    for i in range(len(buttons)):
        bar.columnconfigure(i, weight=1, uniform="act")
    made = []
    for i, (label, style, command, help_text) in enumerate(buttons):
        b = ttk.Button(bar, text=label, command=command, cursor="hand2",
                       **({"style": style} if style else {}))
        b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else PAD_X, 0))
        Tooltip(b, help_text)
        made.append(b)
    return made

tag_button, move_button = _actions(tag_tab, 4, [
    ("\u25b6  Tag", "Primary.TButton", lambda: tag_only(),
     "Look up metadata and write tags in place, without moving anything.\n\n"
     "Unticking Commit previews it: you see the guess, provider scores and the "
     "exact metadata that would be written, and nothing is touched."),
    ("\u2192  Move", None, lambda: run(),
     "Tag each book, then move it into the destination as Author/Title (Year), "
     "merging any disc sub-folders.\n\nTick Copy to leave the source in place."),
])

restructure_button, flatten_button, striptags_button, repair_button = _actions(organise_tab, 2, [
    ("\u2637  Restructure", None, lambda: restructure(),
     "Reorganise an already-tagged library into Author/Year - Title, using "
     "existing tags, metadata.json or the folder name. No metadata lookup."),
    ("\u29c9  Flatten Discs", None, lambda: flatten_run(),
     "Merge 'Disc 01'/'Disc 02' sub-folders into a single book folder with "
     "sequentially numbered tracks."),
    ("\u2717  Strip Tags", "Danger.TButton", lambda: strip_tags_run(),
     "Delete ALL tags from every audio file under Source.\n\n"
     "Cannot be undone; asks for confirmation when Commit is on."),
    ("\u2692  Repair M4B", None, lambda: repair_run(),
     "Rewrite .m4b/.mp4 files that mutagen refuses to read (the "
     "'zero length atom' error), using ffmpeg."),
])

dup_button, = _actions(dupes_tab, 3, [
    ("\u26b2  Find Duplicates", "Primary.TButton", lambda: find_dupes(),
     "Find duplicate audio files.\n\nWith a Destination set, compares the two "
     "folders against each other; otherwise scans Source alone. Results go to "
     "duplicate_log.txt - nothing is ever deleted."),
])

encode_button, = _actions(encode_tab, 3, [
    ("\u2699  Encode to M4B", "Primary.TButton", lambda: encode_run(),
     "Combine each folder's audio into one .m4b via ffmpeg, verifying the "
     "result with ffprobe.\n\nAlready-AAC sources are copied losslessly "
     "rather than re-encoded."),
])

action_buttons.extend([tag_button, move_button, restructure_button, flatten_button,
                       striptags_button, repair_button, dup_button, encode_button])

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
    # Restore the previous session: paths, options, endpoint/model, geometry.
    # Everything except Commit, which is deliberately never restored -- writing
    # to a library must be an explicit choice each run, not something a previous
    # session silently left switched on.
    _saved = load_settings()
    for _key, _var in (("source", source_var), ("dest", dest_var),
                       ("llm_endpoint", llm_endpoint_var), ("llm_model", llm_model_var)):
        _value = _saved.get(_key)
        if isinstance(_value, str) and _value.strip():
            _var.set(_value)
    # `cleanup` (deletes source audio) and the API key are deliberately not
    # restored -- like Commit, destructive or secret settings should be a
    # fresh decision each run.
    for _key, _var in (("copy", copy_var), ("yes", yes_var), ("recurse", recurse_var),
                       ("network", network_var), ("only_src_log", only_src_log_var),
                       ("use_llm", use_llm_var), ("no", no_var), ("debug", debug_var),
                       ("show_files", show_files_var), ("overwrite", overwrite_var)):
        if isinstance(_saved.get(_key), bool):
            _var.set(_saved[_key])
    for _key, _var in (("timeout", timeout_var), ("threads", threads_var),
                       ("llm_threshold", llm_threshold_var), ("workers", workers_var)):
        if isinstance(_saved.get(_key), int):
            _var.set(_saved[_key])
    for _key, _var in (("bitrate", bitrate_var), ("channels", channels_var),
                       ("provider", provider_var)):
        if isinstance(_saved.get(_key), str) and _saved[_key]:
            _var.set(_saved[_key])
    if isinstance(_saved.get("compare_by"), str) and _saved["compare_by"] in ("hash", "name"):
        compare_by_var.set(_saved["compare_by"])
    if isinstance(_saved.get("geometry"), str):
        try:
            root.geometry(_saved["geometry"])
        except tk.TclError:
            pass
    toggle_llm_controls()

    def _persist_and_close() -> None:
        save_settings(
            source=source_var.get(), dest=dest_var.get(),
            copy=copy_var.get(), yes=yes_var.get(), recurse=recurse_var.get(),
            network=network_var.get(), only_src_log=only_src_log_var.get(),
            use_llm=use_llm_var.get(), timeout=timeout_var.get(),
            threads=threads_var.get(), compare_by=compare_by_var.get(),
            llm_endpoint=llm_endpoint_var.get(), llm_model=llm_model_var.get(),
            no=no_var.get(), llm_threshold=llm_threshold_var.get(),
            debug=debug_var.get(), show_files=show_files_var.get(),
            overwrite=overwrite_var.get(), bitrate=bitrate_var.get(),
            channels=channels_var.get(), workers=workers_var.get(),
            provider=provider_var.get(),
            geometry=root.winfo_geometry(),
        )
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _persist_and_close)

    poll_queue()
    # Probe shortly after the window appears rather than before it: the request
    # is local-only and runs on a worker with a short timeout, so it can never
    # delay or block the UI.
    root.after(300, refresh_models)
    root.mainloop()
