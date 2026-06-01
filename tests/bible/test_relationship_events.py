"""Tests for Phase-6 BIBLE-07 relationship event store, DTO, load, and name matching.

Tests cover:
  BIBLE-07-A — record_relationship_event writes a row; returned DTO has correct character IDs
  BIBLE-07-B — load_series_bible returns relationship_events in SeriesBibleDTO
  BIBLE-07-F — case-insensitive name matching in merge_bible_analysis for events (CR-01)

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.

Phase 6 complete: all tests promoted to real PASS — xfail markers removed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock


# ---------------------------------------------------------------------------
# Helpers — mirror test_address_map.py helper pattern
# ---------------------------------------------------------------------------

async def _create_series(session_factory, arr_series_id: int = 200) -> int:
    """Create a minimal Series row and return its id."""
    from trezarr.bible.store import get_or_create_series
    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=arr_series_id,
        arr_metadata_snapshot={"title": "Relationship Event Test Series"},
    )
    return dto.id


async def _create_characters(
    session_factory,
    series_id: int,
    name_a: str = "Alice",
    name_b: str = "Bob",
) -> tuple[int, int]:
    """Create two Character rows and return (char_a_id, char_b_id)."""
    from trezarr.bible.store import upsert_character
    a, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name=name_a,
        source="inference",
    )
    b, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name=name_b,
        source="inference",
    )
    return a.id, b.id


# ---------------------------------------------------------------------------
# Tests — BIBLE-07-A, B, F
# ---------------------------------------------------------------------------

async def test_relationship_event_written_to_db(session_factory):  # formerly @pytest.mark.xfail — promoted to passing in Phase 6
    """BIBLE-07-A: record_relationship_event writes a row; DTO has correct character IDs.

    Arrange: create a series and two characters via real DB fixtures.
    Act: call record_relationship_event with a valid series/character/episode triple.
    Assert: the returned RelationshipEventDTO has character_a_id and character_b_id
            matching the inputs.
    """
    from trezarr.bible.store import record_relationship_event
    from trezarr.bible.dto import RelationshipEventDTO

    series_id = await _create_series(session_factory, arr_series_id=200)
    char_a_id, char_b_id = await _create_characters(session_factory, series_id, "Alice", "Bob")

    result = await record_relationship_event(
        session_factory,
        series_id=series_id,
        character_a_id=char_a_id,
        character_b_id=char_b_id,
        episode_marker="S01E03",
        description="They become friends in this episode",
    )

    assert isinstance(result, RelationshipEventDTO), (
        f"Expected RelationshipEventDTO, got {type(result)!r}"
    )
    assert result.character_a_id == char_a_id, (
        f"Expected character_a_id={char_a_id}, got {result.character_a_id}"
    )
    assert result.character_b_id == char_b_id, (
        f"Expected character_b_id={char_b_id}, got {result.character_b_id}"
    )


async def test_load_series_bible_includes_events(session_factory):  # formerly @pytest.mark.xfail — promoted to passing in Phase 6
    """BIBLE-07-B: load_series_bible returns relationship_events in SeriesBibleDTO.

    Arrange: write a relationship_event row for a series.
    Act: call load_series_bible.
    Assert: returned SeriesBibleDTO.relationship_events has length >= 1.
    """
    from trezarr.bible.store import record_relationship_event, load_series_bible

    series_id = await _create_series(session_factory, arr_series_id=201)
    char_a_id, char_b_id = await _create_characters(session_factory, series_id, "Minh", "Lan")

    await record_relationship_event(
        session_factory,
        series_id=series_id,
        character_a_id=char_a_id,
        character_b_id=char_b_id,
        episode_marker="S01E04",
        description="Relationship transition in episode 4",
    )

    bible = await load_series_bible(session_factory, series_id=series_id)
    assert bible is not None, "load_series_bible returned None"
    assert hasattr(bible, "relationship_events"), (
        "SeriesBibleDTO is missing relationship_events field"
    )
    assert len(bible.relationship_events) >= 1, (
        f"Expected at least 1 relationship_event, got {len(bible.relationship_events)}"
    )


async def test_name_matching_case_insensitive(session_factory):  # formerly @pytest.mark.xfail — promoted to passing in Phase 6
    """BIBLE-07-F: case-insensitive name matching in merge_bible_analysis (CR-01).

    Arrange: create series + characters with names "alice" / "bob".
    Feed merge_bible_analysis a BibleAnalysis whose RelationshipEventInference
    has character_a_name="ALICE" (different casing from the stored "alice").
    Assert: a relationship_event row is still written — not silently skipped.
    """
    from trezarr.bible.analyze import merge_bible_analysis, BibleAnalysis, RelationshipEventInference
    from trezarr.bible.store import load_series_bible
    from trezarr.config import TrezarrSettings

    series_id = await _create_series(session_factory, arr_series_id=202)
    char_a_id, char_b_id = await _create_characters(session_factory, series_id, "alice", "bob")

    # RelationshipEventInference with UPPER-CASED character name (CR-01 case-insensitivity test)
    analysis = BibleAnalysis(
        relationship_events=[
            RelationshipEventInference(
                character_a_name="ALICE",   # mismatched casing vs stored "alice"
                character_b_name="bob",
                episode_marker="S01E02",
                description="They reconcile in episode 2",
            ),
        ],
    )

    settings = TrezarrSettings(llm_api_key="test-key")
    mock_llm = AsyncMock()

    await merge_bible_analysis(
        analysis=analysis,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E02",
        settings=settings,
    )

    # A row should have been written despite the casing mismatch
    bible = await load_series_bible(session_factory, series_id=series_id)
    assert bible is not None
    assert len(bible.relationship_events) >= 1, (
        "CR-01 violation: case-insensitive name lookup failed — "
        f"no relationship_event written for ALICE vs stored alice. "
        f"Got {len(bible.relationship_events)} events."
    )
