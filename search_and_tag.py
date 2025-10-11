#!/usr/bin/env python3
"""
ABtools/search_and_tag.py – v2.30  (2025-09-12)
Tag (or strip) audiobook files using multiple metadata providers.

    The script queries Audible, Open Library, Google Books and Goodreads
    via dedicated MCP provider tools (e.g. ``search_audible_tool`` and
    ``search_google_books_tool``). Results are parsed and ranked using
    fuzzy title *and author* matching.
    Low scoring hits will prompt for confirmation unless you run with
    ``--yes``. Use ``--no`` to automatically decline low-scoring matches.
    When prompted, the default answer is "No" so low confidence matches
    won't be accepted accidentally. Log files are written next to the
    chosen root as ``tag_log.txt`` and ``review_log.txt``. Use
    ``--version`` to print the script version and file location.

Supply ``--llm-endpoint``/``--llm-model`` to let a local LM Studio
instance (tested with Mistral-7B Q4 on port 1234) suggest metadata when
online providers fail or return low scores. Adjust the trigger with
``--llm-threshold`` (default: 75). When the fallback is used the script
shares folder context and file names with the model and expects JSON
metadata in return; no local transcription step is required anymore.
"""

from __future__ import annotations
import argparse, datetime, os, re, sys, textwrap
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from uuid import uuid4
from abclient import AbClient
from dataclasses import dataclass

VERSION = "2.30"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

DEBUG = False
AB = AbClient()

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
SESSION = requests.Session()
from rapidfuzz import fuzz
import json
import xml.etree.ElementTree as ET
from mutagen import File as MFile, MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TALB, TPE1, TDRC, TXXX, TRCK
from mutagen.mp4 import MP4, MP4StreamInfoError
from bs4 import BeautifulSoup

from mcp_server.tools.audible import search_audible as mcp_search_audible
from mcp_server.tools.goodreads import search_goodreads as mcp_search_goodreads
from mcp_server.tools.googlebooks import (
    search_google_books as mcp_search_google_books,
)
from mcp_server.tools.openlibrary import search_openlibrary as mcp_search_openlibrary

# â”€â”€â”€â”€â”€ colour (rich) or plain text â”€â”€â”€â”€â”€
try:
    from rich import print as rprint
    from rich.prompt import Confirm
except ImportError:  # plain console, strip tags like [bold]…[/]
    _TAGS = re.compile(r"\[/-[a-zA-Z].*-]")
    def rprint(*a, **k): print(_TAGS.sub("", " ".join(map(str, a))), **k)
    def Confirm(prompt: str, default=False):
        ans = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").lower().strip()
        return default if ans == "" else ans in {"y", "yes"}

# â”€â”€â”€â”€â”€ constants â”€â”€â”€â”€â”€
AUDIO_EXTS = {".mp3", ".m4a", ".m4b"}
TAIL_RX    = re.compile(r"(-:\{[^}]*\})-(-:\s*\d+\.\d{2}\.\d{2})-(-:\s*\d+\s*[kK])-\s*$")
PAREN_RX   = re.compile(r"\([^)]*\)")
YEAR_RX    = re.compile(r"^(\d{4})\s*[-_]\s*")
LOG_PATH   = Path("tag_log.txt")
REVIEW_PATH = Path("review_log.txt")

LLM_ENDPOINT: Optional[str] = "http://127.0.0.1:1234/v1/chat/completions"
LLM_MODEL_NAME: Optional[str] = "llama-3-8b-instruct-abliterated-v2"
LLM_TIMEOUT: int = 90
LLM_MAX_TOKENS: int = 8000
DUCKDUCKGO_SEARCH_URL: str = "https://html.duckduckgo.com/html/"
REFINEMENT_TRIGGER: int = 90
LLM_SYSTEM_PROMPT = (
    "You analyse audiobook folders and files, respond with JSON metadata only."
)

METADATA_REFINER_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are the “Metadata Refiner” for an audiobook tagging pipeline.
    Merge fuzzy provider matches with new research by calling the available MCP tools
    (`search_audible_tool`, `search_goodreads_tool`, `search_google_books_tool`,
    `search_openlibrary_tool`, `search`, and `fetch_content`). Use them to confirm
    title, author, year, narrator, series, description, and publisher details.
    Return a single JSON object with the audiobook metadata. Use `null` when a field
    cannot be determined. Do not include explanatory text outside the JSON object.
    """
).strip()

SEQUENTIAL_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are the “Heuristic Tag Synthesizer” stage. When provider matches remain weak,
    plan reasoning steps with the `sequentialthinking` tool and consult MCP search
    tools to resolve conflicts. Produce a single high-confidence JSON metadata object
    (title, author, optional series, series_index, year, narrator, language, publisher,
    description, confidence). Supply `null` for unknown fields and avoid extra prose.
    """
).strip()

VERIFIER_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are the “Tag Evaluator”. Inspect the supplied audiobook metadata JSON and
    report whether it is internally consistent with the evidence provided. Respond
    with JSON containing at least:
      - "confidence": integer 0-100 reflecting how reliable the metadata is.
      - "notes": optional short justification for the confidence score.
    Do not modify the source metadata, only evaluate it. No additional commentary.
    """
).strip()

COMMON_PROVIDER_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_audible_tool",
            "description": "Scrape Audible search results for matching audiobooks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_goodreads_tool",
            "description": "Scrape Goodreads search results for matching books.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_google_books_tool",
            "description": "Query the Google Books API for matching volumes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_openlibrary_tool",
            "description": "Search OpenLibrary for matching works.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Run a general web search via the MCP server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_content",
            "description": "Fetch full page content for a given URL via the MCP server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
]

METADATA_REFINER_TOOLS: list[dict[str, Any]] = list(COMMON_PROVIDER_TOOLS)

SEQUENTIAL_TOOLS: list[dict[str, Any]] = METADATA_REFINER_TOOLS + [
    {
        "type": "function",
        "function": {
            "name": "sequentialthinking",
            "description": "Plan reasoning steps before producing final metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                },
                "required": ["task"],
            },
        },
    },
]


def _call_llm(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    tools: Optional[list[dict[str, Any]]] = None,
    max_tokens: int | None = None,
) -> Optional[str]:
    if not LLM_ENDPOINT or not LLM_MODEL_NAME:
        return None
    token_budget = max_tokens or LLM_MAX_TOKENS
    sys_prompt = system_prompt or LLM_SYSTEM_PROMPT
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ]
    attempt = 0
    tool_rounds = 0

    while tool_rounds < 4:
        payload: Dict[str, Any] = {
            "model": LLM_MODEL_NAME,
            "messages": messages,
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
        message = first_choice.get("message") if isinstance(first_choice, dict) else None
        if not isinstance(message, dict):
            return None

        tool_calls = message.get("tool_calls") or []
        content = message.get("content") or ""
        finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else None

        if tool_calls:
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)
            for tool_call in tool_calls:
                tool_result = _execute_tool_call(tool_call)
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id") or str(uuid4()),
                    "content": tool_result,
                }
                function_meta = tool_call.get("function")
                if isinstance(function_meta, dict) and function_meta.get("name"):
                    tool_message["name"] = function_meta["name"]
                messages.append(tool_message)
            tool_rounds += 1
            continue

        if content.strip():
            return str(content)

        if finish_reason == "length" and attempt == 0:
            token_budget = min(token_budget * 2, 2048)
            attempt += 1
            if DEBUG:
                rprint(
                    f"  [yellow]- LM Studio response hit max_tokens; retrying with {token_budget}[/]"
                )
            continue
        return None
    return None

def _fetch_url(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
) -> Optional[str]:
    try:
        resp = SESSION.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    return resp.text


def _coerce_limit(raw_value: Any, *, default: int = 10) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, 20))


def _format_tool_response(
    query: str,
    source: str,
    payload: Any,
    *,
    limit: int,
) -> Dict[str, Any]:
    if isinstance(payload, dict) and payload.get("error"):
        return {
            "query": query,
            "source": source,
            "results": [],
            "error": str(payload.get("error")),
        }
    if not isinstance(payload, list):
        return {"query": query, "source": source, "results": []}
    trimmed = payload[:limit] if limit else payload
    return {"query": query, "source": source, "results": trimmed}


def _tool_search_audible(arguments: Dict[str, Any]) -> Dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return {"error": "missing query"}
    limit = _coerce_limit(arguments.get("limit"), default=10)
    data = mcp_search_audible(query)
    return _format_tool_response(query, "audible", data, limit=limit)


def _tool_search_goodreads(arguments: Dict[str, Any]) -> Dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return {"error": "missing query"}
    limit = _coerce_limit(arguments.get("limit"), default=10)
    data = mcp_search_goodreads(query)
    return _format_tool_response(query, "goodreads", data, limit=limit)


def _tool_search_google_books(arguments: Dict[str, Any]) -> Dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return {"error": "missing query"}
    limit = _coerce_limit(arguments.get("limit"), default=10)
    data = mcp_search_google_books(query)
    return _format_tool_response(query, "google_books", data, limit=limit)


def _tool_search_openlibrary(arguments: Dict[str, Any]) -> Dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return {"error": "missing query"}
    limit = _coerce_limit(arguments.get("limit"), default=10)
    data = mcp_search_openlibrary(query)
    return _format_tool_response(query, "openlibrary", data, limit=limit)


def _duckduckgo_search(
    query: str,
    *,
    max_results: int = 5,
) -> Optional[List[Dict[str, str]]]:
    payload = {"q": query}
    try:
        resp = SESSION.post(
            DUCKDUCKGO_SEARCH_URL,
            data=payload,
            timeout=LLM_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except requests.RequestException:
        return None
    if resp.status_code >= 400:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[Dict[str, str]] = []
    for block in soup.select("div.result"):
        link = block.select_one("a.result__a")
        if not link or not link.get("href"):
            continue
        title = link.get_text(" ", strip=True)
        url = link.get("href")
        snippet_elem = block.select_one("a.result__snippet") or block.select_one(
            "div.result__snippet"
        )
        snippet = snippet_elem.get_text(" ", strip=True) if snippet_elem else ""
        results.append(
            {
                "id": str(uuid4()),
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )
        if len(results) >= max_results:
            break
    return results or None


def _execute_tool_call(tool_call: Dict[str, Any]) -> str:
    function_meta = tool_call.get("function")
    name = None
    arguments_raw: Any = {}
    if isinstance(function_meta, dict):
        name = function_meta.get("name")
        arguments_raw = function_meta.get("arguments", {})
    try:
        if isinstance(arguments_raw, str):
            arguments = json.loads(arguments_raw)
        elif isinstance(arguments_raw, dict):
            arguments = arguments_raw
            arguments = {}
    except json.JSONDecodeError:
        arguments = {}
    handlers = {
        "search_audible_tool": _tool_search_audible,
        "search_goodreads_tool": _tool_search_goodreads,
        "search_google_books_tool": _tool_search_google_books,
        "search_openlibrary_tool": _tool_search_openlibrary,
    }
    handler = handlers.get(name)
    if handler is None:
        result: Any = {"error": f"unsupported_tool:{name or 'unknown'}"}
    else:
        try:
            result = handler(arguments if isinstance(arguments, dict) else {})
        except Exception as exc:  # pragma: no cover - defensive
            if DEBUG:
                rprint(f"  [yellow]- tool '{name}' failed: {exc}[/]")
            result = {"error": f"tool_failed:{name}", "detail": str(exc)}
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return json.dumps({"result": str(result)})


def log(status: str, message: str):
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%F %T}  {status:<7}  {message}\n")

def review_log(path: Path, reason: str):
    REVIEW_PATH.parent.mkdir(exist_ok=True)
    with REVIEW_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%F %T}  {reason:<9}  {path}\n")

# â”€â”€â”€â”€â”€ tiny helpers â”€â”€â”€â”€â”€
def clean_tail(s: str) -> str:
    return TAIL_RX.sub("", s).strip()

def has_audio(folder: Path) -> bool:
    return any(c.suffix.lower() in AUDIO_EXTS for c in folder.iterdir())

# â”€â”€â”€â”€â”€ filename guess â”€â”€â”€â”€â”€
def guess_from_path(p: Path) -> Tuple[Optional[str], str, Optional[str]]:
    """Return (author, title, year).  Author may be None."""
    leaf = clean_tail(p.stem if p.is_file() else p.name)
    year = None
    if (m := YEAR_RX.match(leaf)):
        year, leaf = m.group(1), leaf[m.end():].lstrip(" -_")
    parts = [x.strip() for x in leaf.split(" - ")]
    if parts and re.fullmatch(r"\d+", parts[0]):
        parts = parts[1:]
    if parts and re.fullmatch(r"\d{4}", parts[-1]) and year is None:
        year = parts.pop()
    if len(parts) >= 2:
        title = " - ".join(parts[:-1])
        author = parts[-1] if " " in parts[-1] else None
    else:
        title, author = leaf, None
    if not author:
        parent = clean_tail(p.parent.name)
        author = parent if " " in parent else None
    title = PAREN_RX.sub("", title).strip()
    return author, title, year

# â”€â”€â”€â”€â”€ online lookup helpers â”€â”€â”€â”€â”€
def openlib(author: Optional[str], title: str) -> Optional[dict]:
    try:
        q = f"title:{title}" + (f" author:{author}" if author else "")
        raw = _fetch_url(
            "https://openlibrary.org/search.json",
            params={"q": q, "limit": 5},
            timeout=15,
        )
        if not raw:
            return None
        data = json.loads(raw)
        docs = data.get("docs", [])
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
        raw = _fetch_url(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": q, "maxResults": 5},
            timeout=15,
        )
        if not raw:
            return None
        data = json.loads(raw)
        items = data.get("items", [])
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
        html = _fetch_url(
            "https://www.goodreads.com/search",
            params={"q": q},
            timeout=15,
        )
        if not html:
            return None
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
        html = _fetch_url(
            "https://www.audible.com/search",
            params={"keywords": q},
            headers={"User-Agent": "Mozilla/5.0 (compatible; ABtools/1.0)"},
            timeout=15,
        )
        if not html:
            return None
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

def best_match(author: Optional[str], title: str, client: AbClient = AB) -> tuple[Optional[tuple[int, dict]], dict[str, tuple[int, dict]]]:
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
            score = int(title_score * 0.7 + author_score * 0.3)
            meta["source"] = name
            pair = (score, meta)
            candidates.append(pair)
            results[name] = pair

    # audible first when enabled (internal switch)
    if client.is_on("audible_first", default=True, internal=True):
        add_result("audible", audible(author, title))
        if "audible" in results and results["audible"][0] >= 80:
            return results["audible"], results

    providers = [("openlib", openlib), ("gbooks", gbooks)]
    if client.is_on("use_goodreads"):
        providers.append(("goodreads", goodreads))

    with ThreadPoolExecutor(max_workers=len(providers)) as ex:
        future_map = {ex.submit(fn, author, title): name for name, fn in providers}
        for fut in as_completed(future_map):
            add_result(future_map[fut], fut.result())

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


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # remove optional language hint
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
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



def _generate_metadata_via_llm_impl(
    folder: Path,
    files: list[Path],
    *,
    force_duckduckgo: bool = False,
    existing_hint: Optional[dict] = None,
    mode: str = "standard",
) -> Optional[dict]:
    if not files:
        return None
    if not LLM_ENDPOINT or not LLM_MODEL_NAME:
        return None
    if mode not in {"standard", "sequential"}:
        raise ValueError(f"Unsupported LLM mode: {mode}")

    folder_label = folder.name or folder.stem or str(folder)
    role_label = "Metadata Refiner" if mode == "standard" else "Heuristic Tag Synthesizer"
    toolset = METADATA_REFINER_TOOLS if mode == "standard" else SEQUENTIAL_TOOLS
    system_prompt = METADATA_REFINER_SYSTEM_PROMPT if mode == "standard" else SEQUENTIAL_SYSTEM_PROMPT

    mode_label_parts = [role_label]
    if force_duckduckgo:
        mode_label_parts.append("DuckDuckGo assist")
    if mode == "sequential":
        mode_label_parts.append("sequential plan")
    rprint(
        f"  [cyan]LLM request for '{folder_label}': {len(files)} file(s) ({' + '.join(mode_label_parts)})[/]"
    )

    file_lines = "\n".join(f"- {f.name}" for f in files[:25])
    if len(files) > 25:
        file_lines += f"\n- ... (+{len(files) - 25} more)"

    stage_goal = (
        "Merge fuzzy provider matches with corroborating evidence into a single JSON metadata object."
        if mode == "standard"
        else "Resolve ambiguous fields through stepwise reasoning and deliver the most plausible JSON metadata."
    )

    base_prompt = textwrap.dedent(
        f"""
        You are the {role_label} stage of an audiobook tagging workflow.
        Folder name: {folder_label}
        Primary goal: {stage_goal}
        Total audio files: {len(files)}
        Audio files:
        {file_lines}

        Call MCP tools (`search_audible_tool`, `search_goodreads_tool`, `search_google_books_tool`,
        `search_openlibrary_tool`, `search`, `fetch_content`) whenever you need evidence. Respond with
        a single JSON object containing:
          - "title" (required)
          - "author" (required)
          - "series" (optional)
          - "series_index" (optional)
          - "year" (optional four digit year)
          - "narrator" (optional)
          - "language" (optional language code or name)
          - "description" (optional short summary)
          - "publisher" (optional)
          - "confidence" (optional 0-100 assessment of result quality)

        Use null when a value is unknown. Do not include commentary outside the JSON object.
        """
    ).strip()

    if existing_hint:
        hint_json = json.dumps(existing_hint, ensure_ascii=False, indent=2)
        base_prompt += (
            "\n\nExisting low-confidence metadata (validate, correct, and complete):\n"
            + hint_json
        )

    if mode == "sequential":
        base_prompt += (
            "\n\nBefore responding, invoke the `sequentialthinking` tool to outline reasoning steps, "
            "then execute the plan with the necessary search tools. Ensure the final JSON reflects the resolved evidence."
        )

    duck_context: Optional[str] = None
    if force_duckduckgo:
        query_terms: List[str] = [folder_label]
        query_terms.extend(sorted({f.stem for f in files[:5]}))
        query = " ".join(t for t in query_terms if t).strip()
        if query:
            hits = _duckduckgo_search(query, max_results=5)
            if hits:
                parts = []
                for idx, item in enumerate(hits, 1):
                    parts.append(
                        f"{idx}. {item.get('title','')}\n   {item.get('url','')}\n   {item.get('snippet','')}"
                    )
                duck_context = "\n".join(parts)
                if DEBUG:
                    rprint(f"  [cyan]DuckDuckGo context gathered for '{query}'[/]")

    prompt = base_prompt
    if duck_context:
        prompt += (
            "\n\nExternal research via DuckDuckGo Web Search:\n"
            + duck_context
            + "\nUse these findings to produce accurate JSON metadata."
        )

    allowed = {
        "title",
        "author",
        "authors",
        "series",
        "series_index",
        "year",
        "narrator",
        "language",
        "description",
        "publisher",
        "confidence",
    }

    optional_keys = {
        "series",
        "series_index",
        "year",
        "narrator",
        "language",
        "description",
        "publisher",
        "confidence",
    }

    def parse_llm_raw(raw: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
        if raw is None:
            return None
        cleaned = _strip_fence(raw)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            if DEBUG:
                rprint("  [yellow]LM Studio returned non-JSON metadata[/]")
            return None
        if not isinstance(payload, dict):
            return None

        meta: Dict[str, Optional[str]] = {}
        for key in allowed:
            if key in payload:
                meta[key] = _normalise_value(payload[key])

        authors_value = meta.pop("authors", None)
        if not meta.get("author") and authors_value:
            meta["author"] = authors_value

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
        for extra in ("narrator", "language", "description", "publisher", "confidence"):
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
        system_prompt=system_prompt,
        tools=toolset,
        max_tokens=1024,
    )
    if primary_raw is None:
        if DEBUG:
            rprint("  [yellow]LM Studio metadata request returned no content[/]")
        return None

    result = parse_llm_raw(primary_raw)
    missing_fields = missing_optional(result) if result else optional_keys

    if missing_fields:
        missing_list = ", ".join(sorted(missing_fields))
        if not duck_context:
            query_terms = []
            if result and result.get("title"):
                query_terms.append(str(result["title"]))
            else:
                query_terms.append(folder_label)
            if result and result.get("author"):
                query_terms.append(str(result["author"]))
            query = " ".join(t for t in query_terms if t).strip()
            if query:
                hits = _duckduckgo_search(query, max_results=5)
                if hits:
                    parts = []
                    for idx, item in enumerate(hits, 1):
                        parts.append(
                            f"{idx}. {item.get('title','')}\n   {item.get('url','')}\n   {item.get('snippet','')}"
                        )
                    duck_context = "\n".join(parts)
                    if DEBUG:
                        rprint(f"  [cyan]DuckDuckGo context fetched for '{query}'[/]")
        retry_prompt = (
            base_prompt
            + "\n\nThe previous response was missing these fields: "
            + missing_list
            + ". Please research reputable audiobook sources (Audible, Open Library, Google Books, publisher sites) and try again."
        )
        if duck_context:
            retry_prompt += (
                "\n\nAdditional DuckDuckGo results:\n"
                + duck_context
                + "\nUse this information to fill the missing metadata fields."
            )
            retry_prompt += "\n\nIf needed, consult the DuckDuckGo MCP tool when gathering details."
        if DEBUG:
            rprint(
                "  [cyan]- retrying LM Studio metadata request to fill: "
                + missing_list
                + "[/]"
            )
        retry_raw = _call_llm(
            retry_prompt,
            system_prompt=system_prompt,
            tools=toolset,
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
    return result


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
        mp4["Â©nam"] = meta["title"]
        mp4["Â©alb"] = meta["title"]
        mp4["Â©ART"] = meta["author"]
        if meta["year"]:
            mp4["Â©day"] = meta["year"]
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

# â”€â”€â”€â”€â”€ process one leaf â”€â”€â”€â”€â”€
def process_leaf(path: Path, args):
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
    a_guess, t_guess, y_guess = guess_from_path(path)
    rprint(f"[cyan]->[/] {path}")
    rprint(f"  guess: [italic]{t_guess}[/] by {a_guess or '-'} ({y_guess or '-'})")

    if path.is_file():
        targets = [path] if path.suffix.lower() in AUDIO_EXTS else []
    else:
        targets = sorted([f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXTS])
    if not targets:
        rprint("  [yellow]- no audio files found[/]")
        log("SKIP", f"{path}  no_audio")
        return

    folder = path if path.is_dir() else path.parent

    result, scores = best_match(a_guess, t_guess)
    refine_trigger = REFINEMENT_TRIGGER
    llm_used = False
    provider_source: Optional[str] = None
    provider_score: Optional[int] = None
    if not result:
        rprint("  [red] - no match[/]")
        rprint("  [cyan]No catalog hit; querying local LLM for metadata.[/]")
        llm_meta = generate_metadata_via_llm(folder, targets)
        if llm_meta is None:
            rprint("  [cyan]LLM response empty; retrying with DuckDuckGo context.[/]")
            llm_meta = generate_metadata_via_llm(folder, targets, force_duckduckgo=True)
        seq_meta = None
        if llm_meta is None:
            rprint("  [cyan]Invoking SequentialThinking refinement (no provider match).[/]")
            seq_meta = generate_metadata_via_llm(
                folder,
                targets,
                force_duckduckgo=True,
                mode="sequential",
            )
        else:
            rprint("  [cyan]SequentialThinking refining LLM metadata.[/]")
            seq_meta = generate_metadata_via_llm(
                folder,
                targets,
                force_duckduckgo=True,
                existing_hint=llm_meta,
                mode="sequential",
            )
        final_meta = seq_meta or llm_meta
        if not final_meta:
            log("NOMATCH", str(path))
            review_log(path, "no_match")
            return
        meta = final_meta
        llm_used = True
        provider_source = str(meta.get("source") or "").strip() or None
        provider_score_raw = meta.get("confidence") or meta.get("score")
        try:
            provider_score = int(float(provider_score_raw))
        except Exception:
            provider_score = None
    else:
        score, hit = result

        for name, (sc, _) in sorted(scores.items(), key=lambda x: -x[1][0]):
            rprint(f"  {name:>9}: {sc}")

        author_hit = ", ".join(hit["authors"]) or a_guess or "Unknown"
        rprint(
            f"  match: [bold]{hit['title']}[/] by {author_hit} ({hit['year'] or '-'})"
            f"  [score {score}]"
        )
        if hit.get("series"):
            rprint(f"  series: {hit['series']}")
        rprint(f"  provider: {hit['source']}")

        if score < 60:
            rprint("  [yellow]Low confidence - double-check[/]")

        meta = {
            "title": hit["title"],
            "author": author_hit,
            "year": hit["year"],
            "series": hit.get("series"),
        }
        if hit.get("source"):
            meta["source"] = hit["source"]
        provider_source = hit.get("source")
        provider_score = score
        if score < refine_trigger:
            rprint(f"  [cyan]Score {score} below threshold {refine_trigger}; querying local LLM.[/]")
            llm_meta = generate_metadata_via_llm(folder, targets)
            if llm_meta is None:
                rprint("  [cyan]LLM response empty; retrying with DuckDuckGo context.[/]")
                llm_meta = generate_metadata_via_llm(folder, targets, force_duckduckgo=True)
            seq_meta = None
            if llm_meta is None:
                rprint("  [cyan]SequentialThinking refining provider metadata.[/]")
                seq_meta = generate_metadata_via_llm(
                    folder,
                    targets,
                    force_duckduckgo=True,
                    existing_hint=meta,
                    mode="sequential",
                )
            else:
                rprint("  [cyan]SequentialThinking refining LLM metadata.[/]")
                seq_meta = generate_metadata_via_llm(
                    folder,
                    targets,
                    force_duckduckgo=True,
                    existing_hint=llm_meta,
                    mode="sequential",
                )
            final_meta = seq_meta or llm_meta
            if final_meta:
                rprint(
                    f"  [magenta]SequentialThinking/LLM chain supplied metadata (score {score} < {refine_trigger})[/]"
                )
                meta = final_meta
                llm_used = True
                provider_source = str(meta.get("source") or "").strip() or provider_source
                provider_score_raw = meta.get("confidence") or meta.get("score")
                try:
                    provider_score = int(float(provider_score_raw))
                except Exception:
                    pass

        if not llm_used and score < 70 and not args.yes:
            if args.no:
                proceed = False
            elif hasattr(Confirm, "ask"):
                proceed = Confirm.ask("  tag with this metadata-", default=False)
            else:
                proceed = Confirm("tag with this metadata-", default=False)
            if not proceed:
                log("SKIP", str(path))
                review_log(path, "user_skip")
                return

    ok = 0
    alternate_meta: Optional[dict] = None
    for idx, f in enumerate(targets, 1):
        try:
            write_tags(f, meta, idx, len(targets))
            ok += 1
        except (MutagenError, MP4StreamInfoError, ValueError) as exc:
            error_text = str(exc)
            if DEBUG:
                rprint(f"  [red]- failed to tag {f}: {exc}")
            if alternate_meta is None:
                rprint("  [cyan]Tag write failed; retrying with DuckDuckGo-assisted LLM metadata.[/]")
                alternate_meta = generate_metadata_via_llm(folder, targets, force_duckduckgo=True)
                if alternate_meta is None:
                    alternate_meta = generate_metadata_via_llm(
                        folder,
                        targets,
                        force_duckduckgo=True,
                        existing_hint=meta,
                        mode="sequential",
                    )
                if alternate_meta:
                    meta = alternate_meta
                    llm_used = True
                    provider_source = None
                    provider_score = None
                    try:
                        write_tags(f, meta, idx, len(targets))
                        ok += 1
                        continue
                    except (MutagenError, MP4StreamInfoError, ValueError) as inner_exc:
                        error_text = str(inner_exc)
                        if DEBUG:
                            rprint(f"  [red]- fallback tag attempt failed for {f}: {inner_exc}")
            log("ERR", f"tag {f}: {error_text}")

    verifier_confidence: Optional[int] = None
    verifier_notes: Optional[str] = None
    verifier_result = verify_metadata_via_llm(
        folder,
        targets,
        meta,
        provider_source=provider_source,
        provider_score=provider_score,
        stage="LLM" if llm_used else "provider",
    )
    if verifier_result:
        conf_val = verifier_result.get("confidence")
        if conf_val is not None:
            try:
                verifier_confidence = int(conf_val)
            except (TypeError, ValueError):
                pass
        notes_val = verifier_result.get("notes")
        if notes_val:
            verifier_notes = str(notes_val)
            if DEBUG:
                rprint(f"  [cyan]Tag Evaluator notes:[/] {verifier_notes}")
        if verifier_confidence is not None:
            meta["confidence"] = str(verifier_confidence)
            provider_score = verifier_confidence

    label = "OK" if ok == len(targets) else "ERR"
    rprint(f"  [green]tagged {ok}/{len(targets)} file(s)[/]")
    if llm_used:
        if provider_score is not None:
            suffix = f" [LLM {provider_score}]"
        else:
            suffix = " [LLM]"
    else:
        parts: List[str] = []
        source = provider_source or str(meta.get("source") or "").strip()
        if source:
            parts.append(source)
        if provider_score is not None:
            parts.append(str(provider_score))
        suffix = f" [{' '.join(parts)}]" if parts else ""
    log(label, f"{path}  ({ok}/{len(targets)}){suffix}")
    if label == "OK":
        export_metadata(path, meta)


def generate_metadata_via_llm(
    folder: Path,
    files: list[Path],
    *,
    force_duckduckgo: bool = False,
    existing_hint: Optional[dict] = None,
    mode: str = "standard",
) -> Optional[dict]:
    try:
        return _generate_metadata_via_llm_impl(
            folder,
            files,
            force_duckduckgo=force_duckduckgo,
            existing_hint=existing_hint,
            mode=mode,
        )
    except ValueError as exc:
        if DEBUG:
            import traceback

            tb = traceback.format_exc()
            rprint(
                f"  [yellow]LLM metadata request raised ValueError ({exc}); treating as no result.[/]"
            )
            rprint(tb)
        return None



def verify_metadata_via_llm(
    folder: Path,
    files: list[Path],
    meta: Dict[str, Optional[str]],
    *,
    provider_source: Optional[str] = None,
    provider_score: Optional[int] = None,
    stage: str = "",
) -> Optional[Dict[str, Any]]:
    """Invoke the Tag Evaluator stage to assign a confidence score."""
    if not meta or not LLM_ENDPOINT or not LLM_MODEL_NAME:
        return None

    folder_label = folder.name or folder.stem or str(folder)
    file_lines = "\\n".join(f"- {f.name}" for f in files[:15])
    if len(files) > 15:
        file_lines += f"\\n- ... (+{len(files) - 15} more)"

    meta_json = json.dumps(meta, ensure_ascii=False, indent=2)
    context_lines: List[str] = [f"Folder: {folder_label}"]
    if stage:
        context_lines.append(f"Stage: {stage}")
    if provider_source:
        context_lines.append(f"Provider source: {provider_source}")
    if provider_score is not None:
        context_lines.append(f"Provider score: {provider_score}")
    context_lines.append("Audio files:")
    context_lines.append(file_lines or "- (none listed)")

    prompt = textwrap.dedent(
        """
        Evaluate the following audiobook metadata JSON. Confirm it is internally consistent
        and aligns with the supplied context. Respond with JSON only, containing:
          - "confidence": integer 0-100 representing metadata reliability.
          - "notes": optional brief justification (<=50 words).
        """
    ).strip()
    prompt += "\\n\\nContext:\\n" + "\\n".join(context_lines)
    prompt += "\\n\\nMetadata JSON to review:\\n```json\\n" + meta_json + "\\n```"

    raw = _call_llm(
        prompt,
        system_prompt=VERIFIER_SYSTEM_PROMPT,
        max_tokens=512,
    )
    if raw is None:
        return None

    try:
        payload = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        if DEBUG:
            rprint("  [yellow]Tag Evaluator returned non-JSON data[/]")
        return None
    if not isinstance(payload, dict):
        return None

    result: Dict[str, Any] = {}
    if "confidence" in payload:
        conf_value = _normalise_value(payload["confidence"])
        if conf_value is not None:
            try:
                result["confidence"] = int(round(float(conf_value)))
            except (TypeError, ValueError):
                pass
    if payload.get("notes"):
        note_value = _normalise_value(payload["notes"])
        if note_value:
            result["notes"] = note_value
    return result or None

# â”€â”€â”€â”€â”€ leaf finder â”€â”€â”€â”€â”€
def walk_leaves(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    leaves: List[Path] = []
    for p in root.rglob("*"):
        if p.is_dir() and has_audio(p) and not any(
            c.is_dir() and has_audio(c) for c in p.iterdir()):
            leaves.append(p)
    return leaves

# â”€â”€â”€â”€â”€ cli / main â”€â”€â”€â”€â”€
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
              --llm-threshold SCORE  confidence score before using the LLM (default: 75)
            """))

    ap.add_argument("root", type=Path, help="file or folder")
    ap.add_argument("--debug", action="store_true",
                    help="print full tracebacks on errors")
    ap.add_argument("--recurse",   action="store_true")
    ap.add_argument("--commit",    action="store_true")
    ap.add_argument("--yes",       action="store_true")
    ap.add_argument("--no",        action="store_true")
    ap.add_argument("--striptags", action="store_true")
    ap.add_argument("--llm-endpoint", default="http://127.0.0.1:1234/v1/chat/completions",
                    help="OpenAI-compatible completion endpoint (use 'none' to disable; default: %(default)s)")
    ap.add_argument("--llm-model", default="mistral-7b-instruct-q4",
                    help="Model name to request from the LM Studio endpoint (default: %(default)s)")
    ap.add_argument("--llm-threshold", type=int, default=75, metavar="SCORE",
                    help="use the local LLM when provider score falls below SCORE (default: 75)")
    args = ap.parse_args()

    global LOG_PATH, REVIEW_PATH, DEBUG, LLM_ENDPOINT, LLM_MODEL_NAME
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


    args.llm_threshold = max(0, min(100, args.llm_threshold))

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
            rprint(f"[red]ERR:[/] {leaf} â€“ {e}")
            if DEBUG:
                import traceback
                tb = traceback.format_exc()
                rprint(tb)
                log("ERR", f"{leaf} â€“ {type(e).__name__}: {tb.strip()}")
            else:
                log("ERR", f"{leaf} â€“ {type(e).__name__}")

if __name__ == "__main__":
    main()
















