#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py  ·  v0.12  ·  2025-09-09
"""
from __future__ import annotations

import sys, threading, queue, time, json
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
from pathlib import Path
from types import SimpleNamespace
import combobook, search_and_tag, find_duplicates, restructure_for_audiobookshelf

VERSION = "0.12"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

DEFAULT_LLM_ENDPOINT = (
    search_and_tag.LLM_ENDPOINT
    or "http://127.0.0.1:1234/v1/chat/completions"
)
DEFAULT_LLM_MODEL = search_and_tag.LLM_MODEL_NAME or "mistral-7b-instruct-q4"
DEFAULT_LLM_THRESHOLD = 75
DEFAULT_WHISPER_MODEL = "medium.en"
DEFAULT_WHISPER_DEVICE = "auto"
DEFAULT_WHISPER_COMPUTE = "auto"

if "--version" in sys.argv:
    print(VERSION_INFO % {"prog": Path(sys.argv[0]).name})
    sys.exit(0)

root = tk.Tk()
root.title("ABtools GUI")
root.resizable(True, True)
# Allow all visible columns to expand and make the output row stretchy
for i in range(8):
    root.grid_columnconfigure(i, weight=1)
root.grid_rowconfigure(7, weight=1)

# --- input fields ---
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
    path = filedialog.asksaveasfilename(defaultextension=".json")
    if path:
        plan_var.set(path)

tk.Label(root, text="Source").grid(row=0, column=0, sticky="e")
tk.Entry(root, textvariable=source_var, width=40).grid(row=0, column=1, columnspan=2, padx=5, pady=5)
tk.Button(root, text="Browse", command=browse_src).grid(row=0, column=3, padx=5)

tk.Label(root, text="Destination").grid(row=1, column=0, sticky="e")
tk.Entry(root, textvariable=dest_var, width=40).grid(row=1, column=1, columnspan=2, padx=5, pady=5)
tk.Button(root, text="Browse", command=browse_dst).grid(row=1, column=3, padx=5)

tk.Label(root, text="Plan JSON").grid(row=2, column=0, sticky="e")
tk.Entry(root, textvariable=plan_var, width=40).grid(row=2, column=1, columnspan=2, padx=5, pady=5)
tk.Button(root, text="Browse", command=browse_plan).grid(row=2, column=3, padx=5)

# --- options ---
commit_var = tk.BooleanVar()
copy_var = tk.BooleanVar()
yes_var = tk.BooleanVar()
network_var = tk.BooleanVar()
timeout_var = tk.StringVar(value="30")
compare_by_var = tk.StringVar(value="hash")
threads_var = tk.IntVar(value=4)
recurse_var = tk.BooleanVar(value=True)
only_src_log_var = tk.BooleanVar()
llm_endpoint_var = tk.StringVar(value=DEFAULT_LLM_ENDPOINT)
llm_model_var = tk.StringVar(value=DEFAULT_LLM_MODEL)
llm_threshold_var = tk.StringVar(value=str(DEFAULT_LLM_THRESHOLD))
whisper_model_var = tk.StringVar(value=DEFAULT_WHISPER_MODEL)
whisper_device_var = tk.StringVar(value=DEFAULT_WHISPER_DEVICE)
whisper_compute_var = tk.StringVar(value=DEFAULT_WHISPER_COMPUTE)

tk.Checkbutton(root, text="Commit", variable=commit_var).grid(row=3, column=0, sticky="w", padx=5)
tk.Checkbutton(root, text="Copy", variable=copy_var).grid(row=3, column=1, sticky="w", padx=5)
tk.Checkbutton(root, text="Yes", variable=yes_var).grid(row=3, column=2, sticky="w", padx=5)
tk.Checkbutton(root, text="Network Mode", variable=network_var).grid(row=3, column=3, sticky="w", padx=5)

# compare-by controls
tk.Label(root, text="Compare by").grid(row=3, column=4, sticky="e")
ttk.Combobox(root, textvariable=compare_by_var, values=("hash", "name"), width=7, state="readonly").grid(row=3, column=5, sticky="w", padx=5)

# threads controls
tk.Label(root, text="Threads").grid(row=3, column=6, sticky="e")
tk.Spinbox(root, from_=1, to=16, textvariable=threads_var, width=4).grid(row=3, column=7, sticky="w", padx=5)

# timeout + recurse controls
tk.Label(root, text="Timeout (s)").grid(row=2, column=4, sticky="e")
tk.Entry(root, textvariable=timeout_var, width=6).grid(row=2, column=5, sticky="w", padx=5)
tk.Checkbutton(root, text="Recurse", variable=recurse_var).grid(row=2, column=6, sticky="w", padx=5)
tk.Checkbutton(root, text="Only src log", variable=only_src_log_var).grid(row=2, column=6, columnspan=2, sticky="w", padx=5)

llm_frame = ttk.LabelFrame(root, text="LLM fallback")
llm_frame.grid(row=4, column=0, columnspan=8, padx=5, pady=(0, 5), sticky="ew")
llm_frame.columnconfigure(1, weight=1)
llm_frame.columnconfigure(3, weight=1)

ttk.Label(llm_frame, text="Endpoint").grid(row=0, column=0, sticky="e", padx=5, pady=2)
ttk.Entry(llm_frame, textvariable=llm_endpoint_var).grid(
    row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=2
)
ttk.Label(llm_frame, text="Model").grid(row=1, column=0, sticky="e", padx=5, pady=2)
ttk.Entry(llm_frame, textvariable=llm_model_var).grid(
    row=1, column=1, sticky="ew", padx=5, pady=2
)
ttk.Label(llm_frame, text="Threshold").grid(row=1, column=2, sticky="e", padx=5, pady=2)
ttk.Spinbox(
    llm_frame,
    from_=0,
    to=100,
    textvariable=llm_threshold_var,
    width=5,
).grid(row=1, column=3, sticky="w", padx=5, pady=2)
ttk.Label(llm_frame, text="Whisper model").grid(row=2, column=0, sticky="e", padx=5, pady=2)
ttk.Entry(llm_frame, textvariable=whisper_model_var).grid(
    row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=2
)
ttk.Label(llm_frame, text="Device").grid(row=3, column=0, sticky="e", padx=5, pady=2)
ttk.Entry(llm_frame, textvariable=whisper_device_var, width=12).grid(
    row=3, column=1, sticky="w", padx=5, pady=2
)
ttk.Label(llm_frame, text="Compute type").grid(row=3, column=2, sticky="e", padx=5, pady=2)
ttk.Entry(llm_frame, textvariable=whisper_compute_var, width=12).grid(
    row=3, column=3, sticky="w", padx=5, pady=2
)

# --- output ---
output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
# Track whether the progress bar is running in indeterminate mode to avoid
# flicker from redundant determinate updates during cross-compare.
progress_is_indeterminate = False

output_text = scrolledtext.ScrolledText(root, height=15, width=60, state="disabled")
output_text.grid(row=7, column=0, columnspan=8, padx=5, pady=5, sticky="nsew")

progress_var = tk.IntVar(value=0)
progress = ttk.Progressbar(root, variable=progress_var, maximum=100)
progress.grid(row=8, column=0, columnspan=8, padx=5, pady=5, sticky="ew")
eta_var = tk.StringVar(value="ETA: --:--")
tk.Label(root, textvariable=eta_var).grid(row=9, column=0, columnspan=8)


def gather_llm_settings() -> dict[str, object]:
    endpoint = (llm_endpoint_var.get() or "").strip()
    model = (llm_model_var.get() or "").strip()
    whisper_model = (whisper_model_var.get() or "").strip()
    whisper_device = (whisper_device_var.get() or "").strip()
    whisper_compute = (whisper_compute_var.get() or "").strip()
    try:
        threshold = int((llm_threshold_var.get() or "").strip())
    except ValueError:
        threshold = DEFAULT_LLM_THRESHOLD
    threshold = max(0, min(100, threshold))
    return {
        "endpoint": endpoint,
        "model": model,
        "threshold": threshold,
        "whisper_model": whisper_model,
        "whisper_device": whisper_device,
        "whisper_compute": whisper_compute,
    }


def apply_llm_settings(settings: dict[str, object]) -> int:
    endpoint_raw = str(settings.get("endpoint", "") or "").strip()
    model_raw = str(settings.get("model", "") or "").strip()
    whisper_model_raw = str(settings.get("whisper_model", "") or "").strip()
    whisper_device_raw = str(settings.get("whisper_device", "") or "").strip()
    whisper_compute_raw = str(settings.get("whisper_compute", "") or "").strip()
    threshold = int(settings.get("threshold", DEFAULT_LLM_THRESHOLD))
    if endpoint_raw.lower() in {"none", "null", "off"}:
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
    compute_val = whisper_compute_raw.lower() or DEFAULT_WHISPER_COMPUTE
    search_and_tag.WHISPER_DEVICE = device_val
    search_and_tag.WHISPER_COMPUTE_TYPE = compute_val
    search_and_tag.WHISPER_MODEL = None
    search_and_tag.WHISPER_LOAD_ERROR = None

    tagger_mod = getattr(combobook, "tagger", None)
    if tagger_mod is not None and tagger_mod is not search_and_tag:
        tagger_mod.LLM_ENDPOINT = search_and_tag.LLM_ENDPOINT
        tagger_mod.LLM_MODEL_NAME = search_and_tag.LLM_MODEL_NAME
        tagger_mod.WHISPER_MODEL_NAME = search_and_tag.WHISPER_MODEL_NAME
        tagger_mod.WHISPER_DEVICE = search_and_tag.WHISPER_DEVICE
        tagger_mod.WHISPER_COMPUTE_TYPE = search_and_tag.WHISPER_COMPUTE_TYPE
        tagger_mod.WHISPER_MODEL = None
        tagger_mod.WHISPER_LOAD_ERROR = None

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
    src = Path(source_var.get()).expanduser()
    dst = Path(dest_var.get()).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
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
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                apply_llm_settings(llm_settings)
                # Hook up interactive confirms to GUI prompt
                def gui_confirm(question: str, default: bool = False) -> bool:
                    resp_q: queue.Queue[bool] = queue.Queue()
                    output_queue.put(("prompt", (question, default, resp_q)))
                    return bool(resp_q.get())
                try:
                    class _GuiConfirm:
                        @staticmethod
                        def ask(q: str, default: bool = False) -> bool:
                            return gui_confirm(q, default)
                    combobook.Confirm = _GuiConfirm  # type: ignore
                except Exception:
                    pass
                leaves = combobook.leaf_dirs(src)
                total = len(leaves)
                summary = defaultdict(int)
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
                    rate = idx / elapsed if elapsed else 0
                    eta = (total - idx) / rate if rate else 0
                    output_queue.put(("progress", (idx, total, eta)))
                combobook.rprint("\n[bold]summary[/]")
                action_word = "copied" if copy_var.get() else "moved"
                combobook.rprint(f"  total        : {summary['total']}")
                combobook.rprint(f"  {action_word:12}: {summary['moved']}")
                if not commit_var.get():
                    combobook.rprint(f"  would_move   : {summary['would_move']}")
                for k in ("exists", "skip", "unmatched"):
                    combobook.rprint(f"  {k:12}: {summary[k]}")
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


def restructure() -> None:
    src = Path(source_var.get()).expanduser()
    dst = Path(dest_var.get()).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
    dst.mkdir(parents=True, exist_ok=True)

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                leaves = restructure_for_audiobookshelf.leaf_audio_dirs(src)
                total = len(leaves)
                stats = defaultdict(int)
                start = time.time()
                for idx, leaf in enumerate(leaves, 1):
                    restructure_for_audiobookshelf.process(
                        leaf,
                        dst,
                        dry=not commit_var.get(),
                        copy=copy_var.get(),
                        st=stats,
                        interactive=False,
                    )
                    elapsed = time.time() - start
                    rate = idx / elapsed if elapsed else 0
                    eta = (total - idx) / rate if rate else 0
                    output_queue.put(("progress", (idx, total, eta)))
                print("\n──── Summary ────")
                action_word = "copied" if copy_var.get() else "moved"
                print(f" Books scanned            : {stats['total']}")
                print(f" Books {action_word:20}: {stats['moved']}")
                if not commit_var.get():
                    print(f" Books that would move    : {stats['would_move']}")
                for k, label in (
                    ("exists", "Destination exists"),
                    ("no_audio", "No audio"),
                    ("tag_fail", "Tag/name unreadable"),
                ):
                    if stats[k]:
                        print(f" {label:25}: {stats[k]}")
                print("──── Done ────\n")
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


def tag_only() -> None:
    src = Path(source_var.get()).expanduser()
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
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                llm_threshold = apply_llm_settings(llm_settings)
                # Hook up interactive confirms to GUI prompt for search_and_tag
                def gui_confirm(question: str, default: bool = False) -> bool:
                    resp_q: queue.Queue[bool] = queue.Queue()
                    output_queue.put(("prompt", (question, default, resp_q)))
                    return bool(resp_q.get())
                try:
                    class _GuiConfirm:
                        @staticmethod
                        def ask(q: str, default: bool = False) -> bool:
                            return gui_confirm(q, default)
                        def __call__(self, q: str, default: bool = False) -> bool:  # fallback shape
                            return gui_confirm(q, default)
                    search_and_tag.Confirm = _GuiConfirm()  # type: ignore
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
                    whisper_model=search_and_tag.WHISPER_MODEL_NAME,
                    whisper_device=search_and_tag.WHISPER_DEVICE,
                    whisper_compute_type=search_and_tag.WHISPER_COMPUTE_TYPE,
                )
                total = len(leaves)
                start = time.time()
                for idx, leaf in enumerate(leaves, 1):
                    if not commit_var.get():
                        search_and_tag.rprint(f"[dim]preview:[/] {leaf}")
                    else:
                        search_and_tag.process_leaf(leaf, args)
                    elapsed = time.time() - start
                    rate = idx / elapsed if elapsed else 0
                    eta = (total - idx) / rate if rate else 0
                    output_queue.put(("progress", (idx, total, eta)))
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


def find_dupes() -> None:
    src_str = source_var.get().strip()
    dst_str = dest_var.get().strip()
    if not src_str:
        messagebox.showerror("Error", "Source path is required")
        return
    src = Path(src_str).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
    dst = Path(dst_str).expanduser() if dst_str else None
    if dst_str and (dst is None or not dst.exists()):
        messagebox.showerror("Error", "Destination path does not exist")
        return
    # Build paths list for non-cross scans; cross scans are handled as a single operation
    paths = [src] if dst is None else [src, dst]

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    # Cross-compare only when Destination is explicitly provided and exists
    cross = dst is not None
    progress.configure(maximum=(1 if cross else len(paths)))
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                # Determine timeout: when Network Mode is on, use the provided seconds;
                # otherwise None (auto: 30s for UNC paths, unlimited otherwise)
                try:
                    net_timeout = float(timeout_var.get()) if network_var.get() else None
                except ValueError:
                    net_timeout = 30.0 if network_var.get() else None

                by = compare_by_var.get().strip().lower()
                label = "name" if by == "name" else "SHA1"

                # callback to show current file being checked; throttled to avoid spam
                last_print = [0.0]
                def on_file(stage: str, p: Path) -> None:
                    # Show during enumeration, scanning and hashing stages
                    if ("hash" in stage) or ("scan" in stage) or ("enum" in stage):
                        now = time.time()
                        # Always show for hashing; throttle scan to every 0.25s
                        if ("hash" in stage) or (now - last_print[0] >= 0.25):
                            print(f"Checking: {p}")
                            last_print[0] = now

                # optional: limit to paths listed in source duplicate_log.txt
                limit_set = None
                if only_src_log_var.get():
                    try:
                        log_path = src / find_duplicates.DUP_LOG.name
                        limit_set = find_duplicates._read_paths_from_log(log_path)  # type: ignore[attr-defined]
                        print(f"Using source log {log_path} with {len(limit_set)} paths\n")
                    except Exception:
                        limit_set = None

                if cross:
                    # Indeterminate progress with elapsed time ticker
                    output_queue.put(("progress_mode", "indeterminate"))
                    start_ts = time.time()
                    stop_evt = threading.Event()
                    def _ticker():
                        while not stop_evt.is_set():
                            elapsed = time.time() - start_ts
                            output_queue.put(("progress", (0, 1, -elapsed)))
                            time.sleep(1.0)
                    threading.Thread(target=_ticker, daemon=True).start()
                    print(f"Comparing {src} <-> {dst} by {by}...")
                    dupes = find_duplicates.find_cross_dupes(src, dst, by=by, hash_timeout=net_timeout, on_file=on_file, threads=max(1, int(threads_var.get() or 1)), limit_src=limit_set)
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
                    # Finalize progress and elapsed time
                    elapsed = time.time() - start_ts
                    stop_evt.set()
                    output_queue.put(("progress_mode", "determinate"))
                    output_queue.put(("progress", (1, 1, -elapsed)))
                else:
                    for idx, path in enumerate(paths, 1):
                        print(f"Scanning {path} for duplicates by {by}...")
                        lp = limit_set if (limit_set is not None and path == src) else None
                        dupes = find_duplicates.find_dupes(path, by=by, hash_timeout=net_timeout, on_file=on_file, threads=max(1, int(threads_var.get() or 1)), limit_paths=lp)
                        if not dupes:
                            print("No duplicates found.")
                        else:
                            log_file = path / find_duplicates.DUP_LOG.name
                            find_duplicates._print_and_write_grouped(  # type: ignore[attr-defined]
                                dupes,
                                label,
                                log_file,
                            )
                            print(
                                f"\n{sum(len(v) for v in dupes.values())} duplicate files logged to {log_file}"
                            )
                        output_queue.put(("progress", (idx, len(paths), 0)))

                # Summary status line
                def _fmt_timeout(t):
                    if t is None:
                        return "auto"
                    if t == 0:
                        return "disabled"
                    return f"{int(t)}s"
                mode = "cross-compare" if cross else "single-folder"
                print(f"\nMode: {mode} | by: {by} | timeout: {_fmt_timeout(net_timeout)}\n")
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


def make_plan() -> None:
    src = Path(source_var.get()).expanduser()
    dest_str = dest_var.get().strip()
    plan_str = plan_var.get().strip()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
    if not dest_str:
        messagebox.showerror("Error", "Destination path is required")
        return
    if not plan_str:
        messagebox.showerror("Error", "Plan path is required")
        return
    dst = Path(dest_str).expanduser()
    plan_path = Path(plan_str).expanduser()
    dst.mkdir(parents=True, exist_ok=True)

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                from planning import plan_library

                plan = plan_library(src, dst, copy=copy_var.get())
                json.dump(plan, open(plan_path, "w", encoding="utf-8"), indent=2)
                print(f"plan saved to {plan_path}")
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


def apply_plan() -> None:
    plan_str = plan_var.get().strip()
    if not plan_str:
        messagebox.showerror("Error", "Plan path is required")
        return
    plan_path = Path(plan_str).expanduser()
    if not plan_path.exists():
        messagebox.showerror("Error", "Plan file not found")
        return

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                from transaction import execute

                execute(plan_path)
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


def undo_last_txn() -> None:
    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=1)
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                from transaction import undo_last

                undo_last()
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


tk.Button(root, text="Move and Tag", command=run).grid(row=5, column=0, pady=10)
tk.Button(root, text="Restructure Foldes", command=restructure).grid(row=5, column=1, pady=10)
tk.Button(root, text="Tag Only", command=tag_only).grid(row=5, column=2, pady=10)
tk.Button(root, text="Find Duplicates", command=find_dupes).grid(row=5, column=3, pady=10)
tk.Button(root, text="Plan", command=make_plan).grid(row=6, column=0, pady=10)
tk.Button(root, text="Apply Plan", command=apply_plan).grid(row=6, column=1, pady=10)
tk.Button(root, text="Undo Last", command=undo_last_txn).grid(row=6, column=2, pady=10)

if __name__ == "__main__":
    poll_queue()
    root.mainloop()
