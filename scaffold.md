<!-- ABtools/scaffold.md · v2.3 · 2025-09-08 -->
# Audiobook Tagging & Organization – Scaffold

## Project Structure

```
Audiobooks/
│
├── search_and_tag.py       # Tags files using metadata providers
├── flatten_discs.py        # Merges "Disc" folders into one
├── combobook.py            # Combines tagging and restructuring
├── AbtoolsGui.py           # Tkinter GUI with live output, planning controls and duplicate finder
├── restructure_for_audiobookshelf.py  # Reorganizes folders into Audiobookshelf layout
├── find_duplicates.py      # Reports duplicate audio files
├── planning.py             # Build restructure plans with scoring
├── transaction.py          # Execute plans atomically with rollback
├── catalog.py              # SQLite catalog for duplicate detection
├── metadata.json           # Optional: sample metadata format
├── requirements.txt        # Pip requirements
├── README.md
└── SCAFFOLD.md
```

## Scripts Overview


### `search_and_tag.py`

- Tags audio files using best match from:
  - Audible
  - Goodreads
  - OpenLibrary
  - Google Books
- Writes:
  - ID3 or MP4 tags
  - `metadata.json`
  - `book.nfo`
  - `--debug` prints tracebacks on errors
  - `--no` auto-declines metadata suggestions
  - fetches metadata in parallel for faster processing
  - ranks matches using title and author similarity
  - `--version` prints the script version and file path
  - Experimental switches stored in `~/.abclient.json` (used by `AbClient`)
  - Prints scores from all metadata providers
  - Optional LM Studio fallback via `--llm-endpoint` / `--llm-model` / `--llm-threshold` supplies metadata when lookups fail, feeding an LM Studio server (default `http://127.0.0.1:1234/v1/chat/completions`) a Faster-Whisper transcript from the first minute of audio (configurable with `--whisper-model`, `--whisper-device`, and `--whisper-compute-type`)

### `flatten_discs.py`

- Flattens multi-disc folders (e.g., `Disc 01`, `CD1`)
- Renames all tracks sequentially
- Merges into a single clean folder

### `combobook.py`

- Combines the functionality of both scripts:
    - Detects audio files
    - Tags them using `search_and_tag.py` logic
    - Calls the shared LM Studio fallback when provider lookups fail, tagging tracks automatically and logging AI-assisted folders
    - Creates cleaned-up `Author/Year - Title` folder
    - Moves and renames content
    - Only moves folders into `_unmatched` when both provider searches and the LM Studio fallback fail
    - Embeds tags with FFmpeg; fixed missing output file to ensure tags are written
    - Accepts source paths with spaces without needing quotes
    - Passes the source path explicitly to avoid `NameError: SRC is not defined` when imported elsewhere

### `AbtoolsGui.py`

- Simple Tkinter GUI front-end for `combobook.py`
- Text fields for source and library folders
- Checkboxes for `--commit`, `--copy` and `--yes`
- Scrollable output pane and progress bar with estimated time
- "Tag Only" button that runs `search_and_tag.py` without moving files
- "Find Duplicates" button; when both Source and Destination are set it cross-compares them using `find_duplicates.py`, otherwise it scans the single folder
- "Compare by" selector (hash/name) for duplicate scans
- "Threads" control to adjust hashing concurrency
- Output grouped by folder (matches CLI grouped logs)
- "Restructure" button that reorganizes folders via `restructure_for_audiobookshelf.py`
- "Network Mode" toggle with a timeout field to prevent stalls when reading from network shares during duplicate scans
- Buttons to generate restructure plans, apply them atomically and undo the last run
- Processes output queue in small batches so the window remains responsive during large scans
- Saves plan files with UTF-8 encoding for cross-platform compatibility

### `restructure_for_audiobookshelf.py`

- Reorganizes existing folders into Audiobookshelf layout using metadata from
  tags, `metadata.json` or `book.nfo`
- Keeps numeric part suffixes like `(1 of 6)` or `Part 1` when moving files
- Writes `track` or `trkn` tags so players keep the right order
- Renames tracks safely to avoid name collisions
- Detects fuzzy series numbering ("Book 2", "#2", "Volume II")
- `--interactive` prompts for series info when unclear
- Handles source folders with spaces without quoting

Examples:

```bash
# preview
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks"

# commit changes
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --commit

# create and apply plan
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --plan-json plan.json
python restructure_for_audiobookshelf.py "Downloads" "Audiobooks" --apply-plan plan.json
```

### `find_duplicates.py`

- Scans recursively for audio files
- Compares files by SHA1 hash or by name
- Cross-compares two folders to report duplicates present in both
- Skips hashing files with unique sizes for faster scans
- Prints groups of duplicate files
- Writes results to `duplicate_log.txt` (in the scanned folder, or the source when comparing two roots)
- Shows scanning progress and prints the current file being checked
- `--version` shows the script version and path
- Shows progress while hashing when `tqdm` is installed
- Parallel hashing with configurable threads via `--threads` (default: 4)
- Per-file read timeouts via `--hash-timeout` (auto 30s on UNC paths)

## Regex Patterns Used

- `^(\d{4})\s*[-_]\s*`: extracts leading year
- `\(Disc \d+\)`, `CD\d+`, etc.: disc recognition
- Removes `{size}`, `bitrate`, timestamps like `12.56.09`

## Metadata JSON Format

```json
{
  "title": "Book Title",
  "author": "Author Name",
  "year": "2005",
  "series": "Optional Series Title",
  "source": "audible | openlib | gbooks"
}
```

## Script Versions

| Script | Version | Path |
|-------|---------|------|
| `combobook.py` | v1.17 | `ABtools/combobook.py` |
| `AbtoolsGui.py` | v0.11 | `ABtools/AbtoolsGui.py` |
| `flatten_discs.py` | v1.4 | `ABtools/flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v5.3 | `ABtools/restructure_for_audiobookshelf.py` |
| `search_and_tag.py` | v2.21 | `ABtools/search_and_tag.py` |
| `find_duplicates.py` | v0.5 | `ABtools/find_duplicates.py` |
| `abclient.py` | v0.2 | `ABtools/abclient.py` |
| `planning.py` | v0.2 | `ABtools/planning.py` |
| `transaction.py` | v0.2 | `ABtools/transaction.py` |
| `catalog.py` | v0.1 | `ABtools/catalog.py` |

