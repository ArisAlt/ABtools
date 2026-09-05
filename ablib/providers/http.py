"""HTTP-based metadata provider helpers (Audible, Goodreads, Google Books, Open Library)."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

_log = logging.getLogger(__name__)

# Score at which a single provider is trusted outright, short-circuiting the
# remaining lookups. See constants.DEFAULT_MATCH_THRESHOLD for the measured
# bands this sits between.
from ablib.core.constants import DEFAULT_MATCH_THRESHOLD

ACCEPT_SCORE = DEFAULT_MATCH_THRESHOLD

from abclient import AbClient
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from ablib.core.http import SESSION


# ── query hygiene ───────────────────────────────────────────────────────────
# Folder names carry rip debris that no catalogue will ever match:
# "Daughter of the Empire 128kbps" returned nothing at all, and
# "Magicians End (Unabridged)" scored 45. Stripping it before the query is the
# cheapest accuracy win available, and every hit here is a book that does not
# have to go to the LLM.

_NOISE_PATTERNS = (
    r"\((?:un)?abridged\)", r"\[(?:un)?abridged\]",
    r"\b(?:un)?abridged\b",
    r"\[[^\]]*audio ?book[^\]]*\]", r"\((?:[^)]*audio ?book[^)]*)\)",
    r"\baudio ?book\b",
    r"\b\d{2,3}\s?kbps\b", r"\b\d{2,3}k\b",
    r"\b(?:mp3|m4b|m4a|flac|aac|ogg)\b",
    r"\b\d{1,3}\s*(?:of|/)\s*\d{1,3}\b",
    r"\b(?:cd|disc|disk|part|pt|track|tape|side)\s*\.?\s*\d{1,3}\b",
    r"\{[^}]*\}", r"\[[^\]]*\]",
    r"\(\s*\d{4}\s*\)",
    r"\b(?:complete|full)\s+audiobook\b",
)
NOISE_RX = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

# Goodreads titles carry the series inline: "Silverthorn (The Riftwar Saga, #3)".
# That is precisely the series level the library layout needs, and it used to be
# thrown away with the rest of the parenthetical.
SERIES_SUFFIX_RX = re.compile(
    r"""^(?P<title>.+?)\s*\(\s*
        (?P<series>[^,()]+?)
        (?:\s+series)?
        \s*(?:,\s*|\s+)
        (?:\#|book\s+|vol\.?\s*|volume\s+|part\s+)
        (?P<index>\d+(?:\.\d+)?|[a-z]+)
        \s*\)\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

# Catalogues spell the sequence out as often as they number it:
# "Hitler's War (the War That Came Early, Book One)".
WORD_NUMBERS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20",
}


def clean_query_title(title: Optional[str]) -> str:
    """Strip rip debris from a title before it is sent to a catalogue."""
    if not title:
        return ""
    cleaned = NOISE_RX.sub(" ", title)
    # An unclosed parenthetical is a typo, not a subtitle: "West and East
    # (20109" matched an unrelated book by an unrelated author.
    if cleaned.count("(") > cleaned.count(")"):
        cleaned = re.sub(r"\s*\([^)]*$", "", cleaned)
    if cleaned.count("[") > cleaned.count("]"):
        cleaned = re.sub(r"\s*\[[^\]]*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -_:.,")


def split_series_suffix(title: Optional[str]) -> tuple[str, Optional[str], Optional[str]]:
    """"Silverthorn (The Riftwar Saga, #3)" -> ("Silverthorn", "The Riftwar Saga", "3")."""
    if not title:
        return "", None, None
    match = SERIES_SUFFIX_RX.match(title.strip())
    if not match:
        return title.strip(), None, None
    index = match.group("index").strip()
    if not index.isdigit():
        index = WORD_NUMBERS.get(index.lower(), "")
        if not index:
            return title.strip(), None, None   # "(Radio Play)", not a sequence
    return (
        match.group("title").strip(),
        match.group("series").strip() or None,
        index or None,
    )


BY_AUTHOR_TAIL_RX = re.compile(r"\s+by\s+(?P<who>.+)$", re.IGNORECASE)
EDITION_DATE_RX = re.compile(r"\s*\(\s*\d{4}-\d{2}-\d{2}\s*\)\s*$")


def strip_edition_tail(title: str, authors: Optional[list]) -> str:
    """Drop a "by <Author> (1996-12-05)" tail some catalogue editions carry.

    Goodreads returns e.g. "Worldwar: Striking the Balance by Harry Turtledove
    (1996-12-05)" for reissues. Left alone that whole string becomes the book's
    folder name. The "by ..." part is only removed when it actually names one
    of the authors the same result reported, so a title that genuinely contains
    the word "by" survives.
    """
    cleaned = EDITION_DATE_RX.sub("", title).strip()
    match = BY_AUTHOR_TAIL_RX.search(cleaned)
    if not match or not authors:
        return cleaned
    who = match.group("who").strip()
    if any(fuzz.token_set_ratio(who.lower(), a.lower()) >= 85 for a in authors if a):
        head = cleaned[: match.start()].strip(" -:,")
        if head:
            return head
    return cleaned


def _pack(
    title: Optional[str],
    authors: Optional[list],
    year: Optional[str],
    *,
    series: Optional[str] = None,
    series_index: Optional[str] = None,
    isbn: Optional[str] = None,
    language: Optional[str] = None,
) -> Optional[dict]:
    """Normalise a provider hit, lifting any inline series out of the title."""
    if not title:
        return None
    title = strip_edition_tail(title, authors)
    clean_title, inline_series, inline_index = split_series_suffix(title)
    return {
        "title": clean_title,
        "authors": [a for a in (authors or []) if a],
        "year": str(year) if year else None,
        "series": series or inline_series,
        "series_index": series_index or inline_index,
        "isbn": isbn,
        "language": language,
    }


# Providers are queried repeatedly with the same author across a series, and a
# large run re-asks for books it already looked up. A small bounded cache keeps
# a rerun cheap without holding a library's worth of results.
_CACHE: dict[tuple, Optional[dict]] = {}
_CACHE_LIMIT = 512


def _cached(key: tuple, produce):
    if key in _CACHE:
        return _CACHE[key]
    value = produce()
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key] = value
    return value


def clear_cache() -> None:
    """Forget every cached provider response."""
    _CACHE.clear()
    _goodreads_state["consecutive_failures"] = 0
    _goodreads_state["disabled"] = False


# Goodreads soft-blocks a busy client: it answers HTTP 202 with an empty body
# rather than 403, so raise_for_status() passes and the parse simply finds
# nothing. It is queried first on every book, so once it starts refusing we
# would spend one wasted request per book for the rest of the run. Stop asking
# after a few consecutive refusals.
_GOODREADS_FAILURE_LIMIT = 3
_goodreads_state: dict[str, object] = {"consecutive_failures": 0, "disabled": False}


def _note_goodreads(success: bool) -> None:
    if success:
        _goodreads_state["consecutive_failures"] = 0
        return
    count = int(_goodreads_state["consecutive_failures"]) + 1
    _goodreads_state["consecutive_failures"] = count
    if count >= _GOODREADS_FAILURE_LIMIT and not _goodreads_state["disabled"]:
        _goodreads_state["disabled"] = True
        _log.info(
            "goodreads refused %d consecutive requests; skipping it for the "
            "rest of this run", count
        )


def openlib(author: Optional[str], title: str) -> Optional[dict]:
    """Open Library. Uses the dedicated title=/author= parameters rather than
    the `q:` prefix syntax, and asks for the fields we actually store."""

    def fetch() -> Optional[dict]:
        try:
            params: dict[str, object] = {
                "title": title,
                "limit": 5,
                "fields": "title,author_name,first_publish_year,isbn,language",
            }
            if author:
                params["author"] = author
            response = SESSION.get(
                "https://openlibrary.org/search.json", params=params, timeout=10
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
            isbns = best.get("isbn") or []
            languages = best.get("language") or []
            return _pack(
                best.get("title"),
                best.get("author_name", []),
                best.get("first_publish_year"),
                isbn=isbns[0] if isbns else None,
                language=languages[0] if languages else None,
            )
        except Exception as exc:
            _log.debug("openlib lookup failed: %s", exc)
            return None

    return _cached(("openlib", author, title), fetch)


def gbooks(author: Optional[str], title: str) -> Optional[dict]:
    """Google Books. The author clause is joined with a space: a literal '+'
    inside the `q` value is percent-encoded by requests and not read as AND."""

    def fetch() -> Optional[dict]:
        try:
            query = f'intitle:"{title}"' + (f' inauthor:"{author}"' if author else "")
            response = SESSION.get(
                "https://www.googleapis.com/books/v1/volumes",
                params={"q": query, "maxResults": 5, "printType": "books"},
                timeout=10,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            info = max(
                items,
                key=lambda item: fuzz.token_set_ratio(
                    title, item.get("volumeInfo", {}).get("title", "")
                ),
                default=None,
            )
            if not info:
                return None
            volume = info.get("volumeInfo", {})
            isbn = None
            for ident in volume.get("industryIdentifiers", []) or []:
                if ident.get("type") in {"ISBN_13", "ISBN_10"}:
                    isbn = ident.get("identifier")
                    break
            return _pack(
                volume.get("title"),
                volume.get("authors", []),
                (volume.get("publishedDate") or "")[:4] or None,
                isbn=isbn,
                language=volume.get("language"),
            )
        except Exception as exc:
            _log.debug("gbooks lookup failed: %s", exc)
            return None

    return _cached(("gbooks", author, title), fetch)


def goodreads(author: Optional[str], title: str) -> Optional[dict]:
    """Goodreads search. Ranks every result row rather than taking the first.

    This provider had been returning None for every book: the shared session
    identified as "python-requests/x.y.z", Goodreads answers 403 to that, and
    the helper parsed the error page without checking the status. It is the
    cheapest and most series-aware source available, so a silent failure here
    pushed work onto the LLM on every single lookup.
    """

    if _goodreads_state["disabled"]:
        return None

    def fetch() -> Optional[dict]:
        try:
            query = f"{title} {author}" if author else title
            response = SESSION.get(
                "https://www.goodreads.com/search", params={"q": query}, timeout=10
            )
            response.raise_for_status()
            if not response.text.strip():
                # HTTP 202 with an empty body is their soft block, not an error.
                _note_goodreads(False)
                return None
            soup = BeautifulSoup(response.text, "html.parser")

            best_meta = None
            best_score = -1.0
            for row in soup.select("table.tableList tr"):
                title_el = row.select_one("a.bookTitle span")
                author_el = row.select_one("a.authorName span")
                if not title_el or not author_el:
                    continue        # header rows and ads carry neither
                row_title = title_el.get_text(strip=True)
                score = fuzz.token_set_ratio(title.lower(), row_title.lower())
                if author:
                    score = 0.7 * score + 0.3 * fuzz.token_set_ratio(
                        author.lower(), author_el.get_text(strip=True).lower()
                    )
                if score <= best_score:
                    continue
                year = None
                year_el = row.select_one("span.greyText.smallText")
                if year_el:
                    match = re.search(r"published\s+(\d{4})", year_el.get_text())
                    if match:
                        year = match.group(1)
                best_score = score
                best_meta = _pack(
                    row_title, [author_el.get_text(strip=True)], year
                )
            _note_goodreads(best_meta is not None)
            return best_meta
        except Exception as exc:
            _log.debug("goodreads lookup failed: %s", exc)
            _note_goodreads(False)
            return None

    return _cached(("goodreads", author, title), fetch)


def audible(author: Optional[str], title: str) -> Optional[dict]:
    """Audible search. The one provider that names a narrator."""

    def fetch() -> Optional[dict]:
        try:
            query = f"{title} {author}" if author else title
            response = SESSION.get(
                "https://www.audible.com/search",
                params={"keywords": query},
                timeout=10,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
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
            series_index = None
            if series_el:
                label = item.select_one(".seriesLabel")
                if label:
                    match = re.search(r"Book\s+(\d+(?:\.\d+)?)", label.get_text())
                    if match:
                        series_index = match.group(1)
            return _pack(
                title_el.get_text(strip=True),
                [author_el.get_text(strip=True)],
                year,
                series=series_el.get_text(strip=True) if series_el else None,
                series_index=series_index,
            )
        except Exception as exc:
            _log.debug("audible lookup failed: %s", exc)
            return None

    return _cached(("audible", author, title), fetch)


def score_candidate(
    meta: dict,
    title: str,
    author: Optional[str],
    series: Optional[str] = None,
) -> int:
    """How well a provider hit matches what we asked for, 0-100.

    A dimension only carries weight when there is something to compare it
    against, and the title absorbs whatever is left over. The weights used to
    be fixed, so a *perfect* title match with no known author scored
    100 x 0.7 = 70 -- below both ACCEPT_SCORE and the default --llm-threshold
    of 85. Every untagged book therefore went to the LLM even when a provider
    had already returned exactly the right book.
    """
    title_score = fuzz.token_set_ratio(
        title.lower(), (meta.get("title") or "").lower()
    )

    author_weight = 0.0
    author_score = 0.0
    if author and meta.get("authors"):
        author_weight = 0.30
        author_score = max(
            fuzz.token_set_ratio(author.lower(), candidate.lower())
            for candidate in meta["authors"]
        )

    series_weight = 0.0
    series_score = 0.0
    if series and meta.get("series"):
        series_weight = 0.20
        series_score = fuzz.token_set_ratio(series.lower(), meta["series"].lower())

    title_weight = 1.0 - author_weight - series_weight
    return int(round(
        title_score * title_weight
        + author_score * author_weight
        + series_score * series_weight
    ))


def best_match(
    author: Optional[str],
    title: str,
    *,
    series: Optional[str] = None,
    series_index: Optional[str] = None,
    client: AbClient,
) -> tuple[Optional[tuple[int, dict]], dict[str, tuple[int, dict]]]:
    """Query multiple providers and return the best-scoring hit.

    Runs a short ladder of progressively looser queries. Folder-derived titles
    carry rip debris a catalogue will never match ("Daughter of the Empire
    128kbps" matched nothing at all), and an author guessed from a directory
    name is often wrong in a way that suppresses the right book. Each rung is
    only tried when the one before it found nothing good enough, so the common
    case still costs a single Goodreads request.
    """
    cleaned = clean_query_title(title) or title
    attempts: list[tuple[Optional[str], str]] = [(author, cleaned)]
    if author:
        # An author read off a directory name is a guess; the title rarely is.
        attempts.append((None, cleaned))
    if series and cleaned != f"{series} {cleaned}":
        attempts.append((author, f"{cleaned} {series}"))

    seen: set[tuple[Optional[str], str]] = set()
    overall_best: Optional[tuple[int, dict]] = None
    results: dict[str, tuple[int, dict]] = {}

    for query_author, query_title in attempts:
        key = (query_author, query_title)
        if key in seen or not query_title:
            continue
        seen.add(key)

        best, attempt_results = _query_round(
            query_author, query_title, author, title, series, client
        )
        for name, pair in attempt_results.items():
            if name not in results or pair[0] > results[name][0]:
                results[name] = pair
        if best and (overall_best is None or best[0] > overall_best[0]):
            overall_best = best
        if overall_best and overall_best[0] >= ACCEPT_SCORE:
            break

    return overall_best, results


def _query_round(
    query_author: Optional[str],
    query_title: str,
    score_author: Optional[str],
    score_title: str,
    series: Optional[str],
    client: AbClient,
) -> tuple[Optional[tuple[int, dict]], dict[str, tuple[int, dict]]]:
    """One pass over the providers for a single query form.

    Scoring always uses the *original* title and author, not the loosened query
    -- otherwise a broadened search would flatter itself.
    """
    candidates: list[tuple[int, dict]] = []
    results: dict[str, tuple[int, dict]] = {}

    def add_result(name: str, meta: Optional[dict]) -> None:
        if not meta or not meta.get("title"):
            return
        meta = dict(meta)
        meta["source"] = name
        pair = (score_candidate(meta, score_title, score_author, series), meta)
        candidates.append(pair)
        results[name] = pair

    # Tier 1: Goodreads alone. A confident hit costs one request, which keeps
    # the common case cheap and is gentle on the scraped sites. It also names
    # the series inline, which none of the JSON APIs do.
    if client.is_on("use_goodreads", default=True):
        add_result("goodreads", goodreads(query_author, query_title))
        best = results.get("goodreads")
        if best and best[0] >= ACCEPT_SCORE:
            return best, results

    # Tier 2: the rest concurrently. Fanning out bounds a miss at roughly one
    # timeout rather than three chained ones. add_result runs in this thread,
    # as as_completed yields here, so nothing needs locking.
    remaining = {"audible": audible, "openlib": openlib, "gbooks": gbooks}
    with ThreadPoolExecutor(max_workers=len(remaining)) as pool:
        futures = {
            pool.submit(fn, query_author, query_title): name
            for name, fn in remaining.items()
        }
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
    "clean_query_title",
    "clear_cache",
    "score_candidate",
    "split_series_suffix",
    "enrich_metadata_with_providers",
    "gbooks",
    "goodreads",
    "openlib",
]
