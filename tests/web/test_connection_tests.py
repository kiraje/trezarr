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
        "D-71 violation: API key value leaked into connection error response"
    )



# ── Regression: frontend/backend field-name contract (debug llm-test-connection-422) ──


def test_llm_rejects_ui_prefixed_payload():
    """The raw UI-prefixed payload (llm_*) MUST be rejected with 422 (regression guard).

    This pins the backend contract that the frontend bug violated: the Settings UI
    section-state object uses prefixed keys (llm_base_url/llm_model/llm_api_key).
    Posting it raw produced HTTP 422 (every field "missing"), so "Test Connection"
    never attempted a connection. The frontend now strips the `${svc}_` prefix via
    stripSvcPrefix() before POSTing; this test documents WHY that mapping is required.
    """
    import asyncio  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/llm",
                json={
                    "llm_base_url": "https://api.tlemons.com/v1",
                    "llm_model": "ds/deepseek-v4-pro",
                    "llm_api_key": "",
                },
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 422, "prefixed UI payload must 422 — frontend must strip the svc_ prefix"
    missing = {tuple(e["loc"]) for e in resp.json()["detail"] if e["type"] == "missing"}
    assert ("body", "base_url") in missing
    assert ("body", "api_key") in missing
    assert ("body", "model") in missing


def test_llm_accepts_deprefixed_payload(httpx_mock):
    """The de-prefixed payload (what the frontend now sends after stripSvcPrefix) succeeds.

    Mirrors the exact shape the Settings UI produces post-fix: llm_* form keys with
    the `llm_` prefix removed -> base_url/model/api_key. Proves the contract the
    frontend now satisfies, using the same realistic Base URL/model from the report.
    """
    import asyncio  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    # openai SDK posts to base_url + /chat/completions
    httpx_mock.add_response(
        url="https://api.tlemons.com/v1/chat/completions",
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "ds/deepseek-v4-pro",
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
            # The frontend's stripSvcPrefix("llm", {llm_base_url, llm_model, llm_api_key})
            # yields exactly this body:
            return await client.post(
                "/api/test/llm",
                json={
                    "base_url": "https://api.tlemons.com/v1",
                    "model": "ds/deepseek-v4-pro",
                    "api_key": "test-key",
                },
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


# ── Regression: masked-key reuse (test reuses stored credential when key blank) ──


def test_llm_empty_key_falls_back_to_stored(httpx_mock):
    """Empty api_key -> the test reuses the server-side stored LLM key (D-71).

    When the operator clicks Test Connection without re-typing the masked ("set")
    key, the Settings UI sends api_key="". The endpoint must fall back to the
    stored secret so the test reflects the saved configuration — and the stored
    key must travel only on the outbound request, never back in the response.
    """
    import asyncio  # noqa: PLC0415
    from pydantic import SecretStr  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    httpx_mock.add_response(
        url="https://api.tlemons.com/v1/chat/completions",
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "ds/deepseek-v4-pro",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "p"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
        status_code=200,
    )

    app = create_app()
    app.state.settings = TrezarrSettings(
        llm_base_url="https://api.tlemons.com/v1",
        llm_model="ds/deepseek-v4-pro",
        llm_api_key=SecretStr("stored-llm-key"),
    )

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/llm",
                json={"base_url": "https://api.tlemons.com/v1", "model": "ds/deepseek-v4-pro", "api_key": ""},
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    # The stored key authenticated the probe (OpenAI SDK -> Authorization: Bearer <key>)
    req = httpx_mock.get_request(url="https://api.tlemons.com/v1/chat/completions")
    assert req.headers.get("authorization") == "Bearer stored-llm-key"
    # D-71: the stored key must never appear in the response body
    assert "stored-llm-key" not in resp.text


def test_sonarr_empty_key_falls_back_to_stored(httpx_mock):
    """Empty api_key -> the Sonarr test reuses the stored key (X-Api-Key header)."""
    import asyncio  # noqa: PLC0415
    from pydantic import SecretStr  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/system/status",
        json={"version": "3.0.9.1549"},
        status_code=200,
    )

    app = create_app()
    app.state.settings = TrezarrSettings(sonarr_api_key=SecretStr("stored-sonarr-key"))

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/sonarr",
                json={"host": "192.168.1.100", "port": 8989, "api_key": ""},
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    req = httpx_mock.get_request(url="http://192.168.1.100:8989/api/v3/system/status")
    assert req.headers.get("x-api-key") == "stored-sonarr-key"
    assert "stored-sonarr-key" not in resp.text


def test_typed_key_overrides_stored(httpx_mock):
    """A freshly-typed key wins over the stored one — fallback only fires when blank.

    Guards against the fallback masking a deliberately-entered new key: the
    operator typed "fresh-typed-key", which must authenticate the probe instead
    of the stored "stored-llm-key".
    """
    import asyncio  # noqa: PLC0415
    from pydantic import SecretStr  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    httpx_mock.add_response(
        url="https://api.tlemons.com/v1/chat/completions",
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "ds/deepseek-v4-pro",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "p"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
        status_code=200,
    )

    app = create_app()
    app.state.settings = TrezarrSettings(llm_api_key=SecretStr("stored-llm-key"))

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/test/llm",
                json={
                    "base_url": "https://api.tlemons.com/v1",
                    "model": "ds/deepseek-v4-pro",
                    "api_key": "fresh-typed-key",
                },
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    req = httpx_mock.get_request(url="https://api.tlemons.com/v1/chat/completions")
    assert req.headers.get("authorization") == "Bearer fresh-typed-key"
