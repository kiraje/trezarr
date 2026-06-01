"""Queue/History/Logs REST API — GET /api/queue, GET /api/jobs, GET /api/jobs/{id}/logs (SVC-03).

Design decisions honoured:
  SVC-03  Operator can view in-flight jobs (queue), completed/failed history, and
          per-job log trail from the web UI.
  D-75    Log rows are captured by JobLogHandler in worker.py and read back here.

Security (STRIDE threat register):
  T-07-05-01  error_reason capped at 500 chars (path data, no secrets; accepted).
  T-07-05-02  GET /api/jobs LIMIT 200 — prevents OOM from unbounded history.
  T-07-05-03  GET /api/jobs/{id}/logs LIMIT 1000 — log retention cap.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()

# Regex to extract SxxExx episode key from a subtitle file path.
_EPISODE_RE = re.compile(r"[Ss](\d{1,4})[Ee](\d{1,4})")


def _extract_episode_key(source_path: str) -> str:
    """Extract a SxxExx episode key from source_path for the UI Episode column.

    Returns the canonical SxxExx string, or an empty string if not found
    (movies, one-off specials, or non-standard naming).

    Args:
        source_path: Absolute or relative path to the subtitle file.

    Returns:
        SxxExx string (e.g. "S01E02") or "" if not matched.
    """
    m = _EPISODE_RE.search(source_path)
    if m:
        return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}"
    return ""


def _get_session_factory(request: Request):
    """Return the async session_factory from app.state, or None in tests without lifespan."""
    try:
        return request.app.state.session_factory
    except AttributeError:
        return None


# ── GET /api/queue ───────────────────────────────────────────────────────────────


@router.get("/queue")
async def get_queue(request: Request):
    """Return in-flight jobs (status=queued or running) ordered by enqueued_at.

    Response shape per row:
      id, source_path, series_id, status, enqueued_at, started_at, episode_key

    Returns an empty list if no jobs are in flight.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from trezarr.jobs.models import Job  # noqa: PLC0415

    session_factory = _get_session_factory(request)
    if session_factory is None:
        return []

    async with session_factory() as session:
        result = await session.execute(
            select(Job)
            .where(Job.status.in_(["queued", "running"]))
            .order_by(Job.enqueued_at)
        )
        jobs = result.scalars().all()

    return [
        {
            "id": job.id,
            "source_path": job.source_path,
            "series_id": job.series_id,
            "status": job.status,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "episode_key": _extract_episode_key(job.source_path),
        }
        for job in jobs
    ]


# ── GET /api/jobs ────────────────────────────────────────────────────────────────


@router.get("/jobs")
async def get_jobs(request: Request):
    """Return historical jobs (status=done, failed, quarantined) — LIMIT 200 (T-07-05-02).

    Response shape per row:
      id, source_path, series_id, status, error_reason (capped 500 chars),
      trigger, enqueued_at, finished_at, episode_key

    Returns an empty list if no history exists.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from trezarr.jobs.models import Job  # noqa: PLC0415

    session_factory = _get_session_factory(request)
    if session_factory is None:
        return []

    async with session_factory() as session:
        result = await session.execute(
            select(Job)
            .where(Job.status.in_(["done", "failed", "quarantined"]))
            .order_by(Job.finished_at.desc())
            .limit(200)
        )
        jobs = result.scalars().all()

    return [
        {
            "id": job.id,
            "source_path": job.source_path,
            "series_id": job.series_id,
            "status": job.status,
            # T-07-05-01: error_reason may contain file paths; cap at 500 chars as precaution.
            "error_reason": (job.error_reason[:500] if job.error_reason else None),
            "trigger": job.trigger,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "episode_key": _extract_episode_key(job.source_path),
        }
        for job in jobs
    ]


# ── GET /api/jobs/{id}/logs ──────────────────────────────────────────────────────


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: int, request: Request):
    """Return per-job log entries for a given job_id — LIMIT 1000 (T-07-05-03).

    Response shape per row:
      id, level, message, created_at

    Returns 404 if the job does not exist.
    Returns an empty list if the job exists but has no log entries (possible for
    jobs completed before D-75 per-job log capture was deployed).
    """
    from sqlalchemy import select  # noqa: PLC0415
    from trezarr.jobs.models import Job, JobLog  # noqa: PLC0415

    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify the job exists (returns 404 if not, per plan spec)
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        log_result = await session.execute(
            select(JobLog)
            .where(JobLog.job_id == job_id)
            .order_by(JobLog.created_at)
            .limit(1000)
        )
        logs = log_result.scalars().all()

    return [
        {
            "id": log.id,
            "level": log.level,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
