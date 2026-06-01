"""Re-export shared db fixtures for trezarr.bible.* tests.

The db_engine and session_factory fixtures are defined in tests/db/conftest.py.
pytest conftest.py files are scoped to their directory — fixtures from
tests/db/conftest.py are not visible to tests/bible/*.

This file re-exports them by importing the fixture functions so pytest discovers
them in this test directory.
"""
from __future__ import annotations

# Re-export fixtures from the shared db conftest
from tests.db.conftest import db_engine, session_factory  # noqa: F401
