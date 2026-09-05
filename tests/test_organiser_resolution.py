"""Regression tests for how the two organisers resolve a book's identity.

These start from *files on disk*, not a pre-built Meta. The earlier parity test
compared `combobook.dest_path()` with `restructure.target_for()` using an
already-resolved record, which only exercised the formatter the two tools
share -- it passed while the resolvers disagreed completely (bug.md 4.8).

Tag values here are taken verbatim from a real library that was mis-organised;
each is a case that previously produced a junk top-level author folder, a
missing series level, or an unnecessary trip to _unmatched/.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ablib.metadata.utils import (  # noqa: E402
    is_plausible_author,
    normalise_author,
    parse_book_folder_name,
    primary_author,
)
from ablib.tagging.files import strip_track_tail  # noqa: E402

LONG_CREDIT = "Andrzej Sapkowski, Terry Goodkind, Anthony Ryan, Andy Weir, Raymond E. Feist"


# ── the author guard ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name, stem",
    [
        ("Side 01", None),
        ("Disc 1", None),
        ("CD 2", None),
        ("01", None),
        ("3 of 12", None),
        ("Unknown", None),
        ("Various Artists", None),
        ("", None),
        ("AttheGatesofDarkness Part1 Track 01", "AttheGatesofDarkness Part1 Track 01"),
        ("01 A Darhness at Sethanon", "01_A_Darhness_at_Sethanon"),
    ],
)
def test_rip_debris_is_not_an_author(name, stem):
    assert not is_plausible_author(name, filename_stem=stem)


@pytest.mark.parametrize("name", ["Raymond E. Feist", "Raymond E Feist", "Feist", "bell hooks"])
def test_real_names_survive(name):
    assert is_plausible_author(name)


def test_one_author_yields_one_folder():
    assert normalise_author("Raymond E Feist") == normalise_author("Raymond E. Feist")


def test_long_credit_list_is_not_truncated_mid_word():
    # Previously became "Andrzej Sapkowski, Terry Goodkind, Anthony Ryan, A".
    assert primary_author(LONG_CREDIT) == "Andrzej Sapkowski"


def test_co_authorship_is_preserved():
    assert primary_author("Terry Pratchett, Neil Gaiman") == "Terry Pratchett, Neil Gaiman"


# ── self-describing folder names ────────────────────────────────────────────

@pytest.mark.parametrize(
    "folder, author, series, index, title",
    [
        ("Feist - Riftwar Saga - Book 4 - A Darkness at Sethanon",
         "Feist", "Riftwar Saga", "4", "A Darkness at Sethanon"),
        ("Feist - Empire Trilogy - Book 1 - Daughter of the Empire",
         "Feist", "Empire Trilogy", "1", "Daughter of the Empire"),
        ("Feist - Riftwar Saga - Book 1 & 2 - Magician & Master",
         "Feist", "Riftwar Saga", "1", "Magician & Master"),
        ("Serpentwar Saga 03 - Rage of a Demon King (1998)",
         None, "Serpentwar Saga", "03", "Rage of a Demon King"),
        ("Mistborn Book 1 - The Final Empire (2006)",
         None, "Mistborn", "1", "The Final Empire"),
    ],
)
def test_leaf_name_carries_the_book(folder, author, series, index, title):
    parsed = parse_book_folder_name(folder)
    assert parsed["author"] == author
    assert parsed["series"] == series
    assert parsed["series_index"] == index
    assert parsed["title"] == title


def test_standalone_book_gets_no_invented_series():
    parsed = parse_book_folder_name("Krondor the Betrayal (1998)")
    assert parsed["series"] is None
    assert parsed["title"] == "Krondor the Betrayal"
    assert parsed["year"] == "1998"


# ── track titles must not name the folder ───────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Rage of a Demon King - 01 of 14", "Rage of a Demon King"),
        ("At the Gates of Darkness Part1", "At the Gates of Darkness"),
        ("Slaughterhouse 5", "Slaughterhouse 5"),   # a number that belongs
        ("Catch 22", "Catch 22"),
        ("Faerie Tale", "Faerie Tale"),
    ],
)
def test_track_tail_stripping(raw, expected):
    assert strip_track_tail(raw) == expected


# ── end to end, from files on disk ──────────────────────────────────────────

def _write_book(root, folder, filename, artist=None, album=None, date=None):
    pytest.importorskip("mutagen")
    from mutagen.easyid3 import EasyID3

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg needed to synthesise the audio fixture")
    book = Path(root) / folder
    book.mkdir(parents=True, exist_ok=True)
    target = book / filename
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", "-c:a", "libmp3lame",
         "-q:a", "9", "-y", str(target)],
        check=True,
    )
    if artist or album:
        tags = EasyID3()
        if artist:
            tags["artist"] = artist
        if album:
            tags["album"] = album
        if date:
            tags["date"] = date
        tags.save(str(target))
    return book


def test_junk_artist_tag_never_becomes_an_author_folder(tmp_path):
    """The regression that mattered: 'Side 01' was a top-level library folder."""
    import restructure_for_audiobookshelf as restructure

    book = _write_book(
        tmp_path / "src", "Side 01/Riftwar saga 03 - Silverthorn",
        "Side 01 - 01.mp3", artist="Side 01", album="Riftwar saga 03 - Silverthorn",
    )
    lib = tmp_path / "lib"
    parts = restructure.target_for("Side 01", book, lib).relative_to(lib).parts

    assert parts[0] != "Side 01"
    assert parts[0] == "Unknown Author"
    # the series level still has to appear, and the title must lose its prefix
    assert parts[1] == "Riftwar saga"
    assert parts[2] == "Silverthorn"


def test_tagged_series_book_gets_a_series_level(tmp_path):
    import combobook
    import restructure_for_audiobookshelf as restructure

    book = _write_book(
        tmp_path / "src",
        "Raymond E Feist/Serpentwar Saga 03 - Rage of a Demon King (1998)",
        "Raymond E Feist - Rage of a Demon King - 01 of 14.mp3",
        artist="Raymond E Feist", album="Serpentwar Saga 03 - Rage of a Demon King",
        date="1998",
    )
    lib = tmp_path / "lib"
    expected = Path("Raymond E. Feist/Serpentwar Saga/Rage of a Demon King (1998)")

    tags = combobook.tags_from_track(next(book.glob("*.mp3")))
    merged = combobook.merge_tag_and_folder(tags, combobook.guess_from_folder(book))
    assert combobook.dest_path(lib, merged).relative_to(lib) == expected

    # and the other organiser must land in exactly the same place
    assert restructure.target_for("Raymond E Feist", book, lib).relative_to(lib) == expected


def test_unmatched_folder_is_left_alone(tmp_path):
    """`--move-unmatched` off means the source folder is not touched at all."""
    import combobook

    src = tmp_path / "src"
    book = _write_book(src, "Totally Unidentifiable Rip 12345", "01.mp3")
    before = sorted(p.name for p in book.iterdir())

    combobook.MOVE_UNMATCHED = False
    combobook.tagger.CONFIG.llm_endpoint = None
    summary = defaultdict(int)
    combobook.process(book, src, tmp_path / "lib", dry=False, yes=True,
                      copy=False, summary=summary)

    assert book.exists()
    assert sorted(p.name for p in book.iterdir()) == before
    assert summary["left_in_place"] == 1
    assert not list((tmp_path / "lib").glob("**/*.mp3"))
