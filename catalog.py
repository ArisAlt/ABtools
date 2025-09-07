#!/usr/bin/env python3
"""
ABtools/catalog.py · v0.1 · 2025-09-01
SQLite catalog of processed audiobooks.
"""
from __future__ import annotations
import sqlite3, hashlib
from pathlib import Path
from typing import Tuple, Dict

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".opus"}

class Catalog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS catalog(
                signature TEXT PRIMARY KEY,
                author TEXT,
                title TEXT,
                year TEXT,
                duration INTEGER,
                tracks INTEGER,
                sha1snippet TEXT
            )"""
        )
        self.conn.commit()

    def has(self, signature: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM catalog WHERE signature=?", (signature,))
        return cur.fetchone() is not None

    def add(self, signature: str, data: Dict) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO catalog(signature,author,title,year,duration,tracks,sha1snippet)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                signature,
                data.get("author"),
                data.get("title"),
                data.get("year"),
                data.get("duration", 0),
                data.get("tracks", 0),
                data.get("sha1snippet"),
            ),
        )
        self.conn.commit()

    @staticmethod
    def calc_signature(book: Path, meta: Dict) -> Tuple[str, Dict]:
        audio_files = sorted(
            [p for p in book.iterdir() if p.suffix.lower() in AUDIO_EXTS]
        )
        tracks = len(audio_files)
        sha1snippet = ""
        if audio_files:
            with audio_files[0].open("rb") as fh:
                sha1snippet = hashlib.sha1(fh.read(65536)).hexdigest()
        duration = int(meta.get("duration", 0))
        key = f"{meta.get('author')}|{meta.get('title')}|{meta.get('year')}|{duration}|{tracks}|{sha1snippet}"
        signature = hashlib.sha1(key.encode()).hexdigest()
        data = {
            "author": meta.get("author"),
            "title": meta.get("title"),
            "year": meta.get("year"),
            "duration": duration,
            "tracks": tracks,
            "sha1snippet": sha1snippet,
        }
        return signature, data
