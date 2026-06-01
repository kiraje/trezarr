"""async_sessionmaker factory for SQLAlchemy 2.0 async sessions (D-38, D-39).

Design decisions honoured:
  D-38  async_sessionmaker bound to AsyncEngine; expire_on_commit=False is
        MANDATORY (Pitfall 2 in 04-RESEARCH.md: the default True marks attributes
        expired after commit, which triggers a lazy refresh that deadlocks under
        async code that accesses attributes after await).
  D-39  Sessions never cross the trezarr.bible.store boundary — callers receive
        Pydantic DTOs only. The session factory stays inside the store layer.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the per-app async_sessionmaker factory from the given engine.

    expire_on_commit=False is mandatory — see Pitfall 2 in 04-RESEARCH.md.
    Default True causes MissingGreenlet or silent hang when attributes are accessed
    after commit in an async context.

    Args:
        engine: An AsyncEngine from build_engine().

    Returns:
        An async_sessionmaker configured for safe async usage.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # required pattern for async code (Pitfall 2)
    )
