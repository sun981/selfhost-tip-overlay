"""
Stripe adapter unit tests — signature verification + payload normalization.

Self-consistency vectors (same standard as the Omise tests): they prove the scheme
is internally consistent. Ground-truth = a real Stripe test-mode webhook (Stripe CLI
`stripe trigger payment_intent.succeeded`), per SPEC §11.

create_charge / list_recent hit the Stripe API and are covered by a live test-mode
call, not here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from core.payment.base import ReplayError, SignatureError, WebhookEvent
from core.payment.stripe import StripeAdapter

WHSEC = "whsec_test_secret_abc123XYZ"


@pytest.fixture
def stripe_adapter() -> StripeAdapter:
    return StripeAdapter(secret_key="sk_test_dummy", webhook_secret=WHSEC)


def _sign(body: bytes, ts: int | None = None, secret: str = WHSEC) -> dict:
    """Build a valid Stripe-Signature header for `body`."""
    ts = int(time.time()) if ts is None else ts
    signed = f"{ts}".encode() + b"." + body
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={sig}"}


def _succeeded_body(amount: int = 5000) -> bytes:
    return json.dumps({
        "id": "evt_1",
        "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_123",
            "object": "payment_intent",
            "amount": amount,
            "currency": "thb",
            "status": "succeeded",
            "metadata": {"supporter_name": "Carol", "message": "gg"},
            "created": 1780000000,
        }},
    }).encode()


# ── Signature verification ────────────────────────────────────────────────────

class TestStripeSignature:

    def test_good_signature_normalizes(self, stripe_adapter: StripeAdapter):
        """Valid sig → WebhookEvent. The valid sig is computed with the utf-8 whsec key,
        so this also proves the adapter uses whsec as-is (NOT base64-decoded like Omise)."""
        body = _succeeded_body()
        event = stripe_adapter.verify_webhook(body, _sign(body))

        assert isinstance(event, WebhookEvent)
        assert event.kind == "successful"
        assert event.charge_id == "pi_123"
        assert event.amount == 5000
        assert event.currency == "thb"
        assert event.supporter_name == "Carol"
        assert event.message == "gg"
        assert event.source_type == "promptpay"
        assert event.paid_at is None  # handler defaults to now()

    def test_bad_signature_raises(self, stripe_adapter: StripeAdapter):
        body = _succeeded_body()
        headers = {"stripe-signature": f"t={int(time.time())},v1={'0' * 64}"}
        with pytest.raises(SignatureError):
            stripe_adapter.verify_webhook(body, headers)

    def test_tampered_body_rejected(self, stripe_adapter: StripeAdapter):
        body = _succeeded_body(amount=2000)
        headers = _sign(body)  # sign the original
        tampered = _succeeded_body(amount=999999)
        with pytest.raises(SignatureError):
            stripe_adapter.verify_webhook(tampered, headers)

    def test_missing_header_raises(self, stripe_adapter: StripeAdapter):
        with pytest.raises(SignatureError):
            stripe_adapter.verify_webhook(_succeeded_body(), {})

    def test_missing_v1_raises(self, stripe_adapter: StripeAdapter):
        with pytest.raises(SignatureError):
            stripe_adapter.verify_webhook(
                _succeeded_body(), {"stripe-signature": f"t={int(time.time())}"}
            )

    def test_multiple_v1_one_matches(self, stripe_adapter: StripeAdapter):
        """During signing-secret rotation Stripe may send several v1 — pass if any matches."""
        body = _succeeded_body()
        ts = int(time.time())
        signed = f"{ts}".encode() + b"." + body
        good = hmac.new(WHSEC.encode(), signed, hashlib.sha256).hexdigest()
        headers = {"stripe-signature": f"t={ts},v1={'b' * 64},v1={good}"}
        event = stripe_adapter.verify_webhook(body, headers)
        assert event.kind == "successful"


# ── Replay protection ─────────────────────────────────────────────────────────

class TestStripeReplay:

    def test_old_timestamp_rejected(self, stripe_adapter: StripeAdapter):
        body = _succeeded_body()
        old = int(time.time()) - 400  # > 300s window
        with pytest.raises(ReplayError):
            stripe_adapter.verify_webhook(body, _sign(body, ts=old))

    def test_future_timestamp_rejected(self, stripe_adapter: StripeAdapter):
        body = _succeeded_body()
        future = int(time.time()) + 400
        with pytest.raises(ReplayError):
            stripe_adapter.verify_webhook(body, _sign(body, ts=future))


# ── Event-type mapping ────────────────────────────────────────────────────────

class TestStripeEventMapping:

    def _signed(self, payload: dict) -> tuple[bytes, dict]:
        body = json.dumps(payload).encode()
        return body, _sign(body)

    def test_payment_failed_maps_failed(self, stripe_adapter: StripeAdapter):
        body, headers = self._signed({
            "type": "payment_intent.payment_failed",
            "data": {"object": {"id": "pi_f"}},
        })
        event = stripe_adapter.verify_webhook(body, headers)
        assert event.kind == "failed"
        assert event.charge_id == "pi_f"

    def test_canceled_maps_expired(self, stripe_adapter: StripeAdapter):
        body, headers = self._signed({
            "type": "payment_intent.canceled",
            "data": {"object": {"id": "pi_c"}},
        })
        event = stripe_adapter.verify_webhook(body, headers)
        assert event.kind == "expired"

    def test_unknown_type_ignored(self, stripe_adapter: StripeAdapter):
        body, headers = self._signed({
            "type": "charge.refunded",
            "data": {"object": {"id": "pi_r"}},
        })
        event = stripe_adapter.verify_webhook(body, headers)
        assert event.kind == "ignored"
