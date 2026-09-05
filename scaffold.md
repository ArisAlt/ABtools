<!-- ABtools/scaffold.md - v2.38 - 2026-09-05 -->
# Audiobook Tagging & Organization - Scaffold

## Project Layout

```
AudioBooks_tools/
|-- ablib/                      # Package powering the CLI, providers, tagging helpers
|   |-- cli/                      # Command-line entry point and option parsing
|   |-- core/                     # Config, constants, console helpers, log writers
|   |-- metadata/                 # LLM + MCP metadata refinement pipeline & canonical dest builder
|   |-- providers/                # HTTP + MCP adapters for book sources
|   `-- tagging/                  # Tag export/strip helpers built on mutagen
|-- AbtoolsGui.py                 # Tkinter GUI front end
|-- combobook.py                  # One-shot tag + restructure orchestrator
|-- repair_m4b.py                 # Repairs zero-length atom failures in M4B/MP4 files
|-- restructure_for_audiobookshelf.py  # Moves books into Audiobookshelf canonical layout
|-- flatten_discs.py              # Collapses Disc 01/Disc 02 style folders
|-- find_duplicates.py            # Hash/name duplicate detector with logs
|-- catalog.py                    # SQLite duplicate catalog helper
|-- abclient.py                   # Feature flag client reading ~/.abclient.json
|-- abclient.json                 # Sample client configuration
|-- search_and_tag.py             # Legacy shim invoking ablib.cli.main
|-- ab_encode.py                  # Audiobook M4B Builder with Auto-Verification & Cleanup
|-- README.md
|-- scaffold.md
|-- bug.md                         # Logic error & bug audit report
|-- proposal.md                    # Design proposal: dynamic LLM model configuration
|-- packaging-proposal.md          # Review of the standalone AppImage / Windows portable plan
|-- requirements.txt
|-- mcp_server/                   # FastMCP server exposing search_* and tag_books tools
|-- output/                       # Optional runtime artifacts (empty by default)
`-- tests/                        # Pytest suite (e.g. web provider smoke tests)
```

## Core Entry Points

- **Tagging CLI (`ablib/cli/main.py`)** drives folder analysis, metadata lookups, optional tag stripping, and writes tags plus Audiobookshelf-compliant `metadata.json` and `book.nfo`. It normalises guesses from folder names, consults multiple providers (Audible, Goodreads, Open Library, Google Books), escalates to LM Studio tooling when confidence drops below 90, and records `tag_log.txt` / `review_log.txt` alongside the selected root.
- **Legacy shim (`search_and_tag.py`)** keeps the historical command name; it simply imports and runs `ablib.cli.main.main()`.
- **`combobook.py`** wraps the CLI to tag audio, then reorganises folders into Audiobookshelf canonical layout `<Author>/[Series]/<Title (Year)>` via the shared `format_canonical_dest` helper. Supports `--commit`, `--copy`, `--yes`, `--move-unmatched`, and embeds tags via FFmpeg so renamed tracks carry metadata. Folders it cannot identify are left in place by default rather than swept into `_unmatched/`.
- **`AbtoolsGui.py`** provides a Tkinter front end with source/library pickers, commit/copy/yes toggles, duplicate scan and restructure actions, adjustable hashing threads and network timeouts, network-share paths resolved to their local mount point, dynamic model auto-discovery, 9 curated dark/light themes with seamless flat card and tab framing, and scrollable log output.
- **`restructure_for_audiobookshelf.py`** reorganises `<source>/<Author>/[Series]/<Book>` folders into `<dest>/<Author>/[Series]/<Title (Year)>` resolving metadata from embedded audio tags, sidecars (`metadata.json`, `book.nfo`), and folder heuristics. Discovers books at any depth, including one sitting at the source root or the root itself. Runs as a dry-run unless `--commit` is supplied, with optional `--copy` and `--move-unmatched` modes. `--refresh-sidecars` rewrites `metadata.json` / `book.nfo` under an existing library in the current schema and moves nothing.
- **`flatten_discs.py`** flattens `Disc 01` style folders into a single directory with sequentially numbered tracks. Preview-only by default; add `--commit` (and optionally `--yes`) to apply changes.
- **`find_duplicates.py`** scans one or two roots, compares by SHA1 hash or filename, writes grouped results to `duplicate_log.txt`, shows progress (with optional `tqdm`), supports per-file timeouts for UNC paths, and parallelises hashing (`--threads`).
- **`repair_m4b.py`** detects the `MP4StreamInfoError` zero-length atom issue and rewrites the file via FFmpeg, keeping a `.bak` when `--overwrite` is used.
- **`catalog.py`** maintains the SQLite database used by duplicate detection.
- **`mcp_server/server.py`** hosts the FastMCP server that powers the LM Studio fallback (`search_*_tool`, `tag_books_tool`).
- **`ab_encode.py`** acts as an Audiobook M4B Builder with Auto-Verification & Cleanup.

## LLM and MCP Metadata Pipeline

- `ablib.metadata.llm` implements staged fallbacks: provider merge (accepts matches >=90), `refine_metadata_via_mcp` for MCP-driven research, a SequentialThinking reasoning pass, and a final tag evaluator that logs confidence scores.
- `ablib.metadata.utils` owns the resolvers both organisers share: `parse_book_folder_name` (reads `<Author> - <Series> - Book <N> - <Title>`), `is_plausible_author` (rejects disc markers, track indices and filename echoes), `normalise_author` and `primary_author`. `ablib.providers.http` and `ablib.providers.mcp` consolidate HTTP requests, scoring, and MCP tool definitions. The MCP prompt enforces running Goodreads before Audible and pulls DuckDuckGo snippets when needed.
- DuckDuckGo search support is enabled by providing `DUCKDUCKGO_MCP` (or the literal "no key required") so the metadata refiner can fetch live web excerpts.
- Experimental behaviour toggles live in `~/.abclient.json` and are loaded through `abclient.AbClient`.

## Configuration and Logging

- `ablib.core.config` exposes runtime configuration shared across modules, including LLM endpoint/model defaults (Granite 4 H Tiny on `http://127.0.0.1:8888`), timeouts, and log locations (`tag_log.txt`, `review_log.txt`).
- `ablib.core.logging` writes timestamped status messages and review entries; GUI and CLI surfaces reuse these helpers.
- `ablib.core.console` wraps rich-printing and interactive confirmations (`--yes` auto accepts prompts).

## Testing and Utilities

- `tests/test_organiser_resolution.py` (46 tests) pins how a book's identity is resolved: the author guard against rip debris, self-describing folder names, album-vs-track titles, and end-to-end parity between the two organisers starting from files on disk.
- The `output/` directory is available for runtime artifacts if needed but is empty by default.
- The MCP server can be launched separately to provide tools to LM Studio, or called programmatically via the fallback pipeline.

## Version Reference

| Component | Version | Location |
|-----------|---------|----------|
| Tagging CLI | 2.30 | `ablib/core/constants.py` |
| combobook | 1.20 | `combobook.py` |
| AbtoolsGui | 0.17 | `AbtoolsGui.py` |
| flatten_discs | 1.5 | `flatten_discs.py` |
| find_duplicates | 0.5 | `find_duplicates.py` |
| abclient | 0.2 | `abclient.py` |
| restructure | 5.8 | `restructure_for_audiobookshelf.py` |
| repair_m4b | 1.1 | `repair_m4b.py` |
| MCP server | 1.1.0 | `mcp_server/server.py` |
| ab_encode | 1.3 | `ab_encode.py` |
