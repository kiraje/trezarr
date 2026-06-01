"""AsyncEngine factory with PRAGMA event listener for SQLite (D-38).

Design decisions honoured:
  D-38  Single AsyncEngine + async_sessionmaker at startup. PRAGMAs applied at
        every new connection via event.listens_for(engine.sync_engine, "connect")
        — NOT at session level (Pitfall 4 in 04-RESEARCH.md: foreign_keys is a
        per-connection runtime setting, not a persistent DB property).
        journal_mode=WAL is file-persistent but harmless to re-issue each time.

Pitfall 4 (from 04-RESEARCH.md): PRAGMA foreign_keys MUST be set per-connection.
Using event.listens_for(engine.sync_engine, "connect") is the only reliable way
to guarantee the PRAGMA fires on every connection from the pool.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)


def build_engine(settings: "TrezarrSettings") -> AsyncEngine:
    """Build the AsyncEngine and register the PRAGMA event listener (D-38).

    Creates a SQLAlchemy 2.0 async engine from settings.bible_db_url.
    Registers a connect-event listener on the underlying sync engine to issue
    SQLite PRAGMAs on EVERY new pool connection (Pitfall 4):
      - journal_mode=WAL (if bible_db_enable_wal is True)
      - synchronous=NORMAL (always — safe with WAL, improves write throughput)
      - foreign_keys=ON (if bible_db_enforce_fk is True)

    Args:
        settings: Validated TrezarrSettings with bible_db_* fields populated.

    Returns:
        A configured AsyncEngine ready for session creation and migrations.
    """
    engine = create_async_engine(settings.bible_db_url, echo=False, future=True)  # D-38

    @event.listens_for(engine.sync_engine, "connect")  # D-38: per-connection, not per-session
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        if settings.bible_db_enable_wal:
            cursor.execute("PRAGMA journal_mode=WAL")       # file-persistent on the DB file
        cursor.execute("PRAGMA synchronous=NORMAL")         # safe with WAL; better throughput
        if settings.bible_db_enforce_fk:
            cursor.execute("PRAGMA foreign_keys=ON")        # MUST be per-connection (Pitfall 4)
        cursor.close()

    logger.info("AsyncEngine built for %s (WAL=%s, FK=%s)",
                settings.bible_db_url,
                settings.bible_db_enable_wal,
                settings.bible_db_enforce_fk)
    return engine
