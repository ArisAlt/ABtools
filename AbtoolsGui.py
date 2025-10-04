#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py v0.20  (2025-10-04)
"""
from __future__ import annotations

import sys
import threading
import queue
import time
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

import combobook, search_and_tag, find_duplicates, restructure_for_audiobookshelf

VERSION = "0.20"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

DEFAULT_LLM_ENDPOINT = (
    search_and_tag.LLM_ENDPOINT
    or "http://127.0.0.1:1234/v1/chat/completions"
)
DEFAULT_LLM_MODEL = search_and_tag.LLM_MODEL_NAME or "mistral-7b-instruct-q4"
DEFAULT_LLM_THRESHOLD = 75
DEFAULT_WHISPER_MODEL = search_and_tag.WHISPER_MODEL_NAME or search_and_tag.DEFAULT_WHISPER_MODEL
DEFAULT_WHISPER_DEVICE = search_and_tag.WHISPER_DEVICE or search_and_tag.DEFAULT_WHISPER_DEVICE

if "--version" in sys.argv:
    print(VERSION_INFO % {"prog": Path(sys.argv[0]).name})
    sys.exit(0)

root = tk.Tk()
root.title("ABtools GUI")
root.resizable(True, True)

style = ttk.Style(root)
style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 10))
style.configure("Action.TButton", padding=(12, 6))

root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

main = ttk.Frame(root, padding=12)
main.grid(row=0, column=0, sticky="nsew")
main.columnconfigure(0, weight=1)
main.rowconfigure(4, weight=1)

# ---------------------------------------------------------------------------
# Tk variables
source_var = tk.StringVar()
dest_var = tk.StringVar()

commit_var = tk.BooleanVar()
copy_var = tk.BooleanVar()
yes_var = tk.BooleanVar()
network_var = tk.BooleanVar()
recurse_var = tk.BooleanVar(value=True)
only_src_log_var = tk.BooleanVar()

timeout_var = tk.IntVar(value=30)
threads_var = tk.IntVar(value=4)
compare_by_var = tk.StringVar(value="hash")

llm_enabled_var = tk.BooleanVar(value=bool(search_and_tag.LLM_ENDPOINT))
llm_endpoint_var = tk.StringVar(value=DEFAULT_LLM_ENDPOINT)
llm_model_var = tk.StringVar(value=DEFAULT_LLM_MODEL)
llm_threshold_var = tk.IntVar(value=DEFAULT_LLM_THRESHOLD)
whisper_model_var = tk.StringVar(value=DEFAULT_WHISPER_MODEL)
whisper_device_var = tk.StringVar(value=DEFAULT_WHISPER_DEVICE)

llm_widgets: list[tk.Widget] = []


def register_llm_widget(widget: tk.Widget) -> tk.Widget:
    llm_widgets.append(widget)
    return widget


def on_llm_toggle(*_: object) -> None:
    enabled = bool(llm_enabled_var.get())
    state = "normal" if enabled else "disabled"
    for widget in llm_widgets:
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass

# ---------------------------------------------------------------------------
# File paths group
paths_frame = ttk.LabelFrame(main, text="File Paths", padding=10)
paths_frame.grid(row=0, column=0, sticky="ew")
paths_frame.columnconfigure(1, weight=1)


def browse_src() -> None:
    path = filedialog.askdirectory()
    if path:
        source_var.set(path)


def browse_dst() -> None:
    path = filedialog.askdirectory()
    if path:
        dest_var.set(path)

for r, (label, var, cmd) in enumerate((
    ("Source", source_var, browse_src),
    ("Destination", dest_var, browse_dst),
)):
    ttk.Label(paths_frame, text=label).grid(row=r, column=0, sticky="e", padx=6, pady=4)
    ttk.Entry(paths_frame, textvariable=var).grid(row=r, column=1, sticky="ew", padx=6, pady=4)
    ttk.Button(paths_frame, text="Browse", command=cmd).grid(row=r, column=2, padx=6, pady=4)

# ---------------------------------------------------------------------------
# Operation settings
ops_frame = ttk.LabelFrame(main, text="Operation Settings", padding=10)
ops_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
for col in range(4):
    ops_frame.columnconfigure(col, weight=1)

for idx, (label, var) in enumerate((
    ("Commit", commit_var),
    ("Copy", copy_var),
    ("Auto-accept", yes_var),
    ("Network mode", network_var),
    ("Only source log", only_src_log_var),
)):
    ttk.Checkbutton(ops_frame, text=label, variable=var).grid(row=0, column=idx, sticky="w", padx=4)

(ttk.Label(ops_frame, text="Timeout (s)")
 .grid(row=1, column=0, sticky="e", padx=4, pady=4))
timeout_spin = ttk.Spinbox(ops_frame, from_=0, to=3600, textvariable=timeout_var, width=6)
timeout_spin.grid(row=1, column=1, sticky="w", padx=4, pady=4)

(ttk.Label(ops_frame, text="Threads")
 .grid(row=1, column=2, sticky="e", padx=4, pady=4))
threads_spin = ttk.Spinbox(ops_frame, from_=1, to=32, textvariable=threads_var, width=5)
threads_spin.grid(row=1, column=3, sticky="w", padx=4, pady=4)

(ttk.Label(ops_frame, text="Compare by")
 .grid(row=2, column=0, sticky="e", padx=4, pady=4))
compare_combo = ttk.Combobox(
    ops_frame,
    textvariable=compare_by_var,
    values=("hash", "name"),
    width=12,
    state="readonly",
)
compare_combo.grid(row=2, column=1, sticky="w", padx=4, pady=4)

(ttk.Checkbutton(ops_frame, text="Recurse sub-folders", variable=recurse_var)
 .grid(row=2, column=2, columnspan=2, sticky="w", padx=4, pady=4))

# ---------------------------------------------------------------------------
# Model configuration
llm_frame = ttk.LabelFrame(main, text="Model Configuration", padding=10)
llm_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
llm_frame.columnconfigure(1, weight=1)
llm_frame.columnconfigure(3, weight=1)

register_llm_widget(
    ttk.Checkbutton(
        llm_frame,
        text="Enable LLM fallback",
        variable=llm_enabled_var,
        command=on_llm_toggle,
    )
).grid(row=0, column=0, columnspan=4, sticky="w", padx=4, pady=(0, 6))

register_llm_widget(ttk.Label(llm_frame, text="Endpoint")).grid(row=1, column=0, sticky="e", padx=4, pady=4)
register_llm_widget(ttk.Entry(llm_frame, textvariable=llm_endpoint_var)).grid(row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=4)

register_llm_widget(ttk.Label(llm_frame, text="Model")).grid(row=2, column=0, sticky="e", padx=4, pady=4)
llm_model_combo = ttk.Combobox(
    llm_frame,
    textvariable=llm_model_var,
    values=(
        DEFAULT_LLM_MODEL,
        "mistral-7b-instruct-q4",
        "llama-3-8b-instruct",
        "gpt-4o-mini",
    ),
)
register_llm_widget(llm_model_combo).grid(row=2, column=1, sticky="ew", padx=4, pady=4)

register_llm_widget(ttk.Label(llm_frame, text="Threshold")).grid(row=2, column=2, sticky="e", padx=4, pady=4)
llm_threshold_spin = ttk.Spinbox(llm_frame, from_=0, to=100, textvariable=llm_threshold_var, width=5)
register_llm_widget(llm_threshold_spin).grid(row=2, column=3, sticky="w", padx=4, pady=4)

register_llm_widget(ttk.Label(llm_frame, text="Whisper model")).grid(row=3, column=0, sticky="e", padx=4, pady=4)
whisper_model_combo = ttk.Combobox(
    llm_frame,
    textvariable=whisper_model_var,
    values=(
        DEFAULT_WHISPER_MODEL,
        "onnx-community/whisper-small.en",
        "onnx-community/whisper-medium.en",
        "openai/whisper-base.en",
    ),
)
register_llm_widget(whisper_model_combo).grid(row=3, column=1, sticky="ew", padx=4, pady=4)

register_llm_widget(ttk.Label(llm_frame, text="Device")).grid(row=3, column=2, sticky="e", padx=4, pady=4)
whisper_device_combo = ttk.Combobox(
    llm_frame,
    textvariable=whisper_device_var,
    values=("auto", "cpu", "cuda", "rocm", "dml"),
    state="readonly",
)
register_llm_widget(whisper_device_combo).grid(row=3, column=3, sticky="w", padx=4, pady=4)

# ---------------------------------------------------------------------------
# Actions
actions_frame = ttk.LabelFrame(main, text="Actions", padding=10)
actions_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
actions_frame.columnconfigure((0, 1, 2, 3), weight=1)

primary_btn = ttk.Button(actions_frame, text="Move and Tag", command=lambda: run(), style="Primary.TButton")
primary_btn.grid(row=0, column=0, sticky="ew", padx=4)

restructure_btn = ttk.Button(actions_frame, text="Restructure Folders", command=lambda: restructure(), style="Action.TButton")
restructure_btn.grid(row=0, column=1, sticky="ew", padx=4)

tag_only_btn = ttk.Button(actions_frame, text="Tag Only", command=lambda: tag_only(), style="Action.TButton")
tag_only_btn.grid(row=0, column=2, sticky="ew", padx=4)

find_dupes_btn = ttk.Button(actions_frame, text="Find Duplicates", command=lambda: find_dupes(), style="Action.TButton")
find_dupes_btn.grid(row=0, column=3, sticky="ew", padx=4)

# ---------------------------------------------------------------------------
# Output / progress
log_frame = ttk.LabelFrame(main, text="Log", padding=10)
log_frame.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
log_frame.columnconfigure(0, weight=1)
log_frame.rowconfigure(0, weight=1)

output_text = scrolledtext.ScrolledText(log_frame, height=16, state="disabled")
output_text.grid(row=0, column=0, sticky="nsew")

progress_var = tk.IntVar(value=0)
progress = ttk.Progressbar(main, variable=progress_var, maximum=100)
progress.grid(row=5, column=0, sticky="ew", pady=(8, 4))

eta_var = tk.StringVar(value="ETA: --:--")
ttk.Label(main, textvariable=eta_var, anchor="e").grid(row=6, column=0, sticky="e")

on_llm_toggle()

output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
progress_is_indeterminate = False


def gather_llm_settings() -> dict[str, object]:
    endpoint = (llm_endpoint_var.get() or "").strip()
    model = (llm_model_var.get() or "").strip()
    whisper_model = (whisper_model_var.get() or "").strip()
    whisper_device = (whisper_device_var.get() or "").strip()
    threshold = max(0, min(100, int(llm_threshold_var.get() or 0)))
    return {
        "endpoint": endpoint,
        "model": model,
        "threshold": threshold,
        "whisper_model": whisper_model,
        "whisper_device": whisper_device,
        "llm_enabled": bool(llm_enabled_var.get()),
    }


def apply_llm_settings(settings: dict[str, object]) -> int:
    endpoint_raw = str(settings.get("endpoint", "") or "").strip()
    model_raw = str(settings.get("model", "") or "").strip()
    whisper_model_raw = str(settings.get("whisper_model", "") or "").strip()
    whisper_device_raw = str(settings.get("whisper_device", "") or "").strip()
    llm_enabled = bool(settings.get("llm_enabled", True))
    threshold = int(settings.get("threshold", DEFAULT_LLM_THRESHOLD))

    if not llm_enabled or endpoint_raw.lower() in {"none", "null", "off"}:
        search_and_tag.LLM_ENDPOINT = None
    elif endpoint_raw:
        search_and_tag.LLM_ENDPOINT = endpoint_raw
    else:
        search_and_tag.LLM_ENDPOINT = DEFAULT_LLM_ENDPOINT

    if model_raw.lower() in {"none", "null", "off"}:
        search_and_tag.LLM_MODEL_NAME = None
    elif model_raw:
        search_and_tag.LLM_MODEL_NAME = model_raw
    else:
        search_and_tag.LLM_MODEL_NAME = DEFAULT_LLM_MODEL

    if whisper_model_raw.lower() == "none":
        search_and_tag.WHISPER_MODEL_NAME = None
    elif whisper_model_raw:
        search_and_tag.WHISPER_MODEL_NAME = whisper_model_raw
    else:
        search_and_tag.WHISPER_MODEL_NAME = DEFAULT_WHISPER_MODEL

    device_val = whisper_device_raw.lower() or DEFAULT_WHISPER_DEVICE
    search_and_tag.WHISPER_DEVICE = device_val
    search_and_tag.WHISPER_PIPELINE = None
    search_and_tag.WHISPER_PIPELINE_PROVIDER = None
    search_and_tag.WHISPER_PIPELINE_ERROR = None

    llm_enabled_var.set(llm_enabled)
    on_llm_toggle()

    tagger_mod = getattr(combobook, "tagger", None)
    if tagger_mod is not None and tagger_mod is not search_and_tag:
        tagger_mod.LLM_ENDPOINT = search_and_tag.LLM_ENDPOINT
        tagger_mod.LLM_MODEL_NAME = search_and_tag.LLM_MODEL_NAME
        tagger_mod.WHISPER_MODEL_NAME = search_and_tag.WHISPER_MODEL_NAME
        tagger_mod.WHISPER_DEVICE = search_and_tag.WHISPER_DEVICE
        tagger_mod.WHISPER_PIPELINE = None
        tagger_mod.WHISPER_PIPELINE_PROVIDER = None
        tagger_mod.WHISPER_PIPELINE_ERROR = None

    return threshold

