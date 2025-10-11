from __future__ import annotations

import requests


def search_google_books(query: str):
    """Search Google Books API by title or author."""
    if not query:
        return {"error": "query is required"}
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "maxResults": 10}
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return {"error": f"gbooks_request_failed:{exc}"}
    except ValueError:
        return {"error": "Invalid JSON returned from Google Books"}

    items = []
    for book in data.get("items", []):
        volume = book.get("volumeInfo") or {}
        items.append(
            {
                "title": volume.get("title"),
                "authors": volume.get("authors"),
                "published": volume.get("publishedDate"),
                "preview": volume.get("previewLink"),
            }
        )
        if len(items) >= 10:
            break
    return items or {"error": "No results"}
