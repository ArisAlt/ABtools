"""Metadata provider helpers routed through the MCP tooling layer."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import requests
from rapidfuzz import fuzz

from ablib.core import config
from ablib.core.console import rprint
from ablib.core.http import SESSION
from ablib.metadata.utils import derive_label_hints
from .http import audible, gbooks, goodreads, openlib

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

CONFIG = config.config

MCP_RESULT_CACHE: Dict[str, Dict[str, Any]] = {}
MCP_RESULT_SEQ = 0
# The cache only exists so get_web_search_summaries can look up ids from the
# current conversation, but nothing ever cleared it -- tagging a large library
# accumulated every search result for the life of the process. Bound it, oldest
# out first; dropping a stale id at worst costs one re-fetch.
_MCP_CACHE_LIMIT = 512


def _next_mcp_result_id() -> str:
    global MCP_RESULT_SEQ
    MCP_RESULT_SEQ += 1
    return f"res-{MCP_RESULT_SEQ}"


def serialise_tool_result(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"result": str(result)}, ensure_ascii=False)


def _parse_provider_query(query: str) -> tuple[Optional[str], str]:
    cleaned = re.sub(r"\bsite:[^\s]+\b", "", str(query), flags=re.IGNORECASE).strip()
    if not cleaned:
        return None, ""
    author = None
    title = cleaned
    # Split on the *last* "by", not the first: titles legitimately contain the
    # word ("Stand by Me", "Side by Side"), and taking the first match turned
    # "Stand by Me" into title="Stand", author="Me".
    for match in reversed(list(re.finditer(r"\bby\b", cleaned, flags=re.IGNORECASE))):
        head = cleaned[: match.start()].strip(" \"'-")
        tail = cleaned[match.end():].strip(" \"'-")
        if not head or not tail or any(ch.isdigit() for ch in tail):
            continue
        # Require a two-word author. Single words are too ambiguous -- "Side by
        # Side" would otherwise split into title="Side" / author="Side".
        # A mononym ("Homer") therefore stays unsplit, which is the harmless
        # outcome: the full string is searched as a title and still matches,
        # whereas a wrong split corrupts both fields.
        if len(tail.split()) < 2:
            continue
        title, author = head, tail
        break
    if not title:
        title = cleaned
    return author or None, title


def _compute_confidence(
    query_title: Optional[str], query_author: Optional[str], payload: dict[str, Any]
) -> int:
    title_score = 0
    author_score = 0
    result_title = (payload.get("title") or payload.get("name") or "").strip()
    if query_title and result_title:
        title_score = fuzz.token_set_ratio(query_title.lower(), result_title.lower())
    raw_authors = payload.get("authors") or payload.get("author")
    authors: list[str] = []
    if isinstance(raw_authors, str):
        authors = [raw_authors]
    elif isinstance(raw_authors, list):
        authors = [str(item) for item in raw_authors if isinstance(item, str)]
    elif raw_authors is not None:
        authors = [str(raw_authors)]
    if query_author and authors:
        author_score = max(
            fuzz.token_set_ratio(query_author.lower(), candidate.lower())
            for candidate in authors
        )
    weight_title = 0.7 if query_author else 1.0
    weight_author = 0.3 if query_author else 0.0
    confidence = int(round(title_score * weight_title + author_score * weight_author))
    return max(0, min(100, confidence))


def _normalise_provider_hit(
    source: str,
    data: Optional[Any],
    *,
    query_title: Optional[str],
    query_author: Optional[str],
) -> list[dict[str, Any]]:
    if not data:
        return []
    if isinstance(data, list):
        entries = [dict(item) for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        entries = [dict(data)]
    else:
        return []
    normalised: list[dict[str, Any]] = []
    for payload in entries:
        if "author" in payload and not payload.get("authors"):
            value = payload.pop("author")
            if isinstance(value, str):
                payload["authors"] = [val.strip() for val in value.split(",") if val.strip()]
        payload["source"] = source
        payload["confidence"] = _compute_confidence(query_title, query_author, payload)
        normalised.append(payload)
    return normalised


def mcp_search_audible(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    if not title:
        return []
    return _normalise_provider_hit(
        "audible",
        audible(author, title),
        query_title=title,
        query_author=author,
    )


def mcp_search_goodreads(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    if not title:
        return []
    return _normalise_provider_hit(
        "goodreads",
        goodreads(author, title),
        query_title=title,
        query_author=author,
    )


def mcp_search_google_books(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    if not title:
        return []
    return _normalise_provider_hit(
        "gbooks",
        gbooks(author, title),
        query_title=title,
        query_author=author,
    )


def mcp_search_openlibrary(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    if not title:
        return []
    return _normalise_provider_hit(
        "openlib",
        openlib(author, title),
        query_title=title,
        query_author=author,
    )


def mcp_duckduckgo_fetch_content(query: Optional[str]) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"error": "query is required"}
    results = mcp_full_web_search(q, num_results=1, include_content=True)
    if not results:
        return {"error": "No results", "query": q}
    entry = dict(results[0])
    content = entry.get("content")
    if not content and entry.get("url"):
        page = mcp_get_single_page_content(entry["url"])
        if isinstance(page, dict) and page.get("content"):
            entry["content"] = page["content"]
            entry.setdefault("url", page.get("url"))
    entry.setdefault("query", q)
    return entry


def execute_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    if not name:
        return ""
    try:
        if name == "full_web_search":
            query = str(arguments.get("query", "")).strip()
            num_results = int(arguments.get("num_results", 5) or 5)
            include_content = bool(arguments.get("include_content", False))
            results = mcp_full_web_search(
                query, num_results=num_results, include_content=include_content
            )
            return serialise_tool_result({"results": results})
        if name == "get_web_search_summaries":
            ids = arguments.get("ids") or []
            summaries = [
                MCP_RESULT_CACHE[result_id]
                for result_id in ids
                if result_id in MCP_RESULT_CACHE
            ]
            return serialise_tool_result({"summaries": summaries})
        if name == "get_single_web_page_content":
            url = arguments.get("url")
            return serialise_tool_result(mcp_get_single_page_content(url))
        if name == "sequential_thinking":
            return serialise_tool_result(
                mcp_sequential_thinking(
                    str(arguments.get("query", "")),
                    str(arguments.get("context", "")),
                )
            )
        if name == "search_audible_tool":
            return serialise_tool_result(
                {"results": mcp_search_audible(arguments.get("query", ""))}
            )
        if name == "search_goodreads_tool":
            return serialise_tool_result(
                {"results": mcp_search_goodreads(arguments.get("query", ""))}
            )
        if name == "search_google_books_tool":
            return serialise_tool_result(
                {"results": mcp_search_google_books(arguments.get("query", ""))}
            )
        if name == "search_openlibrary_tool":
            return serialise_tool_result(
                {"results": mcp_search_openlibrary(arguments.get("query", ""))}
            )
        if name == "fetch_content":
            if arguments.get("url"):
                return serialise_tool_result(
                    {"error": "fetch_content expects query; got url"}
                )
            query = str(arguments.get("query", "")).strip()
            if not query:
                return serialise_tool_result({"error": "missing query"})
            return serialise_tool_result(mcp_duckduckgo_fetch_content(query))
        if name == "tag_books_tool":
            return serialise_tool_result(
                {"error": "tag_books_tool is not supported from this client"}
            )
        return serialise_tool_result({"error": f"unknown tool: {name}"})
    except Exception as exc:  # pragma: no cover - defensive
        if CONFIG.debug:
            rprint(f"  [yellow]- tool {name} failed: {exc}[/]")
        return serialise_tool_result({"error": str(exc)})


def mcp_full_web_search(
    query: str, *, num_results: int = 5, include_content: bool = False
) -> list[dict[str, Any]]:
    # DuckDuckGo needs no key. Tavily used to be tried first, but it required a
    # paid key that few installs had, so it only ever added a failed request.
    results = _ddg_search_raw(query, max_results=num_results) or []

    collected: list[dict[str, Any]] = []
    for item in results[:num_results]:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        entry_id = entry.get("id") or entry.get("url") or _next_mcp_result_id()
        entry["id"] = entry_id
        if not include_content and "content" in entry:
            entry.pop("content", None)
        MCP_RESULT_CACHE[entry_id] = entry
        while len(MCP_RESULT_CACHE) > _MCP_CACHE_LIMIT:
            MCP_RESULT_CACHE.pop(next(iter(MCP_RESULT_CACHE)))
        collected.append(entry)
    return collected


def mcp_get_single_page_content(url: Optional[str]) -> dict[str, Any]:
    if not url:
        return {"error": "missing url"}
    try:
        resp = SESSION.get(str(url), timeout=CONFIG.llm_timeout)
        resp.raise_for_status()
        content = resp.text
    except requests.RequestException as exc:
        return {"error": str(exc), "url": url}
    trimmed = content if len(content) <= 4000 else content[:4000]
    return {"url": url, "content": trimmed}


def mcp_sequential_thinking(query: str, context: Optional[str]) -> dict[str, Any]:
    hints = derive_label_hints(query)
    notes: list[str] = []
    title_hint = hints.get("title")
    author_hint = hints.get("author")
    year_hint = hints.get("year")
    series_hint = hints.get("series")
    series_index_hint = hints.get("series_index")
    if title_hint:
        notes.append(f"Normalized title candidate: {title_hint}")
    if author_hint:
        notes.append(f"Possible author fragment: {author_hint}")
    if year_hint:
        notes.append(f"Year detected in label: {year_hint}")
    if series_hint:
        seq_display = f" #{series_index_hint}" if series_index_hint else ""
        notes.append(f"Series clue: {series_hint}{seq_display}")
    if hints.get("normalized") and hints["normalized"] != hints.get("raw"):
        notes.append(f"Label stripped of annotations: {hints['normalized']}")
    if context:
        ctx = context.strip()
        if ctx and ctx.lower() != "audiobook metadata for local tagging":
            notes.append(f"Context: {ctx}")
    if not notes:
        notes.append("No structured hints extracted; rely on catalog research.")
    notes.append("Do not call sequential_thinking again; respond with final JSON metadata now.")
    return {
        "title_hint": title_hint,
        "author_hint": author_hint,
        "year_hint": year_hint,
        "series_hint": series_hint,
        "series_index_hint": series_index_hint,
        "notes": notes,
        "guidance": (
            "Use the hints to cross-check catalog data, confirm author/title alignment, "
            "and adjust series metadata before finalising the JSON response."
        ),
    }


def _ddg_search_raw(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    if DDGS is None:
        if CONFIG.debug:
            rprint("  [yellow]- duckduckgo-search module not installed[/]")
        return []
    
    try:
        results = []
        with DDGS() as ddgs:
            # ddgs.text returns an iterator of dicts {'title':..., 'href':..., 'body':...}
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title"),
                    "url": r.get("href"),
                    "content": r.get("body"),
                })
        return results
    except Exception as exc:
        if CONFIG.debug:
            rprint(f"  [yellow]- DDG search failed: {exc}[/]")
        return []


__all__ = [
    "execute_tool_call",
    "serialise_tool_result",
    "mcp_duckduckgo_fetch_content",
    "mcp_full_web_search",
    "mcp_get_single_page_content",
    "mcp_search_audible",
    "mcp_search_goodreads",
    "mcp_search_google_books",
    "mcp_search_openlibrary",
    "mcp_sequential_thinking",
    "_ddg_search_raw",
]
