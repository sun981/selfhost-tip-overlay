"""
Omise payment adapter — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Implements: verify_webhook, create_charge, list_recent, proxy_qr.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import httpx


# ── Exceptions ──────────────────────────────────────────────────────────────

class SignatureError(Exception):
    """Webhook signature did not match — caller must return 401."""


class ReplayError(Exception):
    """Webhook timestamp outside replay window — caller must return 401."""


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ChargeResult:
    charge_id: str
    qr_download_uri: str
    status: str
    amount: int      # satang
    currency: str


@dataclass
class ChargeData:
    charge_id: str
    amount: int      # satang
    currency: str
    status: str
    metadata: dict[str, Any]
    paid_at: datetime | None
    source_type: str


# ── Adapter ──────────────────────────────────────────────────────────────────

class OmiseAdapter:
    """
    Omise payment gateway adapter.
    All methods are stateless except for injected secrets (never logged).
    """

    OMISE_API = "https://api.omise.co"
    REPLAY_WINDOW = 300  # seconds (±5 min per SPEC §4.2)

    def __init__(self, secret_key: str, webhook_secret_b64: str) -> None:
        self._skey = secret_key
        # Decode once at init, not per-request — b64decode validates format
        try:
            self._webhook_key = base64.b64decode(webhook_secret_b64, validate=True)
        except Exception as exc:
            raise ValueError(
                "OMISE_WEBHOOK_SECRET is not valid base64. "
                "Check the value copied from the Omise dashboard."
            ) from exc

    # ── Webhook verification (SPEC §4.1, §4.2) ─────────────────────────────

    def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> dict:
        """
        Verify Omise webhook signature and replay window.

        Accepts Starlette Headers (case-insensitive) or plain dict with lowercased keys.
        Returns parsed JSON dict on success.
        Raises SignatureError (→ 401) or ReplayError (→ 401) on failure.

        DOES NOT route on event type — that's the handler's job.
        A valid sig on charge.create / refund.* must return 200 from the handler.
        """
        # --- Header extraction (missing or non-numeric → clean 401, not 500) ---
        ts_str = headers.get("omise-signature-timestamp")
        sig_header = headers.get("omise-signature")

        if not ts_str or not sig_header:
            raise SignatureError("Missing Omise-Signature or Omise-Signature-Timestamp header")

        try:
            ts_int = int(ts_str)
        except ValueError:
            raise SignatureError("Omise-Signature-Timestamp is not a valid integer")

        # --- Replay window (SPEC §4.2) ---
        if abs(time.time() - ts_int) > self.REPLAY_WINDOW:
            raise ReplayError(
                f"Webhook timestamp {ts_int} is outside ±{self.REPLAY_WINDOW}s window"
            )

        # --- Signature (SPEC §4.1) ---
        # signed = <timestamp_str_bytes> + b"." + <raw_body>
        # Never decode/re-encode raw_body — byte-exact is required
        signed = ts_str.encode() + b"." + raw_body
        expected = hmac.new(self._webhook_key, signed, hashlib.sha256).hexdigest()

        # Omise-Signature may carry comma-separated sigs during 24h rotation
        provided_sigs = [s.strip() for s in sig_header.split(",") if s.strip()]
        if not provided_sigs:
            raise SignatureError("Omise-Signature header is empty")

        # constant-time compare against each — pass if any matches (SPEC §4.1)
        if not any(hmac.compare_digest(expected, sig) for sig in provided_sigs):
            raise SignatureError("Webhook signature mismatch")

        return json.loads(raw_body)

    # ── Charge creation (SPEC §3, D2) ──────────────────────────────────────

    def create_charge(
        self,
        amount_satang: int,
        supporter_name: str,
        message: str,
    ) -> ChargeResult:
        """
        Create PromptPay source + charge server-side (no Omise.js, D2).
        Returns ChargeResult with charge_id and QR download URI.
        """
        with httpx.Client(
            base_url=self.OMISE_API,
            auth=(self._skey, ""),
            timeout=30.0,
        ) as client:
            # Step 1: create PromptPay source
            source_resp = client.post("/sources", json={
                "type": "promptpay",
                "amount": amount_satang,
                "currency": "thb",
            })
            source_resp.raise_for_status()
            source = source_resp.json()

            # Step 2: create charge from source
            charge_resp = client.post("/charges", json={
                "amount": amount_satang,
                "currency": "thb",
                "source": source["id"],
                "metadata": {
                    "supporter_name": supporter_name,
                    "message": message,
                },
            })
            charge_resp.raise_for_status()
            charge = charge_resp.json()

        qr_uri = (
            charge.get("source", {})
            .get("scannable_code", {})
            .get("image", {})
            .get("download_uri", "")
        )

        return ChargeResult(
            charge_id=charge["id"],
            qr_download_uri=qr_uri,
            status=charge["status"],
            amount=charge["amount"],
            currency=charge["currency"],
        )

    # ── Reconciliation list (SPEC §6) ───────────────────────────────────────

    def list_recent(self, since: datetime) -> list[ChargeData]:
        """
        Fetch successful charges since `since` (paginated).
        Used by reconciliation on startup.
        """
        results: list[ChargeData] = []
        since_ts = int(since.timestamp())

        with httpx.Client(
            base_url=self.OMISE_API,
            auth=(self._skey, ""),
            timeout=30.0,
        ) as client:
            params: dict[str, Any] = {
                "status": "successful",
                "from": since_ts,
                "limit": 100,
            }
            while True:
                resp = client.get("/charges", params=params)
                resp.raise_for_status()
                data = resp.json()

                for charge in data.get("data", []):
                    paid_at = None
                    if charge.get("paid_at"):
                        paid_at = datetime.fromisoformat(
                            charge["paid_at"].replace("Z", "+00:00")
                        )
                    results.append(ChargeData(
                        charge_id=charge["id"],
                        amount=charge["amount"],
                        currency=charge["currency"],
                        status=charge["status"],
                        metadata=charge.get("metadata") or {},
                        paid_at=paid_at,
                        source_type=(
                            charge.get("source", {}).get("type", "promptpay")
                        ),
                    ))

                # Pagination
                if not data.get("pagination", {}).get("has_more", False):
                    break
                params["starting_after"] = data["data"][-1]["id"]

        return results

    # ── QR proxy (D10) ──────────────────────────────────────────────────────

    def proxy_qr(self, download_uri: str) -> tuple[bytes, str]:
        """
        Fetch the QR image from Omise and return (bytes, content_type). Served from our own
        origin so it satisfies the tip/overlay CSP img-src 'self'.

        follow_redirects=True is REQUIRED: Omise's document-download 302-redirects to the
        actual image, and the PromptPay QR is delivered as image/svg+xml (not PNG). httpx
        drops the Authorization header on cross-origin redirects, so the secret key is not
        leaked to the redirect target.
        """
        with httpx.Client(auth=(self._skey, ""), timeout=15.0, follow_redirects=True) as client:
            resp = client.get(download_uri)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/svg+xml").split(";")[0].strip()
            return resp.content, content_type
