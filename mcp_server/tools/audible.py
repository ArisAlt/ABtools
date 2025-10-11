from __future__ import annotations

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ABtools/1.0)"}


def search_audible(query: str):
    """Scrape Audible search results (no API key required)."""
    if not query:
        return {"error": "query is required"}
    url = f"https://www.audible.com/search?keywords={query.replace(' ', '+')}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"error": f"audible_request_failed:{exc}"}

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for item in soup.select("li.bc-list-item"):
        title_el = item.select_one(".bc-heading a")
        author_el = item.select_one(".bc-author a")
        if not title_el or not author_el:
            continue
        href = title_el.get("href") or ""
        results.append(
            {
                "title": title_el.text.strip(),
                "author": author_el.text.strip(),
                "url": f"https://www.audible.com{href}",
            }
        )
        if len(results) >= 10:
            break

    return results or {"error": "No results"}
