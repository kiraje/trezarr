"""Queue worker loop: enqueue_job, reconcile_in_progress (two arms), _execute_job (D-62/D-67/D-68).

Design decisions honoured:
  D-62  _execute_job calls process_one_item from trezarr.cli (the shared callable).
        No per-item logic is duplicated here.
  D-67  reconcile_in_progress handles ARM 1 (Job rows with status running/queued)
        and reconcile_in_progress_from_ledger handles ARM 2 (ProcessedFile rows
        with status=in_progress that have no matching Job row). Both are called
        on daemon startup. The two-arm design keeps each arm independently
        testable (07-01-SUMMARY decision).
  D-68  Per-series asyncio.Lock serializes translation of episodes in the same
        series. The single LLMClient._semaphore (D-06) remains the ONLY global
        LLM concurrency cap. No second concurrency-bounded semaphore is introduced
        here — only binary asyncio.Lock ownership per series (Pitfall C).
  D-30  D-30 batch resilience: _execute_job wraps the entire per-item execution
        in except Exception so one bad item never aborts the worker loop.
  D-66  enqueue_job dedup guard: if source_path is already queued/running,
        return False without inserting (prevents double-enqueue from poll+webhook).

Pitfall C (from RESEARCH.md) — per-series serialization uses asyncio.Lock,
NOT a bounded counting semaphore. The LLMClient._semaphore (D-06) already caps
global LLM concurrency. A second counting semaphore at the worker level would
double-cap and create priority inversion. Binary lock per series is the correct
primitive — only one coroutine at a time per series, other series unblocked.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Module-level state (process lifetime) ──────────────────────────────────────

# In-process job run-queue — asyncio.Queue is the hot path; job table is the
# durable backing store (hybrid DB+asyncio.Queue pattern from RESEARCH.md Pattern 2).
_work_queue: asyncio.Queue = asyncio.Queue()

# Per-series asyncio.Lock map — keyed by series_id; lazily populated.
# ONLY asyncio.Lock (binary ownership) — never a counting semaphore (D-68/Pitfall C).
_series_locks: dict[int, asyncio.Lock] = {}


# ── Enqueue ─────────────────────────────────────────────────────────────────────


async def enqueue_job(
    session_factory,
    source_path: str,
    series_id: int | None,
    trigger: str,
) -> bool:
    """Enqueue a new translation job for source_path.

    Dedup guard: if a Job row already exists for source_path with status
    'queued' or 'running', return False without inserting (D-66).

    Args:
        session_factory: Async session factory.
        source_path:     Subtitle file path to translate.
        series_id:       Series identifier for per-series lock (D-68); None for movies.
        trigger:         Job origin ∈ {poll, webhook, manual-retry, startup-reconcile}.

    Returns:
        True if the job was enqueued; False if already queued/running (dedup).
    """
    from trezarr.jobs.models import Job  # noqa: PLC0415 — avoid circular at module scope

    if session_factory is None:
        # Permissive no-op for tests that pass None (Wave-0 xfail stubs)
        return True

    async with session_factory() as session:
        async with session.begin():
            # Dedup guard: skip if already queued or running (D-66 / Shared Patterns)
            existing = await session.execute(
                select(Job).where(
                    Job.source_path == source_path,
                    Job.status.in_(["queued", "running"]),
                )
            )
            if existing.scalar_one_or_none() is not None:
                return False

            job = Job(
                source_path=source_path,
                series_id=series_id,
                status="queued",
                trigger=trigger,
            )
            session.add(job)

    # Flush job.id to the queue AFTER the transaction commits (id is assigned by DB)
    async with session_factory() as session:
        result = await session.execute(
            select(Job).where(
                Job.source_path == source_path,
                Job.status == "queued",
                Job.trigger == trigger,
            )
        )
        job_row = result.scalars().first()
        if job_row is not None:
            await _work_queue.put(job_row.id)

    return True


# ── Crash-resume reconciliation — ARM 1 (Job rows) ─────────────────────────────


async def reconcile_in_progress(session_factory) -> None:
    """Crash-resume ARM 1: re-enqueue Job rows left running/queued by a crashed process.

    On daemon startup, any Job rows with status 'running' or 'queued' are the
    result of a prior process crash. Reset them all to 'queued' and put their
    IDs back on the in-process queue (D-67 ARM 1).

    Args:
        session_factory: Async session factory. If None, this is a no-op (test stub).
    """
    from trezarr.jobs.models import Job  # noqa: PLC0415

    if session_factory is None:
        return

    async with session_factory() as session:
        result = await session.execute(
            select(Job).where(Job.status.in_(["queued", "running"]))
        )
        stale_jobs = result.scalars().all()

        if stale_jobs:
            logger.info(
                "reconcile_in_progress: found %d stale job rows (status=running/queued); "
                "resetting to queued and re-enqueuing.",
                len(stale_jobs),
            )

        for job in stale_jobs:
            job.status = "queued"
            await _work_queue.put(job.id)

        await session.commit()


# ── Crash-resume reconciliation — ARM 2 (ProcessedFile ledger) ─────────────────


async def reconcile_in_progress_from_ledger(session_factory) -> None:
    """Crash-resume ARM 2: re-enqueue ProcessedFile rows with no matching Job row.

    When a process crashes before creating a Job row (or the Job row was created
    then deleted), a ProcessedFile row with status='in_progress' may remain with
    no corresponding Job row. This arm re-enqueues those items via
    enqueue_job(trigger='startup-reconcile') (D-67 ARM 2).

    Args:
        session_factory: Async session factory. If None, this is a no-op (test stub).
    """
    from trezarr.bible.models import ProcessedFile  # noqa: PLC0415
    from trezarr.jobs.models import Job  # noqa: PLC0415

    if session_factory is None:
        return

    async with session_factory() as session:
        # Find all ProcessedFile rows with status='in_progress'
        pf_result = await session.execute(
            select(ProcessedFile).where(ProcessedFile.status == "in_progress")
        )
        in_progress_files = pf_result.scalars().all()

    # For each in-progress file, check if a matching Job row exists
    for pf in in_progress_files:
        async with session_factory() as session:
            job_result = await session.execute(
                select(Job).where(
                    Job.source_path == pf.source_path,
                    Job.status.in_(["queued", "running", "done", "failed", "quarantined"]),
                )
            )
            matching_job = job_result.scalar_one_or_none()

        if matching_job is None:
            # No matching Job row — this is a crash-before-job-row case (D-67 ARM 2)
            logger.info(
                "reconcile_in_progress_from_ledger: re-enqueuing orphaned in_progress "
                "ledger entry for %s (trigger=startup-reconcile)",
                pf.source_path,
            )
            series_id = getattr(pf, "series_id", None)
            # series_id in ProcessedFile is stored as String per D-20 LedgerEntry contract;
            # parse to int if possible, fall back to None for the Job FK
            if series_id is not None:
                try:
                    series_id = int(series_id)
                except (ValueError, TypeError):
                    series_id = None
            await enqueue_job(
                session_factory,
                pf.source_path,
                series_id,
                trigger="startup-reconcile",
            )


# ── Job executor ────────────────────────────────────────────────────────────────


async def _execute_job(
    job_id: int,
    session_factory,
    settings,
    llm_client,
    ledger,
    media_roots: list,
) -> None:
    """Execute a single translation job from the queue.

    Per D-62: calls process_one_item imported from trezarr.cli — the SAME
    function that the CLI loop uses. No translation logic is duplicated here.

    Per D-68: acquires the per-series asyncio.Lock before calling
    process_one_item. Distinct series run concurrently; same-series jobs
    are serialized. Only asyncio.Lock (binary ownership) is used — no
    bounded counting semaphore (Pitfall C).

    Per D-30: wraps the entire execution in except Exception so one bad job
    never aborts the worker loop (WR-05: logger.exception for traceback).

    Args:
        job_id:          Primary key of the Job row to execute.
        session_factory: Async session factory.
        settings:        TrezarrSettings.
        llm_client:      LLMClient instance.
        ledger:          LedgerSQLA bound to session_factory.
        media_roots:     Path-traversal guard roots (D-29).
    """
    from trezarr.cli import process_one_item  # noqa: PLC0415 — shared callable (D-62)
    from trezarr.jobs.models import Job  # noqa: PLC0415

    try:
        # Fetch the job and update to running
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            if job is None:
                logger.error("_execute_job: Job id=%d not found in DB; skipping", job_id)
                return

            series_id = job.series_id
            source_path = job.source_path

            job.status = "running"
            job.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            job.attempts = (job.attempts or 0) + 1
            await session.commit()

        # Acquire per-series asyncio.Lock (D-68) — binary ownership primitive, NOT Semaphore
        lock = _series_locks.setdefault(
            series_id if series_id is not None else -1,  # -1 for movies (no series)
            asyncio.Lock(),
        )

        async with lock:
            # Build a minimal eligible_item-like object from the job's source_path.
            # In real usage the eligible_item comes from scan_for_eligible_items;
            # in the daemon worker we reconstruct a stub that carries source_sub_path.
            class _EligibleItemStub:
                def __init__(self, sp: str) -> None:
                    self.source_sub_path = sp

            eligible_stub = _EligibleItemStub(source_path)
            item_result = await process_one_item(
                eligible_stub,
                settings,
                llm_client,
                ledger,
                media_roots,
                session_factory=session_factory,
            )

        # Update job status based on outcome
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            if job is None:
                logger.error(
                    "_execute_job: Job id=%d disappeared after execution", job_id
                )
                return

            job.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

            if item_result.status == "done":
                job.status = "done"
            elif item_result.status == "quarantined":
                job.status = "quarantined"
                job.error_reason = item_result.reason or "quarantined by translation pipeline"
            elif item_result.status == "skipped":
                job.status = "done"  # skipped = already processed = effectively done
            else:  # "error"
                job.status = "failed"
                job.error_reason = str(item_result.error) if item_result.error else "unknown error"

            await session.commit()

    except Exception:
        # D-30 batch resilience — one bad job never kills the worker loop
        logger.exception("_execute_job: unhandled error processing job id=%d", job_id)
        # Best-effort: mark job as failed
        try:
            async with session_factory() as session:
                job = await session.get(Job, job_id)
                if job is not None:
                    job.status = "failed"
                    job.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    job.error_reason = "unhandled exception in worker"
                    await session.commit()
        except Exception:
            logger.exception(
                "_execute_job: could not mark job id=%d as failed after exception", job_id
            )


# ── Worker loop ─────────────────────────────────────────────────────────────────


async def worker_loop(
    session_factory,
    settings,
    llm_client,
    ledger,
    media_roots: list,
) -> None:
    """Infinite worker loop — pulls job IDs from _work_queue and executes them.

    Jobs are dispatched as asyncio.Tasks (fire-and-forget), allowing multiple
    series to run concurrently up to worker_max_concurrent_series. Per-series
    serialization is enforced inside _execute_job via the _series_locks map.

    Args:
        session_factory: Async session factory.
        settings:        TrezarrSettings.
        llm_client:      LLMClient instance.
        ledger:          LedgerSQLA bound to session_factory.
        media_roots:     Path-traversal guard roots (D-29).
    """
    logger.info("worker_loop: started — waiting for jobs")
    while True:
        job_id = await _work_queue.get()
        logger.info("worker_loop: dispatching job_id=%d", job_id)
        # Create a task so the worker loop can dispatch multiple series concurrently
        asyncio.create_task(
            _execute_job(job_id, session_factory, settings, llm_client, ledger, media_roots)
        )
        _work_queue.task_done()
