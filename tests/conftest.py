"""
Test fixtures for security invariant tests.
Uses in-memory SQLite and computed HMAC vectors.

NOTE: These vectors are self-consistency checks — they prove the code is
internally consistent. Ground-truth validation requires a real Omise test-mode
webhook (SPEC §11 step 8 — test with Omise test mode before going live).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Generator

import pytest

# Set test env vars before importing anything that calls secrets.validate()
os.environ.setdefault("OMISE_SECRET_KEY", "skey_test_fixture")
os.environ.setdefault("OMISE_WEBHOOK_SECRET", base64.b64encode(b"test-secret-32-bytes-padding!!").decode())
os.environ.setdefault("CORS_ORIGIN", "https://test.example.com")
os.environ.setdefault("OVERLAY_TOKEN", "test-overlay-token")
os.environ.setdefault("OBS_WS_PASSWORD", "test-obs-password")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DEBUG", "false")

from sqlalchemy import create_engine

from core.db.operations import DBOps
from core.db.schema import init_db
from core.payment.omise import OmiseAdapter


# ── Shared test secret ────────────────────────────────────────────────────────

TEST_SECRET_BYTES = b"test-secret-32-bytes-padding!!"
TEST_SECRET_B64 = base64.b64encode(TEST_SECRET_BYTES).decode()


def make_valid_signature(raw_body: bytes, ts_str: str | None = None) -> tuple[str, str]:
    """Return (timestamp_str, signature_hex) for a valid webhook."""
    if ts_str is None:
        ts_str = str(int(time.time()))
    signed = ts_str.encode() + b"." + raw_body
    sig = hmac.new(TEST_SECRET_BYTES, signed, hashlib.sha256).hexdigest()
    return ts_str, sig


def make_headers(ts_str: str, sig: str) -> dict:
    return {
        "omise-signature-timestamp": ts_str,
        "omise-signature": sig,
        "content-type": "application/json",
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def omise_adapter() -> OmiseAdapter:
    return OmiseAdapter(
        secret_key="skey_test_fixture",
        webhook_secret_b64=TEST_SECRET_B64,
    )


@pytest.fixture
def db() -> Generator[DBOps, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(engine)
    yield DBOps(engine)
    engine.dispose()
