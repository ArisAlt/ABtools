"""Shared HTTP session helpers."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Goodreads answers 403 to the default "python-requests/x.y.z" agent, and the
# provider helper parsed that error page silently -- so the first and cheapest
# tier of the lookup chain had been failing on every single book, wasting a
# request each time and pushing work onto the LLM that a provider could have
# answered. Identify as a browser; every site here serves public search pages.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-GB,en;q=0.9",
    }
)

# Providers are public endpoints with occasional 429/5xx blips. One automatic,
# backed-off retry turns a transient failure into a hit instead of a fall
# through to the LLM.
_retry = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
    raise_on_status=False,
)
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=8, pool_maxsize=8)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)

__all__ = ["SESSION", "USER_AGENT"]
