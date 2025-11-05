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
    re.compile(r"^(.+?)\s+(\d+(?:\.\d+)?)\s+(.+)$"),  # "Series 01 Title"
    re.compile(r"^(.+?)\s+Book\s+(\d+)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+#(\d+)\s+(.+)$"),
    re.compile(r"^(.+?)\s+Vol\.?\s+(\d+)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(\d+(?:\.\d+)?)\s+(.+)$"),  # "01 Title"
]

# LLM / MCP defaults ---------------------------------------------------------
DEFAULT_LLM_ENDPOINT = "http://127.0.0.1:8888/v1/chat/completions"
DEFAULT_LLM_MODEL_NAME = "ibm/granite-4-h-tiny"
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
