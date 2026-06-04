---
quick_id: 260604-gfl
slug: fix-daemon-crash-loop-job-dedup
created: 2026-06-04
status: in-progress
---

# Quick Task 260604-gfl: Fix P0 daemon startup crash-loop chain

## Problem (verified in code 2026-06-04)

A four-link chain that bricks the daemon UI on restart, actively driven by the live deepseek setup:

1. **Orphan-sentinel quarantine** (separate task) — weak model hallucinates `<<TN>>` → every attempt quarantines.
2. **B2 — enqueue dedup incomplete**: `enqueue_job` (worker.py:195-203) only skips `queued`/`running`. A terminal `failed`/`quarantined` job does not match, so each poll creates a NEW Job row for the same `source_path`.
3. **B3 — no poller backoff**: `poll_and_enqueue` (scheduler.py) re-enqueues an item every cycle (a quarantined file produced no `.vi` sidecar → stays eligible forever). Duplicate terminal Job rows accumulate. `Job.source_path` is indexed but not unique.
4. **B1 — crash on restart**: `reconcile_in_progress_from_ledger` (worker.py:313) does `select(Job).where(source_path==…, status IN (…,failed,quarantined)).scalar_one_or_none()`. With >1 matching row → `MultipleResultsFound` → FastAPI lifespan crashes → restart loop → UI down.

## Fix

- **B1 (crash, REQUIRED):** `worker.py:313` only uses `matching_job` for an `is None` existence check — replace `scalar_one_or_none()` with `.scalars().first()` so it is robust to ≥1 matching rows. Never raises.
- **B2+B3 (root cause):** add an **auto-retry cap** in `enqueue_job`. For automatic triggers (`poll`/`webhook`), count terminal (`failed`/`quarantined`) Job rows for `source_path`; if `>= max_auto_attempts`, skip (return False, log once). `manual` / `manual-retry` / `startup-reconcile` bypass the cap. This bounds duplicate-row accumulation AND stops the budget bleed at the single chokepoint every trigger flows through.
- New config field `job_max_auto_attempts: int = 5`. `poll_and_enqueue` threads `getattr(settings, "job_max_auto_attempts", 5)` into `enqueue_job`; the webhook path reuses `poll_and_enqueue` so it is covered.

## Invariants preserved
- Single `LLMClient._semaphore` remains the only global LLM cap (no new semaphore).
- Per-series `asyncio.Lock` ordering unchanged.
- D-66 queued/running dedup unchanged; the cap is additive.
- No Job UNIQUE constraint (multiple jobs per source_path over time is legitimate — retries / re-translation upgrades).

## Tasks
1. **TDD RED** — `tests/web/conftest.py` (re-export db fixtures) + `tests/web/test_worker_dedup_reconcile.py`: (a) reconcile survives duplicate terminal jobs (no MultipleResultsFound); (b) reconcile still re-enqueues a true orphan; (c) `enqueue_job(trigger=poll)` capped after N terminal rows; (d) `manual-retry` bypasses cap; (e) below-cap still enqueues.
2. **GREEN** — config field + worker.py B1 `.first()` + `enqueue_job` cap + scheduler.py thread-through.
3. Run full `uv run pytest`; commit atomically.

## must_haves
- truths:
  - reconcile_in_progress_from_ledger does not raise MultipleResultsFound when >1 Job matches a ledger source_path
  - reconcile still re-enqueues a ProcessedFile in_progress row that has NO matching Job
  - enqueue_job with an automatic trigger returns False once `job_max_auto_attempts` terminal jobs exist for source_path
  - manual / manual-retry / startup-reconcile triggers bypass the cap
  - no new asyncio.Semaphore introduced; per-series Lock + single LLM semaphore intact
- artifacts: trezarr/web/worker.py, trezarr/web/scheduler.py, trezarr/config.py, tests/web/test_worker_dedup_reconcile.py, tests/web/conftest.py
