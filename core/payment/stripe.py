"""
Stripe payment adapter — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

PromptPay via Stripe, server-side (no Stripe.js — confirmed by spike): a PaymentIntent
is created with confirm=true and returns next_action.promptpay_display_qr_code with a
scannable QR URL, which we proxy like the Omise flow (D2/D10).

Implements the same PaymentGateway interface as OmiseAdapter (ARCHITECTURE §9.5).

⚠️ Signature scheme differs from Omise — do not copy Omise's:
  - header is a single `Stripe-Signature: t=<ts>,v1=<sig>[,v1=<sig2>]` (no separate
    timestamp header)
  - the webhook secret (`whsec_...`) is used **as-is (utf-8)** as the HMAC key —
    NOT base64-decoded (Omise's IS base64)
  - signed payload = `<t>` + "." + `<raw_body>`, HMAC-SHA256 → hex
  Verified against https://docs.stripe.com/webhooks#verify-manually
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

# Shared, gateway-neutral types (ARCHITECTURE §9.5).
from core.payment.base import (
    ChargeData,
    ChargeResult,
    ReplayError,
    SignatureError,
    WebhookEvent,
)


class StripeAdapter:
    """Stripe gateway adapter. Stateless except for injected secrets (never logged)."""

    STRIPE_API = "https://api.stripe.com"
    REPLAY_WINDOW = 300  # seconds — Stripe's default tolerance

    def __init__(
        self, secret_key: str, webhook_secret: str, receipt_email: str = "noreply@example.com"
    ) -> None:
        self._skey = secret_key
        # whsec_... is used as-is as the HMAC key — NOT base64-decoded (unlike Omise).
        self._webhook_key = webhook_secret.encode("utf-8")
        # Stripe REQUIRES billing_details.email for a PromptPay PaymentIntent. We don't
        # collect a donor email (the donor scans the on-screen QR), so a placeholder
        # satisfies the API; the emailed instructions go unused. Overridable in config.
        self._receipt_email = receipt_email

    # ── Webhook verification ────────────────────────────────────────────────

    def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> WebhookEvent:
        """Verify the Stripe signature + replay window, then normalize → WebhookEvent.
        Raises SignatureError / ReplayError (→ 401) on failure."""
        payload = self._verify_signature(raw_body, headers)
        return self._parse_event(payload)

    def _verify_signature(self, raw_body: bytes, headers: Mapping[str, str]) -> dict:
        """
        Signature + replay verification ONLY. Byte-exact, never re-serializes the body.
        Stripe-Signature: `t=<unix>,v1=<hexsig>[,v1=<hexsig2>]`.
        """
        sig_header = headers.get("stripe-signature")
        if not sig_header:
            raise SignatureError("Missing Stripe-Signature header")

        ts_str: str | None = None
        v1_sigs: list[str] = []
        for part in sig_header.split(","):
            key, sep, val = part.partition("=")
            if not sep:
                continue
            key = key.strip()
            val = val.strip()
            if key == "t":
                ts_str = val
            elif key == "v1":
                v1_sigs.append(val)

        if not ts_str or not v1_sigs:
            raise SignatureError("Stripe-Signature missing t or v1")

        try:
            ts_int = int(ts_str)
        except ValueError:
            raise SignatureError("Stripe-Signature timestamp is not a valid integer")

        # Replay window
        if abs(time.time() - ts_int) > self.REPLAY_WINDOW:
            raise ReplayError(
                f"Webhook timestamp {ts_int} is outside ±{self.REPLAY_WINDOW}s window"
            )

        # signed = <timestamp> + "." + <raw_body>; whsec used as-is (not base64)
        signed = ts_str.encode() + b"." + raw_body
        expected = hmac.new(self._webhook_key, signed, hashlib.sha256).hexdigest()

        # Multiple v1 may appear during signing-secret rotation — pass if any matches.
        if not any(hmac.compare_digest(expected, sig) for sig in v1_sigs):
            raise SignatureError("Webhook signature mismatch")

        return json.loads(raw_body)

    @staticmethod
    def _parse_event(payload: dict) -> WebhookEvent:
        """Map a verified Stripe event → gateway-neutral WebhookEvent.

        Stripe carries the PaymentIntent under data.object (not Omise's `data` charge).
        """
        event_type = payload.get("type", "")
        obj = payload.get("data", {}).get("object", {})
        charge_id = obj.get("id", "")  # pi_...

        if event_type == "payment_intent.succeeded":
            metadata = obj.get("metadata") or {}
            return WebhookEvent(
                kind="successful",
                charge_id=charge_id,
                amount=int(obj.get("amount", 0)),
                currency=obj.get("currency", "thb"),
                supporter_name=str(metadata.get("supporter_name", ""))[:50],
                message=str(metadata.get("message", ""))[:200],
                source_type="promptpay",
                # PaymentIntent has no payment timestamp; the handler defaults None → now()
                # (≈ payment time for a real-time succeeded event).
                paid_at=None,
            )

        if event_type == "payment_intent.payment_failed":
            return WebhookEvent(kind="failed", charge_id=charge_id)

        if event_type == "payment_intent.canceled":
            # Canceled PromptPay PI (e.g. QR expired) maps to our "expired" status.
            return WebhookEvent(kind="expired", charge_id=charge_id)

        return WebhookEvent(kind="ignored", charge_id=charge_id)

    # ── Charge creation (server-side PromptPay, no Stripe.js) ────────────────

    def create_charge(
        self,
        amount_satang: int,
        supporter_name: str,
        message: str,
    ) -> ChargeResult:
        """
        Create + confirm a PromptPay PaymentIntent server-side. Returns the scannable
        QR URL from next_action.promptpay_display_qr_code (proxied by /qr, D10).
        """
        # Stripe API is form-encoded; nested fields use bracket keys.
        form = {
            "amount": str(amount_satang),
            "currency": "thb",
            "payment_method_types[]": "promptpay",
            "confirm": "true",
            "payment_method_data[type]": "promptpay",
            "payment_method_data[billing_details][email]": self._receipt_email,
            "metadata[supporter_name]": supporter_name,
            "metadata[message]": message,
        }
        with httpx.Client(
            base_url=self.STRIPE_API,
            auth=(self._skey, ""),  # secret key as HTTP Basic username
            timeout=30.0,
        ) as client:
            resp = client.post("/v1/payment_intents", data=form)
            resp.raise_for_status()
            pi = resp.json()

        qr = (
            pi.get("next_action", {})
            .get("promptpay_display_qr_code", {})
            .get("image_url_png", "")
        )
        if not qr:
            raise ValueError("Stripe PaymentIntent returned no PromptPay QR (next_action missing)")

        return ChargeResult(
            charge_id=pi["id"],
            qr_download_uri=qr,
            status=pi["status"],
            amount=int(pi["amount"]),
            currency=pi["currency"],
        )

    # ── Reconciliation list ──────────────────────────────────────────────────

    def list_recent(self, since: datetime) -> list[ChargeData]:
        """
        Fetch PaymentIntents created since `since` (paginated). Stripe's list has no
        status filter, so the caller filters on ChargeData.status; succeeded PIs are
        normalized to 'successful' to match the rest of the system.
        """
        results: list[ChargeData] = []
        since_ts = int(since.timestamp())

        with httpx.Client(
            base_url=self.STRIPE_API,
            auth=(self._skey, ""),
            timeout=30.0,
        ) as client:
            # expand latest_charge: the PI's `created` is when the QR was shown, not
            # when the donor paid (PromptPay is async). Reconciliation's "too old to
            # push" threshold keys on paid_at — using QR-creation time would silently
            # suppress the overlay for a tip paid minutes ago on an older QR.
            params: dict[str, Any] = {
                "created[gte]": since_ts,
                "limit": 100,
                "expand[]": "data.latest_charge",
            }
            while True:
                resp = client.get("/v1/payment_intents", params=params)
                resp.raise_for_status()
                data = resp.json()

                for pi in data.get("data", []):
                    status = pi.get("status", "")
                    # Normalize Stripe's "succeeded" → our "successful"
                    norm_status = "successful" if status == "succeeded" else status
                    latest_charge = pi.get("latest_charge")
                    paid_ts = (
                        latest_charge.get("created")
                        if isinstance(latest_charge, dict)
                        else None
                    ) or pi.get("created")
                    paid_at = (
                        datetime.fromtimestamp(int(paid_ts), tz=timezone.utc)
                        if paid_ts
                        else None
                    )
                    results.append(ChargeData(
                        charge_id=pi["id"],
                        amount=int(pi.get("amount", 0)),
                        currency=pi.get("currency", "thb"),
                        status=norm_status,
                        metadata=pi.get("metadata") or {},
                        paid_at=paid_at,
                        source_type="promptpay",
                    ))

                if not data.get("has_more"):
                    break
                params["starting_after"] = data["data"][-1]["id"]

        return results

    # ── QR proxy ──────────────────────────────────────────────────────────────

    def proxy_qr(self, download_uri: str) -> tuple[bytes, str]:
        """
        Fetch the QR image (hosted on Stripe's public qr.stripe.com) and return
        (bytes, content_type). No auth header — the URL is public, so the secret key
        is never sent to it.
        """
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(download_uri)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/png").split(";")[0].strip()
            return resp.content, content_type
