# Past Memory

- [2025-01-20] Initial setup of GEMINI.md and past_memory.md.
- [2025-01-20] Fixed version inconsistencies in `combobook.py`, `AbtoolsGui.py`, and `restructure_for_audiobookshelf.py`.
- [2025-01-20] Updated `README.md` and `scaffold.md` to match codebase state.
- [2026-03-09] Fixed f-string syntax error in `ab_encode.py` which prevented backslashes inside f-string expressions.
- [2026-03-09] Fixed ab_encode.py ffmpeg command: added -err_detect ignore_err and -fflags +discardcorrupt to tolerate VBR/corrupt MP3 headers at file join points; upgraded -loglevel to 'warning'.
- [2026-03-09] Improved ab_encode.py v1.1: type hints, ffmpeg/ffprobe startup check, tempfile concat list, defaultdict summary, --version, -v verbose flag, per-file cleanup error handling.
- [2026-03-09] Full project improvement pass: fixed console.py Confirm fallback to class with .ask(); added echo= kwarg to log(); added debug logging to all providers; fixed meta mutation in best_match(); added MAX_TOOL_ITERATIONS guard to _call_llm; fixed ROOT global in flatten_discs.py; renamed repair_m4b --no-overwrite to --overwrite; replaced legacy typing imports throughout. All files syntax-verified.
- [2026-03-09] Improved ab_encode.py v1.2: added background thread to update tqdm progress bar description with currently encoding folders so it doesn't appear frozen during long encodes.
- [2026-03-09] Improved ab_encode.py tqdm ETA accuracy by adding smoothing=0.1 to prevent fast-skips from skewing the remaining time calculation.
- [2026-03-09] Fixed ffmpeg 'Unable to find a suitable output format' error in ab_encode.py when writing to .tmp files by adding explicit -f mp4 format flag.
- [2026-03-09] Fixed FFmpeg crashes on embedded album art in ab_encode.py by adding the -vn flag to ignore video streams (prevents x264 'width not divisible by 2' errors).
- [2026-03-09] Replaced tqdm with rich.progress in ab_encode.py for a stable, multi-bar premium UI that shows exactly what each worker is currently doing.
- [2026-03-09] Fixed missing progress bar in ab_encode.py: added rich.logging.RichHandler so the standard python logger doesn't suppress the rich.progress live UI.
- [2026-03-09] Suppressed ffmpeg stderr to hide MP3 duration warnings from breaking the rich progress bar layout in ab_encode.py.
- [2026-03-09] Fixed UI freeze in ab_encode.py by adding a threading.Semaphore to strictly control task submission to the executor queue, ensuring workers accurately obey the -w limit.
- [2026-03-09] Reverted ab_encode.py UI back to smoothed tqdm implementation over rich.progress due to user preference/instability.
- [2026-03-09] Added -threads 1 to ffmpeg command in ab_encode.py to prevent thread thrashing caused by running multiple unrestricted ffmpeg processes via ThreadPoolExecutor.
- [2026-03-09] Added smart AAC passthrough to ab_encode.py. If source files are already AAC (.m4a. m4b, mp4), ffmpeg applies -c:a copy instead of re-encoding, avoiding generation loss and finishing in seconds.
- [2026-03-09] Added comprehensive KeyboardInterrupt exception handling to the as_completed threading loop in ab_encode.py to ensure the thread pool shuts down cleanly without vomiting a traceback wall.
- [2026-09-04] Full codebase logic error audit: identified 24 logic errors, crashes, and protocol bugs across 10 files (restructure_for_audiobookshelf parser crash, GUI restructure signature mismatch, MCP server stdout protocol corruption, combobook dry-run tag writing/renaming, ffmpeg .tmp format failures in repair_m4b/combobook, combobook leaf_dirs disc dropping, ab_encode concat quote escaping, XML serialization int crash). Compiled full report in bug.md; updated scaffold.md and README.md. No source files modified per user instruction.
- [2026-09-04] Second independent audit + empirical verification of every bug.md claim. THREE CLAIMS REFUTED — do not "fix" them: (1) ab_encode.py concat single-quote escaping `'\''` is CORRECT; tested, ffmpeg rc=0 on a filename containing an apostrophe, while the unescaped control fails with "Impossible to open" — the proposed `\'` change would BREAK apostrophe filenames. (2) ab_encode.py Windows backslashes are literal inside single quotes; non-issue. (3) repair_m4b.py missing `Iterable` import is NOT a runtime NameError, because `from __future__ import annotations` (PEP 563) defers annotation evaluation — type-checker nit only. Reclassified: abclient local abclient.json is by-design ("Sample client configuration" per scaffold.md); rename_tracks dry-run bug is latent (RENAME_TRACKS=False); catalog.py duration crash is unreachable (module never imported anywhere); llm.py token-budget shrink is latent (all call sites pass max_tokens=1024).
- [2026-09-04] Three additional bugs the first audit missed, added to bug.md as 4.5/5.7/5.8: ab_encode.py selects an arbitrary .m4b via unordered os.listdir and has an unreachable elif (.m4b is absent from EXTENSIONS); ablib/metadata/utils.py guess_from_path discards the real title when the pre-title segments match a SERIES_PATTERNS regex; combobook.py choose_meta raises AttributeError when Google Books / Open Library return a null title. Also reviewed mcp_server/tools/*.py (5 modules an earlier -maxdepth 2 search had missed).
- [2026-09-04] FIXED all four P0 bugs; each verified with an end-to-end test. (2.1) combobook.py process(): wrapped the write_tags loop in `if not dry:` so preview no longer retags source files — verified file bytes are byte-identical after a dry run, with a control confirming commit=True still tags correctly. (3.1) combobook.py write_tags(): temp file renamed from "track.mp3.tmp" to "track.abtmp.mp3" so ffmpeg can infer the container, and stderr is now captured and reported. Previously ffmpeg exited rc=234 ("Unable to choose an output format") and created no file, so BOTH branches of the result check were skipped — the "failed to write tags" message was unreachable and tagging had a 100% SILENT failure rate. (3.1b) repair_m4b.py run_ffmpeg(): added explicit `-f mp4` (the same fix applied to ab_encode.py back in March but never backported), so --overwrite works instead of raising RuntimeError on every file. (1.1) restructure_for_audiobookshelf.py: added the missing "--commit" flag name to add_argument — the script previously crashed on ANY invocation including --help, so no code path in it had ever run. (1.2) AbtoolsGui.py restructure(): now calls restructure_library(src, dst, dry=..., copy=...) instead of main() with six parameters that never existed; note restructure_library has no stop_event hook, so Stop only takes effect after it returns. ORDERING NOTE: 2.1 had to be fixed before 3.1 — the dry-run tag writes were only harmless while the ffmpeg bug made them fail silently.
- [2026-09-04] Created the abtools_env virtualenv and installed all dependencies. NOTE: only Python 3.14.7 is available on this machine, not the 3.11 the README specifies; everything installed and ran fine on 3.14, but the README instructions are now stale. Installed all of requirements.txt (mutagen 1.48.1, requests 2.34.2, beautifulsoup4 4.15.0, rapidfuzz 3.14.6, rich 15.0.0, tqdm 4.70.0, duckduckgo-search 8.1.1). FOUND AN UNDECLARED DEPENDENCY: mcp_server/server.py imports `mcp` but it was missing from requirements.txt — added as `mcp<2`. The pin is required because mcp 2.x renamed FastMCP to MCPServer, so `from mcp.server.fastmcp import FastMCP` raises ModuleNotFoundError on 2.x; installed mcp 1.29.1. Migrating mcp_server to the 2.x MCPServer API is still open. Added `abtools_env/` to .gitignore (alongside the existing whisper_env/) so the venv is not tracked. Verified all 26 project modules import cleanly and `pip check` is clean; re-ran the P0 fix tests against the real (unstubbed) rapidfuzz and all passed, plus --version/--help smoke tests on every CLI entry point.
- [2026-09-04] FIXED bug.md 1.3 (MCP stdout protocol corruption): moved the startup banner, tool list and shutdown notice in mcp_server/server.py from sys.stdout to sys.stderr. stdio transport reserves stdout for the JSON-RPC stream, so those two banner writes before mcp.run() were the first thing any client read, breaking initialization. Verified with a real handshake (initialize -> notifications/initialized -> tools/list): every stdout line parses as JSON-RPC, the banner appears only on stderr, and all five tools are advertised. This was the FIRST end-to-end test the MCP server has ever had, because `mcp` was missing from requirements.txt until today.
- [2026-09-04] Verified the MCP tools actually execute, not just register (first ever end-to-end run, now possible after fixing 1.3 and installing the undeclared `mcp` dep). WORKING: search_openlibrary_tool (returned real Dune/OL893414W data), search_goodreads_tool (HTTP 200, 20 rows matched its selector), tag_books_tool (preview returned status/processed). BLOCKED BY REMOTE HOST, not code defects: search_google_books_tool gets HTTP 429 'Quota exceeded ... Queries per day' (unauthenticated Google Books quota is per-IP/shared) and search_audible_tool gets HTTP 503 with a 2.5KB block page (anti-scraping) — both degrade gracefully to error dicts. TESTING GOTCHA worth remembering: a probe that writes all requests then closes stdin makes the server exit on EOF mid-queue, which looks like 'NO RESPONSE' from slow tools; hold the pipe open and read replies as they arrive. Logged two new items in bug.md section 8: (8.1) audible is scraped in TWO places with disjoint selectors — mcp_server/tools/audible.py uses .bc-heading a/.bc-author a while ablib/providers/http.py uses h3/.authorLabel a, so at most one is current and the stale one fails silently as 'No results'; could not validate which from here because Audible 503s. (8.2) all four provider tools return a list on success but a dict on failure, so callers must type-check and cannot distinguish 'site returned nothing' from 'our parser matched nothing'.
- [2026-09-04] FIXED bug.md 4.1 and 4.4 (the P1 multi-disc data-safety pair), with regression tests. 4.4 flatten_discs.py: the base-name logic was DUPLICATED in disc_sets_in (line 60) and flatten (line 88), which is how they drifted; both now call a new shared disc_base_name() that falls back to the text AFTER the disc marker when the text before it is empty. So '[Disc 1] Book A' and '[Disc 1] Book B' no longer both collapse to base '' (which had made book_dir == parent, mixing two books into one folder and then crashing on FileExistsError). Deliberately PRESERVED: a bare marker like 'Disc 1' still yields base '' -> flatten into the parent, because there the parent genuinely IS the book. Also added a pre-flight collision check: flatten() computes all destinations first and refuses the whole set if any exists, instead of aborting mid-loop with an uncaught FileExistsError after some tracks already moved. 4.1 combobook.py: leaf_dirs now returns the PARENT as the book when every audio-bearing sub-folder is a bare disc marker, and excludes those sub-folders; process() additionally collects tracks from those sub-folders, otherwise the parent was skipped as 'no audio' since the tracks live one level down. KEY DESIGN CONSTRAINT worth remembering: folding ANY DISC_RX/PART_RX match into its parent would merge unrelated titles — 'Tolkien/The Hobbit Part 1' and 'Tolkien/The Hobbit Part 2' both match PART_RX, so the naive rule would treat 'Tolkien/' as a single book. Hence is_bare_disc_marker() requires the folder name to be NOTHING BUT a marker, and disc_children() returns [] on an ambiguous mix rather than guessing. Verified end-to-end: two-disc book -> 1 leaf, both discs moved+flattened+tagged, source left empty; plus regression tests for ordinary single-folder books, multi-book author folders, the Part 1/Part 2 case, and dry-run byte-integrity.
- [2026-09-04] FIXED bug.md 4.2 (root folder ignored when pointing directly at a book). Path.rglob('*') only yields DESCENDANTS, never the root itself, so `combobook.py "/books/Dune" /dest` and `search_and_tag --recurse` aimed at a single book folder both found 0 books and exited silently having done nothing. Fixed in BOTH entry points — combobook.leaf_dirs and ablib/cli/main.py walk_leaves — by iterating `[root, *root.rglob('*')]` so root is judged by the same rules as any other directory rather than needing a special case. A library root has no audio of its own so it still isn't a leaf (no spurious duplicate entry); a book root now is. In combobook this composes correctly with the 4.1 disc-folding, so a root that is itself a multi-disc book resolves to the one book folder. Cosmetic leftover: when root IS the book, process() prints the source as '.' via folder.relative_to(src). Consolidated regression suite now covers 2.1/3.1/3.1b/4.1/4.2/4.4 and passes 10/10.
- [2026-09-05] Wrote proposal.md assessing a four-option design sketch for dynamic LLM model configuration (auto-discovery via /v1/models, provider presets, MRU cache, config cascade). Verified the claims against running code first, which turned up three things the sketch had wrong or missed: (1) ALL FIVE CONFIG references (gui/cli.main/llm/core.config/combobook.tagger) are the SAME RuntimeConfig singleton object, id-checked, so the tagger_mod.CONFIG copy block in AbtoolsGui.apply_llm_settings is dead code assigning attributes to themselves - delete it; (2) ablib/metadata/llm.py _call_llm sends NO headers at all, so there is no Authorization/api-key path and remote or hosted providers cannot work today - any 'Custom/Remote' preset is aspirational until an api_key field is added to RuntimeConfig and threaded into _call_llm (the api_key grep hits in llm.py are Tavily's, unrelated); (3) the sketch ignored Tkinter thread-safety - a background probe must NOT touch model_combo['values'] directly but post to the existing output_queue and let poll_queue apply it on the UI thread. Also noted: ablib/cli/__init__.py's `from .main import main` shadows the submodule, so `from ablib.cli import main` yields a FUNCTION not a module (which is why AbtoolsGui uses importlib.import_module); /v1/models URL derivation needs urlsplit not string replace (tested against 5 endpoint shapes incl. trailing slash, bare host, path-prefixed); settings must extend the existing ~/.abtools_gui.json rather than add a third file; and OPENAI_BASE_URL/OPENAI_MODEL_NAME should NOT be honoured as fallbacks since silently inheriting another tool's env var could point tagging at a paid hosted API. Recommended order: land bug.md 5.1/5.2/5.8 first (5.2's [--] regex silently corrupts author/title for hyphenated names), then auto-discovery + MRU as one change, then reassess presets and the config cascade - whose real payoff is mcp_server, which currently has no way to configure the endpoint at all.
- [2026-09-05] Updated README.md and found several genuinely WRONG claims in it, not just stale ones. (1) The documented LM Studio port was 1234 in five places but the actual default in ablib/core/constants.py is 8888 - anyone following the README would have configured the wrong port; fixed all occurrences. (2) The version table was stale (flatten_discs 1.4->1.5, repair_m4b 1.0->1.1, ab_encode 1.0->1.3) and listed combobook.py/AbtoolsGui.py under a non-existent ablib/ path; corrected and added an mcp_server row, then verified every row against the VERSION constant in each file (8/8 match). (3) The claim that '--llm-threshold is accepted for compatibility but the pipeline always uses the 90-point trigger' was false - the flag is live and gates the LLM fallback (default 85, clamped 80-100), while the 90-point trigger only governs MCP refinement; rewrote it and cross-referenced bug.md 2.4 for the hardcoded-70 confirmation gate. (4) The dependency list omitted mcp entirely and did not mention tkinter needing a distro package on Linux; added both plus duckduckgo-search. Also documented the GUI theme system and hover help, relaxed the Python requirement to '3.11 or newer' since 3.14 was verified working, and linked proposal.md from a new Design Proposals section.
- [2026-09-05] FIXED all eight P2 entries in bug.md section 5, each verified. 5.2 ablib/metadata/utils.py: the `[--]` character class was the range '-' to '-' (a plain hyphen) with OPTIONAL surrounding whitespace, so derive_label_hints split inside hyphenated names; now `\s+[-–—]\s+` requires the dash to be a delimiter. Before/after proof: 'Jean-Paul Sartre - Nausea' split to ['Jean','Paul Sartre','Nausea'] and produced NO author, now yields author='Jean-Paul Sartre' title='Nausea'. 5.7 guess_from_path: when there are 2+ segments the title is now always parts[-1] and `combined` is mined only for series metadata - previously a SERIES_PATTERNS match inside the author text overwrote the title with a fragment ('Author - Series 3 Bonus - The Real Title' gave title='Bonus'). 5.1 export_metadata: child.text = str(value), so an int score no longer aborts an otherwise-successful tagging run at the last step. 5.6 write_tags now embeds series-part (TXXX for MP3, ----:com.apple.iTunes:series-part for MP4) - the series position was being resolved and written to metadata.json/book.nfo but never into the audio files. 5.8 choose_meta skips candidates missing title or author before building the dedup key, and returns None on an empty list. 5.4 _parse_provider_query now scans 'by' RIGHT-TO-LEFT and requires a TWO-WORD author; deliberate trade-off recorded in bug.md: a mononym like 'The Iliad by Homer' stays unsplit because a single-word tail is too ambiguous ('Side by Side' would otherwise become title='Side' author='Side'), and searching the full string still matches whereas a wrong split corrupts both fields. 5.3 best_match now walks goodreads/audible/openlib/gbooks in order with an early return at >=85 - openlib and gbooks had NEVER been queried for matching despite the README listing all four, so books they could have matched fell through to the LLM. 5.5 both mcp_server scrapers use params={} instead of interpolating query.replace(' ','+'), which had let '&' in a title truncate the search. Full earlier regression suite (2.1/3.1/3.1b/4.1/4.2/4.4) still passes 8/8.
- [2026-09-05] FIXED bug.md 2.4, 4.3 and 7.4 - the last three open items that affect a normal run. 2.4 ablib/cli/main.py: the low-confidence confirmation gate read `best_score < 70` (hardcoded) while the LLM fallback used the configurable --llm-threshold, so (a) --no was silently a no-op for any match scoring >=70 because the args.no check sat INSIDE that guard, and (b) a match in the 70..threshold band whose LLM fallback failed was tagged with no prompt at all, defeating the flag. Gate now reads `best_score < llm_threshold`; verified across six paths (above-threshold silent tag / --no skip without prompting / accept / decline / --yes bypass / high threshold). Also removed the unreachable `else: Confirm(prompt_message, default=False)` branch - hasattr(Confirm,'ask') is always True for rich's classmethod, the console fallback's staticmethod AND the GUI's _GuiConfirm instance, so that branch was dead and would have raised if reached. NOTE process_leaf still clamps llm_threshold to 80-100, which is documented CLI behaviour, not a bug. 4.3 combobook.safe_move now rmdir's an existing EMPTY directory destination and proceeds, matching what process() already explicitly allowed - the two had contradicted each other and the move died with FileExistsError; a non-empty destination is still refused. 7.4 combobook.dest_path truncates the title to MAX_TITLE_LEN - len(' (YYYY)') and appends the year AFTER, so a 65-char title now yields 'The Extraordinarily Long And Winding Title (2003)' instead of dropping the year (which also risked similar long titles colliding into one folder). Full regression 13/13. Remaining open bugs are all cosmetic, narrow edge cases, or unverifiable from this host (2.3, 4.5, 6.1, 7.3, 8.1, 8.2).
- [2026-09-05] Follow-up logic pass over ablib/ only, found and fixed four bugs neither earlier audit caught (bug.md 5.9-5.12). 5.9 is the significant one: generate_metadata_via_llm fires a SECOND LLM call whose only purpose is to fill optional fields the first response omitted, then did `result = retry_result` - replacing rather than merging, so the retry could leave LESS metadata than before it ran. Reproduced: primary had year/narrator/publisher/description but no series, retry supplied series but omitted the rest, final result lost all four. Now merges with the primary winning conflicts. 5.10: three different bars for accepting an MCP refinement - refine_metadata_via_mcp returned early at >=90 while both callers required >=95 (a third path accepted anything), so a stage-1 result scoring 90-94 skipped SequentialThinking AND was then discarded; unified as exported MCP_ACCEPT_SCORE=95. 5.11: all provider lookups were serial at 10s each, and my own 5.3 fix had made a miss cost up to four chained timeouts; pyflakes flagged ThreadPoolExecutor/as_completed as imported-but-unused in providers/http.py, and README already claimed parallel fetching. Now tier 1 = Goodreads alone with short-circuit at >=85 (keeps the common case one request and is gentle on scraped sites), tier 2 = remaining three concurrent; measured 2.00s vs ~4.0s with 1s stubs. 5.12: MCP_RESULT_CACHE was never cleared, retaining every search result for the process lifetime; capped at 512 with oldest-out eviction. Also fixed the latent 7.5 token-budget shrink while in the file (max() floor so a retry can never reduce the budget) and documented the ablib/cli/__init__.py submodule-shadowing trap in its docstring - I fell into it myself twice this session. pyflakes now clean over ablib/; regression 13/13.
- [2026-09-05] Second follow-up pass over ablib/, two more bugs found and fixed (bug.md 5.13-5.14). 5.13 is the more serious: validate_metadata_fields returned (len(issues)==0, issues), so ANY finding marked metadata invalid - and process_leaf treats invalid metadata as fatal, logging REVIEW and returning WITHOUT TAGGING. So a book with a perfect title and author was refused because its description ran to seven characters; likewise an empty narrator string, a series_index with no series name, or a malformed year. It also fired a pointless MCP refinement for those cosmetic cases. Added FATAL_VALIDATION_ISSUES = {missing_title, missing_author}; `usable` now reflects only those while `issues` still reports everything, and process_leaf prints the rest as 'metadata notes:' and proceeds. 5.14: enrich_metadata_with_providers put `series` in its `needed` set and only stopped when `needed` emptied - but most books are standalone and have no series, so it could never empty, meaning every such book ran Audible + Open Library + Google Books SERIALLY at 10s each hunting a series that does not exist, on top of best_match. Termination is now keyed on author/year alone with series filled opportunistically; verified a book with author+year known makes ZERO provider calls (was three). Regression 15/15, pyflakes clean.
- [2026-09-05] SCOPE DECISION: LLM provider support is LOCAL ONLY. No auth/api_key plumbing in _call_llm, no 'Custom/Remote' provider preset; proposal.md §3.2 and §6 updated accordingly, which removes the auth prerequisite from its Phase 3. Completed proposal.md Phase 1: deleted the no-op tagger_mod.CONFIG block from AbtoolsGui.apply_llm_settings (all five CONFIG references are one singleton, so it was assigning attributes to themselves - verified afterwards that the GUI still drives combobook.tagger.CONFIG and ablib.cli.main.CONFIG, and that disabling still sets endpoint to None). FOUND AND FIXED DURING THAT CLEANUP: the CLI and GUI defaulted to DIFFERENT MODELS - ablib/core/constants.py gave ibm/granite-4-h-tiny while the CLI's --llm-model default was the literal 'mistral-7b-instruct-q4', and argparse always supplies its default, so every CLI run silently overrode the constant while the GUI used it. The CLI's own --help epilog also still advertised port 1234 against a real default of 8888 (same wrong-port bug as the README had). Both argparse defaults now reference constants.DEFAULT_LLM_* and the epilog is an f-string interpolating them, so constants/CLI/GUI/help cannot drift again - verified all four now report the same endpoint and model. This mattered before the model-discovery work because two silently different defaults would have poisoned any before/after model comparison.
- [2026-09-05] Shipped proposal.md Phase 2 (auto-discovery + MRU persistence); MODEL_CHOICES hardcoded list is gone. models_url() derives the probe URL with urlsplit (all five endpoint shapes from proposal §2.4 verified: chat/completions, trailing slash, bare /v1, bare host, path-prefixed). probe_models() runs on a worker thread and posts ('models', (names, error)) to output_queue, with poll_queue applying it on the UI thread - this was the correction the original design sketch missed, since Tkinter is not thread-safe and touching model_combo['values'] from a worker gives intermittent crashes. Triggers: a new refresh button appended to llm_controls (so it greys out with the LLM toggle), <FocusOut> on the endpoint field, and one probe ~300ms after launch. Resolved proposal §6 decision 2 as 'probe at startup', which is safe now scope is local-only: loopback only, worker thread, 4s timeout. Status line shows 'N model(s) available' / 'endpoint unreachable' / "N available - 'x' not among them". MRU via remember_model() called from apply_llm_settings, deduped, most-recent-first, capped at 10, and used as the dropdown fallback whenever the probe fails. The settings file became ONE versioned document (version/theme/llm_endpoint/llm_model/recent_models) through load_settings()/save_settings(**changes) rather than adding a second file, per proposal §3.4; last endpoint and model are restored at startup. Verified against a stub OpenAI-compatible server: populates, offline fallback, mismatch warning, and no probe while the toggle is off. NOTE my first test run showed status stuck on 'checking...' - that was the test's fault, not the code: poll_queue() only starts under __main__, so nothing drained the queue.
- [2026-09-05] GUI usability pass, built around fixing bug.md 2.3 (preview mode inspected nothing). Both main() and the GUI's tag_only() used to short-circuit with `if not commit: print folder name; continue`, so process_leaf never ran and preview showed only paths - no lookups, no proposed tags, no scores. process_leaf now reads `commit` once at the top (defaulting True so callers omitting the flag are unaffected) and withholds ONLY the mutations: write_tags, export_metadata, strip_tags, and the tag_log/review_log writes. Logs record actions taken, so a preview deliberately adds nothing to them. Verified a preview prints guess + per-provider scores + match + 'would tag N file(s): <full metadata summary>' + 'would write metadata.json + book.nfo', while writing no tags, no nfo/json and no log; --commit still writes all three; --striptags previews as 'would strip tags from N file(s)'. Also added session persistence to the existing ~/.abtools_gui.json: source/dest paths (Browse now also opens at the current path), copy/yes/recurse/network/only_src_log/use_llm toggles, timeout/threads/compare_by, endpoint/model, and window geometry, saved via a WM_DELETE_WINDOW handler and restored at startup. DELIBERATE EXCEPTION: `commit` is never persisted - writing to a library must be an explicit choice each run, not something a previous session leaves switched on. Regression green, pyflakes clean.
- [2026-09-05] Shipped proposal.md Phase 4, the configuration cascade: explicit CLI flag / GUI selection > saved GUI settings > ABTOOLS_* environment > constants.py defaults. RuntimeConfig fields now resolve through _env_str/_env_int/_env_bool honouring ABTOOLS_LLM_ENDPOINT, ABTOOLS_LLM_MODEL, ABTOOLS_LLM_TIMEOUT, ABTOOLS_LLM_MAX_TOKENS, ABTOOLS_LLM_API_KEY and ABTOOLS_DEBUG. CRITICAL DETAIL: the CLI's argparse defaults had to move from constants.DEFAULT_* to config.config.*, otherwise argparse would always supply the constant and silently override the environment on every CLI run - the same class of bug as the earlier CLI/GUI default-model mismatch. Verified env alone yields 'from-env' while env plus an explicit flag yields 'from-flag'. Added --show-config, which prints each setting with its source and exits; the API key shows as set/unset and is never printed. Malformed values are reported rather than swallowed (ABTOOLS_LLM_TIMEOUT='abc' is not a whole number; using 90) because a silent fallback leaves the user wondering why a setting had no effect. OPENAI_BASE_URL/OPENAI_MODEL_NAME stay deliberately ignored per proposal §3.5. THE PAYOFF WAS AS PREDICTED: mcp_server/tools/tagger.py already read core_config.config, so it inherited the cascade with zero changes - the MCP server went from having NO configuration path whatsoever (no flags, no env, just whatever constants.py hardcoded) to honouring the environment. Also had to make the CLI's `root` argument optional (nargs='?') so --show-config can run without a path, with an explicit parser.error if root is missing on a normal run.
- [2026-09-05] Two fixes after the user reported an empty GUI log while testing OpenRouter. (1) THE LOG WAS NEVER EMPTY - it was OFF-SCREEN. _fit_notebook sizes the notebook to the visible tab, and Tag & Move needs ~492px against Organise's ~188, so in a fixed-height window the log pane was pushed past the bottom and Tk never mapped it (winfo_ismapped()==0 on Tag & Move, 1 on every other tab) - which is exactly why the user found it 'works if you change tab'. The notebook fit now grows the window when a taller tab needs it, and main row 4 has minsize=150 so the log can never collapse. (2) Chasing that surfaced a second bug: a hardcoded `CONFIG.debug = False` inside tag_only's worker, running AFTER apply_llm_settings had honoured the Debug checkbox, so the checkbox never worked for Tag. Every LLM diagnostic in ablib/metadata/llm.py is gated on CONFIG.debug, so a failing endpoint reported only 'no metadata found'; with it removed an unauthenticated OpenRouter call now prints 'LM Studio returned HTTP 401: No auth credentials found'. Also: added an opt-in 'Remember key' checkbox that stores llm_api_key in ~/.abtools_gui.json (plain text, file chmod 0600, unticking actively DELETES the stored key rather than just stopping writes, and an environment variable still wins over a stored one); and switched duckduckgo_search to ddgs, which had been emitting a RuntimeWarning on every search since the package was renamed - verified the DDGS class and result keys (title/href/body) are identical so the mapping code is unchanged, with a fallback import for installs still on the old package.
- [2026-09-05] Checked whether the Organise operations actually produce the layout Audiobookshelf needs; they do not. Written up as bug.md 4.6-4.9, NOT yet fixed - changing move/rename behaviour on a real library needs the user's go-ahead and a decision on which layout is canonical. 4.6: restructure_for_audiobookshelf.py imports only argparse/shutil/sys/pathlib/typing/re - NO mutagen and NO json - so it physically cannot read embedded tags or metadata.json/book.nfo, and derives everything from the folder name. README claims it 'reads tags from the audio files first, then metadata.json or book.nfo, and finally falls back to folder names'; only the last happens. Reproduced: a book with date=2006 in its tags AND year=2006 in metadata.json came out as 'Unknown - The Final Empire'. 4.7: target_for returns dest_root/author/f'{year} - {title}' with NO series directory, so Author/Series/Book is unreachable; README also claims fuzzy series detection and an --interactive prompt that do not exist (the parser has only --copy/--commit/--version). 4.8: the two organisers emit incompatible conventions for the same book - restructure gives 'Author/Unknown - The Final Empire' while combobook.dest_path gives 'Author/Mistborn/The Final Empire (2006)' - differing in series level, year placement and sort order, so using both leaves a library in two conventions. Recommended fix is one shared destination helper with combobook's layout as canonical. 4.9: export_metadata writes title/author/year/series/series_index while Audiobookshelf's metadata.json uses authors[]/publishedYear/narrators - only title and series overlap, so ABS probably ignores the file and falls back to tags plus folder parsing, which compounds 4.6. NOTE the ABS key names in 4.9 are from recollection, flagged in bug.md as needing confirmation against current ABS docs before writing to that schema.
- [2026-09-05] Modernized GUI visual design, look-and-feel, and color schemes in `AbtoolsGui.py` with ZERO functional modifications (thread handling, CLI args, queues, provider calls, settings persistence strictly preserved). (1) `THEMES`: fixed 5-char hex typo in Gruvbox Dark (`"danger_hover": "#cc241"` -> `"#cc241d"`); re-tuned contrast and elevation hierarchy across all 7 dark palettes; replaced clashing `Color-Meanings` with authentic `Dracula` (`#282a36`, `#bd93f9`) while retaining `THEMES["Color-Meanings"] = THEMES["Dracula"]` alias for backward-compatibility with saved configs; added `GitHub Light` (`#f6f8fa`, `#ffffff`, `#0969da`) for a crisp light mode option. (2) Card framing: added 1px solid hairline border to `Card.TFrame` (`bordercolor=BORDER, relief="solid", borderwidth=1`) to prevent card surfaces melting into window bg; created `CardBody.TFrame` with `borderwidth=0` for inner frames in `card()` to prevent concentric borders; added 1px border to `Badge.TLabel`. (3) Inputs: unified `TCombobox` arrow button background to `FIELD` (eliminating split two-tone background artifact); added accent focus rings to `TEntry`, `TSpinbox`, `TCombobox` with unified `(9, 6)` padding and 1px border. (4) Buttons: standardized padding `(14, 8)` with 1px border across all buttons; `Primary.TButton` given solid `ACCENT` fill with `ON_ACCENT` text; `Danger.TButton` styled as red hairline outline filling red on hover with dynamic `on_danger` contrast. (5) Checkbuttons: added `checkcolor=ON_ACCENT` to `TCheckbutton` and `Bg.TCheckbutton` so checkmarks are razor sharp across all dark/light themes. (6) Tabs, progress bar & logs: active `TNotebook.Tab` elevated with hairline outline; slim `Horizontal.TProgressbar` (`thickness=6`); minimal 10px `Vertical.TScrollbar` with accent hover; `output_text` highlight border set to `ACCENT` and select foreground to `ON_ACCENT`. Verified syntax with `py_compile`. Updated `README.md` and `scaffold.md`.
- [2026-09-05] Fixed glaring white line around tab container reported by user. Empirical analysis of user screenshot (`media_1788603584095.png`) revealed horizontal/vertical line runs at y=36, y=514, x=24, x=693 drawn in `#EEEBE7` (clam theme's built-in default `lightcolor`). Root cause: `style.configure(".")` omitted `bordercolor/lightcolor/darkcolor`, and `TNotebook`'s `Notebook.client` element in clam draws a bevelled client border defaulting to `#EEEBE7`. Fixed in `AbtoolsGui.py` by: (1) configuring `.` with `bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER` preventing clam `#eeebe7`/`#cfcdc8` fallbacks anywhere; (2) configuring `TNotebook` with `bordercolor=BG, lightcolor=BG, darkcolor=BG, borderwidth=0, tabmargins=(0,0,0,0)` and `TNotebook.Tab` borderless `flat` so active tab seamlessly connects directly into the panel body; (3) verified across all 7 dark themes (max bright run dropped from 670px to <21px). Syntax verified with `py_compile`.
- [2026-09-05] Reviewed a proposed standalone-distribution plan (Linux AppImage + Windows portable zip, PyInstaller, bundled FFmpeg) and wrote the assessment to packaging-proposal.md. Architecture is sound; adopt with corrections. BLOCKING ISSUE the plan missed: its core 'zero code duplication' premise says the audio tools just keep calling shutil.which('ffmpeg') and a launcher prepends the bundled bin/ to PATH. True for repair_m4b.py:41 and ab_encode.py:51 (both call it INSIDE a function) but NOT combobook.py:117, which resolves FFMPEG at MODULE level and latches WRITE_TAGS=False permanently when ffmpeg is absent. AbtoolsGui.py:22 imports combobook at module level, so any project import before PATH injection silently disables all tag writing - reproduced: after a late PATH injection shutil.which finds ffmpeg but combobook.FFMPEG stays None and WRITE_TAGS stays False. Same silent-failure class as bug.md 3.1. Fix both ways: defer all project imports in abtools_entry.py until after injection, AND make combobook resolve ffmpeg lazily per call. Other corrections: hidden-import list omits bs4, requests, abclient and the duckduckgo_search fallback (a miss there fails at runtime on the user's machine, not at build time); plan says '8 themes' but there are 9; GitHub retired the ubuntu-20.04 hosted runner so Job 1 will not schedule (run on ubuntu-latest and keep the ubuntu:20.04 CONTAINER, which is what actually pins glibc 2.31); the apprun.sh TCL_LIBRARY/TK_LIBRARY paths (usr/share/tcltk/...) are guessed and not where PyInstaller puts Tcl/Tk - a wrong override can break an otherwise working bundle since PyInstaller's tkinter hook normally handles it; AbtoolsGui SETTINGS_PATH is computed at import from Path.home() so portable-mode redirection needs it made lazy first. UNADDRESSED: no LICENSE file in the repo while bundling GPL static FFmpeg builds - fine privately, blocking for the automated GitHub Release the plan's Stage 5 creates; artifact size ~120-180MB each, and the MCP server drags in starlette/uvicorn/anyio/pydantic/cryptography for a feature most users never start. Also flagged that portable mode would put the settings file - which can now hold an API key when 'Remember key' is ticked - on a USB stick.
- [2026-09-05] FIXED bug.md 4.6, 4.7, and 4.8 (Audiobookshelf canonical output layout and organiser parity). (1) In ablib/core/constants.py, reordered SERIES_PATTERNS so specific indicators (Book <N>, #<N>, Vol <N>) precede generic whitespace-number patterns; previously 'Mistborn Book 1 - ...' matched pattern 1 and swallowed 'Book' into the series name ('Mistborn Book'). (2) In ablib/metadata/utils.py, updated extract_series_and_title to strip delimiter characters (' -_:.,\t') from titles and series names, eliminating dangling separator dashes. Added slug(), truncate_component(), and format_canonical_dest() enforcing Audiobookshelf canonical hierarchy '<dest_root>/<Author>/[Series]/<Title (Year)>' with per-component 50-char truncation, omitting the year suffix when missing/unknown. (3) In ablib/tagging/files.py, added read_tags() (reading ID3/MP4/easy tags incl. TXXX:series and iTunes series) and read_sidecar_metadata() (reading metadata.json supporting both generic and ABS schema keys, plus book.nfo). (4) In combobook.py, refactored dest_path() to delegate to format_canonical_dest(), retaining _truncate() delegating to truncate_component() for backward compatibility. (5) In restructure_for_audiobookshelf.py, updated VERSION to 5.5, parse_book_folder() to return (year, series, title), discover_books() to detect books under nested Author/Series/Book hierarchies as well as flat Author/Book layouts and bare disc subfolders (disc_children/has_audio), and target_for() to resolve metadata in documented priority order (embedded audio tags -> sidecars -> folder/hierarchy heuristics) before calling format_canonical_dest(). Verified with 7-part parity test between combobook.dest_path and restructure.target_for (standalone book with year, series book in folder name, book without year, series in directory hierarchy, tagged MP3, metadata.json sidecar, long title truncation preserving year suffix), plus live dry-run/copy/move/skip integration tests. 100% path parity achieved.
- [2026-09-05] FIXED bug.md 4.9 (metadata.json now conforms to Audiobookshelf's official sidecar schema). In ablib/tagging/files.py, implemented format_abs_metadata() which formats metadata dictionaries into Audiobookshelf's BookMetadata schema: authors[] (array), narrators[] (array), series[] (array of {"name": str, "sequence": Optional[str]}), genres[] (array), publishedYear (4-digit string), publishedDate, publisher, description, isbn, asin, language, and explicit (bool), while retaining top-level convenience keys (author, year, narrator) for backward compatibility with non-ABS tools. Updated export_metadata() to write this Audiobookshelf-compliant payload to metadata.json, while preserving book.nfo XML generation for Kodi/Emby readers. Verified end-to-end: exported metadata.json carries valid arrays and publishedYear, read_sidecar_metadata() round-trips cleanly, and restructure_for_audiobookshelf.target_for() resolves title, author, year, and series directly from the exported sidecar.
- [2026-09-05] Added explicit verification & test procedure notes to bug.md for entries 4.6, 4.7, 4.8, and 4.9, documenting step-by-step reproduction and verification steps (audio tag and sidecar priority resolution, nested series discovery, combobook/restructure path parity test suite, and Audiobookshelf official BookMetadata schema export/roundtrip verification).
- [2026-09-05] Removed outer bounding box lines from card panels in AbtoolsGui.py per user request (media_1788607378105.png red arrows -> media_1788607484838.png green arrow). Configured Card.TFrame and CardBody.TFrame with borderwidth=0, relief="flat", bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE so Status strip, File Paths card, and Log card sit seamlessly on the background without enclosing border outlines, matching the flat borderless framing of the notebook tabs. Verified across all 9 themes.

## 2026-09-05 — combobook is the organiser that actually ran; unmatched now stays put

Investigated `/home/citizenzero/Documents/temp_audiobooks/` after a report that
bugs 4.6-4.9 were not fixed. They were fixed — in
`restructure_for_audiobookshelf.py`. The library was built by **`combobook.py`**
(identified by the `_unmatched/` literal, which exists only at `combobook.py:51`),
which has its own resolver and calls none of the shared helpers.

- Logged **4.10** (P0): `combobook.process()` accepts the first track's
  `artist`+`album` verbatim and short-circuits the folder guess, providers and
  the LLM. Disc markers (`Side 01`) and filenames became author folders.
- Logged **4.11** (P1): `read_tags` prefers `TIT2` (track title) over `TALB`
  (book title), which poisons `restructure.target_for()` from the top of its
  precedence chain.
- Reopened **4.8**: the old "7/7 parity" test compared the two *formatters*
  using a pre-built `Meta`. It never exercised how each tool arrives at that
  `Meta`, which is where they diverge.
- **4.9 re-verified as genuinely fixed.** The old-schema sidecars on disk predate
  the fix and were moved, not rewritten — existing libraries need a re-tag pass.
- Fixed **4.12**: unmatched folders are now left in place; `--move-unmatched` /
  the GUI **Move unmatched** checkbox restores the sweep. combobook -> v1.19.

Diagnostic note: the four `_unmatched` books are genuinely untagged
(`artist=None`), so that failure is folder-parsing, not tagging.
`guess_from_folder()` climbs *parent* directories for the author and cannot read
`Author - Series - Book N - Title` in a flat layout, yielding
`author='Unknown Author'`. `extract_series_and_title()` parses all four correctly
but is never called from combobook.

## 2026-09-05 (later) — 4.8 / 4.10 / 4.11 fixed; resolvers now genuinely shared

Fixed the tag short-circuit and the folder-name blindness together, because
they were the same fault seen from two directions.

- `ablib/metadata/utils.py` gained the shared resolvers: `is_plausible_author`,
  `normalise_author`, `primary_author`, `parse_book_folder_name`. Both
  organisers import them, so 4.8 is closed at the *resolver* level, not just
  the formatter.
- `combobook.process()` treats tags as evidence; an implausible `artist` logs a
  reason and falls through to folder → providers → LLM.
- `read_tags` prefers `TALB`/`©alb` over `TIT2`/`©nam`, plus `strip_track_tail`.
- Rewrote `_similarity`: title and author scored separately. Concatenating them
  meant an unknown author dominated the diff and identical titles scored 0.44.
  Sequence number now rewards a match but never penalises absence — providers
  almost never return an index, so the old -0.12 hit nearly every right answer.
- `--yes` gained `MIN_AUTO_SCORE` (0.75) and an ambiguity guard. Without them it
  accepted the top-ranked candidate at *any* score; a 0.47 match had written a
  wholly unrelated author into the library.
- `tests/test_organiser_resolution.py`: 31 tests from the real tag values,
  starting from files on disk. **`tests/` is in `.gitignore`**, so this suite is
  not currently committed — raised with the user, not changed unilaterally.

Lesson worth keeping: the original 4.8 "7/7 parity" test passed because it
compared two formatters using a pre-built record. A parity test has to start
from the input the tools actually receive — files on disk — or it verifies the
half that was never in doubt.

## 2026-09-05 (final pass) — 4.13 / 4.14 fixed, whole tree lint-clean

Re-audit after the merge of PR #53 turned up two more gaps, both fixes that
had landed in combobook and were never carried across to restructure.

- **4.13**: `discover_books()` assumed a fixed `<Author>/<Book>` depth, so a
  book at the source root -- or the root itself being one book -- was skipped
  silently while the run reported success (`Processed 0 books ... skipped: 0`).
  Now walks `[root, *root.rglob("*")]` like `combobook.leaf_dirs`, deriving the
  author from path depth. 6/6 discovery parity.
- **4.14**: split `target_for` into `resolve_book_metadata()` + `target_for()`
  so `restructure_library` can see the author was never identified and decline
  the move. `--move-unmatched` restores the sweep, same flag name as combobook.

Also: `repair_m4b` gained the `Iterable` import (harmless at runtime thanks to
`from __future__ import annotations` -- 7.1 stays correctly refuted -- but it
was the last static warning), and `ab_encode` lost two function-local imports
shadowing module-level ones. `pyflakes` is now clean across the whole tree.

Verified but NOT changed: multi-disc books were already handled correctly by
the old `discover_books` (I suspected a 4.1-style split and was wrong --
`has_audio` already accounts for bare disc subfolders). Restructuring is
idempotent: a second pass over the output moves nothing.

Test suite is 38 tests, on `main`.

## 2026-09-05 (cleanup) — the last four open entries closed

- **2.2**: `rename_tracks(folder, dry=False)`. Two of its four call sites sit
  inside `if dry:` branches, so a preview renamed the user's source files for
  real. Latent only because `RENAME_TRACKS = False`.
- **6.1**: `--only-src-log` reached `add_argument` and nothing else. Both scan
  functions had always accepted `limit_paths`/`limit_src` and the GUI already
  wired it — only the CLI dropped it. One-place fix.
- **4.15** (new): `export_metadata` wrote the JSON through
  `format_abs_metadata()` but built the NFO from the raw `meta` dict, so one
  book's two sidecars disagreed and pipeline noise (`score`) leaked into the
  XML. Added `build_book_nfo(abs_payload)`; both now derive from one payload.
  NFO keeps Kodi/Jellyfin element names (`<seriesnumber>`, repeated
  `<author>`), which is the convention that actually reads that file.
- **4.16** (new): 4.9 fixed the sidecar *writer*, but sidecars are only written
  at tagging time and the organisers move them without rewriting — so books
  tagged earlier kept the old schema forever. `upgrade_sidecar()` +
  `restructure_for_audiobookshelf.py <lib> --refresh-sidecars`, plus a
  **Refresh Sidecars** button on the GUI Organise tab. `sidecar_is_current()`
  keys off the `authors` array so re-runs skip what is already done.

bug.md now has no open entries. 43 tests, pyflakes clean, all on `main`.

## 2026-09-05 — 6.4: the folder browser was empty on a network share

Reported as "network mounted folder returns no folders". Three faults, all
presenting as an empty browser:

1. `citizenzero@10.10.10.10:/home/citizenzero/bshelf` is an sshfs *source
   string*, not a path. `Path()` reads it as relative, `is_dir()` is False, and
   `choose_directory`'s parent-walk silently landed on `.` -- the working
   directory -- with no message.
2. **The real trap on this machine:** btrfs `@`-subvolume layout. `/home` is
   subvolid 259 (`subvol=/@home`) mounted at `/home`; `/@home` is the same
   subvolume from the root subvolume. Same directory, but only `/home` carries
   mounts -- `/home/citizenzero/pi_share` had 23 entries,
   `/@home/citizenzero/pi_share` had 0. `~/.abtools_gui.json` had
   `"dest": "/@home/..."` saved, and `/` lists `@home` right beside `home`.
3. `populate()` never distinguished empty / files-only / shadowed, and built the
   listing inside one try, so one entry raising OSError (routine on a flaky
   share) discarded everything.

Fixes: `remote_to_mount_point()` (reads /proc/mounts, decodes octal escapes,
matches source exactly or as a parent), `local_path()` as the single place
user text becomes a Path -- so the remote form works in the Source/Destination
fields too, not just the browser -- and `mounted_twin()` comparing parents with
`os.path.samefile` so it does not care what the subvolume is called.

Testing note worth keeping: a symlink CANNOT model a mount. My first attempt
made `/@home/...` a symlink, so both paths were the same inode, `samefile` was
True and the code correctly returned None. Only a mount produces "same parent,
different child", and tests cannot mount -- so that test stubs the parent
identity check and the traversal is what is under test, with the real-system
result recorded in the docstring.

## 2026-09-05 — 4.17: local LLM fallback when the hosted quota runs out

Field report: OpenRouter's free tier returned 429 partway through a run and
every remaining book was abandoned with "no metadata found".

- `_call_llm` now takes an explicit endpoint/model/api_key and reports failures
  through an `on_retryable_failure` out-parameter. **Only** 401/402/403/408/409/
  429/5xx and transport errors are retryable. 400 and 404 are deliberately not:
  a malformed request or missing model fails identically anywhere, and a model
  that merely answered *badly* would answer badly twice.
- `_call_llm_with_fallback()` retries on `llm_fallback_endpoint`. The
  gap-filling retry now stays on whichever endpoint answered — it used to go
  back to the primary and hit the same quota error.
- `_endpoint_label()` names the host. Everything used to say "LM Studio", which
  is why the field report read as though the local server produced the 429.
- **combobook passed no `guess`** to generate_metadata_via_llm, so nothing could
  check an answer. Fixed — without it the gate below can never pass.

The gate the user asked for: a local model asked "which audiobook is this?"
answers confidently either way, and there is no provider score on this path.
`fallback_confidence()` compares title/author against the folder guess
(0.7*title + 0.3*author) and returns **0 when there is nothing to compare
against**, so unverifiable answers are never confident. Below
`llm_fallback_min_score` (85) the book is left untagged with a review-log entry.

Verified with two throwaway HTTP endpoints: local agreeing -> score 100,
accepted; local inventing "The Hobbit" -> score 33, left untagged. One call to
each endpoint, no wasted retries.

Also widened the --show-config columns, which wrapped once the longer
`llm_fallback_*` names appeared.

## 2026-09-05 — 4.18: providers now answer what the LLM was doing

Goal: better initial queries, less LLM. Measured on the user's real
/home/citizenzero/Downloads/Harry Turtledove (15 books):
**14/15 -> 0/15 handed to the LLM**, 3 wrong books -> 0, 91s -> 36s.

Five compounding faults, the first two being the big ones:

1. `guess_from_path` took the **immediate parent as the author**, so
   `Harry Turtledove/Worldwar - Colonization (1994-2004)/8 - Homeward Bound
   (2004)` queried "Worldwar - Colonization" as an author and dropped the year
   and index. That both suppressed correct hits and let unrelated real authors
   win (Homeward Bound by Elaine Tyler May, Aftershocks by Catherine Coulter).
   `combobook.guess_from_folder` had it right via PARENT_RANGE_RX all along --
   the CLI path never did.
2. **Goodreads had never once worked.** The shared SESSION sent
   `python-requests/2.34.2`; Goodreads 403s that, and the helper read `.text`
   with no `raise_for_status()`. Silent, on every book, in the *first* tier.
3. Fixed scoring weights: a perfect title with no author scored 70, under both
   ACCEPT_SCORE and --llm-threshold (both 85). Same class of bug I had already
   fixed in combobook's `_similarity` but not here.
4. Rip debris went into the query ("Daughter of the Empire 128kbps" -> nothing).
5. One query form, one chance.

Operational note worth keeping: **Goodreads throttles with HTTP 202 and an
empty body**, not 403/429 — `raise_for_status()` sails past it. Added a circuit
breaker after 3 consecutive refusals. It works well when fresh (it is the only
provider naming the series inline) but cannot be leaned on for a bulk run;
openlib + audible carried all 15 on their own.

Benchmark script kept at /tmp/claude-1000/bench2.py — worth recreating as a
tests/ opt-in if provider quality regresses again.

## 2026-09-05 — 4.19: one threshold, 83, measured not guessed

User asked "what is the threshold for a good score, 70 to 80?". Measured it
rather than answering from intuition, using real candidates from the audited
library and `score_candidate` (0-100):

    100  correct - exact, superset title, surname-only folder, missing initial
     97  correct, one-character title typo
     81  RIGHT TITLE, WRONG AUTHOR  (Elaine Tyler May / Catherine Coulter / ...)
     78-80  different book, overlapping words
     53-65  wrong book, or query title is a subset of the hit

So **70-80 is exactly the wrong-answer band**; the gap is 81 -> 97 and 83 sits
in it. Set `constants.DEFAULT_MATCH_THRESHOLD = 83` and pointed every decision
at it: ACCEPT_SCORE, --llm-threshold, --auto-accept-score,
llm_fallback_min_score, both GUI spinboxes.

Found while measuring: **combobook graded on a different scale** (0-1
SequenceMatcher blend) whose bands *overlapped* -- correct 0.82-1.00, wrong
0.75-0.79, floor 0.75 sitting inside the wrong band, so `--yes` accepted
wrong-author matches. No number could fix it; the scorer had to go. It now
delegates to the shared `score_candidate`, giving 100 / 81 / 53 and rejecting
what it used to accept.

`MCP_ACCEPT_SCORE` follows the same constant, on the user's instruction, so the
project has exactly one confidence number. Worth remembering that it gates
`calculate_combined_score` -- the model's own self-reported score averaged with
a fuzzy blend including the folder name -- which is NOT the scale the 83 bands
were measured on. Effect: stage-1 MCP refinements scoring 83-94 now get
accepted and skip the SequentialThinking stage instead of being discarded.

Caveat recorded in the docs: with no author known the score saturates at 100
whether right or wrong, because there is nothing left to disagree about. The
ambiguity guard covers that, not the threshold.

---

## [2026-09-06] Encoder: output profiles, and closing the deletion data-loss path

The ask was a default that plays on an iPhone, Android options, and "ensure
that nothing is deleted before verify that the m4b file is correct and not
corrupted". The last clause turned out to be the real work.

**The reported symptom -- "I think it is bypassing some files" -- was exact.**
`EXTENSIONS` had no `.m4b`/`.m4a`, and `main()` only queues a folder when
something in it matches, so a folder of `.m4b` parts produced no task, no
status line, nothing. In the user's own library that hid a two-part book
(`West and East`, `1.m4b` + `2.m4b`) that had never been joined. Not skipped --
invisible. Bug 4.5 had noticed the missing extension in 2026-09-05's audit but
described it as a listing-order problem; the invisibility was the bigger half.

**The data-loss path, reproduced end to end.** `--cleanup` deleted sources on
the strength of `ffprobe format=duration > 0`. Ran the old code over a real
book (`The Big Switch`, 26 MP3s, 4 of them NUL-padded part-downloads):
ffmpeg exit 0, verify_audio True, status "Success". With cleanup on, all 26
originals gone and four chapters unrecoverable. Three separate things had to
be true at once for that: `-fflags +discardcorrupt` told ffmpeg to drop bad
input silently, `stderr=DEVNULL` threw away the explanation, and the exit code
was trusted -- but **ffmpeg returns 0 after "Error submitting packet to
decoder"**, which I verified directly. Now: no tolerance flags, stderr
captured and surfaced as `detail`, and `decodes_cleanly()` judges by *empty
stderr at -v error*, not by returncode. `cleanup` implies `deep_verify` and
cannot be separated from it.

**The subtle one, found because my own test failed for the wrong reason.**
I wrote a fixture that padded a small file with NULs, expecting the decoder to
reject it. It did not: under ffprobe's 5 MB default probesize the junk is
simply skipped, and the file reports a *plausible* codec, sample rate and a
short duration, then decodes without one error. Duration checking cannot help
either, since the sources' own durations are already wrong. What catches it is
**size against the audio it claims to hold** (`duration x bit_rate / 8`).
Measured over all 353 MP3s in the library: every healthy file scored exactly
1.000 (min = p50 = max = 1.000); broken ones score 10+. Limit set at 3.0, plus
a 64 KiB leading-NUL check that needs no probe at all and is the only signal
left when ffprobe cannot describe the file. Damaged folders are now **refused**
rather than half-encoded, naming each file and what is wrong with it.

**Profiles.** One `PROFILES` table in `ab_encode.py`, read by the CLI and the
GUI so they cannot drift. Default `iphone` = AAC-LC `.m4b`, `-profile:a
aac_low` + `+faststart`; verified the output probes as `mp4a.40.2`, which is
AAC-LC exactly. Deliberately chose reach over efficiency: the honest answer is
that the iPhone profile is also the best Android profile, so `android-aac`
differs only in suffix (for Android scanners that ignore `.m4b`) and
`android-opus` is the one genuinely different trade -- half the size, no Apple
decoder, no chapters in Ogg. Chapters are written per source file from title
tags; without them an M4B is one unbroken blob that Apple Books resumes badly.

**A bug I introduced and caught by testing the passthrough for real:** profile
flags were one list, so `-profile:a aac_low` was appended to `-c:a copy`
commands. ffmpeg tries to evaluate `aac_low` as an expression and exits 234 --
so the already-correct-AAC case, the one passthrough exists for, was the one
case that broke. Split into `encoder_flags` / `muxer_flags` with a test that
keeps them apart. Worth noting the new stderr capture is what made this
diagnosable in one run instead of guessing.

Also tightened `_can_stream_copy` to require one sample rate and one channel
count, not just AAC everywhere: the concat demuxer does not renegotiate
between files, so a rate change plays the remainder at the wrong speed at the
*correct* duration -- invisible to any length check.

120 tests, pyflakes clean. `ab_encode` v2.0, GUI v0.18.
