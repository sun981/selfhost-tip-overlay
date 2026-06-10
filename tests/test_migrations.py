"""
Schema migration invariants.

Proves: fresh DBs stamp the latest version, pre-mechanism (v0.1.0) DBs stamp
the baseline, pending migrations apply in order with data intact, a backup
file is written before file-backed SQLite migrates, and a DB from a newer
build refuses to start (fail-closed, no silent downgrade).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text

from core.db import migrations
from core.db.migrations import SCHEMA_VERSION, schema_version
from core.db.schema import init_db, metadata, tips


def _version(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(
            select(schema_version.c.version).where(schema_version.c.id == 1)
        ).scalar_one()


def test_fresh_db_stamped_with_latest_version():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    assert _version(engine) == SCHEMA_VERSION


def test_premechanism_db_stamped_with_baseline():
    # Simulate a v0.1.0 DB: tips exists, schema_version does not.
    engine = create_engine("sqlite:///:memory:", future=True)
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            tips.insert().values(
                charge_id="chrg_old", status="successful", amount=2000,
                currency="thb", created_at=datetime.now(),
            )
        )

    init_db(engine)

    assert _version(engine) == migrations.BASELINE_VERSION
    with engine.connect() as conn:
        row = conn.execute(select(tips.c.amount).where(tips.c.charge_id == "chrg_old")).scalar_one()
    assert row == 2000  # existing money records survive adoption


def test_pending_migration_applies_with_backup_and_data_intact(tmp_path, monkeypatch):
    db_path = tmp_path / "tips.db"
    db_url = f"sqlite:///{db_path}"

    # Build a v-current DB with one tip.
    engine = create_engine(db_url, future=True)
    init_db(engine, db_url)
    with engine.begin() as conn:
        conn.execute(
            tips.insert().values(
                charge_id="chrg_keep", status="successful", amount=5000,
                currency="thb", created_at=datetime.now(),
            )
        )
    engine.dispose()

    # Register a fake next-version migration.
    next_version = SCHEMA_VERSION + 1
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", next_version)
    monkeypatch.setitem(
        migrations.MIGRATIONS,
        next_version,
        lambda conn: conn.exec_driver_sql("ALTER TABLE tips ADD COLUMN test_col TEXT"),
    )

    engine = create_engine(db_url, future=True)
    init_db(engine, db_url)

    assert _version(engine) == next_version
    cols = {c["name"] for c in inspect(engine).get_columns("tips")}
    assert "test_col" in cols
    with engine.connect() as conn:
        amount = conn.execute(text("SELECT amount FROM tips WHERE charge_id='chrg_keep'")).scalar_one()
    assert amount == 5000  # data survives migration

    backups = list(Path(tmp_path).glob("tips.db.pre-migrate-v*"))
    assert len(backups) == 1, "backup must be written before migrating"
    engine.dispose()


def test_newer_db_refuses_to_start(monkeypatch):
    # DB stamped ahead of what this build supports → fail-closed.
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(
            schema_version.update().where(schema_version.c.id == 1)
            .values(version=SCHEMA_VERSION + 99)
        )
    with pytest.raises(RuntimeError, match="[Dd]owngrade"):
        init_db(engine)


def test_migration_failure_aborts_and_keeps_version(tmp_path, monkeypatch):
    db_path = tmp_path / "tips.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, future=True)
    init_db(engine, db_url)
    engine.dispose()

    next_version = SCHEMA_VERSION + 1
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", next_version)

    def _boom(conn):
        raise RuntimeError("migration exploded")

    monkeypatch.setitem(migrations.MIGRATIONS, next_version, _boom)

    engine = create_engine(db_url, future=True)
    with pytest.raises(RuntimeError, match="migration exploded"):
        init_db(engine, db_url)
    # Version must NOT have advanced (transaction rolled back).
    assert _version(engine) == SCHEMA_VERSION
    engine.dispose()
