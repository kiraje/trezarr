"""Tests for Address Map store functions (BIBLE-03): upsert_address_pair, test_locked_pair_not_overwritten.

Tests use the session_factory fixture from tests/bible/conftest.py (which re-exports
it from tests/db/conftest.py), providing a fresh temp-file SQLite + full Alembic
migration per test.

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.

Threat mitigation coverage:
  T-05-02-01  test_locked_pair_not_overwritten verifies locked_fields prevents overwrites (D-34)
  T-05-02-02  All writes use SQLAlchemy ORM parameterized queries (store.py internals)
"""
from __future__ import annotations



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_series(session_factory, arr_series_id: int = 1) -> int:
    """Create a minimal Series row and return its id."""
    from trezarr.bible.store import get_or_create_series
    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=arr_series_id,
        arr_metadata_snapshot={"title": "Test Series"},
    )
    return dto.id


async def _create_characters(session_factory, series_id: int) -> tuple[int, int]:
    """Create two minimal Character rows and return their ids (speaker, addressee)."""
    from trezarr.bible.store import upsert_character
    speaker_dto, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Minh",
        gender="male",
        source="inference",
    )
    addressee_dto, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Lan",
        gender="female",
        source="inference",
    )
    return speaker_dto.id, addressee_dto.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_upsert_address_pair(session_factory):
    """Address Map is populated with directed character pairs after Pass 1 (BIBLE-03).

    Assert:
    - upsert_address_pair importable from trezarr.bible.store
    - Calling upsert_address_pair with a directed character pair inserts a row
    - The inserted row can be read back with the correct speaker/addressee IDs
      and the specified pronoun pair
    """
    from trezarr.bible.store import upsert_address_pair

    series_id = await _create_series(session_factory)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)

    dto, events = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=speaker_id,
        addressee_character_id=addressee_id,
        self_term="anh",
        address_term="em",
        valid_from_episode="S01E01",
        episode_key="S01E01",
        source="inference",
    )

    assert dto.self_term == "anh"
    assert dto.address_term == "em"
    assert dto.speaker_character_id == speaker_id
    assert dto.addressee_character_id == addressee_id
    assert dto.valid_from_episode == "S01E01"
    assert dto.series_id == series_id

    # Events should be emitted for new non-None fields
    event_fields = {e.field for e in events}
    assert "self_term" in event_fields
    assert "address_term" in event_fields


async def test_locked_pair_not_overwritten(session_factory):
    """Locked Address Map entry is never overwritten by a new inference (BIBLE-03, D-34).

    Assert:
    - When an AddressMap entry has self_term in locked_fields, calling upsert_address_pair
      with a different self_term does NOT overwrite the locked entry
    - The original locked self_term remains unchanged after the upsert attempt
    """
    from sqlalchemy import select
    from trezarr.bible.models import AddressMap
    from trezarr.bible.store import upsert_address_pair

    series_id = await _create_series(session_factory)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)

    # Insert the initial row with self_term="anh"
    dto, _ = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=speaker_id,
        addressee_character_id=addressee_id,
        self_term="anh",
        address_term="em",
        episode_key="S01E01",
        source="inference",
    )

    # Manually set locked_fields=["self_term"] on the existing row (simulates user lock)
    async with session_factory() as session:
        async with session.begin():
            stmt = select(AddressMap).where(AddressMap.id == dto.id)
            row = (await session.execute(stmt)).scalar_one()
            row.locked_fields = ["self_term"]

    # Attempt to overwrite self_term with "chị" — must be blocked by the lock
    dto2, events2 = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=speaker_id,
        addressee_character_id=addressee_id,
        self_term="chị",   # different value — should be rejected
        address_term="em",
        episode_key="S01E02",
        source="inference",
    )

    # The locked self_term must remain "anh" (not overwritten to "chị")
    assert dto2.self_term == "anh", (
        f"Expected locked self_term='anh' to survive, got {dto2.self_term!r}"
    )
    # No event should have been emitted for the locked self_term field
    locked_field_events = [e for e in events2 if e.field == "self_term"]
    assert locked_field_events == [], (
        f"Expected no events for locked field 'self_term', got {locked_field_events}"
    )
