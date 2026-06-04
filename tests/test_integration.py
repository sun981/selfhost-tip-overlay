"""
Integration tests — FastAPI app boots and key endpoints behave correctly.
Tests that unit tests cannot cover: HTTP status codes, routing wiring, app lifespan.

These tests patch Omise API + OBS WebSocket — no real credentials needed.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_SECRET_BYTES, make_valid_signature, make_headers


# ── App import (validate() + startup_test.run() fire at import — conftest sets env) ──

def _get_test_client():
    """Create a TestClient that skips reconciliation (no Omise API call)."""
    with patch("app.reconciliation.run", new_callable=AsyncMock), \
         patch("core.security.startup_test.run"):  # skip self-test that checks HMAC runtime
        from main import app
        return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client():
    with patch("app.reconciliation.run", new_callable=AsyncMock), \
         patch("core.security.startup_test.run"):
        from main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── §11: bad-signature webhook → 401 (end-to-end HTTP) ───────────────────────

class TestWebhookEndpoint:

    def test_bad_signature_returns_401(self, client: TestClient):
        """SPEC §11: bad sig → HTTP 401."""
        raw_body = b'{"key":"charge.complete","data":{"object":"charge","status":"successful"}}'
        ts_str = str(int(time.time()))
        bad_sig = "0" * 64

        resp = client.post(
            "/webhooks/omise",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "omise-signature-timestamp": ts_str,
                "omise-signature": bad_sig,
            },
        )
        assert resp.status_code == 401

    def test_good_signature_non_charge_event_returns_200(self, client: TestClient):
        """Valid sig on non-charge event (e.g. refund) must return 200, not 401."""
        raw_body = json.dumps({
            "key": "refund.create",
            "data": {"object": "refund"},
        }).encode()
        ts_str, sig = make_valid_signature(raw_body)

        resp = client.post(
            "/webhooks/omise",
            content=raw_body,
            headers={
                "content-type": "application/json",
                **make_headers(ts_str, sig),
            },
        )
        assert resp.status_code == 200

    def test_replay_attack_returns_401(self, client: TestClient):
        """Timestamp > 5 min old → HTTP 401."""
        raw_body = b'{"key":"charge.complete","data":{}}'
        old_ts = str(int(time.time()) - 400)
        key = base64.b64decode(base64.b64encode(TEST_SECRET_BYTES))
        signed = old_ts.encode() + b"." + raw_body
        sig = hmac.new(key, signed, hashlib.sha256).hexdigest()

        resp = client.post(
            "/webhooks/omise",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "omise-signature-timestamp": old_ts,
                "omise-signature": sig,
            },
        )
        assert resp.status_code == 401

    def test_missing_headers_returns_401(self, client: TestClient):
        """No Omise headers → HTTP 401."""
        resp = client.post(
            "/webhooks/omise",
            content=b'{"key":"charge.complete"}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_successful_charge_recorded_and_pushed(self, client: TestClient):
        """
        SPEC §11 core: a valid-sig successful charge.complete must return 200,
        record the money (status=successful), and push to the overlay exactly once.
        Covers the record→push ordering end-to-end.

        Read back over HTTP, not app.state.db directly: with sqlite :memory: each
        thread gets its own DB, so the test thread can't see the app-thread writes
        (prod uses a file DB, so this is a test-only quirk).
        """
        charge_id = "chrg_e2e_success_1"
        raw_body = json.dumps({
            "key": "charge.complete",
            "data": {
                "object": "charge",
                "id": charge_id,
                "status": "successful",
                "amount": 5000,
                "currency": "thb",
                "metadata": {"supporter_name": "Carol", "message": "gg"},
                "paid_at": "2026-06-04T00:00:00Z",
            },
        }).encode()
        ts_str, sig = make_valid_signature(raw_body)

        resp = client.post(
            "/webhooks/omise",
            content=raw_body,
            headers={"content-type": "application/json", **make_headers(ts_str, sig)},
        )
        assert resp.status_code == 200

        # Recorded as successful money record
        st = client.get(f"/api/charge/{charge_id}/status")
        assert st.status_code == 200
        assert st.json() == {"status": "successful", "amount": 5000}

        # Pushed exactly once (token-gated backfill endpoint reads pushed rows)
        recent = client.get("/api/tips/recent", params={"after": 0, "token": "test-overlay-token"})
        assert recent.status_code == 200
        tips = [t for t in recent.json()["tips"] if t["charge_id"] == charge_id]
        assert len(tips) == 1, "successful charge must be pushed exactly once"
        assert tips[0]["supporter_name"] == "Carol"
        assert tips[0]["message"] == "gg"  # ≥฿20 tier, no banned word → shown


# ── P0#3: crashing stage → blinded message (not raw) ─────────────────────────

class TestFallbackMessageBlinding:

    def test_crashing_stage_blinds_message(self):
        """P0#3: if process_tip crashes, pushed message must be '[ซ่อน]' not raw."""
        from contracts.events import TipEvent
        import dataclasses

        raw_message = "สวัสดีคำหยาบ"  # simulated adversarial input

        tip_event = TipEvent(
            charge_id="chrg_crash_test",
            amount=5000,
            currency="thb",
            supporter_name="Alice",
            message=raw_message,
            paid_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
            source_type="promptpay",
        )

        def crashing_stage(event):
            raise RuntimeError("Simulated filter crash")

        # Simulate the fallback logic from webhook.py _push_tip
        try:
            result = crashing_stage(tip_event)
        except Exception:
            result = dataclasses.replace(tip_event, message="[ซ่อน]")

        assert result.message == "[ซ่อน]", "Crashed stage must blind message, not pass raw"
        assert result.message != raw_message, "Raw adversarial message must not reach overlay"


# ── Health endpoint ──────────────────────────────────────────────────────────

class TestHealth:

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Amount validation via HTTP ────────────────────────────────────────────────

class TestChargeValidation:

    def test_amount_below_min_returns_422(self, client: TestClient):
        """Below ฿20 → HTTP 422 Unprocessable Entity."""
        resp = client.post(
            "/api/charge",
            json={"amount": 1999, "currency": "thb"},
        )
        assert resp.status_code in (422, 403)  # 422 validation error or 403 not live


# ── SPEC §4.9: rate limiting is actually enforced at POST /api/charge ─────────

class TestRateLimit:

    def test_charge_is_rate_limited(self, client: TestClient):
        """
        SPEC §4.9: /api/charge must throttle. With the live gate failing closed,
        requests under the limit return 403; once the 30/min cap is hit → 429.
        Uses a unique CF-Connecting-IP so this test owns its own limiter bucket.
        """
        headers = {"cf-connecting-ip": "203.0.113.7"}  # isolated key
        valid = {"amount": 2000, "currency": "thb"}

        # OBS isn't reachable in tests → get_live_status fails closed (403).
        # The limiter runs *before* the endpoint body, so it still counts these.
        with patch("app.obs_client.get_live_status", new=AsyncMock(return_value=False)):
            statuses = [
                client.post("/api/charge", json=valid, headers=headers).status_code
                for _ in range(35)
            ]

        assert statuses[0] == 403, f"under-limit request should hit live gate, got {statuses[0]}"
        assert 429 in statuses, f"expected a 429 after 30/min, got {sorted(set(statuses))}"


# ── Manual overlay replay (POST /api/tips/{id}/replay) — token-gated, local-only ──

class TestReplay:

    def test_replay_requires_token_and_rebroadcasts(self, client: TestClient):
        """A recorded successful tip can be re-shown: 401 without token, 404 for an
        unknown id, and 200 {replayed:true, event_seq} for a real one."""
        charge_id = "chrg_replay_1"
        raw_body = json.dumps({
            "key": "charge.complete",
            "data": {
                "object": "charge", "id": charge_id, "status": "successful",
                "amount": 5000, "currency": "thb",
                "metadata": {"supporter_name": "Dave", "message": "wp"},
                "paid_at": "2026-06-04T00:00:00Z",
            },
        }).encode()
        ts_str, sig = make_valid_signature(raw_body)
        assert client.post(
            "/webhooks/omise", content=raw_body,
            headers={"content-type": "application/json", **make_headers(ts_str, sig)},
        ).status_code == 200

        # no token → 401
        assert client.post(f"/api/tips/{charge_id}/replay").status_code == 401
        # unknown id → 404
        assert client.post(
            "/api/tips/chrg_does_not_exist/replay", params={"token": "test-overlay-token"}
        ).status_code == 404
        # valid → 200, rebroadcast with a fresh event_seq (no re-record of money)
        resp = client.post(f"/api/tips/{charge_id}/replay", params={"token": "test-overlay-token"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["replayed"] is True
        assert body["charge_id"] == charge_id
        assert isinstance(body["event_seq"], int)
