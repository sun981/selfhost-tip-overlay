"""
GET /api/events/overlay — SSE stream for overlay.
Token-gated. SSE Last-Event-ID replay on reconnect.
Fresh connection (no Last-Event-ID) = start live, no replay (prevent burst).
"""
from __future__ import annotations

import json
import logging
import os
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app import sse_broadcaster
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

    # Stay live — forward from broadcaster
    async for raw in sse_broadcaster.subscribe():
        if await request.is_disconnected():
            return
        yield {"data": raw.strip()}


@router.get("/api/events/overlay")
async def overlay_sse(request: Request, token: str = ""):
    overlay_token = os.environ.get("OVERLAY_TOKEN", "")
    if not overlay_token or token != overlay_token:
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
    if not overlay_token or token != overlay_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    db: DBOps = request.app.state.db
    rows = db.get_since_seq(after, limit=50)
    return {"tips": rows}
