"""Logging utilities shared across the CLI and helpers."""

from __future__ import annotations

import datetime
from pathlib import Path

from .config import config
from .console import rprint


def _write_line(path: Path, entry: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry + "\n")


def log(status: str, message: str) -> None:
    """Write a timestamped entry to the tag log."""

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{status}] {stamp} {message}"
    rprint(entry)
    _write_line(config.log_path, entry)


def review_log(path: Path, reason: str) -> None:
    """Append an entry to the review log."""

    entry = f"{path} | {reason}"
    _write_line(config.review_path, entry)
