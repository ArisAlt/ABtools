from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.audible import search_audible
from mcp_server.tools.goodreads import search_goodreads
from mcp_server.tools.googlebooks import search_google_books
from mcp_server.tools.openlibrary import search_openlibrary
from mcp_server.tools.tagger import tag_audiobooks

MCP_SERVER_NAME = "ABtools MCP"
MCP_SERVER_VERSION = "1.1.0"

# FastMCP currently only accepts name/description arguments; keep the version in
# module metadata for reference and surface it via manifest.json instead.
mcp = FastMCP(MCP_SERVER_NAME)


@mcp.tool()
def search_audible_tool(query: str):
    """Search Audible for audiobooks by title or author."""
    return search_audible(query)


@mcp.tool()
def search_goodreads_tool(query: str):
    """Search Goodreads by title or author."""
    return search_goodreads(query)


@mcp.tool()
def search_google_books_tool(query: str):
    """Search Google Books API by title or author."""
    return search_google_books(query)


@mcp.tool()
def search_openlibrary_tool(query: str):
    """Search OpenLibrary by title or author."""
    return search_openlibrary(query)


@mcp.tool()
def tag_books_tool(path: str, commit: bool = False, yes: bool = False):
    """Tag audiobook folder using all sources."""
    return tag_audiobooks(path, commit=commit, yes=yes)

if __name__ == "__main__":
    import traceback

    sys.stdout.write(f"[mcp] starting {MCP_SERVER_NAME} ({MCP_SERVER_VERSION})\n")
    sys.stdout.flush()
    sys.stdout.write(
        "Registered tools: ['search_audible_tool', 'search_goodreads_tool', "
        "'search_google_books_tool', 'search_openlibrary_tool', 'tag_books_tool']\n"
    )
    sys.stdout.flush()
    try:
        mcp.run()
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
    finally:
        sys.stdout.write("[mcp] server stopped\n")
        sys.stdout.flush()
