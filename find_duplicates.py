#!/usr/bin/env python3
"""
ABtools/find_duplicates.py - v0.5 (2025-09-08)
Find duplicate audio files by comparing SHA1 hashes or file names.

Usage:
  - Single folder scan (within-folder duplicates):
      python find_duplicates.py ROOT [--by hash|name]

  - Cross compare two folders (duplicates that exist in both):
      python find_duplicates.py SRC DST [--by hash|name]

Results are written to ``duplicate_log.txt`` in the chosen root folder
(or the source folder when comparing two roots). Use ``--version`` to
print the script version and file path. Shows progress with tqdm when
installed, otherwise inline counters. Hashing skips files with unique
sizes for faster scans.
"""

from __future__ import annotations
import argparse, hashlib, sys, multiprocessing as mp, threading
from pathlib import Path
from collections import defaultdict
from contextlib import contextmanager
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

VERSION = "0.5"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"%(prog)s v{VERSION} ({FILE_PATH})"

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}

DUP_LOG = Path("duplicate_log.txt")

# Optional pretty progress bars
try:  # pragma: no cover - optional dependency
    from tqdm import tqdm  # type: ignore
except Exception:  # pragma: no cover - if tqdm not installed
    tqdm = None  # type: ignore


@contextmanager
def progress_bar(total: int, desc: str):
    """Yield an update(n) function that advances progress.

    Uses tqdm when available; otherwise prints inline counters.
    """
    if total <= 0:
        yield (lambda n=1: None)
        return
    if tqdm is not None:
        bar = tqdm(total=total, desc=desc, unit='file', leave=False)
        try:
            yield lambda n=1: bar.update(n)
        finally:
            bar.close()
    else:
        done = {'n': 0}
        def _upd(n: int = 1) -> None:
            done['n'] += n
            print(f"\r{desc}: {done['n']}/{total}...", end='', flush=True)
        try:
            yield _upd
        finally:
            print()


def is_audio(p: Path) -> bool:
    return p.suffix.lower() in AUDIO_EXTS


def sha1sum(path: Path) -> str:
    h = hashlib.sha1()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_worker(path_str: str, q):  # pragma: no cover - child process
    try:
        p = Path(path_str)
        h = hashlib.sha1()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        q.put(h.hexdigest())
    except Exception:
        q.put("__ERROR__")


def sha1sum_with_timeout(path: Path, timeout_s: float) -> str:
    """Compute sha1 with a per-file timeout. timeout_s <= 0 disables timeout.

    Uses a child process so we can safely terminate on timeout (important
    for flaky network shares that can hang on reads).
    """
    if timeout_s <= 0:
        return sha1sum(path)
    ctx = mp.get_context('spawn')
    q = ctx.Queue(1)
    proc = ctx.Process(target=_hash_worker, args=(str(path), q))
    proc.start()
    proc.join(timeout_s)
    if proc.is_alive():
        try:
            proc.terminate()
        finally:
            proc.join()
        raise TimeoutError(f"read timeout after {timeout_s:.0f}s")
    try:
        res = q.get_nowait()
    except Exception:
        raise OSError("hash worker failed")
    if res == "__ERROR__":
        raise OSError("hash worker error")
    return res


def _is_unc_path(p: Path) -> bool:
    s = str(p)
    return s.startswith('\\\\') or s.startswith('//')


def _iter_audio_files(
    root: Path,
    on_file: Optional[Callable[[str, Path], None]] = None,
    stage: str = 'enum',
    limit_paths: Optional[set[Path]] = None,
    recursive: bool = True,
    stop_event: Optional["threading.Event"] = None,
) -> list[Path]:
    def _is_subpath(child: Path, parent: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except Exception:
            return False

    files: list[Path] = []
    if limit_paths:
        for p in limit_paths:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                if p.exists() and p.is_file() and is_audio(p) and _is_subpath(p, root):
                    _notify(on_file, stage, p)
                    files.append(p)
            except Exception:
                continue
        return files

    it = root.rglob("*") if recursive else root.iterdir()
    for p in it:
        if stop_event is not None and stop_event.is_set():
            break
        if p.is_file() and is_audio(p):
            _notify(on_file, stage, p)
            files.append(p)
    return files


def _read_paths_from_log(log_path: Path) -> set[Path]:
    paths: set[Path] = set()
    if not log_path.exists():
        return paths
    try:
        for line in log_path.read_text(encoding='utf-8', errors='ignore').splitlines():
            s = line.rstrip("\n\r")
            if s.startswith("  "):
                p = s.strip()
                if p.startswith("-"):
                    p = p.lstrip("- ")
                try:
                    paths.add(Path(p))
                except Exception:
                    pass
    except Exception:
        return paths
    return paths


def _group_by_folder(dupes: dict[str, list[Path]]) -> dict[Path, dict[str, list[Path]]]:
    """Reindex dupes as folder -> key -> [paths in that folder]."""
    folders: dict[Path, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    for key, paths in dupes.items():
        for p in paths:
            folders[p.parent][key].append(p)
    # sort paths within each group for stable output
    for folder in folders:
        for key in folders[folder]:
            folders[folder][key] = sorted(folders[folder][key])
    return dict(sorted(folders.items(), key=lambda kv: str(kv[0]).lower()))


def _print_and_write_grouped(dupes: dict[str, list[Path]], label: str, log_file: Path, header: Optional[str] = None) -> None:
    """Print and write duplicates grouped by parent folder."""
    folders = _group_by_folder(dupes)
    if header:
        print(header)
    for folder, by_key in folders.items():
        print(f"\nFolder {folder}")
        for key, paths in by_key.items():
            print(f"  {label} {key}")
            for p in paths:
                print(f"    {p}")
    # write log
    with log_file.open("w", encoding="utf-8") as fh:
        if header:
            fh.write(header + "\n\n")
        for folder, by_key in folders.items():
            fh.write(f"Folder {folder}\n")
            for key, paths in by_key.items():
                fh.write(f"  {label} {key}\n")
                for p in paths:
                    fh.write(f"    {p}\n")
            fh.write("\n")


def _notify(cb: Optional[Callable[[str, Path], None]], stage: str, p: Path) -> None:
    if cb is None:
        return
    try:
        cb(stage, p)
    except Exception:
        pass


def find_dupes(
    root: Path,
    by: str = 'hash',
    hash_timeout: float | None = None,
    on_file: Optional[Callable[[str, Path], None]] = None,
    threads: int = 4,
    limit_paths: Optional[set[Path]] = None,
    recursive: bool = True,
    stop_event: Optional["threading.Event"] = None,
) -> dict[str, list[Path]]:
    files = _iter_audio_files(
        root,
        on_file=on_file,
        stage='enum',
        limit_paths=limit_paths,
        recursive=recursive,
        stop_event=stop_event,
    )
    if stop_event is not None and stop_event.is_set():
        return {}
    total = len(files)
    if by == 'name':
        groups: dict[str, list[Path]] = defaultdict(list)
        with progress_bar(total, 'Grouping by name') as upd:
            for p in files:
                if stop_event is not None and stop_event.is_set():
                    return {}
                _notify(on_file, 'name', p)
                groups[p.name].append(p)
                upd(1)
        return {k: v for k, v in groups.items() if len(v) > 1}

    # group by file size first to avoid hashing uniques
    size_map: dict[int, list[Path]] = defaultdict(list)
    with progress_bar(total, 'Scanning files') as upd:
        for p in files:
            if stop_event is not None and stop_event.is_set():
                return {}
            try:
                _notify(on_file, 'scan', p)
                size_map[p.stat().st_size].append(p)
            except OSError as e:
                print(f"\nCould not stat {p}: {e}", file=sys.stderr)
            upd(1)

    hashes: dict[str, list[Path]] = defaultdict(list)
    # Auto-timeout for UNC paths unless overridden
    timeout_s = 30.0 if (hash_timeout is None and _is_unc_path(root)) else (hash_timeout or 0.0)
    work = [p for g in size_map.values() if len(g) > 1 for p in g]
    to_hash = len(work)

    def _task(p: Path):
        if stop_event is not None and stop_event.is_set():
            return ('CANCEL', '', p)
        try:
            _notify(on_file, 'hash', p)
            d = sha1sum_with_timeout(p, timeout_s)
            return ('OK', d, p)
        except TimeoutError as e:
            return ('TIMEOUT', str(e), p)
        except OSError as e:
            return ('ERROR', str(e), p)

    with progress_bar(to_hash, 'Hashing candidates') as upd:
        if to_hash:
            with ThreadPoolExecutor(max_workers=max(1, int(threads or 1))) as ex:
                futures = [ex.submit(_task, p) for p in work]
                for fut in as_completed(futures):
                    status, payload, p = fut.result()
                    if stop_event is not None and stop_event.is_set():
                        for pending in futures:
                            pending.cancel()
                        return {}
                    if status == 'CANCEL':
                        return {}
                    if status == 'OK':
                        hashes[payload].append(p)
                    else:
                        print(f"Could not read {p}: {payload}", file=sys.stderr)
                    upd(1)
    return {k: v for k, v in hashes.items() if len(v) > 1}


def find_cross_dupes(
    src: Path,
    dst: Path,
    by: str = "hash",
    hash_timeout: float | None = None,
    on_file: Optional[Callable[[str, Path], None]] = None,
    threads: int = 4,
    limit_src: Optional[set[Path]] = None,
    recursive: bool = True,
    stop_event: Optional["threading.Event"] = None,
) -> dict[str, list[Path]]:
    """Find duplicates that exist in BOTH ``src`` and ``dst``.

    Returns a dict mapping match key (sha1 or name) to a combined list of
    files from both roots. Only keys present in both sides are returned.
    """
    src_files = _iter_audio_files(
        src,
        on_file=on_file,
        stage='enum-src',
        limit_paths=limit_src,
        recursive=recursive,
        stop_event=stop_event,
    )
    if stop_event is not None and stop_event.is_set():
        return {}
    dst_files = _iter_audio_files(
        dst,
        on_file=on_file,
        stage='enum-dst',
        recursive=recursive,
        stop_event=stop_event,
    )
    if stop_event is not None and stop_event.is_set():
        return {}

    # Name-based matching is straightforward
    if by == 'name':
        src_by_name: dict[str, list[Path]] = defaultdict(list)
        dst_by_name: dict[str, list[Path]] = defaultdict(list)
        with progress_bar(len(src_files) + len(dst_files), 'Indexing names') as upd:
            for p in src_files:
                if stop_event is not None and stop_event.is_set():
                    return {}
                _notify(on_file, 'name-src', p)
                src_by_name[p.name].append(p)
                upd(1)
            for p in dst_files:
                if stop_event is not None and stop_event.is_set():
                    return {}
                _notify(on_file, 'name-dst', p)
                dst_by_name[p.name].append(p)
                upd(1)
        keys = src_by_name.keys() & dst_by_name.keys()
        return {k: src_by_name[k] + dst_by_name[k] for k in sorted(keys)}

    # Hash-based matching with size pre-filtering to minimize hashing
    src_sizes: dict[int, list[Path]] = defaultdict(list)
    dst_sizes: dict[int, list[Path]] = defaultdict(list)
    for p in src_files:
        if stop_event is not None and stop_event.is_set():
            return {}
        try:
            _notify(on_file, 'scan-src', p)
            src_sizes[p.stat().st_size].append(p)
        except OSError as e:
            print(f"Could not stat {p}: {e}", file=sys.stderr)
    for p in dst_files:
        if stop_event is not None and stop_event.is_set():
            return {}
        try:
            _notify(on_file, 'scan-dst', p)
            dst_sizes[p.stat().st_size].append(p)
        except OSError as e:
            print(f"Could not stat {p}: {e}", file=sys.stderr)

    candidate_sizes = {s for s, v in src_sizes.items() if v} & {s for s, v in dst_sizes.items() if v}
    if not candidate_sizes:
        return {}

    # Hash only files whose size exists on both sides
    src_hashes: dict[str, list[Path]] = defaultdict(list)
    dst_hashes: dict[str, list[Path]] = defaultdict(list)

    src_candidates = [p for s in candidate_sizes for p in src_sizes[s]]
    dst_candidates = [p for s in candidate_sizes for p in dst_sizes[s]]
    timeout_s_src = 30.0 if (hash_timeout is None and _is_unc_path(src)) else (hash_timeout or 0.0)
    timeout_s_dst = 30.0 if (hash_timeout is None and _is_unc_path(dst)) else (hash_timeout or 0.0)

    total = len(src_candidates) + len(dst_candidates)

    def _task(p: Path, stage: str, timeout_s: float):
        if stop_event is not None and stop_event.is_set():
            return ('CANCEL', '', p, stage)
        try:
            _notify(on_file, stage, p)
            d = sha1sum_with_timeout(p, timeout_s)
            return ('OK', d, p, stage)
        except TimeoutError as e:
            return ('TIMEOUT', str(e), p, stage)
        except OSError as e:
            return ('ERROR', str(e), p, stage)

    with progress_bar(total, 'Hashing candidates (src+dst)') as upd:
        if total:
            with ThreadPoolExecutor(max_workers=max(1, int(threads or 1))) as ex:
                futures = []
                for p in src_candidates:
                    futures.append(ex.submit(_task, p, 'hash-src', timeout_s_src))
                for p in dst_candidates:
                    futures.append(ex.submit(_task, p, 'hash-dst', timeout_s_dst))
                for fut in as_completed(futures):
                    status, payload, p, stage = fut.result()
                    if stop_event is not None and stop_event.is_set():
                        for pending in futures:
                            pending.cancel()
                        return {}
                    if status == 'OK':
                        if stage == 'hash-src':
                            src_hashes[payload].append(p)
                        else:
                            dst_hashes[payload].append(p)
                    elif status == 'CANCEL':
                        return {}
                    else:
                        print(f"\nCould not read {p}: {payload}", file=sys.stderr)
                    upd(1)

    keys = src_hashes.keys() & dst_hashes.keys()
    return {k: src_hashes[k] + dst_hashes[k] for k in sorted(keys)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description=(
            "Detect duplicate audio files. Provide one folder to find duplicates "
            "within it, or two folders to report duplicates that exist in both."
        )
    )
    ap.add_argument("root", type=Path, help="Root folder to scan (or source when two roots)")
    ap.add_argument("dest", type=Path, nargs="?", help="Optional second folder to compare against")
    ap.add_argument(
        "--by",
        choices=["hash", "name"],
        default="hash",
        help="Compare files by SHA1 hash or file name",
    )
    ap.add_argument(
        "--hash-timeout",
        type=float,
        default=None,
        help=(
            "Per-file read timeout in seconds (0 disables). Default is auto: apply 30s on UNC paths, unlimited otherwise."
        ),
    )
    ap.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Number of hashing threads (default: 4)",
    )
    ap.add_argument(
        "--only-src-log",
        action="store_true",
        help="Limit the scan to files listed in root/duplicate_log.txt on the source",
    )
    ap.add_argument(
        "--show-files",
        action="store_true",
        help="Print per-file 'Checking:' messages during hashing (full path).",
    )
    ap.add_argument("--version", action="version", version=VERSION_INFO)
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        sys.exit(f"{root} is not a directory")

    label = "name" if args.by == "name" else "SHA1"

    def _print_current(stage: str, p: Path) -> None:
        # Quiet by default; enable with --show-files
        if not args.show_files:
            return
        if "hash" not in stage:
            return
        msg = f"Checking: {p}"
        if tqdm is not None:
            try:
                tqdm.write(msg)
                return
            except Exception:
                pass
        print(msg)

    if args.dest:
        dest = args.dest.resolve()
        if not dest.is_dir():
            sys.exit(f"{dest} is not a directory")
        print(f"Comparing {root} <-> {dest} by {args.by}...")
        dupes = find_cross_dupes(
            root,
            dest,
            by=args.by,
            hash_timeout=args.hash_timeout,
            on_file=_print_current,
            threads=args.threads,
        )
        if not dupes:
            print("No cross-duplicates found.")
            sys.exit(0)
        log_file = root / DUP_LOG.name
        _print_and_write_grouped(
            dupes,
            label,
            log_file,
            header=f"Cross-duplicates between {root} and {dest} (by {args.by})",
        )
        print(f"\n{sum(len(v) for v in dupes.values())} files logged to {log_file}")
    else:
        dupes = find_dupes(
            root,
            by=args.by,
            hash_timeout=args.hash_timeout,
            on_file=_print_current,
            threads=args.threads,
        )
        if not dupes:
            print("No duplicates found.")
        else:
            log_file = root / DUP_LOG.name
            _print_and_write_grouped(dupes, label, log_file)
            print(f"\n{sum(len(v) for v in dupes.values())} duplicate files logged to {log_file}")
