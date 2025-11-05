from __future__ import annotations

from pathlib import Path
import contextlib
import io
from types import SimpleNamespace
from typing import Any, Dict, List

import abtools.cli.main as tag_cli
from abtools.core import config as core_config

CONFIG = tag_cli.CONFIG


def _build_args(root: Path, *, commit: bool, yes: bool) -> SimpleNamespace:
    return SimpleNamespace(
        root=root,
        debug=False,
        recurse=root.is_dir(),
        commit=commit,
        yes=yes,
        no=not yes,
        striptags=False,
        llm_endpoint=core_config.config.llm_endpoint,
        llm_model=core_config.config.llm_model_name,
        llm_threshold=75,
    )


def tag_audiobooks(path: str, *, commit: bool = False, yes: bool = False) -> Dict[str, Any]:
    """Tag audiobook folder using search_and_tag logic."""
    target = Path(path).expanduser()
    if not target.exists():
        return {"error": f"path_not_found:{target}"}

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    def _run() -> Dict[str, Any]:
        args = _build_args(target, commit=commit, yes=yes)
        base = target if target.is_dir() else target.parent
        core_config.update_paths(base)
        CONFIG.debug = False

        if target.is_dir() and args.recurse:
            leaves: List[Path] = tag_cli.walk_leaves(target)
        else:
            leaves = [target]

        processed: List[str] = []
        errors: List[Dict[str, str]] = []

        for leaf in leaves:
            if not commit:
                processed.append(str(leaf))
                continue
            try:
                tag_cli.process_leaf(leaf, args)
                processed.append(str(leaf))
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append({"path": str(leaf), "error": str(exc)})

        status = "tagged" if commit else "preview"
        result: Dict[str, Any] = {"status": status, "processed": processed}
        if errors:
            result["errors"] = errors
        return result

    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            outcome = _run()
    except Exception as exc:  # pragma: no cover - defensive guard
        outcome = {
            "error": f"tagger_failed:{type(exc).__name__}",
            "detail": str(exc),
        }

    stdout_text = stdout_buf.getvalue().strip()
    stderr_text = stderr_buf.getvalue().strip()
    if stdout_text:
        outcome["stdout"] = stdout_text
    if stderr_text:
        outcome["stderr"] = stderr_text
    return outcome
