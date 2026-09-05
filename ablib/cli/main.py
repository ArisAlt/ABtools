"""Command-line entry point for the search-and-tag workflow."""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import List, Optional

from abclient import AbClient
from mutagen import MutagenError
from mutagen.mp4 import MP4StreamInfoError

from ablib.core import config, constants
from ablib.core.console import Confirm, rprint
from ablib.core.logging import log, review_log
from ablib.metadata.llm import (
    MCP_ACCEPT_SCORE,
    generate_metadata_via_llm,
    refine_metadata_via_mcp,
)
from ablib.metadata.utils import (
    format_metadata_summary,
    guess_from_path,
    validate_metadata_fields,
)
from ablib.providers.http import best_match, enrich_metadata_with_providers
from ablib.tagging.files import export_metadata, has_audio, strip_tags, write_tags

CONFIG = config.config
AB = AbClient()


def process_leaf(path: Path, args: argparse.Namespace) -> None:
    try:
        llm_threshold = int(getattr(args, "llm_threshold", 85))
    except (TypeError, ValueError):
        llm_threshold = 85
    llm_threshold = max(80, min(100, llm_threshold))
    setattr(args, "llm_threshold", llm_threshold)

    # Preview runs the whole pipeline -- lookups, refinement, validation -- and
    # withholds only the writes, so "preview" actually shows what would happen.
    # Defaults True so callers that omit the flag keep the old behaviour.
    commit = bool(getattr(args, "commit", True))

    if path.name == "Unknown Author" or path.parent.name == "Unknown Author":
        rprint("- skip Unknown Author:", path)
        log("SKIP", str(path))
        return

    if args.striptags:
        targets = (
            [path]
            if path.is_file()
            else [f for f in path.rglob("*") if f.suffix.lower() in constants.AUDIO_EXTS]
        )
        if not commit:
            rprint(f"[cyan]->[/] {path}  [dim]would strip tags from {len(targets)} file(s)[/]")
            return
        ok = 0
        for target in targets:
            try:
                strip_tags(target)
                ok += 1
            except MutagenError:
                log("ERR", f"strip {target}")
        rprint(f"[cyan]->[/] {path}  [green]tags stripped ({ok}/{len(targets)})[/]")
        log("STRIP", f"{path}  ({ok}/{len(targets)})")
        return

    a_guess, t_guess, y_guess, s_guess, si_guess = guess_from_path(path)
    rprint(f"[cyan]->[/] {path}")
    rprint(f"  guess: [italic]{t_guess}[/] by {a_guess or '?'} ({y_guess or '?'})")
    if s_guess:
        rprint(f"  series: {s_guess} #{si_guess or '?'}")

    if path.is_file():
        targets = [path] if path.suffix.lower() in constants.AUDIO_EXTS else []
    else:
        targets = sorted(
            [f for f in path.rglob("*") if f.suffix.lower() in constants.AUDIO_EXTS]
        )
    if not targets:
        rprint("  [red]no audio files found[/]")
        log("SKIP", f"{path}  (no audio)")
        return

    folder = path if path.is_dir() else path.parent
    guess_info = {
        "path": str(path),
        "title": t_guess,
        "author": a_guess,
        "year": y_guess,
        "series": s_guess,
        "series_index": si_guess,
    }

    result, scores = best_match(
        a_guess, t_guess, series=s_guess, series_index=si_guess, client=AB
    )
    provider_scores = {name: sc for name, (sc, _) in scores.items()} if scores else {}
    llm_used = False
    refinement_source = None
    best_score: Optional[int] = None

    if not result:
        rprint("  [red] - no match[/]")
        if AB.is_on("use_mcp_refinement"):
            rprint("  [cyan]- attempting MCP refinement[/]")
            mcp_meta = refine_metadata_via_mcp(
                folder, a_guess, t_guess, s_guess, si_guess, 0
            )
            if mcp_meta and mcp_meta.get("score", 0) >= MCP_ACCEPT_SCORE:
                rprint(
                    f"  [magenta]- metadata refined via MCP (score: {mcp_meta['score']})[/]"
                )
                meta = mcp_meta
                llm_used = True
                refinement_source = mcp_meta.get("refinement_source", "mcp_refinement")
            else:
                llm_meta = generate_metadata_via_llm(
                    folder,
                    targets,
                    guess=guess_info,
                    provider_scores=provider_scores,
                )
                if llm_meta:
                    rprint("  [magenta]- metadata supplied by local LLM[/]")
                    meta = llm_meta
                    llm_used = True
                else:
                    rprint("  [yellow]- no metadata found[/]")
                    if commit:
                        log("NOMATCH", str(path))
                        review_log(path, "no_match")
                    return
        else:
            llm_meta = generate_metadata_via_llm(
                folder,
                targets,
                guess=guess_info,
                provider_scores=provider_scores,
            )
            if llm_meta:
                rprint("  [magenta]- metadata supplied by local LLM[/]")
                meta = llm_meta
                llm_used = True
            else:
                rprint("  [yellow]- no metadata found[/]")
                if commit:
                    log("NOMATCH", str(path))
                    review_log(path, "no_match")
                return
    else:
        score, hit = result
        best_score = score
        for name, (sc, _) in sorted(scores.items(), key=lambda item: -item[1][0]):
            rprint(f"    {name}: {sc}")
        author_hit = ", ".join(hit["authors"]) or a_guess or "Unknown"
        rprint(f"  match: [bold]{hit['title']}[/] by {author_hit} ({hit['year'] or '?'})")
        if hit.get("series"):
            rprint(f"  series: {hit['series']}")
        rprint(f"  provider: {hit['source']}")
        if score < 60:
            rprint("  [yellow]!! low confidence - double-check[/]")
        meta = {
            "title": hit["title"],
            "author": author_hit,
            "year": hit["year"],
            "series": hit.get("series") or s_guess,
            "series_index": hit.get("series_index") or si_guess,
        }
        meta = enrich_metadata_with_providers(meta)

        if best_score is not None and best_score < llm_threshold:
            if AB.is_on("use_mcp_refinement") and best_score < 90:
                rprint("  [cyan]- attempting MCP refinement (low score)[/]")
                mcp_meta = refine_metadata_via_mcp(
                    folder,
                    a_guess,
                    t_guess,
                    s_guess,
                    si_guess,
                    best_score or 0,
                    meta,
                )
                if mcp_meta and mcp_meta.get("score", 0) >= MCP_ACCEPT_SCORE:
                    rprint(
                        f"  [magenta]- metadata refined via MCP (score: {mcp_meta['score']})[/]"
                    )
                    meta = mcp_meta
                    llm_used = True
                    refinement_source = mcp_meta.get(
                        "refinement_source", "mcp_refinement"
                    )
                else:
                    llm_meta = generate_metadata_via_llm(
                        folder,
                        targets,
                        guess=guess_info,
                        provider_scores=provider_scores,
                    )
                    if llm_meta:
                        rprint(
                            f"  [magenta]- metadata supplied by local LLM (score {best_score} < {llm_threshold})[/]"
                        )
                        meta = llm_meta
                        llm_used = True
            else:
                llm_meta = generate_metadata_via_llm(
                    folder,
                    targets,
                    guess=guess_info,
                    provider_scores=provider_scores,
                )
                if llm_meta:
                    rprint(
                        f"  [magenta]- metadata supplied by local LLM (score {best_score} < {llm_threshold})[/]"
                    )
                    meta = llm_meta
                    llm_used = True

        # Gate on the configured threshold, not a hardcoded 70. Previously a
        # match scoring between 70 and --llm-threshold whose LLM fallback had
        # failed was tagged with no prompt at all, and --no was silently a
        # no-op for anything >= 70 because the check below sat inside this
        # guard. --yes still bypasses the prompt entirely.
        if not llm_used and best_score is not None and best_score < llm_threshold and not args.yes:
            score_val = (
                f"{best_score:.1f}" if isinstance(best_score, float) else str(best_score)
            )
            summary_lines = [
                "Tag with this metadata?",
                "",
                f"Title   : {meta.get('title') or 'Unknown'}",
                f"Author  : {meta.get('author') or 'Unknown'}",
            ]
            if meta.get("series"):
                summary_lines.append(f"Series  : {meta['series']}")
            if meta.get("year"):
                summary_lines.append(f"Year    : {meta['year']}")
            summary_lines.append(f"Provider: {hit.get('source', '?')}")
            summary_lines.append(f"Score   : {score_val} (threshold {llm_threshold})")
            summary_lines.append(f"Path    : {path}")
            prompt_message = "\n".join(summary_lines)
            if args.no:
                proceed = False
            else:
                # Every Confirm in play exposes .ask -- rich's classmethod, the
                # console fallback's staticmethod, and the GUI's _GuiConfirm
                # instance. The old `else: Confirm(...)` branch was therefore
                # unreachable, and would have raised if it ever ran.
                proceed = Confirm.ask(prompt_message, default=False)
            if not proceed:
                rprint("  [yellow]- declined[/]")
                if commit:
                    log("SKIP", str(path))
                    review_log(path, "user_skip")
                return

    valid, validation_issues = validate_metadata_fields(meta)
    if valid and validation_issues:
        # Advisory only -- worth showing, but not a reason to refuse a book
        # whose title and author are sound.
        rprint(f"  [yellow]- metadata notes: {', '.join(validation_issues)}[/]")
    if not valid:
        issues_text = ", ".join(validation_issues)
        rprint(f"  [yellow]- metadata validation failed: {issues_text}")
        validation_refined = False
        if AB.is_on("use_mcp_refinement") and not llm_used:
            rprint("  [cyan]- attempting MCP refinement (validation)")
            initial_score = (
                best_score if best_score is not None else meta.get("score", 0) or 0
            )
            mcp_meta = refine_metadata_via_mcp(
                folder,
                a_guess,
                t_guess,
                s_guess,
                si_guess,
                initial_score,
                meta,
            )
            if mcp_meta:
                meta = mcp_meta
                llm_used = True
                refinement_source = mcp_meta.get(
                    "refinement_source", "mcp_refinement"
                )
                validation_refined = True
                valid, validation_issues = validate_metadata_fields(meta)
        if not valid:
            issues_text = ", ".join(validation_issues)
            rprint("  [red]- validation failed; book queued for review")
            if commit:
                log("REVIEW", f"{path} validation_failed: {issues_text}")
                review_log(path, "validation_failed")
            return
        if validation_refined:
            rprint("  [magenta]- metadata passed validation after refinement[/]")

    suffix_parts: List[str] = []
    if llm_used:
        suffix_parts.append(f"[MCP-{refinement_source}]" if refinement_source else "[LLM]")

    if meta.get("score"):
        score_info = f"score={meta['score']}"
        if meta.get("series_index"):
            score_info += f" series={meta['series_index']}"
        suffix_parts.append(f"[{score_info}]")

    suffix = " " + " ".join(suffix_parts) if suffix_parts else ""
    meta_summary = format_metadata_summary(meta)

    if not commit:
        # Preview: everything above ran for real -- guess, provider scores,
        # match, refinement -- so the user can see what *would* be written.
        # Only the writes are withheld.
        rprint(f"  [dim]would tag {len(targets)} file(s):[/] {meta_summary}{suffix}")
        rprint(f"  [dim]would write metadata.json + book.nfo in[/] {path}")
        return

    ok = 0
    for idx, target in enumerate(targets, 1):
        try:
            write_tags(target, meta, idx, len(targets))
            ok += 1
        except (MutagenError, MP4StreamInfoError):
            log("ERR", f"tag {target}")

    label = "OK" if ok == len(targets) else "ERR"
    rprint(f"  [green]tagged {ok}/{len(targets)} file(s)[/]")
    log(label, f"{path}  ({ok}/{len(targets)}){suffix} | {meta_summary}")

    if label == "OK":
        export_metadata(path, meta)


def walk_leaves(root: Path) -> List[Path]:
    """Find book folders at or below `root`.

    `root` itself is a candidate: `rglob` only yields descendants, so with
    `--recurse` pointed straight at a single book folder nothing was found.
    """
    if root.is_file():
        return [root]
    leaves: List[Path] = []
    for candidate in [root, *root.rglob("*")]:
        if candidate.is_dir() and has_audio(candidate) and not any(
            child.is_dir() and has_audio(child) for child in candidate.iterdir()
        ):
            leaves.append(candidate)
    return leaves


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Tag or strip audiobook files.",
        epilog=textwrap.dedent(
            f"""\
            flags
            -----
              --recurse     walk sub-folders that hold audio
              --commit      actually write changes
              --yes         auto-accept matches (tag mode)
              --no          auto-decline matches (tag mode)
              --striptags   delete *all* tags instead of adding
              --llm-endpoint URL   OpenAI-compatible endpoint (default: {constants.DEFAULT_LLM_ENDPOINT})
              --llm-model NAME     model to request from the endpoint (default: {constants.DEFAULT_LLM_MODEL_NAME})
              --llm-threshold SCORE  confidence score before using the LLM (default: 85)
              --llm-api-key KEY    bearer token for a hosted endpoint (e.g. OpenRouter)
            """
        ),
    )
    parser.add_argument("root", type=Path, help="file or folder")
    parser.add_argument(
        "--debug", action="store_true", help="print full tracebacks on errors"
    )
    parser.add_argument("--recurse", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no", action="store_true")
    parser.add_argument("--striptags", action="store_true")
    parser.add_argument(
        "--llm-endpoint",
        default=constants.DEFAULT_LLM_ENDPOINT,
        help="OpenAI-compatible completion endpoint (use 'none' to disable; default: %(default)s)",
    )
    parser.add_argument(
        "--llm-model",
        default=constants.DEFAULT_LLM_MODEL_NAME,
        help="Model name to request from the LM Studio endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--llm-threshold",
        type=int,
        default=85,
        metavar="SCORE",
        help="use the local LLM when provider score falls below SCORE (default: 85, minimum: 80)",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        metavar="KEY",
        help=(
            "Bearer token for a hosted OpenAI-compatible endpoint such as "
            "OpenRouter. Prefer the ABTOOLS_LLM_API_KEY or OPENROUTER_API_KEY "
            "environment variable so the key stays out of your shell history."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    CONFIG.debug = args.debug
    base = args.root if args.root.is_dir() else args.root.parent
    config.update_paths(base)

    endpoint_arg = (args.llm_endpoint or "").strip()
    CONFIG.llm_endpoint = None if endpoint_arg.lower() in {"", "none", "null"} else endpoint_arg

    model_arg = (args.llm_model or "").strip()
    CONFIG.llm_model_name = model_arg or None

    # An explicit flag wins; otherwise whatever the environment already put on
    # CONFIG.llm_api_key stands.
    if args.llm_api_key:
        CONFIG.llm_api_key = args.llm_api_key.strip() or None


    args.llm_threshold = max(80, min(100, args.llm_threshold))
    if not args.root.exists():
        sys.exit("path not found")

    items = walk_leaves(args.root) if args.recurse else [args.root]
    for leaf in items:
        try:
            process_leaf(leaf, args)
        except Exception as exc:
            rprint(f"[red]ERR:[/] {leaf} - {exc}")
            if CONFIG.debug:
                import traceback

                tb = traceback.format_exc()
                rprint(tb)
                log("ERR", f"{leaf} - {type(exc).__name__}: {tb.strip()}")
            else:
                log("ERR", f"{leaf} - {type(exc).__name__}")


__all__ = ["main", "process_leaf", "walk_leaves"]
