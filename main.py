"""
Tip Overlay System — FastAPI entry point.
Startup order: validate secrets → self-test → init DB → run reconciliation → serve.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

# ── Secret validation + self-test (before anything else) ────────────────────
from core.security import secrets, startup_test

secrets.validate()
startup_test.run()

# ── After validation: import everything else ────────────────────────────────
from core.db.operations import DBOps
from core.db.schema import create_engine_for_url, init_db
from core.payment.omise import OmiseAdapter
from app import sse_broadcaster, reconciliation
from routes import charge as charge_route
from routes import live_status as live_route
from routes import sse as sse_route
from routes import webhook as webhook_route

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# ── Settings (config-over-code, ARCHITECTURE §13.2) ─────────────────────────

from app.settings_loader import load_settings

SETTINGS = load_settings()


# Rate limiter lives in core/ratelimit.py (shared with routes for @limiter.limit).
# Enforced per-route via decorators — NOT global middleware (SPEC §4.9, see core/ratelimit).


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init DB
    db_url = os.environ.get("DATABASE_URL", "sqlite:////data/tips.db")
    engine = create_engine_for_url(db_url)
    init_db(engine, db_url)
    db = DBOps(engine)

    # Init payment gateway adapter (Secure Core) — selected by PAYMENT_GATEWAY.
    # if/else over two reviewed adapters, not a registry (seam, not framework).
    gateway_name = os.environ.get("PAYMENT_GATEWAY", "omise").strip().lower()
    if gateway_name == "stripe":
        from core.payment.stripe import StripeAdapter
        gateway = StripeAdapter(
            secret_key=secrets.get("STRIPE_SECRET_KEY"),
            webhook_secret=secrets.get("STRIPE_WEBHOOK_SECRET"),
        )
    else:
        gateway = OmiseAdapter(
            secret_key=secrets.get("OMISE_SECRET_KEY"),
            webhook_secret_b64=secrets.get("OMISE_WEBHOOK_SECRET"),
        )

    # process_tip (Safe Edge — loaded here to avoid core importing app)
    from app.process_tip import process_tip

    # Set reconciliation threshold from settings
    old_threshold = SETTINGS.get("recon_old_threshold_minutes", 10)
    reconciliation.set_old_threshold(old_threshold)

    # Wire state — `gateway` is the active PaymentGateway adapter (selected above).
    app.state.gateway = gateway
    app.state.db = db
    app.state.broadcaster = sse_broadcaster.broadcast
    app.state.process_tip = process_tip
    app.state.qr_cache = {}  # charge_id → qr_download_uri (ephemeral, lost on restart)

    # Run reconciliation on startup (SPEC §6)
    startup_time = datetime.now(timezone.utc)
    asyncio.create_task(
        reconciliation.run(
            db=db,
            adapter=gateway,
            broadcaster=sse_broadcaster.broadcast,
            process_tip=process_tip,
            startup_time=startup_time,
        )
    )

    # Privacy purge (CLAUDE.md default 90d) — strip name/message from old rows.
    # Implemented in DBOps.purge_old; scheduled here so the retention promise is real.
    purge_days = int(SETTINGS.get("privacy_purge_days", 90))

    async def _purge_loop() -> None:
        while True:
            try:
                before = datetime.now(timezone.utc) - timedelta(days=purge_days)
                n = db.purge_old(before)
                if n:
                    logger.info("Privacy purge: cleared PII from %d old record(s)", n)
            except Exception as e:
                logger.error("Privacy purge failed: %s", str(e))
            await asyncio.sleep(86400)  # daily

    purge_task = asyncio.create_task(_purge_loop())

    yield  # serve

    purge_task.cancel()

    # Cleanup
    engine.dispose()


# ── Application ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Tip Overlay System",
    docs_url=None,    # disable Swagger UI in production
    redoc_url=None,
    lifespan=lifespan,
)

# CORS — explicit domain only, never * (SPEC §4.7)
cors_origin = os.environ.get("CORS_ORIGIN", "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[cors_origin] if cors_origin else [],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Last-Event-ID"],
    allow_credentials=False,
)

# Rate limiting (SPEC §4.9) is applied as a FastAPI dependency on POST /api/charge
# (see routes/charge.py + core/ratelimit.py). No global middleware — it would consume
# the webhook raw body and break signature verification (SPEC §4.1).

# Routes
app.include_router(webhook_route.router)
app.include_router(charge_route.router)
app.include_router(live_route.router)
app.include_router(sse_route.router)

# DEV-only test trigger — mounted ONLY when explicitly enabled (never in prod).
# Lets you fire a fake overlay alert without a payment. See routes/dev.py.
if os.environ.get("DEV_TEST_TRIGGER") == "1":
    from routes import dev as dev_route
    app.include_router(dev_route.router)
    logger.warning(
        "DEV_TEST_TRIGGER=1 — POST /api/dev/test-tip is LIVE (bypasses payment). "
        "Never enable this in production."
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
