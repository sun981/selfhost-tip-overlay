"""
Rate limiting — Secure Core.
WARNING: security-critical (SPEC §4.9). Human review required before editing.

A tiny in-process fixed-window limiter exposed as a FastAPI dependency. Chosen over
slowapi on purpose: slowapi's global middleware consumes the request stream (breaks
raw-body webhook signature verify, SPEC §4.1) and its @limiter.limit decorator drops
the endpoint's Pydantic body annotation (FastAPI then 422s every /api/charge). A
dependency runs before the handler, raises 429 when over budget, and never reads the
body. Single-process / single-host per the PoC architecture, so in-memory state is fine.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def cf_key(request: Request) -> str:
    """
    Rate-limit key. Prefers CF-Connecting-IP (set authoritatively by Cloudflare Tunnel —
    the intended deployment, ARCHITECTURE §9 P0#1), then the first X-Forwarded-For hop,
    then the raw socket peer (request.client.host), which a client cannot spoof.

    SECURITY (F7): CF-Connecting-IP and X-Forwarded-For are client-settable headers. They
    are only trustworthy because Cloudflare overwrites CF-Connecting-IP at its edge and the
    origin has no inbound port (tunnel-only). If you fork this and deploy WITHOUT a trusted
    proxy in front, an attacker can rotate those headers to dodge the per-IP limit — the
    socket-peer fallback below keeps the limiter honest in that case, but for real per-client
    limiting you must keep a trusted proxy (Cloudflare/nginx) that sets these.
    """
    ip = request.headers.get("cf-connecting-ip")
    if not ip:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    return ip or "unknown"


class RateLimiter:
    """Fixed sliding window per key. Drive via a plain function dependency below."""

    def __init__(self, max_requests: int, window_secs: int) -> None:
        self._max = max_requests
        self._window = window_secs
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Record a hit for `key`; raise HTTP 429 if it exceeds the window budget."""
        now = time.monotonic()
        dq = self._hits[key]
        cutoff = now - self._window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= self._max:
            raise HTTPException(status_code=429, detail="Too many requests")
        dq.append(now)


# POST /api/charge — the real exposure (creates real Omise charges). SPEC §4.9.
_charge_limiter = RateLimiter(max_requests=30, window_secs=60)


async def charge_rate_limit(request: Request) -> None:
    """FastAPI dependency: 30/min per CF-Connecting-IP on POST /api/charge.
    A plain function (not a callable instance) so FastAPI resolves `request: Request`
    correctly under PEP 563 stringized annotations."""
    _charge_limiter.check(cf_key(request))
