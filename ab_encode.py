"""
ab_encode.py  --  Audiobook builder with auto-verification and cleanup.

Scans a root directory for subfolders containing audio files, concatenates
each folder into a single audiobook file using FFmpeg, verifies the output
against its sources, and optionally deletes those sources.

Two rules shape everything below:

1.  The default output must play on an iPhone. That means AAC-LC in an MP4
    container -- see PROFILES. Other targets are offered explicitly rather
    than guessed at.
2.  Nothing is deleted until the output has been proven to match the sources.
    "Proven" means the expected codec, the same total duration, and a full
    decode with no errors -- not merely a positive duration, which a truncated
    or half-empty file reports just as happily.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache, partial
from typing import List, Optional, Sequence

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
VERSION = "2.0"
FILE_PATH = os.path.abspath(__file__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Every container an audiobook actually arrives in. `.m4b`, `.m4a` and `.opus`
# used to be missing, which meant a folder holding several .m4b parts was not
# merely skipped -- it never entered the task list at all, so nothing was
# reported and the book was silently left unjoined.
EXTENSIONS: tuple[str, ...] = (
    ".mp3", ".m4a", ".m4b", ".mp4", ".aac", ".opus", ".ogg", ".oga",
    ".flac", ".wav", ".wma", ".aiff", ".aif",
)

log = logging.getLogger("ab_encode")


# ---------------------------------------------------------------------------
# Output profiles
# ---------------------------------------------------------------------------
# One table, read by both front ends, so the CLI and the GUI cannot drift into
# offering different encoders. Each entry is a complete recipe: container,
# codec, and the flags that make the result actually play on the hardware
# named in `plays_on`.
#
# The default is deliberately the most compatible rather than the most
# efficient. AAC-LC in an MP4 container is the only format that plays natively
# on iPhone/iPad/Apple Books *and* Android *and* Audiobookshelf *and* CarPlay,
# so a library encoded with it stays portable to whatever player comes next.
# Opus is markedly smaller at matching speech quality, but Apple has never
# shipped an Opus decoder, so it is an explicit Android choice, not a default.


@dataclass(frozen=True)
class EncodeProfile:
    """A complete, self-contained ffmpeg output recipe."""

    key: str
    label: str
    codec: str                      # ffmpeg encoder name, or "copy" to remux
    extension: str                  # output suffix, including the dot
    container: str                  # ffmpeg -f value
    default_bitrate: str
    bitrates: tuple[str, ...]
    sample_rate: Optional[str]      # None = keep the source rate
    # Flags the *encoder* understands. They must never reach a -c:a copy
    # command: "-profile:a aac_low" alongside "copy" makes ffmpeg try to
    # evaluate aac_low as an expression and abort with exit 234.
    encoder_flags: tuple[str, ...] = ()
    # Flags the *muxer* understands, so they apply whether we encode or copy.
    muxer_flags: tuple[str, ...] = ()
    supports_chapters: bool = False
    plays_on: str = ""
    note: str = ""

    @property
    def needs_encoder(self) -> Optional[str]:
        """The ffmpeg encoder that must be compiled in, if any."""
        return None if self.codec == "copy" else self.codec

    @property
    def probe_codec(self) -> Optional[str]:
        """The codec name ffprobe reports for this profile's output."""
        return {"aac": "aac", "libopus": "opus", "libmp3lame": "mp3"}.get(self.codec)


PROFILES: dict[str, EncodeProfile] = {
    # -- the default --------------------------------------------------------
    "iphone": EncodeProfile(
        key="iphone",
        label="iPhone / universal - AAC-LC .m4b",
        codec="aac",
        extension=".m4b",
        container="mp4",
        default_bitrate="64k",
        bitrates=("32k", "48k", "64k", "96k", "128k"),
        # 44.1 kHz is the safe universal rate and far above what speech needs;
        # it is also what the previous hard-coded pipeline used.
        sample_rate="44100",
        # aac_low names AAC-LC explicitly. ffmpeg's native encoder only does LC
        # today, but saying so means a future encoder swap (libfdk_aac) cannot
        # silently start emitting HE-AAC, which older iPods and a fair number
        # of car head units refuse to play.
        encoder_flags=("-profile:a", "aac_low"),
        muxer_flags=("-movflags", "+faststart"),
        supports_chapters=True,
        plays_on="iPhone, iPad, Apple Books, Android, Audiobookshelf, CarPlay",
        note="The portable choice: encode once, play anywhere.",
    ),
    # -- Android ------------------------------------------------------------
    "android-aac": EncodeProfile(
        key="android-aac",
        label="Android - AAC-LC .m4a",
        codec="aac",
        extension=".m4a",
        container="mp4",
        default_bitrate="64k",
        bitrates=("32k", "48k", "64k", "96k", "128k"),
        sample_rate="44100",
        encoder_flags=("-profile:a", "aac_low"),
        muxer_flags=("-movflags", "+faststart"),
        supports_chapters=True,
        plays_on="Android (including players that do not index .m4b), iPhone",
        note="Identical audio to the iPhone profile; only the suffix differs. "
             "Use it when an Android player or media scanner ignores .m4b.",
    ),
    "android-opus": EncodeProfile(
        key="android-opus",
        label="Android - Opus .opus (smallest)",
        codec="libopus",
        extension=".opus",
        container="ogg",
        default_bitrate="32k",
        bitrates=("24k", "32k", "48k", "64k"),
        # Opus resamples everything to 48 kHz internally, so asking for another
        # rate only adds a pointless resample.
        sample_rate="48000",
        encoder_flags=("-vbr", "on", "-application", "voip"),
        supports_chapters=False,
        plays_on="Android 5+, Audiobookshelf, VLC, Plex - NOT iPhone",
        note="Roughly half the size of AAC at matching speech quality. Apple "
             "ships no Opus decoder, and Ogg carries no MP4 chapter atom, so "
             "the result has no chapter marks.",
    ),
    # -- the long tail ------------------------------------------------------
    "mp3": EncodeProfile(
        key="mp3",
        label="Universal MP3 .mp3 (old hardware)",
        codec="libmp3lame",
        extension=".mp3",
        container="mp3",
        default_bitrate="64k",
        bitrates=("32k", "48k", "64k", "96k", "128k"),
        sample_rate="44100",
        supports_chapters=False,
        plays_on="anything with a decoder, including pre-2010 car stereos",
        note="Least efficient, most universally understood. One long MP3 has "
             "no chapters and many players resume it badly.",
    ),
    "copy": EncodeProfile(
        key="copy",
        label="Join without re-encoding (.m4b)",
        codec="copy",
        extension=".m4b",
        container="mp4",
        default_bitrate="",
        bitrates=(),
        sample_rate=None,
        muxer_flags=("-movflags", "+faststart"),
        supports_chapters=True,
        plays_on="whatever already played the sources",
        note="Lossless and fast, but only valid when every source is AAC at "
             "one sample rate and channel count. Refused otherwise, because "
             "the concat demuxer would emit a garbled stream.",
    ),
}

DEFAULT_PROFILE = "iphone"

#: Ordered for menus: the default first, then by how likely you are to want it.
PROFILE_ORDER: tuple[str, ...] = (
    "iphone", "android-aac", "android-opus", "mp3", "copy",
)


def profile_labels() -> list[str]:
    """Combobox values, in menu order."""
    return [PROFILES[k].label for k in PROFILE_ORDER]


def profile_for_label(label: str) -> EncodeProfile:
    """Reverse of :func:`profile_labels`, tolerant of an unknown label."""
    for key in PROFILE_ORDER:
        if PROFILES[key].label == label:
            return PROFILES[key]
    return PROFILES[DEFAULT_PROFILE]


# ---------------------------------------------------------------------------
# ffmpeg capability probing
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def available_encoders() -> frozenset[str]:
    """Encoder names this ffmpeg build actually has.

    Builds vary wildly -- libopus and libmp3lame are common but not
    guaranteed, and libfdk_aac is usually absent for licensing reasons. Asking
    up front lets the UI grey a profile out instead of failing mid-run.
    """
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names: set[str] = set()
    for line in out.splitlines():
        # " A....D libopus              libopus Opus (codec opus)"
        match = re.match(r"^\s*[A-Z.]{6}\s+(\S+)", line)
        if match:
            names.add(match.group(1))
    return frozenset(names)


def profile_available(profile: EncodeProfile) -> tuple[bool, str]:
    """Whether this ffmpeg build can produce *profile*, and why not if it cannot."""
    needed = profile.needs_encoder
    if needed is None:
        return True, ""
    encoders = available_encoders()
    if not encoders:
        # Could not ask; assume yes rather than block the run outright.
        return True, ""
    if needed in encoders:
        return True, ""
    return False, f"this ffmpeg build has no '{needed}' encoder"


def _check_tools() -> None:
    """Abort early with a clear message if ffmpeg or ffprobe are not on PATH."""
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        sys.exit(
            f"[X] Missing required tool(s): {', '.join(missing)}. "
            "Install FFmpeg and ensure it is on PATH."
        )


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

def natural_sort_key(s: str) -> List[int | str]:
    """Sort key that orders '2' before '10' (numeric-aware)."""
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", s)]


#: How much larger than its own audio a file may be before we call it padding.
#: Measured over a real 353-file library: every healthy file scored exactly
#: 1.000, so 3.0 is a wide moat. Cover art and container overhead push a
#: legitimate file to perhaps 1.2; a stalled download scores 10 or more.
PADDING_RATIO_LIMIT = 3.0

#: A run of NUL bytes this long at the head of a file means it was
#: preallocated and never filled. No audio container opens with 64 KiB of
#: zeros, so this needs no tolerance.
NULL_HEAD_BYTES = 1 << 16


@dataclass(frozen=True)
class Probe:
    """What ffprobe could establish about one audio file."""

    path: str
    duration: Optional[float]       # None when it could not be determined
    codec: str
    sample_rate: int
    channels: int
    title: str
    size: int = 0
    bit_rate: int = 0               # stream bitrate, 0 when unreported
    null_head: int = 0              # NUL bytes at the very start of the file

    @property
    def padding_ratio(self) -> Optional[float]:
        """File size over the size its own audio should occupy.

        The check that catches a part-download ffmpeg *can* partly read. Such
        a file reports a plausible codec, sample rate and a short duration --
        everything looks fine -- but the bytes on disk far exceed what that
        duration needs, because most of the file is padding ffmpeg skipped
        over. Nothing about the probe alone reveals it.
        """
        if not (self.duration and self.bit_rate and self.size):
            return None
        expected = self.duration * self.bit_rate / 8
        return self.size / expected if expected > 0 else None

    @property
    def damage(self) -> str:
        """Why this file is not safe to encode from. Empty when it is fine."""
        if self.null_head >= NULL_HEAD_BYTES:
            return f"starts with {self.null_head // 1024} KiB of zero bytes"
        if self.duration is None or self.duration <= 0:
            return "no readable duration"
        if self.sample_rate <= 0 or self.channels <= 0:
            return "no decodable audio stream"
        ratio = self.padding_ratio
        if ratio is not None and ratio > PADDING_RATIO_LIMIT:
            return (f"only {100 / ratio:.0f}% of the file is audio "
                    f"({self.duration:.4g}s of sound in "
                    f"{self.size / 1e6:.4g} MB) -- a part-finished download")
        return ""

    @property
    def readable(self) -> bool:
        """A file we are willing to feed to the encoder.

        A file that fails here is, in practice, a truncated or part-written
        download. ffmpeg will happily emit near-silence for it and still
        return success, so the refusal has to happen before the encode.
        """
        return not self.damage


def _ffprobe_fields(path: str, *, thorough: bool) -> dict[str, str]:
    cmd = ["ffprobe", "-v", "error"]
    if thorough:
        # Variable-bitrate MP3s without a Xing header need a real look before
        # ffprobe will commit to a duration. Cheap enough as a second attempt,
        # too slow to make the default.
        cmd += ["-analyzeduration", "100M", "-probesize", "100M"]
    cmd += [
        "-select_streams", "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,duration,bit_rate"
        ":format=duration,size"
        ":format_tags=title",
        "-of", "default=nw=1",
        path,
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=180
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    fields: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if value and value != "N/A":
            # The stream duration is printed before the format duration; the
            # first non-empty one wins.
            fields.setdefault(key.strip(), value)
    return fields


def _null_head(path: str, window: int = NULL_HEAD_BYTES) -> int:
    """Count the NUL bytes at the very start of the file, up to *window*.

    One small read, no subprocess. It is the only signal that survives when
    ffprobe cannot describe the file at all.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(window)
    except OSError:
        return 0
    stripped = head.lstrip(b"\x00")
    return len(head) - len(stripped)


def probe(path: str) -> Probe:
    """Describe one audio file, retrying harder before giving up on duration."""
    fields = _ffprobe_fields(path, thorough=False)
    if "duration" not in fields:
        fields = {**_ffprobe_fields(path, thorough=True), **fields}

    def _num(key, cast, default):
        try:
            return cast(fields[key])
        except (KeyError, TypeError, ValueError):
            return default

    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0

    return Probe(
        path=path,
        duration=_num("duration", float, None),
        codec=fields.get("codec_name", ""),
        sample_rate=_num("sample_rate", int, 0),
        channels=_num("channels", int, 0),
        title=fields.get("TAG:title", "") or fields.get("tag:title", ""),
        size=size,
        bit_rate=_num("bit_rate", int, 0),
        null_head=_null_head(path),
    )


def verify_audio(file_path: str) -> bool:
    """Return True when ffprobe confirms a valid audio stream with duration.

    Kept as the shallow smoke test it always was. It is *not* sufficient to
    authorise deleting anything -- see :func:`verify_output`.
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False
    result = probe(file_path)
    return result.duration is not None and result.duration > 0


def is_aac_codec(file_path: str) -> bool:
    """Return True if the primary audio stream is encoded as AAC."""
    return probe(file_path).codec.lower() == "aac"


def decodes_cleanly(file_path: str, *, timeout: int = 3600) -> tuple[bool, str]:
    """Decode the whole file and report whether ffmpeg complained.

    The exit code cannot carry this on its own: ffmpeg returns 0 after
    printing "Error submitting packet to decoder" and dropping the packet, so
    a book with four unreadable chapters still "succeeds". An empty stderr at
    -v error is the reliable signal, and -xerror makes it stop at the first
    problem instead of grinding through the rest of a seven-hour file.
    """
    cmd = ["ffmpeg", "-v", "error", "-xerror", "-i", file_path, "-f", "null", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "decode timed out"
    except OSError as exc:
        return False, f"could not run ffmpeg ({exc})"
    noise = result.stderr.strip()
    if result.returncode != 0:
        return False, (noise.splitlines() or ["ffmpeg exited non-zero"])[0][:200]
    if noise:
        return False, noise.splitlines()[0][:200]
    return True, ""


def duration_tolerance(expected: float) -> float:
    """How far the output may drift from the sum of its sources, in seconds.

    Encoder priming and per-file join rounding add a fraction of a second
    each, so the floor absorbs those. The cap keeps the window far below one
    chapter on a long book, which is the mistake actually worth catching.
    """
    return max(4.0, min(60.0, expected * 0.005))


def verify_output(
    path: str,
    *,
    expected_duration: Optional[float],
    profile: EncodeProfile,
    deep: bool,
) -> tuple[bool, str]:
    """Prove the encode is complete and playable. Returns (ok, reason).

    This gates both replacing the previous output and deleting any source, so
    it fails closed: anything it cannot establish counts as a failure.
    """
    if not os.path.exists(path):
        return False, "output was not created"
    if os.path.getsize(path) == 0:
        return False, "output is empty"

    result = probe(path)
    if result.duration is None or result.duration <= 0:
        return False, "output has no readable duration"
    if result.channels <= 0 or result.sample_rate <= 0:
        return False, "output has no decodable audio stream"

    want_codec = profile.probe_codec
    if want_codec and result.codec.lower() != want_codec:
        return False, f"output is {result.codec or 'unknown'}, expected {want_codec}"

    if expected_duration is not None and expected_duration > 0:
        drift = abs(result.duration - expected_duration)
        allowed = duration_tolerance(expected_duration)
        if drift > allowed:
            return False, (
                f"length is {result.duration / 60:.1f} min but the sources total "
                f"{expected_duration / 60:.1f} min (off by {drift:.0f}s, "
                f"tolerance {allowed:.0f}s)"
            )

    if deep:
        ok, why = decodes_cleanly(path)
        if not ok:
            return False, f"full decode failed: {why}"

    return True, ""


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------

def _escape_ffmetadata(text: str) -> str:
    """Escape the characters ffmetadata treats as syntax."""
    for char in ("\\", "=", ";", "#"):
        text = text.replace(char, "\\" + char)
    return text.replace("\n", " ").strip()


def build_chapter_metadata(probes: Sequence[Probe], *, title: str) -> str:
    """An ffmetadata document marking one chapter per source file.

    An M4B with no chapter marks is a single seven-hour blob: Apple Books and
    most Android players show no chapter list and resume badly. The sources
    are already one file per chapter, so the marks cost nothing to derive.
    """
    lines = [";FFMETADATA1", f"title={_escape_ffmetadata(title)}"]
    start_ms = 0
    for item in probes:
        if item.duration is None:
            continue
        end_ms = start_ms + int(round(item.duration * 1000))
        if end_ms <= start_ms:
            continue
        label = item.title.strip() or os.path.splitext(os.path.basename(item.path))[0]
        lines += [
            "",
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={_escape_ffmetadata(label)}",
        ]
        start_ms = end_ms
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Core encoder
# ---------------------------------------------------------------------------

def _can_stream_copy(probes: Sequence[Probe]) -> tuple[bool, str]:
    """Whether the sources may be concatenated with -c:a copy.

    The concat demuxer does not re-negotiate stream parameters between files.
    Copying across a sample-rate or channel-count change yields output that
    plays at the wrong speed from the switch onwards, so matching parameters
    are as much a precondition as a matching codec.
    """
    if not probes:
        return False, "no sources"
    codecs = {p.codec.lower() for p in probes}
    if codecs != {"aac"}:
        return False, f"sources are {', '.join(sorted(codecs)) or 'unknown'}, not all AAC"
    rates = {p.sample_rate for p in probes}
    if len(rates) > 1:
        return False, "sources mix sample rates (" + ", ".join(str(r) for r in sorted(rates)) + ")"
    channels = {p.channels for p in probes}
    if len(channels) > 1:
        return False, "sources mix channel counts (" + ", ".join(str(c) for c in sorted(channels)) + ")"
    return True, ""


def _already_in_target_format(item: Probe, profile: EncodeProfile) -> bool:
    """True when a lone source is already exactly what we would produce.

    Readability is part of the question. The copy profile targets any codec,
    so without this a single damaged .m4b would be reported as finished work
    rather than as the broken file it is.
    """
    if not item.readable:
        return False
    if os.path.splitext(item.path)[1].lower() != profile.extension:
        return False
    want = profile.probe_codec
    if want is None:                       # the copy profile targets any codec
        return True
    return item.codec.lower() == want


def process_folder(
    root: str,
    *,
    bitrate: str = "",
    channels: str = "1",
    cleanup: bool = False,
    profile: "EncodeProfile | str" = DEFAULT_PROFILE,
    chapters: bool = True,
    skip_unreadable: bool = False,
    deep_verify: Optional[bool] = None,
) -> dict[str, str]:
    """Encode all audio files in *root* into a single audiobook file.

    Returns a result dict with keys ``status`` and ``folder``; ``detail``
    carries the reason whenever something was skipped or refused.

    ``deep_verify`` defaults to *cleanup*: a full decode is mandatory before
    any source is deleted, and optional otherwise because it roughly doubles
    the wall time of an encode.
    """
    if isinstance(profile, str):
        profile = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
    # A stale settings file should not crash a worker thread mid-run.
    channels = channels if channels in ("1", "2") else "1"
    if deep_verify is None:
        deep_verify = cleanup
    if cleanup and not deep_verify:
        # Not negotiable: deleting the only copy of the audio on the strength
        # of an unverified file is the one mistake with no way back.
        deep_verify = True

    folder_name = os.path.basename(os.path.abspath(root))
    output_name = f"{folder_name}{profile.extension}"
    output_path = os.path.abspath(os.path.join(root, output_name))

    ok, why = profile_available(profile)
    if not ok:
        return {"status": "[X] Unavailable", "folder": folder_name, "detail": why}

    try:
        contents = os.listdir(root)
    except OSError as exc:
        return {"status": "[X] Unreadable folder", "folder": folder_name,
                "detail": str(exc)}

    # The file we are about to write is never one of its own sources. Compared
    # case-insensitively because a case-folding filesystem would otherwise let
    # "Book.M4B" become an input to "Book.m4b".
    lowered_output = output_name.lower()
    sources = sorted(
        (f for f in contents
         if f.lower().endswith(EXTENSIONS) and f.lower() != lowered_output),
        key=natural_sort_key,
    )
    if not sources:
        if not os.path.exists(output_path):
            return {"status": "[>] Skipped (empty)", "folder": folder_name}
        # There is nothing to rebuild from, so the existing output is all the
        # audio that remains. Say so if it is damaged rather than reporting it
        # as finished work -- an interrupted earlier run leaves exactly this.
        existing = probe(output_path)
        if not existing.readable:
            return {"status": "[!] Existing output is damaged",
                    "folder": folder_name,
                    "detail": f"{output_name} ({existing.damage}); no sources left "
                              "to rebuild from"}
        return {"status": "[>] Skipped (already encoded)", "folder": folder_name}

    probes = [probe(os.path.join(root, name)) for name in sources]

    # A single file that is already exactly what we would produce is finished
    # work, whatever it happens to be called.
    if len(probes) == 1 and _already_in_target_format(probes[0], profile):
        return {
            "status": "[>] Skipped (already encoded)",
            "folder": folder_name,
            "detail": os.path.basename(probes[0].path),
        }

    unreadable = [p for p in probes if not p.readable]
    if unreadable:
        # Name the files and say what is wrong with each, so the fix is
        # obvious without re-running anything by hand.
        listed = sorted(unreadable, key=lambda p: p.path)[:3]
        names = "; ".join(f"{os.path.basename(p.path)} ({p.damage})" for p in listed)
        if len(unreadable) > 3:
            names += f"; +{len(unreadable) - 3} more"
        if not skip_unreadable:
            # Refusing beats producing a book quietly missing chapters and
            # then reporting success over it.
            return {
                "status": "[X] Refused (damaged sources)",
                "folder": folder_name,
                "detail": f"{len(unreadable)} of {len(probes)} unreadable: {names}",
            }
        log.warning("%s: skipping %d unreadable source(s): %s",
                    folder_name, len(unreadable), names)
        probes = [p for p in probes if p.readable]
        if not probes:
            return {"status": "[X] Refused (damaged sources)", "folder": folder_name,
                    "detail": "every source is unreadable"}
        # Sources were dropped, so the output cannot be a faithful copy of the
        # folder; deleting the originals is off the table whatever the flags say.
        cleanup = False

    expected_duration = sum(p.duration or 0.0 for p in probes)

    if profile.codec == "copy":
        can_copy, why = _can_stream_copy(probes)
        if not can_copy:
            return {"status": "[X] Refused (cannot stream-copy)",
                    "folder": folder_name, "detail": why}
        audio_flags: list[str] = ["-c:a", "copy", *profile.muxer_flags]
    else:
        # Smart passthrough: when the sources are already exactly the codec and
        # parameters we would produce, re-encoding only loses quality and time.
        can_copy, _ = _can_stream_copy(probes)
        same_target = (
            profile.probe_codec == "aac"
            and can_copy
            and (profile.sample_rate is None
                 or probes[0].sample_rate == int(profile.sample_rate))
            and probes[0].channels == int(channels)
        )
        if same_target:
            log.info("Smart passthrough for '%s': streams copied losslessly.", root)
            # Muxer flags only. Encoder flags would be handed to a command with
            # no encoder in it.
            audio_flags = ["-c:a", "copy", *profile.muxer_flags]
        else:
            audio_flags = ["-c:a", profile.codec]
            if bitrate:
                audio_flags += ["-b:a", bitrate]
            audio_flags += ["-ac", channels]
            if profile.sample_rate:
                audio_flags += ["-ar", profile.sample_rate]
            audio_flags += [*profile.encoder_flags, *profile.muxer_flags]

    temp_output_path = output_path + ".tmp"
    scratch: list[str] = []

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", dir=root, delete=False, encoding="utf-8"
        ) as tmp:
            scratch.append(tmp.name)
            list_file = tmp.name
            for item in probes:
                safe = os.path.abspath(item.path).replace("'", "'\\''")
                tmp.write(f"file '{safe}'\n")

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
        ]

        want_chapters = chapters and profile.supports_chapters and len(probes) > 1
        if want_chapters:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".ffmeta", dir=root, delete=False, encoding="utf-8"
            ) as meta:
                scratch.append(meta.name)
                meta.write(build_chapter_metadata(probes, title=folder_name))
            cmd += ["-i", meta.name, "-map", "0:a", "-map_metadata", "1"]
        else:
            cmd += ["-map", "0:a"]

        cmd += [
            *audio_flags,
            "-vn",              # ignore embedded cover art, which crashes encoders
            "-threads", "1",    # we are already inside a ThreadPoolExecutor
            "-metadata", f"title={folder_name}",
            "-f", profile.container,
            temp_output_path,
        ]

        # stderr is captured, not discarded: it is the only place ffmpeg
        # explains itself, and the previous version threw it away.
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            first = (result.stderr.strip().splitlines() or ["no output"])[0]
            return {"status": "[X] Encoding error", "folder": folder_name,
                    "detail": first[:300], "error_code": str(result.returncode)}

        ok, why = verify_output(
            temp_output_path,
            expected_duration=expected_duration,
            profile=profile,
            deep=deep_verify,
        )
        if not ok:
            return {"status": "[!] Verification failed", "folder": folder_name,
                    "detail": why}

        os.replace(temp_output_path, output_path)

        if not cleanup:
            return {"status": "[OK] Success (sources kept)", "folder": folder_name}

        # Verified above; confirm once more that what we are keeping is still
        # on disk before removing the only other copy of the audio.
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {"status": "[!] Verification failed", "folder": folder_name,
                    "detail": "output vanished after verification; sources kept"}

        failed: List[str] = []
        for item in probes:
            path = os.path.abspath(item.path)
            if path == output_path:
                continue
            try:
                os.remove(path)
            except OSError as exc:
                failed.append(f"{os.path.basename(path)} ({exc})")
        if failed:
            log.warning("Could not delete: %s", ", ".join(failed))
            return {"status": "[!] Success (some sources not deleted)",
                    "folder": folder_name, "detail": ", ".join(failed)[:300]}
        return {"status": "[OK] Success & sources deleted", "folder": folder_name}

    except OSError as exc:
        return {"status": "[X] Encoding error", "folder": folder_name, "detail": str(exc)}

    finally:
        # The temp output only survives to here when something went wrong.
        if os.path.exists(temp_output_path):
            try:
                os.remove(temp_output_path)
            except OSError:
                pass
        for path in scratch:
            try:
                os.remove(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _profile_help() -> str:
    lines = []
    for key in PROFILE_ORDER:
        item = PROFILES[key]
        mark = "  (default)" if key == DEFAULT_PROFILE else ""
        lines.append(
            f"  {key}{mark}\n"
            f"      {item.label}\n"
            f"      plays on: {item.plays_on}\n"
            f"      {item.note}"
        )
    return "output profiles:\n" + "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audiobook builder with auto-verification and cleanup.",
        epilog=_profile_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Optional so --list-profiles works on its own.
    parser.add_argument(
        "directory", nargs="?",
        help="Root directory containing audiobook sub-folders.",
    )
    parser.add_argument(
        "-p", "--profile", default=DEFAULT_PROFILE, choices=list(PROFILE_ORDER),
        help="Output format (default: %(default)s -- AAC-LC .m4b, plays on iPhone "
             "and everything else).",
    )
    parser.add_argument(
        "-b", "--bitrate", default=None,
        help="Encoder bitrate, e.g. 64k. Defaults to the profile's own.",
    )
    parser.add_argument(
        "-c", "--channels", default="1", choices=["1", "2"],
        help="Audio channels: 1=mono, 2=stereo (default: %(default)s).",
    )
    parser.add_argument(
        "-w", "--workers", type=int, default=4,
        help="Parallel encoding workers (default: %(default)s).",
    )
    parser.add_argument(
        "--no-chapters", action="store_true",
        help="Do not write one chapter mark per source file.",
    )
    parser.add_argument(
        "--skip-unreadable", action="store_true",
        help="Encode a folder even when some sources cannot be decoded, leaving "
             "them out. Forces cleanup off for that folder.",
    )
    parser.add_argument(
        "--deep-verify", action="store_true",
        help="Fully decode each output to prove it is not corrupt. Implied by "
             "--cleanup, which will not delete anything without it.",
    )
    parser.add_argument(
        "--cleanup", action="store_true",
        help="DANGER: delete source audio after the output is fully verified.",
    )
    parser.add_argument(
        "--list-profiles", action="store_true",
        help="Print the output profiles this ffmpeg build can produce, and exit.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{VERSION} ({FILE_PATH})",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug-level logging.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    _check_tools()

    if args.list_profiles:
        for key in PROFILE_ORDER:
            item = PROFILES[key]
            ok, why = profile_available(item)
            mark = "*" if key == DEFAULT_PROFILE else " "
            state = "available" if ok else f"UNAVAILABLE - {why}"
            print(f"{mark} {key:<14} {item.label:<34} {state}")
            print(f"    plays on: {item.plays_on}")
        return

    if not args.directory:
        parser.error("the following arguments are required: directory")

    profile = PROFILES[args.profile]
    ok, why = profile_available(profile)
    if not ok:
        sys.exit(f"[X] Profile '{args.profile}' is not usable: {why}")

    bitrate = args.bitrate if args.bitrate is not None else profile.default_bitrate

    target_dir = os.path.abspath(args.directory)
    if not os.path.isdir(target_dir):
        sys.exit(f"[X] Error: Directory '{target_dir}' does not exist.")

    tasks: List[str] = []
    for root, _, files in os.walk(target_dir):
        if any(f.lower().endswith(EXTENSIONS) for f in files):
            tasks.append(root)

    if not tasks:
        print("No audio files found. Nothing to do.")
        return

    deep = args.deep_verify or args.cleanup
    print(f"Processing: {target_dir}")
    print(f"Profile: {profile.label}  ->  plays on {profile.plays_on}")
    print(
        f"Folders: {len(tasks)} | Workers: {args.workers} | "
        f"Bitrate: {bitrate or 'n/a'} | Deep verify: {'ON' if deep else 'off'} | "
        f"Cleanup: {'ON (deletes sources)' if args.cleanup else 'off'}"
    )

    worker_func = partial(
        process_folder,
        profile=profile,
        bitrate=bitrate,
        channels=args.channels,
        cleanup=args.cleanup,
        chapters=not args.no_chapters,
        skip_unreadable=args.skip_unreadable,
        deep_verify=deep,
    )

    results: list[dict[str, str]] = []

    # Map futures back to folder names so we can label the bar
    future_to_folder: dict[Future[dict[str, str]], str] = {}
    active_futures: set[Future[dict[str, str]]] = set()
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for task in tasks:
            future = executor.submit(worker_func, task)
            future_to_folder[future] = os.path.basename(task)
            active_futures.add(future)

        if tqdm is not None:
            bar = tqdm(
                total=len(tasks),
                unit="folder",
                dynamic_ncols=True,
                smoothing=0.1,  # heavily weight recent slow encodes, ignore initial fast skips
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            )

            # Background thread to keep the progress bar description lively
            stop_monitor = threading.Event()

            def monitor_progress() -> None:
                while not stop_monitor.is_set():
                    with lock:
                        running = [future_to_folder[f][:20] for f in active_futures if f.running()]
                    if running:
                        # Show up to 3 currently running items
                        desc = ", ".join(running[:3])
                        if len(running) > 3:
                            desc += "..."
                        bar.set_description(desc)
                    time.sleep(0.5)

            monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
            monitor_thread.start()
        else:
            bar = None

        done = 0
        try:
            for future in as_completed(future_to_folder):
                folder_name = future_to_folder[future]
                result = future.result()
                results.append(result)
                done += 1

                if "error_code" in result:
                    log.error("FFmpeg failed for '%s': %s", folder_name,
                              result.get("detail", result["error_code"]))

                if bar is not None:
                    with lock:
                        active_futures.remove(future)
                    bar.update(1)
                else:
                    detail = f" -- {result['detail']}" if result.get("detail") else ""
                    print(f"  [{done}/{len(tasks)}] {result['status']} - {folder_name}{detail}")

        except KeyboardInterrupt:
            if bar is not None:
                stop_monitor.set()
                monitor_thread.join(timeout=1.0)
                bar.set_description("Cancelled")
                bar.close()
            print("\nEncoding interrupted by user (Ctrl+C). Shutting down...")
            # Cancel any pending futures that haven't started yet
            executor.shutdown(wait=False, cancel_futures=True)
            sys.exit(130)

        finally:
            if bar is not None and not stop_monitor.is_set():
                stop_monitor.set()
                monitor_thread.join(timeout=1.0)
                bar.set_description("Done")
                bar.close()

    # Group results by status
    summary: dict[str, List[str]] = defaultdict(list)
    for res in results:
        label = res["folder"]
        if res.get("detail"):
            label += f"  -- {res['detail']}"
        summary[res["status"]].append(label)

    print("\nFINAL EXECUTION REPORT:")
    print("-" * 40)
    for status, folders in sorted(summary.items()):
        print(f"\n  {status} ({len(folders)}):")
        for folder in folders:
            print(f"    - {folder}")
    print()


if __name__ == "__main__":
    main()
