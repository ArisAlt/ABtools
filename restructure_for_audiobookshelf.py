#!/usr/bin/env python3
"""
ABtools/restructure_for_audiobookshelf.py · v5.4  (2025-09-10)
Use restructure_for_audiobookshelf.py "Source folder" "Destination folder" --commit 
â€¢ Recursively scans source_root; every directory that *contains* audio but whose
  sub-directories donâ€™t is treated as one â€œbookâ€.
â€¢ Reads tags with mutagen. If ``metadata.json`` or ``book.nfo`` files are
  present, those values are used as well. If tags are missing yet the folder
  name matches one of seven patterns (see REGEX_PATTERNS), injects minimal tags
  with FFmpeg.
â€¢ Flattens sub-folders named â€œDisc 01 / Disc-02 â€¦â€ into the main folder and
  (optionally) renames every track sequentially: Track 001.*, Track 002.* â€¦
â€¢ Moves/renames into Audiobookshelf layout:

      <library_root>/Author/Series?/Title (Year)/
â€¢ Add --copy to duplicate folders instead of moving them
â€¢ ``--version`` prints the script version and file path
â€¢ Fuzzy series matching ("Book 3", "#3", "Volume III", etc.)
â€¢ ``--interactive`` prompts for series info when uncertain
â€¢ Part suffixes like â€œ(1 of 6)â€ or â€œPart 1â€ are preserved when moving

Examples::

    restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --commit
    restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --commit --copy
"""

from __future__ import annotations
import argparse, errno, os, re, shutil, subprocess, sys, json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET

VERSION = "5.4"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€
AUDIO_EXTS: set[str]       = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}
RENAME_TRACKS              = True       # rename Track 001.* â€¦ inside each book?
WRITE_TAGS_WITH_FFMPEG     = False        # inject minimal tags when using folder info
DISC_RX                    = re.compile(r"disc[ _-]?(\d+)", re.I)

try:
    from mutagen import File as MFile, MutagenError
except ImportError:
    MFile = None
    class MutagenError(Exception):
        pass

FFMPEG = shutil.which("ffmpeg")
if WRITE_TAGS_WITH_FFMPEG and not FFMPEG:
    print("âš ï¸  FFmpeg not found â€“ tag injection disabled.")
    WRITE_TAGS_WITH_FFMPEG = False

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        # Windows â€œaccess denied / file in useâ€ or cross-device rename â†’ copy
        if isinstance(e, OSError) and e.errno not in (errno.EXDEV, errno.EACCES):
            raise
        print("  ! rename failed â€“ copying â€¦")
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
            shutil.rmtree(src)
        else:
            shutil.copy2(str(src), str(dst))
            src.unlink()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ fuzzy series helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€
ROMAN_MAP = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

def roman_to_int(s: str) -> Optional[int]:
    """Return integer for Roman numeral ``s`` or ``None``."""
    total = 0
    prev = 0
    for ch in reversed(s.upper()):
        val = ROMAN_MAP.get(ch)
        if not val:
            return None
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total or None

FUZZY_RX = re.compile(
    r"(?P<series>[^#(]+?)\s*(?:\(|\[)?(?:#|(?:book|bk|vol(?:ume)?)\s*)"
    r"(?P<num>\d+|[IVXLCDM]+)(?:\)|\])?",
    re.I,
)
SEQ_PREFIX_RX = re.compile(r"^\s*(?P<num>\d+)\s*[-_.]")

def fuzzy_series(text: str) -> tuple[Optional[str], Optional[str]]:
    """Return (series, seq) if found in ``text`` via fuzzy patterns."""
    m = FUZZY_RX.search(text)
    if m:
        series = m.group("series").strip()
        num = m.group("num")
        if num.isdigit():
            return series, num
        n = roman_to_int(num)
        return series, str(n) if n else None
    m = SEQ_PREFIX_RX.match(text)
    if m:
        return None, m.group("num")
    return None, None

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ metadata â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

def read_json(folder: Path) -> Optional[BookMeta]:
    js = folder / "metadata.json"
    if not js.is_file():
        return None
    try:
        with js.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    meta = BookMeta(
        author=data.get("author") or "Unknown Author",
        series=data.get("series"),
        seq=data.get("seq"),
        year=data.get("year"),
        title=data.get("title") or folder.name,
        narr=data.get("narr") or data.get("narrator"),
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ folder-name patterns â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

def inject_tags(track: Path, meta: BookMeta, index: int = 0, total: int = 0):
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
    if index:
        cmd += ["-metadata", f"track={index}/{total or index}"]
    cmd.append(str(tmp))
    if subprocess.run(cmd, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0 and tmp.exists():
        tmp.replace(track)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ disc-flattener â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    print(f"  Â· Flattening {len(discs)} disc folders â†’ {len(tracks)} tracks")
    for idx, p in enumerate(tracks, 1):
        new = book_dir / f"Track {idx:0{digits}d}{p.suffix.lower()}"
        if p != new:
            print(f"    {'mv' if not dry else 'â†ª'} {p.name} â†’ {new.name}")
            if not dry:
                safe_move(p, new)
    if not dry:
        for _, d in discs:
            try: d.rmdir()
            except OSError: pass

def rename_tracks(folder: Path):
    if not RENAME_TRACKS:
        return
    tracks = sorted(p for p in folder.iterdir()
                    if p.suffix.lower() in AUDIO_EXTS)
    digits = len(str(len(tracks)))
    tmp_files: list[Path] = []
    # first rename to temporary names to avoid collisions
    for idx, p in enumerate(tracks):
        tmp = folder / f".tmp_{idx:0{digits}d}{p.suffix.lower()}"
        p.rename(tmp)
        tmp_files.append(tmp)
    # now rename sequentially to final names
    for i, tmp in enumerate(tmp_files, 1):
        final = folder / f"Track {i:0{digits}d}{tmp.suffix.lower()}"
        tmp.rename(final)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ process one book â”€â”€â”€â”€â”€â”€â”€â”€â”€
def process(book: Path, library: Path, dry: bool, copy: bool, st: defaultdict,
            interactive: bool = False):
    st["total"] += 1
    first = next((p for p in book.iterdir() if p.suffix.lower() in AUDIO_EXTS), None)
    if not first:
        print("â€¢ Skipping (no audio):", book)
        st["no_audio"] += 1
        return

    meta = merge_meta(read_tags(first), read_json(book))
    meta = merge_meta(meta, read_nfo(book))
    meta = merge_meta(meta, parse_folder(book))
    if not meta or not meta.series or not meta.seq:
        fs, fq = fuzzy_series(book.name)
        if fs and (not meta or not meta.series):
            meta = meta or BookMeta("Unknown Author", None, None, None,
                                   clean_title(book.name, None), None)
            if not meta.series:
                meta.series = fs
        if fq and (not meta or not meta.seq):
            meta = meta or BookMeta("Unknown Author", None, None, None,
                                   clean_title(book.name, None), None)
            if not meta.seq:
                meta.seq = fq
    if not meta:
        meta = BookMeta(
            author="Unknown Author",
            series=None,
            seq=None,
            year=None,
            title=clean_title(book.name, None),
            narr=None,
        )
        print(f"  Â· No metadata found: using folder name â€œ{meta.title}â€")
    elif not read_tags(first):
        print(f"  Â· Tags missing â€“ derived metadata â€œ{meta.title}â€")

    if interactive and (not meta.series or not meta.seq):
        print(f"  Â· Missing series info for {book.name}")
        if not meta.series:
            ans = input("    Series name (blank to skip): ").strip()
            if ans:
                meta.series = ans
        if meta.series and not meta.seq:
            ans = input("    Sequence number: ").strip()
            if ans:
                meta.seq = ans
    

    # inject tags when original files lacked metadata
    if (WRITE_TAGS_WITH_FFMPEG and not dry and not read_tags(first)
            and not read_json(book) and not read_nfo(book)):
        tracks = sorted(p for p in book.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        for idx, t in enumerate(tracks, 1):
            inject_tags(t, meta, idx, len(tracks))

    author_dir = slug(meta.author)
    dest = library / author_dir
    if meta.series:
        dest /= slug(meta.series)
    title_text = meta.title or clean_title(book.name, meta.year)
    if meta.year:
        title_text = f"{title_text} ({meta.year})"
    title_dir = slug(title_text)
    dest /= title_dir
    if dest.exists():
        print("â€¢ Destination exists, skipping:", dest)
        st["exists"] += 1
        return

    action = 'cp' if copy else 'mv'
    print(f"{action if not dry else 'â†ª'} {book} â†’ {dest}")
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ main driver â”€â”€â”€â”€â”€â”€â”€â”€â”€
def main(src: Path, library: Path, commit: bool, copy: bool, interactive: bool):
    if not src.is_dir():
        sys.exit(f"âœ— Source folder not found: {src}")

    stats: defaultdict[str, int] = defaultdict(int)
    for bd in leaf_audio_dirs(src):
        process(bd, library, dry=not commit, copy=copy, st=stats,
                interactive=interactive)

    print("\nâ”€â”€â”€â”€ Summary â”€â”€â”€â”€")
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
    print("â”€â”€â”€â”€ Done â”€â”€â”€â”€\n")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€ CLI entry â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Recursively tidy audiobook folders for Audiobookshelf."
    )
    ap.add_argument("paths", nargs="+", metavar=("source_root", "library_root"))
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
    ap.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for series info when not detected",
    )
    ap.add_argument("--version", action="version", version=VERSION_INFO)
    args = ap.parse_args()

    if len(args.paths) < 2:
        ap.error("source_root and library_root required")

    raw = args.paths
    src = None
    for i in range(1, len(raw)):
        cand = Path(" ".join(raw[:i])).expanduser()
        if cand.exists():
            src = cand
            dst = Path(" ".join(raw[i:])).expanduser()
            break
    if src is None:
        src = Path(raw[0]).expanduser()
        dst = Path(" ".join(raw[1:])).expanduser()

    main(src, dst, args.commit, args.copy, args.interactive)


