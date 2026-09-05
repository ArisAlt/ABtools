"""Audio tagging utilities (Mutagen-powered)."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional

from mutagen import File as MFile
from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TRCK, TXXX
from mutagen.mp4 import MP4

from ablib.core import constants


def has_audio(folder: Path) -> bool:
    """Return True when the folder contains at least one supported audio file."""

    try:
        return any(
            child.is_file() and child.suffix.lower() in constants.AUDIO_EXTS
            for child in folder.iterdir()
        )
    except FileNotFoundError:
        return False


def strip_tags(file: Path) -> None:
    """Remove existing tags from an audio file."""

    audio = MFile(str(file))
    if audio:
        audio.delete()
        audio.save()


def write_tags(file: Path, meta: Dict[str, str], index: int = 0, total: int = 0) -> None:
    """Write audiobook tags for MP3/M4B files."""

    ext = file.suffix.lower()
    if ext == ".mp3":
        try:
            audio = ID3(str(file))
        except ID3NoHeaderError:
            audio = ID3()
        audio.clear()
        audio["TIT2"] = TIT2(3, meta["title"])
        audio["TALB"] = TALB(3, meta["title"])
        audio["TPE1"] = TPE1(3, meta["author"])
        if meta.get("year"):
            audio["TDRC"] = TDRC(3, meta["year"])
        if meta.get("series"):
            audio.add(TXXX(3, desc="series", text=meta["series"]))
        if meta.get("series_index"):
            # Without this the series position is resolved and written to
            # metadata.json/book.nfo but never embedded, so Audiobookshelf
            # cannot order a series from the audio files alone.
            audio.add(TXXX(3, desc="series-part", text=str(meta["series_index"])))
        if index:
            audio["TRCK"] = TRCK(3, f"{index}/{total or index}")
        audio.save(str(file))
    elif ext in {".m4a", ".m4b"}:
        mp4 = MP4(str(file))
        mp4.clear()
        mp4["\u00a9nam"] = meta["title"]
        mp4["\u00a9alb"] = meta["title"]
        mp4["\u00a9ART"] = meta["author"]
        if meta.get("year"):
            mp4["\u00a9day"] = meta["year"]
        if meta.get("series"):
            mp4["----:com.apple.iTunes:series"] = [meta["series"].encode("utf-8")]
        if meta.get("series_index"):
            mp4["----:com.apple.iTunes:series-part"] = [
                str(meta["series_index"]).encode("utf-8")
            ]
        if index:
            mp4["trkn"] = [(index, total or 0)]
        mp4.save()


def format_abs_metadata(meta: Dict[str, Any]) -> dict[str, Any]:
    """Format metadata dictionary according to Audiobookshelf's metadata.json schema."""
    # Authors list
    authors: list[str] = []
    if meta.get("authors"):
        if isinstance(meta["authors"], list):
            authors = [str(a).strip() for a in meta["authors"] if str(a).strip()]
        elif isinstance(meta["authors"], str) and meta["authors"].strip():
            authors = [meta["authors"].strip()]
    elif meta.get("author") and str(meta["author"]).strip():
        authors = [str(meta["author"]).strip()]

    # Narrators list
    narrators: list[str] = []
    if meta.get("narrators"):
        if isinstance(meta["narrators"], list):
            narrators = [str(n).strip() for n in meta["narrators"] if str(n).strip()]
        elif isinstance(meta["narrators"], str) and meta["narrators"].strip():
            narrators = [meta["narrators"].strip()]
    elif meta.get("narrator") and str(meta["narrator"]).strip():
        narrators = [str(meta["narrator"]).strip()]

    # Series list of dicts: [{"name": "...", "sequence": "..."}]
    series_list: list[dict[str, Optional[str]]] = []
    if meta.get("series"):
        if isinstance(meta["series"], list):
            for s in meta["series"]:
                if isinstance(s, dict):
                    name = str(s.get("name") or s.get("series") or "").strip()
                    seq = str(s.get("sequence") or s.get("series_index") or "").strip() or None
                    if name:
                        series_list.append({"name": name, "sequence": seq})
                elif isinstance(s, str) and s.strip():
                    series_list.append(
                        {
                            "name": s.strip(),
                            "sequence": str(meta.get("series_index") or "").strip() or None,
                        }
                    )
        elif isinstance(meta["series"], str) and meta["series"].strip():
            series_name = meta["series"].strip()
            series_idx = str(meta.get("series_index") or "").strip() or None
            series_list.append({"name": series_name, "sequence": series_idx})

    # 4-digit publishedYear
    year_str: Optional[str] = None
    raw_year = meta.get("publishedYear") or meta.get("year")
    if raw_year:
        m = re.search(r"\b(\d{4})\b", str(raw_year))
        if m:
            year_str = m.group(1)

    # Genres list
    genres: list[str] = []
    if meta.get("genres"):
        if isinstance(meta["genres"], list):
            genres = [str(g).strip() for g in meta["genres"] if str(g).strip()]
        elif isinstance(meta["genres"], str) and meta["genres"].strip():
            genres = [meta["genres"].strip()]
    elif meta.get("genre") and str(meta["genre"]).strip():
        genres = [str(meta["genre"]).strip()]

    title = str(meta.get("title") or "").strip()
    subtitle = str(meta["subtitle"]).strip() if meta.get("subtitle") else None
    publisher = str(meta["publisher"]).strip() if meta.get("publisher") else None
    published_date = str(meta["publishedDate"]).strip() if meta.get("publishedDate") else None
    description = str(meta["description"]).strip() if meta.get("description") else None
    isbn = str(meta["isbn"]).strip() if meta.get("isbn") else None
    asin = str(meta["asin"]).strip() if meta.get("asin") else None
    language = str(meta["language"]).strip() if meta.get("language") else None
    explicit = bool(meta.get("explicit", False))

    abs_data: dict[str, Any] = {
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "narrators": narrators,
        "series": series_list,
        "genres": genres,
        "publishedYear": year_str,
        "publishedDate": published_date,
        "publisher": publisher,
        "description": description,
        "isbn": isbn,
        "asin": asin,
        "language": language,
        "explicit": explicit,
    }

    # Backward-compatibility convenience keys for non-ABS consumers
    if authors:
        abs_data["author"] = authors[0]
    if narrators:
        abs_data["narrator"] = narrators[0]
    if year_str:
        abs_data["year"] = year_str

    return abs_data


def build_book_nfo(abs_payload: Dict[str, Any]) -> "ET.Element":
    """Build the book.nfo tree from the *same* payload metadata.json is written from.

    Previously the NFO was generated by looping over the raw `meta` dict while
    the JSON went through `format_abs_metadata()`, so the two sidecars for one
    book disagreed: `<author>`/`<series_index>` in the XML against
    `authors`/`sequence` in the JSON, plus whatever incidental keys the
    pipeline happened to be carrying (a `score`, a `confidence`). Deriving both
    from one payload makes disagreement impossible.

    Element names follow the Kodi/Emby/Jellyfin convention rather than
    Audiobookshelf's JSON keys -- that is what reads this file -- so repeated
    `<author>`/`<narrator>`/`<genre>` elements, `<year>`, and
    `<series>`/`<seriesnumber>`.
    """
    root = ET.Element("audiobook")

    def add(tag: str, value: Any) -> None:
        # str(): the payload can carry non-string values, and ElementTree
        # refuses to serialise those, failing an otherwise successful tagging
        # run at the very last step (bug.md 5.1).
        if value in (None, "", [], {}):
            return
        ET.SubElement(root, tag).text = str(value)

    add("title", abs_payload.get("title"))
    add("subtitle", abs_payload.get("subtitle"))
    for author in abs_payload.get("authors") or []:
        add("author", author)
    for narrator in abs_payload.get("narrators") or []:
        add("narrator", narrator)
    add("year", abs_payload.get("publishedYear"))
    add("releasedate", abs_payload.get("publishedDate"))
    add("publisher", abs_payload.get("publisher"))
    series_entries = abs_payload.get("series") or []
    if series_entries:
        first = series_entries[0]
        if isinstance(first, dict):
            add("series", first.get("name"))
            add("seriesnumber", first.get("sequence"))
    for genre in abs_payload.get("genres") or []:
        add("genre", genre)
    add("plot", abs_payload.get("description"))
    add("isbn", abs_payload.get("isbn"))
    add("asin", abs_payload.get("asin"))
    add("language", abs_payload.get("language"))
    return root


def export_metadata(path: Path, meta: Dict[str, Any]) -> None:
    """Persist metadata to disk for external consumers (json + nfo).

    metadata.json follows Audiobookshelf's schema; book.nfo follows the
    Kodi/Emby/Jellyfin convention. Both are built from one payload so their
    contents always agree.
    """
    target = path if path.is_dir() else path.parent
    target.mkdir(exist_ok=True)
    abs_payload = format_abs_metadata(meta)
    with (target / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(abs_payload, handle, ensure_ascii=False, indent=2)
    ET.ElementTree(build_book_nfo(abs_payload)).write(
        target / "book.nfo", encoding="utf-8", xml_declaration=True
    )


# A book folder is named after the *book*, so TALB/©alb (album = book) is the
# right source and TIT2/©nam (title = track) is the fallback. Preferring the
# track title made restructure.target_for() name folders "Rage of a Demon King
# - 01 of 14" or, worse, "01" -- and because read_tags sits at the top of that
# function's precedence chain, it overrode both the sidecar and the folder
# name. See bug.md 4.11.
TRACK_TAIL_RX = re.compile(
    r"""\s*[-–—_]?\s*
        (?:
            \d{1,3}\s*(?:of|/)\s*\d{1,3}   # "01 of 14", "3/12"
          | (?:part|pt|track|disc|disk|cd)\s*\.?\s*\d{1,3}
          | \d{1,3}
        )
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def strip_track_tail(text: Optional[str]) -> Optional[str]:
    """Drop a trailing track/part index from a title, keeping the book name.

    Only strips while at least two words survive, so a title that is genuinely
    just a number, or a short name ending in a digit, is left alone.
    """
    if not text:
        return text
    working = text.strip()
    for _ in range(2):  # "Title - 01 of 14" can leave a second bare index
        candidate = TRACK_TAIL_RX.sub("", working).strip(" -–—_.")
        if not candidate or len(candidate.split()) < 2:
            break
        if candidate == working:
            break
        working = candidate
    return working or text.strip()


def read_tags(file: Path) -> dict[str, Optional[str]]:
    """Read metadata tags (author, title, year, series, series_index) from an audio file."""
    ext = file.suffix.lower()
    res: dict[str, Optional[str]] = {
        "author": None,
        "title": None,
        "year": None,
        "series": None,
        "series_index": None,
    }
    if ext == ".mp3":
        try:
            audio = ID3(str(file))
        except (ID3NoHeaderError, Exception):
            return res
        if "TPE1" in audio and audio["TPE1"].text:
            res["author"] = str(audio["TPE1"].text[0]).strip()
        if "TALB" in audio and audio["TALB"].text:
            res["title"] = strip_track_tail(str(audio["TALB"].text[0]).strip())
        elif "TIT2" in audio and audio["TIT2"].text:
            res["title"] = strip_track_tail(str(audio["TIT2"].text[0]).strip())
        if "TDRC" in audio and audio["TDRC"].text:
            raw_year = str(audio["TDRC"].text[0])
            m = re.search(r"\b(\d{4})\b", raw_year)
            if m:
                res["year"] = m.group(1)
        for frame_id in ("TXXX:series", "TXXX:SERIES"):
            if frame_id in audio and audio[frame_id].text:
                res["series"] = str(audio[frame_id].text[0]).strip()
                break
        for part_id in ("TXXX:series-part", "TXXX:series_index", "TXXX:SERIES-PART"):
            if part_id in audio and audio[part_id].text:
                res["series_index"] = str(audio[part_id].text[0]).strip()
                break
    elif ext in {".m4a", ".m4b"}:
        try:
            mp4 = MP4(str(file))
        except Exception:
            return res
        if "\xa9ART" in mp4 and mp4["\xa9ART"]:
            res["author"] = str(mp4["\xa9ART"][0]).strip()
        if "\xa9alb" in mp4 and mp4["\xa9alb"]:
            res["title"] = strip_track_tail(str(mp4["\xa9alb"][0]).strip())
        elif "\xa9nam" in mp4 and mp4["\xa9nam"]:
            res["title"] = strip_track_tail(str(mp4["\xa9nam"][0]).strip())
        if "\xa9day" in mp4 and mp4["\xa9day"]:
            raw_year = str(mp4["\xa9day"][0])
            m = re.search(r"\b(\d{4})\b", raw_year)
            if m:
                res["year"] = m.group(1)
        if "----:com.apple.iTunes:series" in mp4 and mp4["----:com.apple.iTunes:series"]:
            val = mp4["----:com.apple.iTunes:series"][0]
            val_str = val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else str(val)
            res["series"] = val_str.strip()
        if "----:com.apple.iTunes:series-part" in mp4 and mp4["----:com.apple.iTunes:series-part"]:
            val = mp4["----:com.apple.iTunes:series-part"][0]
            val_str = val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else str(val)
            res["series_index"] = val_str.strip()
    else:
        try:
            audio = MFile(str(file), easy=True)
            if audio:
                if "artist" in audio and audio["artist"]:
                    res["author"] = str(audio["artist"][0]).strip()
                if "album" in audio and audio["album"]:
                    res["title"] = strip_track_tail(str(audio["album"][0]).strip())
                elif "title" in audio and audio["title"]:
                    res["title"] = strip_track_tail(str(audio["title"][0]).strip())
                if "date" in audio and audio["date"]:
                    m = re.search(r"\b(\d{4})\b", str(audio["date"][0]))
                    if m:
                        res["year"] = m.group(1)
                if "series" in audio and audio["series"]:
                    res["series"] = str(audio["series"][0]).strip()
                if "series-part" in audio and audio["series-part"]:
                    res["series_index"] = str(audio["series-part"][0]).strip()
        except Exception:
            pass
    return res


def read_sidecar_metadata(folder: Path) -> dict[str, Optional[str]]:
    """Read metadata from metadata.json or book.nfo if present in folder."""
    res: dict[str, Optional[str]] = {
        "author": None,
        "title": None,
        "year": None,
        "series": None,
        "series_index": None,
    }
    json_path = folder / "metadata.json"
    if json_path.is_file():
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                res["title"] = data.get("title")
                authors = data.get("authors") or data.get("author")
                if isinstance(authors, list) and authors:
                    res["author"] = str(authors[0]).strip()
                elif isinstance(authors, str) and authors:
                    res["author"] = authors.strip()

                raw_year = data.get("year") or data.get("publishedYear")
                if raw_year:
                    m = re.search(r"\b(\d{4})\b", str(raw_year))
                    if m:
                        res["year"] = m.group(1)

                series = data.get("series")
                if isinstance(series, list) and series:
                    first = series[0]
                    if isinstance(first, dict):
                        res["series"] = (first.get("name") or first.get("series") or "").strip() or None
                        res["series_index"] = str(first.get("sequence") or first.get("series_index") or "").strip() or None
                    elif isinstance(first, str) and first:
                        res["series"] = first.strip()
                elif isinstance(series, str) and series:
                    res["series"] = series.strip()

                if not res.get("series_index") and data.get("series_index"):
                    res["series_index"] = str(data["series_index"]).strip() or None

                if any(v for v in res.values()):
                    return res
        except Exception:
            pass

    nfo_path = folder / "book.nfo"
    if nfo_path.is_file():
        try:
            tree = ET.parse(str(nfo_path))
            root = tree.getroot()
            for key in ("title", "author", "year", "series", "series_index"):
                elem = root.find(key)
                if elem is not None and elem.text:
                    val = elem.text.strip()
                    if key == "year":
                        m = re.search(r"\b(\d{4})\b", val)
                        res["year"] = m.group(1) if m else None
                    else:
                        res[key] = val
        except Exception:
            pass

    return res


__all__ = [
    "has_audio",
    "strip_tags",
    "write_tags",
    "export_metadata",
    "format_abs_metadata",
    "read_tags",
    "read_sidecar_metadata",
]


def sidecar_is_current(folder: Path) -> bool:
    """True when folder's metadata.json already uses the Audiobookshelf schema.

    The marker is the `authors` array: the pre-2026-09 writer emitted a flat
    dict with a singular `author` string, `year`, and `series_index`.
    """
    json_path = folder / "metadata.json"
    if not json_path.is_file():
        return False
    try:
        with json_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and isinstance(data.get("authors"), list)


def upgrade_sidecar(folder: Path, *, force: bool = False) -> bool:
    """Rewrite a book's sidecars in the current schema. True if anything changed.

    `export_metadata` only ever writes the schema at tagging time, so a library
    tagged before the schema fix keeps its old flat `metadata.json` -- the
    organisers *move* sidecars, they never rewrite them, and Audiobookshelf
    ignores the old shape. This re-reads whatever is on disk (existing sidecar
    first, embedded tags for anything it does not cover) and writes both files
    back in the current schema.

    Returns False when the sidecar is already current (unless `force`) or when
    nothing on disk yields even a title, so a run over a large library only
    touches the folders that need it.
    """
    if not force and sidecar_is_current(folder):
        return False

    existing = read_sidecar_metadata(folder)

    audio_file = None
    for candidate in sorted(folder.iterdir()):
        if candidate.is_file() and candidate.suffix.lower() in constants.AUDIO_EXTS:
            audio_file = candidate
            break
    tags = read_tags(audio_file) if audio_file else {}

    merged = {
        key: existing.get(key) or tags.get(key)
        for key in ("author", "title", "year", "series", "series_index")
    }
    if not merged.get("title"):
        return False

    export_metadata(folder, {k: v for k, v in merged.items() if v})
    return True
