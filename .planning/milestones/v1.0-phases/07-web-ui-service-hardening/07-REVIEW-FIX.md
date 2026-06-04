---
phase: 07-web-ui-service-hardening
fixed_at: 2026-06-02T00:00:00Z
review_path: .planning/phases/07-web-ui-service-hardening/07-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 7: Code Review Fix Report

**Fixed at:** 2026-06-02
**Source review:** .planning/phases/07-web-ui-service-hardening/07-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01, CR-02, WR-01, WR-02, WR-03, WR-04)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: `_EligibleItemStub` missing `media_item` — Bible-aware daemon translation always crashes

**Files modified:** `trezarr/jobs/models.py`, `alembic/versions/0002_job_queue.py`, `trezarr/web/worker.py`, `trezarr/web/scheduler.py`, `tests/web/test_worker.py`, `tests/db/test_migrations.py`
**Commit:** b5466a4
**Applied fix:** Added `media_item_json` (sa.JSON, nullable) column to the `Job` model and to the 0002 migration. `enqueue_job` now accepts an optional `media_item` parameter and snapshots its fields (`arr_kind`, `series_id`, `tvdb_id`, `tmdb_id`, `title`, `season_number`, `source_type`, `arr_metadata`) into `media_item_json` at INSERT time. `_execute_job` reads this JSON back and reconstructs a `SimpleNamespace` media_item, building a proper `eligible_stub` with both `source_sub_path` and `media_item` — letting `translate_file`'s Bible-aware guard pass without raising `AttributeError`. When `media_item_json` is None (ARM-2 reconcile path), `_execute_job` passes `session_factory=None` to force the mechanical path and logs a warning. `scheduler.py::poll_and_enqueue` now passes `media_item=eligible_item.media_item` to `enqueue_job`. Tests added for both paths; migration test asserts the column exists.

Also includes WR-02 fix (see below) since both were in worker.py.

### CR-02: `asyncio.create_task` results discarded — tasks can be silently GC'd

**Files modified:** `trezarr/web/routes/webhook.py`, `trezarr/web/worker.py` (in CR-01 commit)
**Commit:** 80c120a
**Applied fix:** Added module-level `_background_tasks: set[asyncio.Task] = set()` to both `webhook.py` and `worker.py`. Each `asyncio.create_task(...)` call now saves the result: `t = asyncio.create_task(...); _background_tasks.add(t); t.add_done_callback(_background_tasks.discard)`. This is the asyncio-documented pattern for preventing GC collection of tasks under memory pressure. Test added asserting `_background_tasks` exists and is a `set`.

### WR-01: In-flight `_execute_job` tasks not cancelled on shutdown

**Files modified:** `trezarr/web/app.py`
**Commit:** 824aa9a
**Applied fix:** The lifespan `finally` block now imports `_background_tasks` from `worker.py` as `_worker_background_tasks`. Before `scheduler.shutdown()` and `engine.dispose()`, it cancels all in-flight `_execute_job` tasks with `task.cancel()` and `await asyncio.gather(*list(_worker_background_tasks), return_exceptions=True)`. This prevents the exception storm that previously occurred when already-dispatched tasks attempted DB operations against a disposed engine.

### WR-02: ARM 1 reconcile enqueues before commit

**Files modified:** `trezarr/web/worker.py` (in CR-01 commit)
**Commit:** b5466a4
**Applied fix:** In `reconcile_in_progress` (ARM 1), rewrote the loop to collect `stale_ids = [job.id for job in stale_jobs]`, update all job statuses, call `await session.commit()`, and only THEN put IDs onto `_work_queue`. A commit failure can no longer leave IDs on the queue whose DB state did not persist.

### WR-03: `poll_interval_seconds` hot-reload silently ineffective

**Files modified:** `trezarr/web/config_writer.py`
**Commit:** 2f40c88
**Applied fix:** Added `"poll_interval_seconds"` to `RESTART_REQUIRED_FIELDS` in `config_writer.py`. The APScheduler job bakes the interval at startup (`setup_scheduler` passes `seconds=settings.poll_interval_seconds` as a fixed kwarg); a hot PUT cannot reschedule it. The UI now truthfully marks this field as requiring a restart.

### WR-04: `write_settings_to_yaml` accepts arbitrary keys

**Files modified:** `trezarr/web/config_writer.py`
**Commit:** 2f40c88
**Applied fix:** Added unknown-key filtering at the top of the `for key, value in patch.items()` loop in `write_settings_to_yaml`. `known_fields = set(type(current).model_fields.keys())` (class-level access per Pydantic V2.11+ deprecation). Unknown keys are dropped with `logger.warning(...)` instead of being written to `config.yaml`. Added `import logging` and `logger = logging.getLogger(__name__)` to `config_writer.py`.

## Skipped Issues

None — all in-scope findings were fixed.

---

**Test suite result:** `274 passed, 1 skipped, 1 warning` (pre-existing SRT malformed-block warning in integration tests — not introduced by these fixes).

**Ruff lint:** All changed files are lint-clean. Two pre-existing violations in unchanged code were confirmed pre-existing: `F841` in `app.py:252` (unused `original_app`) and `F401` in `tests/db/test_migrations.py:17` (unused `pytest_asyncio`).

---

_Fixed: 2026-06-02_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
