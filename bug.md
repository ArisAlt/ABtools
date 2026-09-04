# ABtools Codebase Logic Errors & Bug Report

Comprehensive inventory of logic errors, runtime crashes, protocol incompatibilities, and silent failure modes discovered during the codebase audit of **ABtools**.

**Last updated:** 2026-09-04 — merged findings from a second independent audit; every entry re-verified, three claims refuted. **All four P0 bugs are now fixed and verified.**

## Verification legend

| Mark | Meaning |
|------|---------|
| 🛠️ **Fixed** | Fix applied and verified by an end-to-end test. Fix described inline. |
| ✅ **Verified** | Reproduced by execution, or proven by direct code inspection. Safe to fix as written. |
| ⚠️ **Verified — description corrected** | The bug is real, but the original write-up was inaccurate, overstated, or missed the actual mechanism. Read the correction before fixing. |
| ❌ **Refuted** | The claim is **wrong**. Do not "fix" this — the current code is correct. Evidence given inline. |

> Entries marked ❌ were tested empirically. Applying their suggested "fixes" would **introduce** bugs.

## Priority triage

| Priority | Entry | Why | State |
|---|---|---|---|
| P0 | [2.1](#21-combobookpy-write_tags-executed-during-dry-run--preview) | Preview mode writes tags to the user's source files | 🛠️ Fixed |
| P0 | [3.1](#31-repair_m4bpy--combobookpy-ffmpeg-tmp-output-format-failure-code-234) | `combobook` tag writing fails on 100% of files, with zero diagnostics | 🛠️ Fixed |
| P0 | [1.1](#11-restructure_for_audiobookshelfpy-missing-argument-flag-name-crashes-parser) | `restructure_for_audiobookshelf.py` entirely dead | 🛠️ Fixed |
| P0 | [1.2](#12-abtoolsguipy-incompatible-main-call-when-clicking-restructure-folders) | GUI Restructure button always errors | 🛠️ Fixed |
| P1 | [4.1](#41-combobookpy-leaf_dirs-treats-disc-subfolders-as-separate-audiobooks) / [4.4](#44-flatten_discspy-folders-starting-with-disc-prefix-collide-under-empty-string-) | Multi-disc books lose discs; unrelated books merged together | 🛠️ Fixed |
| P1 | [1.3](#13-mcp_serverserverpy-standard-output-banners-violate-mcp-json-rpc-protocol) | MCP server unusable by any stdio client | 🛠️ Fixed |
| P2 | [5.x](#5-metadata-providers--tagging-logic-errors) | Metadata corruption and crashes on specific inputs | Open |
| P3 | [7.x](#7-edge-cases-type-errors--performance-issues) | Latent / narrow edge cases | Open |
| — | [8](#8-mcp-tool-runtime-verification) | MCP tools executed for real: 3 working, 2 blocked by the remote host | Verified |

> **Fix ordering note (already observed):** 2.1 had to be fixed *before* 3.1. The dry-run tag writes were only harmless while the ffmpeg bug made every write fail. Fixing 3.1 first would have turned a silent no-op into live data modification during preview.

---

## Table of Contents
1. [Fatal Crashes & Broken Entry Points](#1-fatal-crashes--broken-entry-points)
2. [Data Modification & Dry-Run Violations](#2-data-modification--dry-run-violations)
3. [FFmpeg Invocation & Concat Escaping Failures](#3-ffmpeg-invocation--concat-escaping-failures)
4. [File Discovery & Multi-Disc Flaws](#4-file-discovery--multi-disc-flaws)
5. [Metadata, Providers & Tagging Logic Errors](#5-metadata-providers--tagging-logic-errors)
6. [GUI & CLI Synchronization Issues](#6-gui--cli-synchronization-issues)
7. [Edge Cases, Type Errors & Performance Issues](#7-edge-cases-type-errors--performance-issues)
8. [MCP Tool Runtime Verification](#8-mcp-tool-runtime-verification)

---

## 1. Fatal Crashes & Broken Entry Points

### 1.1 `restructure_for_audiobookshelf.py`: Missing Argument Flag Name Crashes Parser
- **Status**: 🛠️ **FIXED (2026-09-04)** — `"--commit"` added to the `add_argument` call. Verified: `python3 restructure_for_audiobookshelf.py --help` now prints usage showing `[--copy] [--commit] [--version]`.
- **File**: [`restructure_for_audiobookshelf.py:145-148`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/restructure_for_audiobookshelf.py#L145-L148)
- **Code**:
  ```python
  parser.add_argument(
      action="store_true",
      help="Perform the move/copy (default is dry-run)",
  )
  ```
- **Error**: `parser.add_argument` is invoked with `action="store_true"` but lacks a flag name (e.g. `"--commit"`).
- **Impact**: Running `python restructure_for_audiobookshelf.py` or `--help` immediately crashes on startup:
  `TypeError: _ActionsContainer._get_positional_kwargs() missing 1 required positional argument: 'dest'`.
  Line 159 subsequently references `args.commit`, which would fail if parsing proceeded. **The entire script is unreachable — no code path in it has ever run.**
- **Fix**: Add `"--commit"` to the `add_argument` invocation:
  ```python
  parser.add_argument(
      "--commit",
      action="store_true",
      help="Perform the move/copy (default is dry-run)",
  )
  ```

### 1.2 `AbtoolsGui.py`: Incompatible `main()` Call When Clicking "Restructure Folders"
- **Status**: 🛠️ **FIXED (2026-09-04)** — the GUI now calls `restructure_library(src, dst, dry=not commit, copy=copy)` and prints a summary line. Verified the call binds cleanly against the real signature. **Known limitation:** `restructure_library` has no cancellation hook, so **Stop** only takes effect once the restructure returns.
- **File**: [`AbtoolsGui.py:642-649`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/AbtoolsGui.py#L642-L649)
- **Code**:
  ```python
  restructure_for_audiobookshelf.main(
      src,
      dst,
      commit=commit_var.get(),
      copy=copy_var.get(),
      interactive=False,
      stop_event=stop_event,
  )
  ```
- **Error**: `restructure_for_audiobookshelf.main` is defined as `def main(argv: list[str] | None = None) -> int:`. It does not accept `src`, `dst`, `commit`, `copy`, `interactive`, or `stop_event`. Note there is **no `interactive` or `stop_event` parameter anywhere** in that module — the GUI is calling an API that has never existed.
- **Impact**: Clicking **Restructure Folders** crashes the worker thread immediately; the `except Exception` handler turns it into an error dialog every time.
- **Independent of 1.1**: fixing the argparse bug alone leaves this button broken. Both must be fixed.
- **Fix**: Call `restructure_library(src, dst, dry=not commit_var.get(), copy=copy_var.get())` directly (it is already a clean, importable function), or build an `argv` list. Stop-event support would need to be added to `restructure_library` if desired.

### 1.3 `mcp_server/server.py`: Standard Output Banners Violate MCP JSON-RPC Protocol
- **Status**: 🛠️ **FIXED (2026-09-04)** — all banner/diagnostic writes moved to `sys.stderr`. Verified with a real stdio handshake (`initialize` → `notifications/initialized` → `tools/list`): every stdout line parses as JSON-RPC, the banner appears only on stderr, and all five tools are advertised. This was the first end-to-end test of the server, since `mcp` had been missing from `requirements.txt`.
- **File**: [`mcp_server/server.py:53-59`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/mcp_server/server.py#L53-L59)
- **Code**:
  ```python
  sys.stdout.write(f"[mcp] starting {MCP_SERVER_NAME} ({MCP_SERVER_VERSION})\n")
  sys.stdout.flush()
  sys.stdout.write("Registered tools: ...\n")
  sys.stdout.flush()
  mcp.run()
  ```
- **Error**: FastMCP uses `sys.stdin` / `sys.stdout` for JSON-RPC 2.0 framing. Writing non-JSON text to `sys.stdout` corrupts the stream before the handshake.
- **Impact**: MCP clients (Claude Desktop, LM Studio, Cursor) fail to initialize with JSON parsing errors (`Expecting value: line 1 column 1`). The `[mcp] server stopped` write in the `finally` block has the same problem.
- **Fix applied**: all three `sys.stdout.write` / `flush` pairs (startup banner, tool list, shutdown notice) switched to `sys.stderr`, with a comment recording why. The `ValueError` guard on shutdown was kept.

---

## 2. Data Modification & Dry-Run Violations

### 2.1 `combobook.py`: `write_tags` Executed During Dry-Run / Preview
- **Status**: 🛠️ **FIXED (2026-09-04)** — the `write_tags` loop is now wrapped in `if not dry:`. Verified end-to-end: after a dry run the audio file is **byte-identical** and carries no artist tag, the source folder stays in place, and a control run with `dry=False` still tags correctly (so the guard is not over-broad).
- **File**: [`combobook.py:761-764`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L761-L764)
- **Code**:
  ```python
  for idx, t in enumerate(audio_files, 1):
      write_tags(t, chosen_meta, idx, len(audio_files))
  meta = chosen_meta
  ```
- **Error**: `write_tags` is called unconditionally inside `process()` when new metadata is fetched, without checking `if not dry:`. Every *other* mutating step in this function is correctly gated (lines 737, 781, 803), which makes this an oversight rather than a design choice.
- **Impact**: Running `combobook.py` without `--commit` (or via the GUI with "Commit" unchecked) retags the user's source audio in place. A preview is expected to be a no-op.
- **Interaction with 3.1**: before the fix, the write silently failed anyway because of the ffmpeg `.tmp` bug — so fixing 3.1 *without* fixing 2.1 first would have newly exposed live data modification during preview. This was fixed in the correct order: **2.1 first, then 3.1.**
- **Fix applied**:
  ```python
  # Never mutate the user's files during a preview: every other mutating
  # step in this function is gated on `dry`, this one was not.
  if not dry:
      for idx, t in enumerate(audio_files, 1):
          write_tags(t, chosen_meta, idx, len(audio_files))
  meta = chosen_meta
  ```

### 2.2 `combobook.py`: `rename_tracks` Has No Dry-Run Guard
- **Status**: ⚠️ **Verified — description corrected.** Real defect, but currently **latent**: `RENAME_TRACKS = False` at [`combobook.py:47`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L47), so the branch never executes today. It becomes a live data-loss bug the moment that constant is flipped to `True`.
- **File**: [`combobook.py:784-785`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L784-L785), [`combobook.py:620-626`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L620-L626)
- **Code**:
  ```python
  if dry:
      if FLATTEN_DISCS:
          flatten(folder, True)     # correctly passes dry=True
      if RENAME_TRACKS and not FLATTEN_DISCS:
          rename_tracks(folder)     # no dry parameter exists
  ```
- **Error**: `rename_tracks` takes no `dry` parameter and calls `p.rename(new)` directly. Note the adjacent `flatten()` call *does* correctly thread `dry` through — the inconsistency is the tell.
- **Impact**: Files renamed on disk during preview, if `RENAME_TRACKS` is ever enabled.
- **Fix**: Add a `dry: bool` parameter to `rename_tracks` and skip `p.rename` when set.

### 2.3 `ablib/cli/main.py`: Preview Mode Fails to Inspect or Preview Metadata
- **Status**: ✅ **Verified** — accurate. Best characterised as a design gap rather than a crash.
- **File**: [`ablib/cli/main.py:395-397`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/cli/main.py#L395-L397), [`AbtoolsGui.py:738-740`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/AbtoolsGui.py#L738-L740)
- **Code**:
  ```python
  if not args.commit:
      rprint(f"[dim]preview:[/] {leaf}")
      continue
  process_leaf(leaf, args)
  ```
- **Error**: In preview mode, `process_leaf` is skipped entirely, so nothing is looked up.
- **Impact**: Preview prints folder names only — no provider results, no proposed tags, no confidence scores. `README.md` advertises "preview and logging", and the module docstring's `# preview everything` example implies more than this delivers.
- **Fix**: Let `process_leaf` run in preview mode and guard only the `write_tags` / `export_metadata` calls with `args.commit`.

### 2.4 `ablib/cli/main.py`: `--no` Ignored & Confirmation Skipped for Confidence Scores >= 70
- **Status**: ✅ **Verified.** Note the threshold is hardcoded `70` while the *refinement* trigger uses the configurable `--llm-threshold` (default 85) — so the two gates disagree by design error.
- **File**: [`ablib/cli/main.py:209`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/cli/main.py#L209), [`ablib/cli/main.py:227-233`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/cli/main.py#L227-L233)
- **Code**:
  ```python
  if not llm_used and best_score is not None and best_score < 70 and not args.yes:
      ...
      if args.no:
          proceed = False
  ```
- **Error**: Both the interactive prompt and the `--no` check live inside the `< 70` guard.
- **Impact**: Two distinct consequences:
  1. `--no` is silently a no-op for any match scoring ≥ 70.
  2. A match scoring between 70 and `--llm-threshold` whose LLM/MCP refinement failed (or was unavailable) is auto-tagged with no prompt — defeating the purpose of raising `--llm-threshold`.
- **Fix**: Hoist the confirmation and `--no` check out of the `< 70` guard and compare against `llm_threshold` consistently.

---

## 3. FFmpeg Invocation & Concat Escaping Failures

### 3.1 `repair_m4b.py` & `combobook.py`: FFmpeg `.tmp` Output Format Failure (Code 234)
- **Status**: 🛠️ **FIXED (2026-09-04)** — both call sites repaired. `combobook.write_tags` now writes to `track.abtmp.mp3` (real extension preserved) and captures/reports stderr; `repair_m4b.run_ffmpeg` now passes an explicit `-f mp4`. Verified: tags actually land (`artist=['Frank Herbert']`, no leftover temp files), and `repair_m4b` writes its `.m4b.tmp` output with rc=0. Originally reproduced at **rc=234**, `Unable to choose an output format for '...tmp'`. The `combobook` impact was *worse* than first described — see below.
- **File**: [`repair_m4b.py:40-53`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/repair_m4b.py#L40-L53), [`repair_m4b.py:75`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/repair_m4b.py#L75); [`combobook.py:552-569`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L552-L569)
- **Code**:
  ```python
  # repair_m4b.py:
  temp_output = path.with_suffix(path.suffix + ".tmp")     # book.m4b.tmp
  cmd = [ffmpeg, "-y", "-i", str(input_file), "-c", "copy", str(output_file)]

  # combobook.py:
  tmp = track.with_suffix(track.suffix + ".tmp")           # track.mp3.tmp
  cmd = [FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-i", str(track), "-codec", "copy", ..., str(tmp)]
  ```
- **Error**: ffmpeg infers the container from the output extension; `.tmp` is unrecognised and no `-f` flag is supplied.
- **Impact**:
  - `repair_m4b.py --overwrite` fails on 100% of files with `RuntimeError`. *(Default non-overwrite mode is unaffected — it writes `" - fixed.m4b"`, a valid extension.)*
  - `combobook.py` fails to write tags on 100% of files, **completely silently**. The correction to the original write-up: it is not merely that stderr is `DEVNULL`. ffmpeg creates no output file, so in
    ```python
    if res.returncode == 0 and tmp.exists():   # False
        tmp.replace(track)
    elif tmp.exists():                          # also False -> error message never prints
        tmp.unlink(missing_ok=True)
        rprint("[red]✗ failed to write tags[/]")
    ```
    **neither branch runs** — so even the `✗ failed to write tags` diagnostic is unreachable. Tagging is a total no-op that reports success.
- **Prior art**: `past_memory.md` records this exact fix already being applied to `ab_encode.py` ("added explicit `-f mp4` format flag"). It was never backported to these two call sites.
- **Fix applied**:
  - `repair_m4b.py` — explicit container, matching the March fix in `ab_encode.py`:
    ```python
    cmd = [ffmpeg, "-y", "-i", str(input_file), "-c", "copy",
           "-f", "mp4",              # ".tmp" gives ffmpeg nothing to infer from
           str(output_file)]
    ```
  - `combobook.py` — keep the real extension, and surface failures instead of swallowing them:
    ```python
    tmp = track.with_name(f"{track.stem}.abtmp{track.suffix}")
    ...
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0 and tmp.exists():
        tmp.replace(track)
        return
    tmp.unlink(missing_ok=True)
    detail = (res.stderr or "").strip().splitlines()
    rprint(f"[red]✗ failed to write tags:[/] {track.name}"
           + (f" - {detail[-1]}" if detail else ""))
    ```

### 3.2 `ab_encode.py`: Shell Escaping Breaks Concat Demuxer Single Quotes
- **Status**: ❌ **REFUTED — the current code is correct. Do not change it.**
- **File**: [`ab_encode.py:147`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L147)
- **Original claim**: `safe_path = abs_path.replace("'", "'\\''")` supposedly breaks ffmpeg's concat demuxer, which allegedly only accepts `\'` inside single quotes.
- **Why it is wrong**: ffmpeg's concat demuxer tokenizer (`av_get_token`) *does* follow POSIX-style quoting: a single-quoted run ends at the next `'`, and a backslash escape is honoured **outside** quotes. The sequence `'\''` therefore closes the quote, supplies a literal `'`, and reopens — exactly the intended result.
- **Evidence** (executed):
  ```text
  file '/tmp/abq/Sorcerer'\''s Stone.mp3'    ->  ffmpeg rc=0, 8611-byte output produced
  file '/tmp/abq/Sorcerer's Stone.mp3'       ->  ffmpeg rc=254,
        "Impossible to open '/tmp/abq/Sorcerers'" / "No such file or directory"
  ```
  The control case proves the escaping is doing real, necessary work. The original audit's `rc=234` came from copying an **mp3 stream into an `.m4b` container** (an unrelated codec/container mismatch), not from path escaping.
- **Action**: None. Applying the proposed `replace("'", r"\'")` would **break** filenames containing apostrophes.

### 3.3 `ab_encode.py`: Windows Backslashes in Concat List Unescaped
- **Status**: ❌ **REFUTED — unsubstantiated.**
- **File**: [`ab_encode.py:145-148`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L145-L148)
- **Original claim**: Windows backslashes in `abs_path` are treated as escape characters by the concat demuxer.
- **Why it is wrong**: the path is written **wrapped in single quotes** (`file '{safe_path}'`). Inside a single-quoted run, ffmpeg's tokenizer treats every character literally until the closing quote — which is precisely why the unescaped-apostrophe control in 3.2 terminated the string early. Backslashes inside the quotes are therefore literal, and Windows paths pass through intact.
- **Corroboration**: `past_memory.md` documents extensive real-world `ab_encode.py` runs on this project without any such failure.
- **Action**: None. The suggested forward-slash normalisation is harmless but solves a non-problem.

---

## 4. File Discovery & Multi-Disc Flaws

### 4.1 `combobook.py`: `leaf_dirs` Treats Disc Subfolders as Separate Audiobooks
- **Status**: 🛠️ **FIXED (2026-09-04)** — `leaf_dirs` now folds bare disc sub-folders into their parent, and `process()` collects tracks from those sub-folders. Verified end-to-end: a two-disc book yields **one** leaf, both discs move, both are flattened and tagged, and nothing is left in the source. See the design constraint below.
- **File**: [`combobook.py:137-142`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L137-L142)
- **Code**:
  ```python
  def leaf_dirs(root:Path)->List[Path]:
      return [p for p in root.rglob("*")
              if p.is_dir()
              and any(f.suffix.lower() in AUDIO_EXTS for f in p.iterdir())
              and not any(c.is_dir() and any(g.suffix.lower() in AUDIO_EXTS for g in c.iterdir())
                          for c in p.iterdir())]
  ```
- **Error**: The parent `Book/` holds no audio directly, so it fails the second condition and is dropped; both disc folders qualify and are returned as independent books.
- **Impact**:
  1. `flatten()` finds no disc subdirectories *inside* `Disc 1/` and does nothing.
  2. `Disc 1/` is moved to `lib / Author / Title`.
  3. `Disc 2/` resolves to the same `dest_path`, hits the `book already moved, skip` branch at line 793, is counted as `exists`, and is **left behind in the source**.
  The `FLATTEN_DISCS` machinery never gets a chance to merge the discs.
- **Note**: `ablib/cli/main.py`'s `walk_leaves` has the same structural blind spot, but the consequence is milder there (each disc is tagged as its own book; nothing is moved or abandoned).
- **Fix applied**: two coordinated changes in `combobook.py`.
  1. `leaf_dirs` returns the parent as the book when **every** audio-bearing sub-folder is a *bare* disc marker, and excludes those sub-folders from the results.
  2. `process()` falls back to collecting tracks from those sub-folders when the book folder holds no audio directly — otherwise the parent was skipped as "no audio".
- **Design constraint — why "bare" markers only**: folding *any* `DISC_RX`/`PART_RX` match into its parent would merge unrelated titles. `Tolkien/The Hobbit Part 1` and `Tolkien/The Hobbit Part 2` both match `PART_RX`, so the naive rule would treat `Tolkien/` itself as one book. The new `is_bare_disc_marker()` therefore requires the name to be *nothing but* a marker (`Disc 1`, `CD2`) — a child carrying its own title stays independent. `disc_children()` also returns `[]` for an ambiguous mix rather than guessing. A regression test covers exactly this case.

### 4.2 `combobook.py` & `ablib/cli/main.py`: Root Folder Ignored When Pointing Directly to a Book
- **Status**: 🛠️ **FIXED (2026-09-04)** — both `combobook.leaf_dirs` and `ablib.cli.main.walk_leaves` now evaluate `root` itself as a candidate. Verified: pointing either straight at a book folder finds it (including a multi-disc one), while library roots still yield only their book folders — no spurious root entry.
- **File**: [`combobook.py:137-142`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L137-L142), [`ablib/cli/main.py:307-312`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/cli/main.py#L307-L312)
- **Error**: `root.rglob("*")` only yields descendants of `root`, never `root` itself.
- **Impact**: `python combobook.py "/books/Dune" "/dest"` finds 0 books and exits silently having done nothing.
- **Scope note**: in `ablib/cli/main.py` this only bites with `--recurse`; without it, `main()` uses `[args.root]` directly and works.
- **Fix applied**: both loops iterate `[root, *root.rglob("*")]` instead of `root.rglob("*")`, so `root` is judged by the same rules as any other directory rather than needing a special case. A library root has no audio of its own and therefore still isn't a leaf; a book root is. In `combobook` this composes with the [4.1](#41-combobookpy-leaf_dirs-treats-disc-subfolders-as-separate-audiobooks) disc-folding, so a root that is itself a multi-disc book resolves to the single book folder.
- **Cosmetic note**: when the root *is* the book, `process()` prints the source as `.` (from `folder.relative_to(src)`). Harmless, but the display could be friendlier.

### 4.3 `combobook.py`: `safe_move` Crashes on Empty Destination Directory
- **Status**: ✅ **Verified** by inspection.
- **File**: [`combobook.py:788-791`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L788-L791), [`combobook.py:301-302`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L301-L302)
- **Code**:
  ```python
  # process():
  if dest.is_dir() and not any(dest.iterdir()):
      pass   # intended to allow writing into an empty dir

  # safe_move():
  if dst.exists():
      raise FileExistsError(dst)
  ```
- **Error**: `process()` deliberately permits an empty destination, then `safe_move()` unconditionally rejects any existing path — the two directly contradict each other.
- **Impact**: Moving into an existing empty destination folder raises `FileExistsError`, caught only at the top level.
- **Fix**: Have `safe_move` accept (or `rmdir`) a destination that is an existing empty directory.

### 4.4 `flatten_discs.py`: Folders Starting with Disc Prefix Collide Under Empty String `""`
- **Status**: 🛠️ **FIXED (2026-09-04)** — new shared `disc_base_name()` falls back to the text *after* the marker when the text before it is empty. Verified: `[Disc 1] Book A` / `[Disc 1] Book B` now group as `Book A` / `Book B` and flatten into separate folders; bare `Disc 1` / `Disc 2` still correctly flatten into the parent.
- **File**: [`flatten_discs.py:60`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/flatten_discs.py#L60)
- **Code**:
  ```python
  base = DISC_RX.split(p.name)[0].strip().rstrip(" -_")
  groups.setdefault(base, []).append((int(m.group("num")), p))
  ```
- **Error**: `DISC_RX` consumes the leading bracket, so for names *beginning* with the disc marker (`[Disc 1] Book A`, `Disc 1 - Book B`) the pre-match segment is `""`.
- **Impact**: All such folders in a directory collapse into `groups[""]`. Worse, `flatten()` then computes `book_dir = parent / ""`, which **is the parent directory itself**: the first book's tracks are renumbered into the parent as `Track 001...`, and the second book's identically-named tracks hit `safe_move`'s `FileExistsError` — which `flatten()` does not catch. Result: two books' files mixed into one folder, then a hard crash mid-operation.
- **Fix applied**: the base-name logic was duplicated in `disc_sets_in` (line 60) and `flatten` (line 88) — that duplication is how the two drifted. Both now call one shared `disc_base_name()`, which falls back to the trailing segment when the leading one is empty.
  - **Deliberately preserved:** a base of `""` from a *bare* marker (`Disc 1`) still resolves to the parent folder, because there the parent genuinely *is* the book. That case was always correct; only the prefix-marked case was broken.
  - **Also added:** `flatten()` now computes every destination up front and refuses the whole set if any already exists, printing `! refusing to flatten - N destination file(s) already exist`. Previously `safe_move`'s uncaught `FileExistsError` aborted mid-loop, after some tracks had already moved. Verified: the pre-existing file survives and no traceback is raised.

### 4.5 `ab_encode.py`: Arbitrary `.m4b` Selection and an Unreachable Branch
- **Status**: ✅ **Verified** by inspection. *(Newly added — not in the original report.)*
- **File**: [`ab_encode.py:110-132`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L110-L132), [`ab_encode.py:40`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L40)
- **Code**:
  ```python
  EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".ogg")   # note: no ".m4b"
  ...
  for f in folder_contents:
      if f.lower().endswith(".m4b"):
          existing_m4b = os.path.join(root, f)
          break                                            # first match wins
  ...
  elif os.path.basename(existing_m4b) not in source_files:
      pass                                                 # dead branch
  ```
- **Error**: Two related problems.
  1. `existing_m4b` takes the **first** `.m4b` returned by `os.listdir()`, whose order is arbitrary, and never checks whether it is the canonical `<folder>.m4b` output. A folder can legitimately end up with two `.m4b` files, because `cleanup` only deletes files matching `EXTENSIONS` — which excludes `.m4b`, so a stale non-AAC file is never removed.
  2. Since `.m4b` is absent from `EXTENSIONS`, `os.path.basename(existing_m4b)` can never appear in `source_files`, so the `elif` at line 128 is always true and its body is a bare `pass` — dead code.
- **Impact**: With a leftover non-AAC `.m4b` alongside a good AAC one, whether the folder is correctly skipped or needlessly re-encoded depends on filesystem listing order, and can differ between runs.
- **Fix**: Prefer the canonical `<folder_name>.m4b`; evaluate *all* `.m4b` candidates for AAC before deciding to skip; and delete or archive the superseded file after a verified re-encode.

---

## 5. Metadata, Providers & Tagging Logic Errors

### 5.1 `ablib/tagging/files.py`: Non-String Metadata Crashes XML Serializer
- **Status**: ✅ **Verified** — reproduced: `TypeError: cannot serialize 87 (type int)`.
- **File**: [`ablib/tagging/files.py:84-88`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/tagging/files.py#L84-L88)
- **Code**:
  ```python
  for key, value in meta.items():
      if not value:
          continue
      child = ET.SubElement(root, key)
      child.text = value
  ET.ElementTree(root).write(...)
  ```
- **Error**: `meta` reaches this function carrying non-string values — notably `meta["score"]` (an `int`, set by `calculate_combined_score` in `refine_metadata_via_mcp`). `ElementTree` requires `text` to be `str` or `None`.
- **Impact**: `export_metadata` raises at the very end of `process_leaf`, **after** audio tags were already written successfully — so a fully-tagged book is reported as `ERR`.
- **Fix**: `child.text = str(value)`.

### 5.2 `ablib/metadata/utils.py`: Regex Character Class Typo `[--]` Splits Words on Hyphens
- **Status**: ✅ **Verified** — reproduced: `'Spider-Man - Stan Lee'` → `['Spider', 'Man', 'Stan Lee']`.
- **File**: [`ablib/metadata/utils.py:168`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/utils.py#L168)
- **Code**:
  ```python
  parts = [part.strip() for part in re.split(r"\s*[--]\s*", cleaned) if part.strip()]
  ```
- **Error**: `[--]` is the character range `-` to `-`, i.e. a plain hyphen; with `\s*` on both sides optional, it splits on **internal** hyphens too. The intent was almost certainly `[-–—]` (hyphen / en-dash / em-dash), mangled by an encoding round-trip.
- **Impact**: `'Sci-Fi - Asimov'` → `['Sci', 'Fi', 'Asimov']`; `'Jean-Paul Sartre - Nausea'` → `['Jean', 'Paul Sartre', 'Nausea']`. `parts[0]` then contains no space, so `author_hint` is discarded and `title_part` is corrupted.
- **Fix**: `re.split(r"\s+[-–—]\s+", cleaned)` — require surrounding whitespace so only true delimiters match.

### 5.3 `ablib/providers/http.py`: `openlib` and `gbooks` Never Called in `best_match`
- **Status**: ✅ **Verified** by inspection.
- **File**: [`ablib/providers/http.py:182-192`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/http.py#L182-L192)
- **Error**: `best_match()` queries only Goodreads and Audible. `openlib` and `gbooks` are defined and exported, but reached only from `enrich_metadata_with_providers` (gap-filling), never for primary matching.
- **Impact**: When Goodreads and Audible both miss, `best_match()` returns `None` and the pipeline escalates to the LLM without ever consulting Open Library or Google Books — contradicting `README.md`, which lists all four as match sources.
- **Fix**: Add `openlib` / `gbooks` to the candidate sweep in `best_match()`.

### 5.4 `ablib/providers/mcp.py`: `_parse_provider_query` Splits on "by" Inside Titles
- **Status**: ✅ **Verified** by inspection.
- **File**: [`ablib/providers/mcp.py:52-58`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/mcp.py#L52-L58)
- **Code**:
  ```python
  match = re.search(r"\bby\b", cleaned, flags=re.IGNORECASE)
  if match:
      title = cleaned[: match.start()].strip(" \"'-")
      author = cleaned[match.end() :].strip(" \"'-") or None
  ```
- **Error**: `re.search` takes the **first** `by`, including one inside the title.
- **Impact**: `"Stand by Me"` → title `"Stand"`, author `"Me"`. Also affects "Side by Side", "By the Pricking of My Thumbs".
- **Fix**: Search from the right, and reject the split when the resulting author candidate is implausible (single short token, contains digits, etc.).

### 5.5 `mcp_server/tools/audible.py` & `goodreads.py`: Missing URL Parameter Encoding
- **Status**: ✅ **Verified** by inspection.
- **File**: [`mcp_server/tools/audible.py:13`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/mcp_server/tools/audible.py#L13), [`mcp_server/tools/goodreads.py:13`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/mcp_server/tools/goodreads.py#L13)
- **Code**:
  ```python
  url = f"https://www.audible.com/search?keywords={query.replace(' ', '+')}"
  url = f"https://www.goodreads.com/search?q={query.replace(' ', '+')}"
  ```
- **Error**: `.replace(' ', '+')` does not escape `&`, `?`, `#`, or quotes.
- **Impact**: `"Dungeons & Dragons"` produces `?keywords=Dungeons+&+Dragons` — the `&` starts a new parameter, truncating the search to `"Dungeons"`. A `#` truncates even harder, as a fragment.
- **Corroborating signal**: the sibling modules `googlebooks.py` and `openlibrary.py` already do this correctly with `params={...}`, so this is an inconsistency within the same package, not a deliberate style.
- **Fix**: `requests.get(url, params={"keywords": query}, ...)` / `params={"q": query}`.

### 5.6 `ablib/tagging/files.py`: `series_index` Omitted from Audio Tags
- **Status**: ✅ **Verified** — `grep` over the module shows `series` written twice and `series_index` never.
- **File**: [`ablib/tagging/files.py:53-70`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/tagging/files.py#L53-L70)
- **Error**: `write_tags()` writes `series` to ID3 (`TXXX:series`) and MP4 (`----:com.apple.iTunes:series`) but never writes `series_index`, even though the pipeline resolves it and `export_metadata` persists it to `metadata.json` / `book.nfo`.
- **Impact**: Embedded tags lose series position; Audiobookshelf cannot order a series from the audio files alone.
- **Fix**: Write `TXXX:series-part` (MP3) and `----:com.apple.iTunes:series-part` (MP4), matching the keys `combobook.tags_from_track` already reads back.

### 5.7 `ablib/metadata/utils.py`: `guess_from_path` Can Discard the Real Title
- **Status**: ✅ **Verified** by inspection. *(Newly added — not in the original report.)*
- **File**: [`ablib/metadata/utils.py:76-95`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/utils.py#L76-L95)
- **Code**:
  ```python
  combined = " - ".join(parts[:-1]) if len(parts) >= 2 else parts[0]
  series, series_index, title = extract_series_and_title(combined)
  if not series and len(parts) >= 2:
      ...
      title = parts[-1]        # real title, only assigned on this path
  else:
      author = None            # series matched -> title from `combined` is kept
  ```
- **Error**: `combined` is built from `parts[:-1]`, deliberately **excluding** the final segment that holds the real title. If `extract_series_and_title(combined)` matches a `SERIES_PATTERNS` entry, its third capture group — a fragment of the *author/series* text — is retained as `title`, and the true title in `parts[-1]` is never read.
- **Impact**: For `"Author - Series 3 Bonus - Title"`, `SERIES_PATTERNS[0]` matches `combined`, producing `title="Bonus"` and `author=None`; the actual title `"Title"` is silently lost. Affects any layout where the pre-title segments contain a number followed by more text.
- **Fix**: When `len(parts) >= 2`, always take `title = parts[-1]` and use `combined` solely to extract `series` / `series_index`.

### 5.8 `combobook.py`: `choose_meta` Crashes on a `None` Provider Title
- **Status**: ✅ **Verified** — reproduced: `AttributeError: 'NoneType' object has no attribute 'lower'`. *(Newly added — not in the original report.)*
- **File**: [`combobook.py:525-532`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L525-L532), [`combobook.py:433-452`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L433-L452)
- **Code**:
  ```python
  out.append(Meta(author=..., title=info.get("title"), ...))   # gb_search_all: may be None
  ...
  key = (c.author.lower(), c.title.lower())                    # choose_meta dedup
  ```
- **Error**: `gb_search_all` and `ol_search_all` pass provider titles straight into `Meta` without a null check (`audible_search_all` is guarded and does not have this problem). A Google Books volume lacking `title` yields `Meta.title is None`.
- **Impact**: The dedup step raises `AttributeError`, propagating out of `process()`; the book is aborted and only caught by the top-level handler.
- **Fix**: Skip candidates without a title when building the result lists, or coerce with `(c.title or "").lower()` in the dedup key.

---

## 6. GUI & CLI Synchronization Issues

### 6.1 `find_duplicates.py`: `--only-src-log` Is Dead Code in CLI
- **Status**: ✅ **Verified** — `grep` shows `only_src_log` appears exactly once in the file, at its `add_argument`.
- **File**: [`find_duplicates.py:475-478`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/find_duplicates.py#L475-L478), [`find_duplicates.py:508-545`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/find_duplicates.py#L508-L545)
- **Error**: The flag is parsed, but `args.only_src_log` is never read and never forwarded as `limit_paths` / `limit_src`.
- **Impact**: `--only-src-log` silently does nothing on the CLI. The supporting machinery (`_read_paths_from_log`, `limit_paths`, `limit_src`) is fully implemented and *is* correctly wired from `AbtoolsGui.py:793-799` — only the CLI path was missed.
- **Fix**: Read `args.only_src_log` in `__main__` and pass `limit_paths=` / `limit_src=`, mirroring the GUI.

### 6.2 `abclient.py`: Local `abclient.json` Ignored
- **Status**: ⚠️ **Verified — reclassified as by-design / low priority, not a bug.**
- **File**: [`abclient.py:17`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/abclient.py#L17)
- **Original claim**: `AbClient()` should read the repository's `abclient.json`.
- **Correction**: `scaffold.md` describes the repo file as *"Sample client configuration"*, and `README.md` documents `~/.abclient.json` as the real location. The current behaviour matches both documents, and `AbClient(path=...)` already allows an explicit override. Treating the repo sample as live config would be a **behaviour change**, and would make a checked-in file silently override user settings.
- **Action**: Optional ergonomics improvement only. If adopted, load the repo file as a *lower*-precedence default beneath `~/.abclient.json`, never above it.

---

## 7. Edge Cases, Type Errors & Performance Issues

### 7.1 `repair_m4b.py`: Missing `Iterable` Import
- **Status**: ❌ **REFUTED as a runtime bug** — downgraded to a type-checker nit.
- **File**: [`repair_m4b.py:116`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/repair_m4b.py#L116)
- **Original claim**: `def iter_targets(root: Path) -> Iterable[Path]:` raises `NameError` because `Iterable` is never imported.
- **Why it is wrong**: the module begins with `from __future__ import annotations` ([line 14](file:///home/citizenzero/Documents/Key/Abtools/ABtools/repair_m4b.py#L14)), so under PEP 563 all annotations are stored as **strings** and never evaluated. The module imports and the function runs fine; `python3 -m py_compile` and normal execution both succeed.
- **Residual issue**: `typing.get_type_hints()` or a strict type-checker run would fail. Adding `from collections.abc import Iterable` is still worth doing for correctness of tooling — but it fixes **no runtime behaviour**, and this should not be triaged as a crash.

### 7.2 `catalog.py`: `calc_signature` Crashes on `None` or Decimal Duration
- **Status**: ⚠️ **Verified — but the module is entirely unused.** `grep` finds no `import catalog` / `Catalog(` anywhere in the project, so this code is currently unreachable. Fix opportunistically, not urgently.
- **File**: [`catalog.py:60`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/catalog.py#L60)
- **Code**: `duration = int(meta.get("duration", 0))`
- **Error**: `{"duration": None}` makes `.get` return `None` (the default only applies to a *missing* key), so `int(None)` raises `TypeError`; `"120.5"` raises `ValueError`.
- **Fix**: `int(float(meta.get("duration") or 0))`.

### 7.3 `combobook.py`: Unsafe Index Access in `tags_from_track`
- **Status**: ✅ **Verified** by inspection — narrow edge case (malformed tags only).
- **File**: [`combobook.py:357-360`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L357-L360)
- **Code**: `year = au.get("date",[None])[0][:4] if "date" in au else None`
- **Error**: The `[None]` default is dead — the `if "date" in au` guard means the key always exists. If the value is an **empty list**, `[][0]` raises `IndexError`, which the surrounding `except mutagen.MutagenError` does not catch. The same pattern repeats for `series`, `series-part` and `composer` on the following lines.
- **Fix**: `if "date" in au and au["date"]: ...`, applied to all four fields.

### 7.4 `combobook.py`: Title Truncation Cuts Off / Corrupts Year Suffix
- **Status**: ✅ **Verified** — reproduced: a 54-char title + `" (2003)"` truncates to `'The Extraordinarily Long And Winding Title of This'`, losing the year entirely.
- **File**: [`combobook.py:659-667`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L659-L667)
- **Code**:
  ```python
  if meta.year:
      title_text = f"{title_text} ({meta.year})"
  title_slug = _truncate(title_text, MAX_TITLE_LEN)
  ```
- **Error**: The `(Year)` suffix is appended *before* truncation, so the clip removes it — or leaves a dangling `"... ("`.
- **Impact**: Destination folders lose the year Audiobookshelf uses for disambiguation, and near-identical long titles can collide into one folder.
- **Fix**: Truncate the title to `MAX_TITLE_LEN - len(" (YYYY)")` first, then append the year suffix.

### 7.5 `ablib/metadata/llm.py`: Token Budget Shrinks on Length Retries
- **Status**: ⚠️ **Verified — currently latent.** All three in-module call sites pass `max_tokens=1024`, where `min(2048, 2048)` behaves correctly. The bug bites any caller using the `CONFIG.llm_max_tokens` default — and `_call_llm` is exported in `__all__`.
- **File**: [`ablib/metadata/llm.py:145-146`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/llm.py#L145-L146)
- **Code**: `new_budget = min(token_budget * 2, 2048)`
- **Error**: `CONFIG.llm_max_tokens` defaults to **8000**. On `finish_reason == "length"`, `min(16000, 2048)` yields **2048** — a 4× *reduction* on a retry whose entire purpose is to give the model more room. Verified: `token_budget=8000 -> retry budget=2048`.
- **Fix**: `new_budget = min(token_budget * 2, 16384)`, or better `max(token_budget, min(token_budget * 2, 16384))` so the retry can never shrink.

---

## 8. MCP Tool Runtime Verification

*Added 2026-09-04, after fixing [1.3](#13-mcp_serverserverpy-standard-output-banners-violate-mcp-json-rpc-protocol) and installing the previously-undeclared `mcp` dependency. Each tool was invoked for real over stdio (`initialize` → `notifications/initialized` → `tools/call`) — the first time these have ever been executed end-to-end.*

| Tool | Result | Notes |
|---|---|---|
| `search_openlibrary_tool` | ✅ **Working** | Returned `{"title": "Dune", "author": "Frank Herbert", "year": 1965, "openlibrary_id": "/works/OL893414W"}` |
| `search_goodreads_tool` | ✅ **Working** | Returned real hits; HTTP 200, 20 rows matched the `tr[itemtype=...]` selector |
| `tag_books_tool` | ✅ **Working** | Preview against a temp fixture returned `{"status": "preview", "processed": [...]}` |
| `search_google_books_tool` | ⚠️ **Code OK, blocked** | HTTP **429 — "Quota exceeded for quota metric 'Queries' ... per day"**. Unauthenticated Google Books quota is per-IP and shared; the tool degrades correctly to `{"error": "gbooks_request_failed:429..."}`. Not a code defect. |
| `search_audible_tool` | ⚠️ **Code path OK, blocked** | Audible served **HTTP 503** to this host (2.5 KB block page, zero product markup). Anti-scraping, not a parse failure. See 8.1 — the selectors could not be validated. |

**Testing note:** an initial probe reported "NO RESPONSE" for `search_goodreads_tool` and `tag_books_tool`. That was an artifact of the probe closing stdin while requests were still queued — the server shuts down on EOF. Re-running with the pipe held open showed both working. Not a server bug.

### 8.1 Audible: two different selector sets for the same site
- **Status**: ⚠️ **Unverified — cannot be validated from this host** (Audible returns 503). Flagged for review, not asserted as broken.
- **Files**: [`mcp_server/tools/audible.py:22-24`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/mcp_server/tools/audible.py#L22-L24) vs [`ablib/providers/http.py:120-126`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/http.py#L120-L126)
- **Observation**: the repo scrapes Audible in two places with **disjoint selectors**:
  ```python
  # mcp_server/tools/audible.py
  item.select_one(".bc-heading a")     # title
  item.select_one(".bc-author a")      # author

  # ablib/providers/http.py
  item.select_one("h3")                # title
  item.select_one(".authorLabel a")    # author
  ```
  Both also iterate different containers (`li.bc-list-item` vs `li.bc-list-item.productListItem`).
- **Why it matters**: at most one set can match current Audible markup. Whichever is stale fails **silently** — both code paths return "No results" rather than signalling a parse failure, so a broken scraper is indistinguishable from a genuine miss.
- **Suggested action**: when a host that Audible does not block is available, verify both selector sets against live markup, consolidate on one shared helper, and log a distinct warning when the HTTP fetch succeeds but zero items parse.

### 8.2 Provider tools return a list on success but a dict on failure
- **Status**: ✅ **Verified** by inspection — design inconsistency, low severity.
- **Files**: all four of [`mcp_server/tools/`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/mcp_server/tools)
- **Observation**: each search tool ends with `return results or {"error": "No results"}` — a `list` when it succeeds, a `dict` when it fails.
- **Impact**: a consumer must type-check the response before iterating; an LLM client reading the raw payload can easily mistake the error dict for a result. It also conflates "the site returned nothing" with "our parser matched nothing" (see 8.1).
- **Suggested fix**: always return a consistent envelope, e.g. `{"results": [...], "error": None}`.

---

## Appendix: Summary of corrections to the original report

| Entry | Original verdict | Corrected verdict |
|---|---|---|
| 3.2 ab_encode single-quote escaping | Broken, fix required | ❌ **Refuted** — escaping is correct; proposed fix would break apostrophe filenames |
| 3.3 ab_encode Windows backslashes | Broken | ❌ **Refuted** — backslashes are literal inside single quotes |
| 7.1 repair_m4b `Iterable` import | Runtime `NameError` | ❌ **Refuted as runtime bug** — PEP 563 defers annotations; type-checker nit only |
| 6.2 abclient local json | Bug | ⚠️ **By design** per `scaffold.md` / `README.md`; optional ergonomics change |
| 2.2 rename_tracks dry-run | Live bug | ⚠️ **Latent** — `RENAME_TRACKS = False` today |
| 3.1 combobook `.tmp` | Silent due to `DEVNULL` | ⚠️ **Worse** — the error branch is unreachable; even the failure message never prints |
| 7.2 catalog duration | Bug | ⚠️ **Unreachable** — `catalog.py` is never imported |
| 7.5 token budget | Live bug | ⚠️ **Latent** — all current call sites pass `max_tokens=1024` |

**Newly added in this revision:** [4.5](#45-ab_encodepy-arbitrary-m4b-selection-and-an-unreachable-branch), [5.7](#57-ablibmetadatautilspy-guess_from_path-can-discard-the-real-title), [5.8](#58-combobookpy-choose_meta-crashes-on-a-none-provider-title), plus scope/severity notes on 1.2, 2.1, 2.4, 4.1, 4.2, 4.4, 5.5, 6.1, 7.3.

## Appendix: Fixes applied 2026-09-04

All four P0 entries fixed and verified end-to-end. Files touched: `combobook.py`, `repair_m4b.py`, `restructure_for_audiobookshelf.py`, `AbtoolsGui.py`.

| Entry | Change | Verification |
|---|---|---|
| 2.1 | `write_tags` loop gated behind `if not dry:` | Dry run leaves the file byte-identical and untagged; control with `dry=False` still tags |
| 3.1 | temp file `track.abtmp.mp3` (was `track.mp3.tmp`); stderr captured and reported | Tags land (`artist=['Frank Herbert']`), no leftover temp files |
| 3.1b | `repair_m4b.run_ffmpeg` passes `-f mp4` | `.m4b.tmp` output written, rc=0, 1201 bytes |
| 1.1 | `"--commit"` flag name restored | `--help` prints usage instead of `TypeError` |
| 1.2 | GUI calls `restructure_library(...)` instead of `main(...)` | Call binds cleanly against the real signature |

| 1.3 | MCP banners moved from `stdout` to `stderr` | Real stdio handshake: stdout is pure JSON-RPC, all 5 tools listed |
| 4.1 | `leaf_dirs` folds bare disc folders into the book; `process()` reads tracks from them | Two-disc book → 1 leaf, both discs moved/flattened/tagged, source empty |
| 4.4 | shared `disc_base_name()` + pre-flight collision check in `flatten()` | Prefix-marked books stay separate; bare `Disc N` still folds into parent; clash reports instead of crashing |
| 4.2 | `leaf_dirs` / `walk_leaves` iterate `[root, *root.rglob("*")]` | Root-as-book found by both; library roots still yield only book folders |

**Consolidated regression suite — 10/10 passing** across 2.1, 3.1, 3.1b, 4.1, 4.2 and 4.4: dry-run byte-integrity, tag writing, `repair_m4b` temp output, multi-disc moves with nothing abandoned, distinct `Part N` books kept separate, prefix-marked books not merged, bare `Disc N` folding, root-as-book discovery in both entry points, and no spurious root leaf for libraries.

**Regression coverage added alongside the 4.1/4.4 fixes:** ordinary single-folder books are still discovered; an author folder containing several books is still not a leaf; `Tolkien/The Hobbit Part 1|2` stay separate books; dry-run on a multi-disc book leaves every byte untouched.

**Still open — recommended next:** the P2 metadata-correctness items in [section 5](#5-metadata-providers--tagging-logic-errors). [5.1](#51-ablibtaggingfilespy-non-string-metadata-crashes-xml-serializer) (one-line `str(value)`) and [5.8](#58-combobookpy-choose_meta-crashes-on-a-none-provider-title) (null-title guard) are both small crash fixes; [5.2](#52-ablibmetadatautilspy-regex-character-class-typo----splits-words-on-hyphens) (the `[--]` regex) silently corrupts author/title parsing and is the highest-value of the group.

**Files reviewed:** all 16 modules under `ablib/`, all 11 root-level scripts, and all 7 modules under `mcp_server/` (including `mcp_server/tools/`, which an earlier `-maxdepth 2` search had missed).
