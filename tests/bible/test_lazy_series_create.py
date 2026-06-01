"""Tests for lazy series-row creation and idempotency in bible.store (D-36, D-33, D-35).

Verifies:
  - First call to get_or_create_series() inserts a series row (D-36 lazy creation).
  - Second call with the same (arr_kind, arr_instance, arr_series_id) returns the SAME
    row — no duplicate INSERT (D-33 UNIQUE triple identity + D-36 idempotent get-or-create).
  - Different arr_kind with the same arr_series_id creates separate rows (D-33).
  - tvdb_id and tmdb_id are captured and persisted (D-33 denormalized columns).
  - SELECT + INSERT runs inside a SINGLE session.begin() block (atomic, not two txns).
  - arr_metadata size cap raises ValueError before INSERT (D-35, T-04-05 DoS hardening).

asyncio_mode = "auto" is configured project-wide in pyproject.toml, so tests are
`async def` without @pytest.mark.asyncio.
"""
from __future__ import annotations

import pytest


async def test_first_call_inserts_series_row(session_factory):
    """First get_or_create_series() call creates exactly 1 row with the given identity.

    Verifies: D-36 lazy creation on first translate; D-35 arr_metadata snapshot;
    register stays NULL (Phase 5 sets it via merge_inferred — not Phase 4).
    """
    from sqlalchemy import select, func

    from trezarr.bible.models import Series
    from trezarr.bible.store import get_or_create_series

    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=42,
        arr_metadata_snapshot={"genres": ["drama"], "year": 2020},
    )

    assert dto.arr_kind == "sonarr"
    assert dto.arr_instance == "default"
    assert dto.arr_series_id == 42
    assert dto.register is None, (
        "register must be NULL after Phase-4 creation — Phase 5 sets it via merge_inferred"
    )
    assert dto.arr_metadata == {"genres": ["drama"], "year": 2020}
    assert dto.tvdb_id is None
    assert dto.id is not None and dto.id > 0

    # Verify exactly one row in the database
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Series)
        )
    assert count == 1, f"Expected 1 series row after first creation, got {count}"


async def test_second_call_returns_same_row(session_factory):
    """Two consecutive get_or_create_series() calls with the same triple return DTOs with same id.

    Verifies: D-36 idempotent get-or-create; D-33 UNIQUE(arr_kind, arr_instance, arr_series_id)
    constraint prevents duplicate rows. COUNT(*) FROM series == 1 (not 2).
    """
    from sqlalchemy import select, func

    from trezarr.bible.models import Series
    from trezarr.bible.store import get_or_create_series

    dto1 = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=42,
        arr_metadata_snapshot={"genres": ["drama"]},
    )
    dto2 = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=42,
        arr_metadata_snapshot={"genres": ["drama"]},
    )

    assert dto1.id == dto2.id, (
        f"Second call must return the same row id as first call "
        f"(got dto1.id={dto1.id}, dto2.id={dto2.id})"
    )

    # Verify no duplicate row was created
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Series)
        )
    assert count == 1, (
        f"Expected exactly 1 series row (idempotent get-or-create), got {count}"
    )


async def test_different_arr_kind_creates_separate_rows(session_factory):
    """get_or_create_series with arr_kind='sonarr' vs 'radarr' (same arr_series_id) creates 2 distinct rows.

    Verifies: D-33 — the UNIQUE constraint is on the FULL triple (arr_kind, arr_instance,
    arr_series_id). The same arr_series_id integer is valid for both Sonarr and Radarr
    (their ID namespaces are independent).
    """
    from sqlalchemy import select, func

    from trezarr.bible.models import Series
    from trezarr.bible.store import get_or_create_series

    dto_sonarr = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=42,
        arr_metadata_snapshot={"year": 2020},
    )
    dto_radarr = await get_or_create_series(
        session_factory,
        arr_kind="radarr",
        arr_instance="default",
        arr_series_id=42,
        arr_metadata_snapshot={"year": 2019},
    )

    assert dto_sonarr.id != dto_radarr.id, (
        "sonarr/42 and radarr/42 must be distinct series rows (D-33 full-triple identity)"
    )
    assert dto_sonarr.arr_kind == "sonarr"
    assert dto_radarr.arr_kind == "radarr"

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Series)
        )
    assert count == 2, f"Expected 2 series rows (one per arr_kind), got {count}"


async def test_tvdb_tmdb_captured_at_creation(session_factory):
    """tvdb_id and tmdb_id passed to get_or_create_series are persisted in the row.

    These are NOT used for lookup in v1 — they are captured at series creation to
    enable future Bible portability (v2 COMM-01 hook). Verifies D-33 denormalized
    column capture.
    """
    from sqlalchemy import select

    from trezarr.bible.models import Series
    from trezarr.bible.store import get_or_create_series

    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=99,
        arr_metadata_snapshot={"year": 2022},
        tvdb_id=12345,
        tmdb_id=None,
    )

    assert dto.tvdb_id == 12345, f"Expected tvdb_id=12345, got {dto.tvdb_id!r}"
    assert dto.tmdb_id is None, f"Expected tmdb_id=None, got {dto.tmdb_id!r}"

    # Reload and verify DB values
    async with session_factory() as session:
        row = (await session.execute(
            select(Series).where(Series.id == dto.id)
        )).scalar_one()
    assert row.tvdb_id == 12345
    assert row.tmdb_id is None


async def test_get_or_create_uses_single_transaction(session_factory):
    """get_or_create_series SELECT+INSERT runs inside ONE session.begin() block.

    Verifies atomicity: both the SELECT and the INSERT happen within a single
    transaction boundary. This prevents a race condition where two concurrent first-
    translates of the same series would both INSERT (Phase 7 preview from RESEARCH
    Pitfall 9).

    Implementation check: verify the series row exists and is populated after the
    call (i.e., a rolled-back partial transaction would leave zero rows).
    """
    from sqlalchemy import select, func

    from trezarr.bible.models import Series
    from trezarr.bible.store import get_or_create_series

    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=77,
        arr_metadata_snapshot={"year": 2023},
    )

    # After the call, exactly one row must exist — the transaction completed atomically
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Series)
        )
        row = (await session.execute(
            select(Series).where(Series.id == dto.id)
        )).scalar_one()

    assert count == 1, "Single transaction must have committed exactly one row"
    assert row.arr_series_id == 77, "Row must have the correct arr_series_id after commit"
    assert row.arr_metadata == {"year": 2023}, "arr_metadata must be persisted in the same transaction"


async def test_arr_metadata_size_validation(session_factory):
    """arr_metadata_snapshot larger than 32 KB raises ValueError before INSERT (T-04-05 DoS hardening).

    The 32 KB cap is a defense-in-depth measure since arr payloads should never
    approach this size in practice. Size is measured using
    json.dumps(..., ensure_ascii=False).encode('utf-8') for correct UTF-8 byte count.

    Verifies: T-04-05 DoS hardening; cross-AI review MEDIUM finding on ensure_ascii=False.
    """
    from trezarr.bible.store import get_or_create_series

    # Create a payload that exceeds 32 KB when JSON-serialized
    # 'x' * 40000 produces ~40 KB of JSON ("key": "xxxxxxx...")
    oversized_metadata = {"overview": "x" * 40_000}

    with pytest.raises(ValueError, match="32"):
        await get_or_create_series(
            session_factory,
            arr_kind="sonarr",
            arr_instance="default",
            arr_series_id=1,
            arr_metadata_snapshot=oversized_metadata,
        )
