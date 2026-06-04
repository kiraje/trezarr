"""Regression tests for migration 0004 — ck_job_trigger includes 'manual'.

Covers:
  - trigger='manual' inserts cleanly (no IntegrityError) after migration 0004.
  - All previously-valid triggers still insert cleanly.
  - trigger='invalid' still raises IntegrityError (constraint is still active).
  - Migration 0004 upgrade/downgrade round-trip restores the original constraint.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from trezarr.config import TrezarrSettings
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head, ALEMBIC_INI


@pytest_asyncio.fixture
async def migrated_engine(tmp_path):
    """Fresh temp-file SQLite migrated to head (includes migration 0004)."""
    db_path = tmp_path / "trezarr_0004.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    await run_migrations_to_head(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory_0004(migrated_engine):
    """Async session factory for migration-0004 engine."""
    return async_sessionmaker(migrated_engine, expire_on_commit=False)


async def test_trigger_manual_inserts_cleanly(session_factory_0004):
    """trigger='manual' must insert without IntegrityError after migration 0004.

    This is the direct regression test for the bug: POST /api/translate crashed
    with CHECK constraint failed: ck_job_trigger because 'manual' was absent from
    the original 4-value trigger set. Migration 0004 adds it.
    """
    async with session_factory_0004() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO job (source_path, status, trigger, attempts)"
                    " VALUES ('/media/test.en.srt', 'queued', 'manual', 0)"
                )
            )
    # No IntegrityError raised — regression confirmed fixed.


async def test_all_valid_triggers_accepted(session_factory_0004):
    """All five allowed triggers must insert cleanly: poll, webhook, manual, manual-retry, startup-reconcile."""
    valid_triggers = ["poll", "webhook", "manual", "manual-retry", "startup-reconcile"]
    for trigger in valid_triggers:
        path = f"/media/test_{trigger}.en.srt"
        async with session_factory_0004() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "INSERT INTO job (source_path, status, trigger, attempts)"
                        f" VALUES ('{path}', 'queued', '{trigger}', 0)"
                    )
                )


async def test_invalid_trigger_still_rejected(session_factory_0004):
    """An unrecognised trigger value must still raise IntegrityError (constraint is active)."""
    with pytest.raises(IntegrityError):
        async with session_factory_0004() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "INSERT INTO job (source_path, status, trigger, attempts)"
                        " VALUES ('/media/bad.en.srt', 'queued', 'invalid-trigger', 0)"
                    )
                )


async def test_migration_0004_upgrade_downgrade_round_trip(tmp_path):
    """Migration 0004 upgrade + downgrade round-trip leaves a clean schema.

    After upgrade: 'manual' is in the ck_job_trigger constraint.
    After downgrade to 0003: 'manual' is removed; the original constraint is restored
    and inserting trigger='manual' must raise IntegrityError again.

    Note: we do NOT insert trigger='manual' rows before the downgrade — the
    batch-recreate move-and-copy would fail trying to copy those rows into the
    table with the restored (narrower) constraint. This tests the schema contract,
    not data migration.
    """
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    db_path = tmp_path / "trezarr_round_trip.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    try:
        # Upgrade to head (includes 0004)
        await run_migrations_to_head(engine)

        # Verify 'manual' is accepted at head (no data stays after — clean downgrade later)
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO job (source_path, status, trigger, attempts)"
                    " VALUES ('/media/pre_downgrade.en.srt', 'queued', 'manual', 0)"
                )
            )
            await conn.commit()
            # Clean up so the downgrade batch-copy has no 'manual' rows that would
            # violate the restored constraint in the temp table.
            await conn.execute(
                text("DELETE FROM job WHERE source_path = '/media/pre_downgrade.en.srt'")
            )
            await conn.commit()

        # Downgrade to revision 0003 (one step back)
        cfg = Config(str(ALEMBIC_INI))

        def _do_downgrade(connection, _cfg: Config) -> None:
            _cfg.attributes["connection"] = connection
            command.downgrade(_cfg, "0003")

        async with engine.begin() as conn:
            await conn.run_sync(_do_downgrade, cfg)

        # After downgrade: 'manual' trigger must be rejected again
        with pytest.raises(IntegrityError):
            async with engine.connect() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO job (source_path, status, trigger, attempts)"
                        " VALUES ('/media/post_downgrade.en.srt', 'queued', 'manual', 0)"
                    )
                )
                await conn.commit()

    finally:
        await engine.dispose()
