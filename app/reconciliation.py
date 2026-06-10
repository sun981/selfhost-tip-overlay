"""
Reconciliation — runs on backend startup (SPEC §6, ARCHITECTURE §8.4).
Idempotent re-scan: fetches successful charges from Omise and pushes any that
were missed while the backend was down (e.g. machine crash during live stream).

Cursor (recon_state.last_scan_at) bounds how far back we scan — NOT a correctness
mechanism. Idempotency (charge_id PK + pushed_at IS NULL) is the correctness mechanism.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from contracts.events import TipEvent, OverlayEvent
from core.db.operations import DBOps
from core.payment.base import PaymentGateway
from core.security.log import safe_event

logger = logging.getLogger(__name__)

# Charges paid this long before startup won't be pushed to overlay (prevent burst)
# but are still recorded in DB (ARCHITECTURE LOCKED block)
_DEFAULT_RECON_LOOKBACK_HOURS = 24
_OLD_CHARGE_THRESHOLD_SECONDS: int | None = None  # set from settings.json at startup


def set_old_threshold(minutes: int) -> None:
    global _OLD_CHARGE_THRESHOLD_SECONDS
    _OLD_CHARGE_THRESHOLD_SECONDS = minutes * 60


async def run(
    db: DBOps,
    adapter: PaymentGateway,
    broadcaster,
    process_tip,
    startup_time: datetime,
) -> None:
    """Run reconciliation. Called once at backend startup."""
    last_scan = db.get_last_scan_at()

    if last_scan is None:
        lookback = datetime.now(timezone.utc) - timedelta(hours=_DEFAULT_RECON_LOOKBACK_HOURS)
    else:
        lookback = last_scan - timedelta(hours=1)  # 1h buffer for clock drift

    logger.info(
        "Reconciliation: scanning from %s",
        safe_event("recon_start", "n/a", status="running"),
    )

    try:
        charges = adapter.list_recent(since=lookback)
    except Exception as e:
        logger.error("Reconciliation Omise fetch failed: %s", str(e))
        return

    threshold_secs = _OLD_CHARGE_THRESHOLD_SECONDS or 600  # default 10 min

    # Sort by paid_at ascending (ARCHITECTURE §8.4 ORDER BY paid_at)
    charges.sort(key=lambda c: (c.paid_at or datetime.min.replace(tzinfo=timezone.utc)))

    pushed = 0
    recorded = 0

    for charge in charges:
        if charge.status != "successful":
            continue

        paid_at = charge.paid_at or datetime.now(timezone.utc)
        supporter_name = str(charge.metadata.get("supporter_name", ""))[:50]
        message = str(charge.metadata.get("message", ""))[:200]

        # Record (idempotent — skip if already recorded)
        rowcount = db.record_successful(
            charge_id=charge.charge_id,
            amount=charge.amount,
            currency=charge.currency,
            supporter_name=supporter_name,
            message=message,
            source_type=charge.source_type,
            paid_at=paid_at,
        )
        if rowcount:
            recorded += 1

        # Push only if unpushed AND not too old
        age_secs = (startup_time - paid_at.replace(tzinfo=timezone.utc)).total_seconds()
        if age_secs > threshold_secs:
            # Too old: record in DB but mark pushed silently (no overlay burst)
            db.mark_pushed(charge.charge_id)
            continue

        # Process and push (same pipeline as webhook)
        tip_event = TipEvent(
            charge_id=charge.charge_id,
            amount=charge.amount,
            currency=charge.currency,
            supporter_name=supporter_name,
            message=message,
            paid_at=paid_at,
            source_type=charge.source_type,
        )

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
            db.mark_pushed(charge.charge_id)
            continue

        if result == "HOLD" or not isinstance(result, TipEvent):
            result = tip_event

        # Atomic seq alloc + mark pushed (F6); None → already pushed, skip broadcast
        seq = db.mark_pushed(charge.charge_id)
        if seq is not None:
            overlay_event = OverlayEvent(
                charge_id=charge.charge_id,
                amount=charge.amount,
                supporter_name=result.supporter_name,
                message=result.message,
                event_seq=seq,
            )
            await broadcaster(overlay_event)
            pushed += 1

    db.set_last_scan_at(datetime.now(timezone.utc))
    logger.info(
        "Reconciliation done: recorded=%d pushed=%d",
        recorded,
        pushed,
    )
