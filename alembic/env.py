"""Alembic env.py — async-aware migration runner (RESEARCH Pattern 4).

Supports three usage modes:
  1. Production startup: connection injected via config.attributes["connection"]
     from trezarr.db.migration_runner.run_migrations_to_head() (D-38 Pitfall 1).
  2. CLI online: `alembic upgrade head` builds its own async engine from
     sqlalchemy.url if no injected connection is available.
  3. Offline: `alembic upgrade head --sql` generates a dry-run SQL script.

render_as_batch=True is MANDATORY for SQLite ALTER support (Pitfall 6 in
04-RESEARCH.md: SQLite has no native ALTER TABLE — Alembic must emulate it by
creating a temp table, copying rows, dropping original, and renaming).
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from trezarr.db.base import Base
from trezarr.bible import models  # noqa: F401 — LIVE import (Pitfall 8 in 04-RESEARCH.md)
# The import above causes trezarr.bible.models to register all 7 SQLAlchemy
# model classes into Base.metadata so autogenerate can compare them.
from trezarr.jobs import models as _job_models  # noqa: F401 — registers Job/JobLog into Base.metadata (Pitfall F)

config = context.config

# Configure Python logging if a config file is present.
# Guard: skip fileConfig when running inside pytest to avoid overwriting the
# test harness's logging configuration (which would break caplog captures in
# tests that run after a migration).  pytest sets sys.modules['_pytest'] so
# we can detect the test environment without an extra dependency.
import sys as _sys
_running_under_pytest = "_pytest" in _sys.modules
if config.config_file_name is not None and not _running_under_pytest:
    fileConfig(config.config_file_name)
del _sys, _running_under_pytest

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    """Configure the Alembic migration context with the given connection.

    render_as_batch=True enables SQLite-compatible ALTER emulation (Pitfall 6).
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,   # MANDATORY for SQLite ALTER support (Pitfall 6)
        compare_type=True,      # detect column type changes in autogenerate
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    If a connection was injected by run_migrations_to_head() via
    config.attributes["connection"], use it directly. Otherwise, build a new
    async engine from the sqlalchemy.url config setting (CLI usage path).
    """
    # Production path: connection was injected by migration_runner.py
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        do_run_migrations(connectable)
        return

    # CLI path: build our own async engine from sqlalchemy.url (alembic upgrade head)
    from sqlalchemy.ext.asyncio import async_engine_from_config

    async def _run() -> None:
        engine = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await engine.dispose()

    asyncio.run(_run())


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without a DB connection.

    Used for `alembic upgrade head --sql` dry-run / CI parity checks.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,   # consistent with online mode
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
