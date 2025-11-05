#!/usr/bin/env python3
"""Legacy entry point forwarding to the modern ABtools CLI."""

from __future__ import annotations

from abtools.cli.main import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
