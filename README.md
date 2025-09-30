<!-- ABtools/README.md · v2.11 · 2025-09-09 -->
# Audiobook Organizer & Tagger

This repository contains small utilities for preparing audiobook folders for [Audiobookshelf](https://www.audiobookshelf.org/).


## Features

- Automatically tags `.mp3`, `.m4a`, and `.m4b` files with metadata
- Uses data from Audible, Goodreads, OpenLibrary, and Google Books
- Reorganizes folders into a clean structure using metadata from tags,
  `metadata.json` or `book.nfo`: `Author/Year - Title`
- Strips old or broken tags if needed
- Writes metadata to both `metadata.json` and `book.nfo` (for Kodi-style readers)
- Provides preview and logging
- Optionally prompts for confirmation or proceeds automatically
- Fetches metadata in parallel for faster tagging
- Ranks matches using both title and author similarity for better accuracy
- Local LM Studio fallback can propose metadata when online lookups fail or are low-confidence. It streams folder context and a Faster-Whisper transcript of the first minute (GPU-tunable via `--whisper-device`/`--whisper-compute-type`) to the OpenAI-compatible API that LM Studio exposes on port 1234 and parses the JSON reply.
- `combobook.py` reuses the shared LM Studio fallback to supply metadata when provider searches fail, tags the files automatically, and logs AI-assisted folders for later review
- Preserves part numbers like `(1 of 6)` when reorganizing files
- Adds track numbers so multi-part books play in order
- Detects series and volume numbers with fuzzy matching
  and prompts for confirmation when run with `--interactive`
- Each script reports its version and location with `--version`
- `combobook.py` and `restructure_for_audiobookshelf.py` accept paths with spaces without quoting
- Experimental features are toggled via `~/.abclient.json` using `AbClient`
- Prints the score from each metadata provider during tagging
- `find_duplicates.py` shows progress while scanning and can compare
  files by SHA1 hash or by name, and can cross-compare a source and
  destination folder to report duplicates present in both
- GUI front-end shows live output in a scrollable pane with a progress bar and estimated time
- GUI front-end can run `find_duplicates.py` to scan source and destination for duplicate audio files
- GUI duplicate finder adds: cross-compare Source <-> Destination, Compare-by selector (hash/name), Network Mode with timeout to avoid NAS stalls, adjustable hashing Threads, live "Checking:" current-file output, and output grouped by folder (matches CLI). Window is resizable and progress is smooth.
- GUI front-end processes output in batches so the window stays responsive during large scans
- GUI exposes LM Studio fallback controls (endpoint, model, threshold, and Faster-Whisper device/compute settings) so the "Move and Tag" and "Tag Only" flows match the CLI
- Planning mode writes a JSON plan that can be reviewed before execution
- GUI front-end checks that a plan file path is selected before generating or applying a plan
- Plan files are read and written using UTF-8 encoding for cross-platform compatibility
- Transactions are logged and can be rolled back with `--undo-last`
- Duplicate catalog prevents importing the same book twice

## Requirements

- Python 3.8+
- Dependencies:
  - `mutagen`
  - `requests`
  - `beautifulsoup4`
  - `rapidfuzz`
  - `rich` (optional, for prettier output)
  - `faster-whisper` (optional, provides 1-minute transcripts for the LM Studio fallback in `search_and_tag.py`; supports GPU via `--whisper-device`/`--whisper-compute-type`)
  - An OpenAI-compatible endpoint (LM Studio 0.2+ exposes one locally; start Mistral-7B Q4 on port 1234 for best results)
- `tqdm` (optional, for progress display in `find_duplicates.py`)

Install all dependencies with:

```bash
pip install -r requirements.txt
```

## Local LLM setup (LM Studio)

1. Install the transcription dependency:
   ```bash
   pip install faster-whisper
   ```
   GPU acceleration is available when you pass `--whisper-device cuda` (or `rocm`).
2. Download [LM Studio](https://lmstudio.ai/), open the **Mistral-7B Instruct Q4** model, and start a local server on port `1234` (the UI exposes a "Start Server" button that launches an OpenAI-compatible API).
3. Run `search_and_tag.py` or `combobook.py` with the defaults or override them explicitly:
   ```bash
   python search_and_tag.py "E:/Audio Books" --commit --llm-endpoint http://127.0.0.1:1234/v1/chat/completions --llm-model mistral-7b-instruct-q4
   ```
   Use `--llm-endpoint none` to disable the fallback entirely.
4. The fallback triggers automatically whenever every provider lookup returns no results or the best score falls below `--llm-threshold` (default 75). The script transcribes roughly the first minute of audio using Faster-Whisper (default model `medium.en`) and sends folder context plus the transcript to LM Studio, expecting a single JSON object in return.

## Scripts

| Script | Version | Path |
|-------|---------|------|

| `combobook.py` | v1.17 | `ABtools/combobook.py` |
| `AbtoolsGui.py` | v0.12 | `ABtools/AbtoolsGui.py` |
| `flatten_discs.py` | v1.4 | `ABtools/flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v5.3 | `ABtools/restructure_for_audiobookshelf.py` |
| `search_and_tag.py` | v2.21 | `ABtools/search_and_tag.py` |
| `find_duplicates.py` | v0.5 | `ABtools/find_duplicates.py` |
| `abclient.py` | v0.2 | `ABtools/abclient.py` |
| `planning.py` | v0.2 | `ABtools/planning.py` |
| `transaction.py` | v0.2 | `ABtools/transaction.py` |
| `catalog.py` | v0.1 | `ABtools/catalog.py` |

Run any script with `--version` to print its version and file location.

## `combobook.py`
`combobook.py` tags, flattens and moves audiobook folders in a single pass. It searches Open Library, Google Books and Audible, ranks potential matches using fuzzy similarity and asks you to confirm before tagging and moving files. When provider lookups and prompts fail, the script now consults the shared LM Studio fallback to propose metadata, tags every track automatically, and logs which folders used the AI assist. Only when both paths fail does it fall back to moving the folder into an `_unmatched` directory inside your library for manual review.

The CLI exposes `--llm-endpoint`, `--llm-model`, `--whisper-model`, `--whisper-device`, and `--whisper-compute-type` so you can steer the same LM Studio and Faster-Whisper settings used by `search_and_tag.py` without touching its code.

It now also collapses folders named like `Book Title (1 of 5)` into a single directory and names each file `Part 01`, `Part 02`, etc.

The source path is now passed explicitly, avoiding `NameError: SRC is not defined` when the script is imported by other modules or run via the GUI.

For a simple graphical front-end, use `AbtoolsGui.py`, which provides text fields for source and destination folders, checkboxes for `--commit`, `--copy` and `--yes` options, a live output pane, and a progress bar with estimated time. It includes a "Restructure" button for reorganizing folders, a "Tag Only" button that runs `search_and_tag.py` without moving files, a "Find Duplicates" button, and new controls to generate plans, apply them transactionally, or undo the last run.

FFmpeg tag writing previously failed silently; the script now specifies the output file so tags are embedded correctly.

"""

  Tag (or strip) audiobook files using multiple metadata providers.

  The script queries Audible, Open Library and Google Books, ranks the
  results using fuzzy title and author matching and automatically tags
  files with the best match. Low scoring hits will prompt for confirmation
  unless you run with ``--yes``. When prompted, the default answer is "No" so low
  confidence matches won't be accepted accidentally. Log files are written
  next to the chosen root as ``tag_log.txt`` and ``review_log.txt``.


examples
--------
# preview everything
python search_and_tag.py "E:\\Audio Books" --recurse

# tag automatically
python search_and_tag.py "E:\\Audio Books" --recurse --commit --yes

# strip all tags
python search_and_tag.py "E:\\Audio Books" --recurse --striptags --commit
"""
```
# Preview only (no changes made)
python combobook.py "source_folder" "library_folder"

# Tag + move with manual confirmation
python combobook.py "source_folder" "library_folder" --commit

# Tag + move and auto-confirm all matches
python combobook.py "source_folder" "library_folder" --commit --yes

# Tag + copy instead of move
python combobook.py "source_folder" "library_folder" --commit --copy
```

Folders are moved to `<library>/Author/Series?/Vol # - YYYY - Title {Narrator}/`.

Both `combobook.py` and `restructure_for_audiobookshelf.py` can copy books when run with `--copy` alongside `--commit`.

## `AbtoolsGui.py`
`AbtoolsGui.py` offers a basic Tkinter interface for `combobook.py`. It provides text fields for selecting the source and library folders, checkboxes matching the `--commit`, `--copy` and `--yes` command-line options, and shows live `combobook` output in a scrolling pane. Progress messages that rely on carriage returns are normalized so each update appears on its own line. A progress bar displays overall progress with an estimated time remaining. Alongside buttons for "Restructure", "Tag Only" and "Find Duplicates", the GUI exposes controls to generate restructure plans, apply them atomically, and undo the most recent transaction. The GUI also includes a "Network Mode" toggle with a timeout field used by the duplicate finder to prevent stalls on slow or flaky network shares, and a "Compare by" selector (hash/name). When both Source and Destination are set, "Find Duplicates" compares them against each other; otherwise it scans the single folder.

A dedicated **LLM fallback** panel mirrors the CLI flags: set the LM Studio endpoint, model name, low-score threshold, and Faster-Whisper device/compute choices used to generate transcripts. Enter `none` to disable the endpoint or whisper model entirely. These settings are applied to both the "Move and Tag" workflow (which calls `combobook.py`) and the "Tag Only" flow (which calls `search_and_tag.py`) so GUI runs match the CLI. The GUI validates that a plan file path is chosen before generating or applying a plan to avoid permission errors, and processes queued output in small batches so the window stays responsive during long runs.

## `search_and_tag.py`
`search_and_tag.py` tags or strips audiobook files. It queries Audible,
Goodreads (optional), Open Library and Google Books. Results are ranked
using both title and author similarity, and the score from each
provider is printed so you can see which source matched best. Audible is
queried first when enabled via `abclient.json`. Matches with a low score
will ask for confirmation unless you pass `--yes`. Use `--no` to
decline automatically. The prompt defaults to `no` so low-confidence
matches aren't accepted accidentally. Use `--debug` to print full
tracebacks on unexpected errors.

When a book has no match or you decline the suggested metadata, the
folder path is written to `review_log.txt` in the chosen root folder for
later inspection. All actions are logged to `tag_log.txt` beside it. On
successful tagging, the metadata is exported to `metadata.json` and
`book.nfo` so other players (including Audiobookshelf) can read the
details.

For stubborn matches, keep the default `--llm-endpoint http://127.0.0.1:1234/v1/chat/completions` or set it explicitly alongside `--llm-model mistral-7b-instruct-q4` to consult LM Studio. When online providers score below `--llm-threshold` (default 75) or return nothing, the script takes roughly a 1-minute sample from the first audio file, transcribes it locally with Faster-Whisper (configurable via `--whisper-model`, `--whisper-device`, and `--whisper-compute-type`), and feeds the transcript plus folder context to LM Studio. Successful LLM suggestions skip the review log but are written to tags, `metadata.json`, and `book.nfo` like any other metadata.


## `flatten_discs.py`
`flatten_discs.py` merges disc-numbered rips into one folder with sequential track names. Preview changes by default; use `--commit` to apply them and `--yes` to auto-confirm.

## `restructure_for_audiobookshelf.py`
`restructure_for_audiobookshelf.py` reorganizes a source collection into Audiobookshelf layout. It reads tags from the audio files first, then `metadata.json` or `book.nfo`, and finally falls back to folder names. Disc folders are flattened and books are moved or copied to `<library>/Author/Series?/Vol # - YYYY - Title {Narrator}/`. Series names and volume numbers are detected with fuzzy matching (e.g. `Book 3`, `#3`, `Volume III`). When run with `--interactive`, the script prompts for missing series info. Metadata matching is handled by `search_and_tag.py`. Track renaming now avoids collisions by staging files with temporary names first.

Examples:

```bash
# preview
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks"

# move folders
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --commit

# plan then apply
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --plan-json plan.json
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --apply-plan plan.json
```

## `find_duplicates.py`
`find_duplicates.py` scans recursively and can find duplicates either by computing SHA1 hashes or by matching file names. You can scan a single folder for within-folder duplicates, or pass two folders to report duplicates that exist in both. Progress is shown (uses `tqdm` when installed; otherwise inline counters). Results are written to `duplicate_log.txt` inside the scanned folder (or the source folder when comparing two roots). Use `--version` to show the script version and path. Hash matching skips hashing files with unique sizes for faster scans. To avoid stalls on flaky network shares, per-file hashing supports a timeout via `--hash-timeout SECONDS` (auto-applies 30s on UNC paths; use `0` to disable). Hashing runs in parallel threads for speed and prints the current file being checked.

CLI options of interest:
- `--by {hash,name}`: comparison mode
- `--hash-timeout SECONDS`: per-file read timeout (0 disables; default auto)
- `--threads N`: hashing threads (default 4)

Examples:

```bash
# Within a single folder (4 threads)
python find_duplicates.py "E:\\Audio" --by hash --threads 4
python find_duplicates.py "E:\\Audio" --by name --threads 4

# Cross-compare two folders with timeout for network shares
python find_duplicates.py "E:\\Downloads" "E:\\Audiobooks" --by hash --threads 4
python find_duplicates.py "E:\\Downloads" "E:\\Audiobooks" --by name --hash-timeout 60 --threads 4
```

## Planning & Transactions

Build a safe, reviewable plan for restructuring your library, then apply it atomically with undo support.

- GUI usage:
  - Plan: set Source and Destination, click "Plan" to generate a JSON plan using `planning.plan_library(...)`.
  - Apply: click "Apply Plan" to execute the plan via `transaction.execute(plan.json)`.
  - Undo: click "Undo Last" to roll back the most recent applied plan.

- CLI usage:
  - Build plan JSON:
    - `python planning.py "Downloads" "Audiobooks" --plan-json plan.json`  (add `--copy` to propose copies instead of moves)
  - Apply plan (module call):
    - `python -c "import pathlib; from transaction import execute; execute(pathlib.Path('plan.json'))"`
  - Undo last transaction:
    - `python -c "from transaction import undo_last; undo_last()"`

Notes
- Plans contain a list of actions (move/copy/skip/quarantine) with resolved source/destination paths.
- A SQLite catalog at `<dest>/.abtools_catalog.db` prevents re-importing duplicates across runs.
- Books with disc/track gaps are quarantined to `<dest>/_quarantine/...` for manual review.



## `abclient.py`
`abclient.py` provides simple A/B switch management. Switch states are loaded from the JSON file `~/.abclient.json`. For example:

```json
{
  "use_goodreads": true,
  "audible_first": false
}
```

Edit this file to enable or disable experimental features.
# Generate and apply plans (alternative CLI)
python planning.py "source" "library" --plan-json plan.json
python -c "import pathlib; from transaction import execute; execute(pathlib.Path('plan.json'))"
python -c "from transaction import undo_last; undo_last()"
