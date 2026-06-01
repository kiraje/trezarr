"""Wave-0 RED stubs for SVC-02 settings masking / write-back / secret-never-in-response.

These stubs are xfail markers — the RED suite runs without import errors.
All trezarr.web.* imports are deferred inside test bodies.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.routes.settings not yet created — Plan 07-02")
async def test_secrets_masked():
    """GET /api/settings returns masked sentinel for SecretStr fields, not raw values (SVC-02)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    # Secret fields must never appear as raw strings — must be masked sentinel or is_set dict
    secret_fields = {"llm_api_key", "sonarr_api_key", "radarr_api_key", "bazarr_api_key"}
    for field in secret_fields:
        if field in data:
            val = data[field]
            # Must be {"is_set": bool, "value": "**REDACTED**"} or similar sentinel
            assert isinstance(val, dict) or val in ("**REDACTED**", ""), (
                f"{field} must be masked; got: {val!r}"
            )


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.routes.settings not yet created — Plan 07-02")
async def test_settings_write():
    """PUT /api/settings writes config to config.yaml and returns updated settings (SVC-02)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/settings", json={"web_port": 6868, "poll_interval_seconds": 900})
    assert resp.status_code in (200, 204)


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.routes.settings not yet created — Plan 07-02")
async def test_secret_never_in_response():
    """GET /api/settings must never return raw SecretStr value (D-70).

    Any SecretStr field that appears in the settings response must be masked
    with a sentinel value — the raw secret must never travel over the wire.
    """
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.text
    # The actual secret value "not-set" or any configured key must never appear in response
    # We check the raw response text for any raw secret pattern
    secret_fields = {"llm_api_key", "sonarr_api_key", "radarr_api_key", "bazarr_api_key"}
    data = resp.json()
    for field in secret_fields:
        if field in data:
            val = data[field]
            # Must NOT be a plain string of the secret value
            assert not isinstance(val, str) or val in ("**REDACTED**", ""), (
                f"D-70 violation: {field} returned raw string value in response"
            )
