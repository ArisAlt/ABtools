# Audiobook Organizer & Tagger

This repository contains small utilities for preparing audiobook folders for [Audiobookshelf](https://www.audiobookshelf.org/).

## Scripts

| Script | Version | Path |
|-------|---------|------|

| `combobook.py` | v1.5 | `ABtools/combobook.py` |
| `flatten_discs.py` | v1.3 | `ABtools/flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v4.1 | `ABtools/restructure_for_audiobookshelf.py` |
| `search_and_tag.py` | v2.3 | `ABtools/search_and_tag.py` |

Run any script with `--version` to print its version and file location.

## `combobook.py`
`combobook.py` tags, flattens and moves audiobook folders in a single pass. It searches Open Library, Google Books and Audible, ranks potential matches using fuzzy similarity and asks you to confirm before tagging and moving files.

It now also collapses folders named like `Book Title (1 of 5)` into a single directory and names each file `Part 01`, `Part 02`, etc.


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
confirmation unless you pass `--yes`.

When a book has no match or you decline the suggested metadata, the
folder path is written to `review_log.txt` for later inspection. On
successful tagging, the metadata is exported to `metadata.json` and
`book.nfo` so other players (including Audiobookshelf) can read the
details.


## `flatten_discs.py`
`flatten_discs.py` merges disc-numbered rips into one folder with sequential track names. Preview changes by default; use `--commit` to apply them and `--yes` to auto-confirm.

## `restructure_for_audiobookshelf.py`
`restructure_for_audiobookshelf.py` reorganizes a source collection into Audiobookshelf layout. It injects basic tags from folder names when needed, flattens disc folders, and moves or copies books to `<library>/Author/Series?/Vol # - YYYY - Title {Narrator}/`. Run with `--commit` to perform the move and `--copy` to duplicate instead.

