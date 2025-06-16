#!/usr/bin/env python3
"""
ABtools/find_duplicates.py - v0.3 (2025-09-01)
Find duplicate audio files by comparing SHA1 hashes.

Results are written to ``duplicate_log.txt`` in the chosen root folder.
Use ``--version`` to print the script version and file path.
Now shows scanning progress.
"""

from __future__ import annotations
import argparse, hashlib, sys
from pathlib import Path
from collections import defaultdict

VERSION = "0.3"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}

DUP_LOG = Path("duplicate_log.txt")


def is_audio(p: Path) -> bool:
    return p.suffix.lower() in AUDIO_EXTS


def sha1sum(path: Path) -> str:
    h = hashlib.sha1()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_dupes(root: Path) -> dict[str, list[Path]]:
    hashes: dict[str, list[Path]] = defaultdict(list)
    files = [p for p in root.rglob('*') if p.is_file() and is_audio(p)]
    total = len(files)
    for idx, p in enumerate(files, 1):
        print(f"\rScanning {idx}/{total}...", end="", flush=True)
        try:
            digest = sha1sum(p)
        except OSError as e:
            print(f"\nCould not read {p}: {e}", file=sys.stderr)
            continue
        hashes[digest].append(p)
    print()  # newline after progress
    return {k: v for k, v in hashes.items() if len(v) > 1}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Detect duplicate audio files under a directory.")
    ap.add_argument("root", type=Path, help="Top-level folder to scan")
    ap.add_argument("--version", action="version", version=VERSION_INFO)
    args = ap.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        sys.exit(f"{root} is not a directory")
    dupes = find_dupes(root)
    if not dupes:
        print("No duplicates found.")
    else:
        for digest, files in dupes.items():
            print(f"\nSHA1 {digest}")
            for f in files:
                print(f"  {f}")
        log_file = root / DUP_LOG.name
        with log_file.open("w", encoding="utf-8") as fh:
            for digest, files in dupes.items():
                fh.write(f"SHA1 {digest}\n")
                for f in files:
                    fh.write(f"  {f}\n")
                fh.write("\n")
        print(f"\n{sum(len(v) for v in dupes.values())} duplicate files logged to {log_file}")

