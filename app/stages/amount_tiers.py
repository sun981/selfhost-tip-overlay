"""
Amount tier stage — Safe Edge.
If amount < show_message_min → hide message (don't show on overlay).
Configured via app/settings.json — no code change needed.
"""
from __future__ import annotations

import json
from pathlib import Path

from contracts.events import TipEvent, StageResult

_settings: dict | None = None


def _get_settings() -> dict:
    global _settings
    if _settings is None:
        path = Path(__file__).parent.parent / "settings.json"
        _settings = json.loads(path.read_text()) if path.exists() else {}
    return _settings


def process(event: TipEvent) -> StageResult:
    """Hide message if amount is below the configured tier minimum."""
    settings = _get_settings()
    min_satang = settings.get("amount_tiers", {}).get("show_message_min", 2000)

    if event.amount < min_satang:
        import dataclasses
        return dataclasses.replace(event, message="")

    return event
