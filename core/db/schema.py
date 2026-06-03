"""
DB schema — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Tips table + recon_state. SQLAlchemy Core, SQLite WAL mode.
Schema portable to Postgres via DATABASE_URL (D5, D15).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

tips = Table(
    "tips",
    metadata,
    # charge_id PK = idempotency key for money record (ARCHITECTURE §6)
    Column("charge_id", Text, primary_key=True),
    Column("status", Text, nullable=False),               # pending | successful | failed | expired
    Column("amount", Integer, nullable=False),             # satang (1 THB = 100)
    Column("currency", Text, nullable=False, default="thb"),
    Column("supporter_name", Text),                            # escape on render — never trust
    Column("message", Text),                               # escape on render — never trust
    Column("source_type", Text),                           # promptpay
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("paid_at", DateTime(timezone=True)),            # set when status → successful
    Column("pushed_at", DateTime(timezone=True)),          # set after SSE push — separate key from money
    Column("event_seq", Integer),                          # monotonic seq for SSE Last-Event-ID replay
)

Index("idx_tips_event_seq", tips.c.event_seq)
Index("idx_tips_status_pushed", tips.c.status, tips.c.pushed_at)

recon_state = Table(
    "recon_state",
    metadata,
    Column("id", Integer, primary_key=True),  # always id=1 (singleton)
    Column("last_scan_at", DateTime(timezone=True)),
)


def create_engine_for_url(database_url: str) -> Engine:
    """Create engine with WAL mode for SQLite, passthrough for Postgres."""
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    engine = create_engine(database_url, connect_args=connect_args, future=True)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """Create tables if they don't exist. Idempotent."""
    metadata.create_all(engine)
