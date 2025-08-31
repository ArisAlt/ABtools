#!/usr/bin/env python3
"""
ABtools/AbtoolsGui.py  ·  v0.1  ·  2025-08-31
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import combobook

VERSION = "0.1"
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

def run():
    src = Path(source_var.get()).expanduser()
    dst = Path(dest_var.get()).expanduser()
    if not src.exists():
        messagebox.showerror("Error", "Source path does not exist")
        return
    dst.mkdir(parents=True, exist_ok=True)
    combobook.AUTO_YES = yes_var.get()
    try:
        combobook.main(src, dst, commit_var.get(), yes_var.get(), copy_var.get())
        messagebox.showinfo("Done", "Processing finished")
    except Exception as exc:
        messagebox.showerror("Error", str(exc))

tk.Button(root, text="Run", command=run).grid(row=3, column=0, columnspan=4, pady=10)

if __name__ == "__main__":
    root.mainloop()
