"""The local-LLM fallback, and the gate that keeps its answers honest.

A hosted free tier runs out partway through a large run --
"HTTP 429: Rate limit exceeded: free-models-per-day" -- and every remaining
book was then left with no metadata. Falling back to a local model fixes that,
but a small local model asked "which audiobook is this folder?" will answer
confidently even when it has no idea, and there is no provider score on this
path to catch it. So a fallback answer is checked against the folder before it
is written.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ablib.core.config import config  # noqa: E402
from ablib.metadata import llm  # noqa: E402

RIGHT = {"title": "Homeward Bound", "author": "Harry Turtledove",
         "series": "Worldwar", "series_index": "8", "year": "2004",
         "narrator": "Todd McLaren", "language": "en",
         "description": "The final Worldwar novel.", "publisher": "Del Rey"}
WRONG = {"title": "The Hobbit", "author": "J. R. R. Tolkien", "series": None,
         "series_index": None, "year": "1937", "narrator": None,
         "language": None, "description": None, "publisher": None}
GUESS = {"title": "Homeward Bound", "author": None, "year": None,
         "series": "Worldwar - Colonization", "series_index": None}


class _Endpoint:
    """A throwaway OpenAI-compatible server that answers, or refuses."""

    def __init__(self, status: int, payload: dict | None):
        self.calls = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.calls += 1
                if status != 200:
                    body = json.dumps({"error": {
                        "message": "Rate limit exceeded: free-models-per-day",
                        "code": status}}).encode()
                else:
                    body = json.dumps({"choices": [{
                        "message": {"content": json.dumps(payload)},
                        "finish_reason": "stop"}]}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = TCPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/v1/chat/completions"

    def close(self):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def book(tmp_path):
    folder = tmp_path / "Worldwar - Colonization" / "Homeward Bound"
    folder.mkdir(parents=True)
    track = folder / "01.mp3"
    track.touch()
    return folder, [track]


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "log_path", tmp_path / "tag_log.txt")
    monkeypatch.setattr(config, "review_path", tmp_path / "review_log.txt")
    monkeypatch.setattr(config, "debug", False)
    monkeypatch.setattr(config, "llm_api_key", "sk-test")
    monkeypatch.setattr(config, "llm_model_name", "hosted/model")
    monkeypatch.setattr(config, "llm_fallback_model", "local/model")
    monkeypatch.setattr(config, "llm_fallback_min_score", 85)


def _run(monkeypatch, book, hosted: _Endpoint, local: _Endpoint | None):
    monkeypatch.setattr(config, "llm_endpoint", hosted.url)
    monkeypatch.setattr(config, "llm_fallback_endpoint", local.url if local else None)
    folder, files = book
    return llm.generate_metadata_via_llm(folder, files, guess=GUESS)


def test_quota_error_falls_back_to_the_local_model(monkeypatch, book):
    hosted, local = _Endpoint(429, None), _Endpoint(200, RIGHT)
    try:
        result = _run(monkeypatch, book, hosted, local)
        assert result is not None
        assert result["title"] == "Homeward Bound"
        assert result["author"] == "Harry Turtledove"
        assert hosted.calls == 1 and local.calls == 1
    finally:
        hosted.close(); local.close()


def test_low_scoring_fallback_answer_leaves_the_book_untagged(monkeypatch, book):
    hosted, local = _Endpoint(429, None), _Endpoint(200, WRONG)
    try:
        assert _run(monkeypatch, book, hosted, local) is None
    finally:
        hosted.close(); local.close()


def test_threshold_governs_acceptance(monkeypatch, book):
    hosted, local = _Endpoint(429, None), _Endpoint(200, WRONG)
    try:
        monkeypatch.setattr(config, "llm_fallback_min_score", 0)
        assert _run(monkeypatch, book, hosted, local) is not None
    finally:
        hosted.close(); local.close()


def test_a_bad_answer_is_not_retried_elsewhere(monkeypatch, book):
    """Only quota/auth/server failures are retryable. A model that answered --
    even unusably -- would answer the same way twice, so it is not asked."""
    hosted, local = _Endpoint(200, {"title": None, "author": None}), _Endpoint(200, RIGHT)
    try:
        assert _run(monkeypatch, book, hosted, local) is None
        # The fallback is what must not fire. (The primary is called twice: the
        # pre-existing gap-filling retry, which is unrelated to this feature.)
        assert local.calls == 0
        assert hosted.calls >= 1
    finally:
        hosted.close(); local.close()


def test_no_fallback_configured_is_not_an_error(monkeypatch, book):
    hosted = _Endpoint(429, None)
    try:
        assert _run(monkeypatch, book, hosted, None) is None
    finally:
        hosted.close()


def test_fallback_is_skipped_when_it_is_the_failing_endpoint(monkeypatch, book):
    hosted = _Endpoint(429, None)
    try:
        monkeypatch.setattr(config, "llm_endpoint", hosted.url)
        monkeypatch.setattr(config, "llm_fallback_endpoint", hosted.url)
        folder, files = book
        assert llm.generate_metadata_via_llm(folder, files, guess=GUESS) is None
        assert hosted.calls == 1          # not asked the same question twice
    finally:
        hosted.close()


@pytest.mark.parametrize(
    "meta, guess, expected_min",
    [
        ({"title": "Homeward Bound", "author": "Harry Turtledove"}, GUESS, 85),
        ({"title": "The Hobbit", "author": "J. R. R. Tolkien"}, GUESS, 0),
    ],
)
def test_fallback_confidence_tracks_agreement(meta, guess, expected_min):
    score = llm.fallback_confidence(meta, guess)
    assert 0 <= score <= 100
    if expected_min:
        assert score >= expected_min
    else:
        assert score < 85


def test_unverifiable_answer_scores_zero():
    """With nothing to check against, a fallback answer is never confident."""
    assert llm.fallback_confidence({"title": "Anything"}, None) == 0
    assert llm.fallback_confidence({"title": "Anything"}, {"title": ""}) == 0
    assert llm.fallback_confidence(None, GUESS) == 0


def test_endpoint_label_names_the_host():
    """A quota error from a hosted provider used to be reported as coming from
    "LM Studio", which is what made the field report confusing."""
    assert llm._endpoint_label("https://openrouter.ai/api/v1/chat/completions") == "openrouter.ai"
    assert llm._endpoint_label("http://127.0.0.1:8888/v1/chat/completions") == "local LLM"
    assert llm._endpoint_label(None) == "LLM"
