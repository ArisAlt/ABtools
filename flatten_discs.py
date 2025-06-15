#!/usr/bin/env python3
"""
ABtools/flatten_discs.py  –  v1.3  (2025-06-15)

Flatten audiobook rips that live in
    Book Name (Disc 01)  /  Book Name (Disc 02)  …
creating one folder called  Book Name/Track 001.* …

• Preview by default.  Add  --commit  to do it,  --yes  to skip prompts.
"""

from __future__ import annotations
import argparse, re, shutil, sys
from pathlib import Path
from typing import List, Tuple

VERSION = "1.3"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

def safe_move(src: Path, dst: Path) -> None:
    """Move ``src`` to ``dst`` ensuring ``dst`` does not exist."""
    if dst.exists():
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}

# one-line regex that matches  Disc 01, disk-02, CD03, Part 4, etc.
DISC_RX = re.compile(
    r'(?:[\(\[\{]?)(?:disc|disk|cd|part)[\s_\-]*(?P<num>\d{1,3})(?:[\)\]\}]?)',
    re.IGNORECASE,
)

# ───────── helpers ────────────────────────────────────────────────────────────
def is_audio(p: Path) -> bool:
    return p.suffix.lower() in AUDIO_EXTS

def disc_sets_in(folder: Path) -> List[Tuple[str, List[Tuple[int, Path]]]]:
    """
    Return list of (base_name, [(disc_no, Path)…]) whose sub-dirs match *disk pattern*.
    Accepts even a single disc.
    """
    groups: dict[str, List[Tuple[int, Path]]] = {}
    for p in folder.iterdir():
        if not p.is_dir():
            continue
        m = DISC_RX.search(p.name)
        if not m:
            continue
        base = DISC_RX.split(p.name)[0].strip().rstrip(" -_")
        groups.setdefault(base, []).append((int(m.group("num")), p))
    return [(b, sorted(lst, key=lambda t: t[0])) for b, lst in groups.items()]

def collect_tracks(discs: List[Tuple[int, Path]]) -> List[Path]:
    tracks: List[Path] = []
    for _, d in discs:
        tracks.extend(sorted(f for f in d.iterdir() if is_audio(f)))
    return tracks

def flatten(parent: Path, discs: List[Tuple[int, Path]],
            dry: bool, auto_yes: bool) -> bool:
    base = DISC_RX.split(discs[0][1].name)[0].strip().rstrip(" -_")
    book_dir = parent / base
    tracks   = collect_tracks(discs)
    if not tracks:
        return False

    print(f"\n⇒ {parent.relative_to(ROOT)} → {book_dir.name}   "
          f"({len(discs)} disc{'s' if len(discs)>1 else ''}, {len(tracks)} tracks)")

    if not auto_yes:
        resp = input("   flatten here? [y/N] ").strip().lower()
        if resp != "y":
            print("   skipped.")
            return False

    digits = len(str(len(tracks)))
    for i, src in enumerate(tracks, 1):
        dest = book_dir / f"Track {i:0{digits}d}{src.suffix.lower()}"
        print(f"   {'mv' if not dry else '↪'} {src.name} → {dest.relative_to(parent)}")
        if not dry:
            book_dir.mkdir(exist_ok=True)
            safe_move(src, dest)

    if not dry:
        for _, d in discs:
            try: d.rmdir()
            except OSError: pass
        print("   ✔ done.")
    return True

# ───────── driver ────────────────────────────────────────────────────────────
def main(root: Path, commit: bool, auto_yes: bool):
    flattened = 0

    # 1) look at ROOT itself
    for base, discs in disc_sets_in(root):
        if flatten(root, discs, dry=not commit, auto_yes=auto_yes):
            flattened += 1

    # 2) recurse
    for folder in root.rglob("*"):
        if not folder.is_dir():
            continue
        for base, discs in disc_sets_in(folder):
            if flatten(folder, discs, dry=not commit, auto_yes=auto_yes):
                flattened += 1

    if flattened:
        print(f"\nFinished – {flattened} book(s) processed.")
    else:
        print("No folders like  “Book (Disc 1)”  found under that root.")

# ───────── CLI ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Flatten “Disc 01” / “disk-02” sub-folders.")
    ap.add_argument("root", type=Path, help="Top-level audiobook folder")
    ap.add_argument("--commit", action="store_true", help="Actually move/rename (default: preview)")
    ap.add_argument("--yes",    action="store_true", help="Auto-confirm every book")
    ap.add_argument("--version", action="version", version=VERSION_INFO)
    args = ap.parse_args()
    ROOT = args.root.resolve()
    if not ROOT.is_dir():
        sys.exit(f"{ROOT} is not a directory")
    main(ROOT, commit=args.commit, auto_yes=args.yes)
