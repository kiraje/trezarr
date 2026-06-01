"""Tests for Address Map store functions (BIBLE-03): upsert_address_pair, test_locked_pair_not_overwritten.

RED stubs — all tests are marked xfail(strict=False) until upsert_address_pair is
implemented in trezarr.bible.store (Phase 5 Plan 05-02).

Tests use the session_factory fixture from tests/bible/conftest.py (which re-exports
it from tests/db/conftest.py), providing a fresh temp-file SQLite + full Alembic
migration per test.

All trezarr.* imports from store are deferred inside each test function body so pytest
collection succeeds even when upsert_address_pair does not yet exist.

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.
"""
import pytest


@pytest.mark.xfail(strict=False, reason="upsert_address_pair not yet in store.py", raises=(ImportError, AttributeError))
async def test_upsert_address_pair(session_factory):
    """Address Map is populated with directed character pairs after Pass 1 (BIBLE-03).

    Assert:
    - upsert_address_pair importable from trezarr.bible.store
    - Calling upsert_address_pair with a directed character pair inserts a row
    - The inserted row can be read back with the correct speaker/addressee IDs
      and the specified pronoun pair
    """
    from trezarr.bible.store import upsert_address_pair
    assert False, "stub — implement in Plan 05-02"


@pytest.mark.xfail(strict=False, reason="upsert_address_pair not yet in store.py", raises=(ImportError, AttributeError))
async def test_locked_pair_not_overwritten(session_factory):
    """Locked Address Map entry is never overwritten by a new inference (BIBLE-03).

    Assert:
    - upsert_address_pair importable from trezarr.bible.store
    - When an AddressMap entry has locked=True, calling upsert_address_pair with
      conflicting data does NOT overwrite the locked entry
    - The original locked pair remains unchanged after the upsert attempt
    """
    from trezarr.bible.store import upsert_address_pair
    assert False, "stub — implement in Plan 05-02"
