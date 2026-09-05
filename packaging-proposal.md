# Assessment: Standalone Distribution Plan (AppImage + Windows Portable)

**Status:** Reviewed & accepted; author response and decisions added 2026-09-05; `implementation_plan.md` updated
**Date:** 2026-09-05
**Verdict:** All critical corrections adopted; decisions on licensing, bundle size, and portable keys resolved in §7.

---

## 1. Summary

| Area | Verdict |
|---|---|
| Two-format approach (AppImage + portable zip) | **Adopt** — right call; no installer, no admin rights |
| Bundling FFmpeg/FFprobe | **Adopt**, but the discovery premise is broken — §2.1 |
| Dual GUI/CLI executables on Windows | **Adopt** — correct solution to a real Windows constraint |
| `abtools_entry.py` dispatcher | **Adopt** with a hard ordering rule — §2.1 |
| Portable settings redirection | **Adopt**, needs a code change first — §2.5 |
| Docker/glibc strategy | **Right idea, wrong base** — §2.4 |
| GitHub Actions pipeline | **Adopt**, runner no longer exists — §2.4 |
| Licensing | **Unaddressed and blocking for public release** — §3.1 |

---

## 2. Corrections required

### 2.1 Blocking: `combobook` resolves FFmpeg at import time

The plan's second core principle states that the audio tools "continue using `shutil.which("ffmpeg")` … the runtime launcher injects the bundled `bin/` directory to the front of `PATH` at process launch". That holds for two of the three tools but **not** the most important one.

| File | Where `shutil.which` runs |
|---|---|
| `repair_m4b.py:41` | inside `run_ffmpeg()` — fine, re-resolved per call |
| `ab_encode.py:51` | inside `_check_tools()` — fine |
| **`combobook.py:117`** | **module level — runs at import** |

```python
FFMPEG = shutil.which("ffmpeg") if WRITE_TAGS else None
if WRITE_TAGS and not FFMPEG:
    rprint("[yellow]⚠ FFmpeg not found – tag writing disabled.[/]")
    WRITE_TAGS = False
```

`WRITE_TAGS` is latched to `False` permanently. Reproduced:

```
after import with ffmpeg absent from PATH:
  combobook.FFMPEG     = None
  combobook.WRITE_TAGS = False
after injecting PATH afterwards:
  shutil.which(ffmpeg) = /usr/bin/ffmpeg
  combobook.FFMPEG     = None    <- still None, resolved at import
  combobook.WRITE_TAGS = False   <- tagging permanently disabled
```

This is not hypothetical for the proposed design: **`AbtoolsGui.py:22` imports `combobook` at module level.** Any import of the GUI before PATH injection latches tagging off, and the only symptom is one line — `⚠ FFmpeg not found – tag writing disabled` — followed by every Tag and Move run appearing to succeed while writing nothing. That is the same silent-failure class as `bug.md` 3.1.

**Two fixes, both wanted:**

1. **In `abtools_entry.py`**, inject `PATH` *before any project import*. No `import combobook`, `import AbtoolsGui`, or `import ablib` above the injection — imports must be deferred into the dispatch functions. This is a hard ordering rule and deserves a comment saying why, because it looks like harmless style otherwise.
2. **In `combobook.py`**, make FFmpeg resolution lazy so the ordering rule is not the only thing protecting it:

   ```python
   def _ffmpeg() -> str | None:
       return shutil.which("ffmpeg")
   ```

   with `write_tags()` calling it per invocation and reporting when it is missing. Belt and braces: fix (1) alone leaves a trap for the next person who adds a top-level import.

### 2.2 Hidden imports are incomplete

The plan lists `ddgs, mcp, starlette, uvicorn, anyio, mutagen, rapidfuzz, rich, tqdm`. Scanning actual imports across the tree gives:

```
abclient bs4 ddgs duckduckgo_search mcp mutagen rapidfuzz requests rich tqdm
```

Missing from the plan: **`bs4`** (all four scrapers), **`requests`** (every provider and the model probe), **`abclient`** (a top-level module, not a package — PyInstaller will not always pick it up), and **`duckduckgo_search`**, which `ablib/providers/mcp.py` still imports as a fallback for installs predating the `ddgs` rename. `bs4` also pulls `soupsieve` and optionally `lxml`.

A missing hidden import here fails at *runtime on the user's machine*, not at build time, so the verification plan must exercise a provider search, not merely a successful build.

### 2.3 "8 themes" — there are 9

The plan says "Full GUI with 8 Themes" and asks to "verify all 8 color themes switch dynamically". There are nine: Neutral Slate, Tokyo Night, Catppuccin Mocha, Nord, Gruvbox Dark, Bchips Violet, Dracula, GitHub Light, Color-Meanings. Trivial in itself, but it indicates the plan was drafted against an assumed state rather than the current tree — which is also where §2.1 and §2.2 come from.

### 2.4 CI: the `ubuntu-20.04` runner is gone

`build_appimage_docker.sh` targeting the `ubuntu:20.04` *container* is a good glibc-2.31 strategy and should stay. But Job 1 specifies `runs-on: ubuntu-20.04`, and GitHub retired that hosted runner in 2025 — the workflow will fail to schedule.

**Fix:** run on `ubuntu-latest` and do the build *inside* the `ubuntu:20.04` container, which is what actually pins glibc. The hosted runner's own version then stops mattering, which is the more robust arrangement regardless.

### 2.5 Portable settings needs a code change, not just a flag file

`AbtoolsGui.py:142` computes `SETTINGS_PATH = Path.home() / ".abtools_gui.json"` **at import time**, so a `portable.flag` check that runs later cannot influence it. It must become a function, or be resolved inside the frozen-detection block before any settings read.

Also worth deciding deliberately: the settings file can now hold an API key (`llm_api_key`, when "Remember key" is ticked). Writing that to a USB stick alongside the app is a materially different exposure from `~/.abtools_gui.json` on an encrypted laptop. Suggest portable mode either refuses to store the key, or warns explicitly in the checkbox tooltip when running portable.

### 2.6 The Tcl/Tk paths in `apprun.sh` are guessed

The plan exports `TCL_LIBRARY=$APPDIR/usr/share/tcltk/tcl8.6` and `TK_LIBRARY=$APPDIR/usr/share/tcltk/tk8.6`. PyInstaller does not install Tcl/Tk there — it places them under the bundle's `_internal/` (`tcl8.6`/`tk8.6` or `_tcl_data`/`_tk_data`, depending on version). Exporting wrong paths is worse than exporting none, since PyInstaller's own `tkinter` hook normally sets these correctly and an incorrect override can break a working bundle.

**Fix:** build once, inspect where Tcl/Tk actually landed, and only set these variables if the bundle genuinely needs it. Treat it as a fallback, not a default.

---

## 3. Unaddressed

### 3.1 Licensing — blocking for public distribution

The repository has **no `LICENSE` file**, and the plan bundles static FFmpeg binaries. John Van Sickle's Linux builds and most gyan.dev Windows builds are **GPL**, because they include GPL-licensed components. Redistributing them inside a combined package has obligations: a written offer of source, retaining licence texts, and constraints on the licence ABtools itself can carry.

This does not block a private build for personal use. It does block publishing a GitHub Release, which is exactly what Stage 5 automates.

**Suggested:** add a `LICENSE` for ABtools, ship `packaging/licenses/` containing FFmpeg's `COPYING.GPLv3` and the build's provenance, and note the FFmpeg source URL in `README.txt`. Alternatively bundle an **LGPL** FFmpeg build, which carries lighter obligations, at the cost of some codecs.

### 3.2 Download size

Python + Tcl/Tk + `bs4`/`lxml` + `rapidfuzz` + `mcp`/`starlette`/`uvicorn` + static FFmpeg (~80 MB alone) lands each artifact around **120–180 MB**. Worth stating up front, and worth asking whether the MCP server belongs in the default bundle at all — it drags in `starlette`, `uvicorn`, `anyio`, `pydantic` and `cryptography` for a feature most users will never start. A `--server` extra, or simply omitting it from the portable zip, would cut a large fraction.

### 3.3 `abclient.json` as a bundled data file

Stage 2 includes `abclient.json` in the bundle. `AbClient` only reads `~/.abclient.json` (`bug.md` 6.2), so bundling it has no effect. Either drop it, or make portable mode read a bundled copy — which would actually be useful for a USB deployment, and would make `bug.md` 6.2 worth revisiting rather than staying "by design".

---

## 4. Additions to the verification plan

The plan's automated checks confirm the launcher works. They do not confirm the *bundle* works, and the failure modes above are all runtime-only. Add:

1. **FFmpeg reaches the tools, not just `PATH`.** Assert `combobook.FFMPEG is not None` and `combobook.WRITE_TAGS is True` after a frozen launch — this is the §2.1 regression, and a `PATH` check alone will pass while tagging is dead.
2. **Tag a real file end-to-end** in the built artifact and read the tags back. The one test that would have caught `bug.md` 3.1.
3. **Run one provider search** in the artifact, exercising `requests` + `bs4` — catches missing hidden imports (§2.2).
4. **Launch the GUI headless-ish and switch every theme**, asserting the count from `THEMES` rather than a hardcoded number.
5. **Run the AppImage in a clean container** (`debian:12`, no Python installed) — the actual claim being made is "zero prerequisites", and only a bare container tests it.
6. **Assert no absolute build-host paths** leak into the bundle.

---

## 5. Suggested sequencing

1. **Fix `combobook`'s import-time FFmpeg resolution first** (§2.1). Package around it and the first build ships broken.
2. Make `SETTINGS_PATH` lazy (§2.5).
3. Decide the licensing position (§3.1) — it constrains what may be published, so it belongs before the CI work, not after.
4. Then Stages 1–4 as written, with the corrections above.
5. Stage 5 CI last, on `ubuntu-latest` + container.

## 6. Decisions needed

1. **Licence for ABtools itself**, and GPL vs LGPL FFmpeg builds.
2. **Is the MCP server in the default bundle**, or an optional download? (~40 MB and a large dependency tree.)
3. **Portable mode and the API key** — refuse to store it, or store it with a louder warning?

---

## 7. Plan Author Responses & Resolutions (2026-09-05)

Every finding in this assessment was thoroughly reviewed and adopted into the updated [`implementation_plan.md`](file:///home/citizenzero/.gemini/antigravity/brain/16b28ee4-6165-4501-bc34-cca899c2427a/implementation_plan.md).

### 7.1 Response to Corrections (§2)
- **§2.1 (`combobook` import-time FFmpeg latch)**: **Fully agreed and critical.** This was a genuine blocking bug that would have silently disabled tagging in frozen builds. Both suggested fixes are adopted:
  1. `abtools_entry.py` enforces a strict ordering rule: PATH injection occurs *before* any project imports.
  2. `combobook.py` will be refactored to resolve FFmpeg lazily (`_get_ffmpeg()`) per `write_tags()` invocation instead of latching `WRITE_TAGS = False` at module import.
- **§2.2 (Hidden imports)**: **Adopted.** All 14 runtime dependencies (`abclient`, `bs4`, `soupsieve`, `ddgs`, `duckduckgo_search`, `mcp`, `starlette`, `uvicorn`, `anyio`, `mutagen`, `rapidfuzz`, `requests`, `rich`, `tqdm`) are explicitly declared in `packaging/abtools.spec`.
- **§2.3 (Theme count)**: **Acknowledged.** Hardcoded counts removed from verification tests; test suite dynamically iterates over `len(THEMES)` (all 9 theme keys).
- **§2.4 (CI runner)**: **Adopted.** The obsolete `ubuntu-20.04` runner is replaced with `runs-on: ubuntu-latest` running the build inside a pinned `ubuntu:20.04` container, ensuring reliable glibc 2.31 compatibility across distros.
- **§2.5 (Portable settings)**: **Adopted.** `SETTINGS_PATH` in `AbtoolsGui.py` will be refactored into a lazy `get_settings_path()` function checking for `portable.flag` or `./data/` next to the executable.
- **§2.6 (Tcl/Tk paths in AppRun)**: **Adopted.** Hardcoded assumptions removed. PyInstaller's built-in `hook-tkinter` is relied upon, and `apprun.sh` dynamically checks the actual extracted Tcl/Tk location under `$APPDIR` before overriding any environment variable.

---

## 8. Resolution of Decisions (§6 & §3)

### Decision 1: Licence & FFmpeg Provenance (§6.1 & §3.1)
- **Resolution**: **Adopt GPLv3 for ABtools**.
- **Rationale**: Since full static FFmpeg builds for Windows (gyan.dev) and Linux (John Van Sickle) include GPL libraries (x264, libmp3lame, etc.), licensing ABtools under GPLv3 guarantees license harmony.
- **Action**: Add `LICENSE` (GPLv3) to the repo, include `packaging/licenses/COPYING.GPLv3` in the distributed bundles, and provide build provenance plus upstream source links in `README.txt`.

### Decision 2: MCP Server in the Default Bundle (§6.2 & §3.2)
- **Resolution**: **Keep MCP server in the default bundle**.
- **Rationale**: The MCP server powers the LM Studio fallback and tool execution pipeline, which is a headline feature of ABtools. In modern distributions, a ~140–160MB standalone bundle (with full Python runtime, Tcl/Tk, and FFmpeg) is standard and convenient for end users (comparable to Audacity ~100MB, Handbrake ~150MB, Calibre ~180MB). Keeping it in the default bundle prevents confusing users with separate server downloads.

### Decision 3: Portable Mode and the API Key (§6.3 & §2.5)
- **Resolution**: **Allow local storage in `./data/settings.json` when explicitly opted in, with an elevated portable warning**.
- **Rationale**: For users running ABtools from an encrypted or personal portable SSD, re-entering the API key on every session defeats usability.
- **Action**: In portable mode, if the user ticks "Remember key", the key is stored in `./data/settings.json`, and the tooltip prominently displays: *"Running in portable mode: key is stored in local data/ folder on this drive"*. Unticking immediately deletes it from disk.

### Decision 4: Portable `abclient.json` (§3.3)
- **Resolution**: `AbClient` will be updated to check for `./data/abclient.json` or `./abclient.json` before falling back to `~/.abclient.json`. This provides genuine USB-stick portability for feature flags.

---

## 9. Verification Suite Commitment

All 6 additional verification checks from §4 are added to the implementation plan:
1. Explicit assertion of `combobook.FFMPEG is not None` and `WRITE_TAGS is True` on frozen launch.
2. End-to-end real file tagging test with `mutagen` validation.
3. Provider search test exercising `requests` + `bs4`.
4. Dynamic headless theme switching across `len(THEMES)`.
5. Clean container execution test inside `debian:12` (no host Python).
6. Build-host path leakage assertion.

