"""
DB operations — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Idempotency invariants (ARCHITECTURE §6, SPEC §4.3):
  - record_successful: guarded UPDATE WHERE status!='successful' — idempotent money record
  - mark_pushed:       UPDATE WHERE pushed_at IS NULL — atomic, returns rowcount;
                       caller emits SSE only if rowcount==1 (prevents double-push)
  - These are TWO separate keys: charge_id guards money, pushed_at IS NULL guards overlay.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text, update
from sqlalchemy.engine import Engine

from core.db.schema import tips, recon_state


class DBOps:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ── Sequence counter (monotonic, used for SSE event_seq) ──────────────

    def _next_seq(self, conn) -> int:
        result = conn.execute(
            select(tips.c.event_seq)
            .where(tips.c.event_seq.isnot(None))
            .order_by(tips.c.event_seq.desc())
            .limit(1)
        )
        row = result.fetchone()
        return (row[0] + 1) if row else 1

    # ── Charge lifecycle ──────────────────────────────────────────────────

    def upsert_pending(
        self,
        charge_id: str,
        amount: int,
        currency: str,
        supporter_name: str,
        message: str,
        source_type: str = "promptpay",
    ) -> None:
        """Insert pending charge. INSERT OR IGNORE — safe to call twice."""
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO tips "
                    "(charge_id, status, amount, currency, supporter_name, message, "
                    " source_type, created_at) "
                    "VALUES (:charge_id, 'pending', :amount, :currency, "
                    ":supporter_name, :message, :source_type, :created_at)"
                ),
                {
                    "charge_id": charge_id,
                    "amount": amount,
                    "currency": currency,
                    "supporter_name": supporter_name,
                    "message": message,
                    "source_type": source_type,
                    "created_at": datetime.now(timezone.utc),
                },
            )

    def record_successful(
        self,
        charge_id: str,
        amount: int,
        currency: str,
        supporter_name: str,
        message: str,
        source_type: str,
        paid_at: datetime,
    ) -> int:
        """
        Idempotently record a successful charge.
        UPDATE WHERE status!='successful' → rowcount 1 on first call, 0 on repeat.
        Always safe to call; returns rowcount so caller knows if it was new.
        """
        with self._engine.begin() as conn:
            # Ensure row exists (reconciliation may see a charge we never created locally)
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO tips "
                    "(charge_id, status, amount, currency, supporter_name, message, "
                    " source_type, created_at) "
                    "VALUES (:charge_id, 'pending', :amount, :currency, "
                    ":supporter_name, :message, :source_type, :created_at)"
                ),
                {
                    "charge_id": charge_id,
                    "amount": amount,
                    "currency": currency,
                    "supporter_name": supporter_name,
                    "message": message,
                    "source_type": source_type,
                    "created_at": paid_at,
                },
            )
            result = conn.execute(
                text(
                    "UPDATE tips SET status='successful', paid_at=:paid_at "
                    "WHERE charge_id=:charge_id AND status!='successful'"
                ),
                {"charge_id": charge_id, "paid_at": paid_at},
            )
            return result.rowcount

    def get_unpushed(self) -> list[dict]:
        """
        Get successful charges that haven't been pushed to overlay yet.
        ORDER BY paid_at for reconciliation ordering (ARCHITECTURE §8.4).
        """
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT charge_id, amount, currency, supporter_name, message, "
                    "       source_type, paid_at "
                    "FROM tips "
                    "WHERE status='successful' AND pushed_at IS NULL "
                    "ORDER BY paid_at ASC"
                )
            )
            return [dict(row._mapping) for row in result]

    def mark_pushed(self, charge_id: str) -> Optional[int]:
        """
        Atomically mark a charge as pushed AND allocate its event_seq in ONE statement.
        Returns the allocated event_seq on the first call, or None if the charge was
        already pushed — caller must then NOT broadcast (prevents double-push on
        concurrent delivery).

        F6 fix (TOCTOU): event_seq is computed by the subquery INSIDE this UPDATE, not
        via a separate next_seq() read. An UPDATE holds the write lock while its SET
        subquery evaluates, so two concurrent pushes can never observe the same MAX and
        collide on a seq. (The old split — next_seq() read under a shared lock, then a
        separate mark_pushed write — is exactly what let two tips share one event_seq.)
        RETURNING hands the value back in the same round-trip; portable to Postgres.
        """
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    "UPDATE tips "
                    "SET pushed_at=:now, "
                    "    event_seq=(SELECT COALESCE(MAX(event_seq), 0) + 1 "
                    "               FROM tips WHERE event_seq IS NOT NULL) "
                    "WHERE charge_id=:charge_id AND pushed_at IS NULL "
                    "RETURNING event_seq"
                ),
                {"charge_id": charge_id, "now": datetime.now(timezone.utc)},
            ).fetchone()
            return row[0] if row else None

    def get_since_seq(self, last_seq: int, limit: int = 50) -> list[dict]:
        """
        Get pushed tips with event_seq > last_seq, for SSE Last-Event-ID replay.
        Returns only fields the overlay needs (no PII beyond supporter_name + message).
        """
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT charge_id, amount, currency, supporter_name, message, event_seq "
                    "FROM tips "
                    "WHERE event_seq > :last_seq AND pushed_at IS NOT NULL "
                    "ORDER BY event_seq ASC "
                    "LIMIT :limit"
                ),
                {"last_seq": last_seq, "limit": limit},
            )
            return [dict(row._mapping) for row in result]

    def get_charge_status(self, charge_id: str) -> Optional[dict]:
        """Get charge status and amount for status polling. Returns None if not found."""
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT status, amount FROM tips WHERE charge_id=:charge_id"
                ),
                {"charge_id": charge_id},
            )
            row = result.fetchone()
            if row is None:
                return None
            return {"status": row[0], "amount": row[1]}

    def get_tip(self, charge_id: str) -> Optional[dict]:
        """
        Full tip row for manual overlay replay (read-only). None if not found.
        supporter_name/message may be NULL after privacy purge — replay shows them blank.
        """
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT charge_id, amount, currency, supporter_name, message, "
                    "       source_type, status, paid_at "
                    "FROM tips WHERE charge_id=:charge_id"
                ),
                {"charge_id": charge_id},
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def update_status(self, charge_id: str, status: str) -> None:
        """Update status for non-successful terminal states (failed, expired)."""
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE tips SET status=:status "
                    "WHERE charge_id=:charge_id AND status='pending'"
                ),
                {"status": status, "charge_id": charge_id},
            )

    # ── Reconciliation cursor ─────────────────────────────────────────────

    def get_last_scan_at(self) -> Optional[datetime]:
        """Return last reconciliation scan timestamp, or None if never run."""
        with self._engine.connect() as conn:
            result = conn.execute(
                text("SELECT last_scan_at FROM recon_state WHERE id=1")
            )
            row = result.fetchone()
            if not row or row[0] is None:
                return None
            val = row[0]
            if isinstance(val, str):
                val = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            return val

    def set_last_scan_at(self, ts: datetime) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO recon_state (id, last_scan_at) VALUES (1, :ts) "
                    "ON CONFLICT(id) DO UPDATE SET last_scan_at=:ts"
                ),
                {"ts": ts},
            )

    # ── Privacy purge ─────────────────────────────────────────────────────

    def next_seq(self) -> int:
        """Allocate next monotonic event_seq. Thread-safe via SQLite serialized writer."""
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT COALESCE(MAX(event_seq), 0) + 1 FROM tips "
                    "WHERE event_seq IS NOT NULL"
                )
            )
            return result.scalar() or 1

    def purge_old(self, before: datetime) -> int:
        """
        Null out supporter name/message from records older than `before`. Returns count.

        Covers BOTH paid rows (paid_at) AND abandoned pending rows (created_at): a charge
        the donor never completed stays status='pending' with paid_at=NULL, so a
        `paid_at < :before` test alone is NULL→false for it and would retain that donor's
        name/message forever — defeating the 90-day purge promise (PDPA). The created_at
        clause sweeps those too.
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE tips SET supporter_name=NULL, message=NULL "
                    "WHERE supporter_name IS NOT NULL "
                    "  AND (paid_at < :before "
                    "       OR (status='pending' AND created_at < :before))"
                ),
                {"before": before},
            )
            return result.rowcount
