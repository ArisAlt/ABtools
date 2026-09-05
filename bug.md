# ABtools Codebase Logic Errors & Bug Report

Comprehensive inventory of logic errors, runtime crashes, protocol incompatibilities, and silent failure modes discovered during the codebase audit of **ABtools**.

**Last updated:** 2026-09-06 — added [section 9](#9-encoder-output-formats--deletion-safety) from the encoder work: output profiles, and the deletion-safety path. [9.2](#92-ab_encodepy-verify_audio-was-far-too-weak-to-authorise-deleting-anything) is the significant one — `--cleanup` deleted sources on the strength of a positive duration, and was reproduced deleting a book's only copy of four damaged chapters. [4.5](#45-ab_encodepy-arbitrary-m4b-selection-and-an-unreachable-branch) closed with it. Still open and deliberately so: [7.3](#73-combobookpy-unsafe-index-access-in-tags_from_track) and [8.2](#82-provider-tools-return-a-list-on-success-but-a-dict-on-failure) (low severity), [7.2](#72-catalogpy-calc_signature-crashes-on-none-or-decimal-duration) (unreachable module), and [8.1](#81-audible-two-different-selector-sets-for-the-same-site) (cannot be validated from this host — Audible returns 503).

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
| P2 | [5.x](#5-metadata-providers--tagging-logic-errors) | Metadata corruption and crashes on specific inputs | 🛠️ Fixed (5.1-5.14) |
| P2 | [2.3](#23-ablibclimainpy-preview-mode-fails-to-inspect-or-preview-metadata) | Preview showed folder names only | 🛠️ Fixed |
| P3 | [7.x](#7-edge-cases-type-errors--performance-issues) | Latent / narrow edge cases | Mostly closed — [7.3](#73-combobookpy-unsafe-index-access-in-tags_from_track) open |
| **P1** | [4.6](#46-restructure_for_audiobookshelfpy-ignores-tags-and-sidecars-entirely) / [4.7](#47-restructure_for_audiobookshelfpy-no-series-level-in-the-output-layout) | Restructure ignores tags and drops series | 🛠️ Fixed in `restructure_for_audiobookshelf.py` (2026-09-05) |
| **P1** | [4.8](#48-the-two-organisers-produce-incompatible-layouts) | The two organisers disagree | 🛠️ **Fixed (2026-09-05)** — resolvers now shared, not just the formatter |
| **P0** | [4.10](#410-combobookpy-first-track-tags-short-circuit-the-entire-metadata-pipeline) | combobook trusts the first track's tags unconditionally; junk artist tags become author folders | 🛠️ **Fixed (2026-09-05)** |
| **P1** | [4.11](#411-read_tags-prefers-tit2-track-title-over-talb-album-title) | `read_tags` returns the *track* title, not the book title | 🛠️ **Fixed (2026-09-05)** |
| P2 | [4.12](#412-combobookpy-unidentifiable-folders-were-swept-into-_unmatched) | Unmatched folders were moved into `_unmatched/`, destroying their source path | 🛠️ **Fixed (2026-09-05)** |
| **P1** | [4.13](#413-restructure_for_audiobookshelfpy-books-at-the-source-root-are-skipped-silently) | restructure silently skips books at the source root; reports success having done nothing | 🛠️ **Fixed (2026-09-05)** |
| P2 | [4.14](#414-restructure_for_audiobookshelfpy-no-leave-in-place-for-books-it-cannot-identify) | restructure still sweeps unidentified books into `Unknown Author/` | 🛠️ **Fixed (2026-09-05)** |
| P2 | [4.15](#415-booknfo-and-metadatajson-described-the-same-book-differently) | The two sidecars for one book disagreed | 🛠️ **Fixed (2026-09-05)** |
| **P1** | [6.4](#64-abtoolsguipy-the-folder-browser-shows-nothing-for-a-network-share) | Folder browser empty for a network share or a mount-shadowed path | 🛠️ **Fixed (2026-09-05)** |
| **P1** | [4.17](#417-a-hosted-quota-error-abandoned-every-remaining-book) | A hosted 429 gave up on every remaining book; no local fallback | 🛠️ **Fixed (2026-09-05)** |
| **P0** | [4.18](#418-the-provider-layer-sent-work-to-the-llm-that-it-could-answer-itself) | 14/15 books went to the LLM that providers could answer; 3 wrong books chosen | 🛠️ **Fixed (2026-09-05)** |
| **P1** | [4.19](#419-two-scoring-scales-and-combobooks-floor-sat-inside-the-wrong-answer-band) | combobook's `--yes` floor sat inside the wrong-answer band; two scoring scales | 🛠️ **Fixed (2026-09-05)** |
| **P1** | [4.16](#416-the-schema-fix-never-reached-libraries-already-on-disk) | 4.9 fixed the writer; books already tagged kept the old schema | 🛠️ **Fixed (2026-09-05)** |
| P2 | [4.9](#49-metadatajson-does-not-match-audiobookshelfs-schema) | Sidecar schema likely ignored by Audiobookshelf | 🛠️ **Fixed (2026-09-05)** |
| — | [8](#8-mcp-tool-runtime-verification) | MCP tools executed for real: 3 working, 2 blocked by the remote host | Verified |

> **Fix ordering note (already observed):** 2.1 had to be fixed *before* 3.1. The dry-run tag writes were only harmless while the ffmpeg bug made every write fail. Fixing 3.1 first would have turned a silent no-op into live data modification during preview.
>
> **Verification & Testing Note (Bugs 4.6, 4.7, 4.8, 4.9):** The Audiobookshelf compliance and parity fixes are applied and ready for audit testing:
> - **4.6 (Tags/Sidecars)**: Verified that un-dated source folders containing ID3/MP4 tags or sidecars (`metadata.json`, `book.nfo`) resolve metadata accurately in priority order.
> - **4.7 (Series Level)**: Verified in `restructure_for_audiobookshelf.py`. `extract_series_and_title("Serpentwar Saga 03 - Rage of a Demon King (1998)")` returns `('Serpentwar Saga', '03', 'Rage of a Demon King (1998)')`.
> - **4.8 (Parity)**: ⚠️ **The earlier parity claim was scoped too narrowly.** It compared `combobook.dest_path()` with `restructure.target_for()` — but `dest_path()` is only a *formatter*; it receives an already-resolved `Meta`. combobook's *resolver* (`process()` → `tags_from_track()`) never runs series extraction at all, so identical formatters still produce divergent trees. See [4.10](#410-combobookpy-first-track-tags-short-circuit-the-entire-metadata-pipeline).
> - **4.9 (ABS Schema)**: Verified `export_metadata()` writes official Audiobookshelf `BookMetadata` schema (`authors[]`, `series[{"name", "sequence"}]`, `publishedYear`), valid XML `book.nfo`, and confirmed round-trip deserialization via `read_sidecar_metadata()`. Detailed reproduction and test steps are documented under each entry below.

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
- **Status**: 🛠️ **FIXED (2026-09-05)** — `rename_tracks(folder, dry=False)`; the two call sites inside `if dry:` branches now pass `dry=True` and report `would rename X -> Y` instead of renaming. Previously latent only because `RENAME_TRACKS = False`; it was a live data-loss bug the moment that constant was flipped.
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
- **Status**: 🛠️ **FIXED (2026-09-05)** — `process_leaf` now runs in preview mode and withholds only the writes. Verified: a preview prints the folder guess, per-provider scores, the chosen match and a `would tag …` line carrying the full metadata summary, while writing **no** tags, **no** `metadata.json`/`book.nfo` and **no** log entries; `--commit` still writes all three. `--striptags` previews as `would strip tags from N file(s)`.
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
- **Fix applied**: `process_leaf` reads `commit` once at the top (defaulting True, so callers that omit the flag are unaffected) and gates `write_tags`, `export_metadata`, `strip_tags` and the `tag_log`/`review_log` writes on it — logs record actions taken, so a preview should not add to them. `main()` and the GUI no longer short-circuit before calling it.

### 2.4 `ablib/cli/main.py`: `--no` Ignored & Confirmation Skipped for Confidence Scores >= 70
- **Status**: 🛠️ **FIXED (2026-09-05)** — the gate now reads `best_score < llm_threshold` instead of the hardcoded `70`, so `--no` is honoured for any below-threshold match and the 70-85 band prompts instead of tagging silently. The unreachable `else: Confirm(prompt_message, ...)` branch was removed at the same time. Verified across six paths: above-threshold tags silently; below-threshold with `--no` skips without prompting; accept tags; decline skips; `--yes` bypasses the prompt. (`llm_threshold` is still clamped to 80-100 by `process_leaf`, as documented in the CLI help.)
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
- **Status**: 🛠️ **FIXED (2026-09-05)** — `safe_move` now `rmdir`s an existing *empty* directory destination and proceeds, matching what `process()` already allowed. Verified: a move into a pre-created empty destination succeeds, while a non-empty destination is still refused with `FileExistsError`.
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
- **Status**: 🛠️ **FIXED (2026-09-06)** — the whole `existing_m4b` scan is gone. Source selection is now `every audio file except the one we are about to write`, so `.m4b` parts are ordinary sources and the canonical `<folder><ext>` output can never be one of its own inputs. The dead `elif` went with it. A lone file already in the target codec *and* container is skipped whatever it is called, which preserves the old "AAC M4B exists" behaviour without depending on `os.listdir` order. See [9.1](#91-ab_encodepy-folders-of-m4b-parts-were-invisible-not-skipped).
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

### 4.6 `restructure_for_audiobookshelf.py`: Ignores Tags and Sidecars Entirely
- **Status**: 🛠️ **FIXED (2026-09-05)** — `restructure_for_audiobookshelf.py` now resolves metadata in priority order: embedded audio tags (`read_tags` via mutagen), sidecars (`read_sidecar_metadata` for `metadata.json` and `book.nfo`), and folder name / hierarchy heuristics. Verified: tagged books without year in the folder name now file under their correct `Title (Year)` leaf and optional `Series` directory.
- **File**: [`restructure_for_audiobookshelf.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/restructure_for_audiobookshelf.py) — `target_for` / `parse_book_folder`
- **Error**: the module imported only `argparse, shutil, sys, pathlib, typing, re`. There was **no `mutagen` and no `json`**, so it had no mechanism to read either embedded tags or `metadata.json` / `book.nfo`. Every value was derived from the folder name by `parse_book_folder()`.
- **Contradicts the docs**: `README.md` states *"It reads tags from the audio files first, then `metadata.json` or `book.nfo`, and finally falls back to folder names."*
- **Impact**: previously reproduced against a book whose tags carried `date=2006` and whose `metadata.json` carried `year=2006`, `series=Mistborn`:
  ```
  input   Brandon Sanderson/The Final Empire   (tagged, both sidecars present)
  output  Brandon Sanderson/Unknown - The Final Empire
  ```
- **Fix applied**: added `read_tags()` and `read_sidecar_metadata()` in `ablib/tagging/files.py`. `target_for` queries tags, then sidecars, then folder heuristics before passing resolved fields to `format_canonical_dest()`.
- **Verification & Test Note**: To verify/test:
  1. Create a test directory structure `src/Brandon Sanderson/The Final Empire/` containing an audio file (`track.mp3`).
  2. Embed tags with mutagen: ID3 `TDRC`="2006", `TALB`="The Final Empire", `TXXX:series`="Mistborn", or place a `metadata.json` with `{"series": [{"name": "Mistborn"}], "publishedYear": "2006"}`.
  3. Execute `python3 restructure_for_audiobookshelf.py src dst` (dry-run or commit).
  4. Assert destination resolves to `dst/Brandon Sanderson/Mistborn/The Final Empire (2006)` rather than `dst/Brandon Sanderson/Unknown - The Final Empire`.

### 4.7 `restructure_for_audiobookshelf.py`: No Series Level in the Output Layout
- **Status**: 🛠️ **FIXED (2026-09-05)** — series level is now created whenever series metadata is present.
- **File**: [`restructure_for_audiobookshelf.py:102-106`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/restructure_for_audiobookshelf.py#L102-L106)
- **Error**: previously there was no series directory in the path (`dest_root / author_slug / book_slug`), so the `Author/Series/Book` arrangement Audiobookshelf documents for series could not be produced.
- **Fix applied**: `parse_book_folder()` now returns `(year, series, title)` using reordered `SERIES_PATTERNS`. `discover_books()` supports discovering books in nested `Author/Series/Book` layouts as well as flat `Author/Book` layouts. `target_for()` creates the series directory level whenever series is present (from tags, sidecars, folder name patterns like `Mistborn Book 1 - The Final Empire (2006)`, or directory hierarchy).
- **Verification & Test Note**: To verify/test:
  1. Create source folders representing series structures:
     - Folders matching series regex: `Author/Mistborn Book 1 - The Final Empire (2006)`
     - Existing nested series trees: `Author/Mistborn/The Final Empire (2006)`
  2. Run `python3 restructure_for_audiobookshelf.py src dst --commit`.
  3. Confirm `dst/Author/Mistborn/The Final Empire (2006)` is produced, verifying that the intermediate series directory level is created and nested crawlers discover books within series subfolders.

### 4.8 The Two Organisers Produce Incompatible Layouts
- **Status**: 🛠️ **FIXED (2026-09-05)** — both tools now share the *resolvers* (`parse_book_folder_name`, `is_plausible_author`, `primary_author`, `normalise_author`) as well as the formatter, and the regression suite starts from files on disk rather than a pre-built `Meta`. Previously, sharing `format_canonical_dest` fixed *path formatting* parity only. The two organisers still resolve metadata by completely different rules, so they still emit different trees for the same input. Reproduced against a real 572-entry run into `/home/citizenzero/Documents/temp_audiobooks/` (see [4.10](#410-combobookpy-first-track-tags-short-circuit-the-entire-metadata-pipeline)).
- **Why the earlier verification passed**: the parity test called `combobook.dest_path(dest, meta)` and `restructure.target_for(author, folder, dest)` with a *pre-built* `Meta`. That exercises the formatter both tools share; it never exercises how each tool *arrives* at that `Meta`. `restructure.target_for()` resolves tags → sidecars → folder heuristics and calls `extract_series_and_title()`; `combobook.process()` does none of this when the first track carries `artist` + `album`.
- **Files**: [`restructure_for_audiobookshelf.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/restructure_for_audiobookshelf.py) vs [`combobook.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py)
- **Error**: previously the two organisers produced incompatible conventions for the same book:
  | Tool | Result (Old) | Result (Fixed) |
  |---|---|---|
  | `restructure_for_audiobookshelf.py` | `Brandon Sanderson/Unknown - The Final Empire` | `Brandon Sanderson/Mistborn/The Final Empire (2006)` |
  | `combobook.py` (`dest_path`) | `Brandon Sanderson/Mistborn/The Final Empire (2006)` | `Brandon Sanderson/Mistborn/The Final Empire (2006)` |
- **Fix applied**: extracted destination building into `format_canonical_dest()` in `ablib/metadata/utils.py`. Both `combobook.dest_path()` and `restructure.target_for()` delegate to it, guaranteeing 100% path parity across standalone books, series books, books without years, and multi-disc albums.
- **Verification & Test Note**: To verify/test:
  1. Execute the parity test suite asserting `combobook.dest_path(dest, meta)` == `restructure_for_audiobookshelf.target_for(author, book_folder, dest)`.
  2. Test cases to cover:
     - Standalone book with year: `Author/Title (2020)` -> `Author/Title (2020)`
     - Series book with year: `Author/Series 1 - Title (2020)` -> `Author/Series/Title (2020)`
     - Book without year: `Author/Title` -> `Author/Title` (neither organiser emits `"Unknown - "`)
     - Long title (60+ characters) with year: truncation preserves the 4-digit `(YYYY)` suffix within the 50-character limit.
  3. Assert 100% string equality across both functions.

### 4.9 `metadata.json` Does Not Match Audiobookshelf's Schema
- **Status**: 🛠️ **FIXED (2026-09-05)** — `export_metadata()` now converts metadata into Audiobookshelf's official sidecar schema via `format_abs_metadata()`, writing `authors` (array), `narrators` (array), `series` (array of `{"name": ..., "sequence": ...}`), `publishedYear` (4-digit string), `genres` (array), `title`, `subtitle`, `publisher`, `description`, `isbn`, `asin`, `language`, and `explicit`. Convenience fallback keys (`author`, `year`, `narrator`) are preserved for legacy consumers. `read_sidecar_metadata()` verified round-tripping seamlessly.
- **File**: [`ablib/tagging/files.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/tagging/files.py) — `export_metadata`, `format_abs_metadata`
- **Re-verified 2026-09-05**: `format_abs_metadata()` confirmed to emit `authors: [...]`, `series: [{"name", "sequence"}]`, `publishedYear`, `genres: []`, `explicit`. **Caveat:** sidecars already on disk under `/home/citizenzero/Documents/temp_audiobooks/` are still the old flat schema (`author`, `year`, `series_index`) — they were written at `13:02`, before this fix landed at `14:16`, and were then *moved* by the organiser rather than rewritten. Existing libraries need a re-tag pass; the fix does not retroactively upgrade sidecars.
- **Known gap**: `book.nfo` is still generated from the raw `meta.items()` loop, so the XML keeps `<author>` / `<series_index>` while the JSON uses `authors` / `sequence`. Harmless for Audiobookshelf (it reads the JSON) but the two sidecars now disagree.
- **Error**: `export_metadata` previously dumped a flat dictionary with `title`, `author`, `year`, `series`, `series_index`. Audiobookshelf's server scanner expects `authors` (an array), `publishedYear`, `narrators` (an array), and a `series` array of objects — so Audiobookshelf ignored the file or failed to parse series/authors.
- **Fix applied**: implemented `format_abs_metadata()` in `ablib/tagging/files.py` to structure metadata precisely into Audiobookshelf's sidecar format, while writing `book.nfo` with XML tags for Kodi/Emby/Jellyfin scrapers. Both formats verified via automated unit and integration tests.
- **Verification & Test Note**: To verify/test:
  1. In Python, call `ablib.tagging.files.export_metadata(folder, meta)` with sample book fields (`title`, `author`, `series`, `series_index`, `year`, `narrator`).
  2. Inspect generated `metadata.json`: assert `authors` is a list, `series` is a list of dicts with `name` and `sequence`, and `publishedYear` is a 4-digit string.
  3. Inspect generated `book.nfo`: assert XML elements `<title>`, `<author>`, `<year>`, `<series>` exist.
  4. Call `ablib.tagging.files.read_sidecar_metadata(folder)`: assert it deserializes the official Audiobookshelf schema correctly back into the runtime metadata dictionary.

### 4.10 `combobook.py`: First-Track Tags Short-Circuit the Entire Metadata Pipeline
- **Status**: 🛠️ **FIXED (2026-09-05)** — see *Fix applied* below. This was the root cause behind the "4.6/4.7/4.8 are not actually fixed" report. Those fixes landed in `restructure_for_audiobookshelf.py`; the run that produced the bad library was **`combobook.py`**, which has its own resolver and never calls any of them.
- **File**: [`combobook.py:767-773`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L767-L773) — `process()`; and [`combobook.py:423-437`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py#L423-L437) — `tags_from_track()`
- **How the tool was identified**: the output root contains `_unmatched/`, a literal defined only in `combobook.py:51` (`UNMATCHED_DIR`). `restructure_for_audiobookshelf.py` has no such concept. Output mtimes are `14:38-14:39`; the 4.6/4.7 source fixes are `14:06-14:16`, so the run *did* use the patched tree.
- **Code**:
  ```python
  # 2) Look for the first file that already has valid artist+album tags
  meta: Optional[Meta] = None
  for t in audio_files:
      existing = tags_from_track(t)
      if existing:
          meta = existing
          break
  # 3) If none of the files had tags, do the online-lookup flow
  ```
  and the only gate on what counts as "valid":
  ```python
  if not au or "artist" not in au or "album" not in au:
      return None
  ```
- **Error**: two compounding faults.
  1. **No validation.** Any file with a non-empty `artist` and `album` is accepted verbatim. Audiobook rips routinely carry the *filename*, a disc marker, or a track index in `artist`.
  2. **Unconditional short-circuit.** When tags exist, `process()` skips `guess_from_folder()`, `choose_meta()` (provider lookup) **and** the LLM fallback. There is no confidence check and no cross-check against the folder name — so the bad value can never be corrected. The `llm_threshold` work is unreachable on this path.
  Separately, combobook **never calls `extract_series_and_title()`**. Its only series source is `guess_from_folder()`'s `PARENT_RANGE_RX` (a parent named `<Series> (YYYY-YYYY)`), and that function is unreachable whenever tags are present.
- **Impact — reproduced, 572 entries under `/home/citizenzero/Documents/temp_audiobooks/`**:

  | Output path | `artist` tag | `album` tag | What went wrong |
  |---|---|---|---|
  | `Side 01/Riftwar saga 03 - Silverthorn` | `Side 01` | `Riftwar saga 03 - Silverthorn` | a **disc marker became the author folder**; series `Riftwar saga` #3 never split out |
  | `AttheGatesofDarkness Part1 Track 01/At the Gates of Darkness` | `AttheGatesofDarkness Part1 Track 01` | `At the Gates of Darkness` | a **filename became the author folder** |
  | `Raymond E Feist/Serpentwar Saga 03 - Rage of a Demon King (1998)` | `Raymond E Feist` | `Serpentwar Saga 03 - Rage of a Demon King` | correct author, but **no series level** — should be `Raymond E Feist/Serpentwar Saga/Rage of a Demon King (1998)` |
  | `Andrzej Sapkowski, Terry Goodkind, Anthony Ryan, A/...` | 8 authors, 126 chars | 8 titles joined by `/` | truncated **mid-word at 50 chars**; a compilation filed as one pseudo-author |
  | `Raymond E. Feist/` **and** `Raymond E Feist/` | both spellings present in tags | — | the same author **split across two folders**; no normalisation |

  `extract_series_and_title()` handles every one of these series cases correctly when it is actually called:
  ```
  'Serpentwar Saga 03 - Rage of a Demon King (1998)'   -> ('Serpentwar Saga', '03', 'Rage of a Demon King (1998)')
  'Riftwar saga 03 - Silverthorn'                      -> ('Riftwar saga', '03', 'Silverthorn')
  'Riftwar Legacy 03 Krondor - Tear Of The God (2000)' -> ('Riftwar Legacy', '03', 'Krondor - Tear Of The God (2000)')
  ```
  It is simply never reached from `combobook.py`.
- **Fix applied (2026-09-05)**:
  1. **Tags became evidence, not an answer.** `process()` now computes the folder guess first, then accepts a track's tags only when `is_plausible_author()` passes; an implausible `artist` logs a reason and the book carries on to the folder guess, the providers and the LLM instead of short-circuiting.
  2. **`merge_tag_and_folder()`** merges tag- and folder-derived fields, and runs the album frame through `extract_series_and_title()` — so a tagged `"Serpentwar Saga 03 - Rage of a Demon King"` finally produces a series level.
  3. **The source tree is validated too.** `guess_from_folder()`'s parent climb runs the same guard, so a book filed under `Side 01/` no longer hands that string back as the author.
  4. **`primary_author()` / `normalise_author()`** collapse `Raymond E Feist` and `Raymond E. Feist` into one folder and reduce a 126-character credit list to its first author rather than truncating mid-word.
  5. **Provider queries stopped searching for a placeholder.** `_query_author()` omits the author clause when it is `"Unknown Author"`; previously every lookup for an untagged book searched for a nonexistent author and returned nothing.
  6. **The scorer was rewritten.** `_similarity()` compares title and author separately (concatenating them meant an unknown author dominated the diff: identical titles scored 0.44), treats a contained name as a match (`Feist` ≡ `Raymond E. Feist`), and rewards a matching sequence number without penalising its absence — providers almost never return the index, so the old −0.12 hit applied to nearly every correct match.
  7. **`--yes` gained a floor and an ambiguity guard.** `MIN_AUTO_SCORE` (0.75, `--auto-accept-score`) stops auto-accept taking a 0.47 match, and two candidates by different authors tying within 0.02 are refused outright rather than decided by sort order.
- **Verification**: `tests/test_organiser_resolution.py` — 31 tests, all passing, built from the real tag values. End-to-end on a fixture reproducing every failure:
  ```
  ↪ Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon
      → Raymond E. Feist/Riftwar Saga/A Darkness at Sethanon (1986)   [was _unmatched/]
  ↪ Raymond E Feist/Serpentwar Saga 03 - Rage of a Demon King (1998)
      → Raymond E. Feist/Serpentwar Saga/Rage of a Demon King (1998)  [was flat, no series]
  ↪ AttheGatesofDarkness Part1 Track 01/At the Gates of Darkness
      → Raymond E. Feist/At the Gates of Darkness (2009)              [was a junk author folder]
  ↪ Compilation/The Road with No Return
      → Andrzej Sapkowski/...                                         [was truncated mid-word]
  • Side 01/Riftwar saga 03 - Silverthorn
      ambiguous: Raymond E. Feist and Christopher C. Tubbs both match
      'Silverthorn' at 1.00; not guessing → left in place
  ```
  The remaining unmatched case is genuinely undecidable from the evidence on disk, and now says so instead of inventing an answer.
- **Original fix plan** (all items shipped):
  1. Treat first-track tags as *one candidate*, not as an answer. Sanity-check `artist` before accepting it — reject values matching `DISC_RX`, values equal to the audio filename stem, and values that are purely numeric or index-like.
  2. Always run `extract_series_and_title()` over the `album` tag and the folder name, so `Serpentwar Saga 03 - ...` yields a series level regardless of which source supplied the string.
  3. Fall through to `guess_from_folder()` → `choose_meta()` → LLM when the tag-derived author fails validation, instead of short-circuiting.
  4. Normalise author spelling (`Raymond E Feist` ≡ `Raymond E. Feist`) before it becomes a directory name, and split multi-author `,`-joined strings rather than truncating them.
- **Verification & Test Note**: the earlier 4.8 parity test cannot catch this — it starts from a pre-built `Meta`. A regression test must start from *files on disk*: write an MP3 with `artist="Side 01"`, `album="Riftwar saga 03 - Silverthorn"`, run `combobook.process()`, and assert the destination is `.../<real author>/Riftwar saga/Silverthorn`, **not** `.../Side 01/Riftwar saga 03 - Silverthorn`.

### 4.11 `read_tags` Prefers TIT2 (Track Title) Over TALB (Album Title)
- **Status**: 🛠️ **FIXED (2026-09-05)** — `read_tags` now prefers `TALB` / `\xa9alb` (the album, i.e. the book) and falls back to `TIT2` / `\xa9nam`; `strip_track_tail()` removes a trailing `NN of NN` / `Part N` / bare index while at least two words survive, so "Slaughterhouse 5" and "Catch 22" are untouched.
- **File**: [`ablib/tagging/files.py:223-226`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/tagging/files.py#L223-L226) — `read_tags`
- **Code**:
  ```python
  if "TIT2" in audio and audio["TIT2"].text:
      res["title"] = str(audio["TIT2"].text[0]).strip()
  elif "TALB" in audio and audio["TALB"].text:
      res["title"] = str(audio["TALB"].text[0]).strip()
  ```
- **Error**: for an audiobook, `TIT2` is the **track** title and `TALB` is the **book** title. Preferring `TIT2` means `target_for()` names the destination folder after a single track. Because `read_tags` sits at the *top* of `target_for`'s precedence chain, this overrides both the sidecar and the folder name.
- **Impact**: measured against files already in the library:
  ```
  Rage of a Demon King - 01 of 14   <- TIT2, would become the folder name
  Rage of a Demon King              <- TALB, correct
  01                                <- TIT2 for the Silverthorn rip
  At the Gates of Darkness Part1    <- TIT2, vs "At the Gates of Darkness" in TALB
  ```
- **Fix**: prefer `TALB` for the book title and treat `TIT2` only as a fallback when `TALB` is absent. (`combobook.tags_from_track()` already gets this right — it reads `au["album"][0]`.) Strip trailing `- NN of NN` / `Part N` / bare-index tails from whichever value is used.

### 4.12 `combobook.py`: Unidentifiable Folders Were Swept Into `_unmatched/`
- **Status**: 🛠️ **FIXED (2026-09-05)** — folders with no metadata match are now **left in place** by default. `--move-unmatched` (CLI) / **Move unmatched** (GUI, Tag & Move tab) restores the old behaviour.
- **File**: [`combobook.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py) — `process()`, `MOVE_UNMATCHED`
- **Error**: a folder reaches this branch precisely because *nothing* could identify it — no tags, no provider hit, no LLM answer. The only evidence left about what the book is, is **where it sat in the source tree**. Moving it into a flat `<library>/_unmatched/` destroyed exactly that, and (in the old code path) additionally ran `flatten()` / `rename_tracks()` on it, renaming the tracks of a book whose identity was unknown.
- **Impact**: reproduced — four Feist books landed in `_unmatched/` with names that were entirely parseable:
  ```
  _unmatched/Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon
  _unmatched/Feist - Empire Trilogy - Book 1 - Daughter of the Empire
  _unmatched/Feist - Chaoswar Saga  - Book 3 - Magician's End
  _unmatched/Feist - Riftwar Saga - Book 1 & 2 - Magician & Master
  ```
- **Root cause of *why* they were unmatched** (a folder-parsing fault, not a tag fault — these files are genuinely untagged, `artist=None`, `album=None`): `guess_from_folder()` cannot read this shape. It matches `LEAF_RX` (`Seq - Title (Year)`) against the leaf, then climbs **parent directories** looking for the author. These folders are flat under the source root, so there is no author parent:
  ```
  guess_from_folder("Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon")
    -> Meta(author='Unknown Author', title='Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon',
            year=None, series=None, seq=None)
  ```
  With `author='Unknown Author'` and a 54-character title, `choose_meta()`'s provider search cannot hit, and the LLM fallback also failed. Meanwhile the shared parser handles all four:
  ```
  extract_series_and_title("Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon")
    -> ('Feist - Riftwar Saga', '4', 'A Darkness at Sethanon')
  ```
  `combobook` never calls it — see [4.10](#410-combobookpy-first-track-tags-short-circuit-the-entire-metadata-pipeline). Remaining gaps once it does: the `Author - Series` prefix needs splitting on the first ` - `, and omnibus editions (`Book 1 & 2`) need a rule of their own.
- **Fix applied**: added module-level `MOVE_UNMATCHED = False`. When false, `process()` reports the folder, increments a new `left_in_place` counter, and returns **without** moving, flattening or renaming. Added `--move-unmatched` to the CLI parser, a **Move unmatched** checkbox to the GUI (snapshotted on the UI thread, per [3.x](#3-gui-logic-errors)), and `left_in_place` to both summary blocks.
- **Verification**: run against a real untagged book, `dry=False`:
  ```
  MOVE_UNMATCHED default = False
  • no metadata match: Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon
    left in place: .../src/Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon
  summary: {'total': 1, 'unmatched': 1, 'left_in_place': 1}
  source still there?  True
  lib contents      :  []
  ```
  and with the opt-in re-enabled:
  ```
  MOVE_UNMATCHED = True
  mv Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon → _unmatched/...
  summary: {'total': 1, 'unmatched': 1, 'moved': 1}
  source gone? True
  ```

### 4.13 `restructure_for_audiobookshelf.py`: Books at the Source Root Are Skipped Silently
- **Status**: 🛠️ **FIXED (2026-09-05)** — `discover_books()` now walks `[source_root, *source_root.rglob("*")]` and yields any directory holding a book, deriving the author from the path depth (empty when the layout has no author level). Verified 6/6 discovery parity with `combobook.leaf_dirs()`, and pointing the tool at a single book now processes it. This was [4.2](#42-combookpy--ablibclimainpy-root-folder-ignored-when-pointing-directly-to-a-book) again, in the one tool that never got the fix. `combobook.py` and `ablib/cli/main.py` were both corrected to `[root, *root.rglob("*")]`; `restructure_for_audiobookshelf.py` was not.
- **File**: [`restructure_for_audiobookshelf.py:128-138`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/restructure_for_audiobookshelf.py#L128-L138) — `discover_books`
- **Error**: `discover_books()` assumes every directory under the source root is an *author* directory, and only ever yields at depth 2 (`<source>/<Author>/<Book>`) or depth 3 (`<source>/<Author>/<Series>/<Book>`). Two shapes therefore yield nothing:
  1. a book folder sitting **directly** under the source root — the loop treats it as an author directory, looks inside for sub-directories, finds only audio files, and moves on;
  2. the source root **itself** being a single book.
- **Impact**: silent. There is no warning, and the run reports success for a smaller number than it was given. Measured on the same fixture:
  ```
  combobook.leaf_dirs        : 6
  restructure.discover_books : 5
  SKIPPED SILENTLY: {'Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon'}
  ```
  and pointed straight at one book:
  ```
  $ restructure_for_audiobookshelf.py ".../Raymond E. Feist/Faerie Tale (1988)" dst
  Processed 0 books (dry-run) - moved: 0, skipped: 0     <- reports success, did nothing

  $ combobook.py ".../Raymond E. Feist/Faerie Tale (1988)" dst
  would_move   : 1                                        <- correct
  ```
  The GUI's **Restructure** button calls this function, so it inherits the gap.
- **Fix**: walk the tree the way `combobook.leaf_dirs()` does — consider the root itself and every descendant, yield any directory that `has_audio()`, and derive the author from the parent only when there is one. Then report a count of directories inspected alongside books found, so a mismatch is visible rather than silent.

### 4.14 `restructure_for_audiobookshelf.py`: No "Leave In Place" for Books It Cannot Identify
- **Status**: 🛠️ **FIXED (2026-09-05)** — `target_for` was split into `resolve_book_metadata()` (what was resolved) and `target_for()` (where it goes), so `restructure_library()` can see the author was never identified and decline the move. Books resolving to `Unknown Author` are left in place and counted as `left_in_place`; `--move-unmatched` restores the sweep, matching combobook's flag name. The counterpart to [4.12](#412-combobookpy-unidentifiable-folders-were-swept-into-_unmatched).
- **File**: [`restructure_for_audiobookshelf.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/restructure_for_audiobookshelf.py) — `target_for` / `restructure_library`
- **Error**: when nothing resolves an author, `target_for()` returns `"Unknown Author"` and the book is moved there regardless. Unlike combobook, this tool has no provider or LLM fallback to recover from, and no option to decline the move.
- **Impact**: on the audit fixture, two books were moved out of a meaningful source path into a shared bucket:
  ```
  Side 01/Riftwar saga 03 - Silverthorn        -> Unknown Author/Riftwar saga/Silverthorn
  AttheGatesofDarkness .../At the Gates of ... -> Unknown Author/At the Gates of Darkness
  ```
  `Unknown Author/` is `_unmatched/` by another name, and 4.12 already established why that is the wrong default: the source path is the last evidence about a book nothing could identify.
- **Fix**: apply the 4.12 decision here too — skip the move when the resolved author is `"Unknown Author"`, report it, and gate the old behaviour behind the same `--move-unmatched` flag so both organisers take the same option name.

- **Verification**:
  ```
  $ restructure_for_audiobookshelf.py src lib
  [unidentified] left in place: src/AttheGatesofDarkness Part1 Track 01/At the Gates of Darkness
  [dry-run] src/Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon
              -> lib/Feist/Riftwar Saga/A Darkness at Sethanon      <- was skipped entirely
  [unidentified] left in place: src/Side 01/Riftwar saga 03 - Silverthorn
  Processed 6 books (dry-run) - moved: 0, skipped: 0, left in place: 2   <- was "Processed 5"

  $ restructure_for_audiobookshelf.py ".../Faerie Tale (1988)" lib
  Processed 1 books ...                                             <- was "Processed 0"
  ```
  Also confirmed: a book found at the source root no longer takes the source directory's own name as its series, multi-disc books still yield the book folder rather than one entry per disc, and a second pass over the output moves nothing (`moved: 0, skipped: 2`, tree unchanged).

### 4.15 `book.nfo` and `metadata.json` Described the Same Book Differently
- **Status**: 🛠️ **FIXED (2026-09-05)**
- **File**: [`ablib/tagging/files.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/tagging/files.py) — `export_metadata`, `build_book_nfo`
- **Error**: `export_metadata` wrote `metadata.json` through `format_abs_metadata()` but built `book.nfo` by looping over the raw `meta` dict. The two sidecars for one book therefore disagreed — `<author>` / `<series_index>` in the XML against `authors` / `sequence` in the JSON — and whatever incidental keys the pipeline was carrying leaked into the XML as elements (`<score>93</score>`).
- **Fix applied**: added `build_book_nfo(abs_payload)`; both files are now derived from the one payload, so disagreement is impossible. Element names follow the Kodi/Emby/Jellyfin convention that actually reads the file — repeated `<author>` / `<narrator>` / `<genre>`, plus `<year>`, `<series>` and `<seriesnumber>` — rather than Audiobookshelf's JSON keys. The 5.1 `str()` guard is preserved.
- **Verification**: `test_nfo_and_json_describe_the_same_book` asserts every shared field matches across the two files, and that `<series_index>` and `<score>` are gone.

### 4.16 The Schema Fix Never Reached Libraries Already on Disk
- **Status**: 🛠️ **FIXED (2026-09-05)**
- **Files**: [`ablib/tagging/files.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/tagging/files.py) — `upgrade_sidecar`, `sidecar_is_current`; [`restructure_for_audiobookshelf.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/restructure_for_audiobookshelf.py) — `refresh_sidecars`
- **Error**: [4.9](#49-metadatajson-does-not-match-audiobookshelfs-schema) fixed the *writer*, but sidecars are only written at tagging time. The organisers **move** `metadata.json` and `book.nfo`; they never rewrite them. Every book tagged before the fix therefore kept the old flat schema — which is exactly what was observed in the audited library, where the sidecars were dated `13:02` against a `14:16` fix — and Audiobookshelf goes on ignoring them.
- **Fix applied**: `upgrade_sidecar(folder)` re-reads what is on disk (existing sidecar first, embedded tags for anything it does not cover) and rewrites both files in the current schema. `sidecar_is_current()` keys off the `authors` array, so a run over a large library only touches folders that need it. Exposed as `restructure_for_audiobookshelf.py <library> --refresh-sidecars [--commit]`, which moves nothing (`destination` is not required in this mode), and as **Refresh Sidecars** on the GUI's Organise tab.
- **Verification**:
  ```
  $ restructure_for_audiobookshelf.py lib_old --refresh-sidecars
  [dry-run] would refresh sidecars: lib_old/Raymond E. Feist/Faerie Tale (1988)
  Inspected 1 books (dry-run) - refreshed: 1, already current: 0

  $ restructure_for_audiobookshelf.py lib_old --refresh-sidecars --commit
  Inspected 1 books (applied) - refreshed: 1, already current: 0

  $ restructure_for_audiobookshelf.py lib_old --refresh-sidecars --commit
  Inspected 1 books (applied) - refreshed: 0, already current: 1
  ```

### 4.17 A Hosted Quota Error Abandoned Every Remaining Book
- **Status**: 🛠️ **FIXED (2026-09-05)** — reported from the field, mid-run against OpenRouter's free tier:
  ```
   guess: Homeward Bound by Worldwar - Colonization (?)
     - no match
    - LM Studio returned HTTP 429: {"error":{"message":"Rate limit exceeded:
      free-models-per-day. Add 10 credits to unlock 1000 free model requests per day"...
    - LM Studio metadata request returned no content
    - no metadata found
  ```
- **Files**: [`ablib/metadata/llm.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/llm.py), [`ablib/core/config.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/core/config.py), [`combobook.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py)
- **Error**: `_call_llm` returned `None` for *every* failure alike, and the caller then gave up on the book. A hosted free tier exhausts its daily quota partway through a large run, so from that point on every remaining book was reported "no metadata found" — even though a local model was sitting there able to answer. Three further faults were visible in that one log excerpt:
  1. Every message said **"LM Studio"** regardless of endpoint, so a quota error from `openrouter.ai` read as though the local server had produced it.
  2. `combobook` called `generate_metadata_via_llm(folder, audio_files)` with **no `guess`**, so nothing downstream had anything to check an answer against.
  3. The gap-filling retry always went back to the primary endpoint, so after any successful failover it hit the same quota error again.
- **Fix applied**:
  - `_call_llm` takes an explicit `endpoint` / `model` / `api_key` and reports failures through an `on_retryable_failure` out-parameter. Only statuses another endpoint might not share are retryable — `401, 402, 403, 408, 409, 429, 500, 502, 503, 504` and transport errors. **400 and 404 are not**: a malformed request or a missing model fails identically anywhere, and a model that answered badly would answer badly twice.
  - `_call_llm_with_fallback()` retries on `llm_fallback_endpoint` (default `http://127.0.0.1:8888/v1/chat/completions`), and the gap-filling retry now stays on whichever endpoint actually answered.
  - `_endpoint_label()` names the host, so the line reads `openrouter.ai HTTP 429` or `local LLM`.
  - `combobook.process()` now passes the folder guess.
  - The MCP refinement stages use the same fallback; their results are already gated on `MCP_ACCEPT_SCORE`.
- **The gate on fallback answers**: there is no provider score on this path, and a small local model asked *"which audiobook is this folder?"* answers confidently whether or not it knows. `fallback_confidence()` compares its title and author against the folder guess (`0.7 × title + 0.3 × author`, title alone when no author is known) and returns **0 when there is nothing to compare against**, so an unverifiable answer is never treated as confident. Below `llm_fallback_min_score` (default 85, `--llm-fallback-min-score`, **Min score** in the GUI) the book is **left untagged** and the reason written to the review log.
- **Verification** — two fake endpoints, a rate-limited "hosted" one and a local one:
  ```
  A. local agrees with the folder
    - openrouter HTTP 429 ... - falling back to local LLM (local/model)
    - local LLM answer accepted (score 100)
    RESULT : {'title': 'Homeward Bound', 'author': 'Harry Turtledove', 'series': 'Worldwar', ...}
    calls  : hosted=1 local=1

  B. local invents "The Hobbit"
    - falling back to local LLM (local/model)
    - local LLM answer scores 33 against the folder (needs 85); leaving untagged
    RESULT : None
  ```
  Covered by `tests/test_llm_fallback.py` (10 tests), including that a merely *bad* answer never triggers the fallback and that a fallback pointed at the failing endpoint is skipped rather than asked twice.

### 4.18 The Provider Layer Sent Work to the LLM That It Could Answer Itself
- **Status**: 🛠️ **FIXED (2026-09-05)** — measured against a real library, `/home/citizenzero/Downloads/Harry Turtledove` (15 books, `<Author>/<Series (years)>/<N - Title (Year)>`).

  | | before | after |
  |---|---|---|
  | matched by a provider | 15/15 | 15/15 |
  | scored **below** the 85 threshold, i.e. handed to the LLM | **14/15** | **0/15** |
  | wrong book chosen | 3 | 0 |
  | wall clock | 91s | 36s |

- **Files**: [`ablib/metadata/utils.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/utils.py) (`guess_from_path`), [`ablib/providers/http.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/http.py), [`ablib/core/http.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/core/http.py), [`combobook.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py)
- **Errors** — five faults, compounding:
  1. **The series folder was read as the author.** `guess_from_path` took the immediate parent unconditionally, so `Harry Turtledove/Worldwar - Colonization (1994-2004)/8 - Homeward Bound (2004)` was queried as *author* `"Worldwar - Colonization"` — and its year `(2004)` and index `8` were dropped entirely. A nonexistent author suppressed every correct hit and let unrelated books by real authors outrank them: *Homeward Bound* by **Elaine Tyler May**, *Aftershocks* by **Catherine Coulter**, *Second Contact* by **Craig A. Falconer** all won at 80-84. `combobook.guess_from_folder` had this right via `PARENT_RANGE_RX`; the CLI path did not.
  2. **Goodreads had never worked.** The shared session identified as `python-requests/2.34.2`; Goodreads answers **403** to that, and the helper called `.text` with no `raise_for_status()`, so it parsed the error page and returned `None` — silently, on every book since the tier existed. It is queried *first*, so this cost one wasted request per book and lost the only provider that names the series inline.
  3. **Scoring was deflated when no author was known.** Fixed weights meant a *perfect* title match scored `100 × 0.7 = 70` — below `ACCEPT_SCORE` (85) *and* the default `--llm-threshold` (85). Every untagged book went to the LLM even when a provider had already returned exactly the right book.
  4. **Rip debris went straight into the query.** `"Daughter of the Empire 128kbps"` matched nothing at all; `"Magicians End (Unabridged)"` scored 45.
  5. **One query, one chance.** If the first form found nothing, nothing else was tried.
- **Fix applied**:
  - `guess_from_path` reads the leaf with the shared `parse_book_folder_name`, then recognises a parent named `<Series> (YYYY[-YYYY])` as a series level and takes the author from above it (`split_parent_series`). All five fields are now recovered.
  - The shared `SESSION` sends a browser User-Agent and retries `429/5xx` twice with backoff.
  - `score_candidate()` weights each dimension only when there is something to compare against, so title alone decides when no author is known.
  - `clean_query_title()` strips `(Unabridged)`, `[Audiobook]`, bitrates, `NN of NN`, disc/part markers, bare `(YYYY)`, and unbalanced trailing parentheticals — the last for `"2 - West and East (20109"`, a real folder whose year is a typo.
  - `best_match()` runs a short ladder: as guessed → without the guessed author (a directory name is a guess, the title rarely is) → with the series appended. Each rung only runs if the previous found nothing at/above `ACCEPT_SCORE`, so a confident first hit still costs one request.
  - Providers return `series`/`series_index`/`isbn`/`language`. `split_series_suffix()` lifts a series out of the title (`Silverthorn (The Riftwar Saga, #3)`, `(Colonization, Book 2)`, `(Worldwar Series, Volume 2)`, `Book One`), and `strip_edition_tail()` removes a `by <Author> (1996-12-05)` reissue tail — which would otherwise have become the folder name.
  - Results are cached per query, bounded at 512.
  - Goodreads throttles with **HTTP 202 and an empty body**, which `raise_for_status()` does not catch; three consecutive refusals now disable it for the rest of the run instead of wasting a request per book.
  - `combobook` uses the same `clean_query_title`, and its folder guess strips a leading `N - ` index even when the trailing year is malformed.
- **Verification**: `tests/test_provider_queries.py` (30 tests, no network). Full suite 86.

### 4.19 Two Scoring Scales, and combobook's Floor Sat Inside the Wrong-Answer Band
- **Status**: 🛠️ **FIXED (2026-09-05)** — one constant, `constants.DEFAULT_MATCH_THRESHOLD = 83`, now read by every match decision.
- **Files**: [`ablib/core/constants.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/core/constants.py), [`combobook.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/combobook.py), [`ablib/providers/http.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/http.py), [`ablib/core/config.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/core/config.py), [`ablib/cli/main.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/cli/main.py), [`AbtoolsGui.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/AbtoolsGui.py)
- **Error**: "the threshold" meant two different things. `combobook._similarity` graded 0-1 with its own SequenceMatcher blend and a `MIN_AUTO_SCORE` floor of **0.75**; everything else graded 0-100 via `score_candidate` with a bar of 85. Worse, combobook's scale compressed the bands until they **overlapped**:
  ```
  1.00  ACCEPTED   CORRECT exact
  0.82  ACCEPTED   CORRECT superset title
  0.79  ACCEPTED   WRONG author, right title   <- accepted
  0.75  ACCEPTED   WRONG author, right title   <- accepted, exactly at the floor
  0.53  rejected   WRONG book
  ```
  Correct answers ran 0.82-1.00 and wrong ones 0.75-0.79 — a 0.03 gap with the floor *inside* the wrong band, so `--yes` would write a confidently wrong author. No choice of number could fix it: 0.82 is a correct case.
- **Measured bands** on `score_candidate` (0-100), from the audited library:

  | score | what it is |
  |---|---|
  | 100 | correct — exact title, superset title, surname-only folder, missing initial |
  | 97 | correct, one-character typo in the title |
  | *81* | *right title, **wrong author*** — Homeward Bound / Elaine Tyler May, Aftershocks / Catherine Coulter, Second Contact / Craig A. Falconer |
  | 80 | title padded, different book |
  | 78 | words reordered, different book |
  | 65 | query title is a subset of the hit |
  | 53 | right author, wrong book |

  **70-80 is the wrong-answer band.** The gap is 81 → 97.
- **Fix applied**: `combobook._similarity` delegates to the shared `score_candidate`, so both tools grade identically; its bands become 100 / 81 / 53 and the wrong-author cases are now **rejected**. Every threshold reads `DEFAULT_MATCH_THRESHOLD`: `ACCEPT_SCORE`, `--llm-threshold`, `--auto-accept-score`, `llm_fallback_min_score`, and both GUI spinboxes. `--auto-accept-score` changed scale from 0-1 to 0-100, and the ambiguity guard's tie window from 0.02 to 2.0.
- **Follow-up (same day)**: `MCP_ACCEPT_SCORE` now reads `DEFAULT_MATCH_THRESHOLD` too, at the user's direction, so there is one number in the project. It gates `calculate_combined_score`, which is a *different scale* (the model's self-reported score averaged with a fuzzy blend that includes the folder name), so the 83 bands measured on `score_candidate` do not transfer to it — recorded in the constant's comment. Practical effect: stage-1 MCP refinements scoring 83-94 are now accepted and skip the SequentialThinking stage, where they were previously discarded.
- **Verification**: `test_the_threshold_sits_between_the_measured_bands` asserts real correct results land at/above 83 and real wrong ones below it; `test_every_match_threshold_is_the_shared_constant` stops them drifting apart again.

## 5. Metadata, Providers & Tagging Logic Errors

### 5.1 `ablib/tagging/files.py`: Non-String Metadata Crashes XML Serializer
- **Status**: 🛠️ **FIXED (2026-09-05)** — `child.text = str(value)`. Verified: a dict carrying `score=93` now writes `<score>93</score>` instead of raising.
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
- **Status**: 🛠️ **FIXED (2026-09-05)** — now `re.split(r"\s+[-–—]\s+", cleaned)`, so a dash only splits when it is surrounded by whitespace. Verified: `'Jean-Paul Sartre - Nausea'` previously split to `['Jean', 'Paul Sartre', 'Nausea']` and yielded no author; it now yields `author='Jean-Paul Sartre'`, `title='Nausea'`.
- **File**: [`ablib/metadata/utils.py:168`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/utils.py#L168)
- **Code**:
  ```python
  parts = [part.strip() for part in re.split(r"\s*[--]\s*", cleaned) if part.strip()]
  ```
- **Error**: `[--]` is the character range `-` to `-`, i.e. a plain hyphen; with `\s*` on both sides optional, it splits on **internal** hyphens too. The intent was almost certainly `[-–—]` (hyphen / en-dash / em-dash), mangled by an encoding round-trip.
- **Impact**: `'Sci-Fi - Asimov'` → `['Sci', 'Fi', 'Asimov']`; `'Jean-Paul Sartre - Nausea'` → `['Jean', 'Paul Sartre', 'Nausea']`. `parts[0]` then contains no space, so `author_hint` is discarded and `title_part` is corrupted.
- **Fix**: `re.split(r"\s+[-–—]\s+", cleaned)` — require surrounding whitespace so only true delimiters match.

### 5.3 `ablib/providers/http.py`: `openlib` and `gbooks` Never Called in `best_match`
- **Status**: 🛠️ **FIXED (2026-09-05)** — the providers are now a list walked in order with an early return once one scores ≥85, so the common case stays fast. Verified by instrumenting each provider: all four are queried in order `goodreads, audible, openlib, gbooks`.
- **File**: [`ablib/providers/http.py:182-192`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/http.py#L182-L192)
- **Error**: `best_match()` queries only Goodreads and Audible. `openlib` and `gbooks` are defined and exported, but reached only from `enrich_metadata_with_providers` (gap-filling), never for primary matching.
- **Impact**: When Goodreads and Audible both miss, `best_match()` returns `None` and the pipeline escalates to the LLM without ever consulting Open Library or Google Books — contradicting `README.md`, which lists all four as match sources.
- **Fix**: Add `openlib` / `gbooks` to the candidate sweep in `best_match()`.

### 5.4 `ablib/providers/mcp.py`: `_parse_provider_query` Splits on "by" Inside Titles
- **Status**: 🛠️ **FIXED (2026-09-05)** — searches from the right and requires a two-word author. See the trade-off note below.
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
- **Fix applied**: iterates matches right-to-left and accepts a split only when both sides are non-empty, the author contains no digits, and the author is **two or more words**.
- **Deliberate trade-off**: a mononym author stays unsplit — `"The Iliad by Homer"` is searched whole rather than split. A single-word tail is too ambiguous to act on (`"Side by Side"` would otherwise become title=`"Side"`, author=`"Side"`), and searching the full string still matches, whereas a wrong split corrupts both fields.

### 5.5 `mcp_server/tools/audible.py` & `goodreads.py`: Missing URL Parameter Encoding
- **Status**: 🛠️ **FIXED (2026-09-05)** — both now pass `params={...}` to `requests.get`, matching the sibling `googlebooks.py`/`openlibrary.py` modules.
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
- **Status**: 🛠️ **FIXED (2026-09-05)** — writes `TXXX:series-part` (MP3) and `----:com.apple.iTunes:series-part` (MP4). Verified: a tagged file now carries `TXXX:series-part` alongside `TXXX:series`.
- **File**: [`ablib/tagging/files.py:53-70`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/tagging/files.py#L53-L70)
- **Error**: `write_tags()` writes `series` to ID3 (`TXXX:series`) and MP4 (`----:com.apple.iTunes:series`) but never writes `series_index`, even though the pipeline resolves it and `export_metadata` persists it to `metadata.json` / `book.nfo`.
- **Impact**: Embedded tags lose series position; Audiobookshelf cannot order a series from the audio files alone.
- **Fix**: Write `TXXX:series-part` (MP3) and `----:com.apple.iTunes:series-part` (MP4), matching the keys `combobook.tags_from_track` already reads back.

### 5.7 `ablib/metadata/utils.py`: `guess_from_path` Can Discard the Real Title
- **Status**: 🛠️ **FIXED (2026-09-05)** — when there are 2+ segments the title is always `parts[-1]`; `combined` is now mined only for series metadata. Verified: `"Author - Series 3 Bonus - The Real Title"` returns `title='The Real Title'` (was `'Bonus'`), with `"Frank Herbert/Dune (1965)"` and `"Brandon Sanderson - Mistborn 1 - The Final Empire"` unchanged.
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
- **Status**: 🛠️ **FIXED (2026-09-05)** — candidates missing a title or author are skipped before the dedup key is built, and an empty candidate list returns `None`. Verified: providers returning null titles now yield `None` instead of raising.
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

### 5.9 `ablib/metadata/llm.py`: Gap-Filling Retry Replaces Instead of Merging
- **Status**: 🛠️ **FIXED (2026-09-05)** — the retry result is merged over the primary, primary winning conflicts. *(Found in a follow-up pass over `ablib/`; not in either earlier audit.)*
- **File**: [`ablib/metadata/llm.py:394-396`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/llm.py#L394-L396)
- **Error**: `generate_metadata_via_llm` issues a second LLM call whose *sole purpose* is to fill optional fields the first response omitted, then did `result = retry_result` — discarding everything the primary had established.
- **Impact**: the retry could leave **less** metadata than before it ran. Reproduced: a primary carrying `year`, `narrator`, `publisher` and `description` but missing `series`, followed by a retry supplying `series` but omitting the rest, produced `{'title', 'author', 'series', 'series_index'}` — `year`, `narrator`, `publisher` and `description` all silently lost.
- **Fix applied**: `merged = dict(retry_result)` then `merged.update({k: v for k, v in result.items() if v})`, so the retry supplies only gaps. Verified: all four primary fields survive and `series` is still gained.

### 5.10 `ablib/`: Three Different Bars for Accepting an MCP Refinement
- **Status**: 🛠️ **FIXED (2026-09-05)** — unified as `MCP_ACCEPT_SCORE`. *(Follow-up pass.)*
- **Files**: [`ablib/metadata/llm.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/llm.py), [`ablib/cli/main.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/cli/main.py)
- **Error**: `refine_metadata_via_mcp` returned early once stage 1 scored **≥90**, but both callers only accepted **≥95** (a third path accepted any result). A stage-1 result scoring 90-94 therefore skipped the SequentialThinking stage *and* was then thrown away by the caller.
- **Impact**: books in that band lost the benefit of stage 2 and fell through to the plain LLM path — the expensive refinement ran and its output was binned.
- **Fix applied**: one exported `MCP_ACCEPT_SCORE = 95` used by the stage-1 gate and both callers, so they cannot drift again. The validation-recovery path at `main.py:264` still accepts any result deliberately, because it re-validates immediately afterwards.

### 5.11 `ablib/providers/http.py`: Provider Lookups Were Serial Despite the Advertised Parallel Fetch
- **Status**: 🛠️ **FIXED (2026-09-05)** — tiered, with the second tier concurrent. *(Follow-up pass.)*
- **File**: [`ablib/providers/http.py:145-199`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/http.py#L145-L199)
- **Error**: every lookup was sequential at a 10s timeout each. `ThreadPoolExecutor`/`as_completed` were imported but unused — flagged by pyflakes — and `README.md` advertised "Fetches metadata in parallel for faster tagging", which was untrue of `ablib`. Adding openlib/gbooks in [5.3](#53-ablibprovidershttppy-openlib-and-gbooks-never-called-in-best_match) had made a miss cost up to four chained timeouts.
- **Fix applied**: tier 1 queries Goodreads alone and short-circuits at ≥85, so a confident hit still costs one request and the scraped sites are not hit four times unnecessarily; tier 2 fans the remaining three out concurrently. Verified with 1s stub providers: **2.00s** vs ~4.0s serial, all four queried, and a confident Goodreads hit still returns in 0.00s having queried only Goodreads.

### 5.12 `ablib/providers/mcp.py`: `MCP_RESULT_CACHE` Grew Without Bound
- **Status**: 🛠️ **FIXED (2026-09-05)** — capped at 512 entries, oldest evicted first. *(Follow-up pass.)*
- **File**: [`ablib/providers/mcp.py:25-26`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/mcp.py#L25-L26)
- **Error**: `mcp_full_web_search` wrote every result into a module-level dict that nothing ever cleared.
- **Impact**: a long run over a large library retained every search result for the life of the process. Verified: 1200 cached results now settle at 200 live entries under the cap instead of growing unbounded. Dropping a stale id costs at most one re-fetch.

### 5.13 `ablib/metadata/utils.py`: Cosmetic Validation Issues Refuse the Whole Book
- **Status**: 🛠️ **FIXED (2026-09-05)** — only missing title/author are fatal now. *(Second follow-up pass over `ablib/`.)*
- **Files**: [`ablib/metadata/utils.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/metadata/utils.py), [`ablib/cli/main.py:249`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/cli/main.py#L249)
- **Error**: `validate_metadata_fields` returned `(len(issues) == 0, issues)`, so *any* finding marked the metadata invalid — and `process_leaf` treats invalid metadata as fatal: it logs `REVIEW`, writes the review log and returns **without tagging**.
- **Impact**: a book with a perfect title and author was refused because its description ran to seven characters. Same for an empty narrator string, a `series_index` with no series name, or a malformed year. It also triggered a pointless MCP refinement attempt for those cosmetic cases.
- **Fix applied**: `FATAL_VALIDATION_ISSUES = {"missing_title", "missing_author"}`; `usable` reflects only those, while `issues` still reports everything. `process_leaf` prints the advisory ones as `metadata notes:` and proceeds. Verified: short description / empty narrator / stray series_index / odd year are all now usable, while missing title, missing author, and both together remain fatal.

### 5.14 `ablib/providers/http.py`: Enrichment Queried Every Provider Hunting a Nonexistent Series
- **Status**: 🛠️ **FIXED (2026-09-05)** — loop termination now keyed on author/year only. *(Second follow-up pass.)*
- **File**: [`ablib/providers/http.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ablib/providers/http.py) — `enrich_metadata_with_providers`
- **Error**: `needed` included `series`, and the loop only stopped once `needed` was empty. Most books are standalone and have no series, so `needed` could never empty — every such book ran Audible, Open Library **and** Google Books serially at a 10s timeout each, purely to look for a series that does not exist.
- **Impact**: up to 30s of avoidable lookups per book, on top of `best_match`, for the common case of a book that already had author and year.
- **Fix applied**: termination is decided by author/year alone; `series` is still filled opportunistically from whatever a provider happens to return. Verified: a book with author and year known now makes **zero** provider calls (was three), a book missing both still enriches and stops at the first provider that answers, and series is still picked up when offered.

## 6. GUI & CLI Synchronization Issues

### 6.4 `AbtoolsGui.py`: The Folder Browser Shows Nothing for a Network Share
- **Status**: 🛠️ **FIXED (2026-09-05)** — reported from the field: *"when the folder is network mounted like `citizenzero@10.10.10.10:/home/citizenzero/bshelf` the browser is returning no folders, empty."*
- **File**: [`AbtoolsGui.py`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/AbtoolsGui.py) — `choose_directory`, and the new `local_path` / `remote_to_mount_point` / `mounted_twin`
- **Error**: three separate faults, all of which present identically as an empty browser.
  1. **A remote location is not a path.** `citizenzero@10.10.10.10:/home/citizenzero/bshelf` is an sshfs source string. `Path()` parses it as a *relative* path whose first component is `citizenzero@10.10.10.10:`, so it is never a directory:
     ```
     Path parts : ('citizenzero@10.10.10.10:', 'home', 'citizenzero', 'bshelf')
     is_dir     : False
     parent walk: [... , 'citizenzero@10.10.10.10:', '.']
     landed on  : '.'  ->  /home/citizenzero/Documents/Key/Abtools/ABtools
     ```
     `choose_directory` walked up until something was listable, silently landed on the **working directory**, and said nothing.
  2. **Mount-shadowed paths.** This host is a btrfs `@`-subvolume layout: `/home` is subvolid 259 (`subvol=/@home`) mounted at `/home`, and `/@home` is the same subvolume reached from the root subvolume. They are the same directory on disk, but **only `/home` carries the mounts**:
     ```
     /home/citizenzero/pi_share   ->  23 entries   (the sshfs mount)
     /@home/citizenzero/pi_share  ->   0 entries   (the bare mount point underneath)
     ```
     The GUI had `"dest": "/@home/citizenzero/Documents/temp_audiobooks"` saved in `~/.abtools_gui.json`, and `/` lists `@home` right next to `home`, so this is easy to reach by accident and impossible to diagnose from the UI.
  3. **An empty box was never explained.** `populate()` printed only `..` whether the folder was empty, held files but no sub-folders, or was a shadowed mount point. It also built the listing with `sorted(c for c in path.iterdir() if c.is_dir())` inside one `try`, so a single entry raising `OSError` — routine on a flaky network share — discarded the whole listing.
- **Fix applied**:
  - `remote_to_mount_point()` reads `/proc/mounts` (decoding its octal escapes) and maps a remote location to where it is actually mounted, matching the source exactly or as a parent with the remainder appended. Handles sshfs `user@host:/path`, `//host/share`, and the `sftp://` / `ssh://` / `smb://` / `cifs://` / `nfs://` prefixes.
  - `local_path()` wraps it and is now the single place the GUI turns user-typed text into a `Path` — so the remote form works in the Source and Destination fields, not just the browser.
  - `mounted_twin()` finds the mounted equivalent of a shadowed path by comparing parents with `os.path.samefile`, so it does not care what the subvolume is called. The browser offers it as a double-clickable row.
  - `choose_directory` now reports when it could not reach the requested location instead of silently relocating, `go_typed` says *"… is not a folder on this machine"* rather than doing nothing, per-entry `OSError` skips one entry instead of the listing, and an empty result always states *why* — empty, files-only, or shadowed.
- **Verification** against the live mount on the reporting machine:
  ```
  local_path("citizenzero@10.10.10.10:/home/citizenzero/bshelf")
    -> /home/citizenzero/pi_share    listable: True   entries: 24

  mounted_twin("/@home/citizenzero/pi_share")   (0 entries)
    -> /home/citizenzero/pi_share                     (24 entries)
  ```
  Covered by `test_remote_location_maps_to_its_mount_point`, `test_local_path_accepts_a_remote_location` and `test_mount_shadowed_path_finds_its_mounted_twin`.

### 6.1 `find_duplicates.py`: `--only-src-log` Is Dead Code in CLI
- **Status**: 🛠️ **FIXED (2026-09-05)** — the CLI now reads `root/duplicate_log.txt` via `_read_paths_from_log()` and passes the result as `limit_paths` / `limit_src`. Both scan functions had always accepted it and the GUI already wired it; only the CLI dropped the flag on the floor. It now also exits with a clear message when the log is missing or lists nothing usable.
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

### 6.3 `AbtoolsGui.py`: Tkinter `clam` Default `lightcolor: #EEEBE7` Draws Glaring White Line Around Tab Container
- **Status**: 🛠️ **FIXED (2026-09-05)** — configured root `.` with `bordercolor/lightcolor/darkcolor = BORDER` and `TNotebook` with `bordercolor=BG, lightcolor=BG, darkcolor=BG`, borderless flat tabs.
- **File**: [`AbtoolsGui.py:305-365`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/AbtoolsGui.py#L305-L365)
- **Error**: In Tkinter's `clam` theme engine, the `Notebook.client` container element draws a 3D bevel around the active tab area using a built-in default `lightcolor: #EEEBE7` (off-white) unless overridden. Because `style.configure(".")` and `TNotebook` omitted `lightcolor`, a bright white rectangular line framed the entire notebook content across dark themes (measured empirically across `y=36`, `y=514`, `x=24`, `x=693`).
- **Impact**: In all dark themes, the tab area was framed by a jarring, high-contrast off-white line that cut through the dark theme styling.
- **Fix applied**: Configured root `.` style with `bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER` to eliminate any clam `#eeebe7` fallback, and configured `TNotebook` with `bordercolor=BG, lightcolor=BG, darkcolor=BG` and `tabmargins=(0, 0, 0, 0)` with borderless `flat` tabs. Active tabs now seamlessly flow directly into the tab card body with zero white border.

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
- **Status**: 🛠️ **FIXED (2026-09-05)** — the title is truncated to `MAX_TITLE_LEN - len(" (YYYY)")` first and the year appended after. Verified: the same 65-char title now yields `'The Extraordinarily Long And Winding Title (2003)'` (49 chars, year intact); short titles and year-less titles are unchanged.
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

## 9. Encoder Output Formats & Deletion Safety

Found while adding output profiles to `ab_encode.py` on 2026-09-06. Evidence throughout is the user's own library at `~/Downloads/Harry Turtledove` (353 MP3s, 3 M4Bs across 15 books), which turns out to contain 8 MP3s and 2 M4Bs that are part-finished downloads — an unplanned but ideal test set.

### 9.1 `ab_encode.py`: Folders of `.m4b` parts were invisible, not skipped
- **Status**: 🛠️ **FIXED (2026-09-06)**
- **File**: [`ab_encode.py:40`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L40)
- **Error**: `EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".ogg")` — no `.m4b`, no `.opus`, no `.mp4`. `main()` queues a folder only when `any(f.lower().endswith(EXTENSIONS))`, so a folder holding only `.m4b` files produced **no task at all**: no encode, no skip message, no line in the final report.
- **Impact**: reproduced against the real library. `The War That Came Early/2 - West and East (20109/` holds `1.m4b` and `2.m4b`, a two-part book that was never joined and never mentioned:
  ```
  EXTENSIONS: ('.mp3', '.wav', '.flac', '.m4a', '.ogg')
  folders ffmpeg would process: 13
  folders WITH audio that are NOT in the task list:
     The War That Came Early (2009-2014)/2 - West and East (20109 -> ['1.m4b', '2.m4b']
     Through Darkest Europe (2018) -> ['Through Darkest Europe.m4b']
  ```
- **Fix applied**: `EXTENSIONS` now covers `.mp3 .m4a .m4b .mp4 .aac .opus .ogg .oga .flac .wav .wma .aiff .aif`, and the output file is excluded from its own source list by name.
- **Verification**: `test_a_folder_of_m4b_parts_is_now_visible_to_the_walker`. On the real folder the run now reports the true problem — both parts are NUL-padded downloads — instead of silence.

### 9.2 `ab_encode.py`: `verify_audio` was far too weak to authorise deleting anything
- **Status**: 🛠️ **FIXED (2026-09-06)** — the one entry in this report with a live data-loss path.
- **File**: [`ab_encode.py:61-75`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L61-L75), `process_folder`
- **Error**: the gate on `--cleanup` was `float(ffprobe format=duration) > 0`. A truncated, half-empty or wrong-codec output reports a positive duration just as happily as a correct one. Nothing compared the output against its sources.
- **Impact**: reproduced end to end. `3 - The Big Switch (2011)` holds 26 MP3s, 4 of which are part-downloads (15.5 MB of NUL bytes then ~1.5 MB of real frames):
  ```
  sum of readable source durations : 25621 s
  ffmpeg exit code                 : 0
  verify_audio(output)             : True
  reported status                  : "✅ Success"
  ```
  With `--cleanup` all 26 originals would have been deleted, leaving a book whose four damaged chapters can no longer be re-derived from anything.
- **Fix applied**: `verify_output()` replaces it for every decision that matters, and fails closed. It requires the profile's expected codec, a duration matching the sum of the sources within `max(4s, min(60s, 0.5%))`, and — when deleting — a full end-to-end decode. `cleanup` now *implies* `deep_verify` and the two cannot be separated. `verify_audio` survives only as the shallow smoke test it always was.
- **Verification**: `test_a_damaged_source_is_refused_and_nothing_is_deleted`, `test_cleanup_cannot_be_combined_with_a_shallow_verify`, `test_verify_output_rejects_an_output_shorter_than_its_sources`.

### 9.3 `ab_encode.py`: ffmpeg's exit code is not a success signal, and its stderr was discarded
- **Status**: 🛠️ **FIXED (2026-09-06)**
- **File**: [`ab_encode.py:168-185`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L168-L185)
- **Error**: three compounding problems in one command.
  1. `-err_detect ignore_err -fflags +discardcorrupt` told ffmpeg to **silently drop** corrupt input rather than fail on it.
  2. `stderr=subprocess.DEVNULL` threw away the only place ffmpeg explains itself.
  3. Success was taken from `check=True`, but ffmpeg **returns 0 after dropping an undecodable packet**. Demonstrated directly:
     ```
     $ ffmpeg -v error -i "Ch 05.mp3" -f null -
     [mp3float] Header missing
     [aist#0:0/mp3] Error submitting packet to decoder: Invalid data found
     decode exit: 0
     ```
- **Fix applied**: both tolerance flags are gone from the default path; `stderr` is captured and its first line becomes the reported `detail`; and `decodes_cleanly()` judges a decode by **empty stderr at `-v error`**, with `-xerror` to stop at the first fault rather than grinding through a seven-hour file.
- **Verification**: `test_decodes_cleanly_reads_stderr_not_the_exit_code`.

### 9.4 `ab_encode.py`: a part-download that ffmpeg *can* partly read defeats every obvious check
- **Status**: 🛠️ **FIXED (2026-09-06)** — found while writing the test for 9.2, which initially failed for the wrong reason.
- **Error**: the assumption was that an undecodable file is caught by probing or by decoding. It is not, once the padding is small enough to fit inside ffprobe's default 5 MB `probesize`. ffprobe then skips the junk and reports a **completely plausible** stream — right codec, right sample rate, positive duration — and ffmpeg decodes the surviving tail **without a single error**:
  ```
  Probe(duration=0.39, codec='mp3', sample_rate=44100, channels=1)
  readable          : True
  decodes_cleanly   : (True, '')
  actual content    : 0.39 s of a 4 s file
  ```
  Duration checking cannot help either, because the *sources'* durations are what the output is measured against, and they are already wrong.
- **Fix applied**: two cheap pre-encode signals, neither of which depends on the decoder.
  - **Padding ratio** — file size over the size its own audio should occupy (`duration × bit_rate / 8`). Limit 3.0. Measured across all 353 MP3s in the real library: *every* healthy file scored exactly `1.000` (min 1.000, p50 1.000, max 1.000); the broken ones score 10 or more.
  - **Leading NUL run** — 64 KiB of zeros at the head of the file. One small read, no subprocess, and the only signal left when ffprobe cannot describe the file at all.
- **Verification**: `test_a_part_download_is_caught_by_padding_not_by_decoding`, `test_a_preallocated_file_is_caught_without_any_probe`, `test_a_healthy_file_is_never_called_damaged`.

### 9.5 `ab_encode.py`: stream-copy passthrough ignored mismatched stream parameters
- **Status**: 🛠️ **FIXED (2026-09-06)**
- **File**: [`ab_encode.py:150-166`](file:///home/citizenzero/Documents/Key/Abtools/ABtools/ab_encode.py#L150-L166)
- **Error**: `can_copy` required only that every source be an AAC file in an MP4-family container. The concat demuxer does **not** renegotiate stream parameters between files, so copying across a sample-rate or channel-count change yields output that plays at the wrong speed from the switch onwards — and at the right *duration*, so no length check would ever catch it.
- **Fix applied**: `_can_stream_copy()` requires one codec, one sample rate and one channel count across all sources, and returns the reason when it refuses.
- **Verification**: `test_stream_copy_is_refused_when_the_parameters_differ`, `test_the_copy_profile_refuses_mp3_sources_rather_than_garbling_them`.

### 9.6 `ab_encode.py`: one hard-coded output, and no chapter marks
- **Status**: 🛠️ **FIXED (2026-09-06)** — feature work rather than a defect, recorded here because it changed the same code path.
- **Error**: the encoder had a single hard-coded target (`aac`, `44100`, `.m4b`) with no way to ask for anything else, and never wrote chapter marks. An M4B without them is one unbroken seven-hour file: Apple Books and most Android players show no chapter list and resume badly.
- **Fix applied**: a `PROFILES` table read by both the CLI and the GUI, so they cannot drift into offering different encoders. Default `iphone` = AAC-LC `.m4b` with `-profile:a aac_low` and `+faststart` — the one combination that plays on iOS, Android, Audiobookshelf and CarPlay alike. Added `android-aac` (`.m4a`, for Android players that do not index `.m4b`), `android-opus` (about half the size, no Apple decoder), `mp3`, and `copy`. Chapters are derived from the source files' own durations and title tags, one per file.
- **Also**: neither the sample rate nor the channel count is forced any more. A profile's rate is a *fallback*, used only when the sources are mixed or non-standard; otherwise the source rate is kept, because resampling is never free in either direction. `--channels` defaults to `source` for the same reason: forcing mono on a book that is already an AAC `.m4b` re-encodes it and discards a channel, where leaving it alone joins the parts losslessly. Both were measured against two real libraries — sources run 12/22.05/24/32/44.1/48 kHz in a mix of mono and stereo, **283 of 345 files in one are 24 kHz**, and **930 of 1294 in the other are already `.m4b`** — so the previous fixed `44100` mono would have resampled and downmixed almost everything for nothing. Costs no compatibility: AAC-LC and MPEG audio define every rate in `STANDARD_SAMPLE_RATES` and all iOS/Android decoders accept them.
- **Chapter naming, measured on a second library** (`~/pi_share/audiobooks`, 1294 files): title tags are used only when *every* one is distinct, because a real two-part book carried the identical tag in both halves and would have produced a chapter list of two identical entries. Otherwise filenames, with the prefix every name in the folder repeats trimmed at a **word boundary** — the raw common prefix stops mid-token, so four files numbered 01-04 share the leading `0` and `01 - Opening Credits` became `1 - Opening Credits`. Trimming is abandoned when what survives is too short to read, which is what stops a two-part book becoming `1.2` and `2.2`.
- **Scale of 9.1, on that same library**: the old code queued **11 of 704** folders. 693 were invisible, 43 of them holding books split across several files that had never been joined. The encoder was doing nothing at all on 98% of that collection.
- **False-positive check on 9.4**: over a 200-file random sample, the padding ratio ran min 1.000, p50 1.014, max **1.049** against a limit of 3.0 — zero false positives — while still catching a `Track 1.m4b` with a 64 KiB NUL head, which only the head check could see because no bitrate was computable for the ratio.
- **Verification**: all four re-encoding profiles produce a correct file from the same sources; the `.m4b` output probes as `mp4a.40.2` (AAC-LC exactly), carries three chapters at the right boundaries, and still opens and tags cleanly in mutagen. End to end on real books: a 10.7-hour, 14-file MP3 book encoded and fully decoded in 3m31s with **0 s** duration drift and 14 chapters; the two-part 41-hour *Shadow Rising* stream-copied in **58.6 s** — 1178 MB in, 1175 MB out, duration exact, deep-verified — where the old code could not see the folder at all. `--list-profiles` marks anything this ffmpeg build cannot produce.

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

### Section 5 (P2), applied 2026-09-05

| Entry | Change | Verification |
|---|---|---|
| 5.1 | `child.text = str(value)` | `score=93` now writes `<score>93</score>` instead of raising |
| 5.2 | split on `\s+[-–—]\s+` only | `Jean-Paul Sartre - Nausea` → author kept whole (was `['Jean','Paul Sartre',…]`) |
| 5.3 | provider list walked in order, early return at ≥85 | instrumented: `goodreads, audible, openlib, gbooks` all queried |
| 5.4 | right-to-left `by`, two-word author required | 6/6 cases incl. `Stand by Me`, `Side by Side by Ann Brashares` |
| 5.5 | `params={...}` in both scrapers | manual `'+'` encoding gone from audible + goodreads |
| 5.6 | writes `series-part` for MP3 and MP4 | `TXXX:series-part` present alongside `TXXX:series` |
| 5.7 | title is always `parts[-1]` when 2+ segments | `…Series 3 Bonus - The Real Title` → `The Real Title` (was `Bonus`) |
| 5.8 | skip candidates lacking title/author | null-title providers return `None` instead of `AttributeError` |

**Consolidated regression suite — 10/10 passing** across 2.1, 3.1, 3.1b, 4.1, 4.2 and 4.4: dry-run byte-integrity, tag writing, `repair_m4b` temp output, multi-disc moves with nothing abandoned, distinct `Part N` books kept separate, prefix-marked books not merged, bare `Disc N` folding, root-as-book discovery in both entry points, and no spurious root leaf for libraries.

**Regression coverage added alongside the 4.1/4.4 fixes:** ordinary single-folder books are still discovered; an author folder containing several books is still not a leaf; `Tolkien/The Hobbit Part 1|2` stay separate books; dry-run on a multi-disc book leaves every byte untouched.

**Still open — recommended next:** [6.1](#61-find_duplicatespy---only-src-log-is-dead-code-in-cli) (`--only-src-log` parsed but never used; the GUI already wires the same machinery, so this is a few lines) and the section 7 edge cases. Of those, [7.4](#74-combobookpy-title-truncation-cuts-off--corrupts-year-suffix) is the only one that affects output in normal use — it drops the year from long destination folder names. [7.1](#71-repair_m4bpy-missing-iterable-import), [7.2](#72-catalogpy-calc_signature-crashes-on-none-or-decimal-duration) and [7.5](#75-ablibmetadatallmpy-token-budget-shrinks-on-length-retries) are refuted, unreachable or latent respectively.

**Files reviewed:** all 16 modules under `ablib/`, all 11 root-level scripts, and all 7 modules under `mcp_server/` (including `mcp_server/tools/`, which an earlier `-maxdepth 2` search had missed).
