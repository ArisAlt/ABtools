"""LLM-driven metadata generation and refinement helpers."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rapidfuzz import fuzz
from urllib.parse import urlsplit

from ablib.core import config, constants
from ablib.core.console import rprint
from ablib.core.http import SESSION
from ablib.core.logging import review_log
from ablib.metadata.utils import determine_best_author, enhanced_author_extraction
from ablib.providers.mcp import execute_tool_call, serialise_tool_result

CONFIG = config.config

# Maximum number of tool-call iterations per LLM call to prevent infinite loops
_MAX_TOOL_ITERATIONS: int = 20
_MAX_CALLS_PER_TOOL: int = 5

# Score at which an MCP refinement is considered good enough to use. Shared with
# ablib.cli.main so the two cannot drift: refine_metadata_via_mcp used to stop
# early at 90 while its caller only accepted 95, so a stage-1 result scoring
# 90-94 skipped the SequentialThinking stage and was then discarded anyway.
MCP_ACCEPT_SCORE: int = 95


# Statuses another endpoint might not share, so they are worth retrying
# elsewhere: quota/rate limit, a bad or missing key, and server-side errors.
# 400 and 404 are the model or request being wrong and would fail identically.
_RETRYABLE_STATUS = frozenset({401, 402, 403, 408, 409, 429, 500, 502, 503, 504})


def _endpoint_label(endpoint: Optional[str]) -> str:
    """Name the endpoint in log lines by host.

    Everything used to be reported as "LM Studio", so a quota error from a
    hosted provider read as though the local server had rejected it -- see the
    field report of "LM Studio returned HTTP 429: ... free-models-per-day",
    which came from OpenRouter.
    """
    if not endpoint:
        return "LLM"
    try:
        host = urlsplit(endpoint).hostname or endpoint
    except ValueError:
        return endpoint
    if host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        return "local LLM"
    return host


def _auth_headers(api_key: Optional[str] = None) -> dict[str, str]:
    """Headers for the completions request.

    Hosted OpenAI-compatible providers (OpenRouter and friends) need a bearer
    token; a local LM Studio or Ollama server ignores it. Sending nothing at
    all was why only local endpoints ever worked.
    """
    headers = {"Content-Type": "application/json"}
    key = (CONFIG.llm_api_key if api_key is None else api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        # OpenRouter attributes requests with these; harmless elsewhere.
        headers["HTTP-Referer"] = "https://github.com/ArisAlt/ABtools"
        headers["X-Title"] = "ABtools"
    return headers


def _call_llm(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    tools: Optional[List[dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    attempt: int = 0,
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    on_retryable_failure: Optional[List[str]] = None,
) -> Optional[str]:
    """Call an OpenAI-compatible endpoint. `endpoint`/`model` default to the
    primary configuration, so the same function serves the local fallback.

    `on_retryable_failure` is an out-parameter: when the call fails for a
    reason another endpoint might not share -- a quota or rate limit, a bad or
    missing key, a server-side error, an unreachable host -- the reason is
    appended to it. A model that answered but answered badly is *not*
    retryable, and leaves it untouched.
    """
    endpoint = endpoint or CONFIG.llm_endpoint
    model = model or CONFIG.llm_model_name
    if not endpoint or not model:
        return None
    where = _endpoint_label(endpoint)

    token_budget = max_tokens or CONFIG.llm_max_tokens
    sys_prompt = system_prompt or constants.LLM_SYSTEM_PROMPT
    convo: List[dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ]
    length_retry = attempt
    used_tools: Dict[str, int] = {}
    tool_iterations: int = 0

    while True:
        if tool_iterations > _MAX_TOOL_ITERATIONS:
            if CONFIG.debug:
                rprint(f"  [yellow]- {where} tool loop exceeded {_MAX_TOOL_ITERATIONS} iterations; aborting[/]")
            return None
        payload: dict[str, Any] = {
            "model": model,
            "messages": convo,
            "temperature": 0.0,
            "max_tokens": token_budget,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = SESSION.post(
                endpoint,
                json=payload,
                headers=_auth_headers(api_key),
                timeout=CONFIG.llm_timeout,
            )
        except requests.RequestException as exc:  # pragma: no cover
            if CONFIG.debug:
                rprint(f"  [yellow]- {where} request failed: {exc}[/]")
            if on_retryable_failure is not None:
                on_retryable_failure.append(f"{where} unreachable: {exc}")
            return None
        if resp.status_code >= 400:
            detail = resp.text[:200]
            if CONFIG.debug:
                rprint(f"  [yellow]- {where} returned HTTP {resp.status_code}: {detail}[/]")
            if on_retryable_failure is not None and resp.status_code in _RETRYABLE_STATUS:
                on_retryable_failure.append(f"{where} HTTP {resp.status_code}: {detail}")
            return None

        try:
            data = resp.json()
        except ValueError:
            if CONFIG.debug:
                rprint(f"  [yellow]- {where} response was not valid JSON[/]")
            return None

        choices = data.get("choices")
        if not choices:
            return None
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        finish_reason = (
            first_choice.get("finish_reason") if isinstance(first_choice, dict) else None
        )
        content = message.get("content") if isinstance(message, dict) else None
        tool_calls = message.get("tool_calls") if isinstance(message, dict) else None

        if tool_calls:
            tool_iterations += 1
            convo.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name")
                tool_name = (name or "").strip()
                arguments_raw = fn.get("arguments") or "{}"
                try:
                    arguments = json.loads(arguments_raw) if arguments_raw else {}
                except json.JSONDecodeError:
                    arguments = {}

                if tool_name == "sequential_thinking" and used_tools.get(tool_name):
                    tool_response = serialise_tool_result(
                        {
                            "notes": [
                                "sequential_thinking already executed; respond with final JSON metadata now."
                            ],
                            "guidance": "Use the prior sequential thinking notes to complete the metadata without issuing further tool calls.",
                        }
                    )
                elif tool_name and used_tools.get(tool_name, 0) >= _MAX_CALLS_PER_TOOL:
                    tool_response = serialise_tool_result(
                        {"error": f"{tool_name} has been called {_MAX_CALLS_PER_TOOL} times; stop calling it and respond with JSON."}
                    )
                else:
                    tool_response = execute_tool_call(tool_name, arguments)

                if tool_name:
                    used_tools[tool_name] = used_tools.get(tool_name, 0) + 1

                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or name or "tool",
                        "name": name or "tool",
                        "content": tool_response,
                    }
                )
            continue

        if finish_reason == "length" and length_retry == 0:
            # max() so the retry can never *shrink* the budget: with the
            # CONFIG.llm_max_tokens default of 8000, min(16000, 2048) handed
            # the retry 2048 -- a 4x cut on the very call meant to give the
            # model more room.
            new_budget = max(token_budget, min(token_budget * 2, 16384))
            if CONFIG.debug:
                rprint(
                    f"  [yellow]- {where} response hit max_tokens={token_budget}; retrying with {new_budget}[/]"
                )
            token_budget = new_budget
            length_retry = 1
            continue

        if not content:
            return None
        convo.append({"role": "assistant", "content": str(content)})
        return str(content)


def _call_llm_with_fallback(prompt: str, **kwargs: Any) -> tuple[Optional[str], bool]:
    """Try the primary endpoint, then the local fallback. (raw, used_fallback).

    Only failures another endpoint might not share trigger the second attempt
    -- a quota or rate limit, a rejected key, a server error, an unreachable
    host. A model that answered badly is not retried: the fallback would answer
    just as badly and the run would take twice as long doing it.
    """
    reasons: List[str] = []
    raw = _call_llm(prompt, on_retryable_failure=reasons, **kwargs)
    if raw is not None or not reasons:
        return raw, False

    endpoint = (CONFIG.llm_fallback_endpoint or "").strip()
    model = (CONFIG.llm_fallback_model or "").strip()
    if not endpoint or not model:
        return None, False
    if endpoint == (CONFIG.llm_endpoint or "").strip():
        return None, False   # the fallback *is* the endpoint that just failed

    # In debug the failure was already printed in full by _call_llm; repeating
    # it here just doubles the noise on every book of a rate-limited run.
    if not CONFIG.debug:
        rprint(f"  [yellow]- {reasons[0]}[/]")
    rprint(f"  [cyan]- falling back to {_endpoint_label(endpoint)} ({model})[/]")
    raw = _call_llm(prompt, endpoint=endpoint, model=model, api_key="", **kwargs)
    return raw, raw is not None


def fallback_confidence(
    meta: Optional[Dict[str, Optional[str]]],
    guess: Optional[Dict[str, Any]],
) -> int:
    """How well a fallback answer agrees with the evidence on disk, 0-100.

    A local model asked "which audiobook is this folder?" will answer even when
    it has no idea, and the answer looks exactly like a good one. There is no
    provider score to lean on here, so the folder's own guess is the only
    independent evidence -- if the model's title and author do not resemble it,
    the answer is not trustworthy enough to write into a library.

    Returns 0 when there is nothing to compare against, so an unverifiable
    answer is never treated as confident.
    """
    if not meta or not meta.get("title"):
        return 0
    if not guess:
        return 0

    guess_title = (guess.get("title") or "").strip()
    if not guess_title:
        return 0
    title_score = fuzz.token_set_ratio(meta["title"].lower(), guess_title.lower())

    guess_author = (guess.get("author") or "").strip()
    meta_author = (meta.get("author") or "").strip()
    if guess_author and meta_author and guess_author.lower() != "unknown author":
        author_score = fuzz.token_set_ratio(meta_author.lower(), guess_author.lower())
        return int(round(0.7 * title_score + 0.3 * author_score))
    return int(round(title_score))


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        else:
            cleaned = ""
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
    return cleaned.strip()


def _normalise_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = str(value)
    elif isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        value = ", ".join(parts)
    elif not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def generate_metadata_via_llm(
    folder: Path,
    files: List[Path],
    guess: Optional[Dict[str, Any]] = None,
    provider_scores: Optional[Dict[str, int]] = None,
) -> Optional[dict]:
    if not files:
        return None
    if not CONFIG.llm_endpoint or not CONFIG.llm_model_name:
        return None

    folder_label = folder.name or folder.stem or str(folder)
    file_lines = "\n".join(f"- {f.name}" for f in files[:25])
    if len(files) > 25:
        file_lines += f"\n- ... (+{len(files) - 25} more)"

    guess_lines: List[str] = []
    if guess:
        guess_lines.append("Guess metadata:")
        if guess.get("path"):
            guess_lines.append(f"  - Path: {guess['path']}")
        guess_title = guess.get("title") or "Unknown"
        guess_author = guess.get("author") or "Unknown"
        guess_year = guess.get("year") or "Unknown"
        guess_lines.append(
            f"  - Folder guess: {guess_title} by {guess_author} ({guess_year})"
        )
        if guess.get("series"):
            guess_lines.append(
                f"  - Series guess: {guess['series']} #{guess.get('series_index') or '?'}"
            )
    guess_block = "\n".join(guess_lines) if guess_lines else "Guess metadata: not provided."

    provider_lines: List[str] = []
    if provider_scores:
        provider_lines.append("Provider scores (higher is better):")
        for name, score in sorted(provider_scores.items(), key=lambda item: -item[1]):
            provider_lines.append(f"  - {name}: {score}")
    provider_block = (
        "\n".join(provider_lines) if provider_lines else "Provider scores: not available."
    )

    prompt = textwrap.dedent(
        f"""
        You are generating audiobook metadata for local tagging.
        Folder name: {folder_label}
        Total audio files: {len(files)}
        Audio files:
        {file_lines}

        {guess_block}

        {provider_block}

        Aim to produce metadata that will achieve a confidence score of 90 or higher; high-scoring responses
        earn a bonus reward. Research the matching audiobook edition via the LM Studio MCP server using this order:
          1. Call `search_goodreads_tool` with the suspected title and author.
          2. If the best Goodreads confidence is below 90, call `search_audible_tool` to cross-check.
          3. When neither provider produces a confidence ≥ 90, call the DuckDuckGo MCP `fetch_content`
             tool to gather supporting excerpts before finalising the answer.
        Provider responses include a `confidence` value from 0-100; treat scores ≥ 90 as reliable matches.
        If a specific URL needs inspection, call `get_single_web_page_content`. Respond with a single
        JSON object containing:
          - "title" (required)
          - "author" (required)
          - "series" (optional)
          - "series_index" (optional)
          - "year" (optional four digit year)
          - "narrator" (optional)
          - "language" (optional language code or name)
          - "description" (optional short summary)
          - "publisher" (optional)
        Use null when a value is unknown. Respond with JSON only.
        """
    ).strip()

    allowed = {
        "title",
        "author",
        "series",
        "series_index",
        "year",
        "narrator",
        "language",
        "description",
        "publisher",
    }
    optional_keys = {
        "series",
        "series_index",
        "year",
        "narrator",
        "language",
        "description",
        "publisher",
    }

    def parse_llm_raw(raw: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
        if raw is None:
            return None
        cleaned = _strip_fence(raw)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            if CONFIG.debug:
                rprint("  [yellow]- LLM returned non-JSON metadata[/]")
            return None
        if not isinstance(payload, dict):
            return None

        meta: Dict[str, Optional[str]] = {}
        for key in allowed:
            if key in payload:
                meta[key] = _normalise_value(payload[key])
        if not meta.get("title") or not meta.get("author"):
            return None

        year_value = meta.get("year")
        if year_value:
            match = re.search(r"\b(\d{4})\b", year_value)
            meta["year"] = match.group(1) if match else None
        if meta.get("series_index"):
            meta["series_index"] = _normalise_value(meta["series_index"])

        result_meta: Dict[str, Optional[str]] = {
            "title": meta["title"],
            "author": meta["author"],
            "year": meta.get("year"),
            "series": meta.get("series"),
        }
        if meta.get("series_index"):
            result_meta["series_index"] = meta["series_index"]
        for extra in ("narrator", "language", "description", "publisher"):
            if meta.get(extra):
                result_meta[extra] = meta[extra]
        return result_meta

    def missing_optional(meta: Optional[Dict[str, Optional[str]]]) -> set[str]:
        if not meta:
            return optional_keys
        return {
            key
            for key in optional_keys
            if not (str(meta.get(key)).strip() if meta.get(key) is not None else "")
        }

    primary_raw, used_fallback = _call_llm_with_fallback(
        prompt,
        system_prompt=constants.MCP_SYSTEM_PROMPT,
        tools=constants.MCP_TOOLS,
        max_tokens=1024,
    )
    if primary_raw is None:
        if CONFIG.debug:
            rprint("  [yellow]- LLM metadata request returned no content[/]")
        return None

    result = parse_llm_raw(primary_raw)

    if used_fallback:
        # The fallback has no provider score behind it and no quota discipline
        # keeping it honest, so it is checked against the folder before use.
        score = fallback_confidence(result, guess)
        threshold = CONFIG.llm_fallback_min_score
        if score < threshold:
            rprint(
                f"  [yellow]- local LLM answer scores {score} against the folder "
                f"(needs {threshold}); leaving untagged[/]"
            )
            review_log(
                folder,
                f"local LLM fallback rejected: score {score} < {threshold}",
            )
            return None
        rprint(f"  [green]- local LLM answer accepted (score {score})[/]")

    missing_fields = missing_optional(result)

    if missing_fields:
        missing_list = ", ".join(sorted(missing_fields))
        retry_prompt = (
            prompt
            + "\n\nThe previous response was missing these fields: "
            + missing_list
            + ". Please research reputable audiobook sources (Audible, Open Library, Google Books, publisher sites) and try again."
        )

        # Stay on whichever endpoint actually answered. Sending the gap-filling
        # retry back to the primary meant that after a successful fallback it
        # hit the same quota error that caused the fallback in the first place.
        retry_kwargs: Dict[str, Any] = {}
        if used_fallback:
            retry_kwargs = {
                "endpoint": CONFIG.llm_fallback_endpoint,
                "model": CONFIG.llm_fallback_model,
                "api_key": "",
            }
        retry_where = _endpoint_label(
            retry_kwargs.get("endpoint") or CONFIG.llm_endpoint
        )

        if CONFIG.debug:
            rprint(
                f"  [cyan]- retrying {retry_where} metadata request to fill: "
                + missing_list
                + "[/]"
            )

        retry_raw = _call_llm(
            retry_prompt,
            system_prompt=constants.MCP_SYSTEM_PROMPT,
            tools=constants.MCP_TOOLS,
            max_tokens=1024,
            attempt=1,
            **retry_kwargs,
        )
        retry_result = parse_llm_raw(retry_raw)
        if retry_result:
            # Merge, do not replace. This retry exists solely to fill fields the
            # primary response lacked, but overwriting wholesale meant a retry
            # that found `series` while omitting `narrator`/`publisher` threw
            # away values the primary had already established -- leaving less
            # metadata than before the retry ran. Primary wins any conflict;
            # the retry only supplies gaps.
            merged = dict(retry_result)
            merged.update({k: v for k, v in result.items() if v} if result else {})
            result = merged

    return result


def refine_metadata_via_mcp(
    folder: Path,
    author_guess: Optional[str],
    title_guess: str,
    series_guess: Optional[str] = None,
    series_index_guess: Optional[str] = None,
    initial_score: int = 0,
    partial_meta: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Two-stage MCP refinement pipeline for low-confidence metadata."""

    if not CONFIG.llm_endpoint or not CONFIG.llm_model_name:
        return None

    folder_label = folder.name or folder.stem or str(folder)

    best_author = determine_best_author(folder, author_guess, partial_meta)
    if not best_author:
        best_author = enhanced_author_extraction(folder)

    stage1_prompt = textwrap.dedent(
        f"""
        You are refining audiobook metadata using web search tools.
        Folder: {folder_label}
        Title: "{title_guess}"
        Author: {best_author or 'Unknown'}
        Series: {series_guess or 'Unknown'}
        Series Index: {series_index_guess or 'Unknown'}
        Initial score: {initial_score}

        Use the full_web_search tool with site filters for:
        - site:audible.com "{title_guess}" {best_author or ''}
        - site:openlibrary.org "{title_guess}" {best_author or ''}
        - site:books.google.com "{title_guess}" {best_author or ''}
        - site:goodreads.com "{title_guess}" {best_author or ''}

        Research this audiobook and respond with JSON containing:
        - "title" (required)
        - "author" (required)
        - "year" (optional)
        - "series" (optional)
        - "series_index" (optional)
        - "narrator" (optional)
        - "language" (optional)
        - "description" (optional)
        - "publisher" (optional)
        - "score" (confidence 0-100, required)

        Use null for unknown values. Respond with JSON only.
        """
    ).strip()

    def parse_mcp_response(raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if raw is None:
            return None
        cleaned = _strip_fence(raw)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            if CONFIG.debug:
                rprint("  [yellow]- MCP response was not valid JSON[/]")
            return None
        if not isinstance(payload, dict):
            return None
        if not payload.get("title") or not payload.get("author"):
            return None

        meta: Dict[str, Any] = {}
        for key in [
            "title",
            "author",
            "year",
            "series",
            "series_index",
            "narrator",
            "language",
            "description",
            "publisher",
        ]:
            meta[key] = _normalise_value(payload.get(key))

        llm_score = payload.get("score")
        if isinstance(llm_score, (int, float)):
            meta["score"] = int(llm_score)
        else:
            meta["score"] = 0
        return meta

    def calculate_combined_score(
        meta: Dict[str, Any],
        folder_name: str,
        title_guess: str,
        guessed_author: Optional[str],
    ) -> int:
        llm_score = meta.get("score", 0)
        title_score = fuzz.token_set_ratio(title_guess.lower(), (meta.get("title") or "").lower())
        author_score = 0
        if guessed_author and meta.get("author"):
            author_score = fuzz.token_set_ratio(guessed_author.lower(), meta["author"].lower())
        if best_author and meta.get("author"):
            best_author_score = fuzz.token_set_ratio(best_author.lower(), meta["author"].lower())
            author_score = max(author_score, best_author_score)
        folder_score = fuzz.token_set_ratio(
            folder_name.lower(),
            f"{meta.get('title', '')} {meta.get('author', '')}".lower(),
        )
        fuzzy_score = int((title_score * 0.4 + author_score * 0.3 + folder_score * 0.3))
        combined = int(llm_score * 0.5 + fuzzy_score * 0.5)
        meta["score"] = combined
        return combined

    try:
        stage1_raw, _ = _call_llm_with_fallback(
            stage1_prompt,
            system_prompt=constants.MCP_SYSTEM_PROMPT,
            tools=constants.MCP_TOOLS,
            max_tokens=1024,
        )
        if stage1_raw is None:
            if CONFIG.debug:
                rprint("  [yellow]- Stage 1 MCP refinement failed[/]")
            return None

        stage1_meta = parse_mcp_response(stage1_raw)
        if not stage1_meta:
            if CONFIG.debug:
                rprint("  [yellow]- Stage 1 MCP response invalid[/]")
            return None

        stage1_score = calculate_combined_score(
            stage1_meta, folder_label, title_guess, author_guess
        )
        stage1_meta["refinement_source"] = "refined_web_search"

        if CONFIG.debug:
            rprint(f"  [cyan]- Stage 1 refinement score: {stage1_score}[/]")

        if stage1_score >= MCP_ACCEPT_SCORE:
            return stage1_meta

        if CONFIG.debug:
            rprint("  [cyan]- Proceeding to SequentialThinking refinement[/]")

        stage2_context = f"""
        Previous refinement attempt scored {stage1_score}/100.
        This title may be a novella, anthology entry, or side story in an existing series.
        Consider alternative titles, series relationships, and publication formats.
        """

        stage2_prompt = textwrap.dedent(
            f"""
            Use advanced reasoning to refine this audiobook metadata.

            Folder: {folder_label}
            Title: "{title_guess}"
            Author: {best_author or 'Unknown'}
            Series: {series_guess or 'Unknown'}
            Series Index: {series_index_guess or 'Unknown'}

            Context: {stage2_context}

            Previous attempt found: {stage1_meta.get('title', 'Unknown')} by {stage1_meta.get('author', 'Unknown')}

            Apply sequential thinking to determine the most accurate metadata.
            Consider:
            - Series relationships and numbering
            - Alternative titles or translations
            - Publication format (novella, short story, anthology)
            - Author variations or pseudonyms

            Respond with JSON containing:
            - "title" (required)
            - "author" (required)
            - "year" (optional)
            - "series" (optional)
            - "series_index" (optional)
            - "narrator" (optional)
            - "language" (optional)
            - "description" (optional)
            - "publisher" (optional)
            - "score" (confidence 0-100, required)
            - "reasoning" (brief explanation, optional)

            Use null for unknown values. Respond with JSON only.
            """
        ).strip()

        sequential_tools = [
            {
                "type": "function",
                "function": {
                    "name": "sequential_thinking",
                    "description": "Advanced reasoning for complex metadata inference",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "context": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

        stage2_raw, _ = _call_llm_with_fallback(
            stage2_prompt,
            system_prompt=constants.MCP_SYSTEM_PROMPT,
            tools=sequential_tools,
            max_tokens=1024,
        )
        if stage2_raw is None:
            if CONFIG.debug:
                rprint("  [yellow]- Stage 2 SequentialThinking failed[/]")
            return stage1_meta

        stage2_meta = parse_mcp_response(stage2_raw)
        if not stage2_meta:
            if CONFIG.debug:
                rprint("  [yellow]- Stage 2 response invalid[/]")
            return stage1_meta

        stage2_score = calculate_combined_score(
            stage2_meta, folder_label, title_guess, author_guess
        )
        stage2_meta["refinement_source"] = "sequentialthinking_refinement"

        if CONFIG.debug:
            rprint(f"  [cyan]- Stage 2 refinement score: {stage2_score}[/]")

        return stage2_meta if stage2_score >= stage1_score else stage1_meta

    except Exception as exc:  # pragma: no cover - defensive
        if CONFIG.debug:
            rprint(f"  [yellow]- MCP refinement error: {exc}[/]")
        review_log(folder, f"mcp_refinement_failed: {type(exc).__name__}")
        return None


__all__ = ["_call_llm", "_auth_headers", "generate_metadata_via_llm",
           "refine_metadata_via_mcp", "MCP_ACCEPT_SCORE"]
