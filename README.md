Audiobook Organizer & Tagger

This script (combobook.py) automates the process of:

Flattening audiobook folders (e.g., Disc 01, CD2, etc.) into a single directory.

Renaming and sequencing audio tracks as Track 001.mp3, Track 002.mp3, etc.

Reading or inferring metadata (author, title, year, series, volume) from file/folder names.

Searching for official metadata via Open Library and Google Books.

Writing tags to MP3/M4B/M4A/etc. files using ffmpeg.

Moving books into a structure suitable for Audiobookshelf.

📁 Example Output Folder Structure

/Audiobookshelf Library/
├── Brandon Sanderson/│ 
    └── Mistborn/│ 
                 ├── Vol 1 – 2006 – The Final Empire/│ │ 
                                                     ├── Track 001.mp3│ 
                                                     └── ... 
                                                     └── metadata.json


# Preview only (no changes made)
python combobook.py "source_folder" "library_folder"

# Tag + move (interactive confirmation)
python combobook.py "source_folder" "library_folder" --commit

# Tag + move (auto-confirm all matches)
python combobook.py "source_folder" "library_folder" --commit --yes