#!/usr/bin/env python3
"""
ABtools/transaction.py · v0.2 · 2025-09-01
Apply and rollback restructure plans.
"""
from __future__ import annotations
import json, shutil, hashlib, time, sys
from pathlib import Path
from typing import List, Dict

VERSION = "0.2"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

if "--version" in sys.argv:
    print(VERSION_INFO % {"prog": Path(sys.argv[0]).name})
    sys.exit(0)

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}
SIDE_RX = (".cue", ".pdf", "metadata.json", "book.nfo")


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def execute(plan_file: Path) -> Path:
    plan = json.load(open(plan_file, encoding="utf-8"))
    txndir = Path("transactions")
    txndir.mkdir(exist_ok=True)
    txn_path = txndir / f"txn-{int(time.time())}.json"
    records: List[Dict] = []
    for item in plan:
        action = item.get("action")
        if action not in {"move", "copy", "quarantine"}:
            continue
        src = Path(item["source"])
        dest = Path(item["dest"])
        tmp = dest.with_suffix(".tmp")
        if action == "copy":
            shutil.copytree(src, tmp)
        else:
            shutil.move(src, tmp)
        tmp.rename(dest)
        # mark metadata
        meta = dest / "metadata.json"
        if meta.exists():
            data = json.load(meta.open(encoding="utf-8"))
            data["abtools_processed"] = True
            json.dump(data, meta.open("w", encoding="utf-8"), indent=2)
        # record sha1 of first file
        files = [p for p in dest.rglob("*") if p.is_file()]
        digest = sha1(files[0]) if files else ""
        records.append({"src": str(src), "dst": str(dest), "sha1": digest})
    json.dump(records, txn_path.open("w", encoding="utf-8"), indent=2)
    return txn_path


def undo_last(txndir: Path = Path("transactions")) -> None:
    if not txndir.exists():
        print("no transactions")
        return
    files = sorted(txndir.glob("txn-*.json"))
    if not files:
        print("no transactions")
        return
    last = files[-1]
    moves = json.load(last.open(encoding="utf-8"))
    for mv in reversed(moves):
        dst = Path(mv["dst"])
        src = Path(mv["src"])
        if dst.exists():
            shutil.move(dst, src)
    last.unlink()
