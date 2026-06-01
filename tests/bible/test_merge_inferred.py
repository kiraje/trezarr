"""Integration tests for merge_inferred(), upsert_character(), upsert_term() (04-03).

These tests exercise the full store layer with a real SQLite DB (via session_factory
fixture from tests/db/conftest.py, re-exported by tests/bible/conftest.py).

All async tests run under asyncio_mode="auto" — no @pytest.mark.asyncio needed.

Design decisions exercised:
  D-34  human lock > prior value > new inference (lock survives contradiction)
  D-32  mutable-current + append-only bible_event (atomicity, no-op detection)
  BIBLE-06  carry-forward: no-op inference emits no event
  D-39  DTO boundary: public functions return Pydantic DTOs, never SQLA models
  HIGH  _merge_inferred_in_session re-reads the row inside the transaction (stale-DTO fix)
  HIGH  No nested session.begin() blocks (single-transaction owner invariant)
  MEDIUM  MERGEABLE_FIELDS whitelist enforced; identity columns rejected
  MEDIUM  First-insert emits one event per non-None field with old_value=None
  MEDIUM  Clearing a field to None produces a correct audit event
"""
from __future__ import annotations

import pytest
from sqlalchemy import event, func, select

from trezarr.bible.dto import BibleEventDTO, CharacterDTO, TermDTO
from trezarr.bible.models import BibleEvent, Character, TermDictionary
from trezarr.bible.store import (
    get_character,
    merge_inferred,
    upsert_character,
    upsert_term,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_series(session_factory, arr_series_id=1):
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


# ---------------------------------------------------------------------------
# Test 1: Locked field survives a contradicting inference (D-34 / SUCCESS CRITERION 4)
# ---------------------------------------------------------------------------

async def test_locked_field_survives_contradicting_inference(session_factory):
    """Lock wins — merge_inferred must NOT overwrite a locked field.

    Arrange: Character with role='detective' and locked_fields=['role'].
    Act:     merge_inferred({'role': 'spy'}).
    Assert:  updated.role == 'detective'; events == []; zero bible_event rows.
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
    # Manually set locked_fields on the SQLA row (Phase 4 only does this in tests)
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(Character, char_dto.id)
            row.locked_fields = ["role"]

    # Re-fetch fresh DTO after locking
    dto = await get_character(session_factory, series_id=series_id, original_latin_name="Mary")
    assert dto is not None
    assert dto.locked_fields == ["role"]

    # Count events BEFORE the contradicting merge (may include first-insert events)
    async with session_factory() as session:
        pre_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(BibleEvent.entity_id == char_dto.id)
        )

    # Act
    updated, events = await merge_inferred(
        session_factory, dto, {"role": "spy"}, episode_key="S02E03", source="inference"
    )

    # Assert
    assert updated.role == "detective", "locked field must not be overwritten"
    assert events == [], "no event must be emitted for a locked field"

    async with session_factory() as session:
        post_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(BibleEvent.entity_id == char_dto.id)
        )
    assert post_count == pre_count, (
        "merge_inferred with locked field must not append any new bible_event rows"
    )


# ---------------------------------------------------------------------------
# Test 2: Unlocked field updates and emits a bible_event
# ---------------------------------------------------------------------------

async def test_unlocked_field_updates_and_emits_event(session_factory):
    """Unlocked field changed by merge_inferred → row updated + one bible_event."""
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

    updated, events = await merge_inferred(
        session_factory, dto, {"role": "spy"}, episode_key="S02E03", source="inference"
    )

    assert updated.role == "spy"
    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, BibleEventDTO)
    assert evt.entity_type == "character"
    assert evt.field == "role"
    assert evt.old_value == "detective"
    assert evt.new_value == "spy"
    assert evt.source == "inference"
    assert evt.episode_key == "S02E03"

    # DB confirmation: exactly one event for S02E03/role/spy change
    async with session_factory() as session:
        merge_evt_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(
                BibleEvent.entity_id == char_dto.id,
                BibleEvent.episode_key == "S02E03",
                BibleEvent.field == "role",
            )
        )
        assert merge_evt_count == 1


# ---------------------------------------------------------------------------
# Test 3: No-op inference emits no event (BIBLE-06 carry-forward invariant)
# ---------------------------------------------------------------------------

async def test_noop_inference_emits_no_event_BIBLE_06(session_factory):
    """Identical inference must not produce a bible_event (BIBLE-06 no-op rule)."""
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

    # Count events BEFORE the no-op merge
    async with session_factory() as session:
        pre_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(BibleEvent.entity_id == char_dto.id)
        )

    updated, events = await merge_inferred(
        session_factory, dto, {"role": "detective"}, episode_key="S02E03", source="inference"
    )

    assert updated.role == "detective"
    assert events == []

    async with session_factory() as session:
        post_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(BibleEvent.entity_id == char_dto.id)
        )
    assert post_count == pre_count, "no-op inference must not append any bible_event rows"


# ---------------------------------------------------------------------------
# Test 4: Multiple fields with partial locks
# ---------------------------------------------------------------------------

async def test_multiple_field_partial_lock(session_factory):
    """role locked, gender unlocked+changed — exactly one event (for gender, not role)."""
    series_id = await _create_series(session_factory)
    char_dto, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Mary",
        role="detective",
        gender="female",
        episode_key="S01E01",
        source="inference",
    )

    # Lock role
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(Character, char_dto.id)
            row.locked_fields = ["role"]

    dto = await get_character(session_factory, series_id=series_id, original_latin_name="Mary")
    assert dto is not None

    updated, events = await merge_inferred(
        session_factory,
        dto,
        {"role": "spy", "gender": "other"},
        episode_key="S02E03",
        source="inference",
    )

    assert updated.role == "detective", "locked role must not change"
    assert updated.gender == "other", "unlocked gender must change"
    assert len(events) == 1
    assert events[0].field == "gender"

    # DB confirmation: exactly one event from the merge for S02E03/gender change
    async with session_factory() as session:
        merge_evt_count = await session.scalar(
            select(func.count()).select_from(BibleEvent)
            .where(
                BibleEvent.entity_id == char_dto.id,
                BibleEvent.episode_key == "S02E03",
                BibleEvent.field == "gender",
            )
        )
        assert merge_evt_count == 1


# ---------------------------------------------------------------------------
# Test 5: Atomic transaction — event INSERT failure rolls back UPDATE
# ---------------------------------------------------------------------------

async def test_atomic_transaction_event_insert_failure_rolls_back_update(session_factory):
    """Atomicity: if BibleEvent INSERT fails, the Character UPDATE rolls back.

    Uses a SQLAlchemy event-listener to inject a RuntimeError at before_insert
    for BibleEvent. After the failure, the Character row must have the original
    value (rollback confirmed).
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
    original_role = dto.role

    # Inject failure via SQLAlchemy event listener
    def _force_failure(mapper, conn, target):
        raise RuntimeError("forced bible_event INSERT failure")

    event.listen(BibleEvent, "before_insert", _force_failure)
    try:
        with pytest.raises(RuntimeError, match="forced bible_event INSERT failure"):
            await merge_inferred(
                session_factory, dto, {"role": "spy"}, episode_key="S02E03", source="inference"
            )
    finally:
        event.remove(BibleEvent, "before_insert", _force_failure)

    # Verify rollback: Character.role must still be the original value
    async with session_factory() as session:
        row = await session.get(Character, char_dto.id)
        assert row.role == original_role, (
            f"UPDATE must have rolled back; expected role={original_role!r}, got {row.role!r}"
        )


# ---------------------------------------------------------------------------
# Test 6: merge_inferred returns DTOs (D-39 boundary)
# ---------------------------------------------------------------------------

async def test_merge_inferred_returns_dtos_not_sqla_models(session_factory):
    """D-39: returned (entity, events) must be Pydantic DTOs, never SQLA models."""
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

    updated, events = await merge_inferred(
        session_factory, dto, {"role": "spy"}, episode_key="S01E02", source="inference"
    )

    assert type(updated) is CharacterDTO, f"expected CharacterDTO, got {type(updated)}"
    assert all(type(e) is BibleEventDTO for e in events), "all events must be BibleEventDTO"


# ---------------------------------------------------------------------------
# Test 7: source enum values accepted; invalid source raises before DB write
# ---------------------------------------------------------------------------

async def test_source_enum_values_accepted(session_factory):
    """Each valid source string works; invalid source raises ValueError before any DB write."""
    series_id = await _create_series(session_factory)

    # Create characters for each valid source
    for i, src in enumerate(["inference", "lock", "import", "system"]):
        char_dto, _ = await upsert_character(
            session_factory,
            series_id=series_id,
            original_latin_name=f"Mary_{src}",
            role="detective",
            episode_key="S01E01",
            source="inference",
        )
        dto = await get_character(
            session_factory, series_id=series_id, original_latin_name=f"Mary_{src}"
        )
        assert dto is not None
        updated, events = await merge_inferred(
            session_factory, dto, {"role": "spy"}, episode_key="S01E02", source=src
        )
        assert len(events) == 1
        assert events[0].source == src

    # Invalid source must raise ValueError before any DB write
    char_dto2, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Mary_invalid",
        role="detective",
        episode_key="S01E01",
        source="inference",
    )
    dto2 = await get_character(
        session_factory, series_id=series_id, original_latin_name="Mary_invalid"
    )
    assert dto2 is not None
    with pytest.raises(ValueError, match="source must be one of"):
        await merge_inferred(
            session_factory, dto2, {"role": "spy"}, episode_key="S01E02", source="invalid"
        )


# ---------------------------------------------------------------------------
# Test 8: TermDictionary merge works identically to Character merge
# ---------------------------------------------------------------------------

async def test_term_dictionary_merge_works_identically(session_factory):
    """merge_inferred is entity-type-agnostic; TermDictionary row writes entity_type='term_dictionary'."""
    series_id = await _create_series(session_factory)
    term_dto, _ = await upsert_term(
        session_factory,
        series_id=series_id,
        source_term="Hanoi",
        vietnamese_rendering="Hà Nội",
        episode_key="S01E01",
        source="inference",
    )

    from trezarr.bible.store import get_term
    dto = await get_term(session_factory, series_id=series_id, source_term="Hanoi")
    assert dto is not None

    updated, events = await merge_inferred(
        session_factory, dto, {"vietnamese_rendering": "Vương Đô"}, episode_key="S01E02", source="inference"
    )

    assert isinstance(updated, TermDTO)
    assert updated.vietnamese_rendering == "Vương Đô"
    assert len(events) == 1
    evt = events[0]
    assert evt.entity_type == "term_dictionary"
    assert evt.field == "vietnamese_rendering"
    assert evt.old_value == "Hà Nội"
    assert evt.new_value == "Vương Đô"


# ---------------------------------------------------------------------------
# Test 9: Stale DTO old_value correctness (HIGH finding fix)
# ---------------------------------------------------------------------------

async def test_stale_dto_old_value_correctness(session_factory):
    """old_value in bible_event must reflect the ACTUAL pre-write DB state, not the stale DTO.

    Sequence:
    1. Insert Character with role='detective'.
    2. Build stale DTO (role='detective').
    3. Out-of-band DB update: role → 'spy' (simulates concurrent write).
    4. Call merge_inferred with stale_dto + {'role': 'informant'}.
    5. bible_event.old_value must be 'spy' (from fresh DB re-read), NOT 'detective' (stale).
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

    # Build the stale DTO (role='detective')
    stale_dto = await get_character(
        session_factory, series_id=series_id, original_latin_name="Mary"
    )
    assert stale_dto is not None
    assert stale_dto.role == "detective"

    # Out-of-band write: change role to 'spy' WITHOUT going through merge_inferred
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(Character, char_dto.id)
            row.role = "spy"
    # stale_dto still says role='detective' — this is the stale read scenario

    # Act: merge with stale DTO
    updated, events = await merge_inferred(
        session_factory,
        stale_dto,  # stale: still says role='detective'
        {"role": "informant"},
        episode_key="S02E03",
        source="inference",
    )

    assert updated.role == "informant"
    assert len(events) == 1
    # CRITICAL: old_value must be 'spy' (actual pre-write state), NOT 'detective' (stale DTO)
    assert events[0].old_value == "spy", (
        f"old_value must reflect actual DB state ('spy'), not stale DTO ('detective'); "
        f"got {events[0].old_value!r}"
    )


# ---------------------------------------------------------------------------
# Test 10: No nested transactions in upsert_character (HIGH finding fix)
# ---------------------------------------------------------------------------

async def test_no_nested_transactions_in_upsert(session_factory):
    """Public upsert_character must open exactly ONE transaction — no nesting.

    WR-06: The previous implementation monkey-patched ``session.begin`` on
    the instance, which had three problems:
      1. Anything calling ``type(session).begin(session)`` instead of
         ``session.begin()`` would silently bypass the counter.
      2. The counter only saw ``session.begin()`` — a ``session.begin_nested()``
         (SAVEPOINT) call would be invisible and the test would pass on
         broken code that opened a savepoint.
      3. Only the merge path was exercised; the CREATE path used the
         un-patched factory, so the single-transaction invariant for INSERT
         was not actually verified.

    The new implementation registers an ``after_transaction_create`` listener
    on the underlying synchronous Session (the one wrapped by AsyncSession),
    which fires for BOTH top-level transactions and savepoints. To exclude
    the AUTOBEGIN transaction that SQLAlchemy creates implicitly on first
    operation, we filter for transactions that have no parent (top-level)
    and that are not part of the session's connection-init phase.

    Both the CREATE path AND the MERGE path are exercised under the listener
    so the single-transaction invariant is verified on both branches.
    """
    from sqlalchemy.orm import Session as SyncSession

    series_id = await _create_series(session_factory)

    # Total non-autobegin transactions observed across all sessions in this
    # test. ``after_transaction_create`` fires with a SessionTransaction; we
    # count both regular (.parent is None) and SAVEPOINT (.nested is True)
    # creations so a hypothetical ``begin_nested()`` regression would also
    # trip this assertion.
    txn_count = {"n": 0}

    def _on_txn_create(session: SyncSession, transaction) -> None:  # noqa: ARG001
        # SQLAlchemy fires ``after_transaction_create`` for every level of
        # the transaction stack. The hierarchy on the AsyncSession path is:
        #   - top-level SessionTransaction (parent=None) — what we count
        #   - a nested marker for the AsyncSession.begin() wrapper
        #   - possibly more for per-statement subtxns
        # We only count TOP-LEVEL transactions (parent is None) so we get
        # exactly one event per ``async with session.begin():`` block. A
        # second top-level txn within the same session would indicate a
        # nested explicit begin() — the failure mode the test guards
        # against. SAVEPOINTs (transaction.nested=True) have parent set, so
        # they would NOT be top-level — to also catch those (per the
        # reviewer's WR-06 second point) we count them separately and
        # assert both totals.
        if transaction.parent is None:
            txn_count["n"] += 1
        elif transaction.nested:
            # A SAVEPOINT inside our transaction is also a "nested
            # transaction" the test must refuse. Count under the same key
            # so the assertion message names the regression.
            txn_count["n"] += 1

    # Register globally on Session so it catches transactions on every
    # AsyncSession.sync_session created from session_factory().
    event.listen(SyncSession, "after_transaction_create", _on_txn_create)
    try:
        # Reset before the CREATE path so we can assert exactly 1
        txn_count["n"] = 0
        await upsert_character(
            session_factory,
            series_id=series_id,
            original_latin_name="Mary",
            role="detective",
            episode_key="S01E01",
            source="inference",
        )
        create_txn_count = txn_count["n"]
        assert create_txn_count == 1, (
            f"upsert_character (CREATE path) must open exactly 1 transaction, "
            f"opened {create_txn_count}"
        )

        # Reset before the MERGE path
        txn_count["n"] = 0
        await upsert_character(
            session_factory,
            series_id=series_id,
            original_latin_name="Mary",
            role="spy",  # change to trigger merge path
            episode_key="S02E01",
            source="inference",
        )
        merge_txn_count = txn_count["n"]
        assert merge_txn_count == 1, (
            f"upsert_character (MERGE path) must open exactly 1 transaction, "
            f"opened {merge_txn_count}"
        )
    finally:
        event.remove(SyncSession, "after_transaction_create", _on_txn_create)


# ---------------------------------------------------------------------------
# Test 11: Unsupported inferred fields are rejected (MEDIUM finding — whitelist)
# ---------------------------------------------------------------------------

async def test_unsupported_inferred_fields_rejected(session_factory):
    """Identity columns and non-mergeable fields must be rejected with ValueError."""
    series_id = await _create_series(session_factory)
    char_dto, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Mary",
        role="detective",
        episode_key="S01E01",
        source="inference",
    )
    char_dto_fresh = await get_character(
        session_factory, series_id=series_id, original_latin_name="Mary"
    )
    assert char_dto_fresh is not None

    # original_latin_name is an identity column — not mergeable
    with pytest.raises(ValueError, match="not mergeable"):
        await merge_inferred(
            session_factory,
            char_dto_fresh,
            {"original_latin_name": "NewName"},
            episode_key="S02E01",
            source="inference",
        )

    # TermDictionary: source_term is an identity column — not mergeable
    term_dto, _ = await upsert_term(
        session_factory,
        series_id=series_id,
        source_term="Hanoi",
        vietnamese_rendering="Hà Nội",
        episode_key="S01E01",
        source="inference",
    )
    from trezarr.bible.store import get_term
    term_dto_fresh = await get_term(
        session_factory, series_id=series_id, source_term="Hanoi"
    )
    assert term_dto_fresh is not None

    with pytest.raises(ValueError, match="not mergeable"):
        await merge_inferred(
            session_factory,
            term_dto_fresh,
            {"source_term": "NewTerm"},
            episode_key="S02E01",
            source="inference",
        )


# ---------------------------------------------------------------------------
# Test 12: First insert emits one event per non-None field (MEDIUM finding)
# ---------------------------------------------------------------------------

async def test_first_insert_emits_event_per_non_none_field(session_factory):
    """upsert_character on a new row emits one bible_event per non-None field with old_value=None.

    Arrange: series exists, no Mary character yet.
    Act:     upsert_character(gender='female', role='detective', rough_age=None).
    Assert:  Exactly 2 events — one for gender (old=None, new='female'),
                                 one for role (old=None, new='detective').
             rough_age=None → no event.
    """
    series_id = await _create_series(session_factory)

    char_dto, events = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name="Alice",
        gender="female",
        role="detective",
        rough_age=None,  # None → no event
        episode_key="S01E01",
        source="inference",
    )

    assert len(events) == 2, f"expected 2 events (gender + role), got {len(events)}: {events}"

    field_map = {e.field: e for e in events}
    assert "gender" in field_map, "event for 'gender' must be emitted"
    assert field_map["gender"].old_value is None
    assert field_map["gender"].new_value == "female"
    assert "role" in field_map, "event for 'role' must be emitted"
    assert field_map["role"].old_value is None
    assert field_map["role"].new_value == "detective"
    assert "rough_age" not in field_map, "no event for rough_age=None"

    # All events must have old_value=None (first insert)
    for e in events:
        assert e.old_value is None, f"first-insert event must have old_value=None, got {e.old_value!r}"


# ---------------------------------------------------------------------------
# Test 13: Clearing a field to None via merge produces a correct audit event
# ---------------------------------------------------------------------------

async def test_clearing_field_to_none_via_merge(session_factory):
    """Clearing a field to None via merge_inferred produces a bible_event with new_value=None."""
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
    assert dto.role == "detective"

    updated, events = await merge_inferred(
        session_factory, dto, {"role": None}, episode_key="S01E02", source="inference"
    )

    assert updated.role is None, "role must be cleared to None"
    assert len(events) == 1
    evt = events[0]
    assert evt.field == "role"
    assert evt.old_value == "detective"
    assert evt.new_value is None
