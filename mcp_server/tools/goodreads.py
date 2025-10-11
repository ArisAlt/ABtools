from __future__ import annotations

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ABtools/1.0)"}


def search_goodreads(query: str):
    """Search Goodreads by title or author."""
    if not query:
        return {"error": "query is required"}
    url = f"https://www.goodreads.com/search?q={query.replace(' ', '+')}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"error": f"goodreads_request_failed:{exc}"}

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for book in soup.select("tr[itemtype='http://schema.org/Book']"):
        title_el = book.select_one("a.bookTitle span")
        author_el = book.select_one("a.authorName span")
        link_el = book.select_one("a.bookTitle")
        if not title_el or not author_el or not link_el:
            continue
        results.append(
            {
                "title": title_el.text.strip(),
                "author": author_el.text.strip(),
                "url": "https://www.goodreads.com" + link_el.get("href", ""),
            }
        )
        if len(results) >= 10:
            break

    return results or {"error": "No results"}
