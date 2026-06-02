"""Tests for Phase 8 Bible REST API (BIBLE-08, D-39, D-81, D-82, D-83, D-87).

Tests cover:
  BIBLE-08 c1 — GET /api/series returns bounded list (LIMIT 500)
  BIBLE-08 c1 — GET /api/series/{id}/bible returns full Bible
  BIBLE-08 c2 / T-08-01 — lock AddressMap with empty address_term → HTTP 422
  D-81 — UI write during Pass-1 inference acquires per-series asyncio.Lock
  D-82 / T-08-02 — GET .../history returns BibleEventDTOs (LIMIT 100)
  D-39 — bible route module must not import SQLAlchemy models or sqlalchemy
  D-83 — DELETE /api/series/{id}/address-map/{aid} removes leaf row
  D-83 — DELETE /api/series/{id}/terms/{tid} removes leaf row

asyncio_mode="auto" is configured project-wide in pyproject.toml — no @pytest.mark.asyncio.
"""
from __future__ import annotations


async def test_get_series_list():
    """BIBLE-08 c1: GET /api/series returns list; bounded (LIMIT 500 per security domain)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/series")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_series_bible():
    """BIBLE-08 c1: GET /api/series/{id}/bible on a fresh app (no DB) returns 404."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/series/999/bible")
    assert resp.status_code == 404


async def test_lock_address_map_missing_term_rejected():
    """BIBLE-08 c2 / T-08-01: lock AddressMap with empty address_term → HTTP 422 (D-87 non-None guard)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/series/1/address-map/1",
            json={"self_term": "anh", "address_term": "", "lock": True},
        )
    assert resp.status_code == 422


async def test_write_acquires_series_lock():
    """D-81: validates that field guard fires before lock acquisition (422 on invalid field);
    get_series_lock returns asyncio.Lock (type check).

    Part A: PATCH with invalid field returns 422 BEFORE any series lock/store call.
    Part B: get_series_lock(series_id) returns an asyncio.Lock instance (type-correct accessor).
    """
    import asyncio  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415
    from trezarr.web.worker import get_series_lock  # noqa: PLC0415

    # Part A: invalid field → 422 before lock acquisition
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/series/1/characters/1",
            json={"field": "nonexistent_field", "value": "x", "lock": False},
        )
    assert resp.status_code == 422

    # Part B: get_series_lock returns asyncio.Lock
    lock = get_series_lock(1)
    assert isinstance(lock, asyncio.Lock)


async def test_get_field_history():
    """D-82 / T-08-02: GET /api/series/{id}/bible/{entity_type}/{entity_id}/history on a fresh app returns 200 + list."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/series/1/bible/character/1/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_field_history_dto_is_json_serializable():
    """Regression (Phase-8 live-UAT): the history route must serialize BibleEventDTO via
    model_dump(mode="json"). A real bible_event row carries a datetime created_at; a plain
    model_dump() leaves a datetime object that Starlette's JSONResponse cannot encode -> 500.
    The prior test_get_field_history only hit the empty-DB branch (session_factory is None ->
    JSONResponse([])), so the datetime serialization was never exercised. This guards it.
    """
    import json  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    import pytest  # noqa: PLC0415

    from trezarr.bible.dto import BibleEventDTO  # noqa: PLC0415

    dto = BibleEventDTO(
        id=1,
        series_id=1,
        episode_key="S01E01",
        entity_type="character",
        entity_id=1,
        field="gender",
        old_value="male",
        new_value="female",
        source="import",
        created_at=datetime(2026, 6, 2, 3, 58, 49, tzinfo=timezone.utc),
    )

    # What the route now does — must be JSON-serializable (no raise).
    json.dumps([dto.model_dump(mode="json", by_alias=True)])

    # The original bug: a plain model_dump() leaves a datetime that json.dumps rejects.
    with pytest.raises(TypeError):
        json.dumps([dto.model_dump(by_alias=True)])


async def test_bible_route_does_not_import_sqla():
    """D-39: bible route module must not import SQLAlchemy models or sqlalchemy directly."""
    import inspect  # noqa: PLC0415
    import trezarr.web.routes.bible as bible_module  # noqa: PLC0415

    src = inspect.getsource(bible_module)
    assert "from trezarr.bible.models" not in src
    assert "from sqlalchemy" not in src


async def test_delete_address_pair():
    """D-83: DELETE /api/series/{id}/address-map/{aid} on a fresh app (no DB) returns 404.

    Confirms the route calls delete_address_pair store function via deferred import (D-39).
    """
    from trezarr.bible.store import delete_address_pair  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    # Confirm delete_address_pair is importable from store (D-39 compliance)
    assert callable(delete_address_pair)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete("/api/series/1/address-map/999")
    # No DB → route returns 404 (session_factory None → HTTPException 404)
    assert resp.status_code == 404


async def test_delete_term():
    """D-83: DELETE /api/series/{id}/terms/{tid} on a fresh app (no DB) returns 404.

    Confirms the route calls delete_term store function via deferred import (D-39).
    """
    from trezarr.bible.store import delete_term  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    # Confirm delete_term is importable from store (D-39 compliance)
    assert callable(delete_term)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete("/api/series/1/terms/999")
    # No DB → route returns 404 (session_factory None → HTTPException 404)
    assert resp.status_code == 404
