"""
SSE broadcaster — Safe Edge.
In-memory asyncio.Queue per subscriber. Single process only (SQLite single-host).
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from contracts.events import OverlayEvent

_subscribers: list[asyncio.Queue] = []


async def subscribe() -> AsyncGenerator[str, None]:
    """Yield SSE-formatted strings. Caller holds one queue slot per connection."""
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(q)
    try:
        while True:
            event: OverlayEvent = await q.get()
            data = {
                "charge_id": event.charge_id,
                "amount": event.amount,
                "supporter_name": event.supporter_name,
                "message": event.message,
                "event_seq": event.event_seq,
            }
            yield f"id: {event.event_seq}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    finally:
        _subscribers.remove(q)


async def broadcast(event: OverlayEvent) -> None:
    """Push event to all connected overlay subscribers."""
    dead: list[asyncio.Queue] = []
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        if q in _subscribers:
            _subscribers.remove(q)
