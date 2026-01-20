"""Runtime configuration that can be mutated by the CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .constants import (
    DEFAULT_LLM_ENDPOINT,
    DEFAULT_LLM_MODEL_NAME,
    LLM_MAX_TOKENS_DEFAULT,
    LLM_TIMEOUT_DEFAULT,
)


@dataclass
class RuntimeConfig:
    """Mutable configuration shared across modules."""

    debug: bool = False
    log_path: Path = field(default_factory=lambda: Path("tag_log.txt"))
    review_path: Path = field(default_factory=lambda: Path("review_log.txt"))
    llm_endpoint: Optional[str] = DEFAULT_LLM_ENDPOINT
    llm_model_name: Optional[str] = DEFAULT_LLM_MODEL_NAME
    llm_timeout: int = LLM_TIMEOUT_DEFAULT
    llm_max_tokens: int = LLM_MAX_TOKENS_DEFAULT
    tavily_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("TAVILY_API_KEY")
    )
    tavily_endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "TAVILY_ENDPOINT", "https://api.tavily.com/search"
        )
    )


config = RuntimeConfig()


def update_paths(base: Path) -> None:
    """Update log locations relative to the supplied base directory."""

    config.log_path = base / "tag_log.txt"
    config.review_path = base / "review_log.txt"
