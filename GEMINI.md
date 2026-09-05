# ABtools Project Context

This project contains utilities for organizing users' audiobook collections for Audiobookshelf.
It includes:
- Tagging automation using metadata providers (Audible, Goodreads, Google Books, Open Library).
- LLM integration for refining metadata and handling edge cases (with dynamic model auto-discovery and provider presets).
- Duplicate detection and file restructuring tools.
- A GUI front-end (`AbtoolsGui.py`) with 8 curated dark and light themes, seamless flat tab framing, and session persistence.

## Key Files
- `README.md`: usage instructions and CLI reference.
- `scaffold.md`: project structure, entry points, and component version matrix.
- `past_memory.md`: dense historical log of architectural decisions, bug investigations, and modifications.
- `bug.md`: codebase logic error inventory and audit verification tracker.
- `proposal.md`: design proposals and implementation stages (dynamic LLM discovery, config cascade).
- `combobook.py`: main tag + restructure orchestrator.
- `AbtoolsGui.py`: graphical user interface front-end.
- `ablib/`: core logic package (cli, core, metadata, providers, tagging).

## User Rules
- Maintain `GEMINI.md` and `past_memory.md`.
- Always keep format of `past_memory.md` dense.
- Always use and update `README.md` and `scaffold.md`.
- Use implementation plans for non-trivial changes.

