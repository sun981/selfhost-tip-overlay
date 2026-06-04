"""
Webhook handler — routes to core security path.
POST /webhooks/omise

Flow (ARCHITECTURE §8.3):
  raw body → verify sig → route event → record money first → push overlay
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from contracts.events import TipEvent, OverlayEvent
from core.payment.omise import OmiseAdapter, ReplayError, SignatureError
from core.security.log import safe_event

logger = logging.getLogger(__name__)
router = APIRouter()


# NOTE: webhook is intentionally NOT rate-limited via slowapi. It is already gated by
# signature verification (cheap 401s), and any slowapi wrapper here risks the raw-body
# read (SPEC §4.1). Rate limiting is applied at POST /api/charge — the real exposure.
@router.post("/webhooks/omise", status_code=200)
async def receive_webhook(request: Request) -> Response:
    adapter: OmiseAdapter = request.app.state.omise
    db = request.app.state.db

    # Read raw body BEFORE any parsing (SPEC §4.1 — never re-serialize)
    raw_body = await request.body()

    # Verify signature — 401 on failure
    try:
        payload = adapter.verify_webhook(raw_body, request.headers)
    except (SignatureError, ReplayError) as e:
        logger.warning("Webhook rejected: %s", str(e))
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Route on event type — valid sig on other events (charge.create, refund.*) → 200
    if payload.get("key") != "charge.complete":
        return Response(status_code=200)

    charge = payload.get("data", {})
    if charge.get("object") != "charge":
        return Response(status_code=200)

    charge_id = charge.get("id", "")
    charge_status = charge.get("status", "")

    if charge_status == "successful":
        # Extract from verified charge object — NEVER from client (SPEC §4.4)
        amount = int(charge.get("amount", 0))
        currency = charge.get("currency", "thb")
        metadata = charge.get("metadata") or {}
        supporter_name = str(metadata.get("supporter_name", ""))[:50]
        message = str(metadata.get("message", ""))[:200]
        source_type = charge.get("source", {}).get("type", "promptpay")

        paid_at_str = charge.get("paid_at")
        paid_at = (
            datetime.fromisoformat(paid_at_str.replace("Z", "+00:00"))
            if paid_at_str
            else datetime.now(timezone.utc)
        )

        # [record] Commit money FIRST — always, before pushing (ARCHITECTURE §8.3.h)
        db.record_successful(
            charge_id=charge_id,
            amount=amount,
            currency=currency,
            supporter_name=supporter_name,
            message=message,
            source_type=source_type,
            paid_at=paid_at,
        )
        logger.info(
            "Recorded: %s",
            safe_event("charge_recorded", charge_id, status="successful", amount=amount),
        )

        # [push] Separate key: pushed_at IS NULL (ARCHITECTURE §6)
        await _push_tip(request, charge_id, amount, currency, supporter_name, message, paid_at, source_type)

    elif charge_status in ("failed", "expired"):
        db.update_status(charge_id, charge_status)

    # Always 200 for verified events (prevents Omise retry on dup)
    return Response(status_code=200)


async def _push_tip(
    request: Request,
    charge_id: str,
    amount: int,
    currency: str,
    supporter_name: str,
    message: str,
    paid_at: datetime,
    source_type: str,
) -> None:
    db = request.app.state.db
    broadcaster = request.app.state.broadcaster
    process_tip = request.app.state.process_tip

    tip_event = TipEvent(
        charge_id=charge_id,
        amount=amount,
        currency=currency,
        supporter_name=supporter_name,
        message=message,
        paid_at=paid_at,
        source_type=source_type,
    )

    # process_tip with timeout — fallback on any failure (P0#3)
    # On crash: blank message so adversarial input that tripped the filter doesn't leak raw
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, process_tip, tip_event),
            timeout=5.0,
        )
    except Exception:
        import dataclasses
        result = dataclasses.replace(tip_event, message="[ซ่อน]")

    if result == "DROP":
        # Money recorded; mark pushed silently — don't show on overlay
        db.mark_pushed(charge_id)
        return

    # HOLD = seam (no-op in PoC) → treat as pass-through
    if result == "HOLD" or not isinstance(result, TipEvent):
        result = tip_event

    # Atomic: allocate event_seq + mark pushed in one step (F6). None → already pushed
    # (concurrent delivery) → do NOT broadcast (prevents double-push).
    seq = db.mark_pushed(charge_id)
    if seq is not None:
        overlay_event = OverlayEvent(
            charge_id=charge_id,
            amount=amount,
            supporter_name=result.supporter_name,
            message=result.message,
            event_seq=seq,
        )
        await broadcaster(overlay_event)
        logger.info("Pushed: %s", safe_event("overlay_pushed", charge_id, amount=amount))
