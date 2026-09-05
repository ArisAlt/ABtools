"""Global constants used across the ABtools package."""

from __future__ import annotations

import re
from typing import Any, Final

# Versioning -----------------------------------------------------------------
VERSION: Final[str] = "2.30"

# File / pattern constants ---------------------------------------------------
AUDIO_EXTS: Final[set[str]] = {".mp3", ".m4a", ".m4b"}
TAIL_RX = re.compile(r"(?:\s*(?:\{[^}]*\}|\d+\.\d{2}\.\d{2}|\d+\s*[kK](?:bps)?|kbps))*\s*$")
PAREN_RX = re.compile(r"\([^)]*\)")
YEAR_RX = re.compile(r"^(\d{4})\s*[-_]\s*")

SERIES_PATTERNS = [
    re.compile(r"^(.+?)\s+(?:Book|Bk\.?)\s+(\d+(?:\.\d+)?)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+#(\d+(?:\.\d+)?)\s+(.+)$"),
    re.compile(r"^(.+?)\s+Vol\.?(?:ume)?\s+(\d+(?:\.\d+)?)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(\d+(?:\.\d+)?)\s+(.+)$"),  # "Series 01 Title"
    re.compile(r"^(\d+(?:\.\d+)?)\s+(.+)$"),  # "01 Title"
]

# LLM / MCP defaults ---------------------------------------------------------
DEFAULT_LLM_ENDPOINT = "http://127.0.0.1:8888/v1/chat/completions"
DEFAULT_LLM_MODEL_NAME = "ibm/granite-4-h-tiny"

# The single confidence bar for "this provider hit is the right book", 0-100.
# Everything that decides whether to trust a match reads it, so the tools
# cannot drift apart.
#
# Measured against a real library (Harry Turtledove, 15 books) with
# ablib.providers.http.score_candidate:
#
#     100   correct - exact title, superset title ("In The Balance" ->
#           "Worldwar: In the Balance"), surname-only folder, missing initial
#      97   correct, one-character typo in the title
#   -- the gap --
#      81   right title, WRONG author (Homeward Bound / Elaine Tyler May,
#           Aftershocks / Catherine Coulter, Second Contact / Craig A. Falconer)
#      78   words reordered, different book
#      65   query title is a subset of the hit
#      53   right author, wrong book
#
# 83 sits inside the gap: above every wrong answer observed, below every
# correct one. Note the score saturates at 100 when no author is known, since
# there is then nothing to disagree about -- that case is guarded by the
# ambiguity check in combobook.choose_meta, not by this number.
DEFAULT_MATCH_THRESHOLD = 83
LLM_TIMEOUT_DEFAULT = 90
LLM_MAX_TOKENS_DEFAULT = 8000

LLM_SYSTEM_PROMPT = "You analyse audiobook folders and files, respond with JSON metadata only."

MCP_SYSTEM_PROMPT = (
    "You research audiobooks via the LM Studio MCP server.\n"
    "Always call the ABtools provider tools in this order:\n"
    "  1. Use `search_goodreads_tool` with the title and author.\n"
    "  2. If the best Goodreads confidence is below 90, call `search_audible_tool`.\n"
    "  3. When neither provider yields a confidence ≥ 90, call the DuckDuckGo MCP `fetch_content`\n"
    "     tool to gather supporting excerpts before finalising the JSON.\n"
    "Provider responses include a `confidence` field (0-100); treat values ≥ 90 as reliable matches.\n"
    "Use `get_single_web_page_content` only when you must extract details from a specific URL.\n"
    "Respond with a single JSON object describing the audiobook (title, authors[], year, series,\n"
    "series_index, narrator, publisher, description). Never return plain text."
)

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
