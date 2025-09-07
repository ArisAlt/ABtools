#!/usr/bin/env python3
"""
ABtools/planning.py · v0.2 · 2025-09-01
Builds restructure plans for audiobook libraries.
"""
from __future__ import annotations
import json, re, hashlib, sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

from catalog import Catalog

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}
SIDE_EXTS = {".cue", ".pdf", "metadata.json", "book.nfo"}

VERSION = "0.2"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

if "--version" in sys.argv:
    print(VERSION_INFO % {"prog": Path(sys.argv[0]).name})
    sys.exit(0)

@dataclass
class PlanEntry:
    source: str
    dest: str
    provider: str
    scores: Dict[str, float]
    confidence: float
    external_id: Optional[str]
    action: str  # skip|move|copy|quarantine

def slug(t: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", t).strip().rstrip(" .")

def leaf_audio_dirs(root: Path) -> List[Path]:
    return [
        p for p in root.rglob("*")
        if p.is_dir()
        and any(f.suffix.lower() in AUDIO_EXTS for f in p.iterdir())
        and not any(c.is_dir() and any(g.suffix.lower() in AUDIO_EXTS for g in c.iterdir())
                    for c in p.iterdir())
    ]

def has_disc_gap(book: Path) -> bool:
    nums = []
    for f in book.iterdir():
        if f.suffix.lower() in AUDIO_EXTS:
            m = re.search(r"(\d+)", f.stem)
            if m:
                nums.append(int(m.group(1)))
    if not nums:
        return False
    nums.sort()
    return nums != list(range(nums[0], nums[-1] + 1))

def plan_library(src_root: Path, dest_root: Path, copy: bool = False) -> List[Dict]:
    dest_root = dest_root.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    cat = Catalog(dest_root / ".abtools_catalog.db")
    plan: List[Dict] = []
    for book in leaf_audio_dirs(src_root):
        meta_path = book / "metadata.json"
        meta = json.load(meta_path.open(encoding="utf-8")) if meta_path.exists() else {}
        author = meta.get("author", "Unknown")
        title = meta.get("title", book.name)
        provider = meta.get("provider", "mock")
        score = float(meta.get("score", 100))
        external_id = meta.get("external_id")
        confidence = score
        action = "move"
        dest = dest_root / slug(author) / slug(title)
        if has_disc_gap(book):
            action = "quarantine"
            dest = dest_root / "_quarantine" / slug(author) / slug(title)
        elif score < 92 or not external_id:
            action = "skip" if score >= 85 else "skip"
        else:
            sig, data = Catalog.calc_signature(book, meta)
            if cat.has(sig):
                dest = dest_root / "_duplicates" / slug(author) / slug(title)
            else:
                cat.add(sig, data)
            action = "copy" if copy else "move"
        entry = PlanEntry(
            source=str(book.resolve()),
            dest=str(dest),
            provider=provider,
            scores={provider: score},
            confidence=confidence,
            external_id=external_id,
            action=action,
        )
        plan.append(asdict(entry))
    return plan

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build plan for library")
    ap.add_argument("src")
    ap.add_argument("dest")
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--plan-json")
    args = ap.parse_args()
    p = plan_library(Path(args.src), Path(args.dest), copy=args.copy)
    if args.plan_json:
        json.dump(p, open(args.plan_json, "w", encoding="utf-8"), indent=2)
    else:
        json.dump(p, sys.stdout, indent=2)
