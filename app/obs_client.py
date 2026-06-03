"""
OBS WebSocket client — Safe Edge.
Live detection: GetStreamStatus → outputActive.
Fail-closed: any error → return False (live=false, form hidden).
Cache 3s to avoid hammering OBS on every live-status poll.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_cache_lock = asyncio.Lock()
_cache_value: Optional[bool] = None
_cache_ts: float = 0.0
_CACHE_TTL = 3.0  # seconds


async def get_live_status() -> bool:
    global _cache_value, _cache_ts

    async with _cache_lock:
        if _cache_value is not None and (time.monotonic() - _cache_ts) < _CACHE_TTL:
            return _cache_value

        result = await _fetch_live_status()
        _cache_value = result
        _cache_ts = time.monotonic()
        return result


async def _fetch_live_status() -> bool:
    try:
        import simpleobsws

        host = os.environ.get("OBS_WS_HOST", "host.docker.internal")
        port = int(os.environ.get("OBS_WS_PORT", "4455"))
        password = os.environ.get("OBS_WS_PASSWORD", "")

        ws = simpleobsws.WebSocketClient(
            url=f"ws://{host}:{port}",
            password=password,
        )
        await asyncio.wait_for(ws.connect(), timeout=3.0)
        await asyncio.wait_for(ws.wait_until_identified(), timeout=3.0)

        request = simpleobsws.Request("GetStreamStatus")
        resp = await asyncio.wait_for(ws.call(request), timeout=3.0)
        await ws.disconnect()

        if resp.ok():
            return bool(resp.responseData.get("outputActive", False))
        return False

    except asyncio.TimeoutError:
        logger.warning("OBS WebSocket timed out — returning live=false (fail-closed)")
        return False
    except Exception as e:
        logger.warning("OBS WebSocket error: %s — returning live=false (fail-closed)", str(e))
        return False
