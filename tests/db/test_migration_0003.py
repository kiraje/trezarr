"""Wave 0 RED stubs for Alembic migration 0003 — source_lang_override + model_override (SVC-05).

Migration 0003 adds two nullable columns to the `series` table:
  - source_lang_override  (JSON / TEXT, nullable)
  - model_override        (TEXT, nullable)

These stubs test the up/down migration contract. They are xfail because migration
0003 does not exist yet (it will be created in Phase 10 Plan 03).

Pattern mirrors tests/db/test_migrations.py: temp-file SQLite + Alembic config fixture,
run_migrations_to_head / explicit upgrade / downgrade via alembic.command.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from sqlalchemy import text

from trezarr.config import TrezarrSettings
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head, ALEMBIC_INI


@pytest_asyncio.fixture
async def migrated_engine_0003(tmp_path):
    """Fresh temp-file SQLite migrated to head (includes migration 0003 when it exists)."""
    db_path = tmp_path / "trezarr_0003.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    await run_migrations_to_head(engine)
    yield engine
    await engine.dispose()


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="Migration 0003 (source_lang_override / model_override) not yet created (SVC-05, Phase 10)",
)
async def test_upgrade_adds_columns(tmp_path):
    """After migration 0003 upgrade, series table has source_lang_override and model_override columns.

    Runs run_migrations_to_head() (which includes 0003 once it ships), then inspects
    the series table schema to verify both nullable columns exist.
    """
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    db_path = tmp_path / "trezarr_up.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    try:
        await run_migrations_to_head(engine)

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='series'")
            )
            series_sql = result.scalar() or ""

        assert "source_lang_override" in series_sql, (
            f"Migration 0003: 'source_lang_override' column not found in series table DDL.\n"
            f"Actual DDL: {series_sql}"
        )
        assert "model_override" in series_sql, (
            f"Migration 0003: 'model_override' column not found in series table DDL.\n"
            f"Actual DDL: {series_sql}"
        )
    finally:
        await engine.dispose()


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError, Exception),
    reason="Migration 0003 downgrade not yet implemented (SVC-05, Phase 10)",
)
async def test_downgrade_removes_columns(tmp_path):
    """After migrating to head then downgrading to 0002, series table loses the 0003 columns.

    Proves migration 0003 is reversible — developers can safely roll back without
    losing the rest of the schema.

    xfail because: (1) migration 0003 does not exist yet (upgrade to head won't include 0003
    columns, so the assertion will fail), and (2) the downgrade target revision ID for 0002
    must match the exact Alembic revision string (confirmed at implementation time).
    """
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415
    import importlib  # noqa: PLC0415

    db_path = tmp_path / "trezarr_down.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    try:
        # First upgrade to head (includes 0003 when it exists)
        await run_migrations_to_head(engine)

        # Resolve the 0002 revision ID from the actual migration module
        # (avoids hardcoding the revision string which may differ from the filename stem)
        migration_0002 = importlib.import_module("alembic.versions.0002_job_queue")  # type: ignore[import-not-found]
        revision_0002 = migration_0002.revision

        # Downgrade one step (back to 0002) via run_sync bridge (Alembic is sync-only)
        cfg = Config(str(ALEMBIC_INI))

        def _do_downgrade(connection, _cfg: Config) -> None:
            _cfg.attributes["connection"] = connection
            command.downgrade(_cfg, revision_0002)

        async with engine.begin() as conn:
            await conn.run_sync(_do_downgrade, cfg)

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='series'")
            )
            series_sql = result.scalar() or ""

        assert "source_lang_override" not in series_sql, (
            f"Migration 0003 downgrade: 'source_lang_override' column still present after downgrade.\n"
            f"Actual DDL: {series_sql}"
        )
        assert "model_override" not in series_sql, (
            f"Migration 0003 downgrade: 'model_override' column still present after downgrade.\n"
            f"Actual DDL: {series_sql}"
        )
    finally:
        await engine.dispose()
