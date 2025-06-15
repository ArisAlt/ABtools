# Audiobook Tagging & Organization – Scaffold

## Project Structure

```
Audiobooks/
│
├── search_and_tag.py       # Tags files using metadata providers
├── flatten_discs.py        # Merges "Disc" folders into one
├── combobook.py            # Combines tagging and restructuring
├── metadata.json           # Optional: sample metadata format
├── requirements.txt        # Pip requirements
├── README.md
└── SCAFFOLD.md
```

## Scripts Overview

### `search_and_tag.py`

- Tags audio files using best match from:
  - Audible
  - OpenLibrary
  - Google Books
- Writes:
  - ID3 or MP4 tags
  - `metadata.json`
  - `book.nfo`

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
