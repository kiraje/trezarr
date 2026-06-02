"""Tests for Phase 8 human-edit write path (BIBLE-08/09).

Tests cover:
  BIBLE-08 criterion 2 — locked field survives a contradicting merge_inferred call
  BIBLE-08 criterion 2 — JSON dirty-tracking: locked_fields persisted correctly
  BIBLE-08 criterion 2 — BibleEvent(source="lock") emitted in same transaction
  BIBLE-09 criterion 3 — locked pair survives reconcile_attributions
  BIBLE-09 criterion 3 — locked pair propagates to next episode

asyncio_mode="auto" is configured project-wide in pyproject.toml — no @pytest.mark.asyncio.
DB fixtures provided via tests/bible/conftest.py (re-exports from tests/db/conftest.py).
"""
from __future__ import annotations

import pytest


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

@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_character not yet created — Plan 08-02",
)
async def test_lock_state_in_dto(session_factory):
    """BIBLE-08 c1: locked_fields visible in DTO response."""
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=801)
    speaker_id, _ = await _create_characters(session_factory, series_id)
    dto, _evt = await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_character not yet created — Plan 08-02",
)
async def test_locked_field_survives_merge(session_factory):
    """BIBLE-08 c2: human-locked character field not overwritten by subsequent merge_inferred with contradicting value."""
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=802)
    speaker_id, _ = await _create_characters(session_factory, series_id)
    await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_character not yet created — Plan 08-02",
)
async def test_locked_fields_persisted(session_factory):
    """BIBLE-08 c2: JSON dirty-tracking — locked_fields persisted correctly (reassign-not-append pattern, D-80)."""
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=803)
    speaker_id, _ = await _create_characters(session_factory, series_id)
    await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_character not yet created — Plan 08-02",
)
async def test_bible_event_emitted_on_lock(session_factory):
    """BIBLE-08 c2: apply_human_edit emits BibleEvent(source='lock') in same transaction (D-32)."""
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=804)
    speaker_id, _ = await _create_characters(session_factory, series_id)
    await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_character not yet created — Plan 08-02",
)
async def test_locked_pair_survives_reconcile(session_factory):
    """BIBLE-09 c3: edit→lock→re-analyze: locked pair survives reconcile_attributions (reconcile.py:267-277)."""
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=805)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)
    await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_character not yet created — Plan 08-02",
)
async def test_locked_pair_propagates_to_next_episode(session_factory):
    """BIBLE-09 c3: edit→lock→next episode: locked pair still applied (BIBLE-06 carry-forward + lock combo)."""
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=806)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)
    await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_term not yet created — Plan 08-02",
)
async def test_locked_term_survives_merge(session_factory):
    """BIBLE-08 c1: locking a Term via apply_human_edit_term; locked vietnamese_rendering survives merge_inferred (all four entity types lockable)."""
    from trezarr.bible.store import apply_human_edit_term  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=807)
    await apply_human_edit_term(
        session_factory,
        series_id=series_id,
        source_term="hello",
        field="vietnamese_rendering",
        new_value="xin chào",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="apply_human_edit_series not yet created — Plan 08-02",
)
async def test_locked_register_survives(session_factory):
    """BIBLE-08 c1: locking series register via apply_human_edit_series; locked register_value survives re-analysis (all four entity types lockable, register_value alias per CR-02)."""
    from trezarr.bible.store import apply_human_edit_series  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=808)
    await apply_human_edit_series(
        session_factory,
        series_id=series_id,
        field="register",
        new_value="formal",
        lock=True,
    )
    assert False  # placeholder — Plan 08-02 will implement
