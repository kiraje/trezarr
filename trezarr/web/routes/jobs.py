"""Retry REST API — POST /api/jobs/{id}/retry (SVC-04, D-74).

Design decisions honoured:
  D-74  Retry = re-enqueue via the same worker path (enqueue_job). The retry
        resets job state: status='queued', error_reason=None, attempts=0,
        trigger='manual-retry', started_at=None, finished_at=None. Per-series
        serialization (D-68) still applies once the worker picks it up.

Security (STRIDE threat register):
  T-07-05-04  POST /api/jobs/{id}/retry raises 409 if status NOT IN
              ('failed', 'quarantined') — running or queued jobs cannot be
              double-retried (tamper mitigation).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()

_RETRIABLE_STATUSES = frozenset({"failed", "quarantined"})


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: int, request: Request):
    """Reset a failed/quarantined job to queued and re-enqueue it (D-74).

    Steps:
      1. SELECT Job for job_id; 404 if not found.
      2. 409 if status not in ('failed', 'quarantined') — prevents double-retry
         of running or already-queued jobs (T-07-05-04).
      3. Inside session.begin(): reset status='queued', error_reason=None,
         attempts=0, trigger='manual-retry', started_at=None, finished_at=None.
      4. Call _work_queue.put_nowait(job.id) to re-enqueue (dedup satisfied
         by the status reset: the old failure state is cleared before enqueue).

    Returns:
        {"ok": True, "job_id": job_id}

    Raises:
        HTTPException(404): job not found.
        HTTPException(409): job not in a retriable state.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from trezarr.jobs.models import Job  # noqa: PLC0415
    from trezarr.web.worker import _work_queue  # noqa: PLC0415

    try:
        session_factory = request.app.state.session_factory
    except AttributeError:
        # No lifespan (test environment without DB) — no jobs can exist, return 404.
        raise HTTPException(status_code=404, detail="Job not found")

    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(Job).where(Job.id == job_id)
            )
            job = result.scalar_one_or_none()

            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")

            if job.status not in _RETRIABLE_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=f"Job is not in a retriable state (current status: {job.status!r})",
                )

            # Reset to queued (D-74: clear all failure/execution state)
            job.status = "queued"
            job.error_reason = None
            job.attempts = 0
            job.trigger = "manual-retry"
            job.started_at = None
            job.finished_at = None
            # session.begin().__aexit__ commits the transaction

    # Re-enqueue after the transaction commits so the worker sees the updated row.
    # _work_queue.put_nowait is used (not await put()) to avoid blocking; the queue
    # is unbounded (asyncio.Queue()) so put_nowait never raises QueueFull here.
    _work_queue.put_nowait(job_id)
    logger.info("retry_job: job_id=%d re-enqueued (trigger=manual-retry)", job_id)

    return {"ok": True, "job_id": job_id}
