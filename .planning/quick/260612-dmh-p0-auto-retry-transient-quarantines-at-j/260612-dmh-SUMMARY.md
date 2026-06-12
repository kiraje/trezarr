---
phase: quick-260612-dmh
plan: "01"
subsystem: worker/job-queue
tags: [p0, stability, auto-retry, tdd]
dependency_graph:
  requires: []
  provides: [transient-quarantine-auto-retry]
  affects: [trezarr/web/worker.py, trezarr/config.py, trezarr/jobs/models.py, alembic]
tech_stack:
  added: []
  patterns: [asyncio.create_task delayed re-enqueue, TRANSIENT allowlist prefix match]
key_files:
  created:
    - tests/web/test_worker_transient_retry.py
    - alembic/versions/0005_job_trigger_auto_retry.py
  modified:
    - trezarr/config.py
    - trezarr/web/worker.py
    - trezarr/jobs/models.py
decisions:
  - "job.attempts (existing column) used as the retry counter — no new DB column"
  - "trigger='auto-retry' added to ck_job_trigger via Alembic 0005 (batch_alter_table recreate=always)"
  - "_TRANSIENT_QUARANTINE_PREFIXES uses substring prefix match — broad 'Parsed ' is intentional (T-dmh-03 accepted)"
  - "Delayed re-enqueue via asyncio.create_task + _background_tasks (strong GC reference, CR-02 pattern)"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-12"
  tasks_completed: 2
  files_changed: 5
---

# Phase quick-260612-dmh Plan 01: Transient Quarantine Auto-Retry Summary

**One-liner:** Job-level auto-retry for BatchValidationError parse-contract quarantines (Empty/whitespace-only, Missing line, Parsed N mismatch) via delayed asyncio.create_task re-enqueue, capped at job_auto_retry_max=2, with Alembic 0005 extending ck_job_trigger to include "auto-retry".

## What Was Built

P0 stability fix eliminating manual intervention for the transient deepseek partial-response quarantine class. Live evidence: MK E02 quarantined 4x with "Empty/whitespace-only text for line [N] in LLM response" requiring manual /api/jobs/{id}/retry each time. Unattended overnight runs died on the first transient.

### Components

**trezarr/config.py** — two new fields:
- `job_auto_retry_max: int = 2` — max auto-retries per transient quarantine event
- `job_auto_retry_delay_s: float = 30.0` — delay before re-enqueue (seconds)

**trezarr/web/worker.py** — three additions:
- `_TRANSIENT_QUARANTINE_PREFIXES` constant: `("Empty/whitespace-only text for line [", "Missing line [", "Parsed ")`
- `_is_transient_quarantine(reason)` helper: prefix match against the allowlist
- Post-quarantine auto-retry hook in `_execute_job`: fires when `item_result.status == "quarantined"` + TRANSIENT reason + budget remaining; schedules `_delayed_reenqueue` via `asyncio.create_task` + `_background_tasks` (CR-02 pattern)

**trezarr/jobs/models.py** — `ck_job_trigger` CHECK constraint updated to include `'auto-retry'`

**alembic/versions/0005_job_trigger_auto_retry.py** — migration adding `'auto-retry'` to `ck_job_trigger` (batch_alter_table recreate="always", reversible, down_revision="0004")

**tests/web/test_worker_transient_retry.py** — 7 TDD tests (RED → GREEN)

## TDD Gate Compliance

- RED commit: `e34d284` — `test(quick-260612-dmh): add failing tests for transient quarantine auto-retry`
- GREEN commit: `c21eac7` — `feat(quick-260612-dmh): implement transient quarantine auto-retry (P0 stability)`

Gate sequence: RED (4 failures + 3 absence-assertions pass) → GREEN (7/7 pass). The 3 absence-assertion tests (non-transient does not retry, max=0 disables, exhausted stops) correctly passed in RED since they test the absence of a feature that didn't exist.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock for asyncio.create_task needed to run the coroutine inside the patch context**
- **Found during:** Task 2 (GREEN verification)
- **Issue:** `test_transient_quarantine_triggers_auto_retry` patched `asyncio.create_task` to close the coroutine immediately, preventing `enqueue_job` from being called and making the test unverifiable. Running coros after the `with patch(...)` context exited caused a TypeError because `enqueue_job` was unpatched again.
- **Fix:** Captured coros in a list, ran them inside the `with patch(...)` block (while patches are still active), and also patched `asyncio.sleep` to skip the delay in worker.py via `trezarr.web.worker.asyncio.sleep`.
- **Files modified:** `tests/web/test_worker_transient_retry.py`
- **Commit:** `c21eac7` (bundled with GREEN implementation)

## Known Stubs

None — all behavior fully implemented and wired.

## Threat Surface Scan

No new network endpoints or auth paths introduced. The trigger string "auto-retry" flows through the existing enqueue_job → DB INSERT path protected by the ck_job_trigger CHECK constraint (T-dmh-02 mitigated by migration 0005).

## Self-Check: PASSED

- tests/web/test_worker_transient_retry.py: FOUND
- alembic/versions/0005_job_trigger_auto_retry.py: FOUND
- trezarr/config.py job_auto_retry_max: FOUND
- trezarr/web/worker.py _TRANSIENT_QUARANTINE_PREFIXES: FOUND
- RED commit e34d284: verified
- GREEN commit c21eac7: verified
- Full suite: 612 passed (605 baseline + 7 new)
