"""Runtime configuration that can be mutated by the CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .constants import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_LLM_ENDPOINT,
    DEFAULT_LLM_MODEL_NAME,
    LLM_MAX_TOKENS_DEFAULT,
    LLM_TIMEOUT_DEFAULT,
)


# ── environment cascade ─────────────────────────────────────────────────────
# Precedence, highest first:
#   explicit CLI flag / GUI selection  ->  saved GUI settings  ->  ABTOOLS_*
#   environment variables  ->  the defaults in constants.py
#
# Only ABTOOLS_-prefixed names are honoured. OPENAI_BASE_URL and friends are
# deliberately ignored: silently inheriting a variable set for a different tool
# could point tagging at a paid hosted API without the user realising.
ENV_PREFIX = "ABTOOLS_"

# Misconfigured variables are recorded rather than swallowed, so --show-config
# can report them instead of the user wondering why a setting had no effect.
env_problems: list[str] = []


def _env_str(name: str, fallback: Optional[str]) -> Optional[str]:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return fallback
    return raw.strip() or None


def _env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return fallback
    try:
        return int(raw.strip())
    except ValueError:
        env_problems.append(
            f"{ENV_PREFIX}{name}={raw!r} is not a whole number; using {fallback}"
        )
        return fallback


def _env_bool(name: str, fallback: bool) -> bool:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return fallback
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    env_problems.append(
        f"{ENV_PREFIX}{name}={raw!r} is not a boolean; using {fallback}"
    )
    return fallback


@dataclass
class RuntimeConfig:
    """Mutable configuration shared across modules."""

    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))
    log_path: Path = field(default_factory=lambda: Path("tag_log.txt"))
    review_path: Path = field(default_factory=lambda: Path("review_log.txt"))
    llm_endpoint: Optional[str] = field(
        default_factory=lambda: _env_str("LLM_ENDPOINT", DEFAULT_LLM_ENDPOINT)
    )
    llm_model_name: Optional[str] = field(
        default_factory=lambda: _env_str("LLM_MODEL", DEFAULT_LLM_MODEL_NAME)
    )
    llm_timeout: int = field(
        default_factory=lambda: _env_int("LLM_TIMEOUT", LLM_TIMEOUT_DEFAULT)
    )
    llm_max_tokens: int = field(
        default_factory=lambda: _env_int("LLM_MAX_TOKENS", LLM_MAX_TOKENS_DEFAULT)
    )
    # Bearer token for hosted OpenAI-compatible providers such as OpenRouter.
    # Read from the environment so it need never be typed into the GUI or
    # written to a settings file in plain text.
    llm_api_key: Optional[str] = field(
        default_factory=lambda: (
            os.environ.get("ABTOOLS_LLM_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
        )
    )
    # A local model to fall back to when the primary endpoint cannot answer.
    # A hosted free tier runs out ("HTTP 429: Rate limit exceeded:
    # free-models-per-day") partway through a large run, and every remaining
    # book was then simply left with no metadata. A local server has no quota.
    llm_fallback_endpoint: Optional[str] = field(
        default_factory=lambda: _env_str("LLM_FALLBACK_ENDPOINT", DEFAULT_LLM_ENDPOINT)
    )
    llm_fallback_model: Optional[str] = field(
        default_factory=lambda: _env_str("LLM_FALLBACK_MODEL", DEFAULT_LLM_MODEL_NAME)
    )
    # How closely a fallback answer must match the folder before it is written.
    # A small local model asked "what book is this?" will confidently invent
    # one, so its answer is only accepted when it agrees with the evidence on
    # disk; below this the book is left untagged rather than tagged wrongly.
    llm_fallback_min_score: int = field(
        default_factory=lambda: _env_int("LLM_FALLBACK_MIN_SCORE", DEFAULT_MATCH_THRESHOLD)
    )


config = RuntimeConfig()

# Every setting the cascade governs: (attribute, environment variable, secret?)
ENV_SETTINGS = (
    ("llm_endpoint", "LLM_ENDPOINT", False),
    ("llm_model_name", "LLM_MODEL", False),
    ("llm_timeout", "LLM_TIMEOUT", False),
    ("llm_max_tokens", "LLM_MAX_TOKENS", False),
    ("llm_api_key", "LLM_API_KEY", True),
    ("llm_fallback_endpoint", "LLM_FALLBACK_ENDPOINT", False),
    ("llm_fallback_model", "LLM_FALLBACK_MODEL", False),
    ("llm_fallback_min_score", "LLM_FALLBACK_MIN_SCORE", False),
    ("debug", "DEBUG", False),
)


def describe_config() -> list[tuple[str, str, str]]:
    """(setting, effective value, where it came from) for --show-config.

    Secrets are reported as set/unset, never printed.
    """
    rows: list[tuple[str, str, str]] = []
    for attr, env_name, secret in ENV_SETTINGS:
        value = getattr(config, attr, None)
        if secret:
            shown = "set" if value else "unset"
        else:
            shown = "none" if value is None else str(value)
        if os.environ.get(ENV_PREFIX + env_name) is not None:
            source = f"{ENV_PREFIX}{env_name}"
        elif attr == "llm_api_key" and os.environ.get("OPENROUTER_API_KEY"):
            source = "OPENROUTER_API_KEY"
        else:
            source = "default"
        rows.append((attr, shown, source))
    return rows


def update_paths(base: Path) -> None:
    """Update log locations relative to the supplied base directory."""

    config.log_path = base / "tag_log.txt"
    config.review_path = base / "review_log.txt"
