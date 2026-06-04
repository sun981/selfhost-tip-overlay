"""
SPEC §11 gates that the rest of the suite skipped:
  - reconciliation recovers a missed tip on restart (was mocked in test_integration)
  - backend refuses to start without secrets (was only a _PLACEHOLDERS membership check)

Reconciliation is driven with a fake adapter (no Omise API). The secret-refusal
check runs validate() in a subprocess because it calls sys.exit on failure.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone

from app import reconciliation
from core.payment.omise import ChargeData


# ── §11: reconciliation recovers a missed tip, idempotently ──────────────────

class _FakeAdapter:
    """Stands in for OmiseAdapter.list_recent during reconciliation."""
    def __init__(self, charges: list[ChargeData]) -> None:
        self._charges = charges

    def list_recent(self, since) -> list[ChargeData]:  # noqa: ARG002
        return self._charges


async def _run_recon(db, adapter, pushed: list) -> None:
    async def broadcaster(ev) -> None:
        pushed.append(ev)

    await reconciliation.run(
        db=db,
        adapter=adapter,
        broadcaster=broadcaster,
        process_tip=lambda e: e,  # identity stage
        startup_time=datetime.now(timezone.utc),
    )


def test_reconciliation_recovers_missed_tip(db):
    """SPEC §11: a successful charge the backend never saw → recorded + pushed."""
    reconciliation.set_old_threshold(10)  # 10 min — our charge is "now", so it pushes
    now = datetime.now(timezone.utc)
    charge = ChargeData(
        charge_id="chrg_recon_1",
        amount=5000,
        currency="thb",
        status="successful",
        metadata={"supporter_name": "Bob", "message": "hi"},
        paid_at=now,
        source_type="promptpay",
    )
    adapter = _FakeAdapter([charge])

    pushed: list = []
    asyncio.run(_run_recon(db, adapter, pushed))

    row = db.get_charge_status("chrg_recon_1")
    assert row is not None and row["status"] == "successful", "missed charge must be recorded"
    assert len(pushed) == 1 and pushed[0].charge_id == "chrg_recon_1", "missed tip must be pushed"

    # Idempotent: a second scan of the same charge pushes nothing new
    pushed.clear()
    asyncio.run(_run_recon(db, adapter, pushed))
    assert pushed == [], "already-pushed charge must not re-push on a later scan"


# ── §11: missing secret → refuse start (behavioral, not membership) ──────────

def test_missing_secret_refuses_start():
    """SPEC §11/§4.6: validate() must sys.exit(1) and name what is missing."""
    # Clean env: keep PATH so python runs, omit every required secret.
    env = {"PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        [sys.executable, "-c", "from core.security import secrets; secrets.validate()"],
        env=env,
        cwd="/app",  # backend WORKDIR — `core` importable from here
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    combined = result.stdout + result.stderr
    assert "Missing required env vars" in combined, combined
