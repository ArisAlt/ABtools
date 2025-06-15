#!/usr/bin/env python3
"""
ABtools/search_and_tag.py – v2.2  (2025-06-22)
Tag (or strip) audiobook files using multiple metadata providers.

The script queries Audible, Open Library and Google Books, ranks the
results using fuzzy title matching and automatically tags files with the
best match. Low scoring hits will prompt for confirmation unless you
run with ``--yes``.

examples
--------
# preview everything
python search_and_tag.py "E:\\Audio Books" --recurse

# tag automatically
python search_and_tag.py "E:\\Audio Books" --recurse --commit --yes

# strip all tags
python search_and_tag.py "E:\\Audio Books" --recurse --striptags --commit
"""

from __future__ import annotations
import argparse, datetime, re, sys, textwrap
from pathlib import Path
from typing import Optional, Tuple, List

import requests
from rapidfuzz import fuzz
from mutagen import File as MFile, MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TALB, TPE1, TDRC, TXXX
from mutagen.mp4 import MP4, MP4StreamInfoError
from bs4 import BeautifulSoup

# ───── colour (rich) or plain text ─────
try:
    from rich import print as rprint
    from rich.prompt import Confirm
except ImportError:  # plain console, strip tags like [bold]…[/]
    _TAGS = re.compile(r"\[/?[a-zA-Z].*?]")
    def rprint(*a, **k): print(_TAGS.sub("", " ".join(map(str, a))), **k)
    def Confirm(prompt: str, default=False):
        ans = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").lower().strip()
        return default if ans == "" else ans in {"y", "yes"}

# ───── constants ─────
AUDIO_EXTS = {".mp3", ".m4a", ".m4b"}
TAIL_RX    = re.compile(r"(?:\{[^}]*\})?(?:\s*\d+\.\d{2}\.\d{2})?(?:\s*\d+\s*[kK])?\s*$")
PAREN_RX   = re.compile(r"\([^)]*\)")
YEAR_RX    = re.compile(r"^(\d{4})\s*[-_]\s*")
LOG_PATH   = Path("tag_log.txt")

# ───── logging helper ─────
def log(status: str, message: str):
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%F %T}  {status:<7}  {message}\n")

# ───── tiny helpers ─────
def clean_tail(s: str) -> str:
    return TAIL_RX.sub("", s).strip()

def has_audio(folder: Path) -> bool:
    return any(c.suffix.lower() in AUDIO_EXTS for c in folder.iterdir())

# ───── filename guess ─────
def guess_from_path(p: Path) -> Tuple[Optional[str], str, Optional[str]]:
    """Return (author, title, year).  Author may be None."""
    leaf = clean_tail(p.stem if p.is_file() else p.name)
    year = None
    if (m := YEAR_RX.match(leaf)):
        year, leaf = m.group(1), leaf[m.end():].lstrip(" -_")
    parts = [x.strip() for x in leaf.split(" - ")]
    if len(parts) == 2 and " " in parts[1]:
        title, author = parts
    else:
        title, author = leaf, None
    if not author:
        parent = clean_tail(p.parent.name)
        author = parent if " " in parent else None
    title = PAREN_RX.sub("", title).strip()
    return author, title, year

# ───── online lookup helpers ─────
def openlib(author: Optional[str], title: str) -> Optional[dict]:
    try:
        q = f"title:{title}" + (f" author:{author}" if author else "")
        r = requests.get("https://openlibrary.org/search.json",
                         params={"q": q, "limit": 5}, timeout=10)
        r.raise_for_status()
        docs = r.json().get("docs", [])
        best = max(docs, key=lambda d: fuzz.token_set_ratio(
                   title, d.get("title", "")), default=None)
        if not best: return None
        return {
            "title":   best.get("title"),
            "authors": best.get("author_name", []),
            "year":    str(best.get("first_publish_year")) if best.get("first_publish_year") else None
        }
    except Exception:
        return None

def gbooks(author: Optional[str], title: str) -> Optional[dict]:
    try:
        q = f'intitle:"{title}"' + (f'+inauthor:"{author}"' if author else "")
        r = requests.get("https://www.googleapis.com/books/v1/volumes",
                         params={"q": q, "maxResults": 5}, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        info = max(items, key=lambda i: fuzz.token_set_ratio(
                   title, i["volumeInfo"].get("title", "")), default=None)
        if not info: return None
        info = info["volumeInfo"]
        return {
            "title":   info.get("title"),
            "authors": info.get("authors", []),
            "year":    info.get("publishedDate", "")[:4] or None
        }
    except Exception:
        return None

def audible(author: Optional[str], title: str) -> Optional[dict]:
    try:
        q = f"{title} {author}" if author else title
        html = requests.get(
            "https://www.audible.com/search",
            params={"keywords": q},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        ).text
        soup = BeautifulSoup(html, "html.parser")
        item = soup.select_one("li.bc-list-item.productListItem")
        if not item:
            return None
        title_el = item.select_one("h3")
        author_el = item.select_one(".authorLabel a")
        series_el = item.select_one(".seriesLabel a")
        year_el = item.select_one(".releaseDateLabel+span")
        if not title_el or not author_el:
            return None
        year = None
        if year_el:
            m = re.search(r"\d{4}", year_el.get_text())
            if m:
                year = m.group(0)
        return {
            "title": title_el.get_text(strip=True),
            "authors": [author_el.get_text(strip=True)],
            "year": year,
            "series": series_el.get_text(strip=True) if series_el else None,
        }
    except Exception:
        return None

def best_match(author: Optional[str], title: str) -> Optional[tuple[int, dict]]:
    """Query all providers and return (score, metadata) for the best hit."""
    candidates = []
    for provider in (audible, openlib, gbooks):
        meta = provider(author, title)
        if meta and meta.get("title"):
            score = fuzz.token_set_ratio(title.lower(), meta["title"].lower())
            meta["source"] = provider.__name__
            candidates.append((score, meta))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])

# ───── tag / strip functions ─────
def strip_tags(file: Path):
    audio = MFile(file)
    if audio:
        audio.delete(); audio.save()

def write_tags(file: Path, meta: dict):
    ext = file.suffix.lower()
    if ext == ".mp3":
        try:
            audio = ID3(file)
        except ID3NoHeaderError:
            audio = ID3()
        audio.clear()
        audio["TIT2"] = TIT2(3, meta["title"])
        audio["TALB"] = TALB(3, meta["title"])
        audio["TPE1"] = TPE1(3, meta["author"])
        if meta["year"]:
            audio["TDRC"] = TDRC(3, meta["year"])
        if meta.get("series"):
            audio.add(TXXX(3, desc="series", text=meta["series"]))
        audio.save(file)
    elif ext in {".m4a", ".m4b"}:
        mp4 = MP4(file)
        mp4.clear()
        mp4["©nam"] = meta["title"]
        mp4["©alb"] = meta["title"]
        mp4["©ART"] = meta["author"]
        if meta["year"]:
            mp4["©day"] = meta["year"]
        if meta.get("series"):
            mp4["----:com.apple.iTunes:series"] = [meta["series"]]
        mp4.save()

# ───── process one leaf ─────
def process_leaf(path: Path, args):
    # skip Unknown Author
    if path.name == "Unknown Author" or path.parent.name == "Unknown Author":
        rprint("• skip Unknown Author:", path)
        log("SKIP", str(path)); return

    # strip mode
    if args.striptags:
        targets = [path] if path.is_file() else [f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXTS]
        ok = 0
        for f in targets:
            try:
                strip_tags(f); ok += 1
            except MutagenError:
                log("ERR", f"strip {f}")
        rprint(f"[cyan]→[/] {path}  [green]tags stripped ({ok}/{len(targets)})[/]")
        log("STRIP", f"{path}  ({ok}/{len(targets)})")
        return

    # guess
    a_guess, t_guess, y_guess = guess_from_path(path)
    rprint(f"[cyan]→[/] {path}")
    rprint(f"  guess: [italic]{t_guess}[/] by {a_guess or '?'} ({y_guess or '?'})")

    result = best_match(a_guess, t_guess)
    if not result:
        rprint("  [red] • no match[/]")
        log("NOMATCH", str(path)); return
    score, hit = result

    author_hit = ", ".join(hit["authors"]) or a_guess or "Unknown"
    rprint(f"  match: [bold]{hit['title']}[/] by {author_hit} ({hit['year'] or '?'})")
    if hit.get("series"):
        rprint(f"  series: {hit['series']}")
    rprint(f"  provider: {hit['source']}")

    if score < 60:
        rprint("  [yellow]⚠ low confidence – double-check[/]")
    if score < 70 and not args.yes:
        if hasattr(Confirm, "ask"):
            proceed = Confirm.ask("  tag with this metadata?")
        else:
            proceed = Confirm("tag with this metadata?")
        if not proceed:
            log("SKIP", str(path))
            return

    meta = {
        "title": hit["title"],
        "author": author_hit,
        "year": hit["year"],
        "series": hit.get("series"),
    }
    targets = [path] if path.is_file() else [f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXTS]
    ok = 0
    for f in targets:
        try:
            write_tags(f, meta); ok += 1
        except (MutagenError, MP4StreamInfoError):
            log("ERR", f"tag {f}")
    label = "OK" if ok == len(targets) else "ERR"
    rprint(f"  [green]tagged {ok}/{len(targets)} file(s)[/]")
    log(label, f"{path}  ({ok}/{len(targets)})")

# ───── leaf finder ─────
def walk_leaves(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    leaves: List[Path] = []
    for p in root.rglob("*"):
        if p.is_dir() and has_audio(p) and not any(
            c.is_dir() and has_audio(c) for c in p.iterdir()):
            leaves.append(p)
    return leaves

# ───── cli / main ─────
def main():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Tag or strip audiobook files.",
        epilog=textwrap.dedent("""\
            flags
            -----
              --recurse     walk sub-folders that hold audio
              --commit      actually write changes
              --yes         auto-accept matches (tag mode)
              --striptags   delete *all* tags instead of adding
            """))
    ap.add_argument("root", type=Path, help="file or folder")
    ap.add_argument("--recurse",   action="store_true")
    ap.add_argument("--commit",    action="store_true")
    ap.add_argument("--yes",       action="store_true")
    ap.add_argument("--striptags", action="store_true")
    args = ap.parse_args()

    if not args.root.exists():
        sys.exit("path not found")

    items = walk_leaves(args.root) if args.recurse else [args.root]
    for leaf in items:
        try:
            if not args.commit:
                rprint(f"[dim]preview:[/] {leaf}")
                continue
            process_leaf(leaf, args)
        except Exception as e:
            rprint(f"[red]ERR:[/] {leaf} – {e}")
            log("ERR", f"{leaf} – {type(e).__name__}")

if __name__ == "__main__":
    main()
