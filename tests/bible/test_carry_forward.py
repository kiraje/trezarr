"""End-to-end carry-forward test (BIBLE-06 success criterion 4).

This test is the narrative proof that a character established in S01E01 persists
unchanged across episodes until a genuinely-different merge_inferred is called.

Design decisions exercised:
  BIBLE-06  carry-forward: same character flows unchanged from S01E01 to finale
  D-32      no-op inference emits zero events
  D-34      human lock > prior > new inference
  D-39      DTO boundary holds throughout
"""
from __future__ import annotations

from sqlalchemy import func, select

from trezarr.bible.models import BibleEvent, Character
from trezarr.bible.store import (
    get_character,
    load_series_bible,
    merge_inferred,
    upsert_character,
)


async def test_character_set_in_s01e01_returns_unchanged_at_s02e03(session_factory):
    """BIBLE-06 carry-forward invariant: narrative end-to-end proof.

    1. upsert_character at S01E01 (first encounter, INSERT).
    2. load_series_bible at any later episode returns the same Mary unchanged.
    3. merge_inferred with identical inference at S02E03 → no-op (zero events).
    4. merge_inferred with a DIFFERENT inference at S02E03 → changes role + appends event.
    """
    from trezarr.bible.store import get_or_create_series

    # Step 0 — Create series
    series_dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=42,
        arr_metadata_snapshot={"title": "Carry Forward Test"},
    )
    series_id = series_dto.id

    # Step 1 — First encounter: INSERT at S01E01
    mary_dto, first_events = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Mary",
        role="detective",
        episode_key="S01E01",
        source="inference",
    )
    assert mary_dto.role == "detective"
    assert any(e.field == "role" for e in first_events), "first insert must emit role event"

    # Step 2 — Load bible at S02E03: Mary must still have role='detective' (carry-forward)
    bible = await load_series_bible(session_factory, series_id)
    mary_in_bible = next((c for c in bible.characters if c.original_latin_name == "Mary"), None)
    assert mary_in_bible is not None, "Mary must appear in the series bible"
    assert mary_in_bible.role == "detective", (
        "Mary's role must be 'detective' unchanged across episodes (BIBLE-06 carry-forward)"
    )

    # Step 3 — No-op merge at S02E03 (identical inference)
    mary_dto2 = await get_character(
        session_factory, series_id=series_id, original_latin_name="Mary"
    )
    assert mary_dto2 is not None

    # Count events BEFORE the no-op merge
    async with session_factory() as session:
        pre_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(BibleEvent.entity_id == mary_dto.id)
        )

    _, noop_events = await merge_inferred(
        session_factory,
        mary_dto2,
        {"role": "detective"},  # identical to current → no-op
        episode_key="S02E03",
        source="inference",
    )
    assert noop_events == [], "no-op inference must emit zero events (BIBLE-06)"

    async with session_factory() as session:
        post_noop_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(BibleEvent.entity_id == mary_dto.id)
        )
    assert post_noop_count == pre_count, (
        "no-op merge must not append any bible_event rows"
    )

    # Step 4 — Genuine change at S02E03: role → 'double_agent'
    mary_dto3 = await get_character(
        session_factory, series_id=series_id, original_latin_name="Mary"
    )
    assert mary_dto3 is not None

    updated, change_events = await merge_inferred(
        session_factory,
        mary_dto3,
        {"role": "double_agent"},
        episode_key="S02E03",
        source="inference",
    )
    assert updated.role == "double_agent", "role must be updated to 'double_agent'"
    assert len(change_events) == 1
    evt = change_events[0]
    assert evt.field == "role"
    assert evt.old_value == "detective"
    assert evt.new_value == "double_agent"
    assert evt.episode_key == "S02E03"
    assert evt.source == "inference"

    # Final audit: the event log tells the full story
    async with session_factory() as session:
        events_in_order = (
            await session.execute(
                select(BibleEvent)
                .where(BibleEvent.entity_id == mary_dto.id, BibleEvent.field == "role")
                .order_by(BibleEvent.id)
            )
        ).scalars().all()

    # The first event was for the initial insert (old=None, new='detective')
    # The last event is the change to 'double_agent'
    last_evt = events_in_order[-1]
    assert last_evt.old_value == "detective"
    assert last_evt.new_value == "double_agent"
    assert last_evt.episode_key == "S02E03"
