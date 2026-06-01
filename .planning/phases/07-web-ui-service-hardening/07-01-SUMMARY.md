---
phase: 07-web-ui-service-hardening
plan: "01"
subsystem: tests/web
tags: [tdd, red-scaffold, xfail, wave-0]
dependency_graph:
  requires: []
  provides:
    - tests/web/__init__.py
    - tests/web/test_lifespan.py
    - tests/web/test_settings_api.py
    - tests/web/test_connection_tests.py
    - tests/web/test_jobs_api.py
    - tests/web/test_webhook.py
    - tests/web/test_scheduler.py
    - tests/web/test_worker.py
    - tests/db/test_migrations.py (appended stub)
  affects:
    - Phase 07 automated verification feedback loop (all subsequent plans turn stubs GREEN)
tech_stack:
  added: []
  patterns:
    - xfail(strict=False) RED scaffold pattern (established in Phase 01)
    - asyncio_mode=auto (no explicit @pytest.mark.asyncio)
    - Deferred trezarr.web.* imports inside test bodies (collection-time safety)
key_files:
  created:
    - tests/web/__init__.py
    - tests/web/test_lifespan.py
    - tests/web/test_settings_api.py
    - tests/web/test_connection_tests.py
    - tests/web/test_jobs_api.py
    - tests/web/test_webhook.py
    - tests/web/test_scheduler.py
    - tests/web/test_worker.py
  modified:
    - tests/db/test_migrations.py (appended test_0002_migration_creates_job_tables xfail stub)
decisions:
  - "xfail(strict=False) with raises=(ImportError, AssertionError, TypeError) used for stubs in planned but not-yet-created modules — mirrors Phase 01 decision for pre-implementation test surfaces"
  - "test_reconcile_in_progress_from_ledger targets trezarr.web.worker.reconcile_in_progress_from_ledger (separate function from reconcile_in_progress) to make the D-67 ProcessedFile arm independently testable and discoverable"
  - "All trezarr.web.* imports deferred inside test bodies to prevent collection-time ImportError before Plan 07-02 lands"
metrics:
  duration: "~3 minutes"
  completed: "2026-06-02"
  tasks: 2
  files: 9
---

# Phase 7 Plan 1: Wave-0 RED Test Scaffold Summary

Wave-0 xfail RED stubs for all Phase-7 test surfaces covering SVC-01/SVC-02/SVC-03/SVC-04/AUTO-02/AUTO-05/D-67/D-68/D-69/D-70/D-71 with 25 stubs across 8 new tests/web/ files and 1 appended migration stub.

## What Was Built

Created the `tests/web/` package with 8 test files (24 stubs) and appended 1 stub to `tests/db/test_migrations.py`, for a total of 25 Wave-0 xfail stubs. All stubs import `trezarr.web.*` modules inside test bodies to avoid collection-time errors before implementation exists. The RED suite collects cleanly and reports 25 xfailed, 0 FAILED, 0 ERROR.

### Test Coverage by Requirement

| File | Stubs | Requirements |
|------|-------|--------------|
| test_lifespan.py | 3 | SVC-01 (startup/shutdown/serve subcommand) |
| test_settings_api.py | 3 | SVC-02, D-70 (secret masking, write-back, never-in-response) |
| test_connection_tests.py | 4 | SVC-02, D-71 (sonarr/llm connection test, no key leak) |
| test_jobs_api.py | 4 | SVC-03, SVC-04, D-74 (queue/history/logs/retry) |
| test_webhook.py | 3 | AUTO-02, D-66 (enqueue, fast-200, no-path-trust) |
| test_scheduler.py | 2 | AUTO-02, D-66 (poll-enqueues, deduplication) |
| test_worker.py | 5 | AUTO-05, D-67, D-68 (reconcile Job arm, reconcile ProcessedFile arm, per-series lock, concurrent distinct series, no second semaphore) |
| test_migrations.py (append) | 1 | D-69 (0002 migration creates job/job_log tables) |

### Critical Stub: D-67 ProcessedFile Arm

`test_reconcile_in_progress_from_ledger` in `tests/web/test_worker.py` covers the second reconcile source in D-67: a `ProcessedFile` row with `status='in_progress'` and NO matching `Job` row. This targets `trezarr.web.worker.reconcile_in_progress_from_ledger` as a distinct function from `reconcile_in_progress` (Job row arm), making both arms independently verifiable and present in the test surface per plan requirements.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create tests/web/ package with lifespan, settings, and connection-test stubs | cda5dd1 | tests/web/__init__.py, test_lifespan.py, test_settings_api.py, test_connection_tests.py |
| 2 | Create jobs, webhook, scheduler, and worker stubs; append migration stub | 3e2fc89 | test_jobs_api.py, test_webhook.py, test_scheduler.py, test_worker.py, tests/db/test_migrations.py |

## Verification Results

```
uv run pytest tests/web/ tests/db/test_migrations.py::test_0002_migration_creates_job_tables -v --tb=short
# Result: 25 xfailed in 0.38s
```

Existing migration tests: 6 PASSED (unaffected by append).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

All stubs are intentional Wave-0 xfail markers. No unintentional stubs or placeholder data flows exist. Each stub will be replaced by a real test when the corresponding implementation plan (07-02 onwards) lands.

## Threat Flags

None — this plan creates test files only. No new network endpoints, auth paths, file access patterns, or schema changes were introduced.

## Self-Check: PASSED

- tests/web/__init__.py exists: FOUND
- tests/web/test_lifespan.py exists: FOUND
- tests/web/test_settings_api.py exists: FOUND
- tests/web/test_connection_tests.py exists: FOUND
- tests/web/test_jobs_api.py exists: FOUND
- tests/web/test_webhook.py exists: FOUND
- tests/web/test_scheduler.py exists: FOUND
- tests/web/test_worker.py exists: FOUND (contains test_reconcile_in_progress_from_ledger)
- tests/db/test_migrations.py contains test_0002_migration_creates_job_tables: FOUND
- Commit cda5dd1: FOUND
- Commit 3e2fc89: FOUND
- pytest result: 25 xfailed, 0 FAILED, 0 ERROR
