---
phase: 07-web-ui-service-hardening
reviewed: 2026-06-02T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - trezarr/cli.py
  - trezarr/config.py
  - trezarr/jobs/models.py
  - trezarr/web/app.py
  - trezarr/web/config_writer.py
  - trezarr/web/scheduler.py
  - trezarr/web/worker.py
  - trezarr/web/routes/jobs.py
  - trezarr/web/routes/queue.py
  - trezarr/web/routes/settings.py
  - trezarr/web/routes/test_connection.py
  - trezarr/web/routes/webhook.py
  - alembic/versions/0002_job_queue.py
  - alembic/env.py
findings:
  critical: 2
  warning: 4
  info: 2
  total: 8
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-02
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 7 adds a FastAPI daemon (lifespan, scheduler, worker loop, job queue, settings API, webhook receiver) on top of the existing CLI pipeline. The secret-masking architecture (SECRET_FIELDS, SENTINEL, `settings_to_display_dict`) is sound: all four `SecretStr` fields are covered, `model_dump()` returns `SecretStr` wrapper objects that are unconditionally replaced before any `JSONResponse` is built, and the write path correctly skips sentinel values. The webhook handler is correctly enqueue-only, ignores payload file paths, and returns 200 immediately. The lifecycle (engine disposal, scheduler shutdown) honours CR-01 at process scope.

Two blockers are identified. One causes every daemon translation job to fail with an `AttributeError` once the Bible-aware translation path is active (the worker's `_EligibleItemStub` is missing the `media_item` attribute that `translate_file` unconditionally accesses). The other is an asyncio task-GC footgun: `asyncio.create_task` results are discarded in two call sites, which can silently cancel tasks under memory pressure.

---

## Critical Issues

### CR-01: `_EligibleItemStub` missing `media_item` — Bible-aware daemon translation always crashes

**File:** `trezarr/web/worker.py:364-368`

**Issue:** `_execute_job` builds a `_EligibleItemStub` that carries only `source_sub_path`. It then calls `process_one_item(eligible_stub, …, session_factory=session_factory)`. Inside `translate_file`, the Bible-aware branch is guarded by `if eligible_item is not None and session_factory is not None` — both are true in the daemon path — and then immediately does `media_item = eligible_item.media_item` (no `getattr`, no guard). Because `_EligibleItemStub` has no `media_item` attribute, this raises `AttributeError` every time. The error propagates out of `process_one_item` uncaught, is caught by `_execute_job`'s outer `except Exception`, and marks the job `failed` with `error_reason = "unhandled exception in worker"`. Effectively, the Phase-5 Bible-aware translation pipeline is completely silenced in daemon mode — all jobs fail — with no obvious error at the job level (the `AttributeError` stack trace appears only in logs).

Reference: `trezarr/translate/engine.py:705-711` — the access is unconditional once both guards pass.

**Fix:** Add `media_item = None` to `_EligibleItemStub` so translate_file's `getattr` calls are safe, OR pass `session_factory=None` when constructing the stub call (disabling Bible-aware path) and reconstruct the full `EligibleItem` from a DB-backed series lookup before passing to `process_one_item`. The minimal correct fix:

```python
class _EligibleItemStub:
    def __init__(self, sp: str) -> None:
        self.source_sub_path = sp
        self.media_item = None  # signals: no arr discovery context available
```

Then in `translate_file`, add a guard before the unconditional attribute access:

```python
if eligible_item is not None and session_factory is not None:
    media_item = getattr(eligible_item, "media_item", None)
    if media_item is None:
        # Daemon worker stub path: no arr discovery context; skip Bible-aware branch
        pass
    else:
        arr_kind = getattr(media_item, "arr_kind", None) or "sonarr"
        # … rest of Bible path
```

Or alternatively (cleaner), add a `media_item` field to `_EligibleItemStub` and accept that Bible-aware features require a real `EligibleItem`.

---

### CR-02: `asyncio.create_task` results discarded — tasks can be silently GC'd

**Files:** `trezarr/web/routes/webhook.py:118` and `trezarr/web/worker.py:454`

**Issue:** The Python asyncio documentation explicitly warns: *"Save a reference to the result of this function, it can be garbage-collected at any time, even before it's done running."* The event loop holds only a **weak** reference to tasks; if nothing holds a strong reference, the GC can collect the task object mid-execution. In `webhook.py` the discarded task is `poll_and_enqueue` (a full discovery + enqueue cycle). In `worker.py` the discarded task is `_execute_job` (the actual translation job). Under memory pressure — realistic on resource-constrained self-hosted hardware — either task can disappear silently with no log entry, no job status update, and no error surfaced to the operator.

The comment in `webhook.py` (T-07-03-01) only addresses dedup; it does not address the GC risk.

**Fix:** Maintain a module-level `set` of strong task references, adding each task on creation and removing it via a `done_callback`:

```python
# module level in worker.py (and separately in webhook.py or a shared helper)
_active_tasks: set[asyncio.Task] = set()

# when creating the task:
task = asyncio.create_task(
    _execute_job(job_id, session_factory, settings, llm_client, ledger, media_roots)
)
_active_tasks.add(task)
task.add_done_callback(_active_tasks.discard)
```

Apply the same pattern to the webhook's `poll_and_enqueue` task. The `done_callback` also becomes the natural place to log unhandled task exceptions, improving observability.

---

## Warnings

### WR-01: In-flight `_execute_job` tasks are not cancelled on shutdown — may interact with disposed engine

**File:** `trezarr/web/app.py:184-197`

**Issue:** The lifespan `finally` block cancels `worker_task` (the `worker_loop` coroutine) and disposes the engine. But `worker_loop` dispatches jobs via `asyncio.create_task(_execute_job(…))`. Cancelling `worker_task` stops the loop from dispatching *new* jobs, but any already-dispatched `_execute_job` tasks continue running. After `engine.dispose()` completes, those tasks attempt DB operations against a closed engine and will raise connection errors. The `_execute_job` outer `except Exception` catches these and tries a best-effort `session_factory()` status update — which also fails because the engine is disposed. The job is then left with `status='running'` in the DB, which ARM 1 will reconcile on next startup; data is not lost. But the repeated exception storm during shutdown is avoidable and adds noise to operator logs.

**Fix:** Track all dispatched `_execute_job` tasks in `_active_tasks` (see CR-02 fix) and cancel + await them in the lifespan `finally` before `engine.dispose()`:

```python
# in lifespan finally, before engine.dispose():
for task in list(_active_tasks):
    task.cancel()
if _active_tasks:
    await asyncio.gather(*_active_tasks, return_exceptions=True)
```

---

### WR-02: `reconcile_in_progress` (ARM 1) puts job IDs on `_work_queue` before `session.commit()`

**File:** `trezarr/web/worker.py:210-214`

**Issue:** ARM 1 updates `job.status = "queued"` and calls `await _work_queue.put(job.id)` inside the session context, then commits afterward. If `session.commit()` raises (e.g., I/O error on the SQLite file), the job IDs are already on the in-process queue. The worker picks them up and calls `_execute_job`, which fetches the job and finds `status='running'` (the pre-crash status, since the status='queued' update never committed). `_execute_job` proceeds regardless (it does not gate on status), re-sets `status='running'`, and runs the job. The job then gets marked `done`/`failed`/`quarantined` correctly. This is non-fatal and self-healing, but it means the `attempts` counter is incremented without a corresponding committed status reset, which could mislead an operator reading the history. More importantly, if `session.commit()` throws and the session rolls back, ARM 1 silently exits without surfacing the error — the stale jobs are now partially on the queue but their DB state is inconsistent.

**Fix:** Collect job IDs first, commit, then put onto the queue:

```python
stale_ids = [job.id for job in stale_jobs]
for job in stale_jobs:
    job.status = "queued"
await session.commit()
for job_id in stale_ids:
    await _work_queue.put(job_id)
```

---

### WR-03: `poll_interval_seconds` changes via PUT /api/settings are silently ignored at runtime

**File:** `trezarr/web/routes/settings.py:107-110`, `trezarr/web/scheduler.py:174-187`

**Issue:** `put_settings` performs a hot-reload that updates `app.state.settings` with a freshly loaded `TrezarrSettings`. However, the APScheduler job was registered with a `kwargs` dict containing the *original* `settings` object at startup — it holds a reference to that object, not to `app.state.settings`. Changes to `poll_interval_seconds`, `sonarr_enabled`, `radarr_enabled`, or `bazarr_enabled` via PUT take effect on the `app.state.settings` reference (used by webhook handlers and new requests) but do **not** update the running scheduler job. The field `poll_interval_seconds` is not in `RESTART_REQUIRED_FIELDS`, so the UI presents it as hot-reloadable, but the scheduler continues running at the old interval indefinitely.

**Fix (option A — minimal):** Add `poll_interval_seconds` to `RESTART_REQUIRED_FIELDS` so the UI truthfully marks it as requiring restart:

```python
RESTART_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "bible_db_url",
    "web_host",
    "web_port",
    "poll_interval_seconds",  # APScheduler job is registered at startup; interval is baked in
})
```

**Fix (option B — full):** After hot-reload, reschedule the APScheduler job with the new interval using `scheduler.reschedule_job("main_poll", trigger="interval", seconds=new_settings.poll_interval_seconds)`.

---

### WR-04: `write_settings_to_yaml` accepts arbitrary keys — unknown fields are written to `config.yaml`

**File:** `trezarr/web/config_writer.py:119-124`

**Issue:** `write_settings_to_yaml` iterates over the raw `patch` dict from `request.json()` without validating that keys are known `TrezarrSettings` fields. An attacker (or UI bug) sending `{"__init__": "injected"}` or any arbitrary key causes it to be written into `config.yaml`. On the next startup, pydantic-settings silently ignores unknown YAML keys (no `extra="forbid"` is configured), so no immediate damage occurs. However, the YAML file accumulates junk entries that can confuse operators and future config migrations.

**Fix:** Filter the patch to only known field names before iterating:

```python
known_fields = set(current.model_fields.keys())
for key, value in patch.items():
    if key not in known_fields:
        logger.warning("PUT /api/settings: ignoring unknown field %r", key)
        continue
    if key in SECRET_FIELDS and value == SENTINEL:
        continue
    existing[key] = value
```

---

## Info

### IN-01: `_no_db_enqueued` module-level set is never cleared — test isolation risk

**File:** `trezarr/web/worker.py:54`

**Issue:** The `_no_db_enqueued` set is a process-singleton intended for unit tests where `session_factory=None`. It is never cleared between test runs in the same process. Once a `source_path` is added, it can never be re-enqueued via the no-DB path in subsequent tests in the same session. Tests that rely on this path must manually reset `_no_db_enqueued` between runs.

**Fix:** Expose a `_reset_for_tests()` helper in `worker.py` that clears both `_no_db_enqueued` and `_series_locks`, and call it from test fixtures:

```python
def _reset_for_tests() -> None:
    """Clear module-level state between test runs. NOT for production use."""
    _no_db_enqueued.clear()
    _series_locks.clear()
```

---

### IN-02: `test_bazarr` blocks the event loop with a sync `bazarr_enabled` check ordering

**File:** `trezarr/web/routes/test_connection.py:149-155`

**Issue:** `test_bazarr` checks `settings.bazarr_enabled` before attempting the async HTTP call and returns 503 if disabled. This is sound logic, but the comment "Check bazarr_enabled setting from app.state (when available)" and the silent `pass` in the `except AttributeError` branch mean the check is **skipped silently** in test environments without lifespan. If a future test calls this endpoint with `bazarr_enabled=False` baked into a real settings object on app.state, the test may pass through to the HTTP call unintentionally. The silent `pass` hides whether the guard was exercised.

**Fix:** Log at DEBUG level when the guard is skipped:

```python
except AttributeError:
    logger.debug("test_bazarr: no settings on app.state; skipping bazarr_enabled guard")
    pass
```

---

_Reviewed: 2026-06-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
