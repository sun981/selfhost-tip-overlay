"""
DEV-ONLY test trigger — fire a test alert through the real tip pipeline, no payment.
Mounted ONLY when env DEV_TEST_TRIGGER=1 (see main.py). Absent in prod → 404.

Token-gated with the same OVERLAY_TOKEN as the SSE endpoint, so enabling the flag
does not open an unauthenticated injector. It still bypasses payment, webhook
signature verify, and the money record — dev only. Unlike a raw broadcast, it runs
process_tip (amount_tiers + word_filter), so a dev fire exercises the same stage
pipeline a real tip would, minus the DB/idempotency layer.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from contracts.events import OverlayEvent, TipEvent

router = APIRouter()


@router.post("/api/dev/test-tip")
async def test_tip(
    request: Request,
    token: str = "",
    name: str = "เทสต์ผู้สนับสนุน",
    amount: int = 4200,  # satang = ฿42.00
    message: str = "ทดสอบระบบแจ้งเตือน 🎉",
):
    """Run a fake tip through process_tip, then broadcast to connected overlays."""
    overlay_token = os.environ.get("OVERLAY_TOKEN", "")
    if not overlay_token or token != overlay_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = request.app.state.db
    broadcaster = request.app.state.broadcaster
    process_tip = request.app.state.process_tip

    amount = int(amount)
    # next_seq() is max(recorded)+1. Dev events are never recorded, so this neither
    # persists nor burns ids (it repeats until a real tip lands) — just a valid SSE id.
    seq = db.next_seq()

    tip_event = TipEvent(
        charge_id=f"dev_test_{seq}",
        amount=amount,
        currency="thb",
        supporter_name=name,
        message=message,
        paid_at=datetime.now(timezone.utc),
        source_type="promptpay",
    )

    # Same stage run + fallback as the real path (routes/webhook.py _push_tip)
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, process_tip, tip_event),
            timeout=5.0,
        )
    except Exception:
        result = dataclasses.replace(tip_event, message="[ซ่อน]")

    if result == "DROP":
        return {"fired": False, "result": "DROP", "event_seq": seq}
    if result == "HOLD" or not isinstance(result, TipEvent):
        result = tip_event

    overlay_event = OverlayEvent(
        charge_id=tip_event.charge_id,
        amount=amount,
        supporter_name=result.supporter_name,
        message=result.message,
        event_seq=seq,
    )
    await broadcaster(overlay_event)
    return {"fired": True, "event_seq": seq, "amount": amount}
