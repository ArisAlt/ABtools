"""Provider query quality -- the layer that decides how often the LLM is needed.

Measured against a real library (Nora Ashcroft, 15 books laid out as
<Author>/<Series (years)>/<N - Title (Year)>): before these changes 14 of 15
books scored below the 85 threshold and went to the LLM, and three of those
picked the *wrong* book. After, all 15 score 100 from the providers alone.

Nothing here touches the network: the provider helpers are stubbed, so what is
under test is the query construction, scoring and parsing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ablib.metadata.utils import guess_from_path, split_parent_series  # noqa: E402
from ablib.providers import http as P  # noqa: E402


@pytest.fixture(autouse=True)
def _clear():
    P.clear_cache()
    yield
    P.clear_cache()


# ── query hygiene ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Daughter of the Dominion 128kbps", "Daughter of the Dominion"),   # matched nothing before
        ("Sorcerers End (Unabridged)", "Sorcerers End"),                # scored 45 before
        ("The Last Dominion [Audiobook]", "The Last Dominion"),
        ("Rage of a Fallen King - 01 of 14", "Rage of a Fallen King"),
        ("The Big Switch (2011)", "The Big Switch"),
        ("West and East (20109", "West and East"),                      # real folder, real typo
        ("A Tale of Two Cities", "A Tale of Two Cities"),
        ("Catch 22", "Catch 22"),
    ],
)
def test_query_titles_are_cleaned(raw, expected):
    assert P.clean_query_title(raw) == expected


# ── series carried inline by catalogues ─────────────────────────────────────

@pytest.mark.parametrize(
    "raw, title, series, index",
    [
        ("Nightthorn (The Ember Saga, #3)", "Nightthorn", "The Ember Saga", "3"),
        ("Down to Earth (Colonization, Book 2)", "Down to Earth", "Colonization", "2"),
        ("Tipping the Brink (Ashfall Series, Volume 2)",
         "Tipping the Brink", "Ashfall", "2"),
        ("Hitler's War (the War That Came Early, Book One)",
         "Hitler's War", "the War That Came Early", "1"),
    ],
)
def test_inline_series_is_lifted_out_of_the_title(raw, title, series, index):
    assert P.split_series_suffix(raw) == (title, series, index)


@pytest.mark.parametrize(
    "raw", ["The Hitchhikers Guide (Radio Play)", "Something (A Novel)", "Winter Tale"]
)
def test_a_plain_parenthetical_is_not_a_series(raw):
    assert P.split_series_suffix(raw) == (raw, None, None)


def test_edition_tail_is_stripped_only_when_it_names_the_author():
    assert P.strip_edition_tail(
        "Ashfall: Breaking the Brink by Nora Ashcroft (1996-12-05)",
        ["Nora Ashcroft"],
    ) == "Ashfall: Breaking the Brink"
    # a title that genuinely contains "by" survives
    assert P.strip_edition_tail("Death by Black Hole", ["Neil deGrasse Tyson"]) \
        == "Death by Black Hole"


# ── scoring ─────────────────────────────────────────────────────────────────

def test_a_perfect_title_scores_full_marks_without_a_known_author():
    """The regression that drove everything to the LLM: fixed weights meant a
    perfect title with no author scored 100*0.7 = 70, under the 85 threshold."""
    hit = {"title": "Rage of a Fallen King", "authors": ["Alex E. Rivers"]}
    assert P.score_candidate(hit, "Rage of a Fallen King", None) == 100
    assert P.score_candidate(hit, "Rage of a Fallen King", "Alex E. Rivers") == 100


def test_a_wrong_author_still_costs_the_candidate():
    hit = {"title": "The Long Return", "authors": ["Dana Whitlock"]}
    right = {"title": "The Long Return", "authors": ["Nora Ashcroft"]}
    assert P.score_candidate(hit, "The Long Return", "Nora Ashcroft") \
        < P.score_candidate(right, "The Long Return", "Nora Ashcroft")


def test_series_agreement_lifts_a_candidate():
    with_series = {"title": "Nightthorn", "authors": ["Rivers"], "series": "Ember Saga"}
    without = {"title": "Nightthorn", "authors": ["Rivers"], "series": "Something Else"}
    assert P.score_candidate(with_series, "Nightthorn", "Rivers", "Ember Saga") \
        > P.score_candidate(without, "Nightthorn", "Rivers", "Ember Saga")


# ── the folder tree the query is built from ─────────────────────────────────

def test_series_folder_is_not_mistaken_for_the_author(tmp_path):
    """<Author>/<Series (years)>/<N - Title (Year)> -- the immediate-parent rule
    sent "Ashfall - Reckoning" to the catalogues as an author, which
    suppressed every correct hit and let unrelated books outrank them."""
    book = tmp_path / "Nora Ashcroft" / "Ashfall - Reckoning (1994-2004)" / "8 - The Long Return (2004)"
    book.mkdir(parents=True)
    author, title, year, series, index = guess_from_path(book)
    assert author == "Nora Ashcroft"
    assert title == "The Long Return"
    assert year == "2004"
    assert series == "Ashfall - Reckoning"
    assert index == "8"


def test_author_folder_without_a_series_level(tmp_path):
    book = tmp_path / "Nora Ashcroft" / "Through Darkest Winter (2018)"
    book.mkdir(parents=True)
    author, title, year, series, _ = guess_from_path(book)
    assert (author, title, year, series) == ("Nora Ashcroft", "Through Darkest Winter", "2018", None)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Ashfall - Reckoning (1994-2004)", "Ashfall - Reckoning"),
        ("The War That Came Early (2009-2014)", "The War That Came Early"),
        ("Emberborn (2006)", "Emberborn"),
        ("Nora Ashcroft", None),
        ("Some Folder", None),
    ],
)
def test_parent_series_detection(name, expected):
    assert split_parent_series(name) == expected


# ── the ladder and the circuit breaker ──────────────────────────────────────

class _Client:
    def is_on(self, _name, default=True):
        return default


def test_a_confident_first_hit_costs_one_request(monkeypatch):
    calls: list[str] = []

    def gr(author, title):
        calls.append("goodreads")
        return {"title": title, "authors": [author or "X"], "series": None}

    def other(name):
        def fn(author, title):
            calls.append(name)
            return None
        return fn

    monkeypatch.setattr(P, "goodreads", gr)
    for name in ("audible", "openlib", "gbooks"):
        monkeypatch.setattr(P, name, other(name))

    best, _ = P.best_match("Nora Ashcroft", "The Long Return", client=_Client())
    assert best and best[0] >= P.ACCEPT_SCORE
    assert calls == ["goodreads"]


def test_the_ladder_retries_without_the_guessed_author(monkeypatch):
    """An author read off a directory name is a guess; the title rarely is."""
    seen: list[tuple] = []

    def gr(author, title):
        seen.append((author, title))
        if author:                       # the guessed author suppresses the book
            return None
        return {"title": title, "authors": ["Nora Ashcroft"], "series": None}

    monkeypatch.setattr(P, "goodreads", gr)
    for name in ("audible", "openlib", "gbooks"):
        monkeypatch.setattr(P, name, lambda a, t: None)

    best, _ = P.best_match("Wrong Series Name", "The Long Return", client=_Client())
    assert best is not None
    assert best[1]["authors"] == ["Nora Ashcroft"]
    assert (None, "The Long Return") in seen


def test_goodreads_soft_block_stops_being_retried(monkeypatch):
    """Goodreads answers HTTP 202 with an empty body when it throttles, which
    raise_for_status() does not catch. Asking on every book wastes a request."""
    P.clear_cache()
    for _ in range(P._GOODREADS_FAILURE_LIMIT):
        P._note_goodreads(False)
    assert P._goodreads_state["disabled"] is True

    called: list[int] = []
    monkeypatch.setattr(P.SESSION, "get", lambda *a, **k: called.append(1))
    assert P.goodreads("Nora Ashcroft", "The Long Return") is None
    assert called == []                  # not even attempted

    P.clear_cache()
    assert P._goodreads_state["disabled"] is False


def test_results_are_cached_per_query(monkeypatch):
    calls: list[tuple] = []

    def fake_get(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(P.SESSION, "get", fake_get)
    P.openlib("Nora Ashcroft", "The Long Return")
    P.openlib("Nora Ashcroft", "The Long Return")
    assert len(calls) == 1


# ── one threshold, one meaning ──────────────────────────────────────────────

def test_every_match_threshold_is_the_shared_constant():
    """These drifted before: combobook graded on 0-1 with a 0.75 floor while
    the CLI graded on 0-100 with 85, so "the threshold" meant two things."""
    import combobook
    from ablib.core.config import config
    from ablib.core.constants import DEFAULT_MATCH_THRESHOLD

    assert P.ACCEPT_SCORE == DEFAULT_MATCH_THRESHOLD
    assert combobook.MIN_AUTO_SCORE == DEFAULT_MATCH_THRESHOLD
    assert config.llm_fallback_min_score == DEFAULT_MATCH_THRESHOLD


def test_the_mcp_gate_and_its_callers_read_the_same_number():
    """refine_metadata_via_mcp once stopped early at 90 while both callers
    demanded 95, so a stage-1 result scoring 90-94 skipped SequentialThinking
    and was then thrown away. One constant, checked at the call sites."""
    import importlib
    import inspect
    from ablib.core.constants import DEFAULT_MATCH_THRESHOLD
    from ablib.metadata.llm import MCP_ACCEPT_SCORE

    assert MCP_ACCEPT_SCORE == DEFAULT_MATCH_THRESHOLD

    # import_module, not `from ablib.cli import main`: the package re-exports a
    # *function* called main, which shadows the submodule of the same name.
    cli_main = importlib.import_module("ablib.cli.main")

    # No caller may re-inline a literal bar of its own.
    src = inspect.getsource(cli_main)
    assert src.count("MCP_ACCEPT_SCORE") >= 3          # import + both gates
    for line in src.splitlines():
        if 'mcp_meta.get("score"' in line:
            assert "MCP_ACCEPT_SCORE" in line, line


def test_the_threshold_sits_between_the_measured_bands():
    """Right and wrong answers must fall either side of it, or the number is
    decoration. Cases are real results from the audited library."""
    from ablib.core.constants import DEFAULT_MATCH_THRESHOLD as T

    correct = [
        ({"title": "The Long Return", "authors": ["Nora Ashcroft"]},
         "The Long Return", "Nora Ashcroft"),
        ({"title": "Ashfall: On the Brink", "authors": ["Nora Ashcroft"]},
         "On The Brink", "Nora Ashcroft"),
        ({"title": "The Long Return", "authors": ["Nora Ashcroft"]},
         "The Long Return", "Ashcroft"),          # surname only on disk
    ]
    wrong = [
        ({"title": "The Long Return", "authors": ["Dana Whitlock"]},
         "The Long Return", "Nora Ashcroft"),
        ({"title": "Afterlight", "authors": ["Petra Nilsen"]},
         "Afterlight", "Nora Ashcroft"),
        ({"title": "Bells of the South", "authors": ["Nora Ashcroft"]},
         "The Long Return", "Nora Ashcroft"),
    ]
    for hit, title, author in correct:
        assert P.score_candidate(hit, title, author) >= T, (hit, title)
    for hit, title, author in wrong:
        assert P.score_candidate(hit, title, author) < T, (hit, title)


def test_combobook_grades_on_the_same_scale():
    import combobook

    guess = combobook.Meta(author="Nora Ashcroft", title="The Long Return")
    right = combobook.Meta(author="Nora Ashcroft", title="The Long Return")
    wrong = combobook.Meta(author="Dana Whitlock", title="The Long Return")

    assert combobook._similarity(guess, right) >= combobook.MIN_AUTO_SCORE
    # this one used to score 0.79 against a 0.75 floor -- and be accepted
    assert combobook._similarity(guess, wrong) < combobook.MIN_AUTO_SCORE
