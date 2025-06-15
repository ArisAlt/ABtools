#!/usr/bin/env python3
"""
ABtools/restructure_for_audiobookshelf.py – v4.4  (2025-06-15)
Use restructure_for_audiobookshelf.py "Source folder" "Destination folder" --commit 
• Recursively scans source_root; every directory that *contains* audio but whose
  sub-directories don’t is treated as one “book”.
• Reads tags with mutagen; if tags are missing yet the folder name matches one
  of seven patterns (see REGEX_PATTERNS), injects minimal tags with FFmpeg.
• Flattens sub-folders named “Disc 01 / Disc-02 …” into the main folder and
  (optionally) renames every track sequentially: Track 001.*, Track 002.* …
• Moves/renames into Audiobookshelf layout:

      <library_root>/Author/Series?/Vol # - YYYY - Title {Narrator}/
• Add --copy to duplicate folders instead of moving them
• ``--version`` prints the script version and file path
• Part suffixes like “(1 of 6)” or “Part 1” are preserved when moving
"""

from __future__ import annotations
import argparse, errno, os, re, shutil, subprocess, sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET

VERSION = "4.4"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

# ───────── configuration ─────────
AUDIO_EXTS: set[str]       = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}
RENAME_TRACKS              = True       # rename Track 001.* … inside each book?
WRITE_TAGS_WITH_FFMPEG     = False        # inject minimal tags when using folder info
DISC_RX                    = re.compile(r"disc[ _-]?(\d+)", re.I)

try:
    from mutagen import File as MFile, MutagenError
except ImportError:
    sys.exit("✗ mutagen not installed – run  'pip install mutagen'")

FFMPEG = shutil.which("ffmpeg")
if WRITE_TAGS_WITH_FFMPEG and not FFMPEG:
    print("⚠️  FFmpeg not found – tag injection disabled.")
    WRITE_TAGS_WITH_FFMPEG = False

# ───────── helpers ─────────
def slug(txt: str) -> str:
    txt = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", txt).strip()
    return txt.rstrip(" .")

def has_audio(d: Path) -> bool:
    return any(p.suffix.lower() in AUDIO_EXTS for p in d.iterdir())

def leaf_audio_dirs(root: Path) -> List[Path]:
    return [
        p for p in root.rglob("*")
        if p.is_dir() and has_audio(p)
        and not any(c.is_dir() and has_audio(c) for c in p.iterdir())
    ]

def safe_move(src: Path, dst: Path, copy: bool = False) -> None:
    """Move ``src`` to ``dst`` (or copy when ``copy`` is True) and ensure
    ``dst`` does not already exist."""
    if dst.exists():
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        return
    try:
        shutil.move(str(src), str(dst))
    except (PermissionError, OSError) as e:
        # Windows “access denied / file in use” or cross-device rename → copy
        if isinstance(e, OSError) and e.errno not in (errno.EXDEV, errno.EACCES):
            raise
        print("  ! rename failed – copying …")
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
            shutil.rmtree(src)
        else:
            shutil.copy2(str(src), str(dst))
            src.unlink()

# ───────── metadata ─────────
@dataclass
class BookMeta:
    author: str
    series: Optional[str]
    seq: Optional[str]
    year: Optional[str]
    title: str
    narr: Optional[str]

TAG_MAP = {
    "author": ("artist", "albumartist"),
    "series": ("series", "mvnm"),
    "seq":    ("series-part", "mvin"),
    "year":   ("date", "year"),
    "title":  ("album", "title"),
    "narr":   ("composer",),
}

def read_tags(track: Path) -> Optional[BookMeta]:
    try:
        audio = MFile(str(track), easy=True)
    except MutagenError:
        return None
    if not audio:
        return None
    def tag(*ks): return next((str(audio[k][0]) for k in ks if k in audio and audio[k]), None)
    m = {k: tag(*TAG_MAP[k]) for k in TAG_MAP}
    if not m["author"] and not m["title"]:
        return None
    seq  = m["seq"].split("/")[0] if m["seq"] and "/" in m["seq"] else m["seq"]
    yr   = m["year"][:4] if m["year"] else None
    return BookMeta(m["author"] or "Unknown Author", m["series"], seq, yr,
                    m["title"] or track.stem, m["narr"])

def read_nfo(folder: Path) -> Optional[BookMeta]:
    nfo = folder / "book.nfo"
    if not nfo.is_file():
        return None
    try:
        root = ET.parse(str(nfo)).getroot()
    except ET.ParseError:
        return None
    def txt(tag: str) -> Optional[str]:
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else None
    meta = BookMeta(
        author=txt("author") or "Unknown Author",
        series=txt("series"),
        seq=txt("seq"),
        year=txt("year"),
        title=txt("title") or folder.name,
        narr=txt("narr"),
    )
    if not meta.author and not meta.title:
        return None
    return meta

def merge_meta(primary: Optional[BookMeta], secondary: Optional[BookMeta]) -> Optional[BookMeta]:
    if not secondary:
        return primary
    if not primary:
        return secondary
    for field in primary.__dataclass_fields__:
        if not getattr(primary, field):
            setattr(primary, field, getattr(secondary, field))
    return primary

# ───────── folder-name patterns ─────────
REGEX_PATTERNS: list[re.Pattern[str]] = [
    # A  Author - (Series #) - YYYY - Title {Narrator}
    re.compile(r"""
        ^\s*(?P<author>.+?)\s*-\s*
        (?:(?P<series>[^-\[({]+?)\s*[-#]?\s*(?P<seq>\d+)?\s*-\s*)?
        (?P<year>\d{4})?\s*-\s*
        (?P<title>[^({\[]+?)
        (?:\s*\{(?P<narr>[^}]+)\})?
        \s*$""", re.VERBOSE),
    # B  Title [Series -#] - Author
    re.compile(r"""
        ^\s*(?P<title>.+?)\s*
        \[\s*(?P<series>[^\]-]+?)\s*-\s*(?P<seq>\d+)\s*]\s*-\s*
        (?P<author>.+?)\s*$""", re.VERBOSE),
    # C  Series - Author\[YYYY] Title
    re.compile(r"""
        ^\s*(?P<series>[^-\[]+?)\s*-\s*
        (?P<author>[^\[]+?)\s*\\\[\s*(?P<year>\d{4})]\s*
        (?P<title>.+?)\s*$""", re.VERBOSE),
    # D  [YYYY] Title          (author/series pulled from parent)
    re.compile(r"""
        ^\s*\[\s*(?P<year>\d{4})]\s*
        (?P<title>.+?)\s*$""", re.VERBOSE),
    # E  Author - Title (YYYY)
    re.compile(r"""
        ^\s*(?P<author>.+?)\s*-\s*
        (?P<title>.+?)\s*\(\s*(?P<year>\d{4})\s*\)\s*$""", re.VERBOSE),
    # F  Title - Author (YYYY)
    re.compile(r"""
        ^\s*(?P<title>.+?)\s*-\s*
        (?P<author>.+?)\s*\(\s*(?P<year>\d{4})\s*\)\s*$""", re.VERBOSE),
    # G  Author\[YYYY] Title
    re.compile(r"""
        ^\s*(?P<author>.+?)\s*\\\[\s*(?P<year>\d{4})]\s*
        (?P<title>.+?)\s*$""", re.VERBOSE),
]
CLEAN_TAIL_RX = re.compile(
    r"""                      # strip from the right end:
        (?:\s*\((?!(?:\d+\s*of\s*\d+|[Pp]art\s*\d+))[^)]*\))?  #  (Lee) but keep (1 of 6) / (Part 1)
        (?:\s*\d+\s*[kK])?        #  64k / 128K  bitrate
        (?:\s*\d+\.\d{2}\.\d{2})? #  12.56.09  (h.mm.ss)
        (?:\s*\{[^}]*\})?         #  {303mb}
        \s*$                      #  nothing after that
    """,
    re.VERBOSE,
)
def clean_title(raw: str, year: str | None) -> str:
    """Return title without bitrate / size / duration tails."""
    txt = CLEAN_TAIL_RX.sub("", raw).strip()
    # if it still starts with 'YYYY -', drop it (already stored in meta.year)
    if year and txt.startswith(year):
        after = txt[len(year):].lstrip(" -")
        txt = after or txt
    return txt


def parse_folder(folder: Path) -> Optional[BookMeta]:
    name = folder.name
    for rx in REGEX_PATTERNS:
        m = rx.match(name)
        if not m:
            continue
        g = {k: (v.strip() if v else v) for k, v in m.groupdict().items()}
        # Pattern D needs author/series from parent if available
        if rx is REGEX_PATTERNS[3] and folder.parent != folder:
            parent = parse_folder(folder.parent)
            if parent:
                g.setdefault("author", parent.author)
                g.setdefault("series", parent.series)
        cleaned_title = clean_title(g.get("title") or name, g.get("year"))
        return BookMeta(
            g.get("author") or "Unknown Author",
            g.get("series"),
            g.get("seq"),
            g.get("year"),
            cleaned_title,
            g.get("narr"),
        )
        
    return None

def inject_tags(track: Path, meta: BookMeta):
    if not (WRITE_TAGS_WITH_FFMPEG and FFMPEG):
        return
    tmp = track.with_suffix(track.suffix + ".tmp")
    cmd = [
        FFMPEG, "-nostdin", "-loglevel", "error", "-y",
        "-i", str(track), "-codec", "copy",
        "-metadata", f"artist={meta.author}",
        "-metadata", f"album={meta.title}",
        "-metadata", f"album_artist={meta.author}",
        "-metadata", f"title={track.stem}",
    ]
    if meta.year:
        cmd += ["-metadata", f"date={meta.year}"]
    if meta.narr:
        cmd += ["-metadata", f"composer={meta.narr}"]
    if meta.series:
        comment = f"Series: {meta.series}" + (f" #{meta.seq}" if meta.seq else "")
        cmd += ["-metadata", f"comment={comment}"]
    cmd.append(str(tmp))
    if subprocess.run(cmd, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0 and tmp.exists():
        tmp.replace(track)

# ───────── disc-flattener ─────────
def flatten_discs(book_dir: Path, dry: bool):
    discs = sorted(
        [(int(m.group(1)), p) for p in book_dir.iterdir() if p.is_dir()
         for m in [DISC_RX.search(p.name)] if m],
        key=lambda t: t[0]
    )
    if not discs:
        return
    top_tracks = sorted(p for p in book_dir.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    tracks: list[Path] = top_tracks + [
        t for _, d in discs
        for t in sorted(p for p in d.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    ]
    digits = len(str(len(tracks)))
    print(f"  · Flattening {len(discs)} disc folders → {len(tracks)} tracks")
    for idx, p in enumerate(tracks, 1):
        new = book_dir / f"Track {idx:0{digits}d}{p.suffix.lower()}"
        if p != new:
            print(f"    {'mv' if not dry else '↪'} {p.name} → {new.name}")
            if not dry:
                safe_move(p, new)
    if not dry:
        for _, d in discs:
            try: d.rmdir()
            except OSError: pass

def rename_tracks(folder: Path):
    if not RENAME_TRACKS:
        return
    tracks = [p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTS]
    digits = len(str(len(tracks)))
    for i, p in enumerate(sorted(tracks), 1):
        new = p.with_name(f"Track {i:0{digits}d}{p.suffix.lower()}")
        if new != p:
            p.rename(new)

# ───────── process one book ─────────
def process(book: Path, library: Path, dry: bool, copy: bool, st: defaultdict):
    st["total"] += 1
    first = next((p for p in book.iterdir() if p.suffix.lower() in AUDIO_EXTS), None)
    if not first:
        print("• Skipping (no audio):", book)
        st["no_audio"] += 1
        return

    meta = merge_meta(read_tags(first), read_nfo(book))
    meta = merge_meta(meta, parse_folder(book))
    if not meta:
        meta = BookMeta(
            author="Unknown Author",
            series=None,
            seq=None,
            year=None,
            title=clean_title(book.name, None),
            narr=None,
        )
        print(f"  · No metadata found: using folder name “{meta.title}”")
    elif not read_tags(first):
        print(f"  · Tags missing – derived metadata “{meta.title}”")
    

    # inject tags when original files lacked metadata
    if WRITE_TAGS_WITH_FFMPEG and not dry and not read_tags(first) and not read_nfo(book):
        for t in book.iterdir():
            if t.suffix.lower() in AUDIO_EXTS:
                inject_tags(t, meta)

    author_dir = slug(meta.author)
    title_parts = [
        f"Vol {meta.seq}" if meta.seq else None,
        meta.year,
        meta.title,
        f"{{{meta.narr}}}" if meta.narr else None,
    ]
    title_dir = slug(" - ".join(p for p in title_parts if p))

    dest = library / author_dir
    if meta.series:
        dest /= slug(meta.series)
    dest /= title_dir

    if dest.exists():
        print("• Destination exists, skipping:", dest)
        st["exists"] += 1
        return

    action = 'cp' if copy else 'mv'
    print(f"{action if not dry else '↪'} {book} → {dest}")
    if dry:
        flatten_discs(book, dry=True)
        if RENAME_TRACKS:
            rename_tracks(book)
        st["would_move"] += 1
        return

    safe_move(book, dest, copy=copy)
    flatten_discs(dest, dry=False)
    if RENAME_TRACKS:
        rename_tracks(dest)
    st["moved"] += 1

# ───────── main driver ─────────
def main(src: Path, library: Path, commit: bool, copy: bool):
    if not src.is_dir():
        sys.exit(f"✗ Source folder not found: {src}")

    stats: defaultdict[str, int] = defaultdict(int)
    for bd in leaf_audio_dirs(src):
        process(bd, library, dry=not commit, copy=copy, st=stats)

    print("\n──── Summary ────")
    print(f" Books scanned            : {stats['total']}")
    action_word = 'copied' if copy else 'moved'
    print(f" Books {action_word:20}: {stats['moved']}")
    if not commit:
        print(f" Books that would move    : {stats['would_move']}")
    for k, label in (
        ("exists", "Destination exists"),
        ("no_audio", "No audio"),
        ("tag_fail", "Tag/name unreadable"),
    ):
        if stats[k]:
            print(f" {label:25}: {stats[k]}")
    print("──── Done ────\n")

# ───────── CLI entry ─────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Recursively tidy audiobook folders for Audiobookshelf."
    )
    ap.add_argument("source_root", type=Path, help="Folder to scan recursively")
    ap.add_argument("library_root", type=Path, help="Audiobookshelf library root")
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Actually move/rename (omit for preview)",
    )
    ap.add_argument(
        "--copy",
        action="store_true",
        help="Copy instead of move when --commit is used",
    )
    ap.add_argument("--version", action="version", version=VERSION_INFO)
    args = ap.parse_args()
    main(args.source_root, args.library_root, args.commit, args.copy)
