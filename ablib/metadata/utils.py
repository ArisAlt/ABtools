"""Utility helpers for parsing and validating audiobook metadata."""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any, Optional

from ..core import constants


def clean_tail(text: str) -> str:
    """Remove bitrate and brace annotations often appended to folder names."""

    return constants.TAIL_RX.sub("", text or "").strip()


def strip_annotations(text: str) -> str:
    """Remove parenthetical annotations to improve fuzzy matching."""

    if not text:
        return ""
    cleaned = constants.PAREN_RX.sub("", text)
    cleaned = re.sub(r"\[[^]]*\]", "", cleaned)
    cleaned = re.sub(r"\{[^}]*\}", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -_\t")


def extract_series_and_title(text: str) -> tuple[Optional[str], Optional[str], str]:
    """Split a raw string into optional series metadata and cleaned title."""

    working = text.strip()
    if not working:
        return None, None, ""

    for pattern in constants.SERIES_PATTERNS:
        match = pattern.match(working)
        if not match:
            continue
        groups = match.groups()
        if len(groups) == 3:
            series_name, series_index, title = groups
            cleaned_series = series_name.strip(" -_:. ,\t")
            cleaned_title = title.strip(" -_:. \t")
            return cleaned_series, series_index.strip(), cleaned_title
        if len(groups) == 2:
            series_index, title = groups
            cleaned_title = title.strip(" -_:. \t")
            return None, series_index.strip(), cleaned_title

    return None, None, working


def guess_from_path(
    path: Path,
) -> tuple[Optional[str], str, Optional[str], Optional[str], Optional[str]]:
    """Derive author and title hints from the folder structure."""

    leaf = clean_tail(path.stem if path.is_file() else path.name)
    year: Optional[str] = None
    series: Optional[str] = None
    series_index: Optional[str] = None

    match = constants.YEAR_RX.match(leaf)
    if match:
        year = match.group(1)
        leaf = leaf[match.end() :].lstrip(" -_")

    parts = [segment.strip() for segment in leaf.split(" - ")]

    if parts and re.fullmatch(r"\d+", parts[0]):
        parts = parts[1:]

    if parts and re.fullmatch(r"\d{4}", parts[-1]) and year is None:
        year = parts.pop()

    author: Optional[str] = None
    if not parts:
        title = leaf
    elif len(parts) >= 2:
        # The last segment is the title. Everything before it is author and/or
        # series, and is only ever mined for series metadata -- previously a
        # series pattern matching inside `combined` overwrote `title` with a
        # fragment of the author text, silently discarding the real title.
        combined = " - ".join(parts[:-1])
        series, series_index, _ = extract_series_and_title(combined)
        title = parts[-1]
        if not series:
            author_candidate = strip_annotations(combined.strip())
            if (
                author_candidate
                and not any(ch.isdigit() for ch in author_candidate)
                and sum(ch.isalpha() for ch in author_candidate) >= 2
            ):
                author = author_candidate
    else:
        series, series_index, title = extract_series_and_title(parts[0])

    if not author:
        parent = strip_annotations(clean_tail(path.parent.name))
        author = parent if " " in parent else None

    title = strip_annotations(title)
    return author, title, year, series, series_index


def determine_best_author(
    folder: Path, initial_guess: Optional[str], partial_meta: Optional[dict] = None
) -> Optional[str]:
    """Select the most plausible author string from folder hints."""

    if partial_meta and partial_meta.get("author"):
        return partial_meta["author"]

    if initial_guess:
        cleaned_guess = strip_annotations(initial_guess)
        if len(cleaned_guess.split()) >= 2:
            return cleaned_guess

    parent_name = strip_annotations(clean_tail(folder.parent.name))
    if parent_name and len(parent_name.split()) >= 2 and parent_name != "Unknown Author":
        return parent_name

    if folder.parent.parent != folder.parent:
        grandparent = strip_annotations(clean_tail(folder.parent.parent.name))
        if grandparent and len(grandparent.split()) >= 2:
            return grandparent

    return None


def enhanced_author_extraction(folder: Path) -> Optional[str]:
    """Probe folder context to infer likely author names."""

    parts = folder.parts
    for idx, part in enumerate(parts):
        cleaned = strip_annotations(clean_tail(part))
        if cleaned.lower() in {"audiobooks", "books", "library", "media"}:
            continue
        if len(cleaned.split()) >= 2 and not re.match(r"^\d{4}", cleaned):
            if idx + 1 < len(parts):
                next_part = clean_tail(parts[idx + 1])
                if not re.match(r"^\d{4}", next_part):
                    return cleaned
    return None


def derive_label_hints(label: str) -> dict[str, Optional[str]]:
    """Extract best-effort hints from a folder label."""

    raw = (label or "").strip()
    if not raw:
        return {
            "title": None,
            "author": None,
            "year": None,
            "series": None,
            "series_index": None,
        }

    cleaned = strip_annotations(clean_tail(raw))
    cleaned = constants.TAIL_RX.sub("", cleaned).strip()
    year = None
    match = constants.YEAR_RX.match(cleaned)
    if match:
        year = match.group(1)
        cleaned = cleaned[match.end() :].lstrip(" -_")

    author_hint: Optional[str] = None
    # Split only on a dash used as a *delimiter*, i.e. surrounded by whitespace.
    # The previous class `[--]` was the range '-' to '-' (a plain hyphen) with
    # optional surrounding space, so it also split inside hyphenated names:
    # "Spider-Man - Stan Lee" -> ["Spider", "Man", "Stan Lee"].
    parts = [part.strip() for part in re.split(r"\s+[-–—]\s+", cleaned) if part.strip()]
    title_part = cleaned
    if parts:
        possible_author = parts[0]
        if len(parts) > 1 and " " in possible_author and not possible_author.isdigit():
            author_hint = possible_author
            title_part = " - ".join(parts[1:]).strip()
    title_part = strip_annotations(title_part)
    series_hint, series_index_hint, title_hint = extract_series_and_title(title_part)
    title_hint = strip_annotations(title_hint or title_part) or None

    return {
        "title": title_hint,
        "author": author_hint,
        "year": year,
        "series": series_hint,
        "series_index": series_index_hint,
        "raw": raw,
        "normalized": cleaned,
    }


def format_metadata_summary(meta: dict[str, Any]) -> str:
    """Summarise metadata for logging."""

    fields = {
        "title": meta.get("title") or "?",
        "author": meta.get("author") or "?",
        "year": meta.get("year") or "?",
        "series": meta.get("series") or "",
        "series_index": meta.get("series_index") or "",
        "source": meta.get("source") or "?",
    }
    summary = f"title={fields['title']} | author={fields['author']} | year={fields['year']}"
    if fields["series"]:
        series_idx = fields["series_index"] or "?"
        summary += f" | series={fields['series']} #{series_idx}"
    summary += f" | source={fields['source']}"

    for key in ("narrator", "description", "score"):
        value = str(meta.get(key) or "").strip()
        if not value:
            continue
        if key == "description" and len(value) > 60:
            value = value[:57].rstrip() + "..."
        summary += f" | {key}={value}"

    return summary


# Only these make metadata unusable. Everything else this function reports is
# advisory: a short description or an empty narrator says nothing about whether
# the book can be filed correctly. Treating every issue as fatal meant
# process_leaf refused to tag a book with a perfect title and author because
# its description ran to seven characters.
FATAL_VALIDATION_ISSUES = frozenset({"missing_title", "missing_author"})


def validate_metadata_fields(meta: dict[str, Any]) -> tuple[bool, list[str]]:
    """Run lightweight validation over metadata dicts.

    Returns ``(usable, issues)``. ``usable`` is False only for the issues in
    :data:`FATAL_VALIDATION_ISSUES`; ``issues`` still lists everything found so
    callers can report the advisory ones.
    """

    issues: list[str] = []

    title = (meta.get("title") or "").strip() if meta.get("title") else ""
    author = (meta.get("author") or "").strip() if meta.get("author") else ""
    year = (meta.get("year") or "").strip() if meta.get("year") else ""
    narrator = meta.get("narrator")
    description = meta.get("description")
    series = (meta.get("series") or "").strip() if meta.get("series") else ""
    series_index = meta.get("series_index")

    if not title:
        issues.append("missing_title")
    if not author:
        issues.append("missing_author")

    if year:
        if not re.fullmatch(r"\d{4}", year):
            issues.append("invalid_year_format")
        else:
            current_year = datetime.datetime.now().year
            year_int = int(year)
            if year_int < 1800 or year_int > current_year + 1:
                issues.append("implausible_year")

    if narrator is not None:
        narrator_str = str(narrator).strip() if narrator is not None else ""
        if not narrator_str:
            issues.append("empty_narrator")

    if series_index:
        series_index_str = str(series_index).strip()
        if not re.fullmatch(r"\d+(?:\.\d+)?", series_index_str):
            issues.append("invalid_series_index")
        if not series:
            issues.append("series_index_without_series")

    if description is not None:
        description_text = str(description).strip()
        if description_text and len(description_text) < 15:
            issues.append("short_description")

    return not (set(issues) & FATAL_VALIDATION_ISSUES), issues


def slug(text: str) -> str:
    """Return a filesystem-friendly string with illegal characters removed."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", text or "")
    return cleaned.strip().rstrip(". ")


def truncate_component(name: str, limit: int) -> str:
    """Return a slugged version of name truncated to at most `limit` characters,
    trimming any trailing dots or spaces."""
    slugged = slug(name)
    if len(slugged) <= limit:
        return slugged
    return slugged[:limit].rstrip(". ")


def format_canonical_dest(
    dest_root: Path,
    author: Optional[str] = None,
    title: Optional[str] = None,
    year: Optional[str] = None,
    series: Optional[str] = None,
    *,
    max_author: int = 50,
    max_series: int = 50,
    max_title: int = 50,
) -> Path:
    """Build the canonical Audiobookshelf destination path:

        <dest_root>/<author>/[series]/<title (year)>

    Truncates each component per Audiobookshelf best practices:
      • <author>  → at most max_author (default 50)
      • <series>  → at most max_series (default 50)
      • <title>   → at most max_title (default 50), preserving year suffix
    When year is missing, empty, or 'Unknown', the year suffix is omitted.
    """
    author_folder = truncate_component(author or "Unknown Author", max_author)
    dest = dest_root / author_folder

    if series and series.strip() and series.strip().lower() not in {"unknown", "none", "null"}:
        series_folder = truncate_component(series.strip(), max_series)
        if series_folder:
            dest /= series_folder

    title_text = (title or "").strip() or "Unknown Title"
    clean_year = (year or "").strip()
    year_suffix = f" ({clean_year})" if clean_year and clean_year.lower() != "unknown" else ""

    available_len = max(1, max_title - len(year_suffix))
    title_slug = truncate_component(title_text, available_len) + year_suffix
    dest /= title_slug

    return dest


# ── author sanity ───────────────────────────────────────────────────────────
# Shared by combobook.process() and restructure.target_for() so the two
# organisers agree on what counts as an author. See bug.md 4.8 / 4.10: a rip's
# `artist` frame routinely holds a disc marker, a track index, or the filename,
# and trusting it verbatim turns that string into a top-level library folder.

JUNK_AUTHOR_RX = re.compile(
    r"""^\s*
        (?:\[|\(|\{)?\s*
        (?:side|disc|disk|cd|dvd|part|pt|track|tape|chapter|ch|file|vol|volume)
        \s*[\s._#-]*\d+
        (?:\s*(?:of|/)\s*\d+)?
        \s*(?:\]|\)|\})?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)
INDEX_ONLY_RX = re.compile(r"^\s*\d+\s*(?:(?:of|/)\s*\d+)?\s*$")
UNKNOWN_AUTHORS = frozenset(
    {"", "unknown", "unknown author", "various", "various artists", "va", "none", "null", "n/a"}
)
INITIAL_RX = re.compile(r"\b([A-Z])(?=\s|$)")


def _comparable(text: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace, for equality tests."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def is_plausible_author(name: Optional[str], *, filename_stem: Optional[str] = None) -> bool:
    """True when `name` could actually be a person, rather than rip debris.

    Rejects disc/track markers ("Side 01", "CD 2"), bare indices ("01",
    "3 of 12"), placeholder values, strings with no letters, and — when
    `filename_stem` is given — a value that merely echoes the audio file's own
    name ("AttheGatesofDarkness Part1 Track 01"), which is what a tagger writes
    when it had nothing better to put in the field.
    """
    if not name:
        return False
    candidate = name.strip()
    if candidate.lower() in UNKNOWN_AUTHORS:
        return False
    if JUNK_AUTHOR_RX.match(candidate) or INDEX_ONLY_RX.match(candidate):
        return False
    if not re.search(r"[A-Za-z]", candidate):
        return False
    # "Track 04" anywhere, not just anchored, is never part of a real name.
    if re.search(r"\b(?:track|disc|disk|side|cd)\s*\d+\b", candidate, re.IGNORECASE):
        return False
    if filename_stem and _comparable(candidate) == _comparable(filename_stem):
        return False
    return True


def normalise_author(name: Optional[str]) -> Optional[str]:
    """Canonicalise an author string so one person yields one library folder.

    Restores the period after a bare middle initial, so "Raymond E Feist" and
    "Raymond E. Feist" stop producing two sibling directories, and collapses
    runs of whitespace.
    """
    if not name:
        return None
    cleaned = re.sub(r"\s{2,}", " ", name.strip())
    if not cleaned:
        return None
    return INITIAL_RX.sub(r"\1.", cleaned)


def primary_author(name: Optional[str]) -> Optional[str]:
    """Reduce a comma-joined credit list to a single filing name.

    A compilation can carry a dozen names; at 126 characters `truncate_component`
    cuts it mid-word into a pseudo-author no library will ever match. Filing
    under the first credited author is wrong for exactly one book but readable,
    reversible, and consistent between the two organisers. Two names are kept
    as-is: co-authorship is a real, stable credit.
    """
    normalised = normalise_author(name)
    if not normalised:
        return None
    parts = [p.strip() for p in normalised.split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[0]
    return normalised


# ── self-describing folder names ────────────────────────────────────────────
# Shared by combobook.parse_leaf_name() and restructure.parse_book_folder() so
# both organisers read the same shapes out of a leaf directory name.

BOOK_MARKER_RX = re.compile(
    r"^(?:book|bk|vol|volume|part|pt|#)\s*\.?\s*(?P<seq>\d+(?:\.\d+)?)"
    r"(?P<omnibus>\s*(?:&|\+|and|-|to)\s*\d+)?$",
    re.IGNORECASE,
)
DASH_SPLIT_RX = re.compile(r"\s+[-–—]\s+")
TRAILING_YEAR_RX = re.compile(r"\((\d{4})\)\s*$")


def parse_book_folder_name(name: str) -> dict[str, Optional[str]]:
    """Read author / series / sequence / title / year out of a folder name.

    Recognises "<Author> - <Series> - Book <N> - <Title>" and its shorter
    relatives, then falls back to `extract_series_and_title` for
    "<Series> <NN> - <Title>". Returns a dict whose values are None when the
    name carries no evidence for that field -- never a guess.

    An omnibus ("Book 1 & 2") keeps the first sequence number; there is no
    single correct answer, and the first is what a library sorts by.
    """
    result: dict[str, Optional[str]] = {
        "author": None, "series": None, "series_index": None,
        "title": None, "year": None,
    }
    working = clean_tail(name or "").strip()
    if not working:
        return result

    year_match = TRAILING_YEAR_RX.search(working)
    if year_match:
        result["year"] = year_match.group(1)
        working = working[: year_match.start()].strip()

    segments = [s.strip() for s in DASH_SPLIT_RX.split(working) if s.strip()]
    marker_at = next(
        (i for i, seg in enumerate(segments) if BOOK_MARKER_RX.match(seg)), None
    )
    if marker_at is not None and marker_at < len(segments) - 1:
        marker = BOOK_MARKER_RX.match(segments[marker_at])
        result["series_index"] = marker.group("seq")
        result["title"] = " - ".join(segments[marker_at + 1 :]).strip()
        head = segments[:marker_at]
        if len(head) >= 2:
            result["author"] = normalise_author(head[0])
            result["series"] = " - ".join(head[1:]).strip() or None
        elif len(head) == 1:
            # "<Series> - Book N - <Title>" carries no author. Reading the lone
            # segment as the series is the safer error: a wrong series is a
            # subfolder, a wrong author is a top-level library directory.
            result["series"] = head[0]
        return result

    series, index, title = extract_series_and_title(working)
    if series and " - " in series:
        # extract_series_and_title keeps any author prefix glued to the series.
        author_part, _, series_part = series.partition(" - ")
        result["author"] = normalise_author(author_part)
        result["series"] = series_part.strip() or None
    else:
        result["series"] = series
    result["series_index"] = index
    result["title"] = title or working
    return result
