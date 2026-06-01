"""Series Bible store — Pydantic-typed API hiding SQLAlchemy internals (D-39).

Public API (the ONLY surface Phase 5+ may import):
    load_series_bible(session_factory, series_id) -> SeriesBibleDTO
    get_or_create_series(session_factory, *, arr_kind, arr_instance, arr_series_id,
                         arr_metadata_snapshot, tvdb_id=None, tmdb_id=None) -> SeriesDTO

Internal:
    All SQLAlchemy imports stay inside this module. Sessions are opened with
    `async with session_factory()` and never escape.

Design decisions honoured:
  D-32  Atomic transactions: SELECT+INSERT inside a single session.begin() block.
  D-33  UNIQUE(arr_kind, arr_instance, arr_series_id) identity key; tvdb_id/tmdb_id
        denormalized at creation but NOT used for lookup in v1.
  D-35  arr_metadata is a JSON snapshot captured at series-row creation; register
        stays NULL (Phase 5 sets it via merge_inferred like any other Bible field).
  D-36  Lazy series-row creation on first translate — no startup enumeration.
  D-39  Pydantic DTOs at the store boundary; SQLAlchemy models never escape.
  Pitfall 2  expire_on_commit=False propagates from the session_factory (mandatory
             for async SQLAlchemy — accessing expired attributes post-commit deadlocks).
  Pitfall 7  Never `session.add(dto)` — always construct the SQLA model row, then
             convert to DTO via model_validate(row, from_attributes=True) after flush.

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

from trezarr.bible.models import Series, Character, TermDictionary
from trezarr.bible.dto import SeriesDTO, SeriesBibleDTO, CharacterDTO, TermDTO

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
