"""HTTP-based metadata provider helpers (Audible, Goodreads, Google Books, Open Library)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from abclient import AbClient
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from abtools.core.http import SESSION


def openlib(author: Optional[str], title: str) -> Optional[dict]:
    try:
        query = f"title:{title}" + (f" author:{author}" if author else "")
        response = SESSION.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": 5},
            timeout=10,
        )
        response.raise_for_status()
        docs = response.json().get("docs", [])
        best = max(
            docs,
            key=lambda doc: fuzz.token_set_ratio(title, doc.get("title", "")),
            default=None,
        )
        if not best:
            return None
        return {
            "title": best.get("title"),
            "authors": best.get("author_name", []),
            "year": (
                str(best.get("first_publish_year"))
                if best.get("first_publish_year")
                else None
            ),
        }
    except Exception:
        return None


def gbooks(author: Optional[str], title: str) -> Optional[dict]:
    try:
        query = f'intitle:"{title}"' + (f'+inauthor:"{author}"' if author else "")
        response = SESSION.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": 5},
            timeout=10,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        info = max(
            items,
            key=lambda item: fuzz.token_set_ratio(
                title, item["volumeInfo"].get("title", "")
            ),
            default=None,
        )
        if not info:
            return None
        volume = info["volumeInfo"]
        return {
            "title": volume.get("title"),
            "authors": volume.get("authors", []),
            "year": volume.get("publishedDate", "")[:4] or None,
        }
    except Exception:
        return None


def goodreads(author: Optional[str], title: str) -> Optional[dict]:
    try:
        query = f"{title} {author}" if author else title
        html = SESSION.get(
            "https://www.goodreads.com/search", params={"q": query}, timeout=10
        ).text
        soup = BeautifulSoup(html, "html.parser")
        row = soup.select_one("table.tableList tr")
        if not row:
            return None
        title_el = row.select_one("a.bookTitle span")
        author_el = row.select_one("a.authorName span")
        year_el = row.select_one("span.minirating")
        if not title_el or not author_el:
            return None
        year = None
        if year_el:
            match = re.search(r"(\d{4})", year_el.get_text())
            if match:
                year = match.group(1)
        return {
            "title": title_el.get_text(strip=True),
            "authors": [author_el.get_text(strip=True)],
            "year": year,
        }
    except Exception:
        return None


def audible(author: Optional[str], title: str) -> Optional[dict]:
    try:
        query = f"{title} {author}" if author else title
        html = SESSION.get(
            "https://www.audible.com/search",
            params={"keywords": query},
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
            match = re.search(r"\d{4}", year_el.get_text())
            if match:
                year = match.group(0)
        return {
            "title": title_el.get_text(strip=True),
            "authors": [author_el.get_text(strip=True)],
            "year": year,
            "series": series_el.get_text(strip=True) if series_el else None,
        }
    except Exception:
        return None


def best_match(
    author: Optional[str],
    title: str,
    *,
    series: Optional[str] = None,
    series_index: Optional[str] = None,
    client: AbClient,
) -> Tuple[Optional[Tuple[int, dict]], Dict[str, Tuple[int, dict]]]:
    """Query multiple providers and return the best-scoring hit."""

    candidates: List[Tuple[int, dict]] = []
    results: Dict[str, Tuple[int, dict]] = {}

    def add_result(name: str, meta: Optional[dict]) -> None:
        if not meta or not meta.get("title"):
            return
        title_score = fuzz.token_set_ratio(title.lower(), meta["title"].lower())
        author_score = 0
        if author and meta.get("authors"):
            author_score = max(
                fuzz.token_set_ratio(author.lower(), candidate.lower())
                for candidate in meta["authors"]
            )
        series_score = 0
        if series and meta.get("series"):
            series_score = fuzz.token_set_ratio(series.lower(), meta["series"].lower())
        if series:
            score = int(title_score * 0.5 + author_score * 0.25 + series_score * 0.25)
        else:
            score = int(title_score * 0.7 + author_score * 0.3)
        meta["source"] = name
        pair = (score, meta)
        candidates.append(pair)
        results[name] = pair

    if client.is_on("use_goodreads", default=True):
        add_result("goodreads", goodreads(author, title))
        best = results.get("goodreads")
        if best and best[0] >= 85:
            return best, results

    add_result("audible", audible(author, title))

    if not candidates:
        return None, results
    return max(candidates, key=lambda value: value[0]), results


def enrich_metadata_with_providers(
    meta: Dict[str, Optional[str]]
) -> Dict[str, Optional[str]]:
    """Fill missing metadata fields using provider lookups."""

    title = meta.get("title")
    if not title:
        return meta

    needed = {key for key in ("author", "year", "series") if not (meta.get(key) or "")}
    if not needed:
        return meta

    author = meta.get("author")
    providers = (audible, openlib, gbooks)
    for provider in providers:
        info = provider(author, title)
        if not info:
            continue
        if "author" in needed:
            authors = info.get("authors")
            if authors:
                meta["author"] = ", ".join(value for value in authors if value)
        if "year" in needed and info.get("year"):
            meta["year"] = info["year"]
        if "series" in needed and info.get("series"):
            meta["series"] = info["series"]

        needed = {key for key in ("author", "year", "series") if not (meta.get(key) or "")}
        if not needed:
            break
        author = meta.get("author")

    return meta


__all__ = [
    "audible",
    "best_match",
    "enrich_metadata_with_providers",
    "gbooks",
    "goodreads",
    "openlib",
]
