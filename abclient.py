from __future__ import annotations
import json
from pathlib import Path

VERSION = "0.2"
FILE_PATH = Path(__file__).resolve()
VERSION_INFO = f"abclient.py v{VERSION} ({FILE_PATH})"

class AbClient:
    """Simple A/B switch helper.

    Switches are stored in a JSON file. By default this file is
    ``~/.abclient.json`` but an alternative path can be supplied.
    """

    def __init__(self, config: dict | None = None, path: Path | None = None) -> None:
        self.path = path or Path.home() / ".abclient.json"
        self.config = config or {}
        if self.path.exists():
            try:
                self.config.update(json.loads(self.path.read_text()))
            except json.JSONDecodeError:
                pass

    def is_on(self, name: str, default: bool = False, *, internal: bool = False) -> bool:

        return bool(self.config.get(name, default))
