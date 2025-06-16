# Audiobook Tagging & Organization – Scaffold

## Project Structure

```
Audiobooks/
│
├── search_and_tag.py       # Tags files using metadata providers
├── flatten_discs.py        # Merges "Disc" folders into one
├── combobook.py            # Combines tagging and restructuring
├── restructure_for_audiobookshelf.py  # Reorganizes folders into Audiobookshelf layout
├── find_duplicates.py      # Reports duplicate audio files
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
- `--version` prints the script version and file path
- Experimental switches stored in `~/.abclient.json` (used by `AbClient`)
- Prints scores from all metadata providers

### `flatten_discs.py`

- Flattens multi-disc folders (e.g., `Disc 01`, `CD1`)
- Renames all tracks sequentially
- Merges into a single clean folder

### `combobook.py`

- Combines the functionality of both scripts:
  - Detects audio files
  - Tags them using `search_and_tag.py` logic
  - Creates cleaned-up `Author/Year - Title` folder
  - Moves and renames content

### `restructure_for_audiobookshelf.py`

- Reorganizes existing folders into Audiobookshelf layout using metadata from
  tags, `metadata.json` or `book.nfo`
- Keeps numeric part suffixes like `(1 of 6)` or `Part 1` when moving files
- Writes `track` or `trkn` tags so players keep the right order
- Renames tracks safely to avoid name collisions
- Detects fuzzy series numbering ("Book 2", "#2", "Volume II")
- `--interactive` prompts for series info when unclear

### `find_duplicates.py`

- Scans recursively for audio files with identical SHA1 hashes
- Prints groups of duplicate files
- Writes results to `duplicate_log.txt` in the scanned folder
- Shows scanning progress
- `--version` shows the script version and path

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
| `combobook.py` | v1.7 | `ABtools/combobook.py` |
| `flatten_discs.py` | v1.4 | `ABtools/flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v4.8 | `ABtools/restructure_for_audiobookshelf.py` |
| `search_and_tag.py` | v2.15 | `ABtools/search_and_tag.py` |
| `find_duplicates.py` | v0.3 | `ABtools/find_duplicates.py` |
| `abclient.py` | v0.2 | `ABtools/abclient.py` |

