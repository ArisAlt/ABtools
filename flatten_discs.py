#!/usr/bin/env python3
"""
ABtools/flatten_discs.py  –  v1.5  (2026-03-09)

Flatten audiobook rips that live in
    Book Name (Disc 01)  /  Book Name (Disc 02)  …
creating one folder called  Book Name/Track 001.* …

• Preview by default.  Add  --commit  to do it,  --yes  to skip prompts.
• ``--version`` prints the script version and file path.
"""

from __future__ import annotations
import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

VERSION = "1.5"
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


def disc_base_name(name: str) -> str:
    """Derive the book name from a disc folder name.

    Handles a trailing marker ("Book C (Disc 1)") and a leading one
    ("[Disc 1] Book C"), where the text *before* the marker is empty. Returns
    "" only for a bare marker such as "Disc 1", which means the parent folder
    is itself the book.

    Taking just the text before the marker (the previous behaviour) collapsed
    every prefix-marked folder in a directory to "", merging unrelated books.
    """
    parts = DISC_RX.split(name)
    head = parts[0].strip().strip("-_ ").strip()
    if head:
        return head
    if len(parts) > 1:
        return parts[-1].strip().strip("-_ ").strip()
    return ""


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
        groups.setdefault(disc_base_name(p.name), []).append((int(m.group("num")), p))
    return [(b, sorted(lst, key=lambda t: t[0])) for b, lst in groups.items()]


def collect_tracks(discs: List[Tuple[int, Path]]) -> List[Path]:
    tracks: List[Path] = []
    for _, d in discs:
        tracks.extend(sorted(f for f in d.iterdir() if is_audio(f)))
    return tracks


def flatten(
    parent: Path,
    discs: List[Tuple[int, Path]],
    dry: bool,
    auto_yes: bool,
    root: Path,
) -> bool:
    """Flatten one disc set into a single directory.

    Args:
        parent:   Parent folder containing the disc sub-directories.
        discs:    List of (disc_number, disc_path) pairs.
        dry:      When True, only show what would happen (no changes written).
        auto_yes: When True, skip the confirmation prompt.
        root:     The top-level root passed from CLI; used for display-only relative paths.
    """
    base = disc_base_name(discs[0][1].name)
    # A bare marker ("Disc 1") means the parent folder is the book itself.
    book_dir = parent / base if base else parent
    tracks = collect_tracks(discs)
    if not tracks:
        return False

    try:
        display_parent = parent.relative_to(root)
    except ValueError:
        display_parent = parent

    print(
        f"\n⇒ {display_parent} → {book_dir.name}   "
        f"({len(discs)} disc{'s' if len(discs) > 1 else ''}, {len(tracks)} tracks)"
    )

    if not auto_yes:
        resp = input("   flatten here? [y/N] ").strip().lower()
        if resp != "y":
            print("   skipped.")
            return False

    digits = len(str(len(tracks)))
    planned = [
        (src, book_dir / f"Track {i:0{digits}d}{src.suffix.lower()}")
        for i, src in enumerate(tracks, 1)
    ]

    # Check every destination up front. safe_move raises FileExistsError, which
    # nothing here catches, so discovering a clash mid-loop would abort with a
    # traceback after some tracks had already moved.
    clashes = [dest for _, dest in planned if dest.exists()]
    if clashes:
        print(
            f"   ! refusing to flatten - {len(clashes)} destination file(s) already "
            f"exist, e.g. {clashes[0].name}"
        )
        return False

    for src, dest in planned:
        print(f"   {'mv' if not dry else '↪'} {src.name} → {dest.relative_to(parent)}")
        if not dry:
            book_dir.mkdir(exist_ok=True)
            safe_move(src, dest)

    if not dry:
        for _, d in discs:
            try:
                d.rmdir()
            except OSError:
                pass
        print("   ✔ done.")
    return True


# ───────── driver ────────────────────────────────────────────────────────────
def main(root: Path, commit: bool, auto_yes: bool) -> None:
    flattened = 0

    # 1) look at ROOT itself
    for _base, discs in disc_sets_in(root):
        if flatten(root, discs, dry=not commit, auto_yes=auto_yes, root=root):
            flattened += 1

    # 2) recurse
    for folder in root.rglob("*"):
        if not folder.is_dir():
            continue
        for _base, discs in disc_sets_in(folder):
            if flatten(folder, discs, dry=not commit, auto_yes=auto_yes, root=root):
                flattened += 1

    if flattened:
        print(f"\nFinished – {flattened} book(s) processed.")
    else:
        print("No folders like  \u201cBook (Disc 1)\u201d  found under that root.")


# ───────── CLI ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description='Flatten "Disc 01" / "disk-02" sub-folders.')
    ap.add_argument("root", type=Path, help="Top-level audiobook folder")
    ap.add_argument("--commit", action="store_true", help="Actually move/rename (default: preview)")
    ap.add_argument("--yes", action="store_true", help="Auto-confirm every book")
    ap.add_argument("--version", action="version", version=VERSION_INFO)
    args = ap.parse_args()
    ROOT = args.root.resolve()
    if not ROOT.is_dir():
        sys.exit(f"{ROOT} is not a directory")
    main(ROOT, commit=args.commit, auto_yes=args.yes)
