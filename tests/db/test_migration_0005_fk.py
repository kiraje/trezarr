"""Regression test for the 0005 crash-loop (2026-06-12 prod incident).

Migration 0005 recreates the `job` table (batch move-and-copy). With the
engine's per-connection PRAGMA foreign_keys=ON AND populated `job_log` rows
referencing `job` (the live DB had hundreds), the recreate raised
`sqlite3.IntegrityError: FOREIGN KEY constraint failed`, crash-looping the
daemon and leaving an orphan `_alembic_tmp_job` table behind.

The fix: the in-app migration runner disables FK enforcement on the migration
connection (PRAGMA must be applied at the raw driver level BEFORE the
connection's transaction begins — it is a no-op inside a transaction). Every
other connection keeps FK=ON via the engine listener.

asyncio_mode="auto" is configured project-wide.
"""
from __future__ import annotations

import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from trezarr.config import TrezarrSettings
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import ALEMBIC_INI, run_migrations_to_head


def _upgrade_to(connection, cfg: Config, revision: str) -> None:
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, revision)


@pytest_asyncio.fixture
async def engine_at_0004_with_job_log_rows(tmp_path):
    """Temp-file SQLite at revision 0004 with a job + referencing job_log rows."""
    db_path = tmp_path / "trezarr_0005_fk.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    cfg = Config(str(ALEMBIC_INI))
    async with engine.begin() as conn:
        await conn.run_sync(_upgrade_to, cfg, "0004")
    # Seed the exact prod shape: a job row + job_log children (FK -> job.id).
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO job (id, source_path, status, trigger, attempts)"
                " VALUES (1, '/media/x.zh.srt', 'quarantined', 'manual', 1)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO job_log (job_id, level, message)"
                " VALUES (1, 'WARNING', 'seeded'), (1, 'WARNING', 'seeded2')"
            )
        )
    yield engine
    await engine.dispose()


async def test_0005_upgrade_survives_populated_job_log(engine_at_0004_with_job_log_rows):
    """run_migrations_to_head must not raise FK IntegrityError with job_log rows present."""
    engine = engine_at_0004_with_job_log_rows
    await run_migrations_to_head(engine)  # raised IntegrityError before the fix

    # Schema reached 0005 and data survived intact.
    async with engine.connect() as conn:
        version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        assert version == "0005"
        job_count = (await conn.execute(text("SELECT count(*) FROM job"))).scalar()
        log_count = (await conn.execute(text("SELECT count(*) FROM job_log"))).scalar()
        assert (job_count, log_count) == (1, 2)
        # No orphan tmp table left behind.
        tmp = (
            await conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                    " AND name LIKE '_alembic_tmp%'"
                )
            )
        ).fetchall()
        assert tmp == []
        # FK enforcement still works on NORMAL connections after migration.
        fk_on = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
        assert fk_on == 1, "engine listener must keep FK=ON for app connections"
