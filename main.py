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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

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

def _load_settings() -> dict:
    settings_path = Path(__file__).parent / "app" / "settings.json"
    if settings_path.exists():
        return json.loads(settings_path.read_text())
    return {}


SETTINGS = _load_settings()


# ── Rate limiter (SPEC §4.9, ARCHITECTURE §9) ────────────────────────────────
# Key = CF-Connecting-IP (from Cloudflare Tunnel, ARCHITECTURE §9 P0#1)
# If header absent = request not from tunnel → reject

def _cf_key(request: Request) -> str:
    ip = request.headers.get("cf-connecting-ip")
    if not ip:
        ip = request.headers.get("x-forwarded-for", "")
        ip = ip.split(",")[0].strip()
    return ip or "unknown"


limiter = Limiter(key_func=_cf_key, default_limits=["60/minute"])


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init DB
    db_url = os.environ.get("DATABASE_URL", "sqlite:////data/tips.db")
    engine = create_engine_for_url(db_url)
    init_db(engine)
    db = DBOps(engine)

    # Init Omise adapter (Secure Core)
    omise = OmiseAdapter(
        secret_key=secrets.get("OMISE_SECRET_KEY"),
        webhook_secret_b64=secrets.get("OMISE_WEBHOOK_SECRET"),
    )

    # process_tip (Safe Edge — loaded here to avoid core importing app)
    from app.process_tip import process_tip

    # Set reconciliation threshold from settings
    old_threshold = SETTINGS.get("recon_old_threshold_minutes", 10)
    reconciliation.set_old_threshold(old_threshold)

    # Wire state
    app.state.omise = omise
    app.state.db = db
    app.state.broadcaster = sse_broadcaster.broadcast
    app.state.process_tip = process_tip
    app.state.qr_cache = {}  # charge_id → qr_download_uri (ephemeral, lost on restart)

    # Run reconciliation on startup (SPEC §6)
    startup_time = datetime.now(timezone.utc)
    asyncio.create_task(
        reconciliation.run(
            db=db,
            adapter=omise,
            broadcaster=sse_broadcaster.broadcast,
            process_tip=process_tip,
            startup_time=startup_time,
        )
    )

    yield  # serve

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

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routes
app.include_router(webhook_route.router)
app.include_router(charge_route.router)
app.include_router(live_route.router)
app.include_router(sse_route.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
