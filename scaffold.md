<!-- ABtools/scaffold.md - v2.31 - 2025-11-06 -->
# Audiobook Tagging & Organization - Scaffold

## Project Layout

```
AudioBooks_tools/
|-- abtools/                      # Package powering the CLI, providers, tagging helpers
|   |-- cli/                      # Command-line entry point and option parsing
|   |-- core/                     # Config, constants, console helpers, log writers
|   |-- metadata/                 # LLM + MCP metadata refinement pipeline
|   |-- providers/                # HTTP + MCP adapters for book sources
|   `-- tagging/                  # Tag export/strip helpers built on mutagen
|-- AbtoolsGui.py                 # Tkinter GUI front end
|-- combobook.py                  # One-shot tag + restructure orchestrator
|-- repair_m4b.py                 # Repairs zero-length atom failures in M4B/MP4 files
|-- restructure_for_audiobookshelf.py  # Moves books into Audiobookshelf layout
|-- flatten_discs.py              # Collapses Disc 01/Disc 02 style folders
|-- find_duplicates.py            # Hash/name duplicate detector with logs
|-- catalog.py                    # SQLite duplicate catalog helper
|-- abclient.py                   # Feature flag client reading ~/.abclient.json
|-- abclient.json                 # Sample client configuration
|-- search_and_tag.py             # Legacy shim invoking abtools.cli.main
|-- README.md
|-- scaffold.md
|-- requirements.txt
|-- mcp_server/                   # FastMCP server exposing search_* and tag_books tools
|-- output/                       # Optional runtime artifacts (empty by default)
`-- tests/                        # Pytest suite (e.g. web provider smoke tests)
```

## Core Entry Points

- **Tagging CLI (`abtools/cli/main.py`)** drives folder analysis, metadata lookups, optional tag stripping, and writes tags plus `metadata.json` / `book.nfo`. It normalises guesses from folder names, consults multiple providers (Audible, Goodreads, Open Library, Google Books), escalates to LM Studio tooling when confidence drops below 90, and records `tag_log.txt` / `review_log.txt` alongside the selected root.
- **Legacy shim (`search_and_tag.py`)** keeps the historical command name; it simply imports and runs `abtools.cli.main.main()`.
- **`combobook.py`** wraps the CLI to tag audio, then reorganises folders into `Author/Year - Title`. Supports `--commit`, `--copy`, `--yes`, and embeds tags via FFmpeg so renamed tracks carry metadata.
- **`AbtoolsGui.py`** provides a Tkinter front end with source/library pickers, commit/copy/yes toggles, duplicate scan and restructure actions, adjustable hashing threads and network timeouts, and LM Studio endpoint/model controls mirroring CLI defaults with scrollable log output.
- **`restructure_for_audiobookshelf.py`** reorganises `<source>/<Author>/<Book>` folders into `<dest>/<Author>/<Year - Title>` using simple year/title heuristics, trimming disc prefixes and tails. Runs as a dry-run unless `--commit` is supplied, with an optional `--copy` mode.
- **`flatten_discs.py`** flattens `Disc 01` style folders into a single directory with sequentially numbered tracks. Preview-only by default; add `--commit` (and optionally `--yes`) to apply changes.
- **`find_duplicates.py`** scans one or two roots, compares by SHA1 hash or filename, writes grouped results to `duplicate_log.txt`, shows progress (with optional `tqdm`), supports per-file timeouts for UNC paths, and parallelises hashing (`--threads`).
- **`repair_m4b.py`** detects the `MP4StreamInfoError` zero-length atom issue and rewrites the file via FFmpeg, keeping a `.bak` when `--overwrite` is used.
- **`catalog.py`** maintains the SQLite database used by duplicate detection.
- **`mcp_server/server.py`** hosts the FastMCP server that powers the LM Studio fallback (`search_*_tool`, `tag_books_tool`).

## LLM and MCP Metadata Pipeline

- `abtools.metadata.llm` implements staged fallbacks: provider merge (accepts matches >=90), `refine_metadata_via_mcp` for MCP-driven research, a SequentialThinking reasoning pass, and a final tag evaluator that logs confidence scores.
- `abtools.providers.http` and `abtools.providers.mcp` consolidate HTTP requests, scoring, and MCP tool definitions. The MCP prompt enforces running Goodreads before Audible and pulls DuckDuckGo snippets when needed.
- DuckDuckGo search support is enabled by providing `DUCKDUCKGO_MCP` (or the literal "no key required") so the metadata refiner can fetch live web excerpts.
- Experimental behaviour toggles live in `~/.abclient.json` and are loaded through `abclient.AbClient`.

## Configuration and Logging

- `abtools.core.config` exposes runtime configuration shared across modules, including LLM endpoint/model defaults (Granite 4 H Tiny on `http://127.0.0.1:8888`), timeouts, and log locations (`tag_log.txt`, `review_log.txt`).
- `abtools.core.logging` writes timestamped status messages and review entries; GUI and CLI surfaces reuse these helpers.
- `abtools.core.console` wraps rich-printing and interactive confirmations (`--yes` auto accepts prompts).

## Testing and Utilities

- `tests/test_web_results.py` exercises provider integrations and ensures scoring stays stable.
- The `output/` directory is available for runtime artifacts if needed but is empty by default.
- The MCP server can be launched separately to provide tools to LM Studio, or called programmatically via the fallback pipeline.

## Version Reference

| Component | Version | Location |
|-----------|---------|----------|
| Tagging CLI | 2.30 | `abtools/core/constants.py` |
| combobook | 1.18 | `combobook.py` |
| AbtoolsGui | 0.17 | `AbtoolsGui.py` |
| flatten_discs | 1.4 | `flatten_discs.py` |
| find_duplicates | 0.5 | `find_duplicates.py` |
| abclient | 0.2 | `abclient.py` |
| MCP server | 1.1.0 | `mcp_server/server.py` |
