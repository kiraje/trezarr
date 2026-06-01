"""Bible event audit log contract tests (D-32).

Tests verify that the bible_event append-only audit log has all required fields
and is never mutated — only appended to.

Design decisions exercised:
  D-32  mutable current row + append-only bible_event log
        Every mutation writes one BibleEvent inside the same transaction.
        source ∈ {inference, lock, import, system}
"""
from __future__ import annotations

from sqlalchemy import select

from trezarr.bible.models import BibleEvent
from trezarr.bible.store import get_character, merge_inferred, upsert_character


async def _create_series(session_factory, arr_series_id=1):
    from trezarr.bible.store import get_or_create_series
    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=arr_series_id,
        arr_metadata_snapshot={"title": "Audit Test Series"},
    )
    return dto.id


# ---------------------------------------------------------------------------
# Test 15: bible_event carries all required fields (D-32 schema contract)
# ---------------------------------------------------------------------------

async def test_bible_event_carries_all_required_fields(session_factory):
    """Every event from merge_inferred has all D-32 required fields.

    Required non-NULL: series_id, entity_type, entity_id, field, source, created_at.
    May be NULL: episode_key (some mutations aren't episode-scoped),
                 old_value (first-time set), new_value (clearing a field).
    """
    series_id = await _create_series(session_factory)
    char_dto, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Mary",
        role="detective",
        episode_key="S01E01",
        source="inference",
    )

    dto = await get_character(session_factory, series_id=series_id, original_latin_name="Mary")
    assert dto is not None

    _, events = await merge_inferred(
        session_factory, dto, {"role": "spy"}, episode_key="S01E02", source="inference"
    )
    assert len(events) == 1

    # Verify via a fresh DB query (not just the returned DTO)
    # Filter specifically for the merge event (episode_key=S01E02) to avoid
    # matching the first-insert event from upsert_character.
    async with session_factory() as session:
        db_evt = (
            await session.execute(
                select(BibleEvent).where(
                    BibleEvent.entity_id == char_dto.id,
                    BibleEvent.episode_key == "S01E02",
                )
            )
        ).scalar_one()

    # All D-32 required non-NULL fields
    assert db_evt.series_id is not None, "series_id must not be NULL"
    assert db_evt.entity_type is not None, "entity_type must not be NULL"
    assert db_evt.entity_id is not None, "entity_id must not be NULL"
    assert db_evt.field is not None, "field must not be NULL"
    assert db_evt.source is not None, "source must not be NULL"
    assert db_evt.created_at is not None, "created_at must not be NULL"

    # Correct values
    assert db_evt.series_id == series_id
    assert db_evt.entity_type == "character"
    assert db_evt.entity_id == char_dto.id
    assert db_evt.field == "role"
    assert db_evt.source == "inference"
    assert db_evt.episode_key == "S01E02"
    assert db_evt.old_value == "detective"
    assert db_evt.new_value == "spy"


# ---------------------------------------------------------------------------
# Test 16: bible_event is append-only — a second merge appends, never mutates
# ---------------------------------------------------------------------------

async def test_bible_event_is_append_only_never_mutated_by_merge(session_factory):
    """Running a second merge on the same field appends a NEW event — never mutates the original.

    Assert:
    - After two merges changing 'role', there are exactly 2 distinct BibleEvent rows.
    - Their created_at values differ (or at least they have different ids).
    - The first event is never updated.
    """
    series_id = await _create_series(session_factory, arr_series_id=99)
    char_dto, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Bob",
        role="detective",
        episode_key="S01E01",
        source="inference",
    )

    dto = await get_character(session_factory, series_id=series_id, original_latin_name="Bob")
    assert dto is not None

    # First merge: detective → spy
    _, events1 = await merge_inferred(
        session_factory, dto, {"role": "spy"}, episode_key="S01E02", source="inference"
    )
    assert len(events1) == 1, "first merge must produce 1 event"
    first_event_id = events1[0].id

    # Second merge: spy → double_agent (flip the same field back)
    dto2 = await get_character(session_factory, series_id=series_id, original_latin_name="Bob")
    assert dto2 is not None

    _, events2 = await merge_inferred(
        session_factory, dto2, {"role": "double_agent"}, episode_key="S01E03", source="inference"
    )
    assert len(events2) == 1, "second merge must produce 1 event"
    second_event_id = events2[0].id

    # Both events must exist and be distinct rows
    assert first_event_id != second_event_id, "two merges must produce two distinct event rows"

    async with session_factory() as session:
        all_events = (
            await session.execute(
                select(BibleEvent)
                .where(BibleEvent.entity_id == char_dto.id, BibleEvent.field == "role")
                .order_by(BibleEvent.id)
            )
        ).scalars().all()

    # We expect at least 2 events: the first (detective→spy) and second (spy→double_agent)
    # (There may also be a first-insert event from upsert_character)
    role_change_events = [e for e in all_events if e.old_value is not None]
    assert len(role_change_events) >= 2, (
        f"expected at least 2 change events for 'role', found {len(role_change_events)}"
    )

    # Verify the first event was NOT mutated by the second merge
    first_row = next(e for e in all_events if e.id == first_event_id)
    assert first_row.old_value == "detective"
    assert first_row.new_value == "spy"

    # Verify the second event is correct
    second_row = next(e for e in all_events if e.id == second_event_id)
    assert second_row.old_value == "spy"
    assert second_row.new_value == "double_agent"
