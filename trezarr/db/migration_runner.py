"""Alembic migration runner — async-aware startup bridge (D-31, D-38).

Design decisions honoured:
  D-31  The baseline Alembic migration (0001_baseline_bible_schema.py) is the
        single source of truth for the full long-term Bible schema. run_migrations_to_head()
        ensures every startup applies all pending migrations idempotently.
  D-37  migrate_json_ledger_if_needed() — one-shot JSON→SQLite migration on first
        SQLite startup — is a separate function called AFTER run_migrations_to_head().
        # TODO 04-04: implement migrate_json_ledger_if_needed() in plan 04-04 when
        # the Ledger backend swap lands. The function stub is intentionally absent
        # here — 04-04 adds it to this module.

Pitfall 1 (04-RESEARCH.md): Alembic's command.upgrade() is synchronous and MUST
be invoked via connection.run_sync(_do_upgrade) to avoid blocking the event loop
and bypassing the engine's PRAGMA-configured connection.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# Path to alembic.ini at the project root (two parents up from this file:
# trezarr/db/migration_runner.py → trezarr/db → trezarr → project-root).
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _do_upgrade(connection, cfg: Config) -> None:
    """Sync callback invoked via connection.run_sync().

    Injects the live connection into the Alembic config so env.py's
    run_migrations_online() uses OUR connection (and therefore our PRAGMAs)
    rather than creating a new engine internally.

    Args:
        connection: Synchronous SQLAlchemy connection from run_sync().
        cfg:        Alembic Config with script_location set.
    """
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def run_migrations_to_head(engine: AsyncEngine) -> None:
    """Run all pending Alembic migrations up to the 'head' revision.

    Uses the connection.run_sync(_do_upgrade) bridge to invoke synchronous
    Alembic from an async context without blocking the event loop (Pitfall 1).
    Idempotent — Alembic skips already-applied revisions.

    Args:
        engine: An AsyncEngine from build_engine() with PRAGMAs already registered.

    Raises:
        Exception: Re-raises any Alembic error; caller (cli.py) should sys.exit(1).
    """
    cfg = Config(str(ALEMBIC_INI))
    logger.info("Running Alembic migrations to head (alembic.ini: %s)", ALEMBIC_INI)
    async with engine.begin() as conn:
        await conn.run_sync(_do_upgrade, cfg)
    logger.info("Alembic migrations complete")
