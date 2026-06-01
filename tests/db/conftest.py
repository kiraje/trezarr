"""Shared fixtures for trezarr.db.* and trezarr.bible.* tests.

Convention: temp-file SQLite per test (CONTEXT.md preference — exercises the
real Alembic baseline migration each run; NOT :memory: which breaks Alembic +
multi-connection semantics, per Pitfall 3 in 04-RESEARCH.md).

The db_engine fixture runs the real Alembic baseline migration via
run_migrations_to_head(). There is no pytest.skip fallback — the migration file
exists at Task 1 commit time (post-revision design: no commented-out imports,
no coordination dance).

WAL-mode assertions (test_wal_mode_set) are only valid for file-based SQLite URLs.
This fixture always uses tmp_path, so ALL PRAGMA tests are valid for every test
in the suite.

asyncio_mode = "auto" is configured project-wide in pyproject.toml, so
@pytest_asyncio.fixture (not @pytest.fixture) is used for async fixtures.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from trezarr.config import TrezarrSettings
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    """Fresh temp-file SQLite + full Alembic migration per test.

    Creates a TrezarrSettings stub with bible_db_url pointing to a temp file
    so each test gets an isolated, migration-run database. No pytest.skip
    fallback — the migration runs cleanly on every test invocation.

    Args:
        tmp_path: pytest-provided temporary directory (per-test isolation).

    Yields:
        AsyncEngine with migrations applied and PRAGMAs registered.
    """
    db_path = tmp_path / "trezarr.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",  # required field even though LLM is not exercised
    )
    engine = build_engine(settings)
    await run_migrations_to_head(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    """Build an async_sessionmaker from the db_engine fixture.

    expire_on_commit=False is mandatory — see Pitfall 2 in 04-RESEARCH.md.

    Args:
        db_engine: Migrated AsyncEngine from the db_engine fixture.

    Returns:
        async_sessionmaker configured for safe async usage.
    """
    return async_sessionmaker(db_engine, expire_on_commit=False)
