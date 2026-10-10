"""Preferences and the current pet lineup, kept across restarts."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CHOICES = {"energy": ("chill", "normal", "hyper"), "size": ("small", "medium", "large")}


@dataclass
class Settings:
    cheer_me_on: bool = True
    quiet: bool = False
    energy: str = "chill"  # chill, normal or hyper (see energy.py)
    size: str = "medium"  # small, medium or large (see size.py)
    seen_home: bool = False  # the home page opened at least once
    sound: bool = False  # home page sound effects
    wardrobe: dict[str, list[str]] = field(default_factory=dict)  # pet id -> accessories worn
    pets: list[dict[str, Any]] = field(default_factory=list)  # who's out: [{"id": ..., "worn": [...]}]


def _names(value: Any) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def _wardrobe(value: Any) -> dict[str, list[str]] | None:
    if not isinstance(value, dict):
        return None
    return {k: names for k, v in value.items() if isinstance(k, str) and (names := _names(v)) is not None}


def _pets(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    out = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append({"id": item["id"], "worn": _names(item.get("worn")) or []})
    return out


def load(path: Path) -> Settings:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    values: dict[str, Any] = {}
    for name, default in asdict(Settings()).items():
        v = data.get(name)
        if isinstance(default, bool):
            ok = isinstance(v, bool)
        elif name in CHOICES:
            ok = v in CHOICES[name]
        elif name == "wardrobe":
            v = _wardrobe(v)
            ok = v is not None
        elif name == "pets":
            v = _pets(v)
            ok = v is not None
        else:
            ok = False
        if ok:
            values[name] = v
    return Settings(**values)


def save(path: Path, settings: Settings) -> None:
    """Write atomically so a crash mid-save can't leave a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
