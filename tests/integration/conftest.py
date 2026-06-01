"""Re-export shared db fixtures for tests/integration/*.

The db_engine and session_factory fixtures are defined in tests/db/conftest.py.
pytest conftest.py files are scoped to their directory — fixtures from
tests/db/conftest.py are not visible to tests/integration/*.
"""
from __future__ import annotations

from tests.db.conftest import db_engine, session_factory  # noqa: F401
