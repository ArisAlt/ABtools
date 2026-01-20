#!/usr/bin/env python3
"""
Simple Audiobookshelf reshaper - v5.4

Given a source library where audiobook folders are stored as::

    <source_root>/<Author>/<Some folder name>

this script moves (or copies) each book into::

    <dest_root>/<Author>/<Year - Title>

The year is taken from either a ``(YYYY)`` suffix or a leading
``YYYY -`` pattern. Leading disc/sequence prefixes like ``01 -`` are
stripped from the title. If a year cannot be detected we fall back to
``Unknown``. Only directories containing audio files are considered
books; everything else is ignored.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple
import re

VERSION = "5.4"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

AUDIO_EXTS = {".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".opus", ".wav"}
TAIL_RX = re.compile(
    r"""
        (?:\s*\((?!(?:\d+\s*of\s*\d+|[Pp]art\s*\d+))[^)]*\))?
        (?:\s*\d+\s*[kK])?
        (?:\s*\d+\.\d{2}\.\d{2})?
        (?:\s*\{[^}]*\})?
        \s*$
    """,
    re.VERBOSE,
)

YEAR_SUFFIX_RX = re.compile(r"\((\d{4})\)\s*$")
YEAR_PREFIX_RX = re.compile(r"^\s*(\d{4})\s*[-_:.]\s*")
LEADING_INDEX_RX = re.compile(r"^\s*\d+\s*[-_:.]\s*")


def slug(text: str) -> str:
    """Return filesystem-friendly name."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", text)
    return cleaned.strip().rstrip(". ")


def has_audio(folder: Path) -> bool:
    """Return True if the folder contains at least one audio file."""
    try:
        return any(p.is_file() and p.suffix.lower() in AUDIO_EXTS for p in folder.iterdir())
    except FileNotFoundError:
        return False


def parse_book_folder(name: str) -> Tuple[str, str]:
    """
    Extract (year, title) from a folder name using simple heuristics.
    Year may come from a ``(YYYY)`` suffix or leading ``YYYY -`` pattern.
    """
    raw = name.strip()
    year: str | None = None

    suffix = YEAR_SUFFIX_RX.search(raw)
    if suffix:
        year = suffix.group(1)
        raw = raw[: suffix.start()].strip(" -_.")

    prefix = YEAR_PREFIX_RX.match(raw)
    if prefix:
        if year is None:
            year = prefix.group(1)
        raw = raw[prefix.end() :].strip(" -_.")

    working = TAIL_RX.sub("", raw).strip()
    working = LEADING_INDEX_RX.sub("", working).strip()

    if not working:
        working = "Untitled"
    if not year:
        year = "Unknown"
    return year, working


def discover_books(source_root: Path) -> Iterable[Tuple[str, Path]]:
    """Yield ``(author_name, book_dir)`` pairs for folders containing audio."""
    for author_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        author_name = author_dir.name.strip() or "Unknown Author"
        for book_dir in sorted(p for p in author_dir.iterdir() if p.is_dir()):
            if has_audio(book_dir):
                yield author_name, book_dir


def target_for(author: str, book_dir: Path, dest_root: Path) -> Path:
    year, title = parse_book_folder(book_dir.name)
    author_slug = slug(author or "Unknown Author")
    book_slug = slug(f"{year} - {title}")
    return dest_root / author_slug / book_slug


def move_or_copy(src: Path, dst: Path, *, copy: bool) -> None:
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copytree(src, dst)
    else:
        shutil.move(src, dst)


def restructure_library(source: Path, dest: Path, *, dry: bool, copy: bool) -> Dict[str, int]:
    stats: Dict[str, int] = {"books": 0, "moved": 0, "dry_run": 0, "skipped": 0}
    for author, book_dir in discover_books(source):
        stats["books"] += 1
        destination = target_for(author, book_dir, dest)
        if dry:
            print(f"[dry-run] {book_dir} -> {destination}")
            stats["dry_run"] += 1
            continue
        try:
            move_or_copy(book_dir, destination, copy=copy)
            stats["moved"] += 1
            print(f"{'Copied' if copy else 'Moved'} {book_dir} -> {destination}")
        except FileExistsError:
            print(f"[skip] destination exists: {destination}")
            stats["skipped"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Restructure <source>/<Author>/<Book> into <dest>/<Author>/<Year - Title>",
    )
    parser.add_argument("source", type=Path, help="Source folder containing author subdirectories")
    parser.add_argument("destination", type=Path, help="Destination Audiobookshelf library root")
    parser.add_argument("--copy", action="store_true", help="Copy instead of move")
    parser.add_argument(
        action="store_true",
        help="Perform the move/copy (default is dry-run)",
    )
    parser.add_argument("--version", action="version", version=VERSION_INFO)
    args = parser.parse_args(argv)

    source = args.source.resolve()
    destination = args.destination.resolve()

    if not source.exists():
        print(f"Source folder not found: {source}", file=sys.stderr)
        return 1

    dry = not args.commit
    stats = restructure_library(source, destination, dry=dry, copy=args.copy)

    summary = (
        f"Processed {stats['books']} books "
        f"({'dry-run' if dry else 'moved'}) - "
        f"moved: {stats['moved']}, skipped: {stats['skipped']}"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
