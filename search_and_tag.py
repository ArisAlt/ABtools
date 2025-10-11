#!/usr/bin/env python3
"""
ABtools/search_and_tag.py ΓÇô v2.30  (2025-09-12)
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
``--llm-threshold`` (default: 75). When the fallback is used the script
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
from concurrent.futures import ThreadPoolExecutor, as_completed
SESSION = requests.Session()
from rapidfuzz import fuzz
import json
import xml.etree.ElementTree as ET
from mutagen import File as MFile, MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TALB, TPE1, TDRC, TXXX, TRCK
from mutagen.mp4 import MP4, MP4StreamInfoError

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ colour (rich) or plain text ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
try:
    from rich import print as rprint
    from rich.prompt import Confirm
except ImportError:  # plain console, strip tags like [bold]ΓÇª[/]
    _TAGS = re.compile(r"\[/?[a-zA-Z].*?]")
    def rprint(*a, **k): print(_TAGS.sub("", " ".join(map(str, a))), **k)
    def Confirm(prompt: str, default=False):
        ans = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").lower().strip()
        return default if ans == "" else ans in {"y", "yes"}

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ constants ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
AUDIO_EXTS = {".mp3", ".m4a", ".m4b"}
TAIL_RX    = re.compile(r"(?:\{[^}]*\})?(?:\s*\d+\.\d{2}\.\d{2})?(?:\s*\d+\s*[kK])?\s*$")
PAREN_RX   = re.compile(r"\([^)]*\)")
YEAR_RX    = re.compile(r"^(\d{4})\s*[-_]\s*")
LOG_PATH   = Path("tag_log.txt")
REVIEW_PATH = Path("review_log.txt")

LLM_ENDPOINT: Optional[str] = "http://127.0.0.1:1234/v1/chat/completions"
LLM_MODEL_NAME: Optional[str] = "llama-3-8b-instruct-abliterated-v2"
LLM_TIMEOUT: int = 90
LLM_MAX_TOKENS: int = 8000
TAVILY_API_KEY: Optional[str] = os.environ.get("TAVILY_API_KEY")
TAVILY_ENDPOINT: str = os.environ.get("TAVILY_ENDPOINT", "https://api.tavily.com/search")
LLM_SYSTEM_PROMPT = (
    "You analyse audiobook folders and files, respond with JSON metadata only."
)

MCP_SYSTEM_PROMPT = textwrap.dedent(
    """
    You route audiobook metadata lookups through the LM Studio MCP server.
    Always satisfy user requests by calling the `full_web_search` tool with
    an appropriate `site:` filter, then follow up with MCP summaries or page
    fetches if needed. When you finish researching, respond with a single
    JSON object describing the audiobook (title, authors[], year, series,
    series_index, narrator, publisher, description).
    """
).strip()

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "full_web_search",
            "description": "Run a web search via the LM Studio MCP server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer", "default": 5},
                    "include_content": {"type": "boolean", "default": False},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_web_search_summaries",
            "description": "Fetch summaries for prior MCP search results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["ids"],
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
    payload = {
        "model": LLM_MODEL_NAME,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
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
            rprint(f"  [yellow]ΓÇó LM Studio request failed: {exc}[/]")
        return None

    if resp.status_code >= 400:
        if DEBUG:
            rprint(
                f"  [yellow]ΓÇó LM Studio returned HTTP {resp.status_code}: {resp.text[:200]}[/]"
            )
        return None

    try:
        data = resp.json()
    except ValueError:
        if DEBUG:
            rprint("  [yellow]ΓÇó LM Studio response was not valid JSON[/]")
        return None

    choices = data.get("choices")
    if not choices:
        return None
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message") if isinstance(first_choice, dict) else None
    if not message:
        return None
    content = message.get("content") if isinstance(message, dict) else None
    if not content:
        return None
    finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else None
    if finish_reason == "length" and attempt == 0:
        new_budget = min(token_budget * 2, 2048)
        if DEBUG:
            rprint(
                f"  [yellow]ΓÇó LM Studio response hit max_tokens={token_budget}; retrying with {new_budget}[/]"
            )
        return _call_llm(
            prompt,
            system_prompt=system_prompt,
            tools=tools,
            max_tokens=new_budget,
            attempt=1,
        )
    return str(content)


def _tavily_search(query: str, *, max_results: int = 3) -> Optional[str]:
    if not TAVILY_API_KEY:
        return None
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
    }
    try:
        resp = SESSION.post(TAVILY_ENDPOINT, json=payload, timeout=LLM_TIMEOUT)
    except requests.RequestException as exc:
        if DEBUG:
            rprint(f"  [yellow]ΓÇó Tavily search failed: {exc}[/]")
        return None

    if resp.status_code >= 400:
        if DEBUG:
            rprint(
                f"  [yellow]ΓÇó Tavily returned HTTP {resp.status_code}: {resp.text[:200]}[/]"
            )
        return None

    try:
        data = resp.json()
    except ValueError:
        if DEBUG:
            rprint("  [yellow]ΓÇó Tavily response was not valid JSON[/]")
        return None

    results = data.get("results")
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
            chunk = chunk[:500].rsplit(" ", 1)[0] + "ΓÇª"
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

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ tiny helpers ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
def clean_tail(s: str) -> str:
    return TAIL_RX.sub("", s).strip()

def has_audio(folder: Path) -> bool:
    return any(c.suffix.lower() in AUDIO_EXTS for c in folder.iterdir())

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ filename guess ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
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

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ online lookup helpers ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
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



def generate_metadata_via_llm(folder: Path, files: list[Path]) -> Optional[dict]:
    if not files:
        return None
    if not LLM_ENDPOINT or not LLM_MODEL_NAME:
        return None

    folder_label = folder.name or folder.stem or str(folder)
    file_lines = "\n".join(f"- {f.name}" for f in files[:25])
    if len(files) > 25:
        file_lines += f"\n- ΓÇª (+{len(files) - 25} more)"

    prompt = textwrap.dedent(
        f"""
        You are generating audiobook metadata for local tagging.
        Folder name: {folder_label}
        Total audio files: {len(files)}
        Audio files:
        {file_lines}

        Use the LM Studio MCP tools (full_web_search with site filters for audible.com, openlibrary.org,
        books.google.com, and goodreads.com) to research the matching audiobook edition. Respond with a
        single JSON object containing:
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
                rprint("  [yellow]ΓÇó LM Studio returned non-JSON metadata[/]")
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
            rprint("  [yellow]ΓÇó LM Studio metadata request returned no content[/]")
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
                    rprint(f"  [cyan]ΓÇó Tavily search context fetched for '{query}'[/]")
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
                "  [cyan]ΓÇó retrying LM Studio metadata request to fill: "
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
        mp4["├é┬⌐nam"] = meta["title"]
        mp4["├é┬⌐alb"] = meta["title"]
        mp4["├é┬⌐ART"] = meta["author"]
        if meta["year"]:
            mp4["├é┬⌐day"] = meta["year"]
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

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ process one leaf ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
def process_leaf(path: Path, args):
    # skip Unknown Author
    if path.name == "Unknown Author" or path.parent.name == "Unknown Author":
        rprint("ΓÇó skip Unknown Author:", path)
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
        rprint(f"[cyan]├óΓÇáΓÇÖ[/] {path}  [green]tags stripped ({ok}/{len(targets)})[/]")
        log("STRIP", f"{path}  ({ok}/{len(targets)})")
        return

    # guess
    a_guess, t_guess, y_guess = guess_from_path(path)
    rprint(f"[cyan]├óΓÇáΓÇÖ[/] {path}")
    rprint(f"  guess: [italic]{t_guess}[/] by {a_guess or '?'} ({y_guess or '?'})")

    if path.is_file():
        targets = [path] if path.suffix.lower() in AUDIO_EXTS else []
    else:
        targets = sorted(
            [f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXTS]
        )
    if not targets:
        rprint("  [yellow]ΓÇó no audio files found[/]")
        log("SKIP", f"{path}  no_audio")
        return

    folder = path if path.is_dir() else path.parent

    result, scores = best_match(a_guess, t_guess)
    llm_used = False
    if not result:
        rprint("  [red] ΓÇó no match[/]")
        llm_meta = generate_metadata_via_llm(folder, targets)
        if llm_meta:
            rprint("  [magenta]ΓÇó metadata supplied by local LLM[/]")
            meta = llm_meta
            llm_used = True
        else:
            log("NOMATCH", str(path))
            review_log(path, "no_match")
            return
    else:
        score, hit = result

        for name, (sc, _) in sorted(scores.items(), key=lambda x: -x[1][0]):
            rprint(f"  {name:>9}: {sc}")

        author_hit = ", ".join(hit["authors"]) or a_guess or "Unknown"
        rprint(f"  match: [bold]{hit['title']}[/] by {author_hit} ({hit['year'] or '?'})")
        if hit.get("series"):
            rprint(f"  series: {hit['series']}")
        rprint(f"  provider: {hit['source']}")

        if score < 60:
            rprint("  [yellow]├ó┼í┬á low confidence ├óΓé¼ΓÇ£ double-check[/]")

        meta = {
            "title": hit["title"],
            "author": author_hit,
            "year": hit["year"],
            "series": hit.get("series"),
        }

        if score < args.llm_threshold:
            llm_meta = generate_metadata_via_llm(folder, targets)
            if llm_meta:
                rprint(
                    f"  [magenta]ΓÇó metadata supplied by local LLM (score {score} < {args.llm_threshold})[/]"
                )
                meta = llm_meta
                llm_used = True

        if not llm_used and score < 70 and not args.yes:
            if args.no:
                proceed = False
            elif hasattr(Confirm, "ask"):
                proceed = Confirm.ask("  tag with this metadata?", default=False)
            else:
                proceed = Confirm("tag with this metadata?", default=False)
            if not proceed:
                log("SKIP", str(path))
                review_log(path, "user_skip")
                return
    ok = 0
    for idx, f in enumerate(targets, 1):
        try:
            write_tags(f, meta, idx, len(targets)); ok += 1
        except (MutagenError, MP4StreamInfoError):
            log("ERR", f"tag {f}")
    label = "OK" if ok == len(targets) else "ERR"
    rprint(f"  [green]tagged {ok}/{len(targets)} file(s)[/]")
    suffix = " [LLM]" if llm_used else ""
    log(label, f"{path}  ({ok}/{len(targets)}){suffix}")
    if label == "OK":
        export_metadata(path, meta)

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ leaf finder ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
def walk_leaves(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    leaves: List[Path] = []
    for p in root.rglob("*"):
        if p.is_dir() and has_audio(p) and not any(
            c.is_dir() and has_audio(c) for c in p.iterdir()):
            leaves.append(p)
    return leaves

# ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼ cli / main ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
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
    ap.add_argument("--llm-endpoint", default="http://127.0.0.1:1234/v1/chat/completions",
                    help="OpenAI-compatible completion endpoint (use 'none' to disable; default: %(default)s)")
    ap.add_argument("--llm-model", default="mistral-7b-instruct-q4",
                    help="Model name to request from the LM Studio endpoint (default: %(default)s)")
    ap.add_argument("--llm-threshold", type=int, default=75, metavar="SCORE",
                    help="use the local LLM when provider score falls below SCORE (default: 75)")
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
            rprint(f"[red]ERR:[/] {leaf} ├óΓé¼ΓÇ£ {e}")
            if DEBUG:
                import traceback
                tb = traceback.format_exc()
                rprint(tb)
                log("ERR", f"{leaf} ├óΓé¼ΓÇ£ {type(e).__name__}: {tb.strip()}")
            else:
                log("ERR", f"{leaf} ├óΓé¼ΓÇ£ {type(e).__name__}")

if __name__ == "__main__":
    main()

















