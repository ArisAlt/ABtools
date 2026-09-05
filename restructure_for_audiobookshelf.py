#!/usr/bin/env python3
"""
Audiobookshelf library reshaper - v5.5

Reorganises audiobooks into Audiobookshelf canonical directory layout:

    <dest_root>/<Author>/[Series]/<Title (Year)>

When year is unknown or missing, the leaf folder is named simply:

    <dest_root>/<Author>/[Series]/<Title>

Metadata is resolved in priority order:
  1. Embedded audio file tags (ID3, MP4, Vorbis)
  2. Sidecar metadata files (metadata.json, book.nfo)
  3. Folder name heuristics and directory tree hierarchy
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from ablib.metadata.utils import (
    extract_series_and_title,
    format_canonical_dest,
    is_plausible_author,
    parse_book_folder_name,
    primary_author,
)
from ablib.tagging.files import read_sidecar_metadata, read_tags, upgrade_sidecar

VERSION = "5.8"
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
DISC_RX = re.compile(r"^(?:cd|disc|disk|part|pt)[\s._-]*\d+$", re.IGNORECASE)


def is_bare_disc_marker(name: str) -> bool:
    """True when folder name is a bare disc or part marker (e.g. 'Disc 1', 'CD2')."""
    return bool(DISC_RX.match(name.strip()))


def disc_children(folder: Path) -> list[Path]:
    """Return child folders if all child subdirectories are bare disc markers."""
    try:
        subdirs = [p for p in folder.iterdir() if p.is_dir()]
    except OSError:
        return []
    if subdirs and all(is_bare_disc_marker(c.name) for c in subdirs):
        return subdirs
    return []


def has_audio(folder: Path) -> bool:
    """Return True if the folder contains audio files or bare disc subfolders with audio."""
    try:
        if any(p.is_file() and p.suffix.lower() in AUDIO_EXTS for p in folder.iterdir()):
            return True
        discs = disc_children(folder)
        if discs:
            return any(
                any(f.is_file() and f.suffix.lower() in AUDIO_EXTS for f in d.iterdir())
                for d in discs
            )
        return False
    except (OSError, FileNotFoundError):
        return False


def parse_book_folder(name: str) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    Extract (year, author, series, title) from a folder name using heuristics.

    Delegates the "<Author> - <Series> - Book <N> - <Title>" family to the
    shared `parse_book_folder_name`, so this tool and combobook read a
    self-describing leaf identically (bug.md 4.8). The leading ``YYYY -``
    prefix and bare leading index are handled here, as combobook never emits
    them.
    """
    raw = name.strip()
    year: str | None = None

    prefix = YEAR_PREFIX_RX.match(raw)
    if prefix:
        year = prefix.group(1)
        raw = raw[prefix.end() :].strip(" -_.")

    parsed = parse_book_folder_name(raw)
    year = year or parsed["year"]
    author = parsed["author"]
    series = parsed["series"]
    title = (parsed["title"] or "").strip(" -_:.")

    if not series:
        title = LEADING_INDEX_RX.sub("", title).strip(" -_:.")
    if not title:
        title = "Untitled"

    return year, author, series, title


def discover_books(source_root: Path) -> Iterable[Tuple[str, Path]]:
    """
    Yield ``(author_name, book_dir)`` pairs for folders containing audio.

    Walks the whole tree rather than assuming a fixed depth, so
    ``<source>/<Author>/<Book>``, ``<source>/<Author>/<Series>/<Book>``,
    a book sitting directly at ``<source>/<Book>``, and ``source_root``
    itself being one book are all found. The previous version iterated
    top-level directories as authors and only ever yielded at depth 2 or 3,
    silently dropping the last two shapes and still reporting success
    (bug.md 4.13 -- the same fault as 4.2, which was fixed in combobook and
    ablib.cli.main but never here).

    A multi-disc book yields the *book* folder, not one entry per disc.
    ``author_name`` is empty when the layout carries no author level; the
    caller resolves it from tags, sidecars and the folder name instead.
    """
    leaves: list[Path] = []
    disc_dirs: set[Path] = set()
    for candidate in [source_root, *sorted(source_root.rglob("*"))]:
        if not candidate.is_dir():
            continue
        discs = disc_children(candidate)
        if discs:
            leaves.append(candidate)   # the discs are parts of this book
            disc_dirs.update(discs)
            continue
        if not has_audio(candidate):
            continue
        try:
            if any(c.is_dir() and has_audio(c) for c in candidate.iterdir()):
                continue               # audio-bearing sub-folders -> not a leaf
        except OSError:
            continue
        leaves.append(candidate)

    for book_dir in leaves:
        if book_dir in disc_dirs:
            continue
        try:
            depth = len(book_dir.relative_to(source_root).parts)
        except ValueError:
            depth = 0
        # <source>/<Author>/... has an author level; <source>/<Book> does not.
        author_name = book_dir.parents[depth - 2].name.strip() if depth >= 2 else ""
        yield author_name, book_dir


def _find_audio_file(folder: Path) -> Optional[Path]:
    """Find the first audio file in folder or in bare disc subdirectories."""
    try:
        for item in sorted(folder.iterdir()):
            if item.is_file() and item.suffix.lower() in AUDIO_EXTS:
                return item
        for disc in disc_children(folder):
            for item in sorted(disc.iterdir()):
                if item.is_file() and item.suffix.lower() in AUDIO_EXTS:
                    return item
    except OSError:
        pass
    return None


def resolve_book_metadata(
    author: str,
    book_dir: Path,
    series: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Work out a book's author / title / year / series from what is on disk.

    Priority order:
      1. Embedded audio tags
      2. Sidecars (metadata.json, book.nfo)
      3. Folder name & directory structure hierarchy

    Split out of `target_for` so the caller can see *what* was resolved, not
    just where it would land -- `restructure_library` needs to know the author
    was never identified in order to decline the move (bug.md 4.14).
    """
    # 1. Inspect embedded tags
    audio_file = _find_audio_file(book_dir)
    tag_meta = read_tags(audio_file) if audio_file else {}

    # 2. Inspect sidecars
    sidecar = read_sidecar_metadata(book_dir)

    # 3. Folder name and hierarchy heuristics
    folder_year, folder_author, folder_series, folder_title = parse_book_folder(book_dir.name)
    # Only <source>/<Author>/<Series>/<Book> has a series level. Without the
    # `author` check a book found directly at the source root would take the
    # source directory's own name as its series.
    parent_is_series = bool(
        author
        and book_dir.parent.name != author
        and book_dir.parent != book_dir.parent.parent
    )
    hierarchy_series = book_dir.parent.name if parent_is_series else None

    # Merge metadata with documented precedence.
    # The tag author is only used once it survives is_plausible_author(): rips
    # frequently carry a disc marker or the filename in `artist`, and this
    # value becomes a top-level library folder. The same guard runs in
    # combobook.process(), so both organisers reject the same junk.
    tag_author = tag_meta.get("author")
    if tag_author and not is_plausible_author(
        tag_author, filename_stem=audio_file.stem if audio_file else None
    ):
        tag_author = None

    # The hierarchy author is just a directory name, and the source tree can be
    # as wrong as the tags ("Side 01/<book>"). Validate it the same way, or the
    # junk simply arrives from a different direction.
    hierarchy_author = author if is_plausible_author(author) else None

    resolved_author = primary_author(
        tag_author
        or sidecar.get("author")
        or folder_author
        or hierarchy_author
    ) or "Unknown Author"

    resolved_title = (
        tag_meta.get("title")
        or sidecar.get("title")
        or folder_title
        or book_dir.name
    )
    resolved_year = (
        tag_meta.get("year")
        or sidecar.get("year")
        or folder_year
    )
    resolved_series = (
        series
        or tag_meta.get("series")
        or sidecar.get("series")
        or folder_series
    )
    # An album frame often carries the series inline ("Serpentwar Saga 03 - Rage
    # of a Demon King"). Always strip it off the title -- doing this only when
    # the series was still unknown left the prefix duplicated in the leaf name.
    if resolved_title:
        parsed_series, _, parsed_title = extract_series_and_title(resolved_title)
        if parsed_series and parsed_title:
            resolved_series = resolved_series or parsed_series
            resolved_title = parsed_title
    resolved_series = resolved_series or hierarchy_series

    return {
        "author": resolved_author,
        "title": resolved_title,
        "year": resolved_year,
        "series": resolved_series,
    }


def target_for(
    author: str,
    book_dir: Path,
    dest_root: Path,
    series: Optional[str] = None,
) -> Path:
    """Destination path in Audiobookshelf canonical layout:
    ``<dest_root>/<author>/[series]/<title (year)>``."""
    resolved = resolve_book_metadata(author, book_dir, series)
    return format_canonical_dest(
        dest_root=dest_root,
        author=resolved["author"],
        title=resolved["title"],
        year=resolved["year"],
        series=resolved["series"],
    )


def move_or_copy(src: Path, dst: Path, *, copy: bool) -> None:
    """Move or copy book directory to destination path."""
    if dst.resolve() == src.resolve():
        return
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copytree(src, dst)
    else:
        shutil.move(src, dst)


def refresh_sidecars(root: Path, *, dry: bool, force: bool = False) -> Dict[str, int]:
    """Rewrite every book's sidecars under `root` in the current schema.

    Libraries tagged before the Audiobookshelf schema fix keep their old flat
    metadata.json: the organisers move sidecars, they never rewrite them, so
    the fix does not reach books already on disk. This walks an existing
    library and upgrades them in place, moving nothing.
    """
    stats: Dict[str, int] = {"books": 0, "upgraded": 0, "already_current": 0}
    for _, book_dir in discover_books(root):
        stats["books"] += 1
        if dry:
            from ablib.tagging.files import sidecar_is_current
            if force or not sidecar_is_current(book_dir):
                print(f"[dry-run] would refresh sidecars: {book_dir}")
                stats["upgraded"] += 1
            else:
                stats["already_current"] += 1
            continue
        if upgrade_sidecar(book_dir, force=force):
            print(f"Refreshed sidecars: {book_dir}")
            stats["upgraded"] += 1
        else:
            stats["already_current"] += 1
    return stats


UNKNOWN_AUTHOR = "Unknown Author"


def restructure_library(
    source: Path,
    dest: Path,
    *,
    dry: bool,
    copy: bool,
    move_unmatched: bool = False,
) -> Dict[str, int]:
    """Restructure books under source into Audiobookshelf canonical layout under dest.

    A book whose author nothing could identify is left where it is unless
    `move_unmatched` is set. This tool has no provider or LLM fallback to
    recover with, so filing it under "Unknown Author/" is `_unmatched/` by
    another name -- and its position in the source tree is the last evidence
    about what it is (bug.md 4.12, 4.14).
    """
    stats: Dict[str, int] = {
        "books": 0, "moved": 0, "dry_run": 0, "skipped": 0, "left_in_place": 0,
    }
    for author, book_dir in discover_books(source):
        stats["books"] += 1
        resolved = resolve_book_metadata(author, book_dir)
        if resolved["author"] == UNKNOWN_AUTHOR and not move_unmatched:
            print(f"[unidentified] left in place: {book_dir}")
            stats["left_in_place"] += 1
            continue
        destination = format_canonical_dest(
            dest_root=dest,
            author=resolved["author"],
            title=resolved["title"],
            year=resolved["year"],
            series=resolved["series"],
        )
        if destination.resolve() == book_dir.resolve():
            stats["skipped"] += 1
            continue
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
        description="Restructure <source>/<Author>/[Series]/<Book> into <dest>/<Author>/[Series]/<Title (Year)>",
    )
    parser.add_argument("source", type=Path, help="Source folder containing author subdirectories")
    parser.add_argument(
        "destination",
        type=Path,
        nargs="?",
        help="Destination Audiobookshelf library root "
             "(not required with --refresh-sidecars, which moves nothing)",
    )
    parser.add_argument("--copy", action="store_true", help="Copy instead of move")
    parser.add_argument(
        "--refresh-sidecars",
        action="store_true",
        help="Rewrite metadata.json / book.nfo under SOURCE in the current "
             "Audiobookshelf schema and move nothing. Use on a library that "
             "was tagged before the schema fix.",
    )
    parser.add_argument(
        "--move-unmatched",
        action="store_true",
        help=f"Move books whose author could not be identified into "
             f"<destination>/{UNKNOWN_AUTHOR}/ (default: leave them in place)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Perform the move/copy (default is dry-run)",
    )
    parser.add_argument("--version", action="version", version=VERSION_INFO)
    args = parser.parse_args(argv)

    source = args.source.resolve()

    if not source.exists():
        print(f"Source folder not found: {source}", file=sys.stderr)
        return 1

    dry = not args.commit

    if args.refresh_sidecars:
        sidecar_stats = refresh_sidecars(source, dry=dry)
        print(
            f"Inspected {sidecar_stats['books']} books "
            f"({'dry-run' if dry else 'applied'}) - "
            f"refreshed: {sidecar_stats['upgraded']}, "
            f"already current: {sidecar_stats['already_current']}"
        )
        return 0

    if args.destination is None:
        parser.error("destination is required unless --refresh-sidecars is given")
    destination = args.destination.resolve()

    stats = restructure_library(
        source, destination, dry=dry, copy=args.copy,
        move_unmatched=args.move_unmatched,
    )

    summary = (
        f"Processed {stats['books']} books "
        f"({'dry-run' if dry else 'moved'}) - "
        f"moved: {stats['moved']}, skipped: {stats['skipped']}, "
        f"left in place: {stats['left_in_place']}"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
