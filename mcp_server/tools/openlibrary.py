from __future__ import annotations

import requests


def search_openlibrary(query: str):
    """Search OpenLibrary by title or author."""
    if not query:
        return {"error": "query is required"}
    url = "https://openlibrary.org/search.json"
    params = {"q": query, "limit": 10}
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return {"error": f"openlibrary_request_failed:{exc}"}
    except ValueError:
        return {"error": "Invalid JSON returned from OpenLibrary"}

    results = []
    for doc in data.get("docs", []):
        results.append(
            {
                "title": doc.get("title"),
                "author": (doc.get("author_name") or ["Unknown"])[0],
                "year": doc.get("first_publish_year"),
                "openlibrary_id": doc.get("key"),
            }
        )
        if len(results) >= 10:
            break
    return results or {"error": "No results"}
