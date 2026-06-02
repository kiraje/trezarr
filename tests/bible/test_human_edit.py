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

async def test_lock_state_in_dto(session_factory):
    """BIBLE-08 c1: locked_fields visible in DTO response."""
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=801)
    speaker_id, _ = await _create_characters(session_factory, series_id)
    dto, evt = await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert "gender" in dto.locked_fields, (
        f"locked_fields must contain 'gender' after lock=True, got {dto.locked_fields!r}"
    )
    assert evt.source == "lock", f"BibleEvent source must be 'lock', got {evt.source!r}"
    assert evt.field == "gender"
    assert evt.new_value == "male"


async def test_locked_field_survives_merge(session_factory):
    """BIBLE-08 c2: human-locked character field not overwritten by subsequent merge_inferred with contradicting value."""
    from trezarr.bible.store import apply_human_edit_character, merge_inferred  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=802)
    speaker_id, _ = await _create_characters(session_factory, series_id)
    # Lock gender="male"
    dto_locked, _ = await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    assert "gender" in dto_locked.locked_fields

    # Now merge_inferred tries to set gender="female" — must be blocked by lock
    updated_dto, events = await merge_inferred(
        session_factory,
        dto_locked,
        {"gender": "female"},
        episode_key="S01E01",
        source="inference",
    )
    # Locked field must survive — still "male", not "female"
    assert updated_dto.gender == "male", (
        f"Locked gender must survive merge_inferred('female'), got {updated_dto.gender!r}"
    )
    # No event emitted for the locked field (merge skips it)
    assert not any(e.field == "gender" for e in events), (
        "merge_inferred must not emit an event for a locked field"
    )


async def test_locked_fields_persisted(session_factory):
    """BIBLE-08 c2: JSON dirty-tracking — locked_fields persisted correctly (reassign-not-append pattern, D-80)."""
    from trezarr.bible.store import apply_human_edit_character, load_series_bible  # noqa: PLC0415
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
    # Reload from DB to verify persistence
    bible = await load_series_bible(session_factory, series_id)
    character = next(c for c in bible.characters if c.id == speaker_id)
    assert "gender" in character.locked_fields, (
        f"locked_fields must be persisted to DB; got {character.locked_fields!r}"
    )


async def test_bible_event_emitted_on_lock(session_factory):
    """BIBLE-08 c2: apply_human_edit emits BibleEvent(source='lock') in same transaction (D-32)."""
    from trezarr.bible.store import apply_human_edit_character, load_field_history  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=804)
    speaker_id, _ = await _create_characters(session_factory, series_id)
    dto, evt = await apply_human_edit_character(
        session_factory,
        character_id=speaker_id,
        series_id=series_id,
        field="gender",
        new_value="male",
        lock=True,
    )
    # Verify event was persisted (load_field_history reads from DB)
    history = await load_field_history(
        session_factory,
        series_id=series_id,
        entity_type="character",
        entity_id=speaker_id,
        field="gender",
    )
    assert len(history) >= 1, "At least one BibleEvent must be persisted for the lock"
    lock_events = [e for e in history if e.source == "lock"]
    assert lock_events, f"Expected BibleEvent(source='lock') in history, got {history!r}"
    assert lock_events[0].field == "gender"
    assert lock_events[0].new_value == "male"


async def test_locked_pair_survives_reconcile(session_factory):
    """BIBLE-09 c3: edit→lock→re-analyze: locked pair survives reconcile_attributions (reconcile.py:267-277)."""
    from trezarr.bible.store import apply_human_edit_address_pair, upsert_address_pair  # noqa: PLC0415
    from trezarr.translate.reconcile import reconcile_attributions  # noqa: PLC0415
    from types import SimpleNamespace

    series_id = await _create_series(session_factory, arr_series_id=805)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)

    # Create an address_map entry and lock it
    pair_dto, _ = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=speaker_id,
        addressee_character_id=addressee_id,
        self_term="anh",
        address_term="em",
        episode_key="S01E01",
        source="inference",
    )
    # Lock the pair with human-confirmed terms
    locked_pair, _ = await apply_human_edit_address_pair(
        session_factory,
        address_map_id=pair_dto.id,
        series_id=series_id,
        self_term="anh",
        address_term="em",
        lock=True,
    )
    assert "self_term" in locked_pair.locked_fields
    assert "address_term" in locked_pair.locked_fields

    # Build a bible DTO with the locked pair
    def _make_character(id_, name, gender=None):
        return SimpleNamespace(
            id=id_, series_id=series_id, original_latin_name=name,
            gender=gender, rough_age=None, role=None, locked_fields=[],
        )

    bible = SimpleNamespace(
        id=series_id, arr_kind="sonarr", arr_instance="default", arr_series_id=805,
        characters=[
            _make_character(speaker_id, "Minh", "male"),
            _make_character(addressee_id, "Lan", "female"),
        ],
        terms=[],
        address_map=[locked_pair],
        locked_fields=[],
        relationship_events=[],
    )

    settings = SimpleNamespace(
        pronoun_confidence_threshold="medium",
        pronoun_safe_default=None,
        enable_relationship_events=True,
    )

    # Attribute that contradicts the lock (tries to infer different pair)
    attribution = SimpleNamespace(
        line_index=1, speaker="Minh", addressee="Lan",
        confidence=type("C", (), {"value": "high", "__str__": lambda self: "high"})(),
    )

    resolved = await reconcile_attributions(
        flat_attributions=[attribution],
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E02",
        settings=settings,
    )

    # The locked pair must survive — reconcile_attributions must return ("anh", "em")
    pair_result = resolved.get((speaker_id, addressee_id))
    assert pair_result is not None, "Expected resolved entry for locked pair"
    assert pair_result == ("anh", "em"), (
        f"Locked pair ('anh', 'em') must survive reconcile_attributions, got {pair_result!r}"
    )


async def test_locked_pair_propagates_to_next_episode(session_factory):
    """BIBLE-09 c3: edit→lock→next episode: locked pair still applied (BIBLE-06 carry-forward + lock combo)."""
    from trezarr.bible.store import apply_human_edit_address_pair, upsert_address_pair  # noqa: PLC0415
    from trezarr.translate.reconcile import reconcile_attributions  # noqa: PLC0415
    from types import SimpleNamespace

    series_id = await _create_series(session_factory, arr_series_id=806)
    speaker_id, addressee_id = await _create_characters(session_factory, series_id)

    # Create and lock a pair in episode 1
    pair_dto, _ = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=speaker_id,
        addressee_character_id=addressee_id,
        self_term="chị",
        address_term="em",
        episode_key="S01E01",
        source="inference",
    )
    locked_pair, _ = await apply_human_edit_address_pair(
        session_factory,
        address_map_id=pair_dto.id,
        series_id=series_id,
        self_term="chị",
        address_term="em",
        lock=True,
    )
    assert "self_term" in locked_pair.locked_fields
    assert "address_term" in locked_pair.locked_fields

    def _make_character(id_, name, gender=None):
        return SimpleNamespace(
            id=id_, series_id=series_id, original_latin_name=name,
            gender=gender, rough_age=None, role=None, locked_fields=[],
        )

    bible = SimpleNamespace(
        id=series_id, arr_kind="sonarr", arr_instance="default", arr_series_id=806,
        characters=[
            _make_character(speaker_id, "Minh", "female"),
            _make_character(addressee_id, "Lan", "female"),
        ],
        terms=[],
        address_map=[locked_pair],
        locked_fields=[],
        relationship_events=[],
    )

    settings = SimpleNamespace(
        pronoun_confidence_threshold="medium",
        pronoun_safe_default=None,
        enable_relationship_events=True,
    )

    # Episode 2: no attribution for the pair — carry-forward + lock must apply
    attribution = SimpleNamespace(
        line_index=1, speaker="Minh", addressee="Lan",
        confidence=type("C", (), {"value": "high", "__str__": lambda self: "high"})(),
    )

    resolved = await reconcile_attributions(
        flat_attributions=[attribution],
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E02",
        settings=settings,
    )

    pair_result = resolved.get((speaker_id, addressee_id))
    assert pair_result is not None, "Locked pair must be present in resolved_map for next episode"
    assert pair_result == ("chị", "em"), (
        f"Locked pair ('chị', 'em') must propagate to next episode, got {pair_result!r}"
    )


async def test_locked_term_survives_merge(session_factory):
    """BIBLE-08 c1: locking a Term via apply_human_edit_term; locked vietnamese_rendering survives merge_inferred (all four entity types lockable)."""
    from trezarr.bible.store import apply_human_edit_term, upsert_term, merge_inferred  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=807)

    # Create and lock the term
    term_dto, evt = await apply_human_edit_term(
        session_factory,
        series_id=series_id,
        source_term="hello",
        field="vietnamese_rendering",
        new_value="xin chào",
        lock=True,
    )
    assert term_dto.vietnamese_rendering == "xin chào"
    assert "vietnamese_rendering" in term_dto.locked_fields, (
        f"locked_fields must contain 'vietnamese_rendering', got {term_dto.locked_fields!r}"
    )
    assert evt.source == "lock"

    # merge_inferred tries to overwrite the locked rendering — must be blocked
    updated_dto, events = await merge_inferred(
        session_factory,
        term_dto,
        {"vietnamese_rendering": "xin chao (overwrite)"},
        episode_key="S01E01",
        source="inference",
    )
    assert updated_dto.vietnamese_rendering == "xin chào", (
        f"Locked vietnamese_rendering must survive merge_inferred, got {updated_dto.vietnamese_rendering!r}"
    )
    assert not any(e.field == "vietnamese_rendering" for e in events), (
        "merge_inferred must not emit event for a locked field"
    )


async def test_locked_register_survives(session_factory):
    """BIBLE-08 c1: locking series register via apply_human_edit_series; locked register_value survives re-analysis (all four entity types lockable, register_value alias per CR-02)."""
    from trezarr.bible.store import apply_human_edit_series, merge_inferred  # noqa: PLC0415
    series_id = await _create_series(session_factory, arr_series_id=808)

    # Lock the register
    series_dto, evt = await apply_human_edit_series(
        session_factory,
        series_id=series_id,
        field="register",
        new_value="formal",
        lock=True,
    )
    # CR-02: the DTO field is register_value with alias "register"
    assert series_dto.register_value == "formal", (
        f"register_value must be 'formal' after apply_human_edit_series, got {series_dto.register_value!r}"
    )
    assert "register" in series_dto.locked_fields, (
        f"locked_fields must contain 'register', got {series_dto.locked_fields!r}"
    )
    assert evt.source == "lock"
    assert evt.field == "register"

    # merge_inferred tries to overwrite the locked register — must be blocked
    updated_dto, events = await merge_inferred(
        session_factory,
        series_dto,
        {"register": "informal"},
        episode_key="S01E01",
        source="inference",
    )
    assert updated_dto.register_value == "formal", (
        f"Locked register must survive merge_inferred('informal'), got {updated_dto.register_value!r}"
    )
    assert not any(e.field == "register" for e in events), (
        "merge_inferred must not emit event for a locked field"
    )
