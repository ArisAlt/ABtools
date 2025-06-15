# Audiobook Organizer & Tagger

This repository contains small utilities for preparing audiobook folders for [Audiobookshelf](https://www.audiobookshelf.org/).


## Features

- Automatically tags `.mp3`, `.m4a`, and `.m4b` files with metadata
- Uses data from Audible, OpenLibrary, and Google Books
- Reorganizes folders into a clean structure: `Author/Year - Title`
- Strips old or broken tags if needed
- Writes metadata to both `metadata.json` and `book.nfo` (for Kodi-style readers)
- Provides preview and logging
- Optionally prompts for confirmation or proceeds automatically

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

| `combobook.py` | v1.6 | `ABtools/combobook.py` |
| `flatten_discs.py` | v1.4 | `ABtools/flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v4.2 | `ABtools/restructure_for_audiobookshelf.py` |
| `search_and_tag.py` | v2.9 | `ABtools/search_and_tag.py` |

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
Use ``--version`` to print the script version and file location.

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
Open Library and Google Books, chooses the best match via fuzzy scoring
and automatically applies it. Matches with a low score will ask for
confirmation unless you pass `--yes`. Use `--no` to decline
automatically. The prompt defaults to `no` so low-confidence matches
aren't accepted accidentally. Use `--debug` to print full tracebacks on
unexpected errors.

When a book has no match or you decline the suggested metadata, the
folder path is written to `review_log.txt` in the chosen root folder for
later inspection. All actions are logged to `tag_log.txt` beside it. On
successful tagging, the metadata is exported to `metadata.json` and
`book.nfo` so other players (including Audiobookshelf) can read the
details.


## `flatten_discs.py`
`flatten_discs.py` merges disc-numbered rips into one folder with sequential track names. Preview changes by default; use `--commit` to apply them and `--yes` to auto-confirm.

## `restructure_for_audiobookshelf.py`
`restructure_for_audiobookshelf.py` reorganizes a source collection into Audiobookshelf layout. It injects basic tags from folder names when needed, flattens disc folders, and moves or copies books to `<library>/Author/Series?/Vol # - YYYY - Title {Narrator}/`. Run with `--commit` to perform the move and `--copy` to duplicate instead.


