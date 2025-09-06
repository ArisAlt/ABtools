#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py  ·  v0.3  ·  2025-09-01
"""
from __future__ import annotations

import sys
import threading
import queue
from contextlib import redirect_stdout, redirect_stderr
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import combobook
import search_and_tag

VERSION = "0.3"
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
output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

output_text = tk.Text(root, height=15, width=60, state="disabled")
output_text.grid(row=4, column=0, columnspan=4, padx=5, pady=5)

def append_output(text: str) -> None:
    output_text.configure(state="normal")
    output_text.insert(tk.END, text)
    output_text.see(tk.END)
    output_text.configure(state="disabled")

class QueueWriter:
    def __init__(self, q: queue.Queue[tuple[str, str]]):
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

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                combobook.main(
                    src, dst, commit_var.get(), yes_var.get(), copy_var.get()
                )
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

    def worker() -> None:
        try:
            with redirect_stdout(QueueWriter(output_queue)), redirect_stderr(
                QueueWriter(output_queue)
            ):
                args = [str(src), "--recurse"]
                if commit_var.get():
                    args.append("--commit")
                if yes_var.get():
                    args.append("--yes")
                old_argv = sys.argv
                sys.argv = ["search_and_tag.py"] + args
                try:
                    search_and_tag.main()
                finally:
                    sys.argv = old_argv
            output_queue.put(("status", "done"))
        except Exception as exc:  # pragma: no cover - handled via GUI
            output_queue.put(("status", f"error:{exc}"))

    threading.Thread(target=worker, daemon=True).start()


tk.Button(root, text="Run", command=run).grid(row=3, column=0, columnspan=2, pady=10)
tk.Button(root, text="Tag Only", command=tag_only).grid(row=3, column=2, columnspan=2, pady=10)

if __name__ == "__main__":
    poll_queue()
    root.mainloop()
