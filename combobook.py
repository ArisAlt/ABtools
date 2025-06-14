#!/usr/bin/env python3

ABtools/combobook.py  ·  v1.3  ·  2025-06-14

USAGE
-----
# dry-run (preview only)
python combo_abooks.py  "E:\\Audio Books"  "G:\\AudiobookShelf"

# tag + move, ask Y/N for each metadata hit
python combo_abooks.py  "E:\\Audio Books"  "G:\\AudiobookShelf"  --commit

# tag + move, auto-accept every hit
python combo_abooks.py  "E:\\Audio Books"  "G:\\AudiobookShelf"  --commit  --yes
"""

from __future__ import annotations
import argparse, re, shutil, subprocess, sys, textwrap, json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from difflib import SequenceMatcher

# ───────────── configuration ────────────────────────────────────────────────
AUDIO_EXTS   = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}
FLATTEN_DISCS = True
RENAME_TRACKS = False          # Track 001.*, Track 002.* …
WRITE_TAGS    = True           # needs ffmpeg on PATH
AUTO_YES      = False          # --yes overrides per-run

# “disc / disk / cd / part” + optional ()[]{}
DISC_RX = re.compile(
    r'(?:[\(\[{]?)(?:disc|disk|cd|part)[\s_\-]*(?P<num>\d{1,3})(?:[\)\]}]?)',
    re.IGNORECASE,
)
# also match "(1 of 5)" / "(3/5)" patterns
PART_RX = re.compile(r"\((?P<num>\d{1,3})\s*(?:of|/)?\s*\d{1,3}\)", re.IGNORECASE)

# ︙ — regular expressions carried over from search_and_tag.py — ︙
TAIL_RX  = re.compile(r"(?:\{[^}]*\})?(?:\s*\d+\.\d{2}\.\d{2})?(?:\s*\d+\s*[kK])?\s*$")
PAREN_RX = re.compile(r"\([^)]*\)")
YEAR_RX  = re.compile(r"^(\d{4})\s*[-_]\s*")
LEAF_RX = re.compile(
    r"""^\s*
        (?:(?P<seq>\d+)\s*[-_]\s*)?   # optional  '5 - '
        (?P<title>.+?)                #          'Jaws of Darkness'
        \s*\(\s*(?P<year>\d{4})\s*\)  #          '(2003)'
        \s*$""", re.VERBOSE)

PARENT_RANGE_RX = re.compile(
    r"""^(?P<series>.+?)\s*\(\s*\d{4}\s*-\s*\d{4}\s*\)\s*$""", re.VERBOSE)
SEQ_TITLE_YEAR_RX = re.compile(
    r"^\s*(?P<seq>\d+)\s*[-_]\s*(?P<title>.+?)\s*\(\s*(?P<year>\d{4})\s*\)\s*$"
)
# ───────────── optional deps ────────────────────────────────────────────────
try:
    import requests, mutagen
    from mutagen import File as MFile
    from bs4 import BeautifulSoup
except ImportError as e:
    sys.exit(
        "missing dependency: {}  ➜  pip install mutagen requests beautifulsoup4".format(
            e.name
        )
    )

# colour
try:
    from rich import print as rprint
    from rich.prompt import Confirm
except ImportError:
    _T = re.compile(r"\[/?[a-z]+.*?]", re.I)
    def rprint(*a, **k): print(_T.sub("", " ".join(map(str, a))), **k)
    class Confirm:
        @staticmethod
        def ask(q:str, default:bool=False):
            ans=input(f"{q} [{'Y/n' if default else 'y/N'}] ").strip().lower()
            return default if ans=="" else ans in {"y","yes"}

FFMPEG = shutil.which("ffmpeg") if WRITE_TAGS else None
if WRITE_TAGS and not FFMPEG:
    rprint("[yellow]⚠ FFmpeg not found – tag writing disabled.[/]")
    WRITE_TAGS = False
    

# ───────────── dataclass ────────────────────────────────────────────────────
@dataclass
class Meta:
    author:str
    title:str
    year:Optional[str]=None
    series:Optional[str]=None
    seq:Optional[str]=None
    narr:Optional[str]=None

# ───────────── helpers ──────────────────────────────────────────────────────
def slug(t:str)->str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]',"",t).strip().rstrip(" .")

def leaf_dirs(root:Path)->List[Path]:
    return [p for p in root.rglob("*")
            if p.is_dir()
            and any(f.suffix.lower() in AUDIO_EXTS for f in p.iterdir())
            and not any(c.is_dir() and any(g.suffix.lower() in AUDIO_EXTS for g in c.iterdir())
                        for c in p.iterdir())]

# ───────────── existing tag reader ──────────────────────────────────────────
def tags_from_track(track:Path)->Optional[Meta]:
    try:
        au = MFile(track, easy=True)
    except mutagen.MutagenError:
        return None
    if not au or "artist" not in au or "album" not in au:
        return None
    return Meta(
        author = au["artist"][0],
        title  = au["album"][0],
        year   = au.get("date",[None])[0][:4] if "date" in au else None,
        series = au.get("series",[None])[0] if "series" in au else None,
        seq    = au.get("series-part",[None])[0] if "series-part" in au else None,
        narr   = au.get("composer",[None])[0] if "composer" in au else None,
    )

# ───────────── folder-name guess (uses TAIL_RX, PAREN_RX, YEAR_RX) ───────────
def clean_tail(s:str)->str:
    return TAIL_RX.sub("", s).strip()

def guess_from_folder(leaf: Path) -> Meta:
    """
    1) Parse a leaf folder name like "5 - Jaws of Darkness (2003)" → seq=5, title, year.
    2) If its parent is "Southern Victory (1997-2007)", extract series="Southern Victory"
       and set author_dir = parent.parent.
       Otherwise, author_dir = parent.
    3) Climb from author_dir upward until we find a folder name that "looks like"
       an author (contains a space but isn't just a year).
    4) Return Meta(author, title, year, series, seq, narr=None).
    """
    # 1) Try to match "Seq - Title (Year)" exactly.
    m = LEAF_RX.match(leaf.name)
    if m:
        seq   = m.group("seq")
        title = m.group("title").strip()
        year  = m.group("year")
    else:
        # Fallback: strip common tails and try to find a year anywhere
        seq = None
        raw = PAREN_RX.sub("", clean_tail(leaf.name)).strip()
        y   = YEAR_RX.search(raw)
        year = y.group(1) if y else None
        title = raw

    # 2) Look at parent folder for a "<Series> (YYYY-YYYY)" pattern
    parent = leaf.parent
    series = None
    parent_match = PARENT_RANGE_RX.match(parent.name)
    if parent_match:
        series = parent_match.group("series").strip()
        author_dir = parent.parent
    else:
        author_dir = parent

    # 3) Climb up until we find a plausible author name (contains a space, not just a year)
    author = "Unknown Author"
    for candidate in [author_dir, *author_dir.parents]:
        name = candidate.name
        # if name has at least one space and is not exactly a 4-digit year:
        if " " in name and not YEAR_RX.fullmatch(name):
            author = name
            break

    return Meta(author=author, title=title, year=year, series=series, seq=seq)

# ───────────── online lookup (Open Library ▸ Google Books) ──────────────────
def ol_search_all(meta: Meta) -> List[Meta]:
    try:
        q = f"title:{meta.title} author:{meta.author}"
        r = requests.get(
            "https://openlibrary.org/search.json",
            params={"q": q, "limit": 5}, timeout=10,
        ).json()
        out = []
        for doc in r.get("docs", []):
            out.append(
                Meta(
                    author=", ".join(doc.get("author_name", ["Unknown"])),
                    title=doc.get("title"),
                    year=str(doc.get("first_publish_year")) if doc.get("first_publish_year") else None,
                )
            )
        return out
    except Exception:
        return []

def gb_search_all(meta: Meta) -> List[Meta]:
    try:
        q = f'intitle:"{meta.title}"+inauthor:"{meta.author}"'
        r = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": q, "maxResults": 5}, timeout=10,
        ).json()
        out = []
        for item in r.get("items", []):
            info = item["volumeInfo"]
            out.append(
                Meta(
                    author=", ".join(info.get("authors", ["Unknown"])),
                    title=info.get("title"),
                    year=info.get("publishedDate", "")[:4] or None,
                )
            )
        return out
    except Exception:
        return []

def audible_search_all(meta: Meta) -> List[Meta]:
    try:
        q = f"{meta.title} {meta.author}"
        html = requests.get(
            "https://www.audible.com/search",
            params={"keywords": q},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        ).text
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for item in soup.select("li.bc-list-item"):
            title_el = item.select_one("h3")
            author_el = item.select_one(".authorLabel a")
            year_el = item.select_one(".releaseDateLabel+span")
            if not title_el or not author_el:
                continue
            year = None
            if year_el:
                m = re.search(r"\d{4}", year_el.get_text())
                if m:
                    year = m.group(0)
            out.append(
                Meta(
                    author=author_el.get_text(strip=True),
                    title=title_el.get_text(strip=True),
                    year=year,
                )
            )
            if len(out) >= 5:
                break
        return out
    except Exception:
        return []

def _similarity(a: Meta, b: Meta) -> float:
    t1 = f"{a.author} {a.title}".lower()
    t2 = f"{b.author} {b.title}".lower()
    return SequenceMatcher(None, t1, t2).ratio()

def choose_meta(guess: Meta) -> Optional[Meta]:
    candidates = (
        ol_search_all(guess)
        + gb_search_all(guess)
        + audible_search_all(guess)
    )
    if not candidates:
        return None

    seen = set()
    unique = []
    for c in candidates:
        key = (c.author.lower(), c.title.lower())
        if key not in seen:
            unique.append(c)
            seen.add(key)
    candidates = unique

    candidates.sort(key=lambda m: _similarity(guess, m), reverse=True)

    for hit in candidates:
        score = _similarity(guess, hit)
        rprint(
            f"  guess: [italic]{guess.title}[/] by {guess.author} ({guess.year or '?'})"
        )
        rprint(
            f"  match: [bold]{hit.title}[/] by {hit.author} ({hit.year or '?'})  score: {score:.2f}"
        )
        if AUTO_YES or Confirm.ask("  use this metadata?", default=score > 0.8):
            return hit
    return None

# ───────────── FFmpeg tag writer (title / artist / year) ─────────────────────
def write_tags(track:Path, meta:Meta):
    if not WRITE_TAGS: return
    tmp = track.with_suffix(track.suffix+".tmp")
    cmd=[FFMPEG,"-nostdin","-loglevel","error","-y","-i",str(track),"-codec","copy",
         "-metadata",f"artist={meta.author}",
         "-metadata",f"album={meta.title}",
         "-metadata",f"title={track.stem}"]
    if meta.series:
        cmd += ["-metadata", f"series={meta.series}"]
    if meta.seq:
        cmd += ["-metadata", f"series-part={meta.seq}"]
    if meta.year: cmd+=["-metadata",f"date={meta.year}"]
    subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if tmp.exists(): tmp.replace(track)

# ───────────── disc-flattener ────────────────────────────────────────────────
def flatten(folder: Path, dry: bool):
    discs = []
    for p in folder.iterdir():
        if not p.is_dir():
            continue
        m = DISC_RX.search(p.name) or PART_RX.search(p.name)
        if m:
            discs.append((int(m.group("num")), p))
    discs.sort(key=lambda t: t[0])
    if not discs:
        return

    tracks = []
    single_file = True
    for num, d in discs:
        disc_tracks = sorted(t for t in d.iterdir() if t.suffix.lower() in AUDIO_EXTS)
        tracks.extend((num, t) for t in disc_tracks)
        if len(disc_tracks) != 1:
            single_file = False
    if not tracks:
        return

    rprint(f"  · flatten {len(discs)} disc dirs → {len(tracks)} tracks")
    if single_file:
        digits = len(str(len(discs)))
        for num, src in tracks:
            dest = folder / f"Part {num:0{digits}d}{src.suffix.lower()}"
            rprint(f"    {'mv' if not dry else '↪'} {src.name} → {dest.name}")
            if not dry:
                dest.parent.mkdir(exist_ok=True)
                shutil.move(src, dest)
    else:
        digits = len(str(len(tracks)))
        for i, (num, src) in enumerate(tracks, 1):
            dest = folder / f"Track {i:0{digits}d}{src.suffix.lower()}"
            rprint(f"    {'mv' if not dry else '↪'} {src.name} → {dest.name}")
            if not dry:
                dest.parent.mkdir(exist_ok=True)
                shutil.move(src, dest)

    if not dry:
        for _, d in discs:
            try:
                d.rmdir()
            except OSError:
                pass

# ───────────── track renamer ─────────────────────────────────────────────────
def rename_tracks(folder:Path):
    tracks=sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    digits=len(str(len(tracks)))
    for i,p in enumerate(tracks,1):
        new=p.with_name(f"Track {i:0{digits}d}{p.suffix.lower()}")
        if new!=p: p.rename(new)

# ───────────── build Audiobookshelf dest path ────────────────────────────────
# ───────────── updated dest_path() with truncation ────────────────────────────
# ───────────── updated dest_path() with per-component truncation ─────────────
MAX_AUTHOR_LEN = 50
MAX_SERIES_LEN = 50
MAX_TITLE_LEN  = 50
def _truncate(name: str, limit: int) -> str:
    """
    Return a slugged version of name truncated to at most `limit` characters,
    trimming any trailing dots or spaces.
    """
    slugged = slug(name)
    if len(slugged) <= limit:
        return slugged
    return slugged[:limit].rstrip(". ")

def dest_path(lib: Path, meta: Meta) -> Path:
    """
    Build the Audiobookshelf destination path, truncating each component:
      • <author>  → at most MAX_AUTHOR_LEN
      • <series>  → at most MAX_SERIES_LEN
      • <title>   → at most MAX_TITLE_LEN
    """
    # 1) Truncate author
    author_folder = _truncate(meta.author or "Unknown Author", MAX_AUTHOR_LEN)
    dest = lib / author_folder

    # 2) Truncate series, if present
    if meta.series:
        series_folder = _truncate(meta.series, MAX_SERIES_LEN)
        dest /= series_folder

    # 3) Build the “Vol … – YYYY – Title {Narrator}” bits
    bits = []
    if meta.seq:
        bits.append(f"Vol {meta.seq}")
    if meta.year:
        bits.append(meta.year)
    bits.append(meta.title)
    if meta.narr:
        bits.append(f"{{{meta.narr}}}")

    full_title = " - ".join(bits)
    title_slug = _truncate(full_title, MAX_TITLE_LEN)

    # 4) Append the truncated title slug
    dest /= title_slug
    return dest

# ───────────── process one folder ────────────────────────────────────────────
def process(folder: Path, lib: Path, dry: bool, yes: bool, summary: dict):
    summary["total"] += 1

    # 1) Gather all audio files in this folder
    audio_files = [p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTS]
    if not audio_files:
        rprint("• no audio:", folder)
        summary["skip"] += 1
        return

    # 2) Look for the first file that already has valid artist+album tags
    meta: Optional[Meta] = None
    for t in audio_files:
        existing = tags_from_track(t)
        if existing:
            meta = existing
            break

    # 3) If none of the files had tags, do the online‐lookup flow
    if not meta:
        # Guess metadata from folder name
        guess = guess_from_folder(folder)
        # Prompt the user (or auto‐yes) for a match
        hit = choose_meta(guess)
        if not hit:
            rprint("[yellow]• skip (no tags / no match):[/] ", folder.relative_to(SRC))
            summary["skip"] += 1
            return

        # Write tags to all tracks in this folder
        for t in audio_files:
            write_tags(t, hit)
        meta = hit

    # 4) At this point 'meta' is guaranteed to contain author/title, etc.
    #    We can flatten / rename / move as before.

    if FLATTEN_DISCS:
        flatten(folder, dry)
    if RENAME_TRACKS and not FLATTEN_DISCS:
        rename_tracks(folder)

    dest = dest_path(lib, meta)
    if dest.exists():
        # If the series folder exists but is empty, we can still write into it
        if dest.is_dir() and not any(dest.iterdir()):
            pass
        elif dest.is_dir():
            rprint("[cyan]• book already moved, skip:[/]", dest.relative_to(lib))
            summary["exists"] += 1
            return
        else:
            rprint("[red]✗ destination collision (file exists), skip:[/]", dest.relative_to(lib))
            summary["exists"] += 1
            return

    rprint(f"{'mv' if not dry else '↪'} {folder.relative_to(SRC)} → {dest.relative_to(lib)}")
    if not dry:
        shutil.move(str(folder), str(dest))
        summary["moved"] += 1
    else:
        summary["would_move"] += 1


# ───────────── CLI driver ────────────────────────────────────────────────────
def main(src:Path, lib:Path, commit:bool, yes:bool):
    summary=defaultdict(int)
    for leaf in leaf_dirs(src):
        process(leaf,lib,dry=not commit,yes=yes,summary=summary)
    rprint("\n[bold]summary[/]")
    for k in ("total","moved","would_move","exists","skip"):
        rprint(f"  {k:12}: {summary[k]}")

if __name__=="__main__":
    ap=argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Tag via Open Library / Google Books, flatten discs & build Audiobookshelf folders.",
        epilog=textwrap.dedent("""\
            options
            -------
              --commit    actually move / write tags (omit for preview)
              --yes       auto-accept every metadata match
            """))
    ap.add_argument("source_root", type=Path)
    ap.add_argument("library_root", type=Path)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--yes",    action="store_true")
    args=ap.parse_args()
    SRC=args.source_root.resolve(); LIB=args.library_root.resolve()
    if not SRC.is_dir(): sys.exit("source_root not found")
    LIB.mkdir(exist_ok=True, parents=True)
    AUTO_YES=args.yes
    main(SRC,LIB,args.commit,args.yes)
