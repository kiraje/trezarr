"""Migration-level tests — baseline creates 7 tables, constraints, indexes (D-31, D-33).

Tests:
  1. test_baseline_creates_all_seven_tables: after migration, sqlite_master has all 7 tables
  2. test_baseline_downgrade_drops_all_tables: downgrade drops all 7 tables (reversible)
  3. test_series_unique_constraint_enforced: duplicate (arr_kind, arr_instance, arr_series_id) raises
  4. test_schema_drift_guard: Alembic autogenerate compare returns empty diff (models in sync)
  5. test_check_constraints_exist_in_schema: CHECK constraints present in sqlite_master SQL
  6. test_indexes_exist_in_schema: expected indexes present in sqlite_master

All tests use temp-file SQLite via the db_engine fixture.
asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from trezarr.config import TrezarrSettings
from trezarr.db.base import Base
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head, ALEMBIC_INI
from trezarr.bible import models as _models  # noqa: F401 — populate Base.metadata


async def test_baseline_creates_all_seven_tables(db_engine):
    """After run_migrations_to_head, sqlite_master contains all 7 Bible tables + alembic_version.

    Proves D-31: single baseline creates all tables in one migration.
    """
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = {row[0] for row in result}

    expected = {
        "series", "character", "term_dictionary",
        "address_map", "relationship_event",
        "bible_event", "processed_file",
        "alembic_version",  # Alembic bookkeeping table
    }
    assert expected == tables, f"Expected tables {expected}, got {tables}"


async def test_baseline_downgrade_drops_all_tables(tmp_path):
    """Downgrade to 'base' drops all 7 Bible tables (leaving only alembic_version).

    Proves the migration is reversible — forward-compat for Phase 8 dev workflows.
    """
    db_path = tmp_path / "trezarr_downgrade.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    try:
        await run_migrations_to_head(engine)

        # Downgrade back to base via run_sync bridge (Alembic is sync-only)
        cfg = Config(str(ALEMBIC_INI))

        def _do_downgrade(connection, _cfg: Config) -> None:
            _cfg.attributes["connection"] = connection
            command.downgrade(_cfg, "base")

        async with engine.begin() as conn:
            await conn.run_sync(_do_downgrade, cfg)

        # After downgrade, only alembic_version remains
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            tables = {row[0] for row in result}

        assert tables == {"alembic_version"}, (
            f"Expected only alembic_version after downgrade, got {tables}"
        )
    finally:
        await engine.dispose()


async def test_series_unique_constraint_enforced(db_engine, session_factory):
    """Inserting two Series rows with the same (arr_kind, arr_instance, arr_series_id) raises.

    Proves D-33: UNIQUE(arr_kind, arr_instance, arr_series_id) is enforced at DB level.
    """
    from trezarr.bible.models import Series

    async with session_factory() as session:
        async with session.begin():
            session.add(Series(
                arr_kind="sonarr",
                arr_instance="default",
                arr_series_id=42,
                arr_metadata={},
                locked_fields=[],
            ))

    # Second INSERT with same identity triple must raise IntegrityError
    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            async with session.begin():
                session.add(Series(
                    arr_kind="sonarr",
                    arr_instance="default",
                    arr_series_id=42,  # same triple
                    arr_metadata={},
                    locked_fields=[],
                ))


async def test_schema_drift_guard(db_engine):
    """Alembic autogenerate compare returns empty diff after run_migrations_to_head.

    Proves that the SQLAlchemy models and the baseline migration are in sync —
    no drift between what the migration created and what Base.metadata describes.
    Required by cross-AI review MEDIUM finding.
    """
    diffs = []

    def _run_check(connection) -> None:
        mc = MigrationContext.configure(
            connection,
            opts={"compare_type": True},
        )
        nonlocal diffs
        diffs = compare_metadata(mc, Base.metadata)

    async with db_engine.connect() as conn:
        await conn.run_sync(_run_check)

    assert diffs == [], (
        f"Schema drift detected between models and migration!\n"
        f"Diffs: {diffs}\n"
        f"Fix either the migration or the models to bring them back in sync."
    )


async def test_check_constraints_exist_in_schema(db_engine):
    """CHECK constraints from the migration exist in sqlite_master CREATE TABLE SQL.

    Queries sqlite_master to verify the 3 CHECK constraints were actually created
    by the migration at the DB level (not just defined on Python models).
    """
    async with db_engine.connect() as conn:
        # series.arr_kind CHECK
        result = await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='series'")
        )
        series_sql = result.scalar() or ""

        # bible_event.source CHECK
        result = await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='bible_event'")
        )
        bible_event_sql = result.scalar() or ""

        # processed_file.status CHECK
        result = await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='processed_file'")
        )
        processed_file_sql = result.scalar() or ""

    assert "sonarr" in series_sql and "radarr" in series_sql, (
        f"series.arr_kind CHECK constraint not found in: {series_sql}"
    )
    assert "inference" in bible_event_sql, (
        f"bible_event.source CHECK constraint not found in: {bible_event_sql}"
    )
    assert "done" in processed_file_sql and "quarantined" in processed_file_sql, (
        f"processed_file.status CHECK constraint not found in: {processed_file_sql}"
    )


async def test_indexes_exist_in_schema(db_engine):
    """Expected indexes exist in sqlite_master after the baseline migration.

    Verifies the 3 explicit indexes plus the implicit UNIQUE index on
    processed_file.source_path are present at the DB level.
    """
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        )
        index_names = {row[0] for row in result}

    expected_indexes = {
        "ix_character_series_name",
        "ix_term_dictionary_series_term",
        "ix_bible_event_series_entity_time",
    }
    for idx in expected_indexes:
        assert idx in index_names, (
            f"Expected index '{idx}' not found. Available: {index_names}"
        )

    # processed_file.source_path UNIQUE index — SQLite names it automatically
    # (typically something like sqlite_autoindex_processed_file_1 or similar,
    # OR we created it via unique=True which also creates a named index)
    source_path_unique = any(
        "processed_file" in name or "source_path" in name
        for name in index_names
    )
    assert source_path_unique, (
        f"No UNIQUE index found for processed_file.source_path. Available: {index_names}"
    )
