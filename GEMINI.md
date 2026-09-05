# ABtools Project Context

This project contains utilities for organizing users' audiobook collections for Audiobookshelf.
It includes:
- Tagging automation using metadata providers (Audible, Goodreads, Google Books, Open Library).
- LLM integration for refining metadata and handling edge cases (with dynamic model auto-discovery and provider presets).
- Duplicate detection and file restructuring tools.
- Audiobook encoding (`ab_encode.py`) with output profiles for iPhone, Android and legacy hardware, chapter marks, and source deletion gated on full verification.
- A GUI front-end (`AbtoolsGui.py`) with 9 curated dark and light themes, seamless flat tab framing, and session persistence.

## Key Files
- `README.md`: usage instructions and CLI reference.
- `scaffold.md`: project structure, entry points, and component version matrix.
- `past_memory.md`: dense historical log of architectural decisions, bug investigations, and modifications.
- `bug.md`: codebase logic error inventory and audit verification tracker.
- `proposal.md`: design proposals and implementation stages (dynamic LLM discovery, config cascade).
- `combobook.py`: main tag + restructure orchestrator.
- `AbtoolsGui.py`: graphical user interface front-end.
- `ablib/`: core logic package (cli, core, metadata, providers, tagging).
- `ab_encode.py`: encoder. Its `PROFILES` table is the single source of the format menu for both the CLI and the GUI.

## User Rules
- Maintain `GEMINI.md` and `past_memory.md`.
- Always keep format of `past_memory.md` dense.
- Always use and update `README.md` and `scaffold.md`.
- Use implementation plans for non-trivial changes.

