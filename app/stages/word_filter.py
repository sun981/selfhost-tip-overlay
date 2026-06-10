"""
Word filter stage — Safe Edge.
Masks messages containing banned words.
Configured via settings.json banned_words (user/settings.json overrides the
shipped app/settings.json — see app/settings_loader.py). No code change needed.

Rules:
- Normalize input (lowercase, collapse whitespace) before matching
- On match: replace message with "[กรอง]" (don't DROP — money was paid)
- Never DROP for word filter: streamer already received the tip
"""
from __future__ import annotations

import dataclasses
import re
import unicodedata

from app.settings_loader import load_settings
from contracts.events import TipEvent, StageResult

_settings: dict | None = None
_compiled_patterns: list[re.Pattern] | None = None


def _get_banned_words() -> list[str]:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings.get("banned_words", [])


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, NFC normalize."""
    text = unicodedata.normalize("NFC", text).lower()
    return re.sub(r'\s+', ' ', text).strip()


def _build_patterns(words: list[str]) -> list[re.Pattern]:
    patterns = []
    for word in words:
        if not word.strip():
            continue
        normalized = _normalize(word)
        patterns.append(re.compile(re.escape(normalized), re.IGNORECASE | re.UNICODE))
    return patterns


def _get_patterns() -> list[re.Pattern]:
    global _compiled_patterns
    if _compiled_patterns is None:
        _compiled_patterns = _build_patterns(_get_banned_words())
    return _compiled_patterns


def process(event: TipEvent) -> StageResult:
    """Mask message if it contains a banned word."""
    if not event.message:
        return event

    normalized_msg = _normalize(event.message)
    for pattern in _get_patterns():
        if pattern.search(normalized_msg):
            return dataclasses.replace(event, message="[กรอง]")

    return event
