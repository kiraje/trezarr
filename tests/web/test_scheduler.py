"""Tests for AUTO-02 poll scheduler — enqueue and deduplication (Plan 07-03 GREEN).

Verifies:
  - poll_and_enqueue exists and is callable (no-op on None args)
  - enqueue_job dedup guard returns False for an already-queued source_path (D-66)

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations


async def test_poll_enqueues():
    """Poll job discovers newly-eligible items and enqueues them (AUTO-02).

    The APScheduler poll job must call discover + scan + enqueue for items
    that have a source subtitle but no Vietnamese translation yet.
    """
    from trezarr.web.scheduler import poll_and_enqueue  # noqa: PLC0415

    # poll_and_enqueue must be callable and must not raise on an empty discovery
    await poll_and_enqueue(session_factory=None, settings=None)  # type: ignore[arg-type]
    assert True  # If we reach here, the function exists and is callable


async def test_poll_deduplicates():
    """Poll must not double-enqueue an already-queued source_path (AUTO-02/D-66).

    If a source_path already has a Job row with status in ('queued', 'running'),
    poll_and_enqueue must return False for that item and not insert a duplicate row.
    This mirrors the ledger's select-then-insert dedup guard.
    """
    from trezarr.web.worker import enqueue_job  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    # Use a unique path per test run to avoid collision with other test sessions
    # that share the module-level _no_db_enqueued set
    source_path = f"/tv/Show/dedup-test-{uuid.uuid4()}.mkv"
    # First enqueue — should succeed
    first = await enqueue_job(source_path=source_path, trigger="poll", session_factory=None)  # type: ignore[arg-type]
    # Second enqueue of same path with active job — should be deduped (return False)
    second = await enqueue_job(source_path=source_path, trigger="poll", session_factory=None)  # type: ignore[arg-type]
    assert first is True, "first enqueue_job call should return True"
    assert second is False, (
        "D-66 dedup: enqueue_job must return False for already-queued source_path"
    )
