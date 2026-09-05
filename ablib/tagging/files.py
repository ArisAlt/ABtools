"""Audio tagging utilities (Mutagen-powered)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict

from mutagen import File as MFile
from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TRCK, TXXX
from mutagen.mp4 import MP4

from ablib.core import constants


def has_audio(folder: Path) -> bool:
    """Return True when the folder contains at least one supported audio file."""

    try:
        return any(
            child.is_file() and child.suffix.lower() in constants.AUDIO_EXTS
            for child in folder.iterdir()
        )
    except FileNotFoundError:
        return False


def strip_tags(file: Path) -> None:
    """Remove existing tags from an audio file."""

    audio = MFile(str(file))
    if audio:
        audio.delete()
        audio.save()


def write_tags(file: Path, meta: Dict[str, str], index: int = 0, total: int = 0) -> None:
    """Write audiobook tags for MP3/M4B files."""

    ext = file.suffix.lower()
    if ext == ".mp3":
        try:
            audio = ID3(str(file))
        except ID3NoHeaderError:
            audio = ID3()
        audio.clear()
        audio["TIT2"] = TIT2(3, meta["title"])
        audio["TALB"] = TALB(3, meta["title"])
        audio["TPE1"] = TPE1(3, meta["author"])
        if meta.get("year"):
            audio["TDRC"] = TDRC(3, meta["year"])
        if meta.get("series"):
            audio.add(TXXX(3, desc="series", text=meta["series"]))
        if meta.get("series_index"):
            # Without this the series position is resolved and written to
            # metadata.json/book.nfo but never embedded, so Audiobookshelf
            # cannot order a series from the audio files alone.
            audio.add(TXXX(3, desc="series-part", text=str(meta["series_index"])))
        if index:
            audio["TRCK"] = TRCK(3, f"{index}/{total or index}")
        audio.save(str(file))
    elif ext in {".m4a", ".m4b"}:
        mp4 = MP4(str(file))
        mp4.clear()
        mp4["\u00a9nam"] = meta["title"]
        mp4["\u00a9alb"] = meta["title"]
        mp4["\u00a9ART"] = meta["author"]
        if meta.get("year"):
            mp4["\u00a9day"] = meta["year"]
        if meta.get("series"):
            mp4["----:com.apple.iTunes:series"] = [meta["series"].encode("utf-8")]
        if meta.get("series_index"):
            mp4["----:com.apple.iTunes:series-part"] = [
                str(meta["series_index"]).encode("utf-8")
            ]
        if index:
            mp4["trkn"] = [(index, total or 0)]
        mp4.save()


def export_metadata(path: Path, meta: Dict[str, str]) -> None:
    """Persist metadata to disk for external consumers (json + nfo)."""

    target = path if path.is_dir() else path.parent
    target.mkdir(exist_ok=True)
    with (target / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    root = ET.Element("audiobook")
    for key, value in meta.items():
        if not value:
            continue
        child = ET.SubElement(root, key)
        # str(): meta carries non-string values (notably an int "score" from
        # refine_metadata_via_mcp), and ElementTree refuses to serialise those,
        # failing an otherwise successful tagging run at the very last step.
        child.text = str(value)
    ET.ElementTree(root).write(
        target / "book.nfo", encoding="utf-8", xml_declaration=True
    )


__all__ = ["has_audio", "strip_tags", "write_tags", "export_metadata"]
