---
phase: 7
slug: web-ui-service-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-02
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `07-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (existing, `asyncio_mode=auto`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q -k "not integration"` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30–60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -k "not integration"`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| SVC-01 | lifespan startup/shutdown without error | integration (in-process uvicorn) | `pytest tests/web/test_lifespan.py -x` | ❌ W0 | ⬜ pending |
| SVC-01 | Engine disposed on shutdown (no CR-01 reuse-after-close) | unit | `pytest tests/web/test_lifespan.py::test_engine_disposed_on_shutdown -x` | ❌ W0 | ⬜ pending |
| SVC-01 | `trezarr serve` CLI subcommand registered | unit | `pytest tests/test_cli.py::test_serve_subcommand_exists -x` | ❌ W0 | ⬜ pending |
| SVC-02 | GET /api/settings returns masked secrets | unit | `pytest tests/web/test_settings_api.py::test_secrets_masked -x` | ❌ W0 | ⬜ pending |
| SVC-02 | PUT/POST /api/settings writes to config.yaml | unit | `pytest tests/web/test_settings_api.py::test_settings_write -x` | ❌ W0 | ⬜ pending |
| SVC-02 | POST /api/test/sonarr returns ok/error | unit (mocked pyarr) | `pytest tests/web/test_connection_tests.py::test_sonarr_connection_ok -x` | ❌ W0 | ⬜ pending |
| SVC-03 | GET /api/queue returns in-flight job rows | unit | `pytest tests/web/test_jobs_api.py::test_get_queue -x` | ❌ W0 | ⬜ pending |
| SVC-03 | GET /api/jobs returns history (done/failed + reason) | unit | `pytest tests/web/test_jobs_api.py::test_get_history -x` | ❌ W0 | ⬜ pending |
| SVC-03 | GET /api/jobs/{id}/logs returns per-job log trail | unit | `pytest tests/web/test_jobs_api.py::test_get_job_logs -x` | ❌ W0 | ⬜ pending |
| SVC-04 | POST /api/jobs/{id}/retry re-enqueues | unit | `pytest tests/web/test_jobs_api.py::test_retry_requeues -x` | ❌ W0 | ⬜ pending |
| AUTO-02 | Webhook POST triggers enqueue | unit | `pytest tests/web/test_webhook.py::test_webhook_enqueues -x` | ❌ W0 | ⬜ pending |
| AUTO-02 | Webhook handler returns 200 immediately (non-blocking) | unit | `pytest tests/web/test_webhook.py::test_webhook_returns_200_fast -x` | ❌ W0 | ⬜ pending |
| AUTO-02 | Poll job enqueues newly-eligible items | unit | `pytest tests/web/test_scheduler.py::test_poll_enqueues -x` | ❌ W0 | ⬜ pending |
| AUTO-05 | `in_progress` rows re-enqueued on startup reconcile | unit | `pytest tests/web/test_worker.py::test_reconcile_in_progress -x` | ❌ W0 | ⬜ pending |
| AUTO-05 | Two episodes of same series run serially | unit | `pytest tests/web/test_worker.py::test_per_series_serialization -x` | ❌ W0 | ⬜ pending |
| AUTO-05 | Two episodes of distinct series run concurrently | unit | `pytest tests/web/test_worker.py::test_distinct_series_concurrent -x` | ❌ W0 | ⬜ pending |
| AUTO-05 (D-68) | Single `LLMClient._semaphore` not doubled by a second semaphore | unit | `pytest tests/web/test_worker.py::test_no_second_semaphore -x` | ❌ W0 | ⬜ pending |
| AUTO-05 (D-69) | Alembic 0002 (`job`/`job_log`) migration runs cleanly on the 0001 baseline | integration | `pytest tests/db/test_migrations.py::test_0002_migration -x` | ❌ W0 | ⬜ pending |
| SVC-02 (D-70) | SecretStr value never appears in any settings API response | unit | `pytest tests/web/test_settings_api.py::test_secret_never_in_response -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/web/__init__.py` — new test package
- [ ] `tests/web/test_lifespan.py` — SVC-01, engine/scheduler lifecycle (startup + shutdown dispose)
- [ ] `tests/web/test_settings_api.py` — SVC-02, secret masking, write-back, secret-never-in-response (D-70)
- [ ] `tests/web/test_connection_tests.py` — SVC-02, connection-test endpoints (mocked pyarr / httpx)
- [ ] `tests/web/test_jobs_api.py` — SVC-03/SVC-04, queue/history/logs/retry
- [ ] `tests/web/test_webhook.py` — AUTO-02, webhook handler enqueue + fast-200
- [ ] `tests/web/test_scheduler.py` — AUTO-02, poll job enqueues
- [ ] `tests/web/test_worker.py` — AUTO-05/D-68, reconcile + per-series lock + distinct-series concurrency + no-second-semaphore
- [ ] `tests/db/test_migrations.py` — D-69, Alembic 0002 migration on the 0001 baseline

*Existing pytest infrastructure (`asyncio_mode=auto`, fixture-based async SQLite) covers the harness; Wave 0 adds the `tests/web/` package and the migration test.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Single container builds and runs `trezarr serve` with a `/config` volume next to the *arr stack | SVC-01 | Requires a Docker build + a real host environment (PUID/PGID, volume mounts) | `docker build` the image; run with `-v ./config:/config -p 6868:6868 -e PUID -e PGID`; confirm UI loads on :6868 and DB/config land in `/config` |
| Sidecars written under the service run with correct host ownership | SVC-01 / INTG-04 | Ownership is environment-specific (host UID/GID) | After a real translate under the container, `ls -l` the `.vi.srt` and confirm owner matches PUID/PGID |
| Web UI renders Settings/Queue/History/Logs and Retry works against a live browser | SVC-02/03/04 | Visual + interactive; SPA served by FastAPI | Open `http://host:6868`, edit a connection, run a connection test, observe a job in Queue→History, click Retry |
| Real Sonarr/Radarr Connect + Bazarr outgoing webhook triggers a scan | AUTO-02 | Requires a live *arr stack emitting real webhooks | Configure Connect/outgoing webhook → `:6868/webhook`; add media; confirm an enqueue appears in the Queue |
| Crash mid-translation resumes without duplicate/corrupt output after restart | AUTO-05 | Requires killing the process mid-flight | Start a long translate, `kill -9`, restart `serve`, confirm the `in_progress` item re-runs once and the sidecar is correct |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING test references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter (after Wave 0 stubs exist)

**Approval:** pending
