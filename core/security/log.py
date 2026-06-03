"""
Log redaction — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Ensures secrets never appear in logs (SPEC §4.9, ARCHITECTURE §9.4).
"""
from __future__ import annotations

import os

_SECRET_KEYS = {
    "OMISE_SECRET_KEY",
    "OMISE_WEBHOOK_SECRET",
    "CLOUDFLARE_TUNNEL_TOKEN",
    "OBS_WS_PASSWORD",
    "OVERLAY_TOKEN",
}


def safe_event(event_type: str, charge_id: str, **kwargs) -> dict:
    """
    Build a structured log record safe to emit to stdout.
    Excludes donor name/message at info level per ARCHITECTURE §9.4.
    """
    record = {"event": event_type, "charge_id": charge_id}
    # Only include amount and status — never name/message/secret
    for key in ("status", "amount", "error_code", "count"):
        if key in kwargs:
            record[key] = kwargs[key]
    return record


def redact_env_in_str(s: str) -> str:
    """Replace any secret env var values appearing in a string with [REDACTED]."""
    for key in _SECRET_KEYS:
        val = os.environ.get(key, "")
        if val and val in s:
            s = s.replace(val, "[REDACTED]")
    return s
