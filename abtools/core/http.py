"""Shared HTTP session helpers."""

from __future__ import annotations

import requests

SESSION = requests.Session()

__all__ = ["SESSION"]
