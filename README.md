<!-- ABtools/README.md - v2.31 - 2025-11-01 -->

# Audiobook Organizer & Tagger



This repository contains small utilities for preparing audiobook folders for [Audiobookshelf](https://www.audiobookshelf.org/). The core logic is contained in the `ablib` package.





## Features



- Automatically tags `.mp3`, `.m4a`, and `.m4b` files with metadata

- Uses data from Audible, Goodreads, OpenLibrary, and Google Books

- Reorganizes folders into a clean structure using metadata from tags,

  `metadata.json` or `book.nfo`: `Author/Year - Title`

- Strips old or broken tags if needed

- Writes metadata to both `metadata.json` and `book.nfo` (for Kodi-style readers)

- Preview (omit `--commit`, or untick Commit in the GUI) runs the full pipeline — folder guess, provider lookups and scores, LLM/MCP refinement, validation — and prints exactly what it *would* write, without touching a single file or log

- Optionally prompts for confirmation or proceeds automatically

- Fetches metadata in parallel for faster tagging

- Ranks matches using both title and author similarity for better accuracy

- Local LM Studio fallback now runs a staged pipeline: provider scores ≥90 are accepted immediately, otherwise a "Metadata Refiner" call merges provider matches with MCP web searches (Audible, Open Library, Google Books, Goodreads, plus the generic `search`/`fetch_content` helpers); stubborn cases escalate to a SequentialThinking reasoning pass before a final "Tag Evaluator" assigns a confidence score.

- Optional DuckDuckGo Search integration (no key required) feeds fresh web snippets to the LLM when initial metadata replies are incomplete, improving author/year/series recovery. Tavily support was removed: it needed a paid key that most installs lacked, so it only ever added a failed request before the DuckDuckGo fallback ran.

- LLM replies are retried with stronger prompts when fields stay blank, and any residual gaps (author/year/series/etc.) are resolved inside the staged pipeline before the verifier scores the final JSON.

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

- GUI wraps each configuration cluster in titled `ttk.LabelFrame` sections (File Paths, Operation Settings, Model Configuration, Actions, Log) with consistent padding and responsive `grid()` weights so inputs stretch cleanly.

- GUI groups operation settings, introduces drop-down selectors for CLI arguments, styles primary actions (Move and Tag) for prominence, and keeps the LLM fallback toggle inside the model configuration panel.

- GUI adds a dedicated Plan JSON picker alongside Source and Destination paths, swaps threshold and timeout entries for numeric `ttk.Spinbox` widgets, and keeps the LLM model selector as a combobox for clearer selection.

- GUI exposes LM Studio fallback controls (endpoint, model, threshold) so the "Move and Tag" and "Tag Only" flows match the CLI

- Whisper transcription settings have been retired from the GUI and CLI; tagging now relies solely on metadata lookups and LM Studio research.

- GUI ships eight polished themes (Neutral Slate, Tokyo Night, Catppuccin Mocha, Nord, Gruvbox Dark, Bchips Violet, Dracula, and GitHub Light), switchable live from the Theme dropdown and remembered between launches in `~/.abtools_gui.json`. Every theme is contrast-checked to WCAG AA for UI text.

- GUI shows hover help on every button, field and checkbox, explaining what each option actually does - including the non-obvious ones (Timeout only applies with Network Mode on; Destination is optional for Find Duplicates; Find Duplicates never deletes anything).

- Multi-disc books (`Book/Disc 1`, `Book/Disc 2`) are treated as one book and merged on move, rather than each disc being moved separately

- Pointing any tool directly at a single book folder works, not just at a library root

- Duplicate catalog prevents importing the same book twice



## Requirements



- Python 3.11 or newer (tested on the Windows Store 3.11 build and on Linux with 3.14; create the dedicated virtual environment below)

- Dependencies (installed via `pip install -r requirements.txt`):

  - `mutagen`

  - `requests`

  - `beautifulsoup4`

  - `rapidfuzz`

  - `rich` (optional, for prettier output)

  - `tqdm` (optional, for progress display in `find_duplicates.py`)

  - `duckduckgo-search` (optional web snippets for the LLM fallback)

  - `mcp<2` (only needed to run `mcp_server/`; pinned because mcp 2.x renamed `FastMCP` to `MCPServer`)

  - `tkinter` (ships with Python on Windows/macOS; on Linux install your distro's `python-tk` / `python3-tk` package for `AbtoolsGui.py`)

  - An OpenAI-compatible endpoint (LM Studio 0.2+ exposes one locally; point ABtools at it with --llm-endpoint; the default is port 8888)



Install all dependencies inside the dedicated environment:



```powershell

py -3.11 -m venv abtools_env

abtools_env\Scripts\activate

python -m pip install --upgrade pip

pip install -r requirements.txt

```



(On macOS/Linux: `python3.11 -m venv abtools_env && source abtools_env/bin/activate`.)



## Local LLM setup (LM Studio)



1. Download and install [LM Studio](https://lmstudio.ai/). Open the **Llama 3.2 8B Instruct** model (or your preferred chat model) and start the local server on port `8888` so it exposes an OpenAI-compatible `/v1/chat/completions` endpoint.

2. Enable LM Studio's MCP server (Tools -> MCP) and enable the provider tools (`search_audible_tool`, `search_openlibrary_tool`, `search_google_books_tool`, `search_goodreads_tool`) plus the generic `search` and `fetch_content` helpers. The CLI targets `http://127.0.0.1:8888/v1/chat/completions` by default.

3. Run `search_and_tag.py` or `combobook.py` with the defaults or override them explicitly:

   ```bash

   python search_and_tag.py "E:/Audio Books" --commit --llm-endpoint http://127.0.0.1:8888/v1/chat/completions --llm-model llama-3.2-8b-instruct

   ```

   Use `--llm-endpoint none` to disable the fallback entirely. Provide a DuckDuckGo Search key via `(no key required)` (or the `DUCKDUCKGO_MCP` env var) if you want second-pass LLM retries to include live web snippets.

4. Whenever provider scores sink below 90 or no catalog match exists, the script runs the staged LM Studio pipeline (Metadata Refiner -> SequentialThinking -> Tag Evaluator) before writing tags so each AI-assisted run yields logged confidence scores.



## Scripts



| Script | Version | Path |

|-------|---------|------|



| `combobook.py` | v1.18 | `combobook.py` |
| `AbtoolsGui.py` | v0.17 | `AbtoolsGui.py` |
| `flatten_discs.py` | v1.5 | `flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v5.4 | `restructure_for_audiobookshelf.py` |
| `repair_m4b.py` | v1.1 | `repair_m4b.py` |
| `search_and_tag.py` | v2.30 | `search_and_tag.py` |
| `ab_encode.py` | v1.3 | `ab_encode.py` |
| `find_duplicates.py` | v0.5 | `find_duplicates.py` |
| `abclient.py` | v0.2 | `abclient.py` |
| `catalog.py` | v0.1 | `catalog.py` |
| `mcp_server/server.py` | v1.1.0 | `mcp_server/server.py` |



Run any script with `--version` to print its version and file location.



## `combobook.py`

`combobook.py` tags, flattens and moves audiobook folders in a single pass. It searches Open Library, Google Books and Audible, ranks potential matches using fuzzy similarity and asks you to confirm before tagging and moving files. When provider lookups and prompts fail, the script now consults the shared LM Studio fallback to propose metadata, tags every track automatically, and logs which folders used the AI assist. Only when both paths fail does it fall back to moving the folder into an `_unmatched` directory inside your library for manual review.



The CLI exposes --llm-endpoint, --llm-model, and `--llm-threshold` (legacy compatibility) so you can steer the same LM Studio settings used by search_and_tag.py without touching its code.



It now also collapses folders named like `Book Title (1 of 5)` into a single directory and names each file `Part 01`, `Part 02`, etc.



The source path is now passed explicitly, avoiding `NameError: SRC is not defined` when the script is imported by other modules or run via the GUI.



For a simple graphical front-end, use `AbtoolsGui.py`, which provides text fields for source and destination folders, checkboxes for `--commit`, `--copy` and `--yes` options, a live output pane, and a progress bar with estimated time. It includes a "Restructure" button for reorganizing folders, a "Tag Only" button that runs `search_and_tag.py` without moving files, and a "Find Duplicates" button.



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



Folders are moved to `<library>/Author/Series?/Title (Year)/`.



Both `combobook.py` and `restructure_for_audiobookshelf.py` can copy books when run with `--copy` alongside `--commit`.



## `AbtoolsGui.py`

`AbtoolsGui.py` offers a Tkinter interface for `combobook.py` and related workflows. The layout now uses titled `ttk.LabelFrame` sections that stack vertically: File Paths (source, destination, Plan JSON pickers), Operation Settings (commit/copy/yes toggles, timeout, threads, compare-by, recurse, network and "only src log" switches), Model Configuration (LLM controls with an enable toggle), Actions, and a Log panel with a `tk.Text` widget + scrollbar. Inputs expand with `grid()` weights, and padding is consistent across sections. Numeric inputs use `ttk.Spinbox`, model selectors are `ttk.Combobox`, and the primary "Move and Tag" action uses a bold ttk style for emphasis. The log pane shares space with the progress bar, and the ETA label sits at the bottom-right.

The action row is Tag / Move / Restructure / Find Duplicates / Stop, all one height, with the primary and destructive actions distinguished by colour rather than size.

**Theming.** A Theme dropdown in the bottom status row switches between eight curated dark and light palettes live, without restarting; the choice is saved to `~/.abtools_gui.json`. Palettes are plain data in the `THEMES` dict at the top of `AbtoolsGui.py`, so adding one is a single entry - `apply_theme()` restyles every widget, including already-printed log output. Fonts are resolved against the families actually installed rather than hardcoded, so the UI does not fall back to something arbitrary on Linux or macOS.

**Hover help.** Every button, entry, spinbox, combobox and checkbox carries a tooltip describing what it actually does. Tooltips are clamped to the screen so the bottom-row buttons do not push them off the edge.

**Providers.** A Provider dropdown covers LM Studio, Ollama, vLLM and **OpenRouter**, filling in the endpoint and checking it. The local runners need no credentials; OpenRouter needs an API key, supplied either in the API key field or — preferably — via the `ABTOOLS_LLM_API_KEY` or `OPENROUTER_API_KEY` environment variable. By default the key is held in memory only. Ticking **Remember key** stores it in `~/.abtools_gui.json` so it survives a restart — in **plain text**, though the file is written owner-only (`0600`). Unticking erases the stored key rather than merely stopping future writes. An environment variable is safer and always takes precedence over a stored key. The CLI takes the same value via `--llm-api-key`.

**Model discovery.** The Model dropdown is filled from the server itself: the GUI queries the endpoint's `/v1/models` shortly after launch, whenever you finish editing the Endpoint field, and on demand via the `↻` button. A status line reports how many models the server has loaded, warns when the selected model is not among them, and says so plainly when the endpoint cannot be reached — in which case the list falls back to models you have used before. Endpoint, model and the recent-model list persist in `~/.abtools_gui.json`. You can still type any model name.

Debug output is written to `AudioBooks_tools/AbtoolsGui.debug.log` so you can inspect the underlying CLI runs when troubleshooting.



## `search_and_tag.py`

`search_and_tag.py` tags or strips audiobook files. It now routes Audible,

Goodreads (optional), Open Library, and Google Books lookups through LM Studio's

MCP web-search tools so each provider is queried via `full_web_search` with a

targeted `site:` filter. Results are ranked using both title and author similarity,

and the score from each provider is printed so you can see which source matched

best. Audible is queried first when enabled via `abclient.json`. Matches with a

low score will ask for confirmation unless you pass `--yes`. Use `--no` to

decline automatically. The prompt defaults to `no` so low-confidence matches

aren't accepted accidentally. Use `--debug` to print full tracebacks on unexpected

errors.



When a book has no match or you decline the suggested metadata, the

folder path is written to `review_log.txt` in the chosen root folder for

later inspection. All actions are logged to `tag_log.txt` beside it. On

successful tagging, the metadata is exported to `metadata.json` and

`book.nfo` so other players (including Audiobookshelf) can read the

details.



For stubborn matches, keep the default --llm-endpoint http://127.0.0.1:8888/v1/chat/completions or set it explicitly alongside --llm-model llama-3.2-8b-instruct to consult LM Studio. The fallback now runs a four-stage pipeline:



1. **Provider Merge (score >=90)** - Audible/Open Library/Google Books/Goodreads hits at or above 90 are accepted without further LLM work.

2. **Metadata Refiner** - Scores below 90 trigger the MCP-backed `search_audible_tool`, `search_openlibrary_tool`, `search_google_books_tool`, `search_goodreads_tool`, plus the generic `search` and `fetch_content` helpers to merge fuzzy matches into structured JSON.

3. **SequentialThinking Reasoning** - If the refined answer is still weak or no provider matched, the SequentialThinking tool guides a step-by-step synthesis to reach a 99-100 confidence proposal.

4. **Tag Evaluator** - Every final result is sent to a verifier pass that checks the JSON and assigns a confidence score, which is logged alongside the tagged files.



Supplying a DuckDuckGo key ((no key required) or DUCKDUCKGO_MCP) lets the Metadata Refiner and SequentialThinking stages pull live web snippets before resolving missing fields.

Successful LLM suggestions still skip the review log and are written to tags, metadata.json, and book.nfo like any other metadata.

`--llm-threshold` is live, not legacy: a provider match scoring below it triggers the LLM fallback (default 85, clamped to 80-100). The separate 90-point trigger above governs only whether the MCP refinement stage is attempted. Note that the confirmation prompt for a low-confidence match is currently hardcoded to fire below 70 rather than below `--llm-threshold` - see [`bug.md`](./bug.md) 2.4.





## `flatten_discs.py`

`flatten_discs.py` merges disc-numbered rips into one folder with sequential track names. Preview changes by default; use `--commit` to apply them and `--yes` to auto-confirm.



## `restructure_for_audiobookshelf.py`

`restructure_for_audiobookshelf.py` reorganizes a source collection into Audiobookshelf layout. It reads tags from the audio files first, then `metadata.json` or `book.nfo`, and finally falls back to folder names. Disc folders are flattened and books are moved or copied to `<library>/Author/Series?/Title (Year)/`. Series names and volume numbers are detected with fuzzy matching (e.g. `Book 3`, `#3`, `Volume III`). When run with `--interactive`, the script prompts for missing series info. Metadata matching is handled by `search_and_tag.py`. Track renaming now avoids collisions by staging files with temporary names first.



Examples:



```bash

# preview

python restructure_for_audiobookshelf.py "Downloads" "Audiobooks"



# move folders

python restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --commit



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





## `abclient.py`

`abclient.py` provides simple A/B switch management. Switch states are loaded from the JSON file `~/.abclient.json`. For example:



```json

{

  "use_goodreads": true,

  "audible_first": false

}

```



Edit this file to enable or disable experimental features.



## Known Issues & Bug Tracker

A comprehensive codebase audit report documenting all known logic errors, fatal startup bugs, dry-run caveats, and provider issues is available in [`bug.md`](./bug.md). Every entry carries a status marker, and three claims from an earlier audit pass are marked **REFUTED** with evidence - read those before "fixing" them, because the current code is correct.

All P0 and P1 entries are fixed. The remaining open items are the P2 metadata-correctness group in section 5, of which 5.2 (a regex that silently corrupts author/title for hyphenated names) is the highest impact.

## Configuration

Settings resolve in this order, highest first: an explicit CLI flag or GUI selection, then the saved GUI settings, then the environment, then the defaults in `ablib/core/constants.py`.

| Variable | Sets |
|---|---|
| `ABTOOLS_LLM_ENDPOINT` | OpenAI-compatible chat-completions URL |
| `ABTOOLS_LLM_MODEL` | Model name to request |
| `ABTOOLS_LLM_API_KEY` | Bearer token for a hosted provider (`OPENROUTER_API_KEY` also accepted) |
| `ABTOOLS_LLM_TIMEOUT` | Request timeout, seconds |
| `ABTOOLS_LLM_MAX_TOKENS` | Response token budget |
| `ABTOOLS_DEBUG` | Verbose diagnostics |

Run `python search_and_tag.py --show-config` to see each effective value and where it came from. The API key is reported as set/unset, never printed.

`OPENAI_BASE_URL` and `OPENAI_MODEL_NAME` are deliberately **not** honoured — silently inheriting a variable set for another tool could point tagging at a paid hosted API without you realising.

This is also the only way to configure `mcp_server/`, which has no command-line flags of its own.

## Design Proposals

[`proposal.md`](./proposal.md) covers making the LLM model configuration dynamic - discovering models from the server's `/v1/models` endpoint instead of the hardcoded list, persisting recently used models, and a configuration cascade for the CLI, GUI and MCP server.

