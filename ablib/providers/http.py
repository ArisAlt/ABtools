"""HTTP-based metadata provider helpers (Audible, Goodreads, Google Books, Open Library)."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

_log = logging.getLogger(__name__)

# Score at which a single provider is trusted outright, short-circuiting the
# remaining lookups.
ACCEPT_SCORE = 85

from abclient import AbClient
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from ablib.core.http import SESSION


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
    except Exception as exc:
        _log.debug("openlib lookup failed: %s", exc)
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
    except Exception as exc:
        _log.debug("gbooks lookup failed: %s", exc)
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
    except Exception as exc:
        _log.debug("goodreads lookup failed: %s", exc)
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
    except Exception as exc:
        _log.debug("audible lookup failed: %s", exc)
        return None


def best_match(
    author: Optional[str],
    title: str,
    *,
    series: Optional[str] = None,
    series_index: Optional[str] = None,
    client: AbClient,
) -> tuple[Optional[tuple[int, dict]], dict[str, tuple[int, dict]]]:
    """Query multiple providers and return the best-scoring hit."""

    candidates: list[tuple[int, dict]] = []
    results: dict[str, tuple[int, dict]] = {}

    def add_result(name: str, meta: Optional[dict]) -> None:
        if not meta or not meta.get("title"):
            return
        # Copy to avoid mutating the dict returned by the provider
        meta = dict(meta)
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

    # Tier 1: Goodreads alone. A confident hit here costs a single request,
    # which keeps the common case cheap and is gentle on the scraped sites.
    if client.is_on("use_goodreads", default=True):
        add_result("goodreads", goodreads(author, title))
        best = results.get("goodreads")
        if best and best[0] >= ACCEPT_SCORE:
            return best, results

    # Tier 2: the rest concurrently. openlib/gbooks were previously never
    # consulted here at all, so a book they could have matched fell through to
    # the LLM fallback -- but adding them sequentially made a miss cost up to
    # four chained 10s lookups. Fanning out bounds a miss at roughly one
    # timeout instead of four, and matches the "parallel" fetch the README
    # already advertised. add_result runs in this thread, as as_completed
    # yields here, so `candidates`/`results` need no locking.
    remaining = {"audible": audible, "openlib": openlib, "gbooks": gbooks}
    with ThreadPoolExecutor(max_workers=len(remaining)) as pool:
        futures = {pool.submit(fn, author, title): name for name, fn in remaining.items()}
        for future in as_completed(futures):
            try:
                add_result(futures[future], future.result())
            except Exception as exc:  # provider helpers already swallow their own
                _log.debug("provider %s raised: %s", futures[future], exc)

    if not candidates:
        return None, results
    return max(candidates, key=lambda value: value[0]), results


def enrich_metadata_with_providers(
    meta: dict[str, Optional[str]]
) -> dict[str, Optional[str]]:
    """Fill missing metadata fields using provider lookups."""

    title = meta.get("title")
    if not title:
        return meta

    # Only author and year decide whether another lookup is worth making.
    # `series` used to count too, but most books simply have no series, so it
    # could never be satisfied -- every standalone book therefore ran all three
    # providers serially at 10s each, hunting a series that does not exist.
    # It is still filled opportunistically from whatever a provider returns.
    def missing_essential() -> set[str]:
        return {key for key in ("author", "year") if not (meta.get(key) or "")}

    if not missing_essential():
        return meta

    author = meta.get("author")
    for provider in (audible, openlib, gbooks):
        info = provider(author, title)
        if not info:
            continue
        if not (meta.get("author") or ""):
            authors = info.get("authors")
            if authors:
                meta["author"] = ", ".join(value for value in authors if value)
        if not (meta.get("year") or "") and info.get("year"):
            meta["year"] = info["year"]
        if not (meta.get("series") or "") and info.get("series"):
            meta["series"] = info["series"]

        if not missing_essential():
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
