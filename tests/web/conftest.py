"""Re-export shared db fixtures for trezarr.web.* tests.

The db_engine and session_factory fixtures are defined in tests/db/conftest.py.
pytest conftest.py files are scoped to their directory — fixtures from
tests/db/conftest.py are not visible to tests/web/*.

This file re-exports them so the worker reconcile/dedup tests can drive a real
temp-file SQLite DB (full Alembic migration → real job/job_log/processed_file
tables) instead of mocking SQLAlchemy.
"""
from __future__ import annotations

# Re-export fixtures from the shared db conftest
from tests.db.conftest import db_engine, session_factory  # noqa: F401
