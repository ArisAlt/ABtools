# Audiobook Organizer & Tagger

This repository contains small utilities for preparing audiobook folders for [Audiobookshelf](https://www.audiobookshelf.org/).

## Scripts

| Script | Version | Path |
|-------|---------|------|

| `combobook.py` | v1.5 | `ABtools/combobook.py` |
| `flatten_discs.py` | v1.3 | `ABtools/flatten_discs.py` |
| `restructure_for_audiobookshelf.py` | v4.1 | `ABtools/restructure_for_audiobookshelf.py` |
| `search_and_tag.py` | v2.0 | `ABtools/search_and_tag.py` |

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

