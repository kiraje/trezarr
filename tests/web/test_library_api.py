"""Tests for GET /api/library, GET /api/library/series/{id}/episodes,
and POST /api/translate endpoints (quick task 260603-l8g).

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
All trezarr.web.* imports are deferred inside test bodies (PLC0415 pattern).
"""
from __future__ import annotations


async def test_get_library_returns_200():
    """GET /api/library always returns 200 even when *arr disabled."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library")
    assert resp.status_code == 200
    data = resp.json()
    assert "series" in data
    assert "movies" in data
    assert "errors" in data
    assert isinstance(data["series"], list)
    assert isinstance(data["movies"], list)


async def test_get_series_episodes_disabled_returns_400():
    """GET /api/library/series/{id}/episodes returns 400 when sonarr disabled."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    # Default settings have sonarr_enabled=False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library/series/1/episodes")
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data


async def test_post_translate_missing_source_path_returns_400():
    """POST /api/translate without source_path returns 400."""
    import json  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/translate",
            content=json.dumps({"kind": "series"}),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data


async def test_post_translate_nonexistent_path_returns_400():
    """POST /api/translate with a source_path that doesn't exist on disk returns 400."""
    import json  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/translate",
            content=json.dumps({"kind": "series", "source_path": "/nonexistent/path.srt"}),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
