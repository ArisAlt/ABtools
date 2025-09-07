#!/usr/bin/env python3
"""
ABtools/transaction.py · v0.1 · 2025-09-01
Apply and rollback restructure plans.
"""
from __future__ import annotations
import json, shutil, hashlib, time
from pathlib import Path
from typing import List, Dict

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}
SIDE_RX = (".cue", ".pdf", "metadata.json", "book.nfo")


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def execute(plan_file: Path) -> Path:
    plan = json.load(open(plan_file))
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
            data = json.load(meta.open())
            data["abtools_processed"] = True
            json.dump(data, meta.open("w"), indent=2)
        # record sha1 of first file
        files = [p for p in dest.rglob("*") if p.is_file()]
        digest = sha1(files[0]) if files else ""
        records.append({"src": str(src), "dst": str(dest), "sha1": digest})
    json.dump(records, txn_path.open("w"), indent=2)
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
    moves = json.load(last.open())
    for mv in reversed(moves):
        dst = Path(mv["dst"])
        src = Path(mv["src"])
        if dst.exists():
            shutil.move(dst, src)
    last.unlink()
