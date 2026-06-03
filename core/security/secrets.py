"""
Secret validation — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Validates required env vars at startup. Never logs secret values.
"""
from __future__ import annotations

import os
import sys

# Values that indicate a placeholder — refuse to start
_PLACEHOLDERS = {
    "CHANGEME", "changeme", "xxx", "XXX", "your_secret_here",
    "...", "replace_me", "REPLACE_ME", "TODO", "todo",
    "skey_test_CHANGEME", "skey_live_CHANGEME",
}

_REQUIRED = [
    "OMISE_SECRET_KEY",
    "OMISE_WEBHOOK_SECRET",
    "CORS_ORIGIN",
    "OVERLAY_TOKEN",
    "OBS_WS_PASSWORD",
]


class SecretError(Exception):
    pass


def validate() -> None:
    """
    Check all required env vars are present and not placeholders.
    Calls sys.exit with a descriptive message on failure (secure by default).
    Never logs the secret values themselves.
    """
    missing = []
    placeholder = []

    for key in _REQUIRED:
        val = os.environ.get(key, "").strip()
        if not val:
            missing.append(key)
        elif val in _PLACEHOLDERS or val.startswith("CHANGEME"):
            placeholder.append(key)

    errors: list[str] = []
    if missing:
        errors.append(f"Missing required env vars: {', '.join(missing)}")
    if placeholder:
        errors.append(
            f"Env vars still have placeholder values: {', '.join(placeholder)}. "
            "Edit your .env file."
        )

    if errors:
        msg = "\n".join(errors)
        print(f"\n[STARTUP ERROR] Secret validation failed:\n{msg}\n", flush=True)
        sys.exit(1)

    # CORS must not be wildcard (SPEC §4.7)
    cors = os.environ.get("CORS_ORIGIN", "")
    if cors.strip() == "*":
        print("[STARTUP ERROR] CORS_ORIGIN must not be '*'. Set it to your exact domain.", flush=True)
        sys.exit(1)

    # Debug must be off in production
    debug = os.environ.get("DEBUG", "false").lower()
    if debug in ("1", "true", "yes"):
        print(
            "[STARTUP WARNING] DEBUG=true detected. "
            "This is unsafe in production — set DEBUG=false.",
            flush=True,
        )


def get(key: str) -> str:
    """Return env var value. Raises SecretError if missing (for use after validate())."""
    val = os.environ.get(key, "").strip()
    if not val:
        raise SecretError(f"Env var {key!r} is not set (call validate() at startup)")
    return val
