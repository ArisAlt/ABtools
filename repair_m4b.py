#!/usr/bin/env python3
"""
Quick utility to detect and repair broken M4B/MP4 audiobook files that trigger
``MP4StreamInfoError: only a top-level atom can have zero length`` when tagged.

Usage:
    python repair_m4b.py "path/to/book.m4b"

By default a repaired copy is written alongside the source with `` - fixed``
appended to the filename. Pass ``--overwrite`` to replace the original (a
``.bak`` backup is created first).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from typing import Iterable, Optional

from mutagen.mp4 import MP4, MP4StreamInfoError

VERSION = "1.1"
FILE_PATH = __file__


def detect_zero_length_atom(path: Path) -> bool:
    """
    Return True when the file raises the specific Mutagen error we're interested in.
    """
    try:
        MP4(str(path))
        return False
    except MP4StreamInfoError as exc:
        return "top-level atom" in str(exc).lower()


def run_ffmpeg(input_file: Path, output_file: Path) -> subprocess.CompletedProcess[str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg executable not found in PATH")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_file),
        "-c",
        "copy",
        # Force the container. In --overwrite mode the output is "<name>.m4b.tmp",
        # and ffmpeg cannot infer a format from a ".tmp" extension.
        "-f",
        "mp4",
        str(output_file),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def repair_file(path: Path, *, overwrite: bool) -> dict[str, Optional[str]]:
    """
    Attempt to repair the supplied file.

    Returns a dictionary describing the outcome:
      - status: "clean", "repaired"
      - path: original file path
      - output: repaired file path (for non-overwrite mode)
      - backup: backup file path (when overwrite replaces the original)
      - message: optional diagnostic text
    """
    result: dict[str, Optional[str]] = {"path": str(path)}
    needs_repair = detect_zero_length_atom(path)
    if not needs_repair:
        result["status"] = "clean"
        result["message"] = "File parses correctly; no repair needed."
        return result

    if overwrite:
        temp_output = path.with_suffix(path.suffix + ".tmp")
    else:
        temp_output = path.with_name(path.stem + " - fixed" + path.suffix)

    if temp_output.exists():
        temp_output.unlink()

    proc = run_ffmpeg(path, temp_output)
    if proc.returncode != 0:
        if temp_output.exists():
            temp_output.unlink()
        raise RuntimeError(
            proc.stderr.strip() or "ffmpeg failed while attempting to repair the file"
        )

    if overwrite:
        backup = path.with_suffix(path.suffix + ".bak")
        counter = 1
        while backup.exists():
            backup = path.with_suffix(path.suffix + f".bak{counter}")
            counter += 1
        path.rename(backup)
        temp_output.rename(path)
        result.update(
            {
                "status": "repaired",
                "backup": str(backup),
                "message": f"Repaired in-place; backup saved as {backup}",
            }
        )
    else:
        result.update(
            {
                "status": "repaired",
                "output": str(temp_output),
                "message": f"Repaired copy written to {temp_output}",
            }
        )
    return result


def iter_targets(root: Path) -> Iterable[Path]:
    """
    Yield all candidate files beneath ``root`` (or the file itself).
    """
    if root.is_file():
        yield root
        return
    for suffix in (".m4b", ".mp4"):
        yield from sorted(root.rglob(f"*{suffix}"))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Detect and repair M4B/MP4 files that raise 'only a top-level atom can have zero length'."
        )
    )
    ap.add_argument("path", type=Path, help="Path to a .m4b/.mp4 file or a directory")
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace originals in-place (a .bak backup is created first). Default: write repaired copy alongside source.",
    )
    ap.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s v{VERSION} ({FILE_PATH})",
    )
    args = ap.parse_args()

    root_path: Path = args.path.expanduser()
    if not root_path.exists():
        raise SystemExit(f"Path not found: {root_path}")

    overwrite = args.overwrite
    targets = list(iter_targets(root_path))
    if not targets:
        print("No .m4b or .mp4 files found.")
        return

    repaired = 0
    cleaned = 0
    failures: list[tuple[Path, str]] = []

    for file_path in targets:
        try:
            outcome = repair_file(file_path, overwrite=overwrite)
        except RuntimeError as exc:
            failures.append((file_path, str(exc)))
            print(f"[ERROR] {file_path}: {exc}")
            continue

        status = outcome.get("status")
        message = outcome.get("message") or ""
        if status == "clean":
            cleaned += 1
            print(f"[OK] {file_path}: {message}")
        elif status == "repaired":
            repaired += 1
            if message:
                print(f"[FIXED] {file_path}: {message}")
        else:
            print(f"[WARN] {file_path}: unexpected outcome {status}")

    summary = (
        f"Completed. Repaired: {repaired}, Clean: {cleaned}, "
        f"Failed: {len(failures)}"
    )
    print(summary)
    if failures:
        print("Failures:")
        for file_path, error in failures:
            print(f"  - {file_path}: {error}")


if __name__ == "__main__":
    main()
