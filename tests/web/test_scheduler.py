"""Wave-0 RED stubs for AUTO-02 poll scheduler enqueue and deduplication.

These stubs are xfail markers — the RED suite runs without import errors.
All trezarr.web.* imports are deferred inside test bodies.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.scheduler not yet created — Plan 07-02")
async def test_poll_enqueues():
    """Poll job discovers newly-eligible items and enqueues them (AUTO-02).

    The APScheduler poll job must call discover + scan + enqueue for items
    that have a source subtitle but no Vietnamese translation yet.
    """
    from trezarr.web.scheduler import poll_and_enqueue  # noqa: PLC0415

    # poll_and_enqueue must be callable and must not raise on an empty discovery
    await poll_and_enqueue(session_factory=None, settings=None)  # type: ignore[arg-type]
    assert True  # If we reach here, the function exists and is callable


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.scheduler not yet created — Plan 07-02")
async def test_poll_deduplicates():
    """Poll must not double-enqueue an already-queued source_path (AUTO-02/D-66).

    If a source_path already has a Job row with status in ('queued', 'running'),
    poll_and_enqueue must return False for that item and not insert a duplicate row.
    This mirrors the ledger's select-then-insert dedup guard.
    """
    from trezarr.web.scheduler import poll_and_enqueue  # noqa: PLC0415
    from trezarr.web.worker import enqueue_job  # noqa: PLC0415

    # Simulate: enqueue a path first, then poll should not re-enqueue it
    source_path = "/tv/Show/S01E01.mkv"
    # First enqueue — should succeed
    first = await enqueue_job(source_path=source_path, trigger="poll", session_factory=None)  # type: ignore[arg-type]
    # Second enqueue of same path with active job — should be deduped (return False)
    second = await enqueue_job(source_path=source_path, trigger="poll", session_factory=None)  # type: ignore[arg-type]
    assert second is False, (
        "D-66 dedup: enqueue_job must return False for already-queued source_path"
    )
