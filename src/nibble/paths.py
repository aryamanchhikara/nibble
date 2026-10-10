"""Where nibble keeps its files. NIBBLE_HOME overrides it (tests, development)."""

from __future__ import annotations

import os
from pathlib import Path


def app_support() -> Path:
    override = os.environ.get("NIBBLE_HOME")
    path = Path(override) if override else Path.home() / "Library" / "Application Support" / "nibble"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return app_support() / "settings.json"
