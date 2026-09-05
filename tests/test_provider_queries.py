"""Provider query quality -- the layer that decides how often the LLM is needed.

Measured against a real library (Harry Turtledove, 15 books laid out as
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
        ("Daughter of the Empire 128kbps", "Daughter of the Empire"),   # matched nothing before
        ("Magicians End (Unabridged)", "Magicians End"),                # scored 45 before
        ("The Final Empire [Audiobook]", "The Final Empire"),
        ("Rage of a Demon King - 01 of 14", "Rage of a Demon King"),
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
        ("Silverthorn (The Riftwar Saga, #3)", "Silverthorn", "The Riftwar Saga", "3"),
        ("Down to Earth (Colonization, Book 2)", "Down to Earth", "Colonization", "2"),
        ("Tilting the Balance (Worldwar Series, Volume 2)",
         "Tilting the Balance", "Worldwar", "2"),
        ("Hitler's War (the War That Came Early, Book One)",
         "Hitler's War", "the War That Came Early", "1"),
    ],
)
def test_inline_series_is_lifted_out_of_the_title(raw, title, series, index):
    assert P.split_series_suffix(raw) == (title, series, index)


@pytest.mark.parametrize(
    "raw", ["The Hitchhikers Guide (Radio Play)", "Something (A Novel)", "Faerie Tale"]
)
def test_a_plain_parenthetical_is_not_a_series(raw):
    assert P.split_series_suffix(raw) == (raw, None, None)


def test_edition_tail_is_stripped_only_when_it_names_the_author():
    assert P.strip_edition_tail(
        "Worldwar: Striking the Balance by Harry Turtledove (1996-12-05)",
        ["Harry Turtledove"],
    ) == "Worldwar: Striking the Balance"
    # a title that genuinely contains "by" survives
    assert P.strip_edition_tail("Death by Black Hole", ["Neil deGrasse Tyson"]) \
        == "Death by Black Hole"


# ── scoring ─────────────────────────────────────────────────────────────────

def test_a_perfect_title_scores_full_marks_without_a_known_author():
    """The regression that drove everything to the LLM: fixed weights meant a
    perfect title with no author scored 100*0.7 = 70, under the 85 threshold."""
    hit = {"title": "Rage of a Demon King", "authors": ["Raymond E. Feist"]}
    assert P.score_candidate(hit, "Rage of a Demon King", None) == 100
    assert P.score_candidate(hit, "Rage of a Demon King", "Raymond E. Feist") == 100


def test_a_wrong_author_still_costs_the_candidate():
    hit = {"title": "Homeward Bound", "authors": ["Elaine Tyler May"]}
    right = {"title": "Homeward Bound", "authors": ["Harry Turtledove"]}
    assert P.score_candidate(hit, "Homeward Bound", "Harry Turtledove") \
        < P.score_candidate(right, "Homeward Bound", "Harry Turtledove")


def test_series_agreement_lifts_a_candidate():
    with_series = {"title": "Silverthorn", "authors": ["Feist"], "series": "Riftwar Saga"}
    without = {"title": "Silverthorn", "authors": ["Feist"], "series": "Something Else"}
    assert P.score_candidate(with_series, "Silverthorn", "Feist", "Riftwar Saga") \
        > P.score_candidate(without, "Silverthorn", "Feist", "Riftwar Saga")


# ── the folder tree the query is built from ─────────────────────────────────

def test_series_folder_is_not_mistaken_for_the_author(tmp_path):
    """<Author>/<Series (years)>/<N - Title (Year)> -- the immediate-parent rule
    sent "Worldwar - Colonization" to the catalogues as an author, which
    suppressed every correct hit and let unrelated books outrank them."""
    book = tmp_path / "Harry Turtledove" / "Worldwar - Colonization (1994-2004)" / "8 - Homeward Bound (2004)"
    book.mkdir(parents=True)
    author, title, year, series, index = guess_from_path(book)
    assert author == "Harry Turtledove"
    assert title == "Homeward Bound"
    assert year == "2004"
    assert series == "Worldwar - Colonization"
    assert index == "8"


def test_author_folder_without_a_series_level(tmp_path):
    book = tmp_path / "Harry Turtledove" / "Through Darkest Europe (2018)"
    book.mkdir(parents=True)
    author, title, year, series, _ = guess_from_path(book)
    assert (author, title, year, series) == ("Harry Turtledove", "Through Darkest Europe", "2018", None)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Worldwar - Colonization (1994-2004)", "Worldwar - Colonization"),
        ("The War That Came Early (2009-2014)", "The War That Came Early"),
        ("Mistborn (2006)", "Mistborn"),
        ("Harry Turtledove", None),
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

    best, _ = P.best_match("Harry Turtledove", "Homeward Bound", client=_Client())
    assert best and best[0] >= P.ACCEPT_SCORE
    assert calls == ["goodreads"]


def test_the_ladder_retries_without_the_guessed_author(monkeypatch):
    """An author read off a directory name is a guess; the title rarely is."""
    seen: list[tuple] = []

    def gr(author, title):
        seen.append((author, title))
        if author:                       # the guessed author suppresses the book
            return None
        return {"title": title, "authors": ["Harry Turtledove"], "series": None}

    monkeypatch.setattr(P, "goodreads", gr)
    for name in ("audible", "openlib", "gbooks"):
        monkeypatch.setattr(P, name, lambda a, t: None)

    best, _ = P.best_match("Wrong Series Name", "Homeward Bound", client=_Client())
    assert best is not None
    assert best[1]["authors"] == ["Harry Turtledove"]
    assert (None, "Homeward Bound") in seen


def test_goodreads_soft_block_stops_being_retried(monkeypatch):
    """Goodreads answers HTTP 202 with an empty body when it throttles, which
    raise_for_status() does not catch. Asking on every book wastes a request."""
    P.clear_cache()
    for _ in range(P._GOODREADS_FAILURE_LIMIT):
        P._note_goodreads(False)
    assert P._goodreads_state["disabled"] is True

    called: list[int] = []
    monkeypatch.setattr(P.SESSION, "get", lambda *a, **k: called.append(1))
    assert P.goodreads("Harry Turtledove", "Homeward Bound") is None
    assert called == []                  # not even attempted

    P.clear_cache()
    assert P._goodreads_state["disabled"] is False


def test_results_are_cached_per_query(monkeypatch):
    calls: list[tuple] = []

    def fake_get(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(P.SESSION, "get", fake_get)
    P.openlib("Harry Turtledove", "Homeward Bound")
    P.openlib("Harry Turtledove", "Homeward Bound")
    assert len(calls) == 1
