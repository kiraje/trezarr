"""Tests for Pydantic DTO boundary contract at trezarr.bible.store (D-39).

Verifies:
  - No SQLAlchemy imports are reachable through any public name in trezarr.bible.dto
    (import-graph contract test via inspect.getsource — not brittle dir() inspection).
  - SeriesDTO round-trips correctly from a SQLAlchemy row via model_validate(from_attributes=True).
  - BibleEventDTO.created_at is typed as datetime | None (not Any) — Pydantic v2 coerces
    ISO-8601 strings to datetime objects automatically.

References:
  D-39: Pydantic DTOs at the store boundary; SQLAlchemy stays inside store.py.
  Cross-AI review MEDIUM finding: BibleEventDTO.created_at must be datetime | None.
"""
from __future__ import annotations

import inspect

import pytest


def test_no_sqlalchemy_in_bible_dto_namespace():
    """No 'from sqlalchemy' or 'import sqlalchemy' lines appear in trezarr.bible.dto source.

    This is an import-graph contract test (D-39). We use inspect.getsource() to check the
    actual source text — this is more robust than inspecting dir() names, which can include
    re-exported symbols that don't reveal the actual import relationship.

    Verifies: D-39 — the DTO layer must not import SQLAlchemy so Phase 5 callers remain
    SQLAlchemy-free by importing only from trezarr.bible.dto and trezarr.bible.store.
    """
    import trezarr.bible.dto as dto_mod

    src = inspect.getsource(dto_mod)
    bad_lines = [
        line for line in src.splitlines()
        if line.strip().startswith(("from sqlalchemy", "import sqlalchemy"))
    ]
    assert not bad_lines, (
        f"trezarr.bible.dto leaks SQLAlchemy imports (D-39 violation):\n"
        + "\n".join(bad_lines)
    )


async def test_series_dto_round_trips_from_sqla_row(session_factory):
    """SeriesDTO.model_validate(row, from_attributes=True) produces a DTO with identical field values.

    Creates a Series row via the session_factory, loads it, and validates it into a
    SeriesDTO. The DTO must have model_config = ConfigDict(from_attributes=True).

    Verifies: D-39 ORM bridge pattern (Pydantic v2 from_attributes=True).
    """
    from sqlalchemy import select

    from trezarr.bible.dto import SeriesDTO
    from trezarr.bible.models import Series

    async with session_factory() as session:
        async with session.begin():
            row = Series(
                arr_kind="sonarr",
                arr_instance="default",
                arr_series_id=100,
                tvdb_id=999,
                tmdb_id=None,
                arr_metadata={"genres": ["drama"], "year": 2021},
                register=None,
                locked_fields=[],
            )
            session.add(row)
            await session.flush()
            row_id = row.id

    # Reload from DB and validate into DTO
    async with session_factory() as session:
        loaded = (await session.execute(select(Series).where(Series.id == row_id))).scalar_one()
        dto = SeriesDTO.model_validate(loaded, from_attributes=True)

    assert dto.id == row_id
    assert dto.arr_kind == "sonarr"
    assert dto.arr_instance == "default"
    assert dto.arr_series_id == 100
    assert dto.tvdb_id == 999
    assert dto.tmdb_id is None
    assert dto.arr_metadata == {"genres": ["drama"], "year": 2021}
    assert dto.register is None
    assert dto.locked_fields == []

    # Verify the model carries from_attributes=True
    assert SeriesDTO.model_config.get("from_attributes") is True, (
        "SeriesDTO.model_config must have from_attributes=True for ORM bridge (D-39)"
    )


def test_bible_event_dto_created_at_is_datetime():
    """BibleEventDTO.created_at is typed as datetime | None — Pydantic v2 coerces ISO-8601 strings.

    Passing an ISO-8601 string to BibleEventDTO.created_at must produce a datetime
    object (not a raw string or Any). Pydantic v2 coerces automatically when the
    annotation is `datetime | None`.

    Verifies: Cross-AI review MEDIUM finding — BibleEventDTO.created_at must NOT be
    typed as Any; datetime | None is the correct type for proper coercion.
    """
    from datetime import datetime

    from trezarr.bible.dto import BibleEventDTO

    dto = BibleEventDTO(
        id=1,
        series_id=1,
        entity_type="character",
        entity_id=2,
        field="role",
        source="inference",
        created_at="2026-01-01T00:00:00",
    )

    assert isinstance(dto.created_at, datetime), (
        f"BibleEventDTO.created_at should be a datetime after Pydantic v2 coercion, "
        f"got {type(dto.created_at).__name__}: {dto.created_at!r}"
    )
    assert dto.created_at.year == 2026
    assert dto.created_at.month == 1
    assert dto.created_at.day == 1
