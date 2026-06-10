"""
Amount tier stage — Safe Edge.
If amount < show_message_min → hide message (don't show on overlay).
Configured via settings.json (user/settings.json overrides the shipped
app/settings.json — see app/settings_loader.py). No code change needed.
"""
from __future__ import annotations

from app.settings_loader import load_settings
from contracts.events import TipEvent, StageResult

_settings: dict | None = None


def _get_settings() -> dict:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def process(event: TipEvent) -> StageResult:
    """Hide message if amount is below the configured tier minimum."""
    settings = _get_settings()
    min_satang = settings.get("amount_tiers", {}).get("show_message_min", 2000)

    if event.amount < min_satang:
        import dataclasses
        return dataclasses.replace(event, message="")

    return event
