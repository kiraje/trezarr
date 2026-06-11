"""Series Bible store — Pydantic-typed API hiding SQLAlchemy internals (D-39).

Public API (the ONLY surface Phase 5+ may import):
    load_series_bible(session_factory, series_id) -> SeriesBibleDTO
    get_or_create_series(session_factory, *, arr_kind, arr_instance, arr_series_id,
                         arr_metadata_snapshot, tvdb_id=None, tmdb_id=None) -> SeriesDTO
    get_character(session_factory, series_id, original_latin_name) -> CharacterDTO | None
    get_term(session_factory, series_id, source_term) -> TermDTO | None
    upsert_character(session_factory, *, series_id, original_latin_name, ...) -> (CharacterDTO, list[BibleEventDTO])
    upsert_term(session_factory, *, series_id, source_term, ...) -> (TermDTO, list[BibleEventDTO])
    merge_inferred(session_factory, entity_dto, inferred, episode_key, source)
        -> tuple[CharacterDTO | TermDTO | SeriesDTO, list[BibleEventDTO]]

Internal (private — never call from outside this module):
    _merge_inferred_in_session(session, row, entity_type, dto_cls, inferred, episode_key, source)
    _upsert_character_in_session(session, ...)
    _upsert_term_in_session(session, ...)

All SQLAlchemy imports stay inside this module. Sessions are opened with
`async with session_factory()` and never escape. Public upsert_* and merge_inferred
are the ONLY transaction owners — private helpers run inside the caller's transaction.

Design decisions honoured:
  D-32  Atomic transactions: SELECT+INSERT inside a single session.begin() block.
        merge_inferred performs current-row UPDATE + bible_event INSERT(s) in ONE txn.
  D-33  UNIQUE(arr_kind, arr_instance, arr_series_id) identity key; tvdb_id/tmdb_id
        denormalized at creation but NOT used for lookup in v1.
  D-34  human lock > prior > new inference. _merge_inferred_in_session reads
        locked_fields and old_value OFF THE SQLA ROW inside the transaction —
        never relies on the caller's potentially-stale DTO (HIGH finding fix).
        WR-01: this is not a "fresh re-read" in the identity-map sense; within
        the same AsyncSession session.get returns the SAME Python object as
        the caller passed in. The stale-DTO defence is that we never read
        through the DTO at all; the SQLA row is canonical for this transaction.
  D-35  arr_metadata is a JSON snapshot captured at series-row creation; register
        stays NULL (Phase 5 sets it via merge_inferred like any other Bible field).
  D-36  Lazy series-row creation on first translate — no startup enumeration.
  D-39  Pydantic DTOs at the store boundary; SQLAlchemy models never escape.
  Pitfall 2  expire_on_commit=False propagates from the session_factory (mandatory
             for async SQLAlchemy — accessing expired attributes post-commit deadlocks).
  Pitfall 7  Never `session.add(dto)` — always construct the SQLA model row, then
             convert to DTO via model_validate(row, from_attributes=True) after flush.
  Pitfall 9  merge_inferred does NOT call out to an LLM from inside the transaction.
             Transactions are kept short (UPDATE + INSERT only — no I/O).
  HIGH   _merge_inferred_in_session reads locked + old_value off the SQLA row
         inside the transaction (NOT off the caller's DTO). The SQLA row's
         attribute values reflect the in-session pre-write state; the caller's
         DTO may carry pre-write state from a prior session. WR-01: within the
         same AsyncSession session.get(model, pk) returns the same identity-
         map handle the caller already holds — so this does not bypass any
         cache. The real guarantee is that we never trust the DTO; we read the
         row.

  HIGH   No nested session.begin() blocks: public upsert_* and merge_inferred are the
         ONLY transaction owners. Private helpers run inside the caller's transaction.

Known limitations:
    processed_file.source_path uniqueness is path-string equality only. Case
    sensitivity depends on the host filesystem (case-insensitive on macOS/Windows,
    case-sensitive on Linux). If the same file is referenced with different path
    casing on a case-insensitive filesystem, an IntegrityError may be raised rather
    than finding the existing row. This is an accepted v1 trade-off — document for
    operators if reported (future phase).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from trezarr.bible.models import (
    BibleEvent,
    Series,
    Character,
    TermDictionary,
    AddressMap,
    RelationshipEvent,
)
from trezarr.bible.dto import (
    BibleEventDTO,
    SeriesDTO,
    SeriesBibleDTO,
    CharacterDTO,
    TermDTO,
    AddressMapDTO,
    RelationshipEventDTO,
)
from trezarr.bible.merge import get_locked_fields, compute_field_changes

logger = logging.getLogger(__name__)

# 32 KB cap on arr_metadata_snapshot before INSERT — DoS hardening per RESEARCH §Security Domain.
# Size is measured using json.dumps(..., ensure_ascii=False).encode('utf-8') so Vietnamese
# characters (3 bytes/char in UTF-8) measure as their actual UTF-8 byte length rather than
# as \\uXXXX escape sequences (6 ASCII chars). Cross-AI review MEDIUM finding.
MAX_ARR_METADATA_BYTES = 32 * 1024  # 32 KB


async def get_or_create_series(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    arr_kind: str,
    arr_instance: str = "default",
    arr_series_id: int,
    arr_metadata_snapshot: dict[str, Any],
    tvdb_id: int | None = None,
    tmdb_id: int | None = None,
) -> SeriesDTO:
    """Get the existing series row or create it lazily on first translate (D-36).

    Looks up the series by the UNIQUE identity (arr_kind, arr_instance, arr_series_id).
    If no row exists, creates one with the provided arr_metadata_snapshot and returns
    the resulting DTO. Idempotent: a second call with the same triple returns the
    existing row without modification.

    The SELECT + INSERT runs inside a SINGLE session.begin() block to prevent the
    race condition where two concurrent first-translates of the same series both INSERT
    (RESEARCH Pitfall 9 / Phase 7 preview).

    Args:
        session_factory:       Async session factory from build_session_factory().
        arr_kind:              "sonarr" or "radarr" (D-33).
        arr_instance:          Instance name, default "default" (D-33 v2 hook).
        arr_series_id:         Integer series ID from pyarr (D-33).
        arr_metadata_snapshot: Dict of discovery payload fields to snapshot (D-35).
                               Must fit within MAX_ARR_METADATA_BYTES (UTF-8 encoded).
        tvdb_id:               TVDB ID captured at creation (D-33, denormalized, nullable).
        tmdb_id:               TMDB ID captured at creation (D-33, denormalized, nullable).

    Returns:
        SeriesDTO for the found or newly-created series row.

    Raises:
        ValueError: If arr_metadata_snapshot exceeds MAX_ARR_METADATA_BYTES when
                    JSON-serialized with ensure_ascii=False (T-04-05 DoS hardening).
    """
    # Validate arr_metadata_snapshot size BEFORE opening a session (fail-fast).
    # ensure_ascii=False is required so Vietnamese text (3 bytes/char in UTF-8) measures
    # as its actual UTF-8 byte length, not as \\uXXXX escape sequences (6 bytes each).
    metadata_bytes = len(json.dumps(arr_metadata_snapshot, ensure_ascii=False).encode("utf-8"))
    if metadata_bytes > MAX_ARR_METADATA_BYTES:
        raise ValueError(
            f"arr_metadata snapshot exceeds {MAX_ARR_METADATA_BYTES} bytes "
            f"(measured {metadata_bytes} UTF-8 bytes with ensure_ascii=False)"
        )

    async with session_factory() as session:
        async with session.begin():
            # SELECT inside the transaction — single txn for SELECT+INSERT (D-32, Pitfall 9)
            stmt = select(Series).where(
                Series.arr_kind == arr_kind,
                Series.arr_instance == arr_instance,
                Series.arr_series_id == arr_series_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()

            if row is None:
                row = Series(
                    arr_kind=arr_kind,
                    arr_instance=arr_instance,
                    arr_series_id=arr_series_id,
                    tvdb_id=tvdb_id,
                    tmdb_id=tmdb_id,
                    arr_metadata=arr_metadata_snapshot,
                    register=None,  # D-35: Phase 5 sets via merge_inferred
                    locked_fields=[],
                )
                session.add(row)
                await session.flush()  # populate row.id before the txn commits
                logger.info(
                    "Created series row: %s/%s/%s (id=%d)",
                    arr_kind,
                    arr_instance,
                    arr_series_id,
                    row.id,
                )

        # session.begin() context exit → auto-commit
        # Return DTO after the transaction commits. expire_on_commit=False on the
        # session_factory means row attributes are still accessible post-commit (Pitfall 2).
        return SeriesDTO.model_validate(row, from_attributes=True)


async def load_series_bible(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: int,
) -> SeriesBibleDTO:
    """Load the full Series Bible for the given series_id as a SeriesBibleDTO (D-39).

    Eagerly loads characters and terms via selectinload so the returned DTO contains
    fully-populated lists without requiring additional queries after the session closes.

    Args:
        session_factory: Async session factory from build_session_factory().
        series_id:       Surrogate PK of the target series row.

    Returns:
        SeriesBibleDTO with register (None until Phase 5 sets it), arr_metadata
        snapshot, and populated characters/terms lists.

    Raises:
        sqlalchemy.exc.NoResultFound: If no series row with the given id exists.
                                      Caller's responsibility to handle.
    """
    async with session_factory() as session:
        stmt = (
            select(Series)
            .where(Series.id == series_id)
            .options(
                selectinload(Series.characters),
                selectinload(Series.terms),
                selectinload(Series.address_maps),
                selectinload(Series.relationship_events),  # [Phase 6 NEW]
            )
        )
        row = (await session.execute(stmt)).scalar_one()

        # CR-02: SeriesBibleDTO.register_value carries alias="register"; pass
        # the SQLA row attribute (still named `register` on the model) under
        # the Python field name so populate_by_name=True can resolve it without
        # going through the alias.
        return SeriesBibleDTO(
            id=row.id,
            arr_kind=row.arr_kind,
            arr_instance=row.arr_instance,
            arr_series_id=row.arr_series_id,
            register_value=row.register,
            arr_metadata=row.arr_metadata if row.arr_metadata is not None else {},
            locked_fields=row.locked_fields if row.locked_fields is not None else [],
            characters=[
                CharacterDTO.model_validate(c, from_attributes=True) for c in row.characters
            ],
            terms=[TermDTO.model_validate(t, from_attributes=True) for t in row.terms],
            address_map=[
                AddressMapDTO.model_validate(a, from_attributes=True) for a in row.address_maps
            ],
            relationship_events=[
                RelationshipEventDTO.model_validate(e, from_attributes=True)
                for e in row.relationship_events
            ],
        )


# ---------------------------------------------------------------------------
# Phase 04-03: character/term merge engine constants (D-32, D-34)
# ---------------------------------------------------------------------------

# Valid source enum values for bible_event.source (D-32)
VALID_SOURCES: frozenset[str] = frozenset({"inference", "lock", "import", "system"})

# Per-entity-type whitelist of fields that may be merged (MEDIUM cross-AI finding).
# Identity columns (original_latin_name, source_term, arr_*) are explicitly NOT
# mergeable — they define the row and cannot be changed via inference.
MERGEABLE_FIELDS: dict[str, frozenset[str]] = {
    "character": frozenset({"gender", "rough_age", "role"}),
    "term_dictionary": frozenset({"vietnamese_rendering", "category"}),
    "series": frozenset({"register"}),
    "address_map": frozenset({"self_term", "address_term", "valid_from_episode"}),
}


def _validate_mergeable_fields(entity_type: str, inferred: dict[str, Any]) -> None:
    """Raise ValueError if any key in ``inferred`` is outside MERGEABLE_FIELDS[entity_type].

    WR-02: single source of truth for the per-entity-type whitelist check.
    Previously the same byte-for-byte block lived in both ``merge_inferred``
    (pre-session fail-fast) and ``_merge_inferred_in_session`` (defence in
    depth — _upsert_*_in_session bypasses the public ``merge_inferred``
    fail-fast); the two could silently drift on rule changes. Both call sites
    now delegate here.

    Args:
        entity_type: Key into MERGEABLE_FIELDS — "character" | "term_dictionary" | "series".
        inferred:    Dict of {field: new_value} to validate against the whitelist.

    Raises:
        ValueError: If any key in ``inferred`` is not in MERGEABLE_FIELDS[entity_type].
    """
    allowed = MERGEABLE_FIELDS[entity_type]
    unknown = set(inferred) - allowed
    if unknown:
        raise ValueError(
            f"Field(s) {unknown} are not mergeable for entity type '{entity_type}'. "
            f"Mergeable fields: {allowed}"
        )


# ---------------------------------------------------------------------------
# Private session-scoped helpers (NEVER open a transaction — run inside one)
# ---------------------------------------------------------------------------


async def _merge_inferred_in_session(
    session: AsyncSession,
    row: Any,
    entity_type: str,
    dto_cls: Any,
    inferred: dict[str, Any],
    episode_key: str | None,
    source: str,
) -> tuple[Any, list[BibleEvent]]:
    """Apply inferred changes to `row` inside an ALREADY-OPEN transaction.

    This helper MUST be called from inside an `async with session.begin():` block.
    It does NOT open a transaction itself (HIGH finding: no nested txn).

    HIGH finding fix (WR-01 clarification): the stale-DTO defence is that
    locked_fields and field values are read off the SQLA row inside the open
    transaction — never off the caller's external DTO. The caller's DTO may
    have been built in a prior session and could carry pre-write state; the
    SQLA row's current attribute values are what this session has actually
    materialised. Note: ``session.get(type(row), row.id)`` inside the SAME
    session returns the identical Python object via SQLAlchemy's identity map,
    so it is not a "fresh re-read" in the sense of bypassing in-memory cache —
    it's just the canonical handle for the row this session is operating on.
    The real guarantee is that *we never go through the caller's DTO*; we read
    locked + old_value off the SQLA row (whose attribute values reflect this
    session's view of the row). If a TRUE post-commit re-read is needed (e.g.
    to defeat the identity map after a concurrent commit), use
    ``session.get(..., populate_existing=True)`` or ``session.refresh(row)``.

    Steps:
      1. Validate inferred fields against MERGEABLE_FIELDS whitelist.
      2. Resolve the canonical SQLA row handle inside the session.
      3. Read locked and compute changes off the SQLA row (not the caller's DTO).
      4. For each genuine change: setattr on the row + construct BibleEvent.
      5. session.add(evt) for each event.
      6. Return (fresh_row_or_snapshot, events_list).

    Args:
        session:     Open AsyncSession (transaction must already be active).
        row:         The SQLA model row (used for type(row) to look up via id).
        entity_type: "character" | "term_dictionary" | "series".
        dto_cls:     The Pydantic DTO class for model_validate.
        inferred:    Dict of {field: new_value} to attempt to merge.
        episode_key: Optional episode identifier for the bible_event row.
        source:      Provenance string (one of VALID_SOURCES).

    Returns:
        (fresh_row, list_of_BibleEvent_instances) — the SQLA row with any
        changes applied, and the BibleEvent instances added to the session.
        If no changes are needed, returns (fresh_snapshot_dto, []).

    Raises:
        ValueError: If any key in `inferred` is not in MERGEABLE_FIELDS[entity_type].
    """
    # Validate inferred fields against the whitelist (MEDIUM finding).
    # WR-02: delegated to the module-level _validate_mergeable_fields helper —
    # single source of truth shared with merge_inferred's pre-session check.
    _validate_mergeable_fields(entity_type, inferred)

    # WR-01: this is the canonical SQLA row handle for this transaction. Inside
    # the same AsyncSession, session.get(...) returns the SAME Python object
    # via SQLAlchemy's identity map — it does NOT bypass any cache. The
    # important property is that we then read locked + old_value OFF THIS ROW
    # (not off the caller's DTO), so the audit entry reflects the in-session
    # pre-write state rather than whatever stale snapshot the caller's DTO
    # captured. ``populate_existing=True`` would be the right knob if we ever
    # needed to defeat the identity map after a concurrent commit on a
    # separate session.
    fresh_row = await session.get(type(row), row.id)

    # CR-02: compute_field_changes runs against the SQLA row itself, not a
    # Pydantic DTO snapshot. The SQLA model's Python attribute names match
    # the SQLA column names 1:1 (e.g. ``Series.register``), so the inferred
    # dict's keys (``{"register": ...}``) resolve under getattr without going
    # through Pydantic's alias machinery — which is necessary because the
    # DTO field for ``register`` is now ``register_value`` with
    # ``alias="register"`` (CR-02 shadowing fix). Using the SQLA row keeps
    # the merge contract stable and avoids the parent BaseModel.register
    # method being silently returned by ``getattr(dto, "register", None)``.
    locked = get_locked_fields(fresh_row)
    changes = compute_field_changes(fresh_row, inferred, locked)

    if not changes:
        # No-op: return a fresh DTO snapshot built from the SQLA row.
        fresh_snapshot = dto_cls.model_validate(fresh_row, from_attributes=True)
        return fresh_snapshot, []

    # BibleEvent.series_id is the FK to the series. A Character/term_dictionary/
    # address_map row carries that FK as `.series_id`, but a Series row IS the
    # series — its PK is `.id` and it has no `.series_id` attribute. Resolving
    # the wrong one made a series-level merge (register / source_lang / model
    # overrides) raise 'Series' object has no attribute 'series_id' AFTER the
    # setattr below, rolling back the whole transaction so the register never
    # persisted (v1.0 live finding, 260604-gza).
    event_series_id = fresh_row.id if entity_type == "series" else fresh_row.series_id

    # Apply changes and construct BibleEvent rows
    events: list[BibleEvent] = []
    for field, old_val, new_val in changes:
        setattr(fresh_row, field, new_val)
        evt = BibleEvent(
            series_id=event_series_id,
            episode_key=episode_key,
            entity_type=entity_type,
            entity_id=fresh_row.id,
            field=field,
            old_value=old_val,
            new_value=new_val,
            source=source,
        )
        session.add(evt)
        events.append(evt)

    return fresh_row, events


async def _upsert_character_in_session(
    session: AsyncSession,
    *,
    series_id: int,
    original_latin_name: str,
    gender: str | None,
    rough_age: str | None,
    role: str | None,
    episode_key: str | None,
    source: str,
) -> tuple[Character, list[BibleEvent]]:
    """INSERT or merge-update a Character row INSIDE an already-open transaction.

    This helper MUST be called from inside an `async with session.begin():` block.
    It does NOT open a transaction (HIGH finding: no nested txn).

    For a NEW row: constructs Character, adds to session, flushes to get id, then
    emits one BibleEvent per non-None field with old_value=None (MEDIUM finding).

    For an EXISTING row: builds inferred dict from non-None provided fields, then
    delegates to _merge_inferred_in_session to apply changes and emit events.
    NOTE: always passes ALL non-None fields to _merge_inferred_in_session, even if
    the caller passed None for a field (None fields are excluded from the inferred dict).

    Args:
        session:             Open AsyncSession with active transaction.
        series_id:           FK to the parent Series row.
        original_latin_name: Character identity key (not mergeable).
        gender:              Optional — merged if not None.
        rough_age:           Optional — merged if not None.
        role:                Optional — merged if not None.
        episode_key:         Optional episode key for bible_event provenance.
        source:              Provenance string (one of VALID_SOURCES).

    Returns:
        (Character_row, list_of_BibleEvent_instances)
    """
    # SELECT existing row by identity key (case- and whitespace-insensitive, CR-01)
    stmt = select(Character).where(
        Character.series_id == series_id,
        func.lower(Character.original_latin_name) == original_latin_name.strip().lower(),
    )
    existing_row = (await session.execute(stmt)).scalar_one_or_none()

    if existing_row is None:
        # First insert: construct the row and emit one event per non-None field.
        # WR-05: locked_fields is intentionally hard-coded to [] here — Phase 4
        # never sets locks in production (only tests, via direct row mutation).
        # See upsert_character docstring for the lock-list constraint contract.
        # Display-case is preserved on INSERT — only the SELECT identity comparison is normalized.
        row = Character(
            series_id=series_id,
            original_latin_name=original_latin_name,
            gender=gender,
            rough_age=rough_age,
            role=role,
            locked_fields=[],
        )
        session.add(row)
        await session.flush()  # populate row.id before constructing events

        events: list[BibleEvent] = []
        for field, val in [("gender", gender), ("rough_age", rough_age), ("role", role)]:
            if val is not None:
                evt = BibleEvent(
                    series_id=series_id,
                    episode_key=episode_key,
                    entity_type="character",
                    entity_id=row.id,
                    field=field,
                    old_value=None,
                    new_value=val,
                    source=source,
                )
                session.add(evt)
                events.append(evt)
        return row, events

    # Existing row: build inferred dict of non-None provided fields
    inferred = {
        k: v
        for k, v in [("gender", gender), ("rough_age", rough_age), ("role", role)]
        if v is not None
    }
    if not inferred:
        return existing_row, []

    # Delegate to _merge_inferred_in_session (which re-reads the row for fresh state)
    result, events = await _merge_inferred_in_session(
        session, existing_row, "character", CharacterDTO, inferred, episode_key, source
    )
    # result may be a fresh snapshot (DTO) if no changes, or the SQLA row if changed.
    # We need to return the SQLA row for consistent downstream handling.
    if isinstance(result, Character):
        return result, events
    # No-op path: result is a DTO (fresh_snapshot). Return existing_row unchanged.
    return existing_row, events


async def _upsert_term_in_session(
    session: AsyncSession,
    *,
    series_id: int,
    source_term: str,
    vietnamese_rendering: str | None,
    category: str | None,
    episode_key: str | None,
    source: str,
) -> tuple[TermDictionary, list[BibleEvent]]:
    """INSERT or merge-update a TermDictionary row INSIDE an already-open transaction.

    Mirror of _upsert_character_in_session for TermDictionary.
    This helper MUST be called from inside an `async with session.begin():` block.

    For a NEW row: constructs TermDictionary, flushes, emits one event per non-None field.
    For an EXISTING row: applies the carry-forward guard for ``vietnamese_rendering`` (see
    below), then delegates to _merge_inferred_in_session for any remaining fields.

    Note on TermDictionary first insert: vietnamese_rendering is required (NOT NULL in DB).
    Callers must provide a non-None vietnamese_rendering for inserts.

    Carry-forward policy (260612-7kt / D-02 — prior > inference for unlocked renderings):
    If the existing row has a NON-EMPTY ``vietnamese_rendering`` AND the field is NOT in
    ``locked_fields``, a new inference rendering is suppressed rather than applied.  This
    prevents re-inference churn (MK run: 20/53 rows churned in one night; Khonshu→Khonsu
    contradicting a locked row).  The suppressed inference is recorded as a BibleEvent so
    the audit trail is preserved.  The ladder is:
      locked > prior (non-empty unlocked) > inference
    This guard lives here (not in compute_field_changes / _merge_inferred_in_session) to
    keep the policy change localized to the term entity — mirroring how the scy/ru6
    address-map carry-forward was implemented in _upsert_address_pair_in_session.

    API PATCH path (apply_human_edit_term) is NOT routed through this function (D-80).
    It writes directly via session.get(TermDictionary, term_id) + setattr — completely
    bypassing the inference carry-forward guard.  Human edits are always authoritative.

    Args:
        session:               Open AsyncSession with active transaction.
        series_id:             FK to the parent Series row.
        source_term:           Identity key (not mergeable).
        vietnamese_rendering:  Optional — merged if not None (required for insert).
        category:              Optional — merged if not None.
        episode_key:           Optional episode key for bible_event provenance.
        source:                Provenance string (one of VALID_SOURCES).

    Returns:
        (TermDictionary_row, list_of_BibleEvent_instances)
    """
    # SELECT existing row by identity key
    stmt = select(TermDictionary).where(
        TermDictionary.series_id == series_id,
        TermDictionary.source_term == source_term,
    )
    existing_row = (await session.execute(stmt)).scalar_one_or_none()

    if existing_row is None:
        # First insert: vietnamese_rendering is required for TermDictionary (NOT NULL).
        # WR-05: locked_fields is intentionally hard-coded to [] here — Phase 4
        # never sets locks in production (only tests, via direct row mutation).
        # See upsert_term docstring for the lock-list constraint contract.
        row = TermDictionary(
            series_id=series_id,
            source_term=source_term,
            vietnamese_rendering=vietnamese_rendering or "",
            category=category,
            locked_fields=[],
        )
        session.add(row)
        await session.flush()  # populate row.id before constructing events

        events: list[BibleEvent] = []
        for field, val in [
            ("vietnamese_rendering", vietnamese_rendering),
            ("category", category),
        ]:
            if val is not None:
                evt = BibleEvent(
                    series_id=series_id,
                    episode_key=episode_key,
                    entity_type="term_dictionary",
                    entity_id=row.id,
                    field=field,
                    old_value=None,
                    new_value=val,
                    source=source,
                )
                session.add(evt)
                events.append(evt)
        return row, events

    # Existing row: carry-forward guard for vietnamese_rendering (prior > inference).
    # Must run BEFORE building the inferred dict so the suppressed field is excluded
    # from the _merge_inferred_in_session call.
    suppressed_events: list[BibleEvent] = []
    rendering_suppressed = False

    if vietnamese_rendering is not None:
        prior_rendering = existing_row.vietnamese_rendering or ""
        locked_fields = existing_row.locked_fields or []
        if prior_rendering and "vietnamese_rendering" not in locked_fields:
            # Prior non-empty unlocked rendering exists — suppress the new inference.
            # Emit a provenance event so the suppressed inference is auditable.
            evt = BibleEvent(
                series_id=series_id,
                episode_key=episode_key,
                entity_type="term_dictionary",
                entity_id=existing_row.id,
                field="vietnamese_rendering",
                old_value=prior_rendering,  # the prior rendering that was kept
                new_value=vietnamese_rendering,  # the inference that was suppressed
                source=source,
            )
            session.add(evt)
            suppressed_events.append(evt)
            rendering_suppressed = True
            # Fall through: build inferred WITHOUT vietnamese_rendering

    # Build inferred dict of non-None provided fields, excluding suppressed rendering
    inferred = {
        k: v
        for k, v in [
            ("vietnamese_rendering", None if rendering_suppressed else vietnamese_rendering),
            ("category", category),
        ]
        if v is not None
    }
    if not inferred:
        return existing_row, suppressed_events

    # Delegate remaining fields to _merge_inferred_in_session
    result, merge_events = await _merge_inferred_in_session(
        session, existing_row, "term_dictionary", TermDTO, inferred, episode_key, source
    )
    all_events = suppressed_events + merge_events
    if isinstance(result, TermDictionary):
        return result, all_events
    # No-op path: result is a DTO. Return existing_row unchanged.
    return existing_row, all_events


async def _upsert_address_pair_in_session(
    session: AsyncSession,
    *,
    series_id: int,
    speaker_character_id: int,
    addressee_character_id: int,
    self_term: str | None,
    address_term: str | None,
    valid_from_episode: str | None,
    episode_key: str | None,
    source: str,
) -> tuple[AddressMap, list[BibleEvent]]:
    """INSERT or merge-update an AddressMap row INSIDE an already-open transaction.

    This helper MUST be called from inside an `async with session.begin():` block.
    It does NOT open a transaction (HIGH finding: no nested txn).

    Identity key: (series_id, speaker_character_id, addressee_character_id) — one
    row per directed ordered pair.

    CRITICAL: do NOT delegate to _merge_inferred_in_session for AddressMap — its
    isinstance chain does not handle AddressMapDTO (Pitfall G / PATTERNS.md).
    This is a self-contained helper that mirrors _upsert_character_in_session.

    Lock precedence (D-34): for each mergeable field, if the field name appears
    in the row's locked_fields list, the existing value is preserved. The incoming
    value is only written if the field is NOT locked.

    Args:
        session:               Open AsyncSession with active transaction.
        series_id:             FK to the parent Series row.
        speaker_character_id:  FK → character.id (the one speaking).
        addressee_character_id: FK → character.id (the one being addressed).
        self_term:             Optional Vietnamese self-reference term.
        address_term:          Optional Vietnamese address term for addressee.
        valid_from_episode:    Optional episode key from which mapping applies.
        episode_key:           Optional episode key for bible_event provenance.
        source:                Provenance string (one of VALID_SOURCES).

    Returns:
        (AddressMap_row, list_of_BibleEvent_instances)
    """
    # SELECT existing row by identity key
    stmt = select(AddressMap).where(
        AddressMap.series_id == series_id,
        AddressMap.speaker_character_id == speaker_character_id,
        AddressMap.addressee_character_id == addressee_character_id,
    )
    existing_row = (await session.execute(stmt)).scalar_one_or_none()

    mergeable_fields = [
        ("self_term", self_term),
        ("address_term", address_term),
        ("valid_from_episode", valid_from_episode),
    ]

    if existing_row is None:
        # First insert: construct the row and emit one event per non-None field.
        # WR-05: locked_fields is intentionally hard-coded to [] here — same constraint
        # as _upsert_character_in_session. Locks can only be set via the Phase 8
        # lock-management UI path, not via this function.
        row = AddressMap(
            series_id=series_id,
            speaker_character_id=speaker_character_id,
            addressee_character_id=addressee_character_id,
            self_term=self_term,
            address_term=address_term,
            valid_from_episode=valid_from_episode,
            locked_fields=[],
        )
        session.add(row)
        await session.flush()  # populate row.id before constructing events

        events: list[BibleEvent] = []
        for field, val in mergeable_fields:
            if val is not None:
                evt = BibleEvent(
                    series_id=series_id,
                    episode_key=episode_key,
                    entity_type="address_map",
                    entity_id=row.id,
                    field=field,
                    old_value=None,
                    new_value=val,
                    source=source,
                )
                session.add(evt)
                events.append(evt)
        return row, events

    # Existing row: apply non-None incoming fields, respecting locked_fields (D-34).
    # Read locked_fields off the SQLA row (never off caller's DTO — WR-01 / HIGH finding).
    locked = set(existing_row.locked_fields or [])
    events = []
    for field, new_val in mergeable_fields:
        if new_val is None:
            continue  # None means "no update for this field"
        if field in locked:
            continue  # D-34: human lock > inference — skip locked fields
        old_val = getattr(existing_row, field)
        if old_val == new_val:
            continue  # no-op: same value, no event
        setattr(existing_row, field, new_val)
        evt = BibleEvent(
            series_id=series_id,
            episode_key=episode_key,
            entity_type="address_map",
            entity_id=existing_row.id,
            field=field,
            old_value=old_val,
            new_value=new_val,
            source=source,
        )
        session.add(evt)
        events.append(evt)

    return existing_row, events


# ---------------------------------------------------------------------------
# Public API — read functions
# ---------------------------------------------------------------------------


async def get_character(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: int,
    original_latin_name: str,
) -> CharacterDTO | None:
    """Look up a Character by series + name, returning a DTO or None if not found.

    Args:
        session_factory:       Async session factory.
        series_id:             FK to the parent Series row.
        original_latin_name:   Identity key (case- and whitespace-insensitive match;
                               display-case preserved in DB).

    Returns:
        CharacterDTO if found, None if no such character exists for this series.
    """
    async with session_factory() as session:
        stmt = select(Character).where(
            Character.series_id == series_id,
            func.lower(Character.original_latin_name) == original_latin_name.strip().lower(),
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        return CharacterDTO.model_validate(row, from_attributes=True) if row else None


async def get_term(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: int,
    source_term: str,
) -> TermDTO | None:
    """Look up a TermDictionary by series + source_term, returning a DTO or None.

    Args:
        session_factory: Async session factory.
        series_id:       FK to the parent Series row.
        source_term:     Identity key (exact match, case-sensitive).

    Returns:
        TermDTO if found, None if no such term exists for this series.
    """
    async with session_factory() as session:
        stmt = select(TermDictionary).where(
            TermDictionary.series_id == series_id,
            TermDictionary.source_term == source_term,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        return TermDTO.model_validate(row, from_attributes=True) if row else None


# ---------------------------------------------------------------------------
# Public API — write functions (the ONLY transaction owners)
# ---------------------------------------------------------------------------


async def upsert_character(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    original_latin_name: str,
    gender: str | None = None,
    rough_age: str | None = None,
    role: str | None = None,
    episode_key: str | None = None,
    source: str = "inference",
) -> tuple[CharacterDTO, list[BibleEventDTO]]:
    """INSERT or merge-update a Character row — the single public transaction owner.

    Creates the Character row if it does not exist (emitting a BibleEvent per non-None
    field with old_value=None). If the row already exists, applies any non-None field
    values as inferred changes (respecting locked_fields and no-op detection via
    _merge_inferred_in_session).

    This function NEVER calls public merge_inferred() — it delegates to the private
    _upsert_character_in_session which calls _merge_inferred_in_session internally.
    This avoids nested transactions (HIGH finding).

    WR-05 (lock-list constraint): on first INSERT, locked_fields is
    hard-coded to ``[]`` by ``_upsert_character_in_session``; there is NO
    parameter to seed a caller-supplied lock list on creation. This is
    intentional for Phase 4 (per merge.py:3-4, Phase 4 never sets
    locked_fields in production — only tests). If Phase 8's UI needs to
    pre-seed a row with a locked field set, it must use the Phase 8 lock-
    management API (writes to ``Character.locked_fields`` directly via the
    UI write path), NOT this function. Adding a ``locked_fields=...``
    parameter here without also wiring the merge engine to respect a
    just-created lock during the same call would be a footgun.

    Args:
        session_factory:       Async session factory.
        series_id:             FK to the parent Series row.
        original_latin_name:   Identity key.
        gender:                Optional field to merge if not None.
        rough_age:             Optional field to merge if not None.
        role:                  Optional field to merge if not None.
        episode_key:           Optional episode key for bible_event provenance.
        source:                Provenance string, default "inference".

    Returns:
        (CharacterDTO, list[BibleEventDTO]) — the current state DTO and emitted events.
    """
    async with session_factory() as session:
        async with session.begin():
            row, events = await _upsert_character_in_session(
                session,
                series_id=series_id,
                original_latin_name=original_latin_name,
                gender=gender,
                rough_age=rough_age,
                role=role,
                episode_key=episode_key,
                source=source,
            )
        # Transaction committed; expire_on_commit=False ensures attributes are accessible
        return (
            CharacterDTO.model_validate(row, from_attributes=True),
            [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
        )


async def upsert_term(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    source_term: str,
    vietnamese_rendering: str | None = None,
    category: str | None = None,
    episode_key: str | None = None,
    source: str = "inference",
) -> tuple[TermDTO, list[BibleEventDTO]]:
    """INSERT or merge-update a TermDictionary row — the single public transaction owner.

    Mirror of upsert_character for TermDictionary. Delegates to
    _upsert_term_in_session which calls _merge_inferred_in_session internally.

    WR-05 (lock-list constraint): same as upsert_character — on first INSERT,
    locked_fields is hard-coded to ``[]`` by ``_upsert_term_in_session``.
    There is NO parameter to seed a caller-supplied lock list on creation.
    Phase 8 lock-management is the authoritative path for setting locks.

    Args:
        session_factory:       Async session factory.
        series_id:             FK to the parent Series row.
        source_term:           Identity key.
        vietnamese_rendering:  Optional field to merge (required on first INSERT).
        category:              Optional field to merge if not None.
        episode_key:           Optional episode key for bible_event provenance.
        source:                Provenance string, default "inference".

    Returns:
        (TermDTO, list[BibleEventDTO]) — the current state DTO and emitted events.
    """
    async with session_factory() as session:
        async with session.begin():
            row, events = await _upsert_term_in_session(
                session,
                series_id=series_id,
                source_term=source_term,
                vietnamese_rendering=vietnamese_rendering,
                category=category,
                episode_key=episode_key,
                source=source,
            )
        return (
            TermDTO.model_validate(row, from_attributes=True),
            [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
        )


async def upsert_address_pair(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    speaker_character_id: int,
    addressee_character_id: int,
    self_term: str | None = None,
    address_term: str | None = None,
    valid_from_episode: str | None = None,
    episode_key: str | None = None,
    source: str = "inference",
) -> tuple[AddressMapDTO, list[BibleEventDTO]]:
    """INSERT or merge-update an AddressMap row — the single public transaction owner for address pairs.

    Creates the AddressMap row if it does not exist for the directed
    (speaker_character_id, addressee_character_id) pair within the series.
    If the row already exists, applies any non-None field values respecting
    locked_fields (D-34: human lock > inference).

    CRITICAL: This function NEVER routes AddressMap writes through merge_inferred()
    — merge_inferred's isinstance chain does not handle AddressMapDTO (Pitfall G).
    Delegates to the private _upsert_address_pair_in_session helper.

    WR-05 (lock-list constraint): on first INSERT, locked_fields is
    hard-coded to ``[]`` by ``_upsert_address_pair_in_session``; there is NO
    parameter to seed a caller-supplied lock list on creation. Phase 8
    lock-management is the authoritative path for setting locks.

    Args:
        session_factory:       Async session factory.
        series_id:             FK to the parent Series row.
        speaker_character_id:  FK → character.id (the one speaking).
        addressee_character_id: FK → character.id (the one being addressed).
        self_term:             Optional Vietnamese self-reference term to merge.
        address_term:          Optional Vietnamese address term to merge.
        valid_from_episode:    Optional episode key from which mapping applies.
        episode_key:           Optional episode key for bible_event provenance.
        source:                Provenance string, default "inference".

    Returns:
        (AddressMapDTO, list[BibleEventDTO]) — current state DTO and emitted events.
    """
    async with session_factory() as session:
        async with session.begin():
            row, events = await _upsert_address_pair_in_session(
                session,
                series_id=series_id,
                speaker_character_id=speaker_character_id,
                addressee_character_id=addressee_character_id,
                self_term=self_term,
                address_term=address_term,
                valid_from_episode=valid_from_episode,
                episode_key=episode_key,
                source=source,
            )
        # Transaction committed; expire_on_commit=False ensures attributes are accessible
        return (
            AddressMapDTO.model_validate(row, from_attributes=True),
            [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
        )


# ---------------------------------------------------------------------------
# Phase 08: Human-edit write path — apply_human_edit_* + delete_* + history (D-79/D-80/D-82/D-83)
# ---------------------------------------------------------------------------


async def apply_human_edit_character(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    character_id: int,
    series_id: int,
    field: str,
    new_value: Any,
    lock: bool = False,
) -> tuple[CharacterDTO, BibleEventDTO]:
    """Apply a human edit (and optional lock) to a Character field (D-80).

    Validates field against MERGEABLE_FIELDS["character"] before opening any session
    (T-08-01 defence). Inside one session.begin() transaction: re-reads the row
    (WR-01), sets the new value, reassigns locked_fields as a new list (D-80 JSON
    dirty-tracking footgun guard), emits BibleEvent(source="lock") in the same txn
    (D-32). Returns DTOs — SQLAlchemy models never escape this function (D-39).

    Args:
        session_factory: Async session factory.
        character_id:    PK of the Character row to edit.
        series_id:       Series the character belongs to (cross-series guard).
        field:           Field name to modify (must be in MERGEABLE_FIELDS["character"]).
        new_value:       New value to set.
        lock:            If True, add field to locked_fields (human override flag).

    Returns:
        (CharacterDTO, BibleEventDTO) for the updated row and the audit event.

    Raises:
        ValueError: If field is not in MERGEABLE_FIELDS["character"].
        ValueError: If character_id not found or series_id mismatch.
    """
    # Pre-session validation — field whitelist security defence (T-08-01)
    allowed = MERGEABLE_FIELDS.get("character", frozenset())
    if field not in allowed:
        raise ValueError(
            f"Field '{field}' is not editable for character. Editable fields: {allowed}"
        )

    async with session_factory() as session:
        async with session.begin():
            # WR-01: re-read INSIDE the transaction off the SQLA row
            row = await session.get(Character, character_id)
            if row is None or row.series_id != series_id:
                raise ValueError(
                    f"Character {character_id} not found in series {series_id}"
                )

            old_value = getattr(row, field)
            setattr(row, field, new_value)

            # D-80: reassign NEW list — never .append() on plain JSON column
            locked_list = list(row.locked_fields or [])
            if lock and field not in locked_list:
                locked_list.append(field)
                row.locked_fields = locked_list  # reassignment = dirty-tracked
            elif not lock and field in locked_list:
                locked_list.remove(field)
                row.locked_fields = locked_list

            # D-32: audit event in the same transaction
            # WR-01: use source="lock" only when actually locking; otherwise use "import"
            # as the closest VALID_SOURCES value for a human edit without a lock operation.
            evt = BibleEvent(
                series_id=series_id,
                episode_key=None,
                entity_type="character",
                entity_id=character_id,
                field=field,
                old_value=old_value,
                new_value=new_value,
                source="lock" if lock else "import",
            )
            session.add(evt)

        # expire_on_commit=False: attributes accessible post-commit (Pitfall 2)
        return (
            CharacterDTO.model_validate(row, from_attributes=True),
            BibleEventDTO.model_validate(evt, from_attributes=True),
        )


async def apply_human_edit_address_pair(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    address_map_id: int,
    series_id: int,
    self_term: str | None = None,
    address_term: str | None = None,
    lock: bool = False,
) -> tuple[AddressMapDTO, list[BibleEventDTO]]:
    """Apply a human edit (and optional lock) to an AddressMap pair (D-80).

    D-87 pre-check: if lock=True and either term is empty/whitespace, raises ValueError
    before opening any session (T-08-03 defence). Inside one session.begin() transaction:
    re-reads the row (WR-01), updates self_term/address_term, reassigns locked_fields as
    a new list (D-80), emits BibleEvents for each changed field (D-32). Returns DTOs
    (D-39). NEVER routes through merge_inferred (D-80).

    Args:
        session_factory:  Async session factory.
        address_map_id:   PK of the AddressMap row to edit.
        series_id:        Series the pair belongs to (cross-series guard).
        self_term:        New self_term value (Vietnamese self-reference).
        address_term:     New address_term value (Vietnamese address term).
        lock:             If True, lock both self_term and address_term (D-87: pair locks as a unit).

    Returns:
        (AddressMapDTO, list[BibleEventDTO]) for the updated row and audit events.

    Raises:
        ValueError: D-87 — if lock=True and either term is empty or whitespace.
        ValueError: If address_map_id not found or series_id mismatch.
    """
    # D-87 pre-check BEFORE opening session (T-08-03)
    if lock:
        if not self_term or not self_term.strip():
            raise ValueError("Both self_term and address_term must be non-empty before locking a pair")
        if not address_term or not address_term.strip():
            raise ValueError("Both self_term and address_term must be non-empty before locking a pair")

    async with session_factory() as session:
        async with session.begin():
            # WR-01: re-read INSIDE the transaction
            row = await session.get(AddressMap, address_map_id)
            if row is None or row.series_id != series_id:
                raise ValueError(
                    f"AddressMap {address_map_id} not found in series {series_id}"
                )

            events: list[BibleEvent] = []

            # Apply self_term change
            if self_term is not None:
                self_term = self_term.strip()
                old_self = row.self_term
                if old_self != self_term:
                    row.self_term = self_term
                    evt = BibleEvent(
                        series_id=series_id,
                        episode_key=None,
                        entity_type="address_map",
                        entity_id=address_map_id,
                        field="self_term",
                        old_value=old_self,
                        new_value=self_term,
                        # WR-01: use source="lock" only when actually locking
                        source="lock" if lock else "import",
                    )
                    session.add(evt)
                    events.append(evt)

            # Apply address_term change
            if address_term is not None:
                address_term = address_term.strip()
                old_addr = row.address_term
                if old_addr != address_term:
                    row.address_term = address_term
                    evt = BibleEvent(
                        series_id=series_id,
                        episode_key=None,
                        entity_type="address_map",
                        entity_id=address_map_id,
                        field="address_term",
                        old_value=old_addr,
                        new_value=address_term,
                        # WR-01: use source="lock" only when actually locking
                        source="lock" if lock else "import",
                    )
                    session.add(evt)
                    events.append(evt)

            # D-80: lock or unlock both fields as a pair (symmetric)
            if lock:
                locked_list = list(row.locked_fields or [])
                for f in ("self_term", "address_term"):
                    if f not in locked_list:
                        locked_list.append(f)
                row.locked_fields = locked_list  # reassignment = dirty-tracked
            elif not lock:
                # CR-03: explicit unlock — remove self_term and address_term from locked_fields
                locked_list = list(row.locked_fields or [])
                for f in ("self_term", "address_term"):
                    if f in locked_list:
                        locked_list.remove(f)
                row.locked_fields = locked_list  # reassignment = dirty-tracked

        # expire_on_commit=False: attributes accessible post-commit (Pitfall 2)
        return (
            AddressMapDTO.model_validate(row, from_attributes=True),
            [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
        )


async def apply_human_edit_term(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    source_term: str | None = None,
    term_id: int | None = None,
    field: str,
    new_value: Any,
    lock: bool = False,
) -> tuple[TermDTO, BibleEventDTO]:
    """Apply a human edit (and optional lock) to a TermDictionary field (D-80).

    Looks up the term by term_id (PK, preferred — used by the PATCH route) or by
    source_term (fallback — used for the new-row creation path, e.g. from tests).
    At least one of term_id or source_term must be provided.
    Validates field against MERGEABLE_FIELDS["term_dictionary"] before opening any session
    (T-08-01 defence). Inside one session.begin() transaction: re-reads the row (WR-01),
    sets the new value, reassigns locked_fields as a new list (D-80), emits BibleEvent
    (D-32). NEVER routes through merge_inferred (D-80). Returns DTOs (D-39).

    Args:
        session_factory: Async session factory.
        series_id:       Series the term belongs to.
        term_id:         PK of the TermDictionary row (authoritative — used by PATCH route).
        source_term:     Source-language identity key for the term (used for new-row creation).
        field:           Field to modify (must be in MERGEABLE_FIELDS["term_dictionary"]).
        new_value:       New value to set.
        lock:            If True, add field to locked_fields.

    Returns:
        (TermDTO, BibleEventDTO) for the updated/created row and the audit event.

    Raises:
        ValueError: If field is not in MERGEABLE_FIELDS["term_dictionary"].
        ValueError: If neither term_id nor source_term is provided.
        ValueError: If term_id is given but the row is not found or belongs to a different series.
    """
    if term_id is None and source_term is None:
        raise ValueError("Either term_id or source_term must be provided")

    # Pre-session validation — field whitelist security defence (T-08-01)
    allowed = MERGEABLE_FIELDS.get("term_dictionary", frozenset())
    if field not in allowed:
        raise ValueError(
            f"Field '{field}' is not editable for term_dictionary. Editable fields: {allowed}"
        )

    async with session_factory() as session:
        async with session.begin():
            if term_id is not None:
                # CR-02: look up by PK (authoritative when called from the PATCH route)
                row = await session.get(TermDictionary, term_id)
                if row is None or row.series_id != series_id:
                    raise ValueError(
                        f"TermDictionary {term_id} not found in series {series_id}"
                    )
                source_term = row.source_term  # ensure error messages are informative
            else:
                # Fallback: look up by source_term identity key (creation path)
                stmt = select(TermDictionary).where(
                    TermDictionary.series_id == series_id,
                    TermDictionary.source_term == source_term,
                )
                row = (await session.execute(stmt)).scalar_one_or_none()

            if row is None:
                # Create the term row (require vietnamese_rendering for INSERT)
                if field == "vietnamese_rendering":
                    vr = str(new_value)
                else:
                    raise ValueError(
                        f"Term '{source_term}' not found in series {series_id}. "
                        f"Cannot create without vietnamese_rendering (field={field!r})."
                    )
                row = TermDictionary(
                    series_id=series_id,
                    source_term=source_term,
                    vietnamese_rendering=vr,
                    locked_fields=[],
                )
                session.add(row)
                await session.flush()  # populate row.id
                old_value = None
                new_value = vr  # normalize so the audit event matches what was stored
            else:
                old_value = getattr(row, field)
                setattr(row, field, new_value)

            # D-80: reassign NEW list — never .append() on plain JSON column
            locked_list = list(row.locked_fields or [])
            if lock and field not in locked_list:
                locked_list.append(field)
                row.locked_fields = locked_list  # reassignment = dirty-tracked
            elif not lock and field in locked_list:
                locked_list.remove(field)
                row.locked_fields = locked_list

            # D-32: audit event in the same transaction
            # WR-01: use source="lock" only when actually locking; otherwise use "import"
            # as the closest VALID_SOURCES value for a human edit without a lock operation.
            evt = BibleEvent(
                series_id=series_id,
                episode_key=None,
                entity_type="term_dictionary",
                entity_id=row.id,
                field=field,
                old_value=old_value,
                new_value=new_value,
                source="lock" if lock else "import",
            )
            session.add(evt)

        # expire_on_commit=False: attributes accessible post-commit (Pitfall 2)
        return (
            TermDTO.model_validate(row, from_attributes=True),
            BibleEventDTO.model_validate(evt, from_attributes=True),
        )


async def apply_human_edit_series(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    field: str,
    new_value: Any,
    lock: bool = False,
) -> tuple[SeriesDTO, BibleEventDTO]:
    """Apply a human edit (and optional lock) to a Series field (D-80).

    Primary use case: field="register" (CR-02: the ORM attribute is Series.register;
    the DTO serializes it with alias "register" per CR-02). Validates field against
    MERGEABLE_FIELDS["series"] before opening any session (T-08-01 defence). Inside one
    session.begin() transaction: re-reads the row (WR-01), sets the new value, reassigns
    locked_fields as a new list (D-80), emits BibleEvent (D-32). NEVER routes through
    merge_inferred (D-80). Returns DTOs (D-39).

    Args:
        session_factory: Async session factory.
        series_id:       PK of the Series row to edit.
        field:           Field to modify (must be in MERGEABLE_FIELDS["series"]).
        new_value:       New value to set.
        lock:            If True, add field to locked_fields.

    Returns:
        (SeriesDTO, BibleEventDTO) for the updated row and the audit event.

    Raises:
        ValueError: If field is not in MERGEABLE_FIELDS["series"].
        ValueError: If series_id not found.
    """
    # Pre-session validation — field whitelist security defence (T-08-01)
    allowed = MERGEABLE_FIELDS.get("series", frozenset())
    if field not in allowed:
        raise ValueError(
            f"Field '{field}' is not editable for series. Editable fields: {allowed}"
        )

    async with session_factory() as session:
        async with session.begin():
            # WR-01: re-read INSIDE the transaction off the SQLA row
            row = await session.get(Series, series_id)
            if row is None:
                raise ValueError(f"Series {series_id} not found")

            old_value = getattr(row, field)
            setattr(row, field, new_value)

            # D-80: reassign NEW list — never .append() on plain JSON column
            locked_list = list(row.locked_fields or [])
            if lock and field not in locked_list:
                locked_list.append(field)
                row.locked_fields = locked_list  # reassignment = dirty-tracked
            elif not lock and field in locked_list:
                locked_list.remove(field)
                row.locked_fields = locked_list

            # D-32: audit event in the same transaction
            # WR-01: use source="lock" only when actually locking; otherwise use "import"
            # as the closest VALID_SOURCES value for a human edit without a lock operation.
            evt = BibleEvent(
                series_id=series_id,
                episode_key=None,
                entity_type="series",
                entity_id=series_id,
                field=field,
                old_value=old_value,
                new_value=new_value,
                source="lock" if lock else "import",
            )
            session.add(evt)

        # expire_on_commit=False: attributes accessible post-commit (Pitfall 2)
        return (
            SeriesDTO.model_validate(row, from_attributes=True),
            BibleEventDTO.model_validate(evt, from_attributes=True),
        )


async def delete_address_pair(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    address_map_id: int,
    series_id: int,
) -> dict[str, int]:
    """Delete an AddressMap row (D-83).

    One session.begin() transaction. Guards that the row belongs to series_id
    (T-08-05 cross-series delete defence). No BibleEvent emitted (delete is not
    a lock operation). No SQLAlchemy model escapes this function (D-39).

    Args:
        session_factory:  Async session factory.
        address_map_id:   PK of the AddressMap row to delete.
        series_id:        Series the pair must belong to (guard).

    Returns:
        {"deleted": address_map_id}

    Raises:
        ValueError: If row not found or series_id mismatch.
    """
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(AddressMap, address_map_id)
            if row is None or row.series_id != series_id:
                raise ValueError(
                    f"AddressMap {address_map_id} not found in series {series_id}"
                )
            session.delete(row)
    return {"deleted": address_map_id}


async def delete_term(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    term_id: int,
    series_id: int,
) -> dict[str, int]:
    """Delete a TermDictionary row (D-83).

    One session.begin() transaction. Guards that the row belongs to series_id
    (T-08-05 cross-series delete defence). No BibleEvent emitted (delete is not
    a lock operation). No SQLAlchemy model escapes this function (D-39).

    Args:
        session_factory: Async session factory.
        term_id:         PK of the TermDictionary row to delete.
        series_id:       Series the term must belong to (guard).

    Returns:
        {"deleted": term_id}

    Raises:
        ValueError: If row not found or series_id mismatch.
    """
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(TermDictionary, term_id)
            if row is None or row.series_id != series_id:
                raise ValueError(
                    f"TermDictionary {term_id} not found in series {series_id}"
                )
            session.delete(row)
    return {"deleted": term_id}


async def dedup_canonical_name_terms(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
) -> list[BibleEventDTO]:
    """Repair: collapse competing locked name-term rows to a single canonical rendering (R3, D-04).

    The kfn (key-for-name) auto-lock in merge_bible_analysis Step 3.5 can produce dual locked
    rows for the same character entity: e.g. 'Steven Grant' → 'Steven Grant' (Latin, locked)
    and '史蒂文·格兰特' → 'Sử Địch Văn · Cách Lan Đặc' (CJK, locked). The translate-prompt
    glossary injects both rows, producing split renderings in output subtitles (260611-l74 R3).

    D-04 rule: canonical = the FIRST-LOCKED row (lowest id / earliest established), regardless
    of script (FIX2, 260611-ru6 R2 — bible-consistency-auditor + vietnamese-linguist combined
    finding). The prior "LATIN-form is canonical" heuristic was removed because it false-merges
    DIFFERENT characters in xianxia/CJK-heavy series where multiple CJK-named characters each
    have their own locked CJK row and a single unrelated Latin-named character produces one
    Latin row — making the heuristic rewrite every unrelated CJK row to the Latin character's
    rendering (catastrophic identity collapse).

    Character linkage requirement: a rewrite may ONLY happen when two rows are provably the
    same character. Without a character_id FK on TermDictionary (current schema), this function
    cannot establish linkage and therefore performs NO rewrites. It returns an empty list and
    logs a diagnostic. The primary defence is plan_character_name_terms (FIX2-III guard), which
    prevents the dual-row split from being created in the first place.

    Future path: once a character_id FK is added to TermDictionary (via Alembic migration),
    this function can group rows by character_id and elect the lowest-id locked row as
    canonical — performing the repair with guaranteed-correct character identity.

    Idempotent: returns an empty list on every call until FK linkage is available.
    Series-scoped: only touches locked TermDictionary rows for the given series_id (T-ru6-04).

    Args:
        session_factory: Async session factory.
        series_id:       Series to repair.

    Returns:
        list[BibleEventDTO] — one entry per row rewritten. Empty list = nothing to repair.
    """

    def _is_latin_only(text: str) -> bool:
        """Return True if text contains no CJK or other non-Latin-extended codepoints."""
        # CJK Unified Ideographs: U+4E00–U+9FFF (most common CJK block)
        # Extended CJK blocks: U+3400–U+4DBF (CJK Extension A), U+20000+ (Ext B/C/D via surrogates)
        # Katakana/Hiragana: U+3040–U+30FF
        # Arabic, Hebrew, Thai, etc.: U+0600–U+06FF, U+0590–U+05FF, U+0E00–U+0E7F
        # Conservative approach: any codepoint >= U+0250 that is not Latin Extended or
        # IPA Extensions is treated as non-Latin for this guard.
        # We use a simple CJK-range check sufficient for the name-term dedup use case:
        return not any(
            0x3040 <= ord(c) <= 0x9FFF or 0x3400 <= ord(c) <= 0x4DBF
            for c in text
        )

    async with session_factory() as session:
        # Load all locked name-term rows for this series in one read transaction.
        stmt = select(TermDictionary).where(
            TermDictionary.series_id == series_id,
        )
        all_rows: list[TermDictionary] = list((await session.execute(stmt)).scalars().all())

    # Filter to rows that have vietnamese_rendering locked.
    locked_rows = [
        r for r in all_rows
        if "vietnamese_rendering" in (r.locked_fields or [])
    ]

    if not locked_rows:
        return []

    # FIX2 (260611-ru6): character linkage required before any rewrite.
    #
    # The prior "canonical = the single Latin-form row" heuristic is REMOVED. That heuristic
    # false-merged DIFFERENT characters in xianxia series: a single unrelated Latin-named
    # character produced canonical_rows == [that Latin row], and then ALL CJK-named characters'
    # locked rows (韩立/Hàn Lập, 南宫婉/Nam Cung Uyển, …) were rewritten to that Latin
    # character's rendering — catastrophic identity collapse (bible-consistency-auditor HIGH,
    # vietnamese-linguist HIGH, combined finding 260611-ru6 FIX2).
    #
    # Safe rule: rewrite ONLY when two rows are provably the SAME character entity.
    # TermDictionary has NO character_id FK (current schema, confirmed models.py:134-159).
    # Without a FK, we cannot establish cross-row character identity.
    # → Return immediately with no events. Log a diagnostic for monitoring.
    #
    # Future path (TODO): add a character_id FK to TermDictionary via Alembic migration,
    # then group rows by character_id and elect the lowest-id locked row as canonical —
    # performing the repair with guaranteed-correct character identity and register-agnostic
    # first-locked-wins semantics (D-04).
    #
    # Primary defence until then: plan_character_name_terms FIX2-III guard prevents the
    # dual-row split from being created in the first place (analyze.py:180+).
    #
    # FIX3 atomicity (260611-ru6 LOW): the prior N-writes-in-N-separate-sessions design was
    # non-atomic (crash mid-loop → partial repair). FIX2 removes the write loop entirely, so
    # FIX3 is moot for now. When the FK migration enables writes, the implementation MUST
    # use a single async with session.begin() wrapping all row rewrites and BibleEvent inserts
    # to guarantee all-or-nothing repair (idempotency makes crash recovery safe but
    # a single transaction is the stronger guarantee).
    latin_rows = [r for r in locked_rows if _is_latin_only(r.source_term)]
    script_rows = [r for r in locked_rows if not _is_latin_only(r.source_term)]

    if not latin_rows or not script_rows:
        # No mixed Latin/CJK situation — nothing to consider.
        return []

    logger.info(
        "dedup_canonical_name_terms: series %d has %d Latin-locked and %d CJK-locked rows. "
        "No character_id FK on TermDictionary — cannot safely establish per-row character "
        "linkage. Skipping rewrite to prevent false-merge across different characters. "
        "Add a character_id FK (Alembic migration) to enable safe dedup.",
        series_id,
        len(latin_rows),
        len(script_rows),
    )
    return []


async def load_field_history(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: int,
    entity_type: str,
    entity_id: int,
    field: str | None = None,
    limit: int = 100,
) -> list[BibleEventDTO]:
    """Load BibleEvent history for a specific entity (D-82, T-08-02).

    Read-only query — no session.begin() needed. Filtered by series_id, entity_type,
    entity_id, and optionally field. Ordered by created_at DESC, limited to `limit`
    rows (default 100 — T-08-02 DoS hardening).

    Args:
        session_factory: Async session factory.
        series_id:       FK → series.id (scope guard).
        entity_type:     Entity type string: "character"|"term_dictionary"|"series"|"address_map".
        entity_id:       ID of the specific entity row.
        field:           Optional field name filter.
        limit:           Maximum number of events to return (default 100).

    Returns:
        list[BibleEventDTO] ordered by created_at DESC.
    """
    async with session_factory() as session:
        stmt = select(BibleEvent).where(
            BibleEvent.series_id == series_id,
            BibleEvent.entity_type == entity_type,
            BibleEvent.entity_id == entity_id,
        )
        if field is not None:
            stmt = stmt.where(BibleEvent.field == field)
        stmt = stmt.order_by(BibleEvent.created_at.desc()).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [BibleEventDTO.model_validate(r, from_attributes=True) for r in rows]


async def load_all_series(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[SeriesDTO]:
    """Load all Series rows ordered by id (D-39).

    Read-only query. Returns SeriesDTO (not SeriesBibleDTO — no eager-loading
    needed for the list view). Uses SeriesDTO.model_validate with from_attributes=True
    (CR-02: register_value alias handled by populate_by_name=True in SeriesDTO).

    Args:
        session_factory: Async session factory.

    Returns:
        list[SeriesDTO] ordered by Series.id.
    """
    async with session_factory() as session:
        stmt = select(Series).order_by(Series.id)
        rows = (await session.execute(stmt)).scalars().all()
        return [SeriesDTO.model_validate(r, from_attributes=True) for r in rows]


async def get_series_by_arr_id(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    arr_kind: str,
    arr_series_id: int,
    arr_instance: str = "default",
) -> "SeriesDTO | None":
    """Return SeriesDTO for (arr_kind, arr_instance, arr_series_id), or None if not found.

    Read-only query — does NOT create. Used by process_one_item (D-112) to fetch
    per-series overrides before translate_file so resolve_effective_settings can
    apply source_lang_override and model_override.

    Args:
        session_factory: Async session factory.
        arr_kind:        "sonarr" or "radarr".
        arr_series_id:   Integer series ID from pyarr.
        arr_instance:    Instance name (default "default").

    Returns:
        SeriesDTO if found; None if this series has not been registered in the Bible yet.
    """
    async with session_factory() as session:
        stmt = (
            select(Series)
            .where(
                Series.arr_kind == arr_kind,
                Series.arr_instance == arr_instance,
                Series.arr_series_id == arr_series_id,
            )
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return SeriesDTO.model_validate(row, from_attributes=True)


async def record_relationship_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    character_a_id: int,
    character_b_id: int,
    episode_marker: str,
    description: str | None = None,
) -> RelationshipEventDTO:
    """INSERT a relationship_event row (no-op if dedup key already exists).

    Dedup key: (series_id, character_a_id, character_b_id, episode_marker).
    INSERT-only — no merge/update path (relationship_event has no locked_fields).
    The SELECT+INSERT runs inside a SINGLE session.begin() block (D-32, Pitfall 9).

    Args:
        session_factory:   Async session factory.
        series_id:         FK → series.id.
        character_a_id:    FK → character.id (first party in the relationship).
        character_b_id:    FK → character.id (second party in the relationship).
        episode_marker:    Episode key where the transition occurs (e.g. "S01E04").
        description:       Optional narrative description of the transition.

    Returns:
        RelationshipEventDTO for the found or newly-created row.
    """
    async with session_factory() as session:
        async with session.begin():
            # Dedup check: SELECT before INSERT (D-32, Pitfall 9 — single txn)
            stmt = select(RelationshipEvent).where(
                RelationshipEvent.series_id == series_id,
                RelationshipEvent.character_a_id == character_a_id,
                RelationshipEvent.character_b_id == character_b_id,
                RelationshipEvent.episode_marker == episode_marker,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                return RelationshipEventDTO.model_validate(existing, from_attributes=True)

            row = RelationshipEvent(
                series_id=series_id,
                character_a_id=character_a_id,
                character_b_id=character_b_id,
                episode_marker=episode_marker,
                description=description,
            )
            session.add(row)
            await session.flush()  # populate row.id before txn commits (Pitfall 7)
        # expire_on_commit=False — attributes accessible post-commit (Pitfall 2)
        return RelationshipEventDTO.model_validate(row, from_attributes=True)


async def load_address_map(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: int,
) -> list[AddressMapDTO]:
    """Load all AddressMap rows for the given series_id (D-39).

    Args:
        session_factory: Async session factory from build_session_factory().
        series_id:       Surrogate PK of the target series row.

    Returns:
        List of AddressMapDTOs for the series (empty list if none exist yet).
    """
    async with session_factory() as session:
        stmt = select(AddressMap).where(AddressMap.series_id == series_id)
        rows = (await session.execute(stmt)).scalars().all()
        return [AddressMapDTO.model_validate(r, from_attributes=True) for r in rows]


async def merge_inferred(
    session_factory: async_sessionmaker[AsyncSession],
    entity_dto: Any,
    inferred: dict[str, Any],
    episode_key: str | None,
    source: str,
) -> tuple[Any, list[BibleEventDTO]]:
    """Apply inferred field values to a Bible entity, atomically writing an audit trail.

    The CENTERPIECE of the consistency engine substrate. Enforces:
      - source enum validation (VALID_SOURCES) before any DB access.
      - MERGEABLE_FIELDS whitelist per entity type (MEDIUM finding) — identity
        columns like original_latin_name and source_term are explicitly rejected.
      - Delegates to _merge_inferred_in_session which re-reads the DB row INSIDE
        the transaction (HIGH finding fix — correct old_value audit entries).
      - current-row UPDATE + bible_event INSERT(s) inside ONE session.begin() (D-32).
      - Returns (updated_dto, list[BibleEventDTO]) — D-39 DTO boundary.

    Supported entity types (via isinstance check on entity_dto):
      - CharacterDTO → entity_type="character", MERGEABLE_FIELDS["character"]
      - TermDTO      → entity_type="term_dictionary", MERGEABLE_FIELDS["term_dictionary"]
      - SeriesDTO    → entity_type="series", MERGEABLE_FIELDS["series"]

    Args:
        session_factory: Async session factory.
        entity_dto:      Pydantic DTO of the entity to merge into. Used ONLY to
                         determine entity type and row id — actual state is re-read
                         from the DB inside the transaction (HIGH finding).
        inferred:        Dict of {field: new_value} to attempt to apply.
        episode_key:     Optional episode key for bible_event provenance.
        source:          Provenance string; must be one of VALID_SOURCES.

    Returns:
        (updated_entity_dto, list[BibleEventDTO]) where updated_entity_dto reflects
        the current row state after the merge (may be unchanged if all changes were
        locked or no-op), and events is the list of emitted BibleEventDTO instances.

    Raises:
        ValueError: If source is not in VALID_SOURCES (checked BEFORE any DB access).
        ValueError: If any inferred field is not in MERGEABLE_FIELDS[entity_type].
        TypeError:  If entity_dto is not a CharacterDTO, TermDTO, or SeriesDTO.
    """
    # Validate source enum BEFORE opening any session (fail-fast, T-04-11)
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")

    # Determine model class, entity_type string, and DTO class by isinstance check
    if isinstance(entity_dto, CharacterDTO):
        model_cls = Character
        entity_type = "character"
        dto_cls = CharacterDTO
    elif isinstance(entity_dto, TermDTO):
        model_cls = TermDictionary
        entity_type = "term_dictionary"
        dto_cls = TermDTO
    elif isinstance(entity_dto, SeriesDTO):
        model_cls = Series
        entity_type = "series"
        dto_cls = SeriesDTO
    else:
        raise TypeError(
            f"Unsupported entity_dto type: {type(entity_dto).__name__}. "
            f"Expected CharacterDTO, TermDTO, or SeriesDTO."
        )

    # Validate inferred fields against the whitelist BEFORE opening any session (T-04-10).
    # WR-02: same helper backs _merge_inferred_in_session's defence-in-depth
    # check inside the transaction, so the two cannot silently drift.
    _validate_mergeable_fields(entity_type, inferred)

    async with session_factory() as session:
        async with session.begin():
            # Fetch the row (to pass to _merge_inferred_in_session which will re-read it)
            row = await session.get(model_cls, entity_dto.id)
            if row is None:
                raise ValueError(f"No {entity_type} row found with id={entity_dto.id}")

            # Delegate to the private helper (runs inside the current transaction)
            result, raw_events = await _merge_inferred_in_session(
                session, row, entity_type, dto_cls, inferred, episode_key, source
            )
        # Transaction committed

        # result is either a fresh DTO (no-op path) or the SQLA row (changed path)
        if isinstance(result, dto_cls):
            # No-op path: _merge_inferred_in_session returned a fresh DTO snapshot
            updated_dto = result
        else:
            # Changed path: result is the updated SQLA row
            updated_dto = dto_cls.model_validate(result, from_attributes=True)

        return (
            updated_dto,
            [BibleEventDTO.model_validate(e, from_attributes=True) for e in raw_events],
        )


async def set_series_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    source_lang_override: list[str] | None,  # None = clear override (inherit global)
    model_override: str | None,              # None = clear override (inherit global)
) -> SeriesDTO:
    """Set per-series source-lang and model overrides (D-111, SVC-05).

    NULL = inherit global config. Empty list [] treated as NULL (cleared).
    Emits BibleEvent for audit (D-32). No MERGEABLE_FIELDS check needed —
    these columns are NOT in the merge_inferred pathway; they are override-only.

    Args:
        session_factory:       Async session factory.
        series_id:             PK of the Series row to update.
        source_lang_override:  Ordered list of ISO-639-1 codes, or None to clear.
                               Empty list [] is treated as None (cleared).
        model_override:        LLM model identifier, or None to clear.

    Returns:
        SeriesDTO for the updated row (D-39: returns DTO, not ORM row).

    Raises:
        ValueError: If series_id not found.
    """
    async with session_factory() as session:
        async with session.begin():
            # WR-01: re-read INSIDE the transaction off the SQLA row
            row = await session.get(Series, series_id)
            if row is None:
                raise ValueError(f"Series {series_id} not found")

            # WR-04: capture the prior override values off the live in-txn row
            # BEFORE reassigning, so the audit trail records what actually changed
            # (D-32 audit-trail completeness — old_value must not be hardcoded None).
            old_src = row.source_lang_override
            old_mdl = row.model_override

            # Normalize: empty list [] treated as NULL (cleared override)
            src_override = source_lang_override if source_lang_override else None
            mdl_override = model_override or None

            row.source_lang_override = src_override
            row.model_override = mdl_override

            # D-32: audit event in the same transaction
            evt = BibleEvent(
                series_id=series_id,
                episode_key=None,
                entity_type="series",
                entity_id=series_id,
                field="overrides",
                old_value={
                    "source_lang_override": old_src,
                    "model_override": old_mdl,
                },
                new_value={
                    "source_lang_override": src_override,
                    "model_override": mdl_override,
                },
                source="import",  # human edit via UI
            )
            session.add(evt)

        # expire_on_commit=False: attributes accessible post-commit (Pitfall 2)
        return SeriesDTO.model_validate(row, from_attributes=True)
