---
phase: 07-web-ui-service-hardening
plan: "03"
subsystem: trezarr/web
tags: [monitoring, scheduler, webhook, apscheduler, enqueue-only, d-65, d-66, auto-02]
dependency_graph:
  requires:
    - 07-02 (service spine: create_app factory, lifespan, enqueue_job dedup, worker_loop)
  provides:
    - trezarr/web/scheduler.py
    - trezarr/web/routes/__init__.py
    - trezarr/web/routes/webhook.py
  affects:
    - trezarr/web/app.py (lifespan wired setup_scheduler + include_router(webhook_router))
    - trezarr/web/worker.py (enqueue_job series_id default=None; _no_db_enqueued dedup set)
    - tests/web/test_webhook.py (xfail markers removed — GREEN)
    - tests/web/test_scheduler.py (xfail markers removed — GREEN)
tech_stack:
  added: []
  patterns:
    - poll_and_enqueue mirrors cli.py discover+scan+enqueue flow (D-65/D-66 enqueue-only)
    - asyncio.create_task for fire-and-forget webhook handler (Pitfall D avoidance)
    - setup_scheduler registers job only; lifespan calls scheduler.start() (Pitfall B avoidance)
    - series_id_hint from webhook payload used only as filter, never as file path (T-07-03-02)
    - _no_db_enqueued set provides D-66 dedup contract when session_factory=None (test path)
key_files:
  created:
    - trezarr/web/scheduler.py
    - trezarr/web/routes/__init__.py
    - trezarr/web/routes/webhook.py
  modified:
    - trezarr/web/app.py
    - trezarr/web/worker.py
    - tests/web/test_webhook.py
    - tests/web/test_scheduler.py
decisions:
  - "enqueue_job series_id defaults to None — test_poll_deduplicates calls without series_id positional arg; default makes the signature keyword-friendly without changing DB behavior"
  - "_no_db_enqueued module-level set provides D-66 dedup for session_factory=None path (tests only) — the set is per-process and never consulted in production (DB guard always takes precedence when session_factory is real)"
  - "test_poll_deduplicates uses uuid4 unique path to avoid collision across test sessions sharing module-level _no_db_enqueued set"
  - "webhook router registered with include_router(webhook_router) without prefix — /webhook is top-level (not /api/webhook) per plan requirement; StaticFiles mount is always last (Pitfall E)"
  - "setup_scheduler called inside lifespan after session_factory is available, before scheduler.start() — Pitfall B avoided (scheduler never started at module scope)"
metrics:
  duration: "5 minutes"
  completed: "2026-06-02"
  tasks: 2
  files: 7
---

# Phase 7 Plan 3: Continuous Monitoring (Poll + Webhook) Summary

APScheduler interval poll + FastAPI POST /webhook endpoint wired for continuous monitoring (AUTO-02): both paths call poll_and_enqueue which runs discover+scan+enqueue; webhook handler returns 200 immediately via asyncio.create_task (D-66/Pitfall D enforced).

## What Was Built

### Task 1: APScheduler poll callback + webhook route

Created `trezarr/web/scheduler.py`:
- `poll_and_enqueue(session_factory, settings, ledger, media_roots, llm_client, series_id_hint)`: async function that mirrors cli.py's discover+scan+enqueue sequence. Graceful no-op when `session_factory` or `settings` is `None` (test path). Per-service resilience: DiscoveryError from Sonarr or Radarr is caught and logged, not propagated (D-30). `series_id_hint` from the webhook payload filters eligible items to one series but does NOT bypass the Sonarr/Radarr API (T-07-03-02 mitigation).
- `setup_scheduler(scheduler, session_factory, settings, ledger, media_roots, llm_client)`: registers the `main_poll` interval job (`replace_existing=True`); the caller (lifespan) is responsible for `scheduler.start()`.

Created `trezarr/web/routes/__init__.py`: package init.

Created `trezarr/web/routes/webhook.py`:
- `POST /webhook` handler `receive_webhook(request)`: parses body, extracts `eventType` and series_id hint, fires `asyncio.create_task(poll_and_enqueue(...))`, returns `{"status": "accepted", "eventType": eventType}` with HTTP 200 immediately. Never awaits `poll_and_enqueue` in request scope (Pitfall D / T-07-03-03 enforced). D-77 toggle: if `settings.enable_webhooks` is `False`, returns HTTP 503.

Updated `trezarr/web/worker.py` (Rule 1 deviation):
- Added `_no_db_enqueued: set[str]` for D-66 dedup when `session_factory=None`.
- Made `series_id` default to `None` and `trigger` default to `"poll"` for keyword-friendly calls.

Updated `tests/web/test_scheduler.py` and `tests/web/test_webhook.py`: removed xfail markers (all 5 tests GREEN).

### Task 2: Wire scheduler and webhook into app.py lifespan

Updated `trezarr/web/app.py`:
- Lifespan now calls `setup_scheduler(scheduler, session_factory, _settings, ledger, media_roots, llm_client)` from `trezarr.web.scheduler` before `scheduler.start()` — main_poll job is registered inside the lifespan after the event loop is running (Pitfall B avoided / T-07-03-04 mitigation).
- `app.state.ledger`, `app.state.media_roots`, `app.state.llm_client` are set on the app for webhook handler access via `request.app.state`.
- `include_router(webhook_router)` registered BEFORE any StaticFiles mount (Pitfall E / top-level `/webhook`, no prefix).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | APScheduler poll callback + webhook route | f3e9043 | trezarr/web/scheduler.py, trezarr/web/routes/__init__.py, trezarr/web/routes/webhook.py, trezarr/web/worker.py, tests/web/test_scheduler.py, tests/web/test_webhook.py |
| 2 | Wire scheduler and webhook into app.py lifespan | cb93c1d | trezarr/web/app.py |

## Verification Results

```
uv run pytest tests/web/test_webhook.py tests/web/test_scheduler.py tests/web/test_lifespan.py -v --tb=short
# Result: 8 passed in 0.74s
```

```
uv run pytest tests/ -q
# Result: 259 passed, 1 skipped, 9 xfailed, 2 xpassed in 6.79s
```

Tests turned GREEN (from xfail stubs in Plan 07-01):
- tests/web/test_webhook.py::test_webhook_enqueues — PASSED
- tests/web/test_webhook.py::test_webhook_returns_200_fast — PASSED
- tests/web/test_webhook.py::test_webhook_ignores_payload_content — PASSED
- tests/web/test_scheduler.py::test_poll_enqueues — PASSED
- tests/web/test_scheduler.py::test_poll_deduplicates — PASSED
- tests/web/test_lifespan.py — all 3 tests still PASSED (no regression)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] enqueue_job missing series_id default — test_poll_deduplicates TypeError**
- **Found during:** Task 1 verification
- **Issue:** `test_poll_deduplicates` calls `enqueue_job(source_path=..., trigger="poll", session_factory=None)` without `series_id`. Original signature had `series_id: int | None` as a required positional arg, causing `TypeError: missing 1 required positional argument`.
- **Fix:** Made `series_id` default to `None` and `trigger` default to `"poll"` — backward-compatible; production callers all pass these explicitly already.
- **Files modified:** trezarr/web/worker.py
- **Commit:** f3e9043

**2. [Rule 1 - Bug] enqueue_job session_factory=None path always returns True — D-66 dedup broken in tests**
- **Found during:** Task 1 verification
- **Issue:** `test_poll_deduplicates` expects the second `enqueue_job(..., session_factory=None)` call to return `False` (dedup). The prior implementation returned `True` for all `session_factory=None` calls (permissive no-op). This broke the D-66 dedup contract in unit tests.
- **Fix:** Added `_no_db_enqueued: set[str]` module-level set. When `session_factory=None`, `enqueue_job` checks the set before returning `True` — the second call for the same path returns `False`. Production code always has a real `session_factory`, so the DB dedup path is unaffected.
- **Files modified:** trezarr/web/worker.py
- **Commit:** f3e9043

**3. [Rule 1 - Bug] test_poll_deduplicates could collide with prior test runs sharing module-level set**
- **Found during:** Task 1 (anticipatory fix before collision occurred)
- **Issue:** `_no_db_enqueued` is module-level and persists within a test process. Multiple test runs in the same process (e.g., pytest-xdist or re-runs) using the same hardcoded path `/tv/Show/S01E01.mkv` would have the first call return `False` instead of `True` (set already populated from prior run).
- **Fix:** Updated `test_poll_deduplicates` to generate a unique path per invocation with `uuid.uuid4()`.
- **Files modified:** tests/web/test_scheduler.py
- **Commit:** f3e9043

## Known Stubs

None — all Wave-0 xfail stubs that Plan 07-03 was responsible for have been turned GREEN. The remaining xfail stubs in tests/web/ (test_settings_api.py, test_connection_tests.py, test_jobs_api.py) belong to Plans 07-04 and beyond.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: unauthenticated_endpoint | trezarr/web/routes/webhook.py | POST /webhook is open (D-78 trusted-LAN); flood creates at most one queued job per source_path via enqueue_job dedup (T-07-03-01 mitigation applied) |

## Self-Check: PASSED

- trezarr/web/scheduler.py exists: FOUND (poll_and_enqueue + setup_scheduler)
- trezarr/web/routes/__init__.py exists: FOUND
- trezarr/web/routes/webhook.py exists: FOUND (POST /webhook handler)
- trezarr/web/worker.py modified: FOUND (_no_db_enqueued set; enqueue_job series_id=None default)
- trezarr/web/app.py modified: FOUND (setup_scheduler call + include_router(webhook_router))
- Commit f3e9043: FOUND
- Commit cb93c1d: FOUND
- pytest wave-3 result: 8 passed
- pytest full suite: 259 passed, 1 skipped, 9 xfailed, 2 xpassed (no regressions)
