---
quick_id: 260604-gfl
slug: fix-daemon-crash-loop-job-dedup
status: complete
date: 2026-06-04
commit: 44543d0
---

# Summary — Fix P0 daemon startup crash-loop chain

## What changed

**B1 — crash fix (worker.py).** `reconcile_in_progress_from_ledger` selected full
`Job` rows with `scalar_one_or_none()` purely to test existence; with >1 terminal
Job per `source_path` it raised `MultipleResultsFound` on FastAPI startup → restart
loop → UI bricked. Now `select(Job.id).where(...).first()` — robust to ≥1 rows,
identical re-enqueue semantics.

**B2/B3 — root-cause cap (worker.py + scheduler.py + config.py).** `enqueue_job`
gained `max_auto_attempts`; for automatic triggers (`poll`/`webhook`) it counts
terminal (`failed`/`quarantined`) Job rows for the `source_path` inside the existing
dedup transaction and skips once the cap is hit. `manual`/`manual-retry`/
`startup-reconcile` bypass. New `job_max_auto_attempts: int = 5`; `poll_and_enqueue`
threads it (webhook arrives relabeled as `poll`, so it's covered too). The dedup
guard's `scalar_one_or_none()` was also switched to `.first()` defensively.

## Verification
- RED reproduced the exact `MultipleResultsFound` crash; GREEN after fix.
- New `tests/web/test_worker_dedup_reconcile.py` (real temp-file SQLite + full Alembic): crash-survival, true-orphan re-enqueue, cap, manual bypass, below-cap, config default.
- Full suite: **380 passed, 1 skipped, 3 xfailed, 52 xpassed** (pre-existing). `tests/web`: 61 passed.
- pipeline-reliability-reviewer specialist: **PASS**. Invariants confirmed untouched (single LLM semaphore, per-series asyncio.Lock, no double-retry).

## Deferred (recorded as debt)
- **HIGH-1 (idempotency hardening):** the cap is a soft ceiling — no `UNIQUE` on `Job.source_path`, so concurrent poll+webhook sweeps can race the count and both insert. Post-B1-fix this only bloats the table slightly; it no longer crashes. A hard bound needs a partial-unique index + dedup-first migration (the live DB already holds duplicate rows). Documented in the `enqueue_job` docstring.

## Files
- `trezarr/web/worker.py`, `trezarr/web/scheduler.py`, `trezarr/config.py`
- `tests/web/test_worker_dedup_reconcile.py`, `tests/web/conftest.py`
