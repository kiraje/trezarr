"""Tests for SVC-02 connection-test endpoints (Plan 07-04 GREEN).

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.

pyarr uses httpx internally — httpx_mock from pytest-httpx intercepts at the
transport layer, so no live *arr instance is needed (same pattern as tests/arr/).
"""
from __future__ import annotations


def test_sonarr_connection_ok(httpx_mock):
    """POST /api/test/sonarr returns {ok: true} when Sonarr responds (SVC-02).

    pyarr is synchronous internally — use a plain def test (not async def) so
    httpx_mock intercepts pyarr's synchronous httpx transport correctly.
    The FastAPI endpoint is async but the pyarr call inside is sync-via-httpx.
    """
    import asyncio  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    # pyarr Sonarr.system.get_status() calls GET /api/v3/system/status
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/system/status",
        json={"version": "3.0.9.1549"},
        status_code=200,
    )

    app = create_app()

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/sonarr",
                json={"host": "192.168.1.100", "port": 8989, "api_key": "test-key"},
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_sonarr_connection_error(httpx_mock):
    """POST /api/test/sonarr returns {ok: false, error: ...} on connection failure (SVC-02)."""
    import asyncio  # noqa: PLC0415
    from httpx import ConnectError  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    # Mock a connection error for the nonexistent host
    httpx_mock.add_exception(
        ConnectError("Connection refused"),
        url="http://nonexistent.invalid:8989/api/v3/system/status",
    )

    app = create_app()

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/sonarr",
                json={"host": "nonexistent.invalid", "port": 8989, "api_key": "bad-key"},
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "error" in data


def test_llm_connection_ok(httpx_mock):
    """POST /api/test/llm returns {ok: true} when the LLM endpoint responds (SVC-02)."""
    import asyncio  # noqa: PLC0415
    import json as json_mod  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    # Mock the OpenAI-compatible chat completions endpoint
    # The openai SDK posts to base_url + /chat/completions
    httpx_mock.add_response(
        url="http://localhost:11434/v1/chat/completions",
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "llama3",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "p"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
        status_code=200,
    )

    app = create_app()

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/llm",
                json={"base_url": "http://localhost:11434/v1", "api_key": "test-key", "model": "llama3"},
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_secret_not_in_connection_error(httpx_mock):
    """Connection test error response must never include the API key value (D-71 security).

    WR-01 discipline: credential values must be stripped from all error messages
    and log output. The error dict must not contain the raw api_key string.
    """
    import asyncio  # noqa: PLC0415
    import json as json_mod  # noqa: PLC0415
    from httpx import ConnectError  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    secret_key = "super-secret-api-key-value"

    # Mock a connection error for the nonexistent host
    httpx_mock.add_exception(
        ConnectError("Connection refused"),
        url="http://nonexistent.invalid:8989/api/v3/system/status",
    )

    app = create_app()

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/sonarr",
                json={"host": "nonexistent.invalid", "port": 8989, "api_key": secret_key},
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    data = resp.json()
    # The raw secret must never appear in the response body
    response_text = json_mod.dumps(data)
    assert secret_key not in response_text, (
        f"D-71 violation: API key value leaked into connection error response"
    )
