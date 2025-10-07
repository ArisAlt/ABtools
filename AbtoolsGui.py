#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py  ·  v0.16  ·  2025-09-11
"""
from __future__ import annotations

import sys, threading, queue, time
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from types import SimpleNamespace
import combobook, search_and_tag, find_duplicates, restructure_for_audiobookshelf

VERSION = "0.16"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

PAD_X = 12
PAD_Y = 8

DEFAULT_LLM_ENDPOINT = (
    search_and_tag.LLM_ENDPOINT
    or "http://127.0.0.1:1234/v1/chat/completions"
)
DEFAULT_LLM_MODEL = search_and_tag.LLM_MODEL_NAME or "mistral-7b-instruct-q4"
DEFAULT_LLM_THRESHOLD = 75

if "--version" in sys.argv:
    print(VERSION_INFO % {"prog": Path(sys.argv[0]).name})
    sys.exit(0)

root = tk.Tk()
root.title("ABtools GUI")
root.resizable(True, True)
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

style = ttk.Style(root)
style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 8))

main = ttk.Frame(root, padding=PAD_X)
main.grid(row=0, column=0, sticky="nsew")
main.columnconfigure(0, weight=1)
for i in range(5):
    main.rowconfigure(i, weight=0)
main.rowconfigure(4, weight=1)

source_var = tk.StringVar()
dest_var = tk.StringVar()
plan_var = tk.StringVar()

def browse_src():
    path = filedialog.askdirectory()
    if path:
        source_var.set(path)

def browse_dst():
    path = filedialog.askdirectory()
    if path:
        dest_var.set(path)

def browse_plan():
    path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All Files", "*")])
    if path:
        plan_var.set(path)

paths_frame = ttk.LabelFrame(main, text="File Paths", padding=PAD_X)
paths_frame.grid(row=0, column=0, sticky="ew")
paths_frame.columnconfigure(1, weight=1)

ttk.Label(paths_frame, text="Source:").grid(row=0, column=0, sticky="w", padx=(0, PAD_X), pady=(0, PAD_Y))
ttk.Entry(paths_frame, textvariable=source_var).grid(row=0, column=1, sticky="ew", pady=(0, PAD_Y))
ttk.Button(paths_frame, text="Browse", command=browse_src).grid(row=0, column=2, sticky="ew", padx=(PAD_X, 0), pady=(0, PAD_Y))

ttk.Label(paths_frame, text="Destination:").grid(row=1, column=0, sticky="w", padx=(0, PAD_X), pady=(0, PAD_Y))
ttk.Entry(paths_frame, textvariable=dest_var).grid(row=1, column=1, sticky="ew", pady=(0, PAD_Y))
ttk.Button(paths_frame, text="Browse", command=browse_dst).grid(row=1, column=2, sticky="ew", padx=(PAD_X, 0), pady=(0, PAD_Y))

ttk.Label(paths_frame, text="Plan JSON:").grid(row=2, column=0, sticky="w", padx=(0, PAD_X))
ttk.Entry(paths_frame, textvariable=plan_var).grid(row=2, column=1, sticky="ew")
ttk.Button(paths_frame, text="Browse", command=browse_plan).grid(row=2, column=2, sticky="ew", padx=(PAD_X, 0))

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
llm_threshold_var = tk.IntVar(value=DEFAULT_LLM_THRESHOLD)
use_llm_var = tk.BooleanVar(value=bool(DEFAULT_LLM_ENDPOINT))

operation_frame = ttk.LabelFrame(main, text="Operation Settings", padding=PAD_X)
operation_frame.grid(row=1, column=0, sticky="ew", pady=(PAD_Y, 0))
for col in (0, 2):
    operation_frame.columnconfigure(col, weight=0)
operation_frame.columnconfigure(1, weight=1)
operation_frame.columnconfigure(3, weight=1)

ttk.Label(operation_frame, text="Timeout (s):").grid(row=0, column=0, sticky="w")
timeout_spin = ttk.Spinbox(
    operation_frame,
    from_=0,
    to=600,
    textvariable=timeout_var,
    width=6,
    increment=5,
)
timeout_spin.grid(row=0, column=1, sticky="w", padx=(0, PAD_X))

ttk.Label(operation_frame, text="Threads:").grid(row=0, column=2, sticky="w")
threads_spin = ttk.Spinbox(
    operation_frame,
    from_=1,
    to=64,
    textvariable=threads_var,
    width=5,
)
threads_spin.grid(row=0, column=3, sticky="ew")

ttk.Label(operation_frame, text="Compare by:").grid(row=1, column=0, sticky="w", pady=(PAD_Y, 0))
compare_combo = ttk.Combobox(
    operation_frame,
    textvariable=compare_by_var,
    values=("hash", "name"),
    state="readonly",
    width=8,
)
compare_combo.grid(row=1, column=1, sticky="w", pady=(PAD_Y, 0))

checkbox_frame = ttk.Frame(operation_frame)
checkbox_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(PAD_Y, 0))

ttk.Checkbutton(checkbox_frame, text="Commit", variable=commit_var).grid(row=0, column=0, sticky="w", padx=(0, PAD_X))
ttk.Checkbutton(checkbox_frame, text="Copy", variable=copy_var).grid(row=0, column=1, sticky="w", padx=(0, PAD_X))
ttk.Checkbutton(checkbox_frame, text="Yes", variable=yes_var).grid(row=0, column=2, sticky="w", padx=(0, PAD_X))
ttk.Checkbutton(checkbox_frame, text="Recurse", variable=recurse_var).grid(row=0, column=3, sticky="w", padx=(0, PAD_X))
ttk.Checkbutton(checkbox_frame, text="Network Mode", variable=network_var).grid(row=1, column=0, sticky="w", padx=(0, PAD_X), pady=(PAD_Y // 2, 0))
ttk.Checkbutton(checkbox_frame, text="Only src log", variable=only_src_log_var).grid(row=1, column=1, sticky="w", padx=(0, PAD_X), pady=(PAD_Y // 2, 0))

MODEL_CHOICES = (
    DEFAULT_LLM_MODEL,
    "mistral-7b-instruct-q4",
    "mixtral-8x7b-instruct",
    "phi-3-medium-4k-instruct",
)

llm_frame = ttk.LabelFrame(main, text="Model Configuration", padding=PAD_X)
llm_frame.grid(row=2, column=0, sticky="ew", pady=(PAD_Y, 0))
llm_frame.columnconfigure(1, weight=1)
llm_frame.columnconfigure(3, weight=1)

llm_controls: list[tk.Widget] = []

ttk.Checkbutton(
    llm_frame,
    text="Enable LLM fallback",
    variable=use_llm_var,
    command=lambda: toggle_llm_controls(),
).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, PAD_Y))

ttk.Label(llm_frame, text="Endpoint:").grid(row=1, column=0, sticky="e", padx=(0, PAD_X), pady=(0, PAD_Y))
endpoint_entry = ttk.Entry(llm_frame, textvariable=llm_endpoint_var)
endpoint_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0, PAD_Y))
llm_controls.append(endpoint_entry)

ttk.Label(llm_frame, text="Model:").grid(row=2, column=0, sticky="e", padx=(0, PAD_X), pady=(0, PAD_Y))
model_combo = ttk.Combobox(llm_frame, textvariable=llm_model_var, values=MODEL_CHOICES, state="readonly")
model_combo.grid(row=2, column=1, sticky="ew", pady=(0, PAD_Y))
llm_controls.append(model_combo)

ttk.Label(llm_frame, text="Threshold:").grid(row=2, column=2, sticky="e", padx=(PAD_X, PAD_X), pady=(0, PAD_Y))
threshold_spin = ttk.Spinbox(
    llm_frame,
    from_=0,
    to=100,
    textvariable=llm_threshold_var,
    width=5,
)
threshold_spin.grid(row=2, column=3, sticky="w", pady=(0, PAD_Y))
llm_controls.append(threshold_spin)

def toggle_llm_controls() -> None:
    state = "normal" if use_llm_var.get() else "disabled"
    for widget in llm_controls:
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass

output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
# Track whether the progress bar is running in indeterminate mode to avoid
# flicker from redundant determinate updates during cross-compare.
progress_is_indeterminate = False

actions_frame = ttk.LabelFrame(main, text="Actions", padding=PAD_X)
actions_frame.grid(row=3, column=0, sticky="ew", pady=(PAD_Y, 0))
for i in range(4):
    actions_frame.columnconfigure(i, weight=1)

log_frame = ttk.LabelFrame(main, text="Log", padding=PAD_X)
log_frame.grid(row=4, column=0, sticky="nsew", pady=(PAD_Y, 0))
log_frame.columnconfigure(0, weight=1)
log_frame.rowconfigure(0, weight=1)

output_text = tk.Text(log_frame, height=15, wrap="word", state="disabled")
output_text.grid(row=0, column=0, sticky="nsew")

scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=output_text.yview)
scrollbar.grid(row=0, column=1, sticky="ns", padx=(PAD_X // 2, 0))
output_text.configure(yscrollcommand=scrollbar.set)

progress_var = tk.IntVar(value=0)
progress = ttk.Progressbar(log_frame, variable=progress_var, maximum=100)
progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(PAD_Y, 0))

eta_var = tk.StringVar(value="ETA: --:--")
ttk.Label(main, textvariable=eta_var).grid(row=5, column=0, sticky="e", pady=(PAD_Y, 0))

toggle_llm_controls()

def gather_llm_settings() -> dict[str, object]:
    enabled = use_llm_var.get()
    endpoint = (llm_endpoint_var.get() or "").strip()
    model = (llm_model_var.get() or "").strip()
    try:
        threshold = int(llm_threshold_var.get())
    except Exception:
        threshold = DEFAULT_LLM_THRESHOLD
    threshold = max(0, min(100, threshold))
    if not enabled:
        return {
            "enabled": False,
            "endpoint": "none",
            "model": "",
            "threshold": threshold,
        }
    return {
        "enabled": True,
        "endpoint": endpoint,
        "model": model,
        "threshold": threshold,
    }

def apply_llm_settings(settings: dict[str, object]) -> int:
    enabled = bool(settings.get("enabled", True))
    endpoint_raw = str(settings.get("endpoint", "") or "").strip()
    model_raw = str(settings.get("model", "") or "").strip()
    threshold = int(settings.get("threshold", DEFAULT_LLM_THRESHOLD))

    if not enabled or endpoint_raw.lower() in {"none", "null", "off"}:
        search_and_tag.LLM_ENDPOINT = None
    elif endpoint_raw:
        search_and_tag.LLM_ENDPOINT = endpoint_raw
    else:
        search_and_tag.LLM_ENDPOINT = DEFAULT_LLM_ENDPOINT

    if not enabled or model_raw.lower() in {"none", "null", "off"}:
        search_and_tag.LLM_MODEL_NAME = None
    elif model_raw:
        search_and_tag.LLM_MODEL_NAME = model_raw
    else:
        search_and_tag.LLM_MODEL_NAME = DEFAULT_LLM_MODEL

    tagger_mod = getattr(combobook, "tagger", None)
    if tagger_mod is not None and tagger_mod is not search_and_tag:
        tagger_mod.LLM_ENDPOINT = search_and_tag.LLM_ENDPOINT
        tagger_mod.LLM_MODEL_NAME = search_and_tag.LLM_MODEL_NAME

    return threshold

def append_output(text: str) -> None:
    output_text.configure(state="normal")
    output_text.insert(tk.END, text.replace("\r", "\n"))
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
                messagebox.showinfo("Done", "Processing finished")
            elif msg.startswith("error:"):
                messagebox.showerror("Error", msg[6:])
    root.after(100, poll_queue)

def run() -> None:
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

                leaves = combobook.leaf_dirs(src)
                total = len(leaves)
                summary: defaultdict[str, int] = defaultdict(int)
                start = time.time()
                for idx, leaf in enumerate(leaves, 1):
                    combobook.process(
                        leaf,
                        src,
                        dst,
                        dry=not commit_var.get(),
                        yes=yes_var.get(),
                        copy=copy_var.get(),
                        summary=summary,
                    )
                    elapsed = time.time() - start
                    rate = idx / elapsed if elapsed else 0.0
                    eta = (total - idx) / rate if rate else 0.0
                    output_queue.put(("progress", (idx, total, eta)))

                combobook.rprint("\n[bold]summary[/]")
                action_word = "copied" if copy_var.get() else "moved"
                combobook.rprint(f"  total        : {summary['total']}")
                combobook.rprint(f"  {action_word:12}: {summary['moved']}")
                if not commit_var.get():
                    combobook.rprint(f"  would_move   : {summary['would_move']}")
                for key in ("exists", "skip", "unmatched"):
                    combobook.rprint(f"  {key:12}: {summary[key]}")
            output_queue.put(("status", "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()

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
                restructure_for_audiobookshelf.main(
                    src,
                    dst,
                    commit=commit_var.get(),
                    copy=copy_var.get(),
                    interactive=False,
                )
            output_queue.put(("status", "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()

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
                llm_threshold = apply_llm_settings(llm_settings)

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
                    search_and_tag.Confirm = _GuiConfirm()  # type: ignore[attr-defined]
                except Exception:
                    pass

                search_and_tag.LOG_PATH = src / "tag_log.txt"
                search_and_tag.REVIEW_PATH = src / "review_log.txt"
                search_and_tag.DEBUG = False

                leaves = search_and_tag.walk_leaves(src)
                args = SimpleNamespace(
                    commit=commit_var.get(),
                    yes=yes_var.get(),
                    no=False,
                    striptags=False,
                    llm_threshold=llm_threshold,
                    llm_endpoint=search_and_tag.LLM_ENDPOINT,
                    llm_model=search_and_tag.LLM_MODEL_NAME,
                )

                total = len(leaves)
                start = time.time()
                for idx, leaf in enumerate(leaves, 1):
                    if not commit_var.get():
                        search_and_tag.rprint(f"[dim]preview:[/] {leaf}")
                    else:
                        search_and_tag.process_leaf(leaf, args)
                    elapsed = time.time() - start
                    rate = idx / elapsed if elapsed else 0.0
                    eta = (total - idx) / rate if rate else 0.0
                    output_queue.put(("progress", (idx, total, eta)))
            output_queue.put(("status", "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()

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
                    )
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
                    )
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
            output_queue.put(("status", "done"))
        except Exception as exc:
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()
ttk.Button(actions_frame, text="Move and Tag", style="Primary.TButton", command=run).grid(
    row=0, column=0, sticky="ew", padx=(0, PAD_X), pady=(0, PAD_Y)
)
ttk.Button(actions_frame, text="Restructure Folders", command=restructure).grid(
    row=0, column=1, sticky="ew", padx=(0, PAD_X), pady=(0, PAD_Y)
)
ttk.Button(actions_frame, text="Tag Only", command=tag_only).grid(
    row=0, column=2, sticky="ew", padx=(0, PAD_X), pady=(0, PAD_Y)
)
ttk.Button(actions_frame, text="Find Duplicates", command=find_dupes).grid(
    row=0, column=3, sticky="ew", pady=(0, PAD_Y)
)

if __name__ == "__main__":
    poll_queue()
    root.mainloop()

