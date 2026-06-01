"""Tests for trezarr.db.engine — PRAGMA enforcement per-connection (D-38).

Verifies that WAL mode, foreign_keys=ON, and synchronous=NORMAL are applied
on EVERY new connection from the pool, not just the first (Pitfall 4 in
04-RESEARCH.md: foreign_keys is per-connection, not DB-persistent).

All tests use temp-file SQLite via the db_engine fixture (CONTEXT.md preference —
never :memory: which breaks Alembic + multi-connection semantics).
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from trezarr.config import TrezarrSettings
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head


@pytest_asyncio.fixture
async def settings_and_engine(tmp_path):
    """Fresh temp-file SQLite engine with migrations run, per test."""
    db_path = tmp_path / "trezarr.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    await run_migrations_to_head(engine)
    yield settings, engine
    await engine.dispose()


async def test_foreign_keys_enabled_per_connection(settings_and_engine):
    """Two distinct connections from the pool both report PRAGMA foreign_keys=1.

    This is the critical per-connection check (Pitfall 4 in RESEARCH): foreign_keys
    is a runtime setting that must be set on EVERY new connection. Opening two
    separate connections proves the event listener fires each time.
    """
    settings, engine = settings_and_engine

    # First connection
    async with engine.connect() as conn1:
        result1 = await conn1.execute(text("PRAGMA foreign_keys"))
        val1 = result1.scalar()

    # Second distinct connection (pool may or may not reuse; the listener fires either way)
    async with engine.connect() as conn2:
        result2 = await conn2.execute(text("PRAGMA foreign_keys"))
        val2 = result2.scalar()

    assert val1 == 1, f"First connection: PRAGMA foreign_keys returned {val1}, expected 1"
    assert val2 == 1, f"Second connection: PRAGMA foreign_keys returned {val2}, expected 1"


async def test_wal_mode_set(settings_and_engine):
    """PRAGMA journal_mode returns 'wal' on a fresh file-based SQLite DB.

    Only valid for file-based SQLite (never :memory:). The fixture always uses
    tmp_path so this assertion is always safe.
    """
    settings, engine = settings_and_engine

    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA journal_mode"))
        mode = result.scalar()

    assert mode == "wal", f"Expected journal_mode='wal', got {mode!r}"


async def test_synchronous_normal(settings_and_engine):
    """PRAGMA synchronous returns 1 (NORMAL) after engine construction.

    synchronous=NORMAL is safe with WAL mode and improves write performance.
    """
    settings, engine = settings_and_engine

    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA synchronous"))
        val = result.scalar()

    assert val == 1, f"Expected synchronous=1 (NORMAL), got {val!r}"


async def test_settings_toggles_disable_fk(tmp_path):
    """With bible_db_enforce_fk=False, PRAGMA foreign_keys returns 0.

    Proves the optional toggle wires through build_engine → the event listener.
    """
    db_path = tmp_path / "trezarr_nofk.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
        bible_db_enforce_fk=False,
    )
    engine = build_engine(settings)
    try:
        await run_migrations_to_head(engine)
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA foreign_keys"))
            val = result.scalar()
        assert val == 0, f"Expected foreign_keys=0 when enforce_fk=False, got {val!r}"
    finally:
        await engine.dispose()
