"""
Charge creation — POST /api/charge
Live gate + validation + Omise server-side charge (D1, D2, SPEC §3).
Amount from server, never trusted from client at overlay (SPEC §4.4).
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app import obs_client
from core.payment.omise import OmiseAdapter
from core.ratelimit import charge_rate_limit
from core.security.log import safe_event

logger = logging.getLogger(__name__)
router = APIRouter()

# Amount limits in satang (SPEC §4.4, ARCHITECTURE LOCKED block)
MIN_AMOUNT_SATANG = 2000       # ฿20 — Omise hard minimum
MAX_AMOUNT_SATANG = 10_000_000  # ฿100,000


class ChargeRequest(BaseModel):
    amount: int          # satang
    currency: str = "thb"
    supporter_name: str = ""
    message: str = ""

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: int) -> int:
        if v < MIN_AMOUNT_SATANG:
            raise ValueError(f"Minimum tip is ฿{MIN_AMOUNT_SATANG // 100}")
        if v > MAX_AMOUNT_SATANG:
            raise ValueError(f"Maximum tip is ฿{MAX_AMOUNT_SATANG // 100:,}")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v.lower() != "thb":
            raise ValueError("Only THB is supported")
        return v.lower()

    @field_validator("supporter_name")
    @classmethod
    def validate_supporter_name(cls, v: str) -> str:
        v = v.strip()[:50]
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()[:200]  # SPEC §4.5, ARCHITECTURE §7
        return v


@router.post("/api/charge")
async def create_charge(
    body: ChargeRequest,
    request: Request,
    _rl: None = Depends(charge_rate_limit),  # SPEC §4.9 — 30/min/IP, raises 429
):
    # Live gate — SPEC §5, D7 (checked at POST /api/charge, not at webhook)
    live = await obs_client.get_live_status()
    if not live:
        raise HTTPException(status_code=403, detail="Streamer is not live")

    adapter: OmiseAdapter = request.app.state.omise
    db = request.app.state.db

    try:
        result = adapter.create_charge(
            amount_satang=body.amount,
            supporter_name=body.supporter_name,
            message=body.message,
        )
    except Exception as e:
        logger.error("Omise charge creation failed: %s", str(e))
        raise HTTPException(status_code=502, detail="Payment service unavailable")

    # Cache QR URI keyed by charge_id (served by /qr endpoint, D10)
    request.app.state.qr_cache[result.charge_id] = result.qr_download_uri

    # Record pending (supporter_name + message written here, round-trip via metadata D3)
    db.upsert_pending(
        charge_id=result.charge_id,
        amount=result.amount,
        currency=result.currency,
        supporter_name=body.supporter_name,
        message=body.message,
        source_type="promptpay",
    )

    logger.info(
        "Charge created: %s",
        safe_event("charge_created", result.charge_id, status="pending", amount=result.amount),
    )

    return {
        "charge_id": result.charge_id,
        "qr_url": f"/api/charge/{result.charge_id}/qr",
        "status": "pending",
        "amount": result.amount,
        "currency": result.currency,
    }


@router.get("/api/charge/{charge_id}/status")
async def get_charge_status(charge_id: str, request: Request):
    """
    Poll charge status from local DB — never hits Omise API.
    Returns only {status, amount} — no name/message (ARCHITECTURE §7 P1#5).
    """
    db = request.app.state.db
    row = db.get_charge_status(charge_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Charge not found")
    return {"status": row["status"], "amount": row["amount"]}


@router.get("/api/charge/{charge_id}/qr")
async def get_qr(charge_id: str, request: Request):
    """Proxy QR PNG from Omise — serves self so CSP img-src 'self' passes (D10)."""
    from fastapi.responses import Response

    db = request.app.state.db
    adapter: OmiseAdapter = request.app.state.omise

    row = db.get_charge_status(charge_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Charge not found")

    # We need the QR URI — store it in app state cache keyed by charge_id
    qr_cache: dict = request.app.state.qr_cache
    qr_uri = qr_cache.get(charge_id)
    if not qr_uri:
        raise HTTPException(status_code=404, detail="QR not available")

    try:
        content, content_type = adapter.proxy_qr(qr_uri)
    except Exception:
        raise HTTPException(status_code=502, detail="QR image unavailable")

    # Served same-origin (satisfies CSP img-src 'self'). Harden the response itself: a strict
    # CSP neutralizes any script if the URL is opened directly (SVG-as-document XSS vector),
    # while the image still renders fine inside the tip page's <img>.
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
