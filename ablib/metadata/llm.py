"""LLM-driven metadata generation and refinement helpers."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rapidfuzz import fuzz

from ablib.core import config, constants
from ablib.core.console import rprint
from ablib.core.http import SESSION
from ablib.core.logging import review_log
from ablib.metadata.utils import determine_best_author, enhanced_author_extraction
from ablib.providers.mcp import execute_tool_call, serialise_tool_result, _tavily_search

CONFIG = config.config


def _call_llm(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    tools: Optional[List[dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    attempt: int = 0,
) -> Optional[str]:
    if not CONFIG.llm_endpoint or not CONFIG.llm_model_name:
        return None

    token_budget = max_tokens or CONFIG.llm_max_tokens
    sys_prompt = system_prompt or constants.LLM_SYSTEM_PROMPT
    convo: List[dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ]
    length_retry = attempt
    used_tools: Dict[str, int] = {}

    while True:
        payload: dict[str, Any] = {
            "model": CONFIG.llm_model_name,
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
                CONFIG.llm_endpoint, json=payload, timeout=CONFIG.llm_timeout
            )
        except requests.RequestException as exc:  # pragma: no cover
            if CONFIG.debug:
                rprint(f"  [yellow]- LM Studio request failed: {exc}[/]")
            return None
        if resp.status_code >= 400:
            if CONFIG.debug:
                rprint(
                    f"  [yellow]- LM Studio returned HTTP {resp.status_code}: {resp.text[:200]}[/]"
                )
            return None

        try:
            data = resp.json()
        except ValueError:
            if CONFIG.debug:
                rprint("  [yellow]- LM Studio response was not valid JSON[/]")
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
            new_budget = min(token_budget * 2, 2048)
            if CONFIG.debug:
                rprint(
                    f"  [yellow]- LM Studio response hit max_tokens={token_budget}; retrying with {new_budget}[/]"
                )
            token_budget = new_budget
            length_retry = 1
            continue

        if not content:
            return None
        convo.append({"role": "assistant", "content": str(content)})
        return str(content)


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
                rprint("  [yellow]- LM Studio returned non-JSON metadata[/]")
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

    primary_raw = _call_llm(
        prompt,
        system_prompt=constants.MCP_SYSTEM_PROMPT,
        tools=constants.MCP_TOOLS,
        max_tokens=1024,
    )
    if primary_raw is None:
        if CONFIG.debug:
            rprint("  [yellow]- LM Studio metadata request returned no content[/]")
        return None

    result = parse_llm_raw(primary_raw)
    missing_fields = missing_optional(result)

    if missing_fields:
        missing_list = ", ".join(sorted(missing_fields))
        tavily_context = None
        if CONFIG.tavily_api_key:
            query_terms: List[str] = []
            if result and result.get("title"):
                query_terms.append(str(result["title"]))
            else:
                query_terms.append(folder_label)
            if result and result.get("author"):
                query_terms.append(str(result["author"]))
            query = " ".join(t for t in query_terms if t).strip()
            if query:
                tavily_context = _tavily_search(query)
                if CONFIG.debug and tavily_context:
                    rprint(f"  [cyan]- Tavily search context fetched for '{query}'[/]")

        retry_prompt = (
            prompt
            + "\n\nThe previous response was missing these fields: "
            + missing_list
            + ". Please research reputable audiobook sources (Audible, Open Library, Google Books, publisher sites) and try again."
        )
        if tavily_context:
            retry_prompt += (
                "\n\nExternal research via Tavily Search (summaries):\n"
                + tavily_context
                + "\nUse this information to fill the missing metadata fields."
            )
        else:
            retry_prompt += "\n\nIf needed, consult the Tavily Search API when gathering details."

        if CONFIG.debug:
            rprint(
                "  [cyan]- retrying LM Studio metadata request to fill: "
                + missing_list
                + "[/]"
            )

        retry_raw = _call_llm(
            retry_prompt,
            system_prompt=constants.MCP_SYSTEM_PROMPT,
            tools=constants.MCP_TOOLS,
            max_tokens=1024,
            attempt=1,
        )
        retry_result = parse_llm_raw(retry_raw)
        if retry_result:
            result = retry_result

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
        stage1_raw = _call_llm(
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

        if stage1_score >= 90:
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

        stage2_raw = _call_llm(
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


__all__ = ["_call_llm", "generate_metadata_via_llm", "refine_metadata_via_mcp"]
