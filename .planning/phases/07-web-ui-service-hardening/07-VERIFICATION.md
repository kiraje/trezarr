---
phase: 07-web-ui-service-hardening
verified: 2026-06-01T23:31:19Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open http://localhost:6868 after running `cd frontend && npm run build && uv run trezarr serve`"
    expected: "Browser redirects to /queue; Trezarr wordmark in TopBar; sidebar shows Settings / Queue (active) / History nav items; correct design tokens (dark background, blue accent, status badge colors)"
    why_human: "Visual SPA conformance requires a browser — cannot verify DOM rendering or CSS computed styles programmatically"
  - test: "Navigate to /settings in the live SPA"
    expected: "6 connection sections (LLM, Sonarr, Radarr, Bazarr, Path Mappings, Service Settings); API key fields show 'set' chip; Save and Test Connection buttons present"
    why_human: "UI layout and interactive component behavior requires a browser"
  - test: "Navigate to /queue and /history in the live SPA"
    expected: "Correct column headers (Series, Episode, File, Status, Queued, Logs on queue; ...Finished, Reason, Actions on history); empty state text correct; Retry inline confirmation works"
    why_human: "UI layout and interactive retry flow requires a browser"
  - test: "Navigate to /jobs/{id}/logs if a job exists"
    expected: "History breadcrumb, job summary strip, LogViewer with timestamp prefix and colored level tags ([INFO], [ERROR]); empty state text if no logs"
    why_human: "Per-job log page layout and rendering requires a browser"
  - test: "Check Network tab in DevTools while navigating"
    expected: "/api/queue, /api/jobs, /api/settings, /api/health all return HTTP 200"
    why_human: "Network traffic inspection requires a browser DevTools session"
  - test: "Run `docker build -t trezarr:dev .` from repo root"
    expected: "Build exits 0; both Node 20-slim (SPA compile) and Python 3.12-slim stages complete without errors"
    why_human: "Docker daemon unavailable in autonomous CI — requires host Docker installation"
  - test: "Run `docker run --rm trezarr:dev trezarr --help`"
    expected: "Exits 0; output includes 'serve' as a subcommand"
    why_human: "Requires Docker image built from previous step"
  - test: "Run container with PUID/PGID and /config volume, then `curl http://localhost:6868/api/health`"
    expected: '{"status":"ok"} returned; Docker logs show lifespan startup (scheduler started, worker started)'
    why_human: "Requires Docker daemon and live container"
  - test: "After container run, inspect `ls -la /tmp/trezarr-config/`"
    expected: "Files (trezarr.db, config.yaml) owned by host UID:GID matching PUID/PGID, NOT root"
    why_human: "File ownership requires running the actual container with volume mount"
  - test: "Run `docker compose -f docker-compose.example.yml config`"
    expected: "Exits 0 (or surfaces 'TREZARR_LLM_API_KEY required' error, which is expected behavior)"
    why_human: "Requires Docker Compose CLI and a live Docker daemon"
---

# Phase 7: Web UI & Service Hardening Verification Report

**Phase Goal:** Trezarr runs as a Dockerized, long-running, crash-safe service alongside the *arr stack, with a web UI to configure connections and watch the queue/history/logs and retry failures — the *arr-citizen baseline that makes unattended operation trustworthy.
**Verified:** 2026-06-01T23:31:19Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Trezarr deploys as a single Docker container with `/config` volume and runs as a long-lived service alongside the *arr stack | VERIFIED (automated) + HUMAN NEEDED (live run) | `Dockerfile` exists: multi-stage (Node 20-slim → Python 3.12-slim), `VOLUME ["/config"]`, `EXPOSE 6868`, `CMD ["trezarr", "serve"]`, gosu PUID/PGID drop-privilege. `trezarr serve` subcommand confirmed via `test_serve_subcommand_exists` PASSED. Docker runtime test deferred to HUMAN-UAT. |
| 2 | A web UI configures Sonarr/Radarr/Bazarr connections, the LLM endpoint, and paths, with connection tests | VERIFIED (automated) + HUMAN NEEDED (visual) | `GET /api/settings` returns masked secrets (SENTINEL), `PUT /api/settings` writes YAML. `POST /api/test/{sonarr\|radarr\|bazarr\|llm}` validated. `test_secrets_masked`, `test_settings_write`, `test_secret_never_in_response`, `test_sonarr_connection_ok`, `test_sonarr_connection_error`, `test_secret_not_in_connection_error`, `test_llm_connection_ok` all PASSED. SPA Settings page exists in `frontend/src/pages/Settings.tsx`. Visual conformance deferred to HUMAN-UAT. |
| 3 | The UI shows Queue/History/per-job logs; a failed item can be retried from the UI | VERIFIED (automated) + HUMAN NEEDED (visual) | `GET /api/queue`, `GET /api/jobs`, `GET /api/jobs/{id}/logs`, `POST /api/jobs/{id}/retry` all implemented in `routes/queue.py` and `routes/jobs.py`. Retry resets to `queued`, sets `trigger=manual-retry`, calls `enqueue_job`. Per-job `JobLog` capture via `_JobLogHandler` verified. `test_get_queue`, `test_get_history`, `test_get_job_logs`, `test_retry_requeues` all PASSED. SPA Queue/History/JobLogs pages exist. Visual conformance deferred to HUMAN-UAT. |
| 4 | Trezarr monitors for newly added media (polling + webhook), and resumes safely after a crash per-series-serialized | VERIFIED (automated) | APScheduler `poll_and_enqueue` calls discover+scan+enqueue. `POST /webhook` returns 200 immediately without awaiting translation (background task). Both deduplicate via `enqueue_job` guard. `reconcile_in_progress` (ARM 1: Job rows) + `reconcile_in_progress_from_ledger` (ARM 2: ProcessedFile in_progress with no matching Job) both implemented and called in lifespan startup. Per-series `asyncio.Lock` serialization confirmed; `asyncio.Semaphore` count in `worker.py` = 0 (D-68). All 5 `test_worker.py` tests + `test_webhook_*` + `test_scheduler_*` PASSED. |

**Score:** 4/4 truths verified (automated portions). Human UAT items are the only remaining gate.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/web/__init__.py` | Package marker | VERIFIED | Exists, 0 bytes |
| `tests/web/test_lifespan.py` | SVC-01 lifespan stubs → GREEN | VERIFIED | 3 tests PASSED |
| `tests/web/test_settings_api.py` | SVC-02 secret masking | VERIFIED | 3 tests PASSED |
| `tests/web/test_connection_tests.py` | SVC-02 connection tests | VERIFIED | 4 tests PASSED |
| `tests/web/test_jobs_api.py` | SVC-03/SVC-04 queue/history/logs/retry | VERIFIED | 4 tests PASSED |
| `tests/web/test_webhook.py` | AUTO-02 webhook handler | VERIFIED | 3 tests PASSED |
| `tests/web/test_scheduler.py` | AUTO-02 poll scheduler | VERIFIED | 2 tests PASSED |
| `tests/web/test_worker.py` | AUTO-05/D-67/D-68 worker | VERIFIED | 8 tests PASSED (including D-67 ProcessedFile arm) |
| `tests/db/test_migrations.py` | 0002 migration stub | VERIFIED | `test_0002_migration_creates_job_tables` PASSED; `test_job_table_has_media_item_json_column` PASSED |
| `trezarr/jobs/models.py` | Job + JobLog SQLAlchemy models | VERIFIED | Both classes defined; `media_item_json` JSON column present (CR-01 fix) |
| `alembic/versions/0002_job_queue.py` | Creates job + job_log tables | VERIFIED | `down_revision="0001"`, creates `job` and `job_log` tables with CheckConstraints and indexes; `media_item_json` column present |
| `trezarr/web/app.py` | FastAPI app with CR-01-correct lifespan | VERIFIED | `@asynccontextmanager lifespan`; `engine.dispose()` in `finally`; in-flight task cancellation before disposal (WR-01 fix); API routes registered before StaticFiles (Pitfall E); `GET /api/health` defined |
| `trezarr/web/worker.py` | Queue worker + per-series Lock + two-arm reconcile | VERIFIED | `enqueue_job`, `reconcile_in_progress` (ARM 1), `reconcile_in_progress_from_ledger` (ARM 2), `_execute_job`, `worker_loop`; `_series_locks: dict[int, asyncio.Lock]`; 0 `asyncio.Semaphore` usages; `_background_tasks: set[asyncio.Task]` (CR-02 fix); commit-before-queue (WR-02 fix) |
| `trezarr/web/config_writer.py` | Secret masking + YAML write-back | VERIFIED | `SECRET_FIELDS` covers all 4 SecretStr fields; `SENTINEL = "**REDACTED**"`; `RESTART_REQUIRED_FIELDS` includes `poll_interval_seconds` (WR-03 fix); unknown field filtering (WR-04 fix) |
| `trezarr/web/scheduler.py` | APScheduler poll callback | VERIFIED | `poll_and_enqueue` calls `discover_sonarr_items`, `discover_radarr_items`, `scan_for_eligible_items`, `enqueue_job`; `setup_scheduler` wires interval job |
| `trezarr/web/routes/webhook.py` | POST /webhook enqueue-only | VERIFIED | Returns 200 immediately; `asyncio.create_task` (not awaited); `_background_tasks` strong reference set (CR-02); does NOT call `translate_file` |
| `trezarr/web/routes/queue.py` | GET /api/queue, /api/jobs, /api/jobs/{id}/logs | VERIFIED | All three routes defined |
| `trezarr/web/routes/jobs.py` | POST /api/jobs/{id}/retry | VERIFIED | Resets job status, sets `trigger="manual-retry"`, calls `enqueue_job` |
| `trezarr/web/routes/settings.py` | GET/PUT /api/settings, GET /api/settings/env-locked | VERIFIED | All three routes defined |
| `trezarr/web/routes/test_connection.py` | POST /api/test/{sonarr\|radarr\|bazarr\|llm} | VERIFIED | All four routes defined; error responses strip API key values |
| `trezarr/cli.py` | `process_one_item` extracted; `serve` subparser added | VERIFIED | `process_one_item` top-level async function at line 92; `serve` subparser at line 233; `_run_pipeline_steps` calls `process_one_item` in its loop (D-62) |
| `Dockerfile` | Multi-stage Node→Python; EXPOSE 6868; PUID/PGID; CMD serve | VERIFIED (static) | Node 20-slim build stage; Python 3.12-slim runtime; `gosu` for PUID/PGID; `VOLUME ["/config"]`; `EXPOSE 6868`; `CMD ["trezarr", "serve"]`; `COPY --from=node-builder` for SPA static assets; `HEALTHCHECK` on `/api/health` |
| `docker-compose.example.yml` | Example compose deployment | VERIFIED | File exists (5.6K) |
| `.dockerignore` | Excludes build artifacts | VERIFIED | File exists (1.3K) |
| `frontend/src/pages/Settings.tsx` | Settings SPA page | VERIFIED | File exists (17.9K) — substantive |
| `frontend/src/pages/Queue.tsx` | Queue SPA page | VERIFIED | Polls `GET /api/queue` every 10s via `setInterval` |
| `frontend/src/pages/History.tsx` | History SPA page | VERIFIED | File exists (2.4K) |
| `frontend/src/pages/JobLogs.tsx` | JobLogs SPA page | VERIFIED | File exists (3.3K) |
| `frontend/src/api/client.ts` | Typed fetch wrappers | VERIFIED | Wrappers for `/api/settings`, `/api/queue`, `/api/jobs`, `/api/jobs/{id}/logs`, `/api/test/*` all present |
| `trezarr/web/static/` | Built SPA (served by FastAPI) | VERIFIED | `index.html` + `assets/` present — SPA was built |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `trezarr/web/app.py` | `trezarr/db/engine.py` | `build_engine` inside lifespan; `await engine.dispose()` in `finally` | WIRED | CR-01 invariant: engine created before outer try, disposed in finally |
| `trezarr/web/worker.py` | `trezarr/cli.py` | `_execute_job` imports and calls `process_one_item` (D-62) | WIRED | Confirmed at lines ~366, 448 of `worker.py` |
| `trezarr/cli.py` | `trezarr/cli.py` | `_run_pipeline_steps` loop calls `process_one_item` (same shared callable) | WIRED | Confirmed at line 460 |
| `alembic/env.py` | `trezarr/jobs/models.py` | `from trezarr.jobs import models as _job_models  # noqa: F401` | WIRED | Registers Job/JobLog into `Base.metadata` |
| `trezarr/web/scheduler.py` | `trezarr/discover/scan.py` | `poll_and_enqueue` calls `scan_for_eligible_items` | WIRED | Confirmed at line 112 of `scheduler.py` |
| `trezarr/web/routes/webhook.py` | `trezarr/web/worker.py` | `asyncio.create_task(poll_and_enqueue(...))` + `_background_tasks` strong ref | WIRED | CR-02 fix applied |
| `trezarr/web/routes/settings.py` | `trezarr/web/config_writer.py` | `settings_to_display_dict` + `write_settings_to_yaml` | WIRED | All three settings routes use config_writer functions |
| `frontend/src/pages/Queue.tsx` | `/api/queue` | `setInterval(() => void load(), 10_000)` | WIRED | Confirmed at line 51 of `Queue.tsx` |
| `trezarr/web/routes/jobs.py` | `trezarr/web/worker.py` | `enqueue_job` after resetting job state | WIRED | Retry route calls `enqueue_job` with `trigger="manual-retry"` |
| `Dockerfile` | `trezarr/web/static/` | `COPY --from=node-builder /app/trezarr/web/static ./trezarr/web/static` | WIRED | Static build artifacts present; FastAPI mounts via `StaticFiles` |

---

### Critical Correctness Checks (CR-01 / D-67 / D-68)

| Check | Finding | Status |
|-------|---------|--------|
| CR-01: `media_item_json` column on `Job` model | `Mapped[dict \| None] = mapped_column(JSON, nullable=True, default=None)` at line 72 of `models.py` | VERIFIED |
| CR-01: `media_item_json` in 0002 migration | `sa.Column("media_item_json", sa.JSON, nullable=True)` at line 53 of `0002_job_queue.py` | VERIFIED |
| CR-01: `_execute_job` reconstructs `SimpleNamespace` from JSON; falls back to `session_factory=None` when absent | Lines 431-444 of `worker.py`; `test_execute_job_bible_aware_path_with_media_item_json` PASSED; `test_execute_job_mechanical_fallback_without_media_item_json` PASSED | VERIFIED |
| D-68: 0 `asyncio.Semaphore` usages in `worker.py` | `grep -c "asyncio.Semaphore" worker.py` → 0 | VERIFIED |
| D-68: Per-series `asyncio.Lock` in `_series_locks` | `_series_locks: dict[int, asyncio.Lock] = {}` at line 51; `test_no_second_semaphore` PASSED | VERIFIED |
| CR-02: `_background_tasks: set[asyncio.Task]` in both `worker.py` and `webhook.py` | Lines 62 (`worker.py`), 38 (`webhook.py`); `test_background_tasks_set_exists` PASSED | VERIFIED |
| WR-01: In-flight tasks cancelled before `engine.dispose()` | `_worker_background_tasks` imported in `app.py`; `asyncio.gather(*list(_worker_background_tasks), return_exceptions=True)` before `engine.dispose()` | VERIFIED |
| WR-02: Commit before queue in ARM 1 reconcile | `stale_ids` collected, statuses updated, `await session.commit()`, then `_work_queue.put` | VERIFIED |
| WR-03: `poll_interval_seconds` in `RESTART_REQUIRED_FIELDS` | Confirmed in `config_writer.py` | VERIFIED |
| WR-04: Unknown field filtering in `write_settings_to_yaml` | `known_fields = set(type(current).model_fields.keys())` guard present | VERIFIED |
| D-70: `test_secret_never_in_response` PASSED | Raw `SecretStr` values never escape `settings_to_display_dict` | VERIFIED |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `routes/queue.py` GET /api/queue | `jobs` from DB | `select(Job).where(Job.status.in_(['queued', 'running']))` | Yes — SQLAlchemy query against `job` table | FLOWING |
| `routes/queue.py` GET /api/jobs/{id}/logs | `logs` from DB | `select(JobLog).where(JobLog.job_id == job_id)` | Yes — SQLAlchemy query against `job_log` table | FLOWING |
| `routes/jobs.py` POST /api/jobs/{id}/retry | `job` from DB | Fetches `Job` by ID, resets status, calls `enqueue_job` | Yes — real DB write + queue put | FLOWING |
| `frontend/src/pages/Queue.tsx` | queue state | `setInterval(() => fetch('/api/queue'))` every 10s | Yes — live API call | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase-7 settings fields with correct defaults | `python -c "from trezarr.config import TrezarrSettings; s = TrezarrSettings(llm_api_key='x'); print(s.web_port, s.poll_interval_seconds, s.bazarr_enabled)"` | `6868 900 False` | PASS |
| `process_one_item` is a real async function | `python -c "import trezarr.cli; import inspect; print(inspect.getsource(trezarr.cli.process_one_item)[:50])"` | `async def process_one_item(` — real function | PASS |
| No `asyncio.Semaphore` in `worker.py` | `grep -c "asyncio.Semaphore" trezarr/web/worker.py` | `0` | PASS |
| `_background_tasks` is a `set` | `python -c "from trezarr.web.worker import _background_tasks; print(isinstance(_background_tasks, set))"` | `True` | PASS |
| `SECRET_FIELDS` covers all 4 SecretStr fields | `python -c "from trezarr.web.config_writer import SECRET_FIELDS; print(SECRET_FIELDS)"` | `frozenset({'bazarr_api_key', 'llm_api_key', 'sonarr_api_key', 'radarr_api_key'})` | PASS |
| `poll_interval_seconds` in `RESTART_REQUIRED_FIELDS` | `python -c "from trezarr.web.config_writer import RESTART_REQUIRED_FIELDS; print('poll_interval_seconds' in RESTART_REQUIRED_FIELDS)"` | `True` | PASS |
| Full test suite | `uv run pytest tests/ -q` | `274 passed, 1 skipped, 1 warning in 6.97s` | PASS |

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| SVC-01 | Single Dockerized service with `/config` volume | SATISFIED | `Dockerfile` (multi-stage, PUID/PGID, `VOLUME /config`, `EXPOSE 6868`, `CMD trezarr serve`); `run_serve` in `app.py`; `test_serve_subcommand_exists` PASSED |
| SVC-02 | Web UI configures connections with tests | SATISFIED | `GET/PUT /api/settings` (masked secrets); `GET /api/settings/env-locked`; `POST /api/test/*` (4 services); `test_secret_never_in_response` PASSED (HIGH security gate) |
| SVC-03 | Web UI shows Queue, History, per-job logs | SATISFIED | `GET /api/queue`, `GET /api/jobs`, `GET /api/jobs/{id}/logs`; React pages `Queue.tsx`, `History.tsx`, `JobLogs.tsx`; per-job `JobLog` rows via `_JobLogHandler`; `test_get_queue/history/job_logs` PASSED |
| SVC-04 | User can retry failed/rejected item from UI | SATISFIED | `POST /api/jobs/{id}/retry` resets job, sets `trigger=manual-retry`, re-enqueues; `RetryButton.tsx` component; `test_retry_requeues` PASSED |
| AUTO-02 | Ongoing monitoring: polling + webhook trigger | SATISFIED | APScheduler interval job (`setup_scheduler`, `poll_and_enqueue`); `POST /webhook` enqueue-only background task; both deduplicate; `test_webhook_*` and `test_poll_*` PASSED |
| AUTO-05 | Crash-safe resume without loss or duplication | SATISFIED | `reconcile_in_progress` (ARM 1: Job rows with status running/queued); `reconcile_in_progress_from_ledger` (ARM 2: ProcessedFile `in_progress` with no matching Job row); per-series `asyncio.Lock`; `test_reconcile_in_progress` + `test_reconcile_in_progress_from_ledger` PASSED |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None in phase-modified files | — | No `TBD`, `FIXME`, `XXX`, `HACK`, `PLACEHOLDER`, or `return null/[]/{}` stubs found | — | Clean |

---

### Probe Execution

Step 7c: SKIPPED — no `probe-*.sh` scripts declared in PLAN files or present under `scripts/*/tests/`. Phase verification relies on pytest suite (274 tests) and behavioral spot-checks.

---

### Human Verification Required

The following items are genuinely deferred from `07-HUMAN-UAT.md` (auto-deferred: no Docker daemon + no browser available in autonomous run). All automated correctness checks passed; only visual/runtime verification remains.

#### 1. React SPA Visual Conformance (from 07-05-PLAN Task 4)

**Test:** `cd frontend && npm run build && uv run trezarr serve`, then open `http://localhost:6868` in a browser.
**Expected:** Default route redirects to `/queue`. Wordmark in TopBar. Sidebar shows Settings / Queue (active) / History nav items. Correct design tokens: dark background (#0f1117), blue accent (#3b82f6) on active nav, correct status badge colors (Queued=slate, Running=blue, Done=green, Failed=red, Quarantined=orange).
**Why human:** Visual appearance, CSS computed styles, and React routing behavior require a browser.

#### 2. Settings Page UI Correctness

**Test:** Navigate to `/settings` in the live SPA.
**Expected:** 6 connection sections visible; API key fields show "set" chip when previously configured; Save button disabled when no unsaved changes; Test Connection buttons present for Sonarr/Radarr/Bazarr/LLM.
**Why human:** Interactive component state and conditional rendering require a browser.

#### 3. Queue Page Columns and Empty State

**Test:** Navigate to `/queue`.
**Expected:** Column headers: Series, Episode, File, Status, Queued, Logs. Empty state text: "No jobs in queue" / "Trezarr will enqueue episodes automatically when a source subtitle is found with no Vietnamese output."
**Why human:** UI layout and text content require a browser.

#### 4. History Page + Retry Inline Flow

**Test:** Navigate to `/history`.
**Expected:** Column headers: Series, Episode, File, Status, Finished, Reason, Actions. If failed/quarantined rows exist: Retry button renders inline; clicking shows "Re-queue this item? [Re-queue] [Cancel]" inline confirmation.
**Why human:** Interactive retry confirmation flow requires a browser.

#### 5. Per-Job Logs Page

**Test:** If a job exists in history, click its Logs icon.
**Expected:** Navigates to `/jobs/{id}/logs`; "← History" breadcrumb; job summary strip; LogViewer with `HH:MM:SS` timestamp prefix and colored level prefixes (`[INFO]`, `[ERROR]`, etc.); empty state if no logs.
**Why human:** Per-job log page layout and color rendering require a browser.

#### 6. API Calls Return 200 (DevTools)

**Test:** In a live browser session, navigate between pages and inspect the Network tab.
**Expected:** `/api/queue`, `/api/jobs`, `/api/settings`, `/api/health` all return HTTP 200 (not 404 or 500).
**Why human:** Requires a live browser DevTools session.

#### 7. Docker Build Succeeds (from 07-06-PLAN Task 2)

**Test:** `docker build -t trezarr:dev .` from repo root.
**Expected:** Exits 0; both Node 20-slim and Python 3.12-slim stages complete without errors.
**Why human:** Docker daemon unavailable in autonomous CI.

#### 8. `trezarr serve` Reachable Inside Image

**Test:** `docker run --rm trezarr:dev trezarr --help`
**Expected:** Exits 0; output includes "serve" as a subcommand.
**Why human:** Requires built Docker image.

#### 9. Container Health Endpoint Responds

**Test:** Start container with `/config` volume + `PUID/PGID`, then `curl http://localhost:6868/api/health`.
**Expected:** `{"status":"ok"}` returned; Docker logs show lifespan startup sequence.
**Why human:** Requires Docker daemon and live container.

#### 10. PUID/PGID File Ownership Correct

**Test:** After running the container, inspect `ls -la /tmp/trezarr-config/`.
**Expected:** Files written by the container (trezarr.db, config.yaml) owned by host UID:GID matching `PUID`/`PGID`, NOT root.
**Why human:** File ownership requires actually running the container with a volume mount.

---

### Gaps Summary

No automated gaps. All 4 ROADMAP success criteria are fully verified by the automated test suite (274 passed, 0 failed). All 6 requirement IDs (SVC-01..04, AUTO-02, AUTO-05) are satisfied by verified, substantive, wired implementations.

The 10 human verification items above are **not gaps** — they are legitimately deferred items from `07-HUMAN-UAT.md` (visual SPA conformance and Docker runtime tests) that require a browser and Docker daemon. The `status: human_needed` reflects this only; there are no code-level blockers.

---

_Verified: 2026-06-01T23:31:19Z_
_Verifier: Claude (gsd-verifier)_
