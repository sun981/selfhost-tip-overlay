"""
Schema migrations — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Versioned, forward-only migration runner, executed at startup (fail-closed:
any migration error aborts startup rather than running on a half-migrated DB).

How it works:
- `schema_version` is a single-row table holding the current version.
- A DB that predates this mechanism (v0.1.0) has tips but no schema_version
  → stamped as BASELINE_VERSION. A fresh DB is stamped SCHEMA_VERSION directly
  (create_all already produces the latest shape; no migrations needed).
- MIGRATIONS maps target_version → callable(connection). Pending migrations
  run in order, each in its own transaction, bumping schema_version as they go.
- For file-backed SQLite, a backup copy is written next to the DB before the
  first pending migration runs (sqlite3 backup API — WAL-safe).

Adding a migration:
1. Bump SCHEMA_VERSION.
2. Add MIGRATIONS[new_version] = fn that takes the schema from new_version-1
   to new_version. Keep it additive where possible (SQLite ALTER is limited).
3. Update schema.py so create_all of a fresh DB matches the migrated shape.
4. Add a test in tests/test_migrations.py proving old data survives.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from typing import Callable

from sqlalchemy import Column, Integer, MetaData, Table, inspect, select, update
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)

# Version of the schema produced by schema.py's create_all.
SCHEMA_VERSION = 1
# Version stamped onto pre-mechanism DBs (v0.1.0 shipped this schema).
BASELINE_VERSION = 1

# target_version -> migration. Example:
#   MIGRATIONS[2] = lambda conn: conn.exec_driver_sql(
#       "ALTER TABLE tips ADD COLUMN refunded_at TIMESTAMP")
MIGRATIONS: dict[int, Callable[[Connection], None]] = {}

_migrations_metadata = MetaData()

schema_version = Table(
    "schema_version",
    _migrations_metadata,
    Column("id", Integer, primary_key=True),  # always id=1 (singleton)
    Column("version", Integer, nullable=False),
)


def run_migrations(engine: Engine, database_url: str = "") -> None:
    """Stamp/inspect schema_version, then apply pending migrations in order.

    Must be called AFTER metadata.create_all (the inspection of which tables
    existed beforehand happens in init_db, which passes it via had_tips).
    Raises on any failure — caller must treat that as fatal (fail-closed).
    """
    current = _stamped_version(engine)

    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current} is newer than this build "
            f"supports ({SCHEMA_VERSION}). Downgrades are not supported — "
            "run the matching or newer version of the app."
        )

    pending = sorted(v for v in MIGRATIONS if v > current)
    if not pending:
        return

    _backup_sqlite_file(database_url, current)

    for version in pending:
        logger.info("migrating schema %d -> %d", current, version)
        with engine.begin() as conn:
            MIGRATIONS[version](conn)
            conn.execute(
                update(schema_version)
                .where(schema_version.c.id == 1)
                .values(version=version)
            )
        current = version


def stamp_initial_version(engine: Engine, had_tips: bool, had_version_table: bool) -> None:
    """Insert the singleton version row on first run.

    had_tips/had_version_table describe the DB *before* create_all ran:
    - no schema_version + tips present  → pre-mechanism DB → BASELINE_VERSION
    - no schema_version + no tips       → fresh DB → SCHEMA_VERSION
    """
    if had_version_table:
        return
    initial = BASELINE_VERSION if had_tips else SCHEMA_VERSION
    with engine.begin() as conn:
        conn.execute(schema_version.insert().values(id=1, version=initial))


def _stamped_version(engine: Engine) -> int:
    with engine.connect() as conn:
        version = conn.execute(
            select(schema_version.c.version).where(schema_version.c.id == 1)
        ).scalar_one_or_none()
    if version is None:
        raise RuntimeError("schema_version row missing — init_db must stamp before migrating")
    return version


def _backup_sqlite_file(database_url: str, from_version: int) -> None:
    """Copy a file-backed SQLite DB before migrating. No-op for :memory:/Postgres."""
    if not database_url.startswith("sqlite"):
        return
    path = database_url.split("///", 1)[-1]
    if not path or path == ":memory:":
        return
    backup_path = f"{path}.pre-migrate-v{from_version}-{int(time.time())}"
    try:
        src = sqlite3.connect(path)
        try:
            dst = sqlite3.connect(backup_path)
            try:
                src.backup(dst)  # WAL-safe, consistent snapshot
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.Error:
        # Fall back to a plain copy; if even that fails, abort the migration
        # (better to refuse than to migrate without a backup).
        shutil.copy2(path, backup_path)
    logger.info("pre-migration backup written: %s", backup_path)
