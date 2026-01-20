"""Console helpers with graceful fallback when `rich` is unavailable."""

from __future__ import annotations

import re
from typing import Any

try:  # pragma: no cover - optional dependency
    from rich import print as rprint  # type: ignore
    from rich.prompt import Confirm  # type: ignore
except ImportError:  # pragma: no cover - fallback to plain console
    _TAGS = re.compile(r"\[/?[a-zA-Z].*?]")

    def rprint(*args: Any, **kwargs: Any) -> None:
        text = " ".join(map(str, args))
        print(_TAGS.sub("", text), **kwargs)

    def Confirm(prompt: str, default: bool = False) -> bool:
        ans = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").lower().strip()
        if not ans:
            return default
        return ans in {"y", "yes"}


__all__ = ["rprint", "Confirm"]
