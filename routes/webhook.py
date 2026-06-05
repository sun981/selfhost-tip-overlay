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
from core.payment.base import PaymentGateway, ReplayError, SignatureError
from core.security.log import safe_event

logger = logging.getLogger(__name__)
router = APIRouter()


# NOTE: webhook is intentionally NOT rate-limited via slowapi. It is already gated by
# signature verification (cheap 401s), and any slowapi wrapper here risks the raw-body
# read (SPEC §4.1). Rate limiting is applied at POST /api/charge — the real exposure.
@router.post("/webhooks/omise", status_code=200)
async def receive_webhook(request: Request) -> Response:
    gateway: PaymentGateway = request.app.state.gateway
    db = request.app.state.db

    # Read raw body BEFORE any parsing (SPEC §4.1 — never re-serialize)
    raw_body = await request.body()

    # Verify signature + normalize to a gateway-neutral event — 401 on failure.
    # All provider-specific payload parsing lives in the adapter (ARCHITECTURE §9.5).
    try:
        event = gateway.verify_webhook(raw_body, request.headers)
    except (SignatureError, ReplayError) as e:
        logger.warning("Webhook rejected: %s", str(e))
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Amount/name/message come from the verified event only — never the client (SPEC §4.4)
    if event.kind == "successful":
        paid_at = event.paid_at or datetime.now(timezone.utc)

        # [record] Commit money FIRST — always, before pushing (ARCHITECTURE §8.3.h)
        db.record_successful(
            charge_id=event.charge_id,
            amount=event.amount,
            currency=event.currency,
            supporter_name=event.supporter_name,
            message=event.message,
            source_type=event.source_type,
            paid_at=paid_at,
        )
        logger.info(
            "Recorded: %s",
            safe_event("charge_recorded", event.charge_id, status="successful", amount=event.amount),
        )

        # [push] Separate key: pushed_at IS NULL (ARCHITECTURE §6)
        await _push_tip(
            request, event.charge_id, event.amount, event.currency,
            event.supporter_name, event.message, paid_at, event.source_type,
        )

    elif event.kind in ("failed", "expired"):
        db.update_status(event.charge_id, event.kind)

    # Always 200 for verified events (ignored kinds too) — prevents gateway retry on dup
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
