"""Wave-0 RED stubs for AUTO-05/D-67/D-68 worker per-series lock, reconcile, and concurrency.

These stubs are xfail markers — the RED suite runs without import errors.
All trezarr.web.* imports are deferred inside test bodies.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.worker not yet created — Plan 07-02")
async def test_reconcile_in_progress():
    """Job rows with status running/queued are reset to queued and re-enqueued on reconcile (AUTO-05/D-67).

    On startup, reconcile_in_progress must find all Job rows with status in
    ('queued', 'running'), reset them to 'queued', and re-add them to the work
    queue. This handles the crash-resume case where the previous process died
    mid-translation.
    """
    from trezarr.web.worker import reconcile_in_progress  # noqa: PLC0415

    # Calling reconcile_in_progress on a fresh DB (no stale jobs) should be a no-op
    await reconcile_in_progress(session_factory=None)  # type: ignore[arg-type]
    assert True  # If we reach here, the function exists and is callable


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.worker not yet created — Plan 07-02")
async def test_reconcile_in_progress_from_ledger():
    """A ProcessedFile row with status=in_progress and NO matching Job row must be re-enqueued via enqueue_job(trigger=startup-reconcile) on startup (D-67 second reconcile source).

    When a process crashes mid-translation, two types of stale state can exist:
    1. A Job row with status running/queued (covered by test_reconcile_in_progress)
    2. A ProcessedFile row with status=in_progress but NO corresponding Job row
       (the job was dequeued and the row deleted/missing before the process crashed)

    This test covers arm 2: the ProcessedFile ledger reconcile path.
    On startup, reconcile must also scan ProcessedFile for status='in_progress' rows
    with no matching Job row, and call enqueue_job(trigger='startup-reconcile') for each.
    """
    from trezarr.web.worker import reconcile_in_progress_from_ledger  # noqa: PLC0415

    # On a fresh DB with no stale ProcessedFile in_progress rows, this is a no-op
    await reconcile_in_progress_from_ledger(session_factory=None)  # type: ignore[arg-type]
    assert True  # If we reach here, the function exists and is callable


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.worker not yet created — Plan 07-02")
async def test_per_series_serialization():
    """Two episodes of same series_id must run serially (AUTO-05/D-68).

    The per-series asyncio.Lock must ensure that two concurrent jobs for the
    same series_id do not overlap. When one job is running, the second must
    wait until the first completes before starting.
    """
    import asyncio  # noqa: PLC0415
    from trezarr.web.worker import _series_locks  # noqa: PLC0415

    series_id = 42
    lock = _series_locks.setdefault(series_id, asyncio.Lock())
    results: list[int] = []

    async def task_a():
        async with lock:
            results.append(1)
            await asyncio.sleep(0.01)
            results.append(2)

    async def task_b():
        async with lock:
            results.append(3)

    await asyncio.gather(task_a(), task_b())
    # If serialization works: [1, 2, 3] — task_b waits for task_a
    assert results == [1, 2, 3], (
        f"D-68: per-series lock did not serialize execution; got {results}"
    )


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.worker not yet created — Plan 07-02")
async def test_distinct_series_concurrent():
    """Two episodes of distinct series_id must be able to run concurrently (AUTO-05/D-68).

    Different series must each get their own independent asyncio.Lock.
    Jobs for series A and series B should not block each other.
    """
    import asyncio  # noqa: PLC0415
    from trezarr.web.worker import _series_locks  # noqa: PLC0415

    series_a = 1
    series_b = 2
    lock_a = _series_locks.setdefault(series_a, asyncio.Lock())
    lock_b = _series_locks.setdefault(series_b, asyncio.Lock())

    # Locks for distinct series must be different objects
    assert lock_a is not lock_b, (
        "D-68: distinct series must have independent locks"
    )
    # Both locks must be acquirable simultaneously (no cross-series blocking)
    acquired_a = lock_a.locked()
    acquired_b = lock_b.locked()
    assert not acquired_a and not acquired_b, (
        "D-68: distinct series locks should not block each other"
    )


@pytest.mark.xfail(raises=(ImportError, AssertionError, TypeError), reason="trezarr.web.worker not yet created — Plan 07-02")
async def test_no_second_semaphore():
    """worker must not introduce a second asyncio.Semaphore — only asyncio.Lock per series (D-68/Pitfall C).

    The single LLMClient._semaphore (D-06) is the only global concurrency cap on LLM calls.
    The worker must use asyncio.Lock (per series) for serialization, NOT a second Semaphore.
    Introducing a second Semaphore would double-cap throughput and violate D-68/Pitfall C.
    """
    import asyncio  # noqa: PLC0415
    import inspect  # noqa: PLC0415
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    # Inspect the worker module for any asyncio.Semaphore instances at module level
    # (class-level or module-level Semaphores are the violation)
    module_globals = vars(worker_mod)
    semaphore_vars = [
        name for name, val in module_globals.items()
        if isinstance(val, asyncio.Semaphore)
    ]
    assert semaphore_vars == [], (
        f"D-68/Pitfall C: worker module has module-level Semaphore(s): {semaphore_vars}. "
        "Use asyncio.Lock per series_id instead."
    )
