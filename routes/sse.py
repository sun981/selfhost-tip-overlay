"""
GET /api/events/overlay — SSE stream for overlay.
Token-gated. SSE Last-Event-ID replay on reconnect.
Fresh connection (no Last-Event-ID) = start live, no replay (prevent burst).
"""
from __future__ import annotations

import asyncio
import dataclasses
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app import sse_broadcaster
from contracts.events import OverlayEvent, TipEvent
from core.db.operations import DBOps

logger = logging.getLogger(__name__)
router = APIRouter()


async def _event_generator(
    request: Request,
    last_event_id: str | None,
) -> AsyncGenerator[dict, None]:
    db: DBOps = request.app.state.db

    # Replay missed events if reconnecting
    if last_event_id:
        try:
            last_seq = int(last_event_id)
        except ValueError:
            last_seq = 0

        rows = db.get_since_seq(last_seq, limit=50)
        for row in rows:
            if await request.is_disconnected():
                return
            yield {
                "id": str(row["event_seq"]),
                "data": json.dumps({
                    "charge_id": row["charge_id"],
                    "amount": row["amount"],
                    "supporter_name": row["supporter_name"] or "",
                    "message": row["message"] or "",
                    "event_seq": row["event_seq"],
                }, ensure_ascii=False),
            }

    # Stay live — forward from broadcaster (already {"id","data"}, same shape as replay)
    async for item in sse_broadcaster.subscribe():
        if await request.is_disconnected():
            return
        yield item


@router.get("/api/events/overlay")
async def overlay_sse(request: Request, token: str = ""):
    overlay_token = os.environ.get("OVERLAY_TOKEN", "")
    if not overlay_token or not hmac.compare_digest(
        token.encode("utf-8"), overlay_token.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid token")

    last_event_id = request.headers.get("last-event-id")

    return EventSourceResponse(
        _event_generator(request, last_event_id),
        ping=15,
    )


@router.get("/api/tips/recent")
async def recent_tips(request: Request, after: int = 0, token: str = ""):
    """Backfill endpoint for manual gap recovery. Token-gated."""
    overlay_token = os.environ.get("OVERLAY_TOKEN", "")
    if not overlay_token or not hmac.compare_digest(
        token.encode("utf-8"), overlay_token.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid token")

    db: DBOps = request.app.state.db
    rows = db.get_since_seq(after, limit=50)
    return {"tips": rows}


@router.post("/api/tips/{charge_id}/replay")
async def replay_tip(charge_id: str, request: Request, token: str = ""):
    """
    Manually re-show an already-recorded tip on the overlay (missed render, or "show again").
    Token-gated; local-only (F2 blocks /api/tips/ on the public ingress). Re-broadcasts a
    fresh OverlayEvent built from the stored row — does NOT re-record money or touch pushed_at.
    Runs process_tip so the current word-filter / amount-tier config applies, with the same
    blind-on-crash fallback as the real push path (routes/webhook.py).
    """
    overlay_token = os.environ.get("OVERLAY_TOKEN", "")
    if not overlay_token or not hmac.compare_digest(
        token.encode("utf-8"), overlay_token.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid token")

    db: DBOps = request.app.state.db
    broadcaster = request.app.state.broadcaster
    process_tip = request.app.state.process_tip

    row = db.get_tip(charge_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Tip not found")
    if row["status"] != "successful":
        raise HTTPException(status_code=409, detail="Tip is not in a replayable state")

    paid_at = row.get("paid_at")
    if isinstance(paid_at, str):
        paid_at = datetime.fromisoformat(paid_at.replace("Z", "+00:00"))
    elif paid_at is None:
        paid_at = datetime.now(timezone.utc)

    tip_event = TipEvent(
        charge_id=row["charge_id"],
        amount=row["amount"],
        currency=row["currency"] or "thb",
        supporter_name=row["supporter_name"] or "",
        message=row["message"] or "",
        paid_at=paid_at,
        source_type=row["source_type"] or "promptpay",
    )

    # Same stage run + blind-on-crash fallback as routes/webhook.py _push_tip.
    seq = db.next_seq()
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, process_tip, tip_event), timeout=5.0
        )
    except Exception:
        result = dataclasses.replace(tip_event, message="[ซ่อน]")

    if result == "DROP":
        return {"replayed": False, "result": "DROP", "charge_id": charge_id}
    if result == "HOLD" or not isinstance(result, TipEvent):
        result = tip_event

    overlay_event = OverlayEvent(
        charge_id=tip_event.charge_id,
        amount=tip_event.amount,
        supporter_name=result.supporter_name,
        message=result.message,
        event_seq=seq,
    )
    await broadcaster(overlay_event)
    logger.info("Replayed tip %s as event_seq %s", charge_id, seq)
    return {"replayed": True, "event_seq": seq, "charge_id": charge_id}
