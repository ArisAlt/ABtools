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
            return series_name.strip(), series_index.strip(), title.strip()
        if len(groups) == 2:
            series_index, title = groups
            return None, series_index.strip(), title.strip()

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
    if parts:
        combined = " - ".join(parts[:-1]) if len(parts) >= 2 else parts[0]
        series, series_index, title = extract_series_and_title(combined)
        if not series and len(parts) >= 2:
            author_candidate = strip_annotations(" - ".join(parts[:-1]).strip())
            title = parts[-1]
            if (
                author_candidate
                and not any(ch.isdigit() for ch in author_candidate)
                and sum(ch.isalpha() for ch in author_candidate) >= 2
            ):
                author = author_candidate
            else:
                author = None
        else:
            author = None
    else:
        title = leaf
        author = None

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
    parts = [part.strip() for part in re.split(r"\s*[--]\s*", cleaned) if part.strip()]
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


def validate_metadata_fields(meta: dict[str, Any]) -> tuple[bool, list[str]]:
    """Run lightweight validation over metadata dicts."""

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

    return (len(issues) == 0), issues
