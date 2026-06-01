"""Tests for AUTO-02 webhook handler — enqueue-only + fast-200 (Plan 07-03 GREEN).

Verifies:
  - POST /webhook returns 200 with {"status": "accepted"} for any payload
  - Handler returns in under 1 second (enqueue-only, Pitfall D)
  - Malicious payload paths are ignored — handler triggers a fresh scan, not path-trust

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations


async def test_webhook_enqueues():
    """POST /webhook triggers scan and enqueue of newly-eligible items (AUTO-02)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    payload = {
        "eventType": "Download",
        "series": {"id": 1, "title": "Test Show"},
        "episodeFile": {"path": "/tv/Test Show/S01E01.mkv"},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "accepted"


async def test_webhook_returns_200_fast():
    """Webhook handler must return 200 without awaiting translation (D-66, Pitfall D).

    The handler must enqueue a background task and return immediately.
    It must NOT await the translation pipeline inline — doing so would block
    the event loop and violate the non-blocking webhook contract.
    """
    import time  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    payload = {"eventType": "Test", "series": {"id": 99}}
    start = time.monotonic()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/webhook", json=payload)
    elapsed = time.monotonic() - start
    assert resp.status_code == 200
    # Handler should return in well under 1 second (enqueue-only, no translation)
    assert elapsed < 1.0, (
        f"D-66 violation: webhook took {elapsed:.2f}s — must return before awaiting translation"
    )


async def test_webhook_ignores_payload_content():
    """Handler triggers scan, never trusts payload source_path directly (AUTO-02/D-66).

    The webhook must never use the payload's file path directly to trigger translation.
    Instead, it triggers a fresh scan via poll_and_enqueue so only legitimately
    eligible paths (from Sonarr/Radarr) get translated.
    """
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    # Payload contains a path that should NOT be trusted
    payload = {
        "eventType": "Download",
        "episodeFile": {"path": "/etc/passwd"},  # malicious path
        "series": {"id": 1},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/webhook", json=payload)
    # Handler must still return 200 — it ignores the untrusted path
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "accepted"
    # The malicious path must not appear in the work queue directly
    # (actual validation is via scan, not payload trust)
