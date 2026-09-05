# Proposal: Dynamic LLM Model Configuration

**Status:** draft, awaiting decision
**Date:** 2026-09-05
**Scope:** `AbtoolsGui.py`, `ablib/core/config.py`, `ablib/metadata/llm.py`, `mcp_server/`
**Goal:** remove the hardcoded `MODEL_CHOICES` list and make endpoint/model configuration discoverable, persistent and consistent across the GUI, CLI and MCP server.

This document assesses an earlier four-option design sketch (auto-discovery / presets / MRU cache / config cascade), corrects the parts that do not match the code as it actually stands, and proposes a phased plan.

---

## 1. Summary

The core idea — query the server's `/v1/models` endpoint instead of shipping a hardcoded list — is sound and worth doing. Three corrections are needed before implementing it, and one of the four original options is blocked by a missing feature elsewhere in the codebase.

| Option | Verdict | Notes |
|---|---|---|
| 1. Live auto-discovery via `/v1/models` | **Adopt** | Needs thread-marshalling and robust URL derivation (§3.1, §3.3) |
| 3. Persistent settings + MRU model list | **Adopt, with #1** | Must extend the existing settings file, not add a second (§3.4) |
| 2. Provider presets | Optional, cheap | Drop the "Remote" preset until auth exists (§3.2) |
| 4. Config cascade (env vars) | Defer to last | Largest blast radius; real payoff is the MCP server, not the GUI (§4.4) |

**Recommended order:** fix the open P2 correctness bugs first (§5), then ship options 1 + 3 as a single change, then reassess 2 and 4.

---

## 2. Verified findings

Everything below was checked against the running code, not inferred.

### 2.1 All `CONFIG` references are the same object

```
gui.CONFIG                 id=139757114388368
cli.main.CONFIG            id=139757114388368
llm.CONFIG                 id=139757114388368
core.config.config         id=139757114388368
combobook.tagger.CONFIG    id=139757114388368
ALL THE SAME OBJECT: True
```

`ablib/core/config.py` exposes a single module-level `config = RuntimeConfig()`, and every consumer binds to that same instance.

**Consequence:** this block in `AbtoolsGui.apply_llm_settings()` is dead code — it assigns the object's attributes to themselves:

```python
tagger_mod = getattr(combobook, "tagger", None)
if tagger_mod is not None and hasattr(tagger_mod, "CONFIG"):
    tagger_mod.CONFIG.llm_endpoint = CONFIG.llm_endpoint      # no-op
    tagger_mod.CONFIG.llm_model_name = CONFIG.llm_model_name  # no-op
```

It should be deleted regardless of which option is adopted. It implies a decoupling between the GUI and the tagger that does not exist, and will mislead the next reader.

### 2.2 Authenticated / remote providers cannot work today

`ablib/metadata/llm.py::_call_llm` passes no `headers=` argument at all — there is no `Authorization` header, no API-key plumbing. (Grep hits for "api_key" in that module belong to Tavily search, which is unrelated.)

**Consequence:** any preset or documentation implying support for a hosted OpenAI-compatible provider is aspirational. Remote support requires, in order: an auth/token field in the GUI, an `api_key` field on `RuntimeConfig`, and header support in `_call_llm`.

### 2.3 Submodule shadowing in `ablib/cli/__init__.py`

`ablib/cli/__init__.py` contains `from .main import main`, which rebinds the package attribute `main` from the *submodule* to the *function*:

```
from ablib.cli import main            -> function
importlib.import_module("ablib.cli.main") -> module
```

This is almost certainly why `AbtoolsGui.py` uses `importlib.import_module("ablib.cli.main")` rather than a plain import. Not urgent, but it is a live trap for anyone adding imports here; worth a comment in `__init__.py` at minimum.

### 2.4 `/v1/models` URL derivation is tractable

Deriving the models URL from the configured chat endpoint works across the shapes users realistically type, provided it is done with `urllib.parse.urlsplit` rather than string slicing:

| Configured endpoint | Derived models URL |
|---|---|
| `http://127.0.0.1:8888/v1/chat/completions` | `http://127.0.0.1:8888/v1/models` |
| `http://127.0.0.1:1234/v1/chat/completions/` | `http://127.0.0.1:1234/v1/models` |
| `http://127.0.0.1:11434/v1` | `http://127.0.0.1:11434/v1/models` |
| `http://127.0.0.1:8000` | `http://127.0.0.1:8000/v1/models` |
| `https://api.example.com/openai/v1/chat/completions` | `https://api.example.com/openai/v1/models` |

### 2.5 Infrastructure that already exists

- **Settings file:** `~/.abtools_gui.json` already exists, added for theme persistence.
- **Thread → UI channel:** `output_queue` (a `queue.Queue`) drained by `poll_queue()` via `root.after(100, ...)`.
- **Worker spawning:** `start_worker()` with `current_worker` / `stop_event`.
- **Model combobox is already editable** (`state="normal"`), so free-text model names already work. Only the *memory* of them is missing.
- **`llm_controls`** currently holds 2 widgets; anything new that should grey out with the LLM toggle must be appended to it.

---

## 3. Corrections to the original sketch

### 3.1 Tkinter thread-safety (the actual hard part)

The sketch says to make the HTTP call in the background "so it never freezes the mainloop", but does not address the real constraint: **Tkinter is not thread-safe.** Assigning `model_combo["values"]` from a worker thread produces intermittent, hard-to-reproduce crashes.

The probe must post its result to `output_queue` and let `poll_queue()` apply it on the UI thread. `poll_queue` already has a message-type switch (`stdout` / `progress` / `prompt` / `status`); this adds one more case.

### 3.2 The "Remote" preset is blocked

Given §2.2, a Provider dropdown offering "Custom / Remote" would advertise something that cannot work. Ship presets for local runners only (LM Studio / Ollama / vLLM), or implement auth first.

### 3.3 Use `urlsplit`, not string manipulation

Trailing slashes, bare hosts and path-prefixed deployments all appear in practice (§2.4). A `.replace("/chat/completions", "/models")` will silently produce a wrong URL for three of the five cases above.

### 3.4 One settings file, not three

The sketch proposes `~/.config/abtools/gui_config.json` *or* `~/.abtools.json`. `~/.abtools_gui.json` already exists (§2.5). Extend it. Note also that `~/.abclient.json` already exists for feature flags — that is a separate concern and should stay separate.

Proposed schema, versioned so future changes can migrate:

```json
{
  "version": 1,
  "theme": "Neutral Slate",
  "llm_endpoint": "http://127.0.0.1:8888/v1/chat/completions",
  "llm_model": "qwen2.5-7b-instruct",
  "recent_models": ["qwen2.5-7b-instruct", "ibm/granite-4-h-tiny"]
}
```

### 3.5 Do not honour `OPENAI_*` environment variables

The sketch lists `OPENAI_BASE_URL` / `OPENAI_MODEL_NAME` as fallbacks. Silently inheriting a variable set for an unrelated tool is surprising, and could point tagging at a paid hosted API without the user realising. Use `ABTOOLS_LLM_ENDPOINT` / `ABTOOLS_LLM_MODEL` only.

---

## 4. Plan

### Phase 1 — cleanup (small, do first)

- Delete the no-op `tagger_mod.CONFIG` block in `apply_llm_settings` (§2.1).
- Add a comment in `ablib/cli/__init__.py` recording the shadowing trap (§2.3).

### Phase 2 — auto-discovery + persistence (the main change)

Single change covering options 1 and 3.

**Endpoint derivation:**

```python
from urllib.parse import urlsplit, urlunsplit

def models_url(endpoint: str) -> str:
    """Derive the /v1/models URL from a chat-completions endpoint."""
    s = urlsplit(endpoint.strip().rstrip("/"))
    path = s.path
    for suffix in ("/chat/completions", "/completions"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    if not path.endswith("/v1"):
        path = path.rstrip("/") + "/v1"
    return urlunsplit((s.scheme, s.netloc, path + "/models", "", ""))
```

**Probe, off the UI thread, result marshalled back through the existing queue:**

```python
def probe_models(endpoint: str) -> None:
    def work() -> None:
        try:
            r = requests.get(models_url(endpoint), timeout=3)
            r.raise_for_status()
            ids = [m["id"] for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
            output_queue.put(("models", (sorted(ids), None)))
        except Exception as exc:
            output_queue.put(("models", (None, str(exc))))
    threading.Thread(target=work, daemon=True).start()
```

**Applied on the UI thread**, as a new case in `poll_queue`:

```python
elif typ == "models":
    ids, error = msg
    if ids:
        model_combo["values"] = ids
        endpoint_status.set(f"● {len(ids)} models")
    else:
        model_combo["values"] = recent_models()   # graceful fallback
        endpoint_status.set("● unreachable")
```

**Triggers:** an explicit `↻` button (appended to `llm_controls`) plus `<FocusOut>` on the endpoint field. Not on every keystroke.

**MRU:** on each run that uses the LLM, prepend the selected model to `recent_models`, de-duplicate, cap at 10, save. On startup, seed `model_combo["values"]` from `recent_models` so the dropdown is useful before any probe completes.

**Removals:** the `MODEL_CHOICES` constant disappears entirely.

### Phase 3 — provider presets (optional)

A Provider dropdown that fills in the endpoint and triggers a probe. Local runners only until auth lands:

| Provider | Endpoint |
|---|---|
| LM Studio | `http://127.0.0.1:1234/v1/chat/completions` |
| Ollama | `http://127.0.0.1:11434/v1/chat/completions` |
| vLLM | `http://127.0.0.1:8000/v1/chat/completions` |

### Phase 4 — config cascade (largest, defer)

Precedence: explicit CLI flag / GUI selection → user settings file → `ABTOOLS_*` env vars → `constants.py` defaults.

The GUI is not the main beneficiary. **`mcp_server/` currently has no way at all to configure the endpoint** — it has no CLI flags and reads whatever `constants.py` hardcodes. Env-var support would fix a genuine gap for anyone running the MCP server under LM Studio or in a container.

Because `RuntimeConfig` is a shared singleton (§2.1), this must be done carefully: the CLI, GUI and MCP server all mutate the same instance.

---

## 5. Sequencing against open bugs

This is ergonomics work, and `bug.md` still has open **P2 correctness** items that affect output:

- **5.2** — the `[--]` regex in `ablib/metadata/utils.py` splits on *internal* hyphens, so `Spider-Man - Stan Lee` parses as `['Spider', 'Man', 'Stan Lee']`. Author/title hints are silently corrupted for any hyphenated name.
- **5.1** — `export_metadata` raises `TypeError` on a non-string metadata value.
- **5.8** — `choose_meta` raises `AttributeError` on a null provider title.

All three are small. Recommendation: land those first, then Phase 1 + 2 together.

---

## 6. Decisions needed

1. **Auth:** is remote/hosted provider support wanted? If yes it is a prerequisite for Phase 3's "Remote" preset and needs `api_key` on `RuntimeConfig` plus header support in `_call_llm`.
2. **Probe on startup:** should the GUI probe the saved endpoint automatically at launch, or only on demand? Automatic is more convenient; on-demand avoids firing a request at whatever address happens to be saved.
3. **Phase 4 scope:** GUI + CLI only, or extend to the MCP server at the same time?
