"""
Settings resolution — Safe Edge.

Shipped defaults live in app/settings.json (part of the codebase, updated by
releases). User overrides live in user/settings.json (gitignored, mounted into
the container, survives `git pull` / image updates untouched).

Merge is SHALLOW: a top-level key in user/settings.json replaces the shipped
value wholesale — to override anything inside "amount_tiers", copy the whole
"amount_tiers" object.
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SETTINGS_PATH = _ROOT / "app" / "settings.json"
USER_SETTINGS_PATH = _ROOT / "user" / "settings.json"


def _read(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def load_settings() -> dict:
    """Shipped defaults, shallow-overridden by user/settings.json."""
    return {**_read(DEFAULT_SETTINGS_PATH), **_read(USER_SETTINGS_PATH)}
