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
- Preserves part numbers like `(1 of 6)` when reorganizing files
- Adds track numbers so multi-part books play in order
- Detects series and volume numbers with fuzzy matching
  and prompts for confirmation when run with `--interactive`
- Each script reports its version and location with `--version`
- Experimental features are toggled via `~/.abclient.json` using `AbClient`
- Prints the score from each metadata provider during tagging
- `find_duplicates.py` shows progress while scanning and can compare
  files by SHA1 hash or by name

## Requirements

- Python 3.8+
- Dependencies:
  - `mutagen`
  - `requests`
  - `beautifulsoup4`
  - `rapidfuzz`
  - `rich` (optional, for prettier output)

Install all dependencies with:

```bash
pip install -r requirements.txt
```

## Scripts

| Script | Version | Path |
|-------|---------|------|

| `combobook.py` | v1.7 | `ABtools/combobook.py` |
| `flatten_discs.py` | v1.4 | `ABtools/flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v4.8 | `ABtools/restructure_for_audiobookshelf.py` |
| `search_and_tag.py` | v2.15 | `ABtools/search_and_tag.py` |
| `find_duplicates.py` | v0.4 | `ABtools/find_duplicates.py` |
| `abclient.py` | v0.2 | `ABtools/abclient.py` |

Run any script with `--version` to print its version and file location.

## `combobook.py`
`combobook.py` tags, flattens and moves audiobook folders in a single pass. It searches Open Library, Google Books and Audible, ranks potential matches using fuzzy similarity and asks you to confirm before tagging and moving files.

It now also collapses folders named like `Book Title (1 of 5)` into a single directory and names each file `Part 01`, `Part 02`, etc.

"""

Tag (or strip) audiobook files using multiple metadata providers.

The script queries Audible, Open Library and Google Books, ranks the
results using fuzzy title matching and automatically tags files with the
best match. Low scoring hits will prompt for confirmation unless you
run with ``--yes``. When prompted, the default answer is "No" so low
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

## `search_and_tag.py`
`search_and_tag.py` tags or strips audiobook files. It queries Audible,
Goodreads (optional), Open Library and Google Books. The score from each
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


## `flatten_discs.py`
`flatten_discs.py` merges disc-numbered rips into one folder with sequential track names. Preview changes by default; use `--commit` to apply them and `--yes` to auto-confirm.

## `restructure_for_audiobookshelf.py`
`restructure_for_audiobookshelf.py` reorganizes a source collection into Audiobookshelf layout. It reads tags from the audio files first, then `metadata.json` or `book.nfo`, and finally falls back to folder names. Disc folders are flattened and books are moved or copied to `<library>/Author/Series?/Vol # - YYYY - Title {Narrator}/`. Series names and volume numbers are detected with fuzzy matching (e.g. `Book 3`, `#3`, `Volume III`). When run with `--interactive`, the script prompts for missing series info. Metadata matching is handled by `search_and_tag.py`. Track renaming now avoids collisions by staging files with temporary names first.

## `find_duplicates.py`
`find_duplicates.py` scans a folder recursively and can find duplicates either by computing SHA1 hashes or by matching file names. Progress is shown while scanning. Results are written to `duplicate_log.txt` inside the scanned folder. Use `--version` to show the script version and path. Hash matching now skips hashing files with unique sizes for much faster scans.



## `abclient.py`
`abclient.py` provides simple A/B switch management. Switch states are loaded from the JSON file `~/.abclient.json`. For example:

```json
{
  "use_goodreads": true,
  "audible_first": false
}
```

Edit this file to enable or disable experimental features.
