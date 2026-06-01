"""Wave-0 RED stubs for SVC-02 connection-test endpoints.

These stubs are xfail markers — the RED suite runs without import errors.
All trezarr.web.* imports are deferred inside test bodies.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.routes.test_connection not yet created — Plan 07-02")
async def test_sonarr_connection_ok():
    """POST /api/test/sonarr returns {ok: true} when Sonarr responds (SVC-02)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/test/sonarr",
            json={"host": "192.168.1.100", "port": 8989, "api_key": "test-key"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.routes.test_connection not yet created — Plan 07-02")
async def test_sonarr_connection_error():
    """POST /api/test/sonarr returns {ok: false, error: ...} on connection failure (SVC-02)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/test/sonarr",
            json={"host": "nonexistent.invalid", "port": 8989, "api_key": "bad-key"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "error" in data


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.routes.test_connection not yet created — Plan 07-02")
async def test_llm_connection_ok():
    """POST /api/test/llm returns {ok: true} when the LLM endpoint responds (SVC-02)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/test/llm",
            json={"base_url": "http://localhost:11434/v1", "api_key": "test-key", "model": "llama3"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.routes.test_connection not yet created — Plan 07-02")
async def test_secret_not_in_connection_error():
    """Connection test error response must never include the API key value (D-71 security).

    WR-01 discipline: credential values must be stripped from all error messages
    and log output. The error dict must not contain the raw api_key string.
    """
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    secret_key = "super-secret-api-key-value"
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/test/sonarr",
            json={"host": "nonexistent.invalid", "port": 8989, "api_key": secret_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    # The raw secret must never appear in the response body
    import json  # noqa: PLC0415
    response_text = json.dumps(data)
    assert secret_key not in response_text, (
        f"D-71 violation: API key value leaked into connection error response"
    )
