"""
OBS WebSocket client — Safe Edge.
Direct implementation (obs-websocket v5 protocol) — avoids simpleobsws compat issues.
Fail-closed: any error → return False (live=false, form hidden).
Cache 3s.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from typing import Optional

import websockets

logger = logging.getLogger(__name__)

_cache_lock = asyncio.Lock()
_cache_value: Optional[bool] = None
_cache_ts: float = 0.0
_CACHE_TTL = 3.0


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
        host = os.environ.get("OBS_WS_HOST", "host.docker.internal")
        port = int(os.environ.get("OBS_WS_PORT", "4455"))
        password = os.environ.get("OBS_WS_PASSWORD", "")

        async with websockets.connect(
            f"ws://{host}:{port}",
            open_timeout=3,
            close_timeout=2,
        ) as ws:
            # Step 1: receive Hello
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            if hello.get("op") != 0:
                return False

            # Step 2: build Identify (with auth if required)
            identify: dict = {"op": 1, "d": {"rpcVersion": 1}}

            auth_data = hello.get("d", {}).get("authentication")
            if auth_data and password:
                secret = base64.b64encode(
                    hashlib.sha256((password + auth_data["salt"]).encode()).digest()
                ).decode()
                auth_response = base64.b64encode(
                    hashlib.sha256((secret + auth_data["challenge"]).encode()).digest()
                ).decode()
                identify["d"]["authentication"] = auth_response

            await ws.send(json.dumps(identify))

            # Step 3: receive Identified (op 2)
            identified = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            if identified.get("op") != 2:
                return False

            # Step 4: GetStreamStatus
            await ws.send(json.dumps({
                "op": 6,
                "d": {"requestType": "GetStreamStatus", "requestId": "1"}
            }))

            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            return bool(
                resp.get("d", {}).get("responseData", {}).get("outputActive", False)
            )

    except asyncio.TimeoutError:
        logger.warning("OBS WebSocket timed out — returning live=false (fail-closed)")
        return False
    except Exception as e:
        if "4009" in str(e):
            logger.warning(
                "OBS auth failed (4009): OBS_WS_PASSWORD does not match the password in "
                "OBS → Tools → WebSocket Server Settings (or is empty / auth still "
                "enabled there). Copy 'Show Connect Info' → Server Password into .env, "
                "then `docker compose up -d --force-recreate backend`. "
                "— returning live=false (fail-closed)"
            )
        else:
            logger.warning("OBS WebSocket error: %s — returning live=false (fail-closed)", str(e))
        return False
