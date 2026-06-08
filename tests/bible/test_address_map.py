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


async def test_pass1_create_or_affirm_existing_pair(session_factory):
    """Pass-1 create-or-affirm: calling upsert with self_term=None/address_term=None on an
    EXISTING UNLOCKED pair leaves the established terms UNCHANGED (scy — Vector 1 fix).

    This simulates the post-fix analyze.py behavior for an existing pair: instead of passing
    the fresh LLM-inferred terms, Pass-1 passes None/None so store.py's
    `if new_val is None: continue` guard preserves the established self_term/address_term.
    """
    from trezarr.bible.store import upsert_address_pair

    series_id = await _create_series(session_factory, arr_series_id=2)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)

    # Create the initial row with established terms ("anh", "em")
    dto1, _ = await upsert_address_pair(
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
    assert dto1.self_term == "anh"
    assert dto1.address_term == "em"

    # Simulate Pass-1 create-or-affirm call: self_term=None, address_term=None
    # This is what analyze.py now passes for an existing pair (scy fix).
    dto2, events2 = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=speaker_id,
        addressee_character_id=addressee_id,
        self_term=None,
        address_term=None,
        valid_from_episode="S01E02",
        episode_key="S01E02",
        source="inference",
    )

    # Terms must be UNCHANGED — the None-guard in store.py skips the setattr
    assert dto2.self_term == "anh", (
        f"Expected self_term='anh' to be preserved (None-guard), got {dto2.self_term!r}"
    )
    assert dto2.address_term == "em", (
        f"Expected address_term='em' to be preserved (None-guard), got {dto2.address_term!r}"
    )

    # No events for the term fields (since new_val was None → skipped before old==new check)
    term_events = [e for e in events2 if e.field in ("self_term", "address_term")]
    assert term_events == [], (
        f"Expected no events for term fields when new_val is None, got {term_events}"
    )


async def test_pass1_creates_brand_new_pair(session_factory):
    """Pass-1 brand-new pair: no prior row → upsert creates it with the supplied terms (scy).

    Verifies the non-existing-pair branch of the create-or-affirm fix: when the pair key
    is NOT in existing_pair_keys, analyze.py passes the inferred terms and upsert_address_pair
    creates the row normally.
    """
    from trezarr.bible.store import upsert_address_pair

    series_id = await _create_series(session_factory, arr_series_id=3)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)

    # No prior row exists — brand-new dyad
    dto, events = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=speaker_id,
        addressee_character_id=addressee_id,
        self_term="tôi",
        address_term="bạn",
        valid_from_episode="S01E01",
        episode_key="S01E01",
        source="inference",
    )

    assert dto.self_term == "tôi", (
        f"Brand-new pair must be created with supplied self_term='tôi', got {dto.self_term!r}"
    )
    assert dto.address_term == "bạn", (
        f"Brand-new pair must be created with supplied address_term='bạn', got {dto.address_term!r}"
    )
    # Events should be emitted for the new non-None fields
    event_fields = {e.field for e in events}
    assert "self_term" in event_fields
    assert "address_term" in event_fields
