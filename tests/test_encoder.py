"""Encoder profiles and the guarantees around deleting source audio.

The two behaviours under test are the ones that cost real data:

*   A folder whose audio ffmpeg cannot decode used to be encoded anyway.
    ffmpeg returned 0, the old verify_audio saw a positive duration, the run
    reported success, and --cleanup then deleted the originals -- leaving a
    book quietly missing whichever chapters were unreadable. Reproduced on a
    real library (Nora Ashcroft) where 8 of 353 MP3s and 2 of 3 M4Bs are
    NUL-padded part-downloads.
*   Folders holding .m4b or .m4a parts never entered the task list at all,
    because those suffixes were missing from EXTENSIONS. A two-part book was
    not skipped with a message; it was invisible.

Files here are generated with ffmpeg rather than committed, so the suite skips
cleanly on a machine without it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ab_encode as E  # noqa: E402

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


# ── helpers ────────────────────────────────────────────────────────────────

def make_tone(path: Path, *, seconds: int, freq: int = 440, title: str = "",
              codec: str = "libmp3lame", rate: int = 44100, channels: int = 1) -> Path:
    """Write a short real audio file so the encoder has something to chew on."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
        "-c:a", codec, "-b:a", "64k", "-ar", str(rate), "-ac", str(channels),
    ]
    if title:
        cmd += ["-metadata", f"title={title}"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def make_part_download(path: Path, *, source: Path) -> Path:
    """A file whose first 90% is NUL bytes, as a stalled download leaves it.

    Shaped from real examples in a downloaded library: 17 MB allocated, 1.5 MB
    of actual MP3 frames at the tail. On a large file ffprobe cannot describe
    it at all; on a small one ffprobe *skips the junk*, reports a plausible
    codec and a short duration, and ffmpeg decodes the tail without error --
    which is precisely why the padding ratio, and not the decoder, is what
    catches this.
    """
    payload = source.read_bytes()
    keep = len(payload) // 10
    path.write_bytes(b"\0" * (len(payload) - keep) + payload[-keep:])
    return path


def make_scrambled(path: Path, *, source: Path) -> Path:
    """A file with valid framing but corrupt audio data in the middle."""
    payload = bytearray(source.read_bytes())
    mid = len(payload) // 2
    payload[mid:mid + 4000] = os.urandom(4000)
    path.write_bytes(bytes(payload))
    return path


# ── profiles ───────────────────────────────────────────────────────────────

def test_the_default_profile_is_the_one_an_iphone_can_play():
    """AAC-LC in MP4 is the only format iOS, Android, ABS and CarPlay share."""
    profile = E.PROFILES[E.DEFAULT_PROFILE]
    assert profile.codec == "aac"
    assert profile.container == "mp4"
    assert profile.extension == ".m4b"
    # aac_low is AAC-LC. Without it a future encoder swap could emit HE-AAC,
    # which older iPods and many car head units refuse.
    assert "aac_low" in profile.encoder_flags
    # faststart moves the index to the front, so streaming players can start
    # without fetching the whole file first.
    assert "+faststart" in profile.muxer_flags
    assert profile.supports_chapters


def test_encoder_flags_are_kept_out_of_the_muxer_set():
    """The two lists exist because mixing them breaks stream copying.

    "-profile:a aac_low" handed to a "-c:a copy" command makes ffmpeg try to
    evaluate aac_low as an expression and abort with exit 234, so a folder of
    already-correct AAC files -- the case passthrough exists for -- failed.
    """
    encoder_only = {"-profile:a", "-vbr", "-application", "-b:a", "-ar", "-ac"}
    for key, profile in E.PROFILES.items():
        assert not (set(profile.muxer_flags) & encoder_only), key
        assert "-movflags" not in profile.encoder_flags, key
    # The copy profile has nothing an encoder could act on.
    assert E.PROFILES["copy"].encoder_flags == ()


def test_the_menu_offers_an_android_choice_that_is_not_the_default():
    keys = set(E.PROFILE_ORDER)
    assert {"android-aac", "android-opus"} <= keys
    opus = E.PROFILES["android-opus"]
    assert opus.codec == "libopus"
    # Opus resamples to 48k internally; any other rate is a wasted resample.
    assert opus.sample_rate == "48000"
    # Apple ships no Opus decoder, and the label has to say so, because the
    # whole point of the default is iPhone playback.
    assert "NOT iPhone" in opus.plays_on


def test_every_profile_is_internally_consistent():
    for key, profile in E.PROFILES.items():
        assert profile.key == key
        assert profile.extension.startswith(".")
        assert profile.plays_on, f"{key} does not say what plays it"
        if profile.codec == "copy":
            assert profile.needs_encoder is None
        else:
            assert profile.probe_codec, f"{key} has no probe codec to verify against"
        if profile.bitrates:
            assert profile.default_bitrate in profile.bitrates


def test_profile_labels_round_trip_and_fall_back():
    for key in E.PROFILE_ORDER:
        assert E.profile_for_label(E.PROFILES[key].label).key == key
    # A label from an older settings file must not leave the GUI stranded.
    assert E.profile_for_label("something removed in v3").key == E.DEFAULT_PROFILE


@needs_ffmpeg
def test_every_offered_profile_names_an_encoder_this_build_has():
    encoders = E.available_encoders()
    assert encoders, "could not read ffmpeg -encoders"
    for key in E.PROFILE_ORDER:
        profile = E.PROFILES[key]
        ok, why = E.profile_available(profile)
        if profile.needs_encoder in encoders or profile.needs_encoder is None:
            assert ok, why


# ── the invisible-folder bug ───────────────────────────────────────────────

def test_source_extensions_cover_what_audiobooks_actually_arrive_in():
    """.m4b and .m4a were missing, and their absence was silent.

    os.walk only queued a folder when something in it matched EXTENSIONS, so a
    folder of .m4b parts produced no task, no status line and no output.
    """
    for suffix in (".mp3", ".m4a", ".m4b", ".opus", ".flac", ".wav", ".ogg"):
        assert suffix in E.EXTENSIONS


def test_a_folder_of_m4b_parts_is_now_visible_to_the_walker(tmp_path):
    old_extensions = (".mp3", ".wav", ".flac", ".m4a", ".ogg")
    book = tmp_path / "2 - West and East"
    book.mkdir()
    (book / "1.m4b").write_bytes(b"")
    (book / "2.m4b").write_bytes(b"")
    names = os.listdir(book)
    assert not any(n.lower().endswith(old_extensions) for n in names)
    assert any(n.lower().endswith(E.EXTENSIONS) for n in names)


# ── verification ───────────────────────────────────────────────────────────

@needs_ffmpeg
def test_verify_output_rejects_an_output_shorter_than_its_sources(tmp_path):
    """The failure a positive duration cannot catch."""
    clip = make_tone(tmp_path / "clip.m4a", seconds=6, codec="aac")
    ok, why = E.verify_output(
        str(clip), expected_duration=600.0,
        profile=E.PROFILES["android-aac"], deep=False,
    )
    assert not ok
    assert "sources total" in why


@needs_ffmpeg
def test_verify_output_rejects_the_wrong_codec(tmp_path):
    clip = make_tone(tmp_path / "clip.mp3", seconds=3)
    ok, why = E.verify_output(
        str(clip), expected_duration=3.0,
        profile=E.PROFILES["iphone"], deep=False,
    )
    assert not ok
    assert "expected aac" in why


def test_verify_output_fails_closed_on_a_missing_or_empty_file(tmp_path):
    profile = E.PROFILES["iphone"]
    ok, why = E.verify_output(str(tmp_path / "nope.m4b"), expected_duration=1.0,
                              profile=profile, deep=False)
    assert not ok and "not created" in why

    empty = tmp_path / "empty.m4b"
    empty.write_bytes(b"")
    ok, why = E.verify_output(str(empty), expected_duration=1.0,
                              profile=profile, deep=False)
    assert not ok and "empty" in why


def test_the_duration_window_stays_narrower_than_a_chapter():
    """A tolerance wide enough to swallow a lost chapter is not a check.

    Chapters run roughly 10-30 minutes, so the window has to stay well under
    ten, while still absorbing encoder priming on a short book.
    """
    assert E.duration_tolerance(30.0) == 4.0            # floor for tiny files
    assert E.duration_tolerance(7 * 3600) == 60.0       # capped on a long book
    assert E.duration_tolerance(3600) == 60.0 * 0.3     # 0.5% in between


@needs_ffmpeg
def test_decodes_cleanly_reads_stderr_not_the_exit_code(tmp_path):
    """ffmpeg exits 0 after dropping an undecodable packet; stderr does not.

    This is the whole reason deep verification reads stderr rather than the
    return code.
    """
    good = make_tone(tmp_path / "good.mp3", seconds=4)
    ok, why = E.decodes_cleanly(str(good))
    assert ok, why

    scrambled = make_scrambled(tmp_path / "scrambled.mp3", source=good)
    ok, why = E.decodes_cleanly(str(scrambled))
    assert not ok
    assert why


@needs_ffmpeg
def test_a_part_download_is_caught_by_padding_not_by_decoding(tmp_path):
    """The failure mode every other check waves through.

    ffprobe skips the leading junk and reports a valid stream with a short
    duration; ffmpeg then decodes that remnant without a single error. Only
    the file's size, set against the audio it claims to hold, gives it away.
    """
    good = make_tone(tmp_path / "good.mp3", seconds=4)
    broken = make_part_download(tmp_path / "broken.mp3", source=good)

    described = E.probe(str(broken))
    assert described.codec == "mp3"          # looks entirely plausible
    assert described.duration and described.duration > 0
    assert E.decodes_cleanly(str(broken))[0]  # and decodes without complaint

    assert described.padding_ratio > E.PADDING_RATIO_LIMIT
    assert not described.readable
    assert "part-finished download" in described.damage

    assert E.probe(str(good)).readable
    assert E.probe(str(good)).damage == ""


def test_a_preallocated_file_is_caught_without_any_probe(tmp_path):
    """The signal that survives when ffprobe cannot describe the file at all.

    A large enough NUL run exhausts ffprobe's probesize before it reaches any
    audio, so there is no duration, codec or bitrate to reason about.
    """
    stalled = tmp_path / "stalled.m4b"
    stalled.write_bytes(b"\0" * (E.NULL_HEAD_BYTES + 1024))
    assert E._null_head(str(stalled)) == E.NULL_HEAD_BYTES

    described = E.Probe(str(stalled), None, "", 0, 0, "",
                        null_head=E.NULL_HEAD_BYTES)
    assert not described.readable
    assert "zero bytes" in described.damage


def test_a_healthy_file_is_never_called_damaged():
    """Guarding the guard: the limit has to clear real containers easily.

    Measured over a 353-file library, every healthy file scored exactly 1.00,
    so the only way to trip this is genuine padding.
    """
    healthy = E.Probe("/x/a.mp3", duration=600.0, codec="mp3", sample_rate=44100,
                      channels=1, title="", size=int(600 * 64000 / 8),
                      bit_rate=64000)
    assert healthy.readable
    assert abs(healthy.padding_ratio - 1.0) < 0.01

    # Even a fat cover image plus container overhead stays far below the limit.
    chunky = E.Probe("/x/b.m4b", duration=600.0, codec="aac", sample_rate=44100,
                     channels=1, title="", size=int(600 * 64000 / 8 * 1.5),
                     bit_rate=64000)
    assert chunky.readable

    # And a file whose bitrate ffprobe would not report is not condemned for it.
    unknown = E.Probe("/x/c.wav", duration=600.0, codec="pcm_s16le",
                      sample_rate=44100, channels=1, title="", size=99, bit_rate=0)
    assert unknown.padding_ratio is None
    assert unknown.readable


# ── refusing to encode damaged sources ─────────────────────────────────────

@needs_ffmpeg
def test_a_damaged_source_is_refused_and_nothing_is_deleted(tmp_path):
    """The data-loss path, end to end, with cleanup armed."""
    book = tmp_path / "Damaged Book"
    make_tone(book / "01.mp3", seconds=4, title="One")
    make_tone(book / "02.mp3", seconds=4, freq=660, title="Two")
    make_part_download(book / "03.mp3", source=book / "01.mp3")
    before = sorted(p.name for p in book.iterdir())

    result = E.process_folder(str(book), bitrate="64k", channels="1", cleanup=True)

    assert "Refused" in result["status"]
    assert "03.mp3" in result["detail"]
    # Every source still on disk, and no half-built output left behind.
    assert sorted(p.name for p in book.iterdir()) == before


@needs_ffmpeg
def test_skip_unreadable_encodes_the_rest_but_still_keeps_the_sources(tmp_path):
    """Opting past the refusal must not also opt into deleting originals.

    The output is knowingly not a faithful copy of the folder, so the sources
    are the only remaining record of what was dropped.
    """
    book = tmp_path / "Partly Damaged"
    make_tone(book / "01.mp3", seconds=4, title="One")
    make_tone(book / "02.mp3", seconds=4, freq=660, title="Two")
    make_part_download(book / "03.mp3", source=book / "01.mp3")

    result = E.process_folder(str(book), bitrate="64k", channels="1",
                              cleanup=True, skip_unreadable=True)

    assert "Success" in result["status"], result
    assert (book / "01.mp3").exists()
    assert (book / "02.mp3").exists()
    assert (book / "03.mp3").exists()
    assert (book / "Partly Damaged.m4b").exists()


def test_cleanup_cannot_be_combined_with_a_shallow_verify(tmp_path, monkeypatch):
    """deep_verify=False plus cleanup=True must resolve to a deep verify."""
    seen: dict[str, object] = {}

    def fake_verify(path, *, expected_duration, profile, deep):
        seen["deep"] = deep
        return False, "stopped here"

    monkeypatch.setattr(E, "verify_output", fake_verify)
    monkeypatch.setattr(E, "probe", lambda p: E.Probe(p, 10.0, "mp3", 44100, 1, ""))
    monkeypatch.setattr(
        E.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, "", ""),
    )

    book = tmp_path / "Book"
    book.mkdir()
    (book / "01.mp3").write_bytes(b"x")
    (book / "02.mp3").write_bytes(b"x")

    E.process_folder(str(book), bitrate="64k", channels="1",
                     cleanup=True, deep_verify=False)
    assert seen["deep"] is True


# ── stream copy ────────────────────────────────────────────────────────────

def _probe(codec="aac", rate=44100, channels=1, name="a.m4a"):
    return E.Probe(path=name, duration=10.0, codec=codec,
                   sample_rate=rate, channels=channels, title="")


def test_stream_copy_is_refused_when_the_parameters_differ():
    """The concat demuxer does not renegotiate between files.

    Copying across a sample-rate change plays the remainder at the wrong
    speed, which no duration check would catch, so it is blocked up front.
    """
    ok, _ = E._can_stream_copy([_probe(), _probe()])
    assert ok

    ok, why = E._can_stream_copy([_probe(rate=44100), _probe(rate=22050)])
    assert not ok and "sample rate" in why

    ok, why = E._can_stream_copy([_probe(channels=1), _probe(channels=2)])
    assert not ok and "channel count" in why

    ok, why = E._can_stream_copy([_probe(), _probe(codec="mp3")])
    assert not ok and "not all AAC" in why

    ok, why = E._can_stream_copy([])
    assert not ok


@needs_ffmpeg
def test_the_copy_profile_refuses_mp3_sources_rather_than_garbling_them(tmp_path):
    book = tmp_path / "Book"
    make_tone(book / "01.mp3", seconds=3)
    make_tone(book / "02.mp3", seconds=3, freq=660)
    result = E.process_folder(str(book), profile="copy")
    assert "Refused" in result["status"]
    assert "not all AAC" in result["detail"]


# ── channels ───────────────────────────────────────────────────────────────

def test_the_channel_count_is_left_alone_by_default():
    """Forcing mono would re-encode every stereo .m4b just to join its parts.

    930 of the 1290 audio files in the library this was measured against are
    already .m4b, a mix of mono and stereo AAC. Downmixing them is lossy, and
    with --cleanup the original is gone.
    """
    stereo = [_probe(channels=2), _probe(channels=2)]
    assert E._output_channels(E.KEEP_SOURCE_CHANNELS, stereo) is None
    assert E._output_channels("1", stereo) == "1"
    assert E._output_channels("2", stereo) == "2"


def test_mixed_channel_counts_resolve_upward_not_downward():
    """One mono file in a folder must not silently downmix the rest."""
    mixed = [_probe(channels=1), _probe(channels=2)]
    assert E._output_channels(E.KEEP_SOURCE_CHANNELS, mixed) == "2"


@needs_ffmpeg
def test_stereo_aac_parts_are_joined_losslessly_rather_than_downmixed(tmp_path):
    """The case the default exists for: joining an already-encoded book."""
    book = tmp_path / "Two Part Book"
    make_tone(book / "p1.m4b", seconds=4, codec="aac", channels=2, title="One")
    make_tone(book / "p2.m4b", seconds=4, freq=660, codec="aac", channels=2,
              title="Two")
    before = sum(f.stat().st_size for f in book.glob("*.m4b"))

    result = E.process_folder(str(book), bitrate="64k")
    assert "Success" in result["status"], result

    out = E.probe(str(book / "Two Part Book.m4b"))
    assert out.channels == 2, "a stereo book came back mono"
    # A copy, not a re-encode: the audio is carried over near byte for byte.
    assert out.size > before * 0.9


# ── sample rate ────────────────────────────────────────────────────────────

def test_the_encoder_does_not_resample_a_standard_rate_at_all():
    """Resampling is never free in either direction.

    Real sources run 12, 22.05, 24, 32, 44.1 and 48 kHz; 24 kHz alone was 82%
    of one measured library, so a fixed 44100 resampled nearly all of it.
    """
    iphone = E.PROFILES["iphone"]
    for rate in sorted(E.STANDARD_SAMPLE_RATES):
        got = E._output_sample_rate(iphone, [_probe(rate=rate), _probe(rate=rate)])
        assert got == str(rate), f"{rate} was resampled to {got}"


def test_an_unusual_or_mixed_source_rate_falls_back_to_the_profile():
    """Both cases must land on something universally playable."""
    iphone = E.PROFILES["iphone"]
    # Mixed sources have to be unified, and the profile rate is the safe one.
    assert E._output_sample_rate(iphone, [_probe(rate=24000),
                                          _probe(rate=44100)]) == "44100"
    # A rate no decoder is guaranteed to define is not adopted.
    assert E._output_sample_rate(iphone, [_probe(rate=37000)]) == "44100"
    assert E._output_sample_rate(iphone, [_probe(rate=96000)]) == "44100"
    assert E._output_sample_rate(iphone, [_probe(rate=0)]) == "44100"


def test_opus_is_left_at_48k_whatever_the_source():
    """Opus resamples internally, so matching the source achieves nothing."""
    opus = E.PROFILES["android-opus"]
    assert E._output_sample_rate(opus, [_probe(rate=24000)]) == "48000"


def test_the_copy_profile_has_no_rate_to_choose():
    assert E._output_sample_rate(E.PROFILES["copy"], [_probe(rate=24000)]) is None


@needs_ffmpeg
def test_a_24k_source_stays_24k_end_to_end(tmp_path):
    book = tmp_path / "Quiet Book"
    make_tone(book / "01.mp3", seconds=3, rate=24000)
    make_tone(book / "02.mp3", seconds=3, freq=660, rate=24000)
    result = E.process_folder(str(book), bitrate="64k", channels="1")
    assert "Success" in result["status"], result
    assert E.probe(str(book / "Quiet Book.m4b")).sample_rate == 24000


# ── chapters ───────────────────────────────────────────────────────────────

def test_chapters_tile_the_book_without_gaps_or_overlaps():
    probes = [
        E.Probe("/x/01.mp3", 5.0, "mp3", 44100, 1, "Opening"),
        E.Probe("/x/02.mp3", 10.0, "mp3", 44100, 1, ""),
        E.Probe("/x/03.mp3", 15.0, "mp3", 44100, 1, "Finale"),
    ]
    text = E.build_chapter_metadata(probes, title="A Book")
    assert text.startswith(";FFMETADATA1")

    starts = [int(l.split("=", 1)[1]) for l in text.splitlines() if l.startswith("START=")]
    ends = [int(l.split("=", 1)[1]) for l in text.splitlines() if l.startswith("END=")]
    assert starts == [0, 5000, 15000]
    assert ends == [5000, 15000, 30000]
    assert starts[1:] == ends[:-1]          # no gap, no overlap

    # One file lacking a tag makes the whole set fall back to filenames, so
    # the chapter list reads consistently instead of half-named.
    assert "title=01" in text and "title=02" in text and "title=03" in text


def test_chapter_names_come_from_tags_only_when_they_distinguish_the_files():
    """Identical tags are worse than no names: the list becomes unusable.

    Taken from a real two-part book whose halves both carried the tag "The Eye
    of the World (The Long Cycle Book 1)" -- on a copy of The Rising Storm,
    at that. Naming both chapters the same helps nobody.
    """
    same = "Book One of the Cycle (The Long Cycle Book 1)"
    probes = [
        E.Probe("/x/p1.2.m4b", 100.0, "aac", 22050, 2, same),
        E.Probe("/x/p2.2.m4b", 100.0, "aac", 22050, 2, same),
    ]
    assert E.chapter_labels(probes) == ["p1.2", "p2.2"]

    distinct = [
        E.Probe("/x/01.mp3", 10.0, "mp3", 44100, 1, "The Ravens"),
        E.Probe("/x/02.mp3", 10.0, "mp3", 44100, 1, "Whirlpools in the Pattern"),
    ]
    assert E.chapter_labels(distinct) == ["The Ravens", "Whirlpools in the Pattern"]


def test_chapter_names_drop_the_boilerplate_every_filename_repeats():
    """From a real 76-part Audible rip: every name opens the same way.

    A chapter list where all 76 entries begin "Until We Are Lost:
    Wayfarer, Book 5 [ASIN00000] - " is unreadable on a phone, and the part
    that varies is the only part worth showing.
    """
    stems = [f"Until We Are Lost: Wayfarer, Book 5 [ASIN00000] - {n} - {t}"
             for n, t in [("01", "Opening Credits"), ("02", "Dedication"),
                          ("03", "Epigraph"),
                          ("04", "1. Destination Galactic Center")]]
    assert E._trim_shared_prefix(stems) == [
        "01 - Opening Credits", "02 - Dedication", "03 - Epigraph",
        "04 - 1. Destination Galactic Center",
    ]


def test_trimming_stops_when_it_would_leave_nothing_worth_reading():
    """Two real books, opposite answers, same rule."""
    # Trimming here leaves "1.2"/"2.2" -- less use than the title it cost.
    wot = ["TLC 04 - The Rising Storm p1.2", "TLC 04 - The Rising Storm p2.2"]
    assert E._trim_shared_prefix(wot) == wot

    # Nothing shared worth removing.
    assert E._trim_shared_prefix(["01", "02", "03"]) == ["01", "02", "03"]

    # A single file has no shared prefix by definition.
    assert E._trim_shared_prefix(["only one"]) == ["only one"]


def test_chapter_names_fall_back_to_an_index_as_a_last_resort():
    """Filenames are unique within a folder, but the caller need not be one."""
    probes = [E.Probe("/a/x.mp3", 5.0, "mp3", 44100, 1, ""),
              E.Probe("/b/x.mp3", 5.0, "mp3", 44100, 1, "")]
    assert E.chapter_labels(probes) == ["Chapter 1", "Chapter 2"]


def test_chapter_titles_escape_ffmetadata_syntax():
    """An unescaped '=' or ';' in a title silently truncates the chapter list."""
    probes = [E.Probe("/x/01.mp3", 5.0, "mp3", 44100, 1, "Act 1; scene=2 #final")]
    text = E.build_chapter_metadata(probes, title="T")
    assert r"Act 1\; scene\=2 \#final" in text


def test_a_source_with_no_duration_is_left_out_of_the_chapter_list():
    probes = [
        E.Probe("/x/01.mp3", 5.0, "mp3", 44100, 1, "One"),
        E.Probe("/x/02.mp3", None, "", 0, 0, ""),
        E.Probe("/x/03.mp3", 5.0, "mp3", 44100, 1, "Three"),
    ]
    text = E.build_chapter_metadata(probes, title="T")
    assert text.count("[CHAPTER]") == 2


# ── output handling ────────────────────────────────────────────────────────

@needs_ffmpeg
def test_the_output_is_never_treated_as_one_of_its_own_sources(tmp_path):
    """Re-running must skip, not fold the previous output back in on itself."""
    book = tmp_path / "Book"
    make_tone(book / "01.mp3", seconds=3, title="One")
    make_tone(book / "02.mp3", seconds=3, freq=660, title="Two")

    first = E.process_folder(str(book), bitrate="64k", channels="1", cleanup=True)
    assert "Success" in first["status"], first
    assert (book / "Book.m4b").exists()
    assert not (book / "01.mp3").exists()

    length = (book / "Book.m4b").stat().st_size
    second = E.process_folder(str(book), bitrate="64k", channels="1", cleanup=True)
    assert "Skipped" in second["status"]
    assert (book / "Book.m4b").stat().st_size == length


@needs_ffmpeg
def test_a_lone_file_already_in_the_target_format_is_left_alone(tmp_path):
    """Finished work, whatever it happens to be called."""
    book = tmp_path / "Through Darkest Winter (2018)"
    make_tone(book / "Through Darkest Winter.m4b", seconds=3, codec="aac")
    result = E.process_folder(str(book), bitrate="64k", channels="1")
    assert "Skipped" in result["status"]


@needs_ffmpeg
def test_a_healthy_book_encodes_to_a_verifiable_iphone_file(tmp_path):
    book = tmp_path / "Good Book"
    make_tone(book / "01.mp3", seconds=5, title="Chapter One")
    make_tone(book / "02.mp3", seconds=10, freq=660, title="Chapter Two")

    result = E.process_folder(str(book), bitrate="64k", channels="1",
                              cleanup=False, deep_verify=True)
    assert "Success" in result["status"], result

    out = book / "Good Book.m4b"
    probe = E.probe(str(out))
    assert probe.codec == "aac"
    assert probe.sample_rate == 44100
    assert abs(probe.duration - 15.0) < E.duration_tolerance(15.0)

    chapters = subprocess.run(
        ["ffprobe", "-v", "error", "-show_chapters", "-of", "default=nw=1", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert chapters.count("id=") == 2
    assert "Chapter One" in chapters and "Chapter Two" in chapters


@needs_ffmpeg
def test_already_correct_aac_sources_are_copied_not_re_encoded(tmp_path):
    """The passthrough path, exercised for real rather than asserted about.

    It regressed once: the profile's encoder flags were being appended to a
    "-c:a copy" command, which ffmpeg rejects outright, so the one case
    passthrough exists to serve was the one case that failed.
    """
    book = tmp_path / "AAC Book"
    make_tone(book / "01.m4a", seconds=3, codec="aac", title="One")
    make_tone(book / "02.m4a", seconds=6, freq=660, codec="aac", title="Two")

    result = E.process_folder(str(book), bitrate="64k", channels="1",
                              deep_verify=True)
    assert "Success" in result["status"], result

    out = E.probe(str(book / "AAC Book.m4b"))
    assert out.codec == "aac"
    assert out.sample_rate == 44100
    assert abs(out.duration - 9.0) < E.duration_tolerance(9.0)


@needs_ffmpeg
def test_no_scratch_files_survive_a_run(tmp_path):
    """The concat list and the chapter metadata are written into the book folder."""
    book = tmp_path / "Book"
    make_tone(book / "01.mp3", seconds=3)
    make_tone(book / "02.mp3", seconds=3, freq=660)
    E.process_folder(str(book), bitrate="64k", channels="1")
    leftovers = [p.name for p in book.iterdir()
                 if p.suffix in (".txt", ".ffmeta", ".tmp")]
    assert leftovers == []


@needs_ffmpeg
def test_a_lone_damaged_file_is_reported_not_mistaken_for_finished_work(tmp_path):
    """A corrupt leftover output must not read as finished work.

    An interrupted run leaves exactly this: the output file in place, no
    sources beside it, and nothing to rebuild from. Reporting "already
    encoded" over it hides the only copy of the audio being broken.
    """
    book = tmp_path / "Stalled Book"
    good = make_tone(book / "seed.m4b", seconds=4, codec="aac")
    make_part_download(book / "Stalled Book.m4b", source=good)
    good.unlink()

    result = E.process_folder(str(book), profile="copy")
    assert "damaged" in result["status"].lower(), result
    assert "no sources left" in result["detail"]


def test_channels_falls_back_rather_than_crashing_a_worker(tmp_path):
    """A stale settings file must not take out a thread mid-run."""
    book = tmp_path / "Book"
    book.mkdir()
    result = E.process_folder(str(book), channels="mono")
    assert "Skipped" in result["status"]


@needs_ffmpeg
def test_an_empty_folder_is_reported_not_crashed(tmp_path):
    book = tmp_path / "Empty"
    book.mkdir()
    (book / "cover.jpg").write_bytes(b"not audio")
    result = E.process_folder(str(book))
    assert "Skipped" in result["status"]
