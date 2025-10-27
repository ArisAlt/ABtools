
#!/usr/bin/env python3
"""
ABtools/search_and_tag.py - v2.30 (2025-09-12)
Tag (or strip) audiobook files using multiple metadata providers.
    The script queries Audible, Open Library, Google Books and Goodreads
    via the LM Studio MCP server. Each provider search is routed through
    ``full_web_search`` with an appropriate ``site:`` filter, then parsed
    into metadata that is ranked using fuzzy title *and author* matching.
    Low scoring hits will prompt for confirmation unless you run with
    ``--yes``. Use ``--no`` to automatically decline low-scoring matches.
    When prompted, the default answer is "No" so low confidence matches
    won't be accepted accidentally. Log files are written next to the
    chosen root as ``tag_log.txt`` and ``review_log.txt``. Use
    ``--version`` to print the script version and file location.
Supply ``--llm-endpoint``/``--llm-model`` to let a local LM Studio
instance (tested with Mistral-7B Q4 on port 1234) suggest metadata when
online providers fail or return low scores. Adjust the trigger with
``--llm-threshold`` (default: 85, minimum: 80). When the fallback is used the script
shares folder context and file names with the model and expects JSON
metadata in return; no local transcription step is required anymore.
"""
from __future__ import annotations
import argparse, datetime, os, re, sys, textwrap
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from abclient import AbClient
from dataclasses import dataclass
VERSION = "2.30"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"
DEBUG = False
AB = AbClient()
import requests
SESSION = requests.Session()
from rapidfuzz import fuzz
import json
import xml.etree.ElementTree as ET
from mutagen import File as MFile, MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TALB, TPE1, TDRC, TXXX, TRCK
from mutagen.mp4 import MP4, MP4StreamInfoError
from bs4 import BeautifulSoup
# ----- colour (rich) or plain text -----
try:
    from rich import print as rprint
    from rich.prompt import Confirm
except ImportError:  # plain console, strip tags like [bold]...[/]
    _TAGS = re.compile(r"\[/?[a-zA-Z].*?]")
    def rprint(*a, **k): print(_TAGS.sub("", " ".join(map(str, a))), **k)
    def Confirm(prompt: str, default=False):
        ans = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").lower().strip()
        return default if ans == "" else ans in {"y", "yes"}
# ----- constants -----
AUDIO_EXTS = {".mp3", ".m4a", ".m4b"}
TAIL_RX    = re.compile(r"(?:\s*(?:\{[^}]*\}|\d+\.\d{2}\.\d{2}|\d+\s*[kK](?:bps)?|kbps))*\s*$")
PAREN_RX   = re.compile(r"\([^)]*\)")
YEAR_RX    = re.compile(r"^(\d{4})\s*[-_]\s*")
LOG_PATH   = Path("tag_log.txt")
REVIEW_PATH = Path("review_log.txt")
SERIES_PATTERNS = [
    re.compile(r'^(.+?)\s+(\d+(?:\.\d+)?)\s+(.+)$'),  # "Series 01 Title"
    re.compile(r'^(.+?)\s+Book\s+(\d+)\s+(.+)$', re.IGNORECASE),  # "Series Book 1 Title"
    re.compile(r'^(.+?)\s+#(\d+)\s+(.+)$'),  # "Series #1 Title"
    re.compile(r'^(.+?)\s+Vol\.?\s+(\d+)\s+(.+)$', re.IGNORECASE),  # "Series Vol 1 Title"
    re.compile(r'^(\d+(?:\.\d+)?)\s+(.+)$'),  # "01 Title" (number only)
]
LLM_ENDPOINT: Optional[str] = "http://127.0.0.1:8888/v1/chat/completions"
LLM_MODEL_NAME: Optional[str] = "ibm/granite-4-h-tiny"
LLM_TIMEOUT: int = 90
LLM_MAX_TOKENS: int = 8000
TAVILY_API_KEY: Optional[str] = os.environ.get("TAVILY_API_KEY")
TAVILY_ENDPOINT: str = os.environ.get("TAVILY_ENDPOINT", "https://api.tavily.com/search")
LLM_SYSTEM_PROMPT = (
    "You analyse audiobook folders and files, respond with JSON metadata only."
)
MCP_SYSTEM_PROMPT = textwrap.dedent(
    """
    You research audiobooks via the LM Studio MCP server.
    Always call the ABtools provider tools in this order:
      1. Use `search_goodreads_tool` with the title and author.
      2. If the best Goodreads confidence is below 90, call `search_audible_tool`.
      3. When neither provider yields a confidence ≥ 90, call the DuckDuckGo MCP `fetch_content`
         tool to gather supporting excerpts before finalising the JSON.
    Provider responses include a `confidence` field (0-100); treat values ≥ 90 as reliable matches.
    Use `get_single_web_page_content` only when you must extract details from a specific URL.
    Respond with a single JSON object describing the audiobook (title, authors[], year, series,
    series_index, narrator, publisher, description). Never return plain text.
    """
).strip()
MCP_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_goodreads_tool",
            "description": "Query Goodreads for audiobook metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_audible_tool",
            "description": "Query Audible for audiobook metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_content",
            "description": "Fetch supporting content via the DuckDuckGo MCP plugin.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_single_web_page_content",
            "description": "Retrieve the content of a web page by URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sequential_thinking",
            "description": "Request structured reasoning guidance before finalising metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
]
MCP_PROVIDER_SITES = {
    "audible": ("Audible", "audible.com"),
    "openlib": ("Open Library", "openlibrary.org"),
    "gbooks": ("Google Books", "books.google.com"),
    "goodreads": ("Goodreads", "goodreads.com"),
}
def _call_llm(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    tools: Optional[list[dict[str, Any]]] = None,
    max_tokens: int | None = None,
    attempt: int = 0,
) -> Optional[str]:
    if not LLM_ENDPOINT or not LLM_MODEL_NAME:
        return None
    token_budget = max_tokens or LLM_MAX_TOKENS
    sys_prompt = system_prompt or LLM_SYSTEM_PROMPT
    convo: list[dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ]
    length_retry = attempt
    used_tools: dict[str, int] = {}
    while True:
        payload: dict[str, Any] = {
            "model": LLM_MODEL_NAME,
            "messages": convo,
            "temperature": 0.0,
            "max_tokens": token_budget,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = SESSION.post(LLM_ENDPOINT, json=payload, timeout=LLM_TIMEOUT)
        except requests.RequestException as exc:  # pragma: no cover - network guard
            if DEBUG:
                rprint(f"  [yellow]- LM Studio request failed: {exc}[/]")
            return None
        if resp.status_code >= 400:
            if DEBUG:
                rprint(
                    f"  [yellow]- LM Studio returned HTTP {resp.status_code}: {resp.text[:200]}[/]"
                )
            return None
        try:
            data = resp.json()
        except ValueError:
            if DEBUG:
                rprint("  [yellow]- LM Studio response was not valid JSON[/]")
            return None
        choices = data.get("choices")
        if not choices:
            return None
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
        if tool_calls:
            convo.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name")
                tool_name = (name or "").strip()
                arguments_raw = fn.get("arguments") or "{}"
                try:
                    arguments = json.loads(arguments_raw) if arguments_raw else {}
                except json.JSONDecodeError:
                    arguments = {}
                if tool_name == "sequential_thinking" and used_tools.get(tool_name):
                    tool_response = _serialise_tool_result(
                        {
                            "notes": [
                                "sequential_thinking already executed; respond with final JSON metadata now."
                            ],
                            "guidance": "Use the prior sequential thinking notes to complete the metadata without issuing further tool calls.",
                        }
                    )
                else:
                    tool_response = _execute_tool_call(tool_name, arguments)
                if tool_name:
                    used_tools[tool_name] = used_tools.get(tool_name, 0) + 1
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or name or "tool",
                        "name": name or "tool",
                        "content": tool_response,
                    }
                )
            # loop to request follow-up completion
            continue
        if finish_reason == "length" and length_retry == 0:
            new_budget = min(token_budget * 2, 2048)
            if DEBUG:
                rprint(
                    f"  [yellow]- LM Studio response hit max_tokens={token_budget}; retrying with {new_budget}[/]"
                )
            token_budget = new_budget
            length_retry = 1
            continue
        if not content:
            return None
        convo.append({"role": "assistant", "content": str(content)})
        return str(content)
MCP_RESULT_CACHE: Dict[str, Dict[str, Any]] = {}
MCP_RESULT_SEQ = 0
def _next_mcp_result_id() -> str:
    global MCP_RESULT_SEQ
    MCP_RESULT_SEQ += 1
    return f"res-{MCP_RESULT_SEQ}"
def _serialise_tool_result(result: Any) -> str:
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
    match = re.search(r"\bby\b", cleaned, flags=re.IGNORECASE)
    if match:
        title = cleaned[: match.start()].strip(" \"'-")
        author = cleaned[match.end() :].strip(" \"'-") or None
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
        authors = [str(a) for a in raw_authors if isinstance(a, str)]
    elif raw_authors is not None:
        authors = [str(raw_authors)]
    if query_author and authors:
        author_score = max(
            fuzz.token_set_ratio(query_author.lower(), author.lower())
            for author in authors
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
    entries: list[dict[str, Any]]
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
                payload["authors"] = [v.strip() for v in value.split(",") if v.strip()]
        payload["source"] = source
        payload["confidence"] = _compute_confidence(query_title, query_author, payload)
        normalised.append(payload)
    return normalised
def mcp_search_audible(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    return (
        _normalise_provider_hit(
            "audible",
            audible(author, title),
            query_title=title,
            query_author=author,
        )
        if title
        else []
    )
def mcp_search_goodreads(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    return (
        _normalise_provider_hit(
            "goodreads",
            goodreads(author, title),
            query_title=title,
            query_author=author,
        )
        if title
        else []
    )
def mcp_search_google_books(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    return (
        _normalise_provider_hit(
            "gbooks",
            gbooks(author, title),
            query_title=title,
            query_author=author,
        )
        if title
        else []
    )
def mcp_search_openlibrary(query: str) -> list[dict[str, Any]]:
    author, title = _parse_provider_query(query)
    return (
        _normalise_provider_hit(
            "openlib",
            openlib(author, title),
            query_title=title,
            query_author=author,
        )
        if title
        else []
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
def _execute_tool_call(name: str, arguments: Dict[str, Any]) -> str:
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
            return _serialise_tool_result({"results": results})
        if name == "get_web_search_summaries":
            ids = arguments.get("ids") or []
            summaries = [
                MCP_RESULT_CACHE[result_id]
                for result_id in ids
                if result_id in MCP_RESULT_CACHE
            ]
            return _serialise_tool_result({"summaries": summaries})
        if name == "get_single_web_page_content":
            url = arguments.get("url")
            return _serialise_tool_result(mcp_get_single_page_content(url))
        if name == "sequential_thinking":
            return _serialise_tool_result(
                mcp_sequential_thinking(
                    str(arguments.get("query", "")),
                    str(arguments.get("context", "")),
                )
            )
        if name == "search_audible_tool":
            return _serialise_tool_result(
                {"results": mcp_search_audible(arguments.get("query", ""))}
            )
        if name == "search_goodreads_tool":
            return _serialise_tool_result(
                {"results": mcp_search_goodreads(arguments.get("query", ""))}
            )
        if name == "search_google_books_tool":
            return _serialise_tool_result(
                {"results": mcp_search_google_books(arguments.get("query", ""))}
            )
        if name == "search_openlibrary_tool":
            return _serialise_tool_result(
                {"results": mcp_search_openlibrary(arguments.get("query", ""))}
            )
        if name == "fetch_content":
            if arguments.get("url"):
                return _serialise_tool_result({"error": "fetch_content expects query; got url"})
            query = str(arguments.get("query", "")).strip()
            if not query:
                return _serialise_tool_result({"error": "missing query"})
            return _serialise_tool_result(mcp_duckduckgo_fetch_content(query))
        if name == "tag_books_tool":
            return _serialise_tool_result(
                {"error": "tag_books_tool is not supported from this client"}
            )
        return _serialise_tool_result({"error": f"unknown tool: {name}"})
    except Exception as exc:  # pragma: no cover - defensive
        if DEBUG:
            rprint(f"  [yellow]- tool {name} failed: {exc}[/]")
        return _serialise_tool_result({"error": str(exc)})
def mcp_full_web_search(
    query: str, *, num_results: int = 5, include_content: bool = False
) -> list[dict[str, Any]]:
    results = _tavily_search_raw(
        query, max_results=num_results, include_content=include_content
    ) or []
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
        collected.append(entry)
    return collected
def mcp_get_single_page_content(url: Optional[str]) -> dict[str, Any]:
    if not url:
        return {"error": "missing url"}
    try:
        resp = SESSION.get(str(url), timeout=LLM_TIMEOUT)
        resp.raise_for_status()
        content = resp.text
    except requests.RequestException as exc:
        return {"error": str(exc), "url": url}
    trimmed = content if len(content) <= 4000 else content[:4000]
    return {"url": url, "content": trimmed}
def mcp_sequential_thinking(query: str, context: Optional[str]) -> dict[str, Any]:
    hints = _derive_label_hints(query)
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
def _tavily_search_raw(
    query: str, *, max_results: int = 5, include_content: bool = False
) -> Optional[list[dict[str, Any]]]:
    if not TAVILY_API_KEY:
        return None
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
    }
    if include_content:
        payload["include_content"] = True
    try:
        resp = SESSION.post(TAVILY_ENDPOINT, json=payload, timeout=LLM_TIMEOUT)
    except requests.RequestException as exc:
        if DEBUG:
            rprint(f"  [yellow]- Tavily search failed: {exc}[/]")
        return None
    if resp.status_code >= 400:
        if DEBUG:
            rprint(
                f"  [yellow]- Tavily returned HTTP {resp.status_code}: {resp.text[:200]}[/]"
            )
        return None
    try:
        data = resp.json()
    except ValueError:
        if DEBUG:
            rprint("  [yellow]- Tavily response was not valid JSON[/]")
        return None
    results = data.get("results")
    if not results:
        return []
    return results
def _tavily_search(query: str, *, max_results: int = 3) -> Optional[str]:
    results = _tavily_search_raw(query, max_results=max_results)
    if not results:
        return None
    snippets: List[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("url") or "Result"
        content = item.get("content") or item.get("snippet") or ""
        url = item.get("url")
        chunk = content.strip()
        if len(chunk) > 500:
            chunk = chunk[:500].rsplit(" ", 1)[0] + "..."
        line = f"- {title.strip()}"
        if url:
            line += f" ({url.strip()})"
        if chunk:
            line += f": {chunk}"
        snippets.append(line)
    return "\n".join(snippets[:max_results]) if snippets else None
def log(status: str, message: str):
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%F %T}  {status:<7}  {message}\n")
def review_log(path: Path, reason: str):
    REVIEW_PATH.parent.mkdir(exist_ok=True)
    with REVIEW_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%F %T}  {reason:<9}  {path}\n")
# ----- tiny helpers -----
def clean_tail(s: str) -> str:
    return TAIL_RX.sub("", s).strip()
def strip_annotations(s: str) -> str:
    if not s:
        return ""
    s = PAREN_RX.sub("", s)
    s = re.sub(r"\[[^]]*\]", "", s)
    s = re.sub(r"\{[^}]*\}", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" -_\t")
def _derive_label_hints(label: str) -> dict[str, Optional[str]]:
    """Extract best-effort hints (title, author, year, series) from a folder label."""
    raw = (label or "").strip()
    if not raw:
        return {"title": None, "author": None, "year": None, "series": None, "series_index": None}
    cleaned = strip_annotations(clean_tail(raw))
    cleaned = TAIL_RX.sub("", cleaned).strip()
    year = None
    if (m := YEAR_RX.match(cleaned)):
        year = m.group(1)
        cleaned = cleaned[m.end():].lstrip(" -_")
    author_hint = None
    parts = [p.strip() for p in re.split(r"\s*[-–]\s*", cleaned) if p.strip()]
    title_part = cleaned
    if parts:
        possible_author = parts[0]
        if len(parts) > 1 and " " in possible_author and not possible_author.isdigit():
            author_hint = possible_author
            title_part = " - ".join(parts[1:]).strip()
        else:
            title_part = cleaned
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
def has_audio(folder: Path) -> bool:
    return any(c.suffix.lower() in AUDIO_EXTS for c in folder.iterdir())
def determine_best_author(folder: Path, initial_guess: Optional[str], partial_meta: Optional[dict] = None) -> Optional[str]:
    """Determine the most plausible author from multiple sources."""
    
    # Priority 1: Existing metadata from previous API calls
    if partial_meta and partial_meta.get("author"):
        return partial_meta["author"]
    
    # Priority 2: Initial guess from folder parsing
    if initial_guess:
        cleaned_guess = strip_annotations(initial_guess)
        if len(cleaned_guess.split()) >= 2:
            return cleaned_guess
    
    # Priority 3: Parent folder name (common audiobook structure)
    parent_name = strip_annotations(clean_tail(folder.parent.name))
    if parent_name and len(parent_name.split()) >= 2 and parent_name != "Unknown Author":
        return parent_name
    
    # Priority 4: Grandparent folder (for nested structures)
    if folder.parent.parent != folder.parent:  # Not root
        grandparent_name = strip_annotations(clean_tail(folder.parent.parent.name))
        if grandparent_name and len(grandparent_name.split()) >= 2:
            return grandparent_name
    
    return None
def enhanced_author_extraction(folder: Path) -> Optional[str]:
    """Enhanced author extraction from folder structure."""
    
    # Check common audiobook folder patterns:
    # Author/Year - Title/
    # Author - Series/Book Title/
    # Series/Author - Book Title/
    
    folder_parts = folder.parts
    for i, part in enumerate(folder_parts):
        part_clean = strip_annotations(clean_tail(part))
        
        # Skip common non-author parts
        if part_clean.lower() in ['audiobooks', 'books', 'library', 'media']:
            continue
            
        # Check if this looks like an author name
        if len(part_clean.split()) >= 2 and not re.match(r'^\d{4}', part_clean):
            # Additional validation: check if next part looks like a title
            if i + 1 < len(folder_parts):
                next_part = clean_tail(folder_parts[i + 1])
                if not re.match(r'^\d{4}', next_part):  # Not a year
                    return part_clean
    
    return None
def extract_series_and_title(text: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Extract series name, series index, and title from text.
    Handles patterns like:
    - "Series Name 01 Title"
    - "Series Name Book 1 Title"
    - "Series Name #1 Title"
    - "01 Title" (series number only)
    Returns: (series_name, series_index, title)
    """
    text = text.strip()
    if not text:
        return None, None, ""
    
    # Try each pattern in order
    for pattern in SERIES_PATTERNS:
        match = pattern.match(text)
        if match:
            groups = match.groups()
            
            if len(groups) == 3:
                # Pattern: "Series Name NN Title"
                series_name, series_index, title = groups
                return series_name.strip(), series_index.strip(), title.strip()
            elif len(groups) == 2:
                # Pattern: "NN Title" (number only)
                series_index, title = groups
                return None, series_index.strip(), title.strip()
    
    # No pattern matched, return as title only
    return None, None, text
# ----- filename guess -----
def guess_from_path(p: Path) -> Tuple[Optional[str], str, Optional[str], Optional[str], Optional[str]]:
    """Return (author, title, year, series, series_index)."""
    leaf = clean_tail(p.stem if p.is_file() else p.name)
    year = None
    series = None
    series_index = None
    
    # Extract year from start
    if (m := YEAR_RX.match(leaf)):
        year, leaf = m.group(1), leaf[m.end():].lstrip(" -_")
    
    # Split by " - "
    parts = [x.strip() for x in leaf.split(" - ")]
    
    # Remove leading numeric part if exists
    if parts and re.fullmatch(r"\d+", parts[0]):
        parts = parts[1:]
    
    # Extract year from end
    if parts and re.fullmatch(r"\d{4}", parts[-1]) and year is None:
        year = parts.pop()
    
    # Try to extract series and title
    if len(parts) >= 1:
        combined_text = " - ".join(parts[:-1]) if len(parts) >= 2 else parts[0]
        series, series_index, title = extract_series_and_title(combined_text)
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
        title, author = leaf, None
    
    # Fallback to parent folder for author
    if not author:
        parent = strip_annotations(clean_tail(p.parent.name))
        author = parent if " " in parent else None
    
    title = strip_annotations(title)
    return author, title, year, series, series_index
# ----- online lookup helpers -----
def openlib(author: Optional[str], title: str) -> Optional[dict]:
    try:
        q = f"title:{title}" + (f" author:{author}" if author else "")
        r = SESSION.get("https://openlibrary.org/search.json",
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
        r = SESSION.get("https://www.googleapis.com/books/v1/volumes",
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
def goodreads(author: Optional[str], title: str) -> Optional[dict]:
    try:
        q = f"{title} {author}" if author else title
        html = SESSION.get(
            "https://www.goodreads.com/search",
            params={"q": q},
            timeout=10,
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
            m = re.search(r"(\d{4})", year_el.get_text())
            if m:
                year = m.group(1)
        return {
            "title": title_el.get_text(strip=True),
            "authors": [author_el.get_text(strip=True)],
            "year": year,
        }
    except Exception:
        return None
def audible(author: Optional[str], title: str) -> Optional[dict]:
    try:
        q = f"{title} {author}" if author else title
        html = SESSION.get(
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
def best_match(author: Optional[str], title: str, series: Optional[str] = None, series_index: Optional[str] = None, client: AbClient = AB) -> tuple[Optional[tuple[int, dict]], dict[str, tuple[int, dict]]]:
    """Query metadata providers and return the best hit along with all scores."""
    candidates: list[tuple[int, dict]] = []
    results: dict[str, tuple[int, dict]] = {}
    def add_result(name: str, meta: Optional[dict]):
        if meta and meta.get("title"):
            title_score = fuzz.token_set_ratio(title.lower(), meta["title"].lower())
            author_score = 0
            if author and meta.get("authors"):
                author_score = max(
                    fuzz.token_set_ratio(author.lower(), a.lower())
                    for a in meta["authors"]
                )
            # Add series matching bonus
            series_score = 0
            if series and meta.get("series"):
                series_score = fuzz.token_set_ratio(series.lower(), meta["series"].lower())
            # Weighted score: 50% title, 25% author, 25% series (if series exists)
            if series:
                score = int(title_score * 0.5 + author_score * 0.25 + series_score * 0.25)
            else:
                score = int(title_score * 0.7 + author_score * 0.3)
            meta["source"] = name
            pair = (score, meta)
            candidates.append(pair)
            results[name] = pair
    # Always query Goodreads first when enabled.
    if client.is_on("use_goodreads", default=True):
        add_result("goodreads", goodreads(author, title))
        if "goodreads" in results and results["goodreads"][0] >= 85:
            return results["goodreads"], results
    # Follow up with Audible only if Goodreads did not return a high-confidence hit.
    add_result("audible", audible(author, title))
    if not candidates:
        return None, results
    return max(candidates, key=lambda x: x[0]), results
def _enrich_metadata_with_providers(meta: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Fill missing metadata fields using provider lookups."""
    title = meta.get("title")
    if not title:
        return meta
    needed_keys = {key for key in ("author", "year", "series") if not (meta.get(key) or "")}
    if not needed_keys:
        return meta
    author = meta.get("author")
    providers = (audible, openlib, gbooks)
    for fn in providers:
        info = fn(author, title)
        if not info:
            continue
        if "author" in needed_keys:
            authors = info.get("authors")
            if authors:
                meta["author"] = ", ".join(a for a in authors if a)
        if "year" in needed_keys and info.get("year"):
            meta["year"] = info["year"]
        if "series" in needed_keys and info.get("series"):
            meta["series"] = info["series"]
        needed_keys = {key for key in ("author", "year", "series") if not (meta.get(key) or "")}
        if not needed_keys:
            break
        author = meta.get("author")
    return meta


def format_metadata_summary(meta: Dict[str, Any]) -> str:
    """Return a compact human-readable summary for logging."""
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
    extra_keys = [
        key for key in ("narrator", "description", "score") if key in meta and meta.get(key)
    ]
    for key in extra_keys:
        value = str(meta.get(key)).strip()
        if not value:
            continue
        if key == "description" and len(value) > 60:
            value = value[:57].rstrip() + "..."
        summary += f" | {key}={value}"
    return summary


def validate_metadata_fields(meta: Dict[str, Any]) -> tuple[bool, list[str]]:
    """Apply heuristic checks to ensure metadata looks plausible."""
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
        narrator_str = str(narrator).strip()
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

def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # remove optional language hint
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        else:
            text = ""
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()
def _normalise_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = str(value)
    elif isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        value = ", ".join(parts)
    elif not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
def generate_metadata_via_llm(
    folder: Path,
    files: list[Path],
    guess: Optional[Dict[str, Any]] = None,
    provider_scores: Optional[Dict[str, int]] = None,
) -> Optional[dict]:
    if not files:
        return None
    if not LLM_ENDPOINT or not LLM_MODEL_NAME:
        return None
    folder_label = folder.name or folder.stem or str(folder)
    file_lines = "\n".join(f"- {f.name}" for f in files[:25])
    if len(files) > 25:
        file_lines += f"\n- ... (+{len(files) - 25} more)"
    guess_lines: list[str] = []
    if guess:
        guess_lines.append("Guess metadata:")
        if guess.get("path"):
            guess_lines.append(f"  - Path: {guess['path']}")
        guess_title = guess.get("title") or "Unknown"
        guess_author = guess.get("author") or "Unknown"
        guess_year = guess.get("year") or "Unknown"
        guess_lines.append(f"  - Folder guess: {guess_title} by {guess_author} ({guess_year})")
        if guess.get("series"):
            guess_lines.append(
                f"  - Series guess: {guess['series']} #{guess.get('series_index') or '?'}"
            )
    guess_block = "\n".join(guess_lines) if guess_lines else "Guess metadata: not provided."

    provider_lines: list[str] = []
    if provider_scores:
        provider_lines.append("Provider scores (higher is better):")
        for name, score in sorted(provider_scores.items(), key=lambda item: -item[1]):
            provider_lines.append(f"  - {name}: {score}")
    provider_block = (
        "\n".join(provider_lines) if provider_lines else "Provider scores: not available."
    )

    prompt = textwrap.dedent(
        f"""
        You are generating audiobook metadata for local tagging.
        Folder name: {folder_label}
        Total audio files: {len(files)}
        Audio files:
        {file_lines}

        {guess_block}

        {provider_block}

        Aim to produce metadata that will achieve a confidence score of 90 or higher; high-scoring responses
        earn a bonus reward. Research the matching audiobook edition via the LM Studio MCP server using this order:
        Research the matching audiobook edition via the LM Studio MCP server using this order:
          1. Call `search_goodreads_tool` with the suspected title and author.
          2. If the best Goodreads confidence is below 90, call `search_audible_tool` to cross-check.
          3. When neither provider produces a confidence ≥ 90, call the DuckDuckGo MCP `fetch_content`
             tool to gather supporting excerpts before finalising the answer.
        Provider responses include a `confidence` value from 0-100; treat scores ≥ 90 as reliable matches.
        If a specific URL needs inspection, call `get_single_web_page_content`. Respond with a single
        JSON object containing:
          - "title" (required)
          - "author" (required)
          - "series" (optional)
          - "series_index" (optional)
          - "year" (optional four digit year)
          - "narrator" (optional)
          - "language" (optional language code or name)
          - "description" (optional short summary)
          - "publisher" (optional)
        Use null when a value is unknown. Respond with JSON only.
        """
    ).strip()
    allowed = {
        "title",
        "author",
        "series",
        "series_index",
        "year",
        "narrator",
        "language",
        "description",
        "publisher",
    }
    optional_keys = {
        "series",
        "series_index",
        "year",
        "narrator",
        "language",
        "description",
        "publisher",
    }
    def parse_llm_raw(raw: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
        if raw is None:
            return None
        cleaned = _strip_fence(raw)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            if DEBUG:
                rprint("  [yellow]- LM Studio returned non-JSON metadata[/]")
            return None
        if not isinstance(payload, dict):
            return None
        meta: Dict[str, Optional[str]] = {}
        for key in allowed:
            if key in payload:
                meta[key] = _normalise_value(payload[key])
        if not meta.get("title") or not meta.get("author"):
            return None
        year_value = meta.get("year")
        if year_value:
            match = re.search(r"\b(\d{4})\b", year_value)
            meta["year"] = match.group(1) if match else None
        if meta.get("series_index"):
            meta["series_index"] = _normalise_value(meta["series_index"])
        result_meta: Dict[str, Optional[str]] = {
            "title": meta["title"],
            "author": meta["author"],
            "year": meta.get("year"),
            "series": meta.get("series"),
        }
        if meta.get("series_index"):
            result_meta["series_index"] = meta["series_index"]
        for extra in ("narrator", "language", "description", "publisher"):
            if meta.get(extra):
                result_meta[extra] = meta[extra]
        return result_meta
    def missing_optional(meta: Dict[str, Optional[str]]) -> set[str]:
        return {
            key
            for key in optional_keys
            if not (str(meta.get(key)).strip() if meta.get(key) is not None else "")
        }
    primary_raw = _call_llm(
        prompt,
        system_prompt=MCP_SYSTEM_PROMPT,
        tools=MCP_TOOLS,
        max_tokens=1024,
    )
    if primary_raw is None:
        if DEBUG:
            rprint("  [yellow]- LM Studio metadata request returned no content[/]")
        return None
    result = parse_llm_raw(primary_raw)
    missing_fields = missing_optional(result) if result else optional_keys
    # Retry once with a stronger instruction if important fields are missing.
    if missing_fields:
        missing_list = ", ".join(sorted(missing_fields))
        tavily_context = None
        if TAVILY_API_KEY:
            query_terms: List[str] = []
            if result and result.get("title"):
                query_terms.append(str(result["title"]))
            else:
                query_terms.append(folder_label)
            if result and result.get("author"):
                query_terms.append(str(result["author"]))
            query = " ".join(t for t in query_terms if t).strip()
            if query:
                tavily_context = _tavily_search(query)
                if DEBUG and tavily_context:
                    rprint(f"  [cyan]- Tavily search context fetched for '{query}'[/]")
        retry_prompt = (
            prompt
            + "\n\nThe previous response was missing these fields: "
            + missing_list
            + ". Please research reputable audiobook sources (Audible, Open Library, Google Books, publisher sites) and try again."
        )
        if tavily_context:
            retry_prompt += (
                "\n\nExternal research via Tavily Search (summaries):\n"
                + tavily_context
                + "\nUse this information to fill the missing metadata fields."
            )
        else:
            retry_prompt += "\n\nIf needed, consult the Tavily Search API when gathering details."
        if DEBUG:
            rprint(
                "  [cyan]- retrying LM Studio metadata request to fill: "
                + missing_list
                + "[/]"
            )
        retry_raw = _call_llm(
            retry_prompt,
            system_prompt=MCP_SYSTEM_PROMPT,
            tools=MCP_TOOLS,
            max_tokens=1024,
        )
        retry_result = parse_llm_raw(retry_raw)
        if retry_result:
            if result:
                for key, value in retry_result.items():
                    if value and not (result.get(key) and result.get(key).strip()):
                        result[key] = value
            else:
                result = retry_result
    if not result:
        return None
    result = _enrich_metadata_with_providers(result)
    result["source"] = "llm"
    return result
def refine_metadata_via_mcp(folder: Path, author_guess: Optional[str], title_guess: str, 
                           series_guess: Optional[str] = None, series_index_guess: Optional[str] = None,
                           initial_score: int = 0, partial_meta: Optional[dict] = None) -> Optional[dict]:
    """Two-stage MCP refinement pipeline for low-confidence metadata."""
    if not LLM_ENDPOINT or not LLM_MODEL_NAME:
        return None
    
    folder_label = folder.name or folder.stem or str(folder)
    
    # Determine best author for search queries
    best_author = determine_best_author(folder, author_guess, partial_meta)
    if not best_author:
        best_author = enhanced_author_extraction(folder)
    
    # Stage 1: Web search refinement
    stage1_prompt = textwrap.dedent(f"""
        You are refining audiobook metadata using web search tools.
        Folder: {folder_label}
        Title: "{title_guess}"
        Author: {best_author or 'Unknown'}
        Series: {series_guess or 'Unknown'}
        Series Index: {series_index_guess or 'Unknown'}
        Initial score: {initial_score}
        
        Use the full_web_search tool with site filters for:
        - site:audible.com "{title_guess}" {best_author or ''}
        - site:openlibrary.org "{title_guess}" {best_author or ''}
        - site:books.google.com "{title_guess}" {best_author or ''}
        - site:goodreads.com "{title_guess}" {best_author or ''}
        
        Research this audiobook and respond with JSON containing:
        - "title" (required)
        - "author" (required)
        - "year" (optional)
        - "series" (optional)
        - "series_index" (optional)
        - "narrator" (optional)
        - "language" (optional)
        - "description" (optional)
        - "publisher" (optional)
        - "score" (confidence 0-100, required)
        
        Use null for unknown values. Respond with JSON only.
    """).strip()
    
    def parse_mcp_response(raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if raw is None:
            return None
        cleaned = _strip_fence(raw)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            if DEBUG:
                rprint("  [yellow]- MCP response was not valid JSON[/]")
            return None
        if not isinstance(payload, dict):
            return None
        
        # Validate required fields
        if not payload.get("title") or not payload.get("author"):
            return None
        
        # Normalize fields
        meta: Dict[str, Any] = {}
        for key in ["title", "author", "year", "series", "series_index", "narrator", "language", "description", "publisher"]:
            meta[key] = _normalise_value(payload.get(key))
        
        # Get score from response
        llm_score = payload.get("score")
        if isinstance(llm_score, (int, float)):
            meta["score"] = int(llm_score)
        else:
            meta["score"] = 0
        
        return meta
    
    def calculate_combined_score(meta: Dict[str, Any], folder_name: str, title_guess: str, author_guess: Optional[str]) -> int:
        """Calculate combined score: 50% LLM score + 50% fuzzy match."""
        llm_score = meta.get("score", 0)
        
        # Fuzzy match against folder name and guesses
        title_score = fuzz.token_set_ratio(title_guess.lower(), meta.get("title", "").lower())
        author_score = 0
        if author_guess and meta.get("author"):
            author_score = fuzz.token_set_ratio(author_guess.lower(), meta.get("author", "").lower())
        
        # Also check against best_author if available
        if best_author and meta.get("author"):
            best_author_score = fuzz.token_set_ratio(best_author.lower(), meta.get("author", "").lower())
            author_score = max(author_score, best_author_score)
        
        folder_score = fuzz.token_set_ratio(folder_name.lower(), f"{meta.get('title', '')} {meta.get('author', '')}".lower())
        
        fuzzy_score = int((title_score * 0.4 + author_score * 0.3 + folder_score * 0.3))
        
        # Combined score: 50% LLM + 50% fuzzy
        combined = int(llm_score * 0.5 + fuzzy_score * 0.5)
        meta["score"] = combined
        return combined
    
    # Stage 1: Web search refinement
    try:
        stage1_raw = _call_llm(
            stage1_prompt,
            system_prompt=MCP_SYSTEM_PROMPT,
            tools=MCP_TOOLS,
            max_tokens=1024,
        )
        
        if stage1_raw is None:
            if DEBUG:
                rprint("  [yellow]- Stage 1 MCP refinement failed[/]")
            return None
        
        stage1_meta = parse_mcp_response(stage1_raw)
        if not stage1_meta:
            if DEBUG:
                rprint("  [yellow]- Stage 1 MCP response invalid[/]")
            return None
        
        # Calculate combined score
        stage1_score = calculate_combined_score(stage1_meta, folder_label, title_guess, author_guess)
        stage1_meta["refinement_source"] = "refined_web_search"
        
        if DEBUG:
            rprint(f"  [cyan]- Stage 1 refinement score: {stage1_score}[/]")
        
        # If score is high enough, return stage 1 result
        if stage1_score >= 90:
            return stage1_meta
        
        # Stage 2: SequentialThinking fallback
        if DEBUG:
            rprint("  [cyan]- Proceeding to SequentialThinking refinement[/]")
        
        stage2_context = f"""
        Previous refinement attempt scored {stage1_score}/100.
        This title may be a novella, anthology entry, or side story in an existing series.
        Consider alternative titles, series relationships, and publication formats.
        """
        
        stage2_prompt = textwrap.dedent(f"""
        Use advanced reasoning to refine this audiobook metadata.
        
        Folder: {folder_label}
        Title: "{title_guess}"
        Author: {best_author or 'Unknown'}
        Series: {series_guess or 'Unknown'}
        Series Index: {series_index_guess or 'Unknown'}
        
        Context: {stage2_context}
        
        Previous attempt found: {stage1_meta.get('title', 'Unknown')} by {stage1_meta.get('author', 'Unknown')}
        
        Apply sequential thinking to determine the most accurate metadata.
        Consider:
        - Series relationships and numbering
        - Alternative titles or translations
        - Publication format (novella, short story, anthology)
        - Author variations or pseudonyms
        
        Respond with JSON containing:
        - "title" (required)
        - "author" (required) 
        - "year" (optional)
        - "series" (optional)
        - "series_index" (optional)
        - "narrator" (optional)
        - "language" (optional)
        - "description" (optional)
        - "publisher" (optional)
        - "score" (confidence 0-100, required)
        - "reasoning" (brief explanation, optional)
        
        Use null for unknown values. Respond with JSON only.
        """).strip()
        
        # Create tools list with only sequential_thinking
        sequential_tools = [
            {
                "type": "function",
                "function": {
                    "name": "sequential_thinking",
                    "description": "Advanced reasoning for complex metadata inference",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "context": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]
        
        stage2_raw = _call_llm(
            stage2_prompt,
            system_prompt=MCP_SYSTEM_PROMPT,
            tools=sequential_tools,
            max_tokens=1024,
        )
        
        if stage2_raw is None:
            if DEBUG:
                rprint("  [yellow]- Stage 2 SequentialThinking failed[/]")
            return stage1_meta  # Return stage 1 result as fallback
        
        stage2_meta = parse_mcp_response(stage2_raw)
        if not stage2_meta:
            if DEBUG:
                rprint("  [yellow]- Stage 2 response invalid[/]")
            return stage1_meta  # Return stage 1 result as fallback
        
        # Calculate combined score for stage 2
        stage2_score = calculate_combined_score(stage2_meta, folder_label, title_guess, author_guess)
        stage2_meta["refinement_source"] = "sequentialthinking_refinement"
        
        if DEBUG:
            rprint(f"  [cyan]- Stage 2 refinement score: {stage2_score}[/]")
        
        # Return the better of the two results
        if stage2_score >= stage1_score:
            return stage2_meta
        else:
            return stage1_meta
            
    except Exception as exc:
        if DEBUG:
            rprint(f"  [yellow]- MCP refinement error: {exc}[/]")
        review_log(folder, f"mcp_refinement_failed: {type(exc).__name__}")
        return None
def strip_tags(file: Path):
    audio = MFile(str(file))
    if audio:
        audio.delete(); audio.save()
def write_tags(file: Path, meta: dict, index: int = 0, total: int = 0):
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
        if meta["year"]:
            audio["TDRC"] = TDRC(3, meta["year"])
        if meta.get("series"):
            audio.add(TXXX(3, desc="series", text=meta["series"]))
        if index:
            audio["TRCK"] = TRCK(3, f"{index}/{total or index}")
        audio.save(str(file))
    elif ext in {".m4a", ".m4b"}:
        mp4 = MP4(str(file))
        mp4.clear()
        mp4["\u00a9nam"] = meta["title"]
        mp4["\u00a9alb"] = meta["title"]
        mp4["\u00a9ART"] = meta["author"]
        if meta["year"]:
            mp4["\u00a9day"] = meta["year"]
        if meta.get("series"):
            mp4["----:com.apple.iTunes:series"] = [meta["series"].encode("utf-8")]
        if index:
            mp4["trkn"] = [(index, total or 0)]
        mp4.save()
def export_metadata(path: Path, meta: dict):
    target = path if path.is_dir() else path.parent
    target.mkdir(exist_ok=True)
    with (target / "metadata.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    root = ET.Element("audiobook")
    for k, v in meta.items():
        if v:
            child = ET.SubElement(root, k)
            child.text = v
    ET.ElementTree(root).write(target / "book.nfo", encoding="utf-8", xml_declaration=True)
# ----- process one leaf -----
def process_leaf(path: Path, args):
    try:
        llm_threshold = int(getattr(args, "llm_threshold", 85))
    except (TypeError, ValueError):
        llm_threshold = 85
    llm_threshold = max(80, min(100, llm_threshold))
    setattr(args, "llm_threshold", llm_threshold)
    # skip Unknown Author
    if path.name == "Unknown Author" or path.parent.name == "Unknown Author":
        rprint("- skip Unknown Author:", path)
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
        rprint(f"[cyan]->[/] {path}  [green]tags stripped ({ok}/{len(targets)})[/]")
        log("STRIP", f"{path}  ({ok}/{len(targets)})")
        return
    # guess
    a_guess, t_guess, y_guess, s_guess, si_guess = guess_from_path(path)
    rprint(f"[cyan]->[/] {path}")
    rprint(f"  guess: [italic]{t_guess}[/] by {a_guess or '?'} ({y_guess or '?'})")
    if s_guess:
        rprint(f"  series: {s_guess} #{si_guess or '?'}")
    if path.is_file():
        targets = [path] if path.suffix.lower() in AUDIO_EXTS else []
    else:
        targets = sorted(
            [f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXTS]
        )
    if not targets:
        rprint("  [yellow]- no audio files found[/]")
        log("SKIP", f"{path}  no_audio")
        return
    folder = path if path.is_dir() else path.parent
    guess_info = {
        "path": str(path),
        "title": t_guess,
        "author": a_guess,
        "year": y_guess,
        "series": s_guess,
        "series_index": si_guess,
    }

    result, scores = best_match(a_guess, t_guess, s_guess, si_guess)
    provider_scores = {name: sc for name, (sc, _) in scores.items()} if scores else {}
    llm_used = False
    refinement_source = None
    best_score: Optional[int] = None
    
    if not result:
        rprint("  [red] - no match[/]")
        # Try MCP refinement first if enabled
        if AB.is_on("use_mcp_refinement"):
            rprint("  [cyan]- attempting MCP refinement[/]")
            mcp_meta = refine_metadata_via_mcp(folder, a_guess, t_guess, s_guess, si_guess, 0)
            if mcp_meta and mcp_meta.get("score", 0) >= 95:
                rprint(f"  [magenta]- metadata refined via MCP (score: {mcp_meta['score']})[/]")
                meta = mcp_meta
                llm_used = True
                refinement_source = mcp_meta.get("refinement_source", "mcp_refinement")
            else:
                # Fallback to original LLM
                llm_meta = generate_metadata_via_llm(
                    folder,
                    targets,
                    guess=guess_info,
                    provider_scores=provider_scores,
                )
                if llm_meta:
                    rprint("  [magenta]- metadata supplied by local LLM[/]")
                    meta = llm_meta
                    llm_used = True
                else:
                    log("NOMATCH", str(path))
                    review_log(path, "no_match")
                    return
        else:
            # Original LLM fallback
            llm_meta = generate_metadata_via_llm(
                folder,
                targets,
                guess=guess_info,
                provider_scores=provider_scores,
            )
            if llm_meta:
                rprint("  [magenta]- metadata supplied by local LLM[/]")
                meta = llm_meta
                llm_used = True
            else:
                log("NOMATCH", str(path))
                review_log(path, "no_match")
                return
    else:
        score, hit = result
        best_score = score
        for name, (sc, _) in sorted(scores.items(), key=lambda x: -x[1][0]):
            rprint(f"    {name}: {sc}")
        author_hit = ", ".join(hit["authors"]) or a_guess or "Unknown"
        rprint(f"  match: [bold]{hit['title']}[/] by {author_hit} ({hit['year'] or '?'})")
        if hit.get("series"):
            rprint(f"  series: {hit['series']}")
        rprint(f"  provider: {hit['source']}")
        if score < 60:
            rprint("  [yellow]!! low confidence - double-check[/]")
        meta = {
            "title": hit["title"],
            "author": author_hit,
            "year": hit["year"],
            "series": hit.get("series") or s_guess,
            "series_index": hit.get("series_index") or si_guess,
        }
        if best_score is not None and best_score < llm_threshold:
            # Try MCP refinement first if enabled and score is low
            if AB.is_on("use_mcp_refinement") and best_score < 90:
                rprint("  [cyan]- attempting MCP refinement (low score)[/]")
                mcp_meta = refine_metadata_via_mcp(folder, a_guess, t_guess, s_guess, si_guess, best_score or 0, meta)
                if mcp_meta and mcp_meta.get("score", 0) >= 95:
                    rprint(f"  [magenta]- metadata refined via MCP (score: {mcp_meta['score']})[/]")
                    meta = mcp_meta
                    llm_used = True
                    refinement_source = mcp_meta.get("refinement_source", "mcp_refinement")
                else:
                    # Fallback to original LLM
                    llm_meta = generate_metadata_via_llm(
                        folder,
                        targets,
                        guess=guess_info,
                        provider_scores=provider_scores,
                    )
                    if llm_meta:
                        rprint(
                            f"  [magenta]- metadata supplied by local LLM (score {best_score} < {llm_threshold})[/]"
                        )
                        meta = llm_meta
                        llm_used = True
            else:
                # Original LLM fallback
                llm_meta = generate_metadata_via_llm(
                    folder,
                    targets,
                    guess=guess_info,
                    provider_scores=provider_scores,
                )
                if llm_meta:
                    rprint(
                        f"  [magenta]- metadata supplied by local LLM (score {best_score} < {llm_threshold})[/]"
                    )
                    meta = llm_meta
                    llm_used = True
        if not llm_used and best_score is not None and best_score < 70 and not args.yes:
            score_val = f"{best_score:.1f}" if isinstance(best_score, float) else str(best_score)
            summary_lines = [
                "Tag with this metadata?",
                "",
                f"Title   : {meta.get('title') or 'Unknown'}",
                f"Author  : {meta.get('author') or 'Unknown'}",
            ]
            if meta.get("series"):
                summary_lines.append(f"Series  : {meta['series']}")
            if meta.get("year"):
                summary_lines.append(f"Year    : {meta['year']}")
            summary_lines.append(f"Provider: {hit.get('source', '?')}")
            summary_lines.append(f"Score   : {score_val} (threshold {llm_threshold})")
            summary_lines.append(f"Path    : {path}")
            prompt_message = "\n".join(summary_lines)
            if args.no:
                proceed = False
            elif hasattr(Confirm, "ask"):
                proceed = Confirm.ask(prompt_message, default=False)
            else:
                proceed = Confirm(prompt_message, default=False)
            if not proceed:
                log("SKIP", str(path))
                review_log(path, "user_skip")
                return
    valid, validation_issues = validate_metadata_fields(meta)
    if not valid:
        issues_text = ", ".join(validation_issues)
        rprint(f"  [yellow]- metadata validation failed: {issues_text}")
        validation_refined = False
        if AB.is_on("use_mcp_refinement") and not llm_used:
            rprint("  [cyan]- attempting MCP refinement (validation)")
            initial_score = best_score if best_score is not None else meta.get("score", 0) or 0
            mcp_meta = refine_metadata_via_mcp(
                folder,
                a_guess,
                t_guess,
                s_guess,
                si_guess,
                initial_score,
                meta,
            )
            if mcp_meta:
                meta = mcp_meta
                llm_used = True
                refinement_source = mcp_meta.get("refinement_source", "mcp_refinement")
                validation_refined = True
                valid, validation_issues = validate_metadata_fields(meta)
        if not valid:
            issues_text = ", ".join(validation_issues)
            rprint("  [red]- validation failed; book queued for review")
            log("REVIEW", f"{path} validation_failed: {issues_text}")
            review_log(path, "validation_failed")
            return
        if validation_refined:
            rprint("  [magenta]- metadata passed validation after refinement[/]")

    ok = 0
    for idx, f in enumerate(targets, 1):
        try:
            write_tags(f, meta, idx, len(targets)); ok += 1
        except (MutagenError, MP4StreamInfoError):
            log("ERR", f"tag {f}")
    label = "OK" if ok == len(targets) else "ERR"
    rprint(f"  [green]tagged {ok}/{len(targets)} file(s)[/]")
    
    # Enhanced logging with refinement source and score
    suffix_parts = []
    if llm_used:
        if refinement_source:
            suffix_parts.append(f"[MCP-{refinement_source}]")
        else:
            suffix_parts.append("[LLM]")
    
    # Add score information if available
    if meta.get("score"):
        score_info = f"score={meta['score']}"
        if meta.get("series_index"):
            score_info += f" series={meta['series_index']}"
        suffix_parts.append(f"[{score_info}]")
    
    suffix = " " + " ".join(suffix_parts) if suffix_parts else ""
    meta_summary = format_metadata_summary(meta)
    log(label, f"{path}  ({ok}/{len(targets)}){suffix} | {meta_summary}")
    
    if label == "OK":
        export_metadata(path, meta)
# ----- leaf finder -----
def walk_leaves(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    leaves: List[Path] = []
    for p in root.rglob("*"):
        if p.is_dir() and has_audio(p) and not any(
            c.is_dir() and has_audio(c) for c in p.iterdir()):
            leaves.append(p)
    return leaves
# ----- cli / main -----
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
              --no          auto-decline matches (tag mode)
              --striptags   delete *all* tags instead of adding
              --llm-endpoint URL   OpenAI-compatible endpoint (default: http://127.0.0.1:1234/v1/chat/completions)
              --llm-model NAME     model to request from the endpoint (default: mistral-7b-instruct-q4)
             --llm-threshold SCORE  confidence score before using the LLM (default: 85)
              --tavily-key KEY     Tavily Search API key for supplemental research
            """))
    ap.add_argument("root", type=Path, help="file or folder")
    ap.add_argument("--debug", action="store_true",
                    help="print full tracebacks on errors")
    ap.add_argument("--recurse",   action="store_true")
    ap.add_argument("--commit",    action="store_true")
    ap.add_argument("--yes",       action="store_true")
    ap.add_argument("--no",        action="store_true")
    ap.add_argument("--striptags", action="store_true")
    ap.add_argument("--llm-endpoint", default="http://127.0.0.1:8888/v1/chat/completions",
                    help="OpenAI-compatible completion endpoint (use 'none' to disable; default: %(default)s)")
    ap.add_argument("--llm-model", default="mistral-7b-instruct-q4",
                    help="Model name to request from the LM Studio endpoint (default: %(default)s)")
    ap.add_argument("--llm-threshold", type=int, default=85, metavar="SCORE",
                    help="use the local LLM when provider score falls below SCORE (default: 85, minimum: 80)")
    ap.add_argument("--tavily-key", default=None,
                    help="Tavily Search API key for supplemental research (use 'none' to disable)")
    args = ap.parse_args()
    global LOG_PATH, REVIEW_PATH, DEBUG, LLM_ENDPOINT, LLM_MODEL_NAME
    global TAVILY_API_KEY
    DEBUG = args.debug
    base = args.root if args.root.is_dir() else args.root.parent
    LOG_PATH = base / "tag_log.txt"
    REVIEW_PATH = base / "review_log.txt"
    endpoint_arg = (args.llm_endpoint or "").strip()
    if endpoint_arg.lower() in {"", "none", "null"}:
        LLM_ENDPOINT = None
    else:
        LLM_ENDPOINT = endpoint_arg
    model_arg = (args.llm_model or "").strip()
    LLM_MODEL_NAME = model_arg or None
    if args.tavily_key is not None:
        tavily_arg = args.tavily_key.strip()
        if tavily_arg.lower() in {"", "none", "null"}:
            TAVILY_API_KEY = None
        else:
            TAVILY_API_KEY = tavily_arg
    args.llm_threshold = max(80, min(100, args.llm_threshold))
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
            rprint(f"[red]ERR:[/] {leaf} - {e}")
            if DEBUG:
                import traceback
                tb = traceback.format_exc()
                rprint(tb)
                log("ERR", f"{leaf} - {type(e).__name__}: {tb.strip()}")
            else:
                log("ERR", f"{leaf} - {type(e).__name__}")
if __name__ == "__main__":
    main()
