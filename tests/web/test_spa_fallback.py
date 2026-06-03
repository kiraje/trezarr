"""Tests for SPAStaticFiles — selective SPA fallback for browser deep-link refresh.

Verifies that:
- Extensionless client-side routes (e.g. /library, /bible/123) return 200 index.html.
- Missing assets with a file extension (e.g. /assets/does-not-exist.js) return 404.
- Unknown /api/... paths return 404 JSON, not the SPA shell.
- The root path (/) continues to return 200 index.html (regression guard).
- A real static file present in the tmp dir is served with its own content (files win).

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio decorator needed.
All trezarr.web.* imports are deferred inside test bodies (PLC0415 pattern).
"""

from __future__ import annotations

_SENTINEL = "<!doctype html><title>SPA</title>"
_ASSET_CONTENT = "console.log('ok');"


def _make_spa_dir(tmp_path):
    """Write a minimal static directory to tmp_path.

    Creates:
      - index.html  (contains the known sentinel string)
      - asset.js    (contains known JS content, used by test_real_static_file_served_directly)

    Returns the directory path as a string.
    """
    (tmp_path / "index.html").write_text(_SENTINEL, encoding="utf-8")
    (tmp_path / "asset.js").write_text(_ASSET_CONTENT, encoding="utf-8")
    return str(tmp_path)


async def test_spa_deep_link_library(tmp_path):
    """GET /library returns 200 and the index.html sentinel content."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    from trezarr.web.app import create_app  # noqa: PLC0415

    spa_dir = _make_spa_dir(tmp_path)
    app = create_app(_spa_dir=spa_dir)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/library")
    assert resp.status_code == 200
    assert _SENTINEL in resp.text


async def test_spa_nested_route_bible(tmp_path):
    """GET /bible/123 returns 200 and the index.html sentinel content."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    from trezarr.web.app import create_app  # noqa: PLC0415

    spa_dir = _make_spa_dir(tmp_path)
    app = create_app(_spa_dir=spa_dir)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/bible/123")
    assert resp.status_code == 200
    assert _SENTINEL in resp.text


async def test_missing_asset_with_extension_returns_404(tmp_path):
    """GET /assets/does-not-exist.js returns 404, not the SPA shell."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    from trezarr.web.app import create_app  # noqa: PLC0415

    spa_dir = _make_spa_dir(tmp_path)
    app = create_app(_spa_dir=spa_dir)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/assets/does-not-exist.js")
    assert resp.status_code == 404
    assert _SENTINEL not in resp.text


async def test_unknown_api_path_returns_404_json(tmp_path):
    """GET /api/nope returns 404 with application/json content type, not the SPA shell."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    from trezarr.web.app import create_app  # noqa: PLC0415

    spa_dir = _make_spa_dir(tmp_path)
    app = create_app(_spa_dir=spa_dir)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/nope")
    assert resp.status_code == 404
    assert "application/json" in resp.headers.get("content-type", "")
    assert _SENTINEL not in resp.text


async def test_root_still_serves_index(tmp_path):
    """GET / returns 200 and index.html sentinel (regression: existing root behavior)."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    from trezarr.web.app import create_app  # noqa: PLC0415

    spa_dir = _make_spa_dir(tmp_path)
    app = create_app(_spa_dir=spa_dir)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert _SENTINEL in resp.text


async def test_real_static_file_served_directly(tmp_path):
    """GET /asset.js returns 200 with the file's own content, not the SPA shell."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    from trezarr.web.app import create_app  # noqa: PLC0415

    spa_dir = _make_spa_dir(tmp_path)
    app = create_app(_spa_dir=spa_dir)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/asset.js")
    assert resp.status_code == 200
    assert resp.text == _ASSET_CONTENT
