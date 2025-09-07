#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py  ·  v0.5  ·  2025-09-01
"""
from __future__ import annotations

import sys, threading, queue, time
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from types import SimpleNamespace
import combobook, search_and_tag, find_duplicates

VERSION = "0.5"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

if "--version" in sys.argv:
    print(VERSION_INFO % {"prog": Path(sys.argv[0]).name})
    sys.exit(0)

root = tk.Tk()
root.title("ABtools GUI")

# --- input fields ---
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

tk.Label(root, text="Source").grid(row=0, column=0, sticky="e")
tk.Entry(root, textvariable=source_var, width=40).grid(row=0, column=1, columnspan=2, padx=5, pady=5)
tk.Button(root, text="Browse", command=browse_src).grid(row=0, column=3, padx=5)

tk.Label(root, text="Destination").grid(row=1, column=0, sticky="e")
tk.Entry(root, textvariable=dest_var, width=40).grid(row=1, column=1, columnspan=2, padx=5, pady=5)
tk.Button(root, text="Browse", command=browse_dst).grid(row=1, column=3, padx=5)

# --- options ---
commit_var = tk.BooleanVar()
copy_var = tk.BooleanVar()
yes_var = tk.BooleanVar()

tk.Checkbutton(root, text="Commit", variable=commit_var).grid(row=2, column=0, sticky="w", padx=5)
tk.Checkbutton(root, text="Copy", variable=copy_var).grid(row=2, column=1, sticky="w", padx=5)
tk.Checkbutton(root, text="Yes", variable=yes_var).grid(row=2, column=2, sticky="w", padx=5)

# --- output ---
output_queue: queue.Queue[tuple[str, object]] = queue.Queue()

output_text = tk.Text(root, height=15, width=60, state="disabled")
output_text.grid(row=4, column=0, columnspan=4, padx=5, pady=5)

progress_var = tk.IntVar(value=0)
progress = ttk.Progressbar(root, variable=progress_var, maximum=100)
progress.grid(row=5, column=0, columnspan=4, padx=5, pady=5, sticky="ew")
eta_var = tk.StringVar(value="ETA: --:--")
tk.Label(root, textvariable=eta_var).grid(row=6, column=0, columnspan=4)

def append_output(text: str) -> None:
    output_text.configure(state="normal")
    output_text.insert(tk.END, text)
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
    while True:
        try:
            typ, msg = output_queue.get_nowait()
        except queue.Empty:
            break
        if typ == "stdout":
            append_output(msg)
        elif typ == "progress":
            idx, total, eta = msg
            progress.configure(maximum=total if total else 1)
            progress_var.set(idx)
            if eta > 0:
                secs = int(eta)
                m, s = divmod(secs, 60)
                h, m = divmod(m, 60)
                eta_var.set(f"ETA: {h:02d}:{m:02d}:{s:02d}")
            else:
                eta_var.set("ETA: --:--")
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


def tag_only() -> None:
    src = Path(source_var.get()).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
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
                search_and_tag.LOG_PATH = src / "tag_log.txt"
                search_and_tag.REVIEW_PATH = src / "review_log.txt"
                search_and_tag.DEBUG = False
                leaves = search_and_tag.walk_leaves(src)
                args = SimpleNamespace(
                    commit=commit_var.get(),
                    yes=yes_var.get(),
                    no=False,
                    striptags=False,
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
    src = Path(source_var.get()).expanduser()
    dst = Path(dest_var.get()).expanduser()
    paths = [p for p in (src, dst) if p.exists()]
    if not paths:
        messagebox.showerror("Error", "No valid source or destination paths")
        return

    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.configure(state="disabled")
    progress.configure(maximum=len(paths))
    progress_var.set(0)
    eta_var.set("ETA: --:--")

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                for idx, path in enumerate(paths, 1):
                    print(f"Scanning {path} for duplicates...")
                    dupes = find_duplicates.find_dupes(path)
                    if not dupes:
                        print("No duplicates found.")
                    else:
                        for digest, files in dupes.items():
                            print(f"\nSHA1 {digest}")
                            for f in files:
                                print(f"  {f}")
                        log_file = path / find_duplicates.DUP_LOG.name
                        with log_file.open("w", encoding="utf-8") as fh:
                            for digest, files in dupes.items():
                                fh.write(f"SHA1 {digest}\n")
                                for f in files:
                                    fh.write(f"  {f}\n")
                                fh.write("\n")
                        print(
                            f"\n{sum(len(v) for v in dupes.values())} duplicate files logged to {log_file}"
                        )
                    output_queue.put(("progress", (idx, len(paths), 0)))
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


tk.Button(root, text="Run", command=run).grid(row=3, column=0, pady=10)
tk.Button(root, text="Tag Only", command=tag_only).grid(row=3, column=1, pady=10)
tk.Button(root, text="Find Duplicates", command=find_dupes).grid(row=3, column=2, columnspan=2, pady=10)

if __name__ == "__main__":
    poll_queue()
    root.mainloop()
