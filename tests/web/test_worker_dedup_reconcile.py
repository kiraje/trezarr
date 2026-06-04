"""Regression tests for the P0 daemon startup crash-loop chain (quick task 260604-gfl).

Verifies, against a real temp-file SQLite DB (full Alembic migration):

  B1  reconcile_in_progress_from_ledger does NOT raise sqlalchemy
      MultipleResultsFound when >1 Job row matches one ledger entry's
      source_path (the crash that bricked the daemon UI on restart).
  B1  reconcile still re-enqueues a true orphan (ProcessedFile in_progress with
      NO matching Job) — the fix must not break ARM-2's actual purpose.
  B2/B3  enqueue_job auto-retry cap: an automatic trigger (poll/webhook) is
      skipped once `job_max_auto_attempts` terminal (failed/quarantined) Job
      rows exist for a source_path — stopping unbounded duplicate-row
      accumulation and the LLM-budget bleed at the single chokepoint.
      manual / manual-retry / startup-reconcile triggers bypass the cap.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

from sqlalchemy import func, select


async def _add(session_factory, *rows):
    async with session_factory() as session:
        async with session.begin():
            for r in rows:
                session.add(r)


# ── B1: crash-loop regression ──────────────────────────────────────────────────


async def test_reconcile_from_ledger_survives_duplicate_terminal_jobs(session_factory):
    """B1: >1 terminal Job per ledger source_path must NOT crash reconcile.

    Before the fix, reconcile_in_progress_from_ledger used scalar_one_or_none()
    which raised MultipleResultsFound on FastAPI startup → restart loop → UI down.
    With duplicate terminal jobs present, reconcile must complete cleanly and,
    because a matching Job already exists, must NOT re-enqueue the orphan arm.
    """
    from trezarr.bible.models import ProcessedFile  # noqa: PLC0415
    from trezarr.jobs.models import Job  # noqa: PLC0415
    from trezarr.web.worker import reconcile_in_progress_from_ledger  # noqa: PLC0415

    src = "/media/Show.S01E06.zh.srt"
    await _add(
        session_factory,
        ProcessedFile(source_path=src, status="in_progress", content_hash="abc123"),
        Job(source_path=src, status="quarantined", trigger="poll"),
        Job(source_path=src, status="quarantined", trigger="poll"),
    )

    # The regression: this call must not raise MultipleResultsFound.
    await reconcile_in_progress_from_ledger(session_factory)

    # A matching Job exists → the orphan arm must NOT create a startup-reconcile job.
    async with session_factory() as session:
        cnt = (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.trigger == "startup-reconcile")
            )
        ).scalar_one()
    assert cnt == 0, "reconcile must not re-enqueue when a matching Job already exists"


async def test_reconcile_from_ledger_reenqueues_true_orphan(session_factory):
    """B1 guard: a ProcessedFile in_progress with NO matching Job is still re-enqueued.

    Ensures the crash fix (.first() instead of scalar_one_or_none) does not break
    ARM-2's real purpose — a genuine orphan must produce one startup-reconcile job.
    """
    from trezarr.bible.models import ProcessedFile  # noqa: PLC0415
    from trezarr.jobs.models import Job  # noqa: PLC0415
    from trezarr.web.worker import reconcile_in_progress_from_ledger  # noqa: PLC0415

    src = "/media/Orphan.S01E01.en.srt"
    await _add(
        session_factory,
        ProcessedFile(source_path=src, status="in_progress", content_hash="def456"),
    )

    await reconcile_in_progress_from_ledger(session_factory)

    async with session_factory() as session:
        rows = (
            await session.execute(select(Job).where(Job.source_path == src))
        ).scalars().all()
    assert len(rows) == 1, "orphan in_progress row must be re-enqueued exactly once"
    assert rows[0].trigger == "startup-reconcile"
    assert rows[0].status == "queued"


# ── B2/B3: auto-retry cap ────────────────────────────────────────────────────────


async def test_enqueue_poll_capped_after_terminal_failures(session_factory):
    """B2/B3: an automatic (poll) trigger is skipped once the cap of terminal jobs exists."""
    from trezarr.jobs.models import Job  # noqa: PLC0415
    from trezarr.web.worker import enqueue_job  # noqa: PLC0415

    src = "/media/Capped.S01E01.zh.srt"
    cap = 3
    await _add(
        session_factory,
        *[Job(source_path=src, status="quarantined", trigger="poll") for _ in range(cap)],
    )

    enqueued = await enqueue_job(
        session_factory, src, series_id=10, trigger="poll", max_auto_attempts=cap
    )
    assert enqueued is False, "poll trigger must be capped after N terminal failures"

    async with session_factory() as session:
        queued = (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.source_path == src, Job.status == "queued")
            )
        ).scalar_one()
    assert queued == 0, "no new queued Job row may be created once capped"


async def test_enqueue_manual_retry_bypasses_cap(session_factory):
    """B2/B3: manual-retry must bypass the auto-retry cap (explicit human action).

    Note: this validates the _AUTO_TRIGGERS exclusion contract directly. The
    production retry route (routes/jobs.py) re-enqueues by mutating the existing
    Job row in place (not via enqueue_job), so it is also unaffected by the cap;
    this test asserts the cap-exclusion logic, not that production code path.
    """
    from trezarr.jobs.models import Job  # noqa: PLC0415
    from trezarr.web.worker import enqueue_job  # noqa: PLC0415

    src = "/media/Manual.S01E01.zh.srt"
    cap = 3
    await _add(
        session_factory,
        *[Job(source_path=src, status="quarantined", trigger="poll") for _ in range(cap)],
    )

    enqueued = await enqueue_job(
        session_factory, src, series_id=10, trigger="manual-retry", max_auto_attempts=cap
    )
    assert enqueued is True, "manual-retry must bypass the cap"

    async with session_factory() as session:
        queued = (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.source_path == src, Job.status == "queued")
            )
        ).scalar_one()
    assert queued == 1, "manual-retry must create a fresh queued Job row"


async def test_enqueue_poll_below_cap_still_enqueues(session_factory):
    """B2/B3: below the cap, an automatic trigger still enqueues normally."""
    from trezarr.jobs.models import Job  # noqa: PLC0415
    from trezarr.web.worker import enqueue_job  # noqa: PLC0415

    src = "/media/UnderCap.S01E01.zh.srt"
    cap = 5
    await _add(
        session_factory,
        *[Job(source_path=src, status="failed", trigger="poll") for _ in range(cap - 1)],
    )

    enqueued = await enqueue_job(
        session_factory, src, series_id=10, trigger="poll", max_auto_attempts=cap
    )
    assert enqueued is True, "below the cap, poll must still enqueue"


async def test_job_max_auto_attempts_config_default():
    """The new config field defaults to a finite cap (bounds duplicate accumulation)."""
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    settings = TrezarrSettings(llm_api_key="test-key")
    assert isinstance(settings.job_max_auto_attempts, int)
    assert settings.job_max_auto_attempts >= 1
