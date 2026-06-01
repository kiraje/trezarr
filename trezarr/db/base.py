"""Shared SQLAlchemy 2.0 DeclarativeBase root for all Bible models.

Design decisions honoured:
  D-31  A single Alembic baseline migration creates all 7 Bible tables; this Base
        holds the MetaData that migration autogenerate compares against.
  D-38  SQLAlchemy 2.0 typed declarative style (DeclarativeBase) is the prescribed
        ORM approach (CLAUDE.md + CONTEXT.md); consistent with Pydantic-everywhere.

All trezarr.bible.models classes inherit from Base. alembic/env.py imports
trezarr.bible.models (and through it, Base) so MetaData is populated before
Alembic autogenerate runs (Pitfall 8 in 04-RESEARCH.md).
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root DeclarativeBase for all Trezarr SQLAlchemy 2.0 models."""
