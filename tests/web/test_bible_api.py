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

import pytest


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_get_series_list():
    """BIBLE-08 c1: GET /api/series returns list; bounded (LIMIT 500 per security domain)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/series")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert False  # placeholder — Plan 08-03 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_get_series_bible():
    """BIBLE-08 c1: GET /api/series/{id}/bible returns full Bible with characters/address_map/terms/register."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/series/1/bible")
    assert resp.status_code in (200, 404)
    assert False  # placeholder — Plan 08-03 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_lock_address_map_missing_term_rejected():
    """BIBLE-08 c2 / T-08-01: lock AddressMap with empty address_term → HTTP 422 (reconcile.py:275 non-None guard, D-87)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/series/1/address-map/1",
            json={"field": "address_term", "value": "", "lock": True},
        )
    assert resp.status_code == 422
    assert False  # placeholder — Plan 08-03 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_write_acquires_series_lock():
    """D-81: UI write during Pass-1 inference acquires per-series asyncio.Lock (no interleave)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/series/1/characters/1",
            json={"field": "gender", "value": "male", "lock": True},
        )
    assert resp.status_code in (200, 503)
    assert False  # placeholder — Plan 08-03 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_get_field_history():
    """D-82 / T-08-02: GET /api/series/{id}/bible/{entity_type}/{entity_id}/history returns BibleEventDTOs (LIMIT 100)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/series/1/bible/character/1/history")
    assert resp.status_code in (200, 404)
    assert False  # placeholder — Plan 08-03 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_bible_route_does_not_import_sqla():
    """D-39: bible route module must not import SQLAlchemy models or sqlalchemy directly."""
    import inspect  # noqa: PLC0415
    import trezarr.web.routes.bible as bible_module  # noqa: PLC0415
    src = inspect.getsource(bible_module)
    assert "from trezarr.bible.models" not in src
    assert "from sqlalchemy" not in src
    assert False  # placeholder — Plan 08-03 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_delete_address_pair():
    """D-83: DELETE /api/series/{id}/address-map/{aid} removes the leaf row and returns {deleted: id}; calls delete_address_pair store function (no inline SQLAlchemy in route, D-39)."""
    from trezarr.bible.store import delete_address_pair  # noqa: PLC0415
    assert False  # placeholder — Plan 08-02/03 will implement


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.web.routes.bible not yet created — Plan 08-03",
)
async def test_delete_term():
    """D-83: DELETE /api/series/{id}/terms/{tid} removes the leaf row and returns {deleted: id}; calls delete_term store function (no inline SQLAlchemy in route, D-39)."""
    from trezarr.bible.store import delete_term  # noqa: PLC0415
    assert False  # placeholder — Plan 08-02/03 will implement
