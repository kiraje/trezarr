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
  D-34  human lock > prior > new inference. _merge_inferred_in_session re-reads the
        DB row INSIDE the transaction to get the freshest locked_fields and old_value
        state — never relies on the caller's potentially-stale DTO (HIGH finding fix).
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
  HIGH   _merge_inferred_in_session re-reads the row inside the transaction. This
         guarantees old_value in bible_event reflects actual pre-write DB state even
         if a concurrent update changed the row after the caller loaded their DTO.
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

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from trezarr.bible.models import BibleEvent, Series, Character, TermDictionary
from trezarr.bible.dto import BibleEventDTO, SeriesDTO, SeriesBibleDTO, CharacterDTO, TermDTO
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
                    register=None,   # D-35: Phase 5 sets via merge_inferred
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
            )
        )
        row = (await session.execute(stmt)).scalar_one()

        return SeriesBibleDTO(
            id=row.id,
            arr_kind=row.arr_kind,
            arr_instance=row.arr_instance,
            arr_series_id=row.arr_series_id,
            register=row.register,
            arr_metadata=row.arr_metadata if row.arr_metadata is not None else {},
            locked_fields=row.locked_fields if row.locked_fields is not None else [],
            characters=[
                CharacterDTO.model_validate(c, from_attributes=True)
                for c in row.characters
            ],
            terms=[
                TermDTO.model_validate(t, from_attributes=True)
                for t in row.terms
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
}


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

    HIGH finding fix: re-reads the row from the DB inside the open session to get
    the freshest locked_fields and field values. This guarantees old_value in the
    bible_event reflects actual pre-write DB state — never the caller's stale DTO.

    Steps:
      1. Validate inferred fields against MERGEABLE_FIELDS whitelist.
      2. Re-read the row from the DB inside the session (fresh state).
      3. Build a fresh DTO snapshot from the re-read row.
      4. Derive locked and changes from the fresh snapshot.
      5. For each genuine change: setattr on the row + construct BibleEvent.
      6. session.add(evt) for each event.
      7. Return (fresh_row_or_snapshot, events_list).

    Args:
        session:     Open AsyncSession (transaction must already be active).
        row:         The SQLA model row (used for type(row) to re-read from DB).
        entity_type: "character" | "term_dictionary" | "series".
        dto_cls:     The Pydantic DTO class for model_validate.
        inferred:    Dict of {field: new_value} to attempt to merge.
        episode_key: Optional episode identifier for the bible_event row.
        source:      Provenance string (one of VALID_SOURCES).

    Returns:
        (fresh_row, list_of_BibleEvent_instances) — the fresh SQLA row with
        any changes applied, and the BibleEvent instances added to the session.
        If no changes are needed, returns (fresh_snapshot_dto, []).

    Raises:
        ValueError: If any key in `inferred` is not in MERGEABLE_FIELDS[entity_type].
    """
    # Validate inferred fields against the whitelist (MEDIUM finding)
    allowed = MERGEABLE_FIELDS[entity_type]
    unknown = set(inferred) - allowed
    if unknown:
        raise ValueError(
            f"Field(s) {unknown} are not mergeable for entity type '{entity_type}'. "
            f"Mergeable fields: {allowed}"
        )

    # Re-read the row from the DB INSIDE the already-open session.
    # This is the critical HIGH finding fix: derive locked AND changes from the FRESH
    # row state, never from the caller's potentially-stale DTO.
    fresh_row = await session.get(type(row), row.id)

    # Build a fresh snapshot DTO from the re-read row for compute_field_changes
    fresh_snapshot = dto_cls.model_validate(fresh_row, from_attributes=True)

    # Derive locked fields and compute changes from the FRESH snapshot
    locked = get_locked_fields(fresh_snapshot)
    changes = compute_field_changes(fresh_snapshot, inferred, locked)

    if not changes:
        # No-op: return the fresh snapshot with an empty events list
        return fresh_snapshot, []

    # Apply changes and construct BibleEvent rows
    events: list[BibleEvent] = []
    for field, old_val, new_val in changes:
        setattr(fresh_row, field, new_val)
        evt = BibleEvent(
            series_id=fresh_row.series_id,
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
    # SELECT existing row by identity key
    stmt = select(Character).where(
        Character.series_id == series_id,
        Character.original_latin_name == original_latin_name,
    )
    existing_row = (await session.execute(stmt)).scalar_one_or_none()

    if existing_row is None:
        # First insert: construct the row and emit one event per non-None field
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
        k: v for k, v in [("gender", gender), ("rough_age", rough_age), ("role", role)]
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
    For an EXISTING row: delegates to _merge_inferred_in_session.

    Note on TermDictionary first insert: vietnamese_rendering is required (NOT NULL in DB).
    Callers must provide a non-None vietnamese_rendering for inserts.

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
        # First insert: vietnamese_rendering is required for TermDictionary (NOT NULL)
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

    # Existing row: build inferred dict of non-None provided fields
    inferred = {
        k: v for k, v in [
            ("vietnamese_rendering", vietnamese_rendering),
            ("category", category),
        ]
        if v is not None
    }
    if not inferred:
        return existing_row, []

    # Delegate to _merge_inferred_in_session
    result, events = await _merge_inferred_in_session(
        session, existing_row, "term_dictionary", TermDTO, inferred, episode_key, source
    )
    if isinstance(result, TermDictionary):
        return result, events
    # No-op path: result is a DTO. Return existing_row unchanged.
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
        original_latin_name:   Identity key (exact match, case-sensitive).

    Returns:
        CharacterDTO if found, None if no such character exists for this series.
    """
    async with session_factory() as session:
        stmt = select(Character).where(
            Character.series_id == series_id,
            Character.original_latin_name == original_latin_name,
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
        raise ValueError(
            f"source must be one of {VALID_SOURCES}, got {source!r}"
        )

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

    # Validate inferred fields against the whitelist BEFORE opening any session (T-04-10)
    allowed = MERGEABLE_FIELDS[entity_type]
    unknown = set(inferred) - allowed
    if unknown:
        raise ValueError(
            f"Field(s) {unknown} are not mergeable for entity type '{entity_type}'. "
            f"Mergeable fields: {allowed}"
        )

    async with session_factory() as session:
        async with session.begin():
            # Fetch the row (to pass to _merge_inferred_in_session which will re-read it)
            row = await session.get(model_cls, entity_dto.id)
            if row is None:
                raise ValueError(
                    f"No {entity_type} row found with id={entity_dto.id}"
                )

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
