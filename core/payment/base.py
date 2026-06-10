"""
Payment gateway contract — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Gateway-neutral types + the PaymentGateway protocol (ARCHITECTURE §9.5, D14).
Each concrete gateway (Omise, Stripe, …) lives in its own module and conforms to
this interface. The rest of the system speaks WebhookEvent / ChargeResult /
ChargeData and never sees a gateway-specific payload shape — so adding a gateway
is a reviewed adapter, not a change to the webhook handler / overlay / DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol


# ── Exceptions (both → 401 at the webhook handler) ───────────────────────────

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


@dataclass
class WebhookEvent:
    """
    Normalized result of verify_webhook — gateway-neutral. The webhook handler
    branches on `kind` only; it never parses a provider payload.

    kind:
      "successful"        → record money + push (other fields populated)
      "failed" | "expired"→ update status only, do not push
      "ignored"           → valid signature but not a completed charge
                            (refund, still-pending, non-charge event) → handler
                            returns 200 and does nothing
    """
    kind: str
    charge_id: str = ""
    amount: int = 0          # satang
    currency: str = "thb"
    supporter_name: str = ""
    message: str = ""
    source_type: str = "promptpay"
    paid_at: datetime | None = None


# ── Gateway interface ─────────────────────────────────────────────────────────

class PaymentGateway(Protocol):
    """
    Stable interface every gateway adapter implements (Secure Core, reviewed).
    Kept to exactly these four methods — a seam, not a framework.
    """

    def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> WebhookEvent:
        """Verify signature + replay window, then normalize → WebhookEvent.
        Raises SignatureError / ReplayError (→ 401) on failure."""
        ...

    def create_charge(
        self, amount_satang: int, supporter_name: str, message: str
    ) -> ChargeResult:
        ...

    def list_recent(self, since: datetime) -> list[ChargeData]:
        ...

    def proxy_qr(self, download_uri: str) -> tuple[bytes, str]:
        ...
