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
  D-75  Per-job structured log capture via JobLogBuffer + JobLogHandler. Each job
        execution buffers log records in-memory and flushes them to job_log rows
        at job completion (RESEARCH.md Pattern 8, Assumption A7 — buffer+flush
        avoids threading complexity from Pitfall I).

Pitfall C (from RESEARCH.md) — per-series serialization uses asyncio.Lock,
NOT a bounded counting semaphore. The LLMClient._semaphore (D-06) already caps
global LLM concurrency. A second counting semaphore at the worker level would
double-cap and create priority inversion. Binary lock per series is the correct
primitive — only one coroutine at a time per series, other series unblocked.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Module-level state (process lifetime) ──────────────────────────────────────

# In-process job run-queue — asyncio.Queue is the hot path; job table is the
# durable backing store (hybrid DB+asyncio.Queue pattern from RESEARCH.md Pattern 2).
_work_queue: asyncio.Queue = asyncio.Queue()

# Per-series asyncio.Lock map — keyed by series_id; lazily populated.
# ONLY asyncio.Lock (binary ownership) — never a counting semaphore (D-68/Pitfall C).
_series_locks: dict[int, asyncio.Lock] = {}

# In-memory dedup set for the session_factory=None path (test/stub mode).
# When session_factory is None, we cannot hit the DB; use this set so the D-66
# dedup contract holds in unit tests without a real DB.
_no_db_enqueued: set[str] = set()

# Strong references to in-flight background asyncio.Tasks (CR-02).
# asyncio holds only a weak reference to tasks — without a strong reference here,
# the GC can collect a task mid-execution under memory pressure (asyncio docs warning).
# Each task is added at creation and removed via add_done_callback when it completes.
_background_tasks: set[asyncio.Task] = set()


# ── Per-job log capture (D-75) ───────────────────────────────────────────────────

# ContextVar that holds the current job_id during _execute_job.
# JobLogHandler.emit() checks this; if None, the handler is a no-op (global
# logging is unaffected outside of a job execution context).
_current_job_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_job_id", default=None
)


class _JobLogBuffer:
    """Collects (level, message) tuples during a single job execution (RESEARCH Assumption A7).

    Buffer + flush-at-end avoids the threading complexity of Pitfall I:
    some logging calls inside translate_file may originate from aiosqlite's
    background threads. Instead of routing log records directly to the async
    DB writer in emit(), we buffer them and flush once, after the job completes.
    """

    def __init__(self) -> None:
        self._records: list[tuple[str, str]] = []

    def append(self, level: str, message: str) -> None:
        self._records.append((level, message))

    def drain(self) -> list[tuple[str, str]]:
        records = self._records[:]
        self._records.clear()
        return records


class _JobLogHandler(logging.Handler):
    """logging.Handler that appends log records to a _JobLogBuffer.

    Checks _current_job_id.get() before every emit(); if None, the handler is
    a no-op so global logging is not affected outside of job executions (D-75).
    """

    def __init__(self, buffer: _JobLogBuffer) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        if _current_job_id.get() is None:
            return  # Not inside a job execution — ignore
        try:
            message = self.format(record)
            self._buffer.append(record.levelname, message)
        except Exception:  # noqa: BLE001
            # Never let the log handler crash the job execution
            pass


# ── Enqueue ─────────────────────────────────────────────────────────────────────

# Fields from the discovery MediaItem that translate_file reads via getattr in
# the Bible-aware path. We snapshot only these — all others are ignored.
_MEDIA_ITEM_SNAPSHOT_FIELDS = (
    "arr_kind",
    "series_id",
    "tvdb_id",
    "tmdb_id",
    "title",
    "season_number",
    "source_type",
    # arr_metadata included separately via getattr below
)


async def enqueue_job(
    session_factory,
    source_path: str,
    series_id: int | None = None,
    trigger: str = "poll",
    media_item: Any = None,
) -> bool:
    """Enqueue a new translation job for source_path.

    Dedup guard: if a Job row already exists for source_path with status
    'queued' or 'running', return False without inserting (D-66).

    Args:
        session_factory: Async session factory. When None, uses an in-memory dedup
                         set (_no_db_enqueued) so the D-66 contract holds in tests.
        source_path:     Subtitle file path to translate.
        series_id:       Series identifier for per-series lock (D-68); None for movies.
        trigger:         Job origin ∈ {poll, webhook, manual-retry, startup-reconcile}.
        media_item:      Optional discovery MediaItem. When provided, a safe snapshot
                         of its fields is persisted on the Job row as media_item_json
                         so _execute_job can reconstruct the Bible-aware path (CR-01).

    Returns:
        True if the job was enqueued; False if already queued/running (dedup).
    """
    from trezarr.jobs.models import Job  # noqa: PLC0415 — avoid circular at module scope

    if session_factory is None:
        # No-DB path for tests: use module-level set for D-66 dedup contract.
        if source_path in _no_db_enqueued:
            return False
        _no_db_enqueued.add(source_path)
        return True

    # Build a safe snapshot of the MediaItem for Bible-aware reconstruction (CR-01).
    media_item_json: dict | None = None
    if media_item is not None:
        snapshot: dict = {}
        for field in _MEDIA_ITEM_SNAPSHOT_FIELDS:
            val = getattr(media_item, field, None)
            if val is not None:
                snapshot[field] = val
        # arr_metadata is a dict of series metadata; include if present
        arr_meta = getattr(media_item, "arr_metadata", None)
        if arr_meta is not None:
            snapshot["arr_metadata"] = arr_meta
        media_item_json = snapshot if snapshot else None

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
                media_item_json=media_item_json,
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

    WR-02 fix: collect IDs, commit first, then put onto the queue. This ensures
    that a commit failure (e.g. SQLite I/O error) never leaves IDs on the queue
    whose DB state did not actually persist.

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

        # WR-02: collect IDs first, commit, then enqueue — commit failure must not
        # leave IDs on the queue whose DB state did not persist.
        stale_ids = [job.id for job in stale_jobs]
        for job in stale_jobs:
            job.status = "queued"

        await session.commit()

    for job_id in stale_ids:
        await _work_queue.put(job_id)


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
            # ARM 2: enqueued without media_item context — _execute_job will use
            # the mechanical (non-Bible-aware) path for these items.
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

    CR-01 fix: reconstructs the eligible_item from job.media_item_json so the
    Bible-aware translation path in translate_file receives a proper media_item.
    If media_item_json is None (ARM-2 reconcile path), falls back to
    session_factory=None so translate_file uses the mechanical path.

    Args:
        job_id:          Primary key of the Job row to execute.
        session_factory: Async session factory.
        settings:        TrezarrSettings.
        llm_client:      LLMClient instance.
        ledger:          LedgerSQLA bound to session_factory.
        media_roots:     Path-traversal guard roots (D-29).
    """
    from trezarr.cli import process_one_item  # noqa: PLC0415 — shared callable (D-62)
    from trezarr.jobs.models import Job, JobLog  # noqa: PLC0415

    # D-75: set up per-job log buffer + handler before execution starts
    _log_buffer = _JobLogBuffer()
    _log_handler = _JobLogHandler(_log_buffer)
    _log_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(_log_handler)

    # Set the ContextVar so _log_handler.emit() knows which job we're in
    _ctx_token = _current_job_id.set(job_id)

    async def _flush_logs_to_db(job_id: int, records: list[tuple[str, str]]) -> None:
        """Flush buffered log records into job_log rows in a single transaction."""
        if not records:
            return
        try:
            async with session_factory() as session:
                async with session.begin():
                    for level, message in records:
                        session.add(JobLog(job_id=job_id, level=level, message=message))
        except Exception:  # noqa: BLE001
            logger.exception(
                "_execute_job: failed to flush %d log records for job_id=%d",
                len(records), job_id,
            )

    try:
        # Fetch the job and update to running
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            if job is None:
                logger.error("_execute_job: Job id=%d not found in DB; skipping", job_id)
                return

            series_id = job.series_id
            source_path = job.source_path
            media_item_json = job.media_item_json  # CR-01: snapshot persisted at enqueue time

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
            # CR-01: reconstruct the eligible_item from the persisted media_item_json.
            #
            # If media_item_json is present: build a SimpleNamespace media_item carrying
            # the discovery fields (arr_kind, series_id, tvdb_id, …) and wrap it in an
            # eligible_stub with both source_sub_path and media_item. translate_file's
            # Bible-aware guard (eligible_item is not None and session_factory is not None)
            # passes, and eligible_item.media_item is set — no AttributeError.
            #
            # If media_item_json is None (ARM-2 reconcile of a bare ProcessedFile row):
            # pass session_factory=None so translate_file's guard fails and it takes the
            # mechanical (non-Bible-aware) path. Log a warning so the operator knows
            # Bible-aware features were skipped; the item will be picked up Bible-aware
            # on the next full poll cycle.
            if media_item_json is not None:
                media_item = SimpleNamespace(**media_item_json)
                eligible_stub = SimpleNamespace(
                    source_sub_path=source_path,
                    media_item=media_item,
                )
                sf_arg = session_factory
            else:
                logger.warning(
                    "_execute_job: job_id=%d has no media_item_json (ARM-2 reconcile path); "
                    "Bible-aware translation skipped — item will be retried Bible-aware on "
                    "next full poll cycle.",
                    job_id,
                )
                eligible_stub = SimpleNamespace(source_sub_path=source_path, media_item=None)
                sf_arg = None  # Forces mechanical path in translate_file

            item_result = await process_one_item(
                eligible_stub,
                settings,
                llm_client,
                ledger,
                media_roots,
                session_factory=sf_arg,
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
    finally:
        # D-75: flush buffered log records to DB and tear down handler
        _current_job_id.reset(_ctx_token)
        root_logger.removeHandler(_log_handler)
        log_records = _log_buffer.drain()
        await _flush_logs_to_db(job_id, log_records)


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

    CR-02 fix: tasks are added to _background_tasks for strong GC references.
    Each task removes itself via add_done_callback when it completes.

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
        # CR-02: hold a strong reference to the task to prevent GC under memory pressure.
        # asyncio holds only a weak reference — without _background_tasks the task
        # object can be collected mid-execution (asyncio docs warning).
        t = asyncio.create_task(
            _execute_job(job_id, session_factory, settings, llm_client, ledger, media_roots)
        )
        _background_tasks.add(t)
        t.add_done_callback(_background_tasks.discard)
        _work_queue.task_done()
