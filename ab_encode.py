"""
ab_encode.py  –  Audiobook M4B Builder with Auto-Verification & Cleanup.

Scans a root directory for subfolders containing audio files, concatenates
each folder into a single .m4b audiobook using FFmpeg, verifies the output
with ffprobe, and optionally deletes the source files.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from functools import partial
from typing import List

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
VERSION = "1.3"
FILE_PATH = os.path.abspath(__file__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
EXTENSIONS: tuple[str, ...] = (".mp3", ".wav", ".flac", ".m4a", ".ogg")

log = logging.getLogger("ab_encode")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_tools() -> None:
    """Abort early with a clear message if ffmpeg or ffprobe are not on PATH."""
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        sys.exit(f"❌ Missing required tool(s): {', '.join(missing)}. Install FFmpeg and ensure it is on PATH.")


def natural_sort_key(s: str) -> List[int | str]:
    """Sort key that orders '2' before '10' (numeric-aware)."""
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", s)]


def verify_audio(file_path: str) -> bool:
    """Return True when ffprobe confirms the file contains a valid audio stream with positive duration."""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        file_path,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip()) > 0
    except (subprocess.CalledProcessError, ValueError):
        return False


def is_aac_codec(file_path: str) -> bool:
    """Return True if the primary audio stream is encoded as AAC."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name",
        "-of", "default=nw=1:nk=1",
        file_path,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout.strip().lower() == "aac"
    except (subprocess.CalledProcessError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Core encoder
# ---------------------------------------------------------------------------

def process_folder(root: str, *, bitrate: str, channels: str, cleanup: bool) -> dict[str, str]:
    """Encode all audio files in *root* into a single .m4b audiobook.

    Returns a result dict with keys ``status`` and ``folder``.
    """
    folder_contents = os.listdir(root)
    source_files = sorted(
        [f for f in folder_contents if f.lower().endswith(EXTENSIONS)],
        key=natural_sort_key,
    )

    # Check for an existing .m4b file
    existing_m4b = None
    for f in folder_contents:
        if f.lower().endswith(".m4b"):
            existing_m4b = os.path.join(root, f)
            break

    # If there are no audio sources, the only thing here is the existing M4B (if any)
    if not source_files and not existing_m4b:
        return {"status": "⏩ Skipped (Empty)", "folder": root}

    if existing_m4b:
        if is_aac_codec(existing_m4b):
            return {"status": "⏩ Skipped (AAC M4B Exists)", "folder": root}
        else:
            log.info("Non-AAC M4B detected in '%s'. Re-encoding to AAC.", root)
            # If the only audio file is the non-AAC M4B itself, use it as the sole source
            if not source_files:
                source_files = [os.path.basename(existing_m4b)]
            elif os.path.basename(existing_m4b) not in source_files:
                # We have other source files (like raw mp3s) AND a non-AAC m4b.
                # In this case, we'll re-build from the original source files and just 
                # overwrite the bad M4B. We don't want to re-encode the bad M4B if we have sources.
                pass

    folder_name = os.path.basename(root)
    output_path = os.path.join(root, f"{folder_name}.m4b")
    # Write to a temporary file in case we are overwriting an existing M4B of the same name
    temp_output_path = output_path + ".tmp"

    # Write the ffmpeg concat list to a secure temp file to avoid filename issues
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", dir=root, delete=False, encoding="utf-8"
    ) as tmp:
        list_file = tmp.name
        for audio in source_files:
            abs_path = os.path.abspath(os.path.join(root, audio))
            # Escape single-quotes for the ffmpeg concat format
            safe_path = abs_path.replace("'", "'\\''")
            tmp.write(f"file '{safe_path}'\n")

    # Smart Passthrough: If all sources are already AAC, we can just copy them
    # without degrading audio quality or wasting CPU cycles.
    can_copy = True
    for audio in source_files:
        ext = os.path.splitext(audio)[1].lower()
        if ext not in (".m4a", ".m4b", ".mp4"):
            can_copy = False
            break
        if not is_aac_codec(os.path.join(root, audio)):
            can_copy = False
            break

    if can_copy:
        log.info("Smart Passthrough enabled for '%s'. Stream will be copied losslessly.", root)
        audio_flags = ["-c:a", "copy"]
    else:
        audio_flags = ["-c:a", "aac", "-b:a", bitrate, "-ac", channels, "-ar", "44100"]

    cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        # Tolerate VBR / missing-header frames at file join points
        "-err_detect", "ignore_err",
        "-fflags", "+discardcorrupt",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        *audio_flags,
        "-vn",  # Ignore embedded album art / video streams that crash the encoder
        "-threads", "1",  # Prevent thread thrashing since we are running in a ThreadPoolExecutor
        "-metadata", f"title={folder_name}",
        "-movflags", "+faststart",
        "-f", "mp4",
        temp_output_path,
    ]

    try:
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

        # Verify the output before replacing originals
        if verify_audio(temp_output_path):
            # Atomically replace the final output file
            os.replace(temp_output_path, output_path)

            if cleanup:
                failed: List[str] = []
                for audio in source_files:
                    # Don't try to delete the file we just encoded TO if it was the only source
                    if os.path.abspath(os.path.join(root, audio)) == output_path:
                        continue
                    try:
                        os.remove(os.path.join(root, audio))
                    except OSError as exc:
                        failed.append(f"{audio} ({exc})")
                if failed:
                    log.warning("Could not delete: %s", ", ".join(failed))
                    return {"status": "⚠️ Success (Some Sources Not Deleted)", "folder": folder_name}
                return {"status": "✅ Success & Sources Deleted", "folder": folder_name}
            return {"status": "✅ Success (Sources Kept)", "folder": folder_name}
        else:
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
            return {"status": "⚠️ Verification Failed", "folder": folder_name}

    except subprocess.CalledProcessError as exc:
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        # log is now handled by the main thread to avoid breaking the Progress display
        return {"status": "❌ Encoding Error", "folder": folder_name, "error_code": str(exc.returncode)}

    finally:
        # Always clean up the temporary concat list
        try:
            os.remove(list_file)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="🎧 Audiobook M4B Builder with Auto-Verification & Cleanup.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("directory", help="Root directory containing audiobook sub-folders.")
    parser.add_argument("-b", "--bitrate", default="64k", help="AAC bitrate (e.g. 64k, 128k).")
    parser.add_argument(
        "-c", "--channels", default="1", choices=["1", "2"],
        help="Audio channels: 1=Mono, 2=Stereo.",
    )
    parser.add_argument("-w", "--workers", type=int, default=4, help="Parallel encoding workers.")
    parser.add_argument(
        "--cleanup", action="store_true",
        help="⚠️ DANGER: delete source audio files after successful verification.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{VERSION} ({FILE_PATH})",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug-level logging.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    _check_tools()

    target_dir = os.path.abspath(args.directory)
    if not os.path.isdir(target_dir):
        sys.exit(f"❌ Error: Directory '{target_dir}' does not exist.")

    tasks: List[str] = []
    for root, _, files in os.walk(target_dir):
        if any(f.lower().endswith(EXTENSIONS) for f in files):
            tasks.append(root)

    if not tasks:
        print("ℹ️  No audio files found. Nothing to do.")
        return

    print(f"🚀 Processing: {target_dir}")
    print(f"⚙️  Folders: {len(tasks)} | Workers: {args.workers} | Cleanup: {'ON ⚠️' if args.cleanup else 'OFF'}")

    worker_func = partial(process_folder, bitrate=args.bitrate, channels=args.channels, cleanup=args.cleanup)

    results: list[dict[str, str]] = []
    
    # Map futures back to folder names so we can label the bar
    future_to_folder: dict[Future[dict[str, str]], str] = {}
    active_futures: set[Future[dict[str, str]]] = set()
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for task in tasks:
            future = executor.submit(worker_func, task)
            future_to_folder[future] = os.path.basename(task)
            active_futures.add(future)

        if tqdm is not None:
            bar = tqdm(
                total=len(tasks),
                unit="folder",
                dynamic_ncols=True,
                smoothing=0.1,  # heavily weight recent slow encodes, ignore initial fast skips
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            )
            
            # Background thread to keep the progress bar description lively
            stop_monitor = threading.Event()
            def monitor_progress() -> None:
                while not stop_monitor.is_set():
                    with lock:
                        running = [future_to_folder[f][:20] for f in active_futures if f.running()]
                    if running:
                        # Show up to 3 currently running items
                        desc = ", ".join(running[:3])
                        if len(running) > 3:
                            desc += "..."
                        bar.set_description(f"⚙️ {desc}")
                    time.sleep(0.5)
            
            monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
            monitor_thread.start()
        else:
            bar = None

        done = 0
        try:
            for future in as_completed(future_to_folder):
                folder_name = future_to_folder[future]
                result = future.result()
                results.append(result)
                done += 1
                
                if "error_code" in result:
                    log.error("FFmpeg failed for '%s': exit code %s", folder_name, result["error_code"])
                
                if bar is not None:
                    with lock:
                        active_futures.remove(future)
                    bar.update(1)
                else:
                    print(f"  [{done}/{len(tasks)}] {result['status']} — {folder_name}")

        except KeyboardInterrupt:
            if bar is not None:
                stop_monitor.set()
                monitor_thread.join(timeout=1.0)
                bar.set_description("🛑 Cancelled")
                bar.close()
            print("\n⚠️  Encoding interrupted by user (Ctrl+C). Shutting down...")
            # Cancel any pending futures that haven't started yet
            executor.shutdown(wait=False, cancel_futures=True)
            sys.exit(130)

        finally:
            if bar is not None and not stop_monitor.is_set():
                stop_monitor.set()
                monitor_thread.join(timeout=1.0)
                bar.set_description("✔ Done")
                bar.close()

    # Group results by status
    summary: dict[str, List[str]] = defaultdict(list)
    for res in results:
        summary[res["status"]].append(res["folder"])

    print("\n📊 FINAL EXECUTION REPORT:")
    print("-" * 40)
    for status, folders in sorted(summary.items()):
        print(f"\n  {status} ({len(folders)}):")
        for folder in folders:
            print(f"    • {folder}")
    print()


if __name__ == "__main__":
    main()
