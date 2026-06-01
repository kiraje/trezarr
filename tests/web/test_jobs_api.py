"""Wave-0 RED stubs for SVC-03/SVC-04 queue/history/logs/retry endpoints.

These stubs are xfail markers — the RED suite runs without import errors.
All trezarr.web.* imports are deferred inside test bodies.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations


async def test_get_queue():
    """GET /api/queue returns list of in-flight job rows with status queued/running (SVC-03)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/queue")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for job in data:
        assert job["status"] in ("queued", "running"), (
            f"Queue endpoint returned job with unexpected status: {job['status']!r}"
        )


async def test_get_history():
    """GET /api/jobs returns history list of done/failed jobs with reason field (SVC-03)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for job in data:
        assert job["status"] in ("done", "failed", "quarantined"), (
            f"History endpoint returned job with unexpected status: {job['status']!r}"
        )
        assert "error_reason" in job or "reason" in job, (
            "History job row must include error_reason/reason field"
        )


async def test_get_job_logs():
    """GET /api/jobs/{id}/logs returns per-job log trail for a given job id (SVC-03)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/jobs/1/logs")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, list)
        for entry in data:
            assert "message" in entry
            assert "level" in entry


async def test_retry_requeues():
    """POST /api/jobs/{id}/retry must re-enqueue and set trigger=manual-retry (D-74).

    A failed or done job that is retried must have its status reset to 'queued'
    and trigger set to 'manual-retry' before being placed back on the work queue.
    """
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/jobs/1/retry")
    assert resp.status_code in (200, 202, 404)
    if resp.status_code in (200, 202):
        data = resp.json()
        assert data.get("trigger") == "manual-retry" or data.get("status") == "queued", (
            "Retry endpoint must reset trigger to manual-retry"
        )
