"""Tests for P0 transient-quarantine auto-retry (260612-dmh).

Verifies that _execute_job auto-retries a job when it quarantines due to a
TRANSIENT BatchValidationError parse-contract reason (Empty/whitespace-only,
Missing line, Parsed N lines but expected M), and does NOT auto-retry for
gate-check content-defect quarantines.

TDD RED phase — all tests must FAIL before the implementation is added.
asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch


def _make_session_factory(fake_job):
    """Build the mock_session_factory pattern matching test_worker.py."""
    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=fake_job)
    mock_session.commit = AsyncMock()
    # session.begin() as async context manager (used in _flush_logs_to_db)
    mock_begin_ctx = MagicMock()
    mock_begin_ctx.__aenter__ = AsyncMock(return_value=None)
    mock_begin_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session.begin = MagicMock(return_value=mock_begin_ctx)

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_session_ctx)


def _make_settings(job_auto_retry_max=2, job_auto_retry_delay_s=30.0):
    """Build a settings MagicMock with the auto-retry knobs."""
    settings = MagicMock()
    settings.job_auto_retry_max = job_auto_retry_max
    settings.job_auto_retry_delay_s = job_auto_retry_delay_s
    return settings


def _make_fake_job(attempts=0):
    """Build a fake Job MagicMock for use with session.get()."""
    fake_job = MagicMock()
    fake_job.series_id = None
    fake_job.source_path = "/test/ep.en.srt"
    fake_job.media_item_json = None  # mechanical path — simpler for these tests
    fake_job.status = "queued"
    fake_job.attempts = attempts
    return fake_job


async def test_transient_quarantine_triggers_auto_retry():
    """TRANSIENT reason 'Empty/whitespace-only...' must schedule a delayed re-enqueue.

    When _execute_job produces item_result.status='quarantined' with a TRANSIENT
    reason and job_auto_retry_max=2, worker must:
    - call enqueue_job with trigger='auto-retry'
    - schedule it via asyncio.create_task
    - NOT exceed the budget (job.attempts=0, max=2 → budget remains)
    """
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    fake_job = _make_fake_job(attempts=0)
    mock_session_factory = _make_session_factory(fake_job)
    settings = _make_settings(job_auto_retry_max=2, job_auto_retry_delay_s=30.0)

    async def fake_process_one_item(
        eligible_item, s, llm_client, ledger, media_roots, *, session_factory=None
    ):
        result = MagicMock()
        result.status = "quarantined"
        result.reason = "Empty/whitespace-only text for line [1] in LLM response"
        return result

    # Patch enqueue_job as an AsyncMock to capture calls without hitting the DB
    mock_enqueue = AsyncMock(return_value=True)

    # Capture the coroutines scheduled via asyncio.create_task so we can
    # run them synchronously and verify enqueue_job is called inside them.
    captured_coros: list = []

    def fake_create_task(coro):
        captured_coros.append(coro)
        # Return a MagicMock sentinel (task object) — we will run the coros manually
        return MagicMock()

    with (
        patch("trezarr.cli.process_one_item", fake_process_one_item),
        patch("trezarr.web.worker.enqueue_job", mock_enqueue),
        patch("trezarr.web.worker.asyncio.create_task", fake_create_task),
        patch("trezarr.web.worker.asyncio.sleep", AsyncMock(return_value=None)),
    ):
        await worker_mod._execute_job(
            job_id=10,
            session_factory=mock_session_factory,
            settings=settings,
            llm_client=MagicMock(),
            ledger=MagicMock(),
            media_roots=[],
        )

        # asyncio.create_task must have been called (the delayed re-enqueue was scheduled)
        assert captured_coros, (
            "asyncio.create_task must be called to schedule the delayed re-enqueue"
        )

        # Run the captured coroutine(s) inside the patch context so enqueue_job mock is active
        for coro in captured_coros:
            await coro

    # enqueue_job must have been called with trigger="auto-retry"
    assert mock_enqueue.called, (
        "enqueue_job must be called when TRANSIENT quarantine fires with budget remaining"
    )
    call_kwargs = mock_enqueue.call_args
    assert call_kwargs is not None
    # trigger="auto-retry" must appear either as positional or keyword arg
    args, kwargs = call_kwargs
    trigger_val = kwargs.get("trigger") or (args[3] if len(args) > 3 else None)
    assert trigger_val == "auto-retry", (
        f"enqueue_job must be called with trigger='auto-retry', got trigger={trigger_val!r}"
    )


async def test_non_transient_quarantine_does_not_retry():
    """Gate-check quarantine reason must NOT trigger auto-retry.

    'CJK script leaked into translated cue' is a Check 1-12 content-defect
    quarantine — it must never be auto-retried (burns 20+ min, same outcome;
    IMP-02b handles it in-run).
    """
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    fake_job = _make_fake_job(attempts=0)
    mock_session_factory = _make_session_factory(fake_job)
    settings = _make_settings(job_auto_retry_max=2)

    async def fake_process_one_item(
        eligible_item, s, llm_client, ledger, media_roots, *, session_factory=None
    ):
        result = MagicMock()
        result.status = "quarantined"
        result.reason = "CJK script leaked into translated cue"
        return result

    mock_enqueue = AsyncMock(return_value=True)

    with (
        patch("trezarr.cli.process_one_item", fake_process_one_item),
        patch("trezarr.web.worker.enqueue_job", mock_enqueue),
    ):
        await worker_mod._execute_job(
            job_id=11,
            session_factory=mock_session_factory,
            settings=settings,
            llm_client=MagicMock(),
            ledger=MagicMock(),
            media_roots=[],
        )

    # enqueue_job must NOT have been called with trigger="auto-retry"
    for call in mock_enqueue.call_args_list:
        args, kwargs = call
        trigger_val = kwargs.get("trigger") or (args[3] if len(args) > 3 else None)
        assert trigger_val != "auto-retry", (
            "enqueue_job must NOT be called with trigger='auto-retry' for non-transient quarantine"
        )


async def test_missing_line_prefix_is_transient():
    """'Missing line [N] in LLM response' must match the TRANSIENT allowlist.

    This is a BatchValidationError parse-contract failure — the LLM returned a
    numbered list missing one of the required line indices.
    """
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    # Test the helper directly
    assert hasattr(worker_mod, "_is_transient_quarantine"), (
        "_is_transient_quarantine helper must exist in worker module"
    )
    reason = "Missing line [3] in LLM response (expected 8 lines)"
    assert worker_mod._is_transient_quarantine(reason), (
        f"_is_transient_quarantine must return True for {reason!r}"
    )


async def test_parsed_lines_mismatch_is_transient():
    """'Parsed N lines but expected M' must match the TRANSIENT allowlist.

    This is a BatchValidationError parse-contract failure — the LLM returned
    a different number of numbered lines than expected.
    """
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    assert hasattr(worker_mod, "_is_transient_quarantine"), (
        "_is_transient_quarantine helper must exist in worker module"
    )
    reason = "Parsed 4 lines but expected 8 (expected_count=8)"
    assert worker_mod._is_transient_quarantine(reason), (
        f"_is_transient_quarantine must return True for {reason!r}"
    )


async def test_auto_retry_max_zero_disables():
    """job_auto_retry_max=0 must disable auto-retry entirely (prod-safe off switch).

    When max=0, even a TRANSIENT quarantine must NOT schedule a re-enqueue.
    """
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    fake_job = _make_fake_job(attempts=0)
    mock_session_factory = _make_session_factory(fake_job)
    settings = _make_settings(job_auto_retry_max=0)

    async def fake_process_one_item(
        eligible_item, s, llm_client, ledger, media_roots, *, session_factory=None
    ):
        result = MagicMock()
        result.status = "quarantined"
        result.reason = "Empty/whitespace-only text for line [1] in LLM response"
        return result

    mock_enqueue = AsyncMock(return_value=True)

    with (
        patch("trezarr.cli.process_one_item", fake_process_one_item),
        patch("trezarr.web.worker.enqueue_job", mock_enqueue),
    ):
        await worker_mod._execute_job(
            job_id=12,
            session_factory=mock_session_factory,
            settings=settings,
            llm_client=MagicMock(),
            ledger=MagicMock(),
            media_roots=[],
        )

    for call in mock_enqueue.call_args_list:
        args, kwargs = call
        trigger_val = kwargs.get("trigger") or (args[3] if len(args) > 3 else None)
        assert trigger_val != "auto-retry", (
            "enqueue_job must NOT be called with trigger='auto-retry' when job_auto_retry_max=0"
        )


async def test_auto_retry_warning_logged(caplog):
    """TRANSIENT quarantine with max=2 must emit a WARNING log containing 'job_auto_retry' and 'attempt=1/2'.

    The WARNING log is the operator's signal that an auto-retry was scheduled.
    """
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    fake_job = _make_fake_job(attempts=0)
    mock_session_factory = _make_session_factory(fake_job)
    settings = _make_settings(job_auto_retry_max=2, job_auto_retry_delay_s=30.0)

    async def fake_process_one_item(
        eligible_item, s, llm_client, ledger, media_roots, *, session_factory=None
    ):
        result = MagicMock()
        result.status = "quarantined"
        result.reason = "Empty/whitespace-only text for line [2] in LLM response"
        return result

    mock_enqueue = AsyncMock(return_value=True)

    def fake_create_task_log(coro):
        # Close the coro to avoid ResourceWarning; we only need the log assertion
        coro.close()
        return MagicMock()

    with (
        patch("trezarr.cli.process_one_item", fake_process_one_item),
        patch("trezarr.web.worker.enqueue_job", mock_enqueue),
        patch("trezarr.web.worker.asyncio.create_task", fake_create_task_log),
        caplog.at_level(logging.WARNING, logger="trezarr.web.worker"),
    ):
        await worker_mod._execute_job(
            job_id=13,
            session_factory=mock_session_factory,
            settings=settings,
            llm_client=MagicMock(),
            ledger=MagicMock(),
            media_roots=[],
        )

    # Verify WARNING log with required tokens
    warning_messages = [
        r.message for r in caplog.records if r.levelno >= logging.WARNING
    ]
    auto_retry_logs = [m for m in warning_messages if "job_auto_retry" in m]
    assert auto_retry_logs, (
        f"Expected a WARNING log containing 'job_auto_retry'; got: {warning_messages}"
    )
    attempt_logs = [m for m in auto_retry_logs if "attempt=1/2" in m]
    assert attempt_logs, (
        f"Expected WARNING log with 'attempt=1/2'; got auto_retry_logs: {auto_retry_logs}"
    )


async def test_auto_retry_exhausted_stops():
    """When job.attempts already >= job_auto_retry_max, no further re-enqueue is scheduled.

    job.attempts=2 with max=2 means the budget is exhausted — the auto-retry hook
    must skip the re-enqueue entirely (not re-add to the queue infinitely).
    """
    from trezarr.web import worker as worker_mod  # noqa: PLC0415

    # Set attempts=2 (already used both auto-retry slots)
    fake_job = _make_fake_job(attempts=2)
    mock_session_factory = _make_session_factory(fake_job)
    settings = _make_settings(job_auto_retry_max=2)

    async def fake_process_one_item(
        eligible_item, s, llm_client, ledger, media_roots, *, session_factory=None
    ):
        result = MagicMock()
        result.status = "quarantined"
        result.reason = "Empty/whitespace-only text for line [1] in LLM response"
        return result

    mock_enqueue = AsyncMock(return_value=True)

    with (
        patch("trezarr.cli.process_one_item", fake_process_one_item),
        patch("trezarr.web.worker.enqueue_job", mock_enqueue),
    ):
        await worker_mod._execute_job(
            job_id=14,
            session_factory=mock_session_factory,
            settings=settings,
            llm_client=MagicMock(),
            ledger=MagicMock(),
            media_roots=[],
        )

    for call in mock_enqueue.call_args_list:
        args, kwargs = call
        trigger_val = kwargs.get("trigger") or (args[3] if len(args) > 3 else None)
        assert trigger_val != "auto-retry", (
            "enqueue_job must NOT be called with trigger='auto-retry' when auto-retry budget is exhausted"
        )
