# Phase 7: Web UI & Service Hardening - Research

**Researched:** 2026-06-02
**Domain:** FastAPI service runtime, APScheduler, SQLAlchemy async lifecycle, Alembic migration, React+Vite SPA, Docker multi-stage + LSIO PUID/PGID
**Confidence:** HIGH (existing codebase verified; library API patterns verified against official docs; version discrepancy noted below)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

D-61: One uvicorn process; FastAPI `lifespan` owns APScheduler poll + webhook receiver + queue worker, serves the Vite SPA dist/; single image, single port (6868).
D-62: Add `trezarr serve` CLI subcommand; preserve `trezarr run --once` unchanged. Extract `_run_pipeline_steps` per-item body into a reusable async callable both paths invoke.
D-63: Add `fastapi` (~0.136), `uvicorn[standard]` (~0.48), `apscheduler` (~3.11), `httpx` (~0.28), `watchfiles` (~1.2, default-off). Frontend is a separate `frontend/` package, Vite 7 / React 19.
D-64: Single multi-stage Dockerfile (Node build stage → Python runtime). LSIO pattern recommended (`ghcr.io/linuxserver/baseimage-*` + s6-overlay); `python:3.12-slim` + small PUID/PGID entrypoint is the acceptable fallback. `/config` volume for DB, config.yaml, quarantine, logs. Expose port 6868.
D-65: Hybrid trigger — APScheduler interval poll is the source of truth; inbound FastAPI webhook endpoint (Sonarr/Radarr Connect, Bazarr subtitle events) is the low-latency complement; `watchfiles` is optional/default-off.
D-66: Both poll and webhook run discover → scan eligible → enqueue only. Translation happens only in the worker. Webhook handler enqueues and returns 200 immediately. Dedup via ledger + queue guard.
D-67: Crash-resume reuses existing `in_progress` ledger semantics. On daemon startup: reconcile any `in_progress` rows left by a prior crashed process by re-enqueueing them. Per-file granularity checkpoint (not per-pass).
D-68: Serialize per series via per-`series_id` asyncio.Lock (or series-keyed single-flight). Distinct series may run concurrently. `worker_max_concurrent_series` bounds distinct parallel series. Single global `LLMClient._semaphore` (D-06) remains the ONLY global in-flight LLM cap — per-series lock is an ordering constraint, NOT a second semaphore.
D-69: New `job` + `job_log` tables via a new Alembic migration (the first since 0001 baseline). job.status = queued|running|done|failed|quarantined. Keeps the frozen D-20 LedgerEntry↔ProcessedFile-column contract untouched.
D-70: Config read/write service; SecretStr fields write-only (never echoed back); config writer writes to /config/config.yaml. Env-var-sourced settings keep existing env > YAML precedence; UI surfaces which fields are env-locked.
D-71: POST /api/test/{sonarr|radarr|bazarr|llm} validates candidate config before saving. Uses pyarr `system/status` ping for *arr; minimal LLM completion for LLM test. API keys never returned in response or logs.
D-72: Prefer hot re-application of affected clients on save; if a setting genuinely requires restart, the UI must say so explicitly.
D-73: React 19 + Vite 7 SPA; REST API with client-side polling for live updates. Views: Settings, Queue, History, per-job Logs + Retry. SSE/WebSocket is a deferrable nice-to-have.
D-74: Retry = re-enqueue via `POST /api/jobs/{id}/retry`; resets job + ledger state; triggers source is `manual-retry`.
D-75: Capture each job's `logging` output into per-job sink (job_log rows); rotating app-wide log file in /config/logs for operator-level observability.
D-76: New Phase-7 TrezarrSettings fields under a Phase-7 header: web_host (0.0.0.0), web_port (6868), poll_interval_seconds (~900), enable_webhooks (True), enable_watchfiles (False), worker_max_concurrent_series (int), bazarr_host/bazarr_port (6767)/bazarr_api_key (SecretStr)/bazarr_enabled (False).
D-77: Independent toggles for staged rollout — daemon, poller, webhook receiver, watcher each individually toggleable.
D-78: Single-user, no-auth, trusted-LAN default. Bind/port configurable for reverse proxy.

### Claude's Discretion
Module layout for the web layer (trezarr/web/ vs trezarr/api/ + trezarr/service/); whether the queue is a DB-polling worker, an asyncio.Queue, or an APScheduler-job-per-item; the exact job/job_log schema (or extending processed_file instead — D-69); the precise REST route names and response DTOs; SSE/WebSocket vs polling for live updates; the per-series serialization primitive (per-series_id asyncio.Lock vs series-keyed single-flight); LSIO baseimage vs python:3.12-slim + entrypoint; how much settings hot-reload to implement (D-72); the per-job log-capture mechanism (D-75); the exact new setting names and numeric defaults (D-76); the SPA component structure and styling approach; whether watchfiles ships wired-but-off or merely scaffolded.

### Deferred Ideas (OUT OF SCOPE)
- Editable/lockable Series Bible UI → Phase 8 (BIBLE-08/09)
- Reading Bazarr's subtitle inventory, source-language selection, per-series overrides → Phase 10 (INTG-02, SRC-01/02, SVC-05)
- ASS/SSA + VTT formats → Phase 9 (FMT-02/03/04)
- watchfiles filesystem watcher fully wired → deferred-within-phase (default-off toggle)
- SSE/WebSocket live updates → nice-to-have; mvp uses client-side polling
- Web UI authentication/multi-user → not v1 (D-78)
- Notifications (Discord/Telegram/ntfy, OBS-02), confidence-flagging (OBS-01), multi-instance *arr (SCALE-01) → v2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SVC-01 | Single Dockerized, long-running self-hosted service with `/config` volume | D-61/D-64: multi-stage Dockerfile + LSIO PUID/PGID; lifespan owns all startup/shutdown |
| SVC-02 | Web UI configures connections (Sonarr/Radarr/Bazarr, LLM endpoint, paths) with connection tests | D-70/D-71: config-writer service + POST /api/test/* endpoints; SecretStr masking |
| SVC-03 | Queue, History, per-job logs in web UI | D-69/D-73/D-75: job table + job_log + REST API + SPA views |
| SVC-04 | User can retry/re-run a failed item from UI | D-74: POST /api/jobs/{id}/retry re-enqueues through worker |
| AUTO-02 | Continuous monitoring: poll + webhook trigger support | D-65/D-66: APScheduler poll + FastAPI /webhook endpoint; both enqueue only |
| AUTO-05 | Crash-safe resume without loss/duplication; per-series serialization | D-67/D-68: in_progress reconciliation on startup + per-series asyncio.Lock |
</phase_requirements>

---

## Summary

Phase 7 is the largest phase in the roadmap: it transforms the proven one-shot CLI (`trezarr run --once`) into a Dockerized, crash-safe, long-running daemon service with a web UI. The translation pipeline (Phases 5–6) is frozen and reused verbatim — this phase only wraps it in a new runtime.

The highest-risk technical area is **async lifecycle ownership**. The current CLI disposes the AsyncEngine inside `asyncio.run()` (CR-01). The long-running service must hold one engine for the entire process lifetime and dispose it in FastAPI `lifespan` SHUTDOWN — the same class of bug appears at process scope if this is wrong. The FastAPI `@asynccontextmanager lifespan` pattern is the correct place for all startup/shutdown resource management (engine, scheduler, worker tasks).

The second risk area is the **queue/worker model**. The decision space covers DB-polling worker vs asyncio.Queue vs APScheduler-job-per-item; the recommended approach (see Architecture Patterns) is a hybrid: the `job` table (D-69) as durable persistence + an `asyncio.Queue` as the in-process runqueue, with a single worker coroutine per concurrent series slot. This satisfies crash-resume (jobs survive process death in the DB), per-series serialization (per-`series_id` asyncio.Lock), and dedup (DB-level uniqueness guard on queued source_path).

The Alembic migration (D-69) is straightforward: author `0002_job_queue.py` with `down_revision = "0001"` to chain off the Phase-4 baseline. The `ProcessedFile` contract is untouched — new tables only. The React 19 + Vite 7 SPA is a functional-first dashboard (Settings, Queue, History, Logs views) built into `frontend/dist/` and served by FastAPI `StaticFiles(html=True)`. The Docker packaging follows the established LSIO base image pattern with a Node build stage.

**Primary recommendation:** Implement in wave order per CONTEXT.md scale note: (W1) service runtime + worker + job/queue persistence + crash-resume → (W2) poll + webhook monitoring → (W3) config read/write + connection tests → (W4) SPA + REST API → (W5) Docker packaging. Each wave is independently testable.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Translation pipeline execution | Backend / worker coroutine | — | `translate_file` is async and CPU-light (LLM I/O bound); belongs entirely in the Python process |
| Job queue persistence + crash-resume | Backend / SQLite | — | Durability requires the DB; in-process asyncio.Queue is ephemeral (lost on crash) |
| Per-series serialization | Backend / asyncio.Lock | — | An ordering constraint on shared SQLite state (Series Bible); owned by the worker |
| APScheduler poll scheduling | Backend / in-process scheduler | — | Single-user daemon; no Redis broker needed |
| Webhook receipt | Backend / FastAPI route | — | HTTP endpoint on the same uvicorn process; enqueues only, no translation in handler |
| Config read/write | Backend / settings service | — | YAML file lives at /config, same process; pydantic-settings owns the read path |
| Secret masking | Backend | — | SecretStr pattern already established in D-11; extended to the HTTP surface |
| Connection tests | Backend / FastAPI routes | — | pyarr ping + minimal LLM call; results return to UI as JSON |
| Queue/History/Logs views | Frontend SPA | Backend REST API | React reads /api/queue + /api/jobs; backend owns the data |
| Config form | Frontend SPA | Backend REST API | React renders the settings form; backend validates and writes |
| Static asset serving | Backend / FastAPI StaticFiles | — | No nginx; FastAPI serves the Vite dist/ directly (D-61, CLAUDE.md) |
| PUID/PGID drop-privilege | Container init / s6-overlay | — | Must happen before the Python process starts; s6-overlay or entrypoint script |

---

## Standard Stack

### Core (already in pyproject.toml — add the missing ones)

| Library | CLAUDE.md Pin | Current Latest | Purpose | Why Standard |
|---------|--------------|----------------|---------|--------------|
| FastAPI | ~0.136 | 0.128.8 [VERIFIED: PyPI registry] | Web framework + REST API | Async-native; Pydantic-native; auto-OpenAPI |
| Uvicorn[standard] | ~0.48 | 0.39.0 [VERIFIED: PyPI registry] | ASGI server | Standard FastAPI prod server |
| APScheduler | ~3.11 | 3.11.2 [VERIFIED: PyPI registry] | In-process job scheduling | No Redis broker; AsyncIOScheduler uses running event loop |
| watchfiles | ~1.2 | 1.1.1 [VERIFIED: PyPI registry] | Filesystem watching (default-off) | Rust-backed, async, debounced |
| httpx | ~0.28 | 0.28.1 [VERIFIED: PyPI registry] | HTTP client (connection tests, Bazarr stubs) | Already a transitive dep; covers *arr calls pyarr misses |

> **Version discrepancy:** CLAUDE.md specifies `fastapi ~0.136` and `uvicorn ~0.48` but PyPI current latest as of 2026-06-02 is `0.128.8` and `0.39.0` respectively. [ASSUMED] These are aspirational/forecast versions not yet released. The planner should pin to `>=0.128,<0.137` (fastapi) and `>=0.39,<0.49` (uvicorn) with a note that CLAUDE.md pins will become available.

### Frontend

| Library | Version | Purpose |
|---------|---------|---------|
| React | 19.2.7 [VERIFIED: npm registry] | SPA framework |
| Vite | 8.0.16 (latest; 7.x = 7.x.x) [VERIFIED: npm registry] | Build tool; Vite 7 = v7.x (stable LTS) |
| @vitejs/plugin-react | 6.0.2 [VERIFIED: npm registry] | React fast-refresh + Babel |
| TypeScript | 6.0.3 [VERIFIED: npm registry] | Type safety in SPA |

> **Vite version note:** CLAUDE.md specifies "Vite 7". The latest Vite as of research time is 8.0.16 with Vite 7 in LTS. [ASSUMED] Pinning to `"vite": "^7"` in frontend/package.json matches the CLAUDE.md intent.

### Already in pyproject.toml (no additions needed)

| Library | Version | Role in Phase 7 |
|---------|---------|-----------------|
| alembic | 1.18.x | New 0002 migration for job/job_log tables |
| pydantic-settings | 2.14.x | Config read; config-writer writes back to YAML |
| sqlalchemy[asyncio] | 2.0.x | Job table ORM + session factory |
| aiosqlite | 0.22.x | Async SQLite driver |
| pydantic | 2.13.x | Job/response DTOs |

**Installation (additions to pyproject.toml):**
```bash
uv add "fastapi>=0.128,<0.137" "uvicorn[standard]>=0.39,<0.49" "apscheduler>=3.11,<3.12" "watchfiles>=1.1,<1.3" "httpx>=0.28,<0.29"
```

**Frontend bootstrap:**
```bash
npm create vite@7 frontend -- --template react-ts
cd frontend && npm install
```

---

## Package Legitimacy Audit

slopcheck was not available at research time. All packages below are well-established with multi-year registry histories.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| fastapi | PyPI | 6 yrs | Very high | github.com/fastapi/fastapi | [ASSUMED] OK | Approved |
| uvicorn | PyPI | 7 yrs | Very high | github.com/encode/uvicorn | [ASSUMED] OK | Approved |
| apscheduler | PyPI | 14 yrs | Very high | github.com/agronholm/apscheduler | [ASSUMED] OK | Approved |
| watchfiles | PyPI | 4 yrs | High | github.com/samuelcolvin/watchfiles | [ASSUMED] OK | Approved |
| httpx | PyPI | 6 yrs | Very high | github.com/encode/httpx | [ASSUMED] OK | Approved |
| react | npm | 11 yrs | Very high | github.com/facebook/react | [ASSUMED] OK | Approved |
| vite | npm | 5 yrs | Very high | github.com/vitejs/vite | [ASSUMED] OK | Approved |
| @vitejs/plugin-react | npm | 4 yrs | High | github.com/vitejs/vite (monorepo) | [ASSUMED] OK | Approved |
| typescript | npm | 13 yrs | Very high | github.com/microsoft/TypeScript | [ASSUMED] OK | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
*slopcheck was unavailable at research time; all packages are tagged [ASSUMED]. Planner may optionally add checkpoint:human-verify before frontend npm install if the security posture demands it, but these are all canonical ecosystem packages.*

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (React SPA)
        |  HTTP REST polling
        v
┌────────────────────────────────────────────────────────────────────┐
│                FastAPI App (uvicorn, port 6868)                      │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              lifespan (asynccontextmanager)                     │  │
│  │  STARTUP:                                                       │  │
│  │    1. assert_media_roots + probe_media_roots                   │  │
│  │    2. build_engine (ONE for process lifetime)                  │  │
│  │    3. run_migrations_to_head (0001 + 0002)                    │  │
│  │    4. build_session_factory                                    │  │
│  │    5. reconcile in_progress rows → enqueue                    │  │
│  │    6. start AsyncIOScheduler (poll job)                        │  │
│  │    7. launch worker coroutine(s) as asyncio.Task(s)           │  │
│  │  yield (app serving requests)                                  │  │
│  │  SHUTDOWN:                                                      │  │
│  │    8. cancel worker tasks; scheduler.shutdown()                │  │
│  │    9. await engine.dispose()          ← CR-01 at process scope │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────┐    ┌───────────────────────────────────┐  │
│  │  REST API Routes      │    │  Monitoring (D-65/D-66)           │  │
│  │  /api/settings        │    │  APScheduler poll interval        │  │
│  │  /api/test/{svc}      │    │  → discover + scan + enqueue      │  │
│  │  /api/queue           │    │                                    │  │
│  │  /api/jobs            │    │  POST /webhook                    │  │
│  │  /api/jobs/{id}/retry │    │  → immediate scan + enqueue       │  │
│  └─────────────────────┘    └───────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Worker Loop (asyncio.Task per series slot, D-68)                │ │
│  │  asyncio.Queue (in-process) ← drained from job table (DB)       │ │
│  │  per-series asyncio.Lock → translate_file() → update job row     │ │
│  │  LLMClient._semaphore (global, D-06) ← the ONLY concurrency cap  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  StaticFiles(directory="frontend/dist", html=True)                   │
│  → catches all non-API routes → returns index.html (SPA fallback)   │
└────────────────────────────────────────────────────────────────────┘
                              │
                         SQLite (aiosqlite)
                    /config/trezarr.db
                    (job, job_log, processed_file, series, ...)
```

### Recommended Project Structure (additions only)

```
trezarr/
├── web/                         # NEW: Phase-7 web layer
│   ├── __init__.py
│   ├── app.py                   # FastAPI app factory + lifespan
│   ├── routes/
│   │   ├── settings.py          # GET/PUT /api/settings; GET /api/settings/env-locked
│   │   ├── test_connection.py   # POST /api/test/{sonarr|radarr|bazarr|llm}
│   │   ├── queue.py             # GET /api/queue, GET /api/jobs, POST /api/jobs/{id}/retry
│   │   └── webhook.py           # POST /webhook (Sonarr/Radarr/Bazarr)
│   ├── worker.py                # Queue worker coroutine(s); per-series lock map
│   ├── scheduler.py             # APScheduler setup + poll job callback
│   └── config_writer.py         # Settings → YAML write-back; secret masking
├── jobs/                        # NEW: job persistence
│   └── models.py                # Job, JobLog SQLAlchemy models (registers with Base)
# existing modules unchanged
├── cli.py                       # ADD `serve` subparser; extract worker callable
├── config.py                    # ADD Phase-7 TrezarrSettings fields (D-76)
frontend/                        # NEW: separate npm package
├── package.json                 # react 19, vite 7, typescript
├── vite.config.ts               # outDir: ../trezarr/web/static OR dist/ (copied in Docker)
├── src/
│   ├── App.tsx
│   ├── pages/
│   │   ├── Settings.tsx
│   │   ├── Queue.tsx
│   │   ├── History.tsx
│   │   └── JobLogs.tsx
│   └── api/
│       └── client.ts            # fetch wrappers for REST API
Dockerfile                       # NEW: multi-stage Node → Python
docker-compose.example.yml       # NEW: alongside *arr stack
```

### Pattern 1: FastAPI lifespan + Engine lifecycle (the CR-01 fix at process scope)

**What:** The `@asynccontextmanager lifespan` function owns ALL startup/shutdown sequencing. The engine is created once before the `yield` and disposed after. This is identical in concept to the CLI's `try/finally` around `engine.dispose()`, but now lives at process scope rather than per-`asyncio.run()` scope.

**Why critical:** The CLI already solved CR-01 by disposing the engine in a `finally` block inside `asyncio.run()`. In the long-running service, `asyncio.run()` wraps the entire uvicorn server lifetime. The engine must outlive all requests and be disposed exactly once — on shutdown. Getting this wrong causes `RuntimeError: Event loop is closed` during process teardown. [VERIFIED: SQLAlchemy 2.0 async docs]

```python
# Source: FastAPI official docs (lifespan) + SQLAlchemy 2.0 async engine docs
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP — ordered exactly as cli.py's _run_once, but at process scope
    settings = TrezarrSettings()
    assert_media_roots_configured(settings)
    media_roots = build_media_roots(settings)
    probe_media_roots(media_roots)

    engine = build_engine(settings)           # ONE engine for process lifetime
    try:
        await run_migrations_to_head(engine)  # 0001 + 0002
        session_factory = build_session_factory(engine)
        await _reconcile_in_progress(session_factory)   # D-67 crash-resume

        scheduler = AsyncIOScheduler()
        scheduler.add_job(poll_callback, 'interval',
                          seconds=settings.poll_interval_seconds,
                          kwargs={"session_factory": session_factory, ...})
        if settings.enable_webhooks:
            pass  # webhook routes already registered; no extra start needed
        scheduler.start()

        worker_task = asyncio.create_task(worker_loop(session_factory, settings))

        # Store shared state for routes to access
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.settings = settings

        yield     # ← app is now serving requests

    finally:
        # SHUTDOWN — reverse order
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        scheduler.shutdown(wait=False)
        await engine.dispose()    # CR-01 fix at process scope

app = FastAPI(lifespan=lifespan)
```

### Pattern 2: DB-backed job queue + in-process asyncio.Queue hybrid (recommended for D-69)

**What:** The `job` table provides durability (crash-survive); an `asyncio.Queue` bridges the DB to the worker coroutine as the in-process runqueue.

**Why this approach over pure DB polling or pure asyncio.Queue:**
- Pure asyncio.Queue: loses all queued work on crash (violates AUTO-05).
- Pure DB polling: every worker tick needs a SELECT, adding latency + complexity.
- Hybrid: DB is source of truth; asyncio.Queue is the hot path. On startup, `_reconcile_in_progress` re-enqueues from DB to Queue. The worker pops from Queue, transitions job to `running`, executes, transitions to `done`/`failed`. [ASSUMED: pattern derived from snappea/persist-queue approaches, verified as sound for single-process asyncio]

```python
# Source: pattern synthesized from SQLite job queue literature [ASSUMED]
from asyncio import Queue as AioQueue
from trezarr.jobs.models import Job, JobStatus

_work_queue: AioQueue = AioQueue()
_series_locks: dict[int, asyncio.Lock] = {}

async def enqueue_job(session_factory, source_path: str, series_id: int,
                       trigger: str) -> bool:
    """Return False if already queued/running (dedup guard)."""
    async with session_factory() as session:
        async with session.begin():
            # Dedup: skip if a job for this source_path is queued or running
            existing = await session.execute(
                select(Job).where(
                    Job.source_path == source_path,
                    Job.status.in_(["queued", "running"])
                )
            )
            if existing.scalar_one_or_none():
                return False
            job = Job(source_path=source_path, series_id=series_id,
                      status="queued", trigger=trigger)
            session.add(job)
        await _work_queue.put(job.id)
    return True

async def worker_loop(session_factory, settings):
    """Single worker coroutine — pulled from asyncio.Queue, serialized per series."""
    while True:
        job_id = await _work_queue.get()
        # Acquire per-series lock (D-68) — limits concurrent series to worker_max_concurrent_series
        lock = _series_locks.setdefault(series_id, asyncio.Lock())
        async with lock:
            await _execute_job(job_id, session_factory, settings)
        _work_queue.task_done()
```

**Startup reconciliation (D-67):**
```python
async def _reconcile_in_progress(session_factory):
    """On startup, re-enqueue any job rows left 'running' or 'queued' by a crashed process."""
    async with session_factory() as session:
        result = await session.execute(
            select(Job).where(Job.status.in_(["queued", "running"]))
        )
        for job in result.scalars():
            job.status = "queued"          # reset running→queued
            await _work_queue.put(job.id)
        await session.commit()
    # Also re-enqueue any processed_file rows with status='in_progress'
    # that have no corresponding Job row (crash before job row was created)
    ...
```

### Pattern 3: Per-series asyncio.Lock (D-68)

**What:** A dict maps `series_id → asyncio.Lock`. Worker acquires the lock before calling `translate_file`; releases after. Distinct series run concurrently (no lock contention between series). The `LLMClient._semaphore` (D-06) remains the single global cap on concurrent LLM calls.

**Critical invariant (Pitfall C):** Do NOT introduce a second `asyncio.Semaphore` around the per-item translate call. The D-06 semaphore is already inside `LLMClient` and gates all LLM calls. A second semaphore at the worker level would double-cap and create a potential deadlock when `worker_max_concurrent_series` × per-series work exceeds the LLM semaphore budget.

```python
# Per-series lock map — created lazily, never deleted (process lifetime is bounded)
_series_locks: dict[int, asyncio.Lock] = {}

async def _execute_job(job_id: int, session_factory, settings):
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        series_id = job.series_id

    lock = _series_locks.setdefault(series_id, asyncio.Lock())
    async with lock:
        # The existing translate_file is called unchanged
        result = await translate_file(
            job.source_path, settings, llm_client, ledger,
            eligible_item=..., session_factory=session_factory
        )
```

### Pattern 4: Alembic migration 0002 (D-69) — chaining off the baseline

**What:** A new migration file `alembic/versions/0002_job_queue.py` with `down_revision = "0001"`. It adds `job` and `job_log` tables WITHOUT touching any of the 7 tables from 0001. SQLite `render_as_batch=True` is already enabled in `env.py` (Alembic env.py — verified in codebase). [VERIFIED: codebase inspection]

**Recommended job table shape:**
```python
# Source: D-69 + CONTEXT.md job shape + SQLAlchemy 2.0 typed models
class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','failed','quarantined')",
            name="ck_job_status",
        ),
        CheckConstraint(
            "trigger IN ('poll','webhook','manual-retry','startup-reconcile')",
            name="ck_job_trigger",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

class JobLog(Base):
    __tablename__ = "job_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String, nullable=False)   # DEBUG/INFO/WARNING/ERROR
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
```

**Alembic migration file header:**
```python
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
```

**IMPORTANT:** The new `Job` and `JobLog` models must be imported in `alembic/env.py` (or in `trezarr/bible/models.py`) so `Base.metadata` picks them up for autogenerate. The established pattern imports `trezarr.bible.models` — the new `trezarr.jobs.models` module must also be imported. [VERIFIED: codebase inspection of alembic/env.py]

### Pattern 5: APScheduler AsyncIOScheduler in FastAPI lifespan

**What:** Create `AsyncIOScheduler` before `yield`, call `scheduler.start()` in startup, `scheduler.shutdown()` in shutdown. The scheduler runs jobs in the existing asyncio event loop (no thread-pool overhead for async jobs). [VERIFIED: APScheduler 3.x docs]

```python
# Source: APScheduler 3.x user guide + FastAPI community patterns
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Inside lifespan startup:
scheduler.add_job(
    poll_and_enqueue,          # async coroutine function
    'interval',
    seconds=settings.poll_interval_seconds,
    id='main_poll',
    replace_existing=True,
    kwargs={"session_factory": session_factory, "settings": settings}
)
scheduler.start()

# Inside lifespan shutdown:
scheduler.shutdown(wait=False)  # wait=False avoids blocking if a job is mid-run
```

**Important:** `AsyncIOScheduler` uses the running event loop at `start()` time. It MUST be started inside the lifespan (inside an async context), not at module import time. Starting it at module import time would use a loop that may not be the uvicorn loop. [ASSUMED from APScheduler docs pattern analysis]

### Pattern 6: FastAPI SPA static file serving

**What:** Mount the built `frontend/dist/` as StaticFiles with `html=True`. This makes FastAPI serve `index.html` for any path that doesn't match an existing static file — the standard SPA routing fallback. API routes must be mounted BEFORE the static files mount so they take precedence. [VERIFIED: FastAPI official docs]

```python
# Source: FastAPI static files docs
from fastapi.staticfiles import StaticFiles
import os

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")  # or "../../frontend/dist"

# Register API routers FIRST
app.include_router(settings_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(webhook_router)

# Mount static files LAST — catches everything else
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
```

**Build integration:** The Docker Node stage runs `npm run build` from `frontend/`, producing `frontend/dist/`. The Python stage copies `frontend/dist/` to `trezarr/web/static/` (or a path it can serve at runtime).

### Pattern 7: Config read/write service + secret masking (D-70)

**What:** pydantic-settings is read-only by design. Phase 7 adds a config-writer that (a) loads current settings for display, masking secrets, and (b) writes UI edits back to `/config/config.yaml`. [VERIFIED: pydantic-settings docs; write-back pattern is a custom addition]

```python
# Source: CLAUDE.md § config + D-70 [ASSUMED write-back pattern — pydantic-settings has no built-in writer]
import yaml
from pydantic import SecretStr

SECRET_FIELDS = {"llm_api_key", "sonarr_api_key", "radarr_api_key", "bazarr_api_key"}
SENTINEL = "**REDACTED**"

def settings_to_display_dict(settings: TrezarrSettings) -> dict:
    """Return settings as a dict for the UI — secrets replaced with sentinel."""
    raw = settings.model_dump()
    for field in SECRET_FIELDS:
        if field in raw:
            val = getattr(settings, field)
            raw[field] = {"is_set": bool(val and val.get_secret_value()), "value": SENTINEL}
    return raw

def write_settings_to_yaml(current: TrezarrSettings, patch: dict) -> None:
    """Merge patch into current config and write to CONFIG_PATH.
    
    Rules:
    - If patch[secret_field] is SENTINEL or absent → keep existing secret (don't overwrite)
    - Env-var-locked fields are not written to YAML (they'd be silently ignored anyway)
    - Uses yaml.safe_dump — comment preservation is NOT guaranteed (D-70 mvp acceptable)
    """
    try:
        with open(CONFIG_PATH, "r") as f:
            existing = yaml.safe_load(f) or {}
    except FileNotFoundError:
        existing = {}

    for key, value in patch.items():
        if key in SECRET_FIELDS and value == SENTINEL:
            continue   # don't overwrite stored secret
        existing[key] = value

    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(existing, f, default_flow_style=False, allow_unicode=True)
```

**Env-locked field detection:** The UI should call `GET /api/settings/env-locked` which returns field names currently overridden by environment variables (compare env layer vs YAML layer). This signals to the user why a saved value "didn't take".

### Pattern 8: Per-job structured log capture (D-75)

**What:** A custom `logging.Handler` subclass that writes records to the `job_log` table, bound to the current job via a `contextvars.ContextVar`. This is injected into the logging tree for the duration of each job execution. [VERIFIED: Python logging docs, contextvars stdlib]

```python
# Source: Python logging cookbook + contextvars stdlib docs
import logging
import contextvars

_current_job_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_job_id", default=None
)

class JobLogHandler(logging.Handler):
    def __init__(self, session_factory):
        super().__init__()
        self._session_factory = session_factory

    def emit(self, record: logging.LogRecord):
        job_id = _current_job_id.get()
        if job_id is None:
            return
        # asyncio-safe: schedule the DB write as a task rather than blocking
        asyncio.get_event_loop().call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._write(job_id, record))
        )

    async def _write(self, job_id: int, record: logging.LogRecord):
        async with self._session_factory() as session:
            session.add(JobLog(job_id=job_id, level=record.levelname,
                               message=self.format(record)))
            await session.commit()
```

**Usage in worker:**
```python
async def _execute_job(job_id, ...):
    token = _current_job_id.set(job_id)
    try:
        # ... call translate_file ...
    finally:
        _current_job_id.reset(token)
```

### Pattern 9: Uvicorn programmatic launch (for `trezarr serve`)

```python
# Source: uvicorn docs — programmatic launch
import uvicorn

def run_serve(settings: TrezarrSettings):
    uvicorn.run(
        "trezarr.web.app:app",
        host=settings.web_host,
        port=settings.web_port,
        log_level="info",
        # Do NOT use reload=True in production — single-process daemon
    )
```

For graceful shutdown signal handling (SIGTERM in Docker), use the `uvicorn.Server` + `uvicorn.Config` class API which exposes a `.handle_exit()` hook. [VERIFIED: uvicorn docs]

### Pattern 10: Sonarr/Radarr webhook payload shape

Sonarr/Radarr webhook payloads (via Settings → Connect → Webhook) for `Download`/`EpisodeFileDelete`/`Upgrade` events include: [VERIFIED: community docs, Sonarr issue tracker]

```json
{
  "eventType": "Download",
  "isUpgrade": false,
  "series": { "id": 1, "title": "...", "path": "/tv/Show", "tvdbId": ... },
  "episodes": [{ "id": 101, "episodeNumber": 1, "seasonNumber": 1, "title": "..." }],
  "episodeFile": { "id": 50, "relativePath": "Season 01/file.mkv", "path": "/tv/Show/Season 01/file.mkv" }
}
```

Radarr uses `"movie"` + `"movieFile"` keys instead of `series/episodes/episodeFile`.

**Webhook handler strategy (D-66):** Do NOT attempt to parse and trust the payload path. Instead, use the `series.id` / `movie.id` to trigger a targeted discovery scan via pyarr (the authoritative source). This is more resilient to payload schema drift. [ASSUMED: defensive pattern based on PITFALLS.md *arr webhook reliability note]

### Pattern 11: Bazarr webhook (Phase 7 scope fence)

Bazarr's outgoing webhook sends a POST to a configured URL when certain events occur (e.g., subtitle downloaded). [MEDIUM confidence — Bazarr wiki does not publish the JSON schema for outgoing events; it documents only the Plex inbound webhook format.]

**Phase 7 scope:** Trezarr only RECEIVES Bazarr webhooks as a trigger; the actual content is not consumed for subtitle state (that's Phase 10). The handler should accept the POST, log the event, and trigger a discovery scan (same as Sonarr/Radarr handler). [ASSUMED: approach consistent with D-65/D-66 "never trust webhook payload, trigger scan instead"]

**Open question:** Bazarr outgoing webhook URL configuration and JSON schema are not publicly documented. When implementing the Bazarr connection, validate against a live Bazarr instance or the Bazarr source code. Field `bazarr_enabled` defaults to `False` (D-76), so this is a risk-free partial implementation at the connection layer.

### Anti-Patterns to Avoid

- **Starting AsyncEngine at module import time:** Engine must be created inside the lifespan (inside async context). Module-level `engine = build_engine(TrezarrSettings())` on import causes PRAGMA listeners to target the wrong event loop and the engine cannot be disposed cleanly on shutdown.
- **Calling `scheduler.start()` outside lifespan:** APScheduler 3.x `AsyncIOScheduler.start()` binds to the running event loop at call time. Calling it at module scope (before uvicorn has started its loop) attaches to a different loop. Always start inside `lifespan`.
- **Introducing a second asyncio.Semaphore in the worker:** The `LLMClient._semaphore` (D-06) is the single global cap. A semaphore around the worker's per-item dispatch would double-cap and fight the LLM semaphore. Per-series serialization uses `asyncio.Lock`, not `asyncio.Semaphore`.
- **Mounting StaticFiles before API routes:** FastAPI route matching is ordered. If StaticFiles is mounted at `/` first, it intercepts all API requests before the API routers run. Always register API routers before the static mount.
- **Translating inside the webhook handler:** The `POST /webhook` handler must return 200 within the HTTP timeout. Any LLM work blocks the handler and causes Sonarr/Radarr to consider the webhook failed. Enqueue only; never `await translate_file()` in a route handler.
- **Writing secrets to logs or API responses:** The D-70 masking rule extends to the new HTTP surface. Use `settings.llm_api_key.get_secret_value()` only inside LLMClient; never in route handlers, test-connection logs, or error messages.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SPA routing fallback (index.html for 404s) | Custom middleware checking every path | `StaticFiles(html=True)` | Built-in Starlette behavior; handles asset serving + SPA fallback in one mount |
| Async scheduler for polling | Custom `asyncio.sleep` loop in a task | APScheduler `AsyncIOScheduler` | Handles missed-fire policy, jitter, job state; `sleep` loops don't survive scheduler restart, don't handle exceptions per-job |
| PUID/PGID drop-privilege | Custom UID-setting startup script | LSIO base image + s6-overlay (or `python:3.12-slim` with the standard LSIO entrypoint pattern) | s6-overlay is the de-facto standard in the *arr ecosystem; hand-rolling drops privileges inconsistently across different distros |
| Config YAML write-back | Rolling your own serialization | `yaml.safe_dump(model_dump_filtered, f)` with custom filtering | pydantic-settings has no write-back; `yaml.safe_dump` handles the serialization cleanly |
| Per-job log capture | String-building log aggregation | `logging.Handler` subclass + `ContextVar` | Standard Python logging integration; captures all `logger.info(...)` calls from any depth of the call stack |
| Connection tests | Parsing pyarr exception messages | `pyarr.get_system_status()` call + except | pyarr encapsulates the *arr HTTP surface; exception hierarchy (`PyarrConnectionError`, `PyarrResourceNotFound`) gives clean error discrimination |
| Docker HEALTHCHECK | Bash scripts checking port | `curl -f http://localhost:6868/api/health || exit 1` | A trivial FastAPI `GET /api/health → 200` endpoint is the standard pattern |

**Key insight:** The most complex custom work in this phase is the DB-backed queue + per-series lock model. Everything else has a library or established pattern.

---

## Runtime State Inventory

> Phase 7 adds the daemon service on top of existing CLI infrastructure. This is not a rename/migration phase. However, the engine lifecycle change from per-run to per-process is a runtime state ownership change worth documenting.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `processed_file` rows with `status='in_progress'` in `/config/trezarr.db` — pre-built by Phase 4 exactly for this purpose | code: startup reconciliation re-enqueues these rows (D-67) |
| Live service config | n/a — service does not exist yet; this phase creates it | n/a |
| OS-registered state | No task scheduler entries, no pm2 processes | none |
| Secrets/env vars | Existing `TREZARR_OPENAI_API_KEY`, `TREZARR_SONARR_API_KEY`, `TREZARR_RADARR_API_KEY` remain valid; Phase 7 adds `TREZARR_BAZARR_API_KEY` | new env var name documented in config.yaml.example |
| Build artifacts | No stale artifacts — this phase adds new code only | none |

**Nothing found requiring migration:** the in_progress ledger semantics were pre-built in Phase 4 specifically for this phase.

---

## Common Pitfalls

### Pitfall A: AsyncEngine created at module scope — "RuntimeError: Event loop is closed"

**What goes wrong:** If `build_engine()` is called at module import time (e.g., as a module-level variable), the PRAGMA event listeners register against whatever event loop exists at import time, which may not be the uvicorn loop. On shutdown, the engine is finalized by the garbage collector — but without an async context, `await engine.dispose()` cannot be called, and aiosqlite worker threads schedule onto the closed loop. This is the exact CR-01 bug from the CLI, reproduced at process scope.

**Why it happens:** Moving from `asyncio.run(main())` to uvicorn's `asyncio.run(server.serve())` changes who owns the event loop. Any global async resource created before uvicorn starts will not be on the correct loop.

**How to avoid:** Create the engine inside the lifespan function (inside `async with`). Store it in `app.state`. Dispose it in the shutdown half of lifespan (after `yield`). [VERIFIED: SQLAlchemy 2.0 async docs]

**Warning signs:** `RuntimeError: Event loop is closed` in uvicorn teardown logs; `ResourceWarning: unclosed connection` on process exit.

### Pitfall B: APScheduler started outside lifespan / at module scope

**What goes wrong:** `AsyncIOScheduler.start()` binds to the CURRENT running asyncio event loop. If called at module scope (before uvicorn's event loop is running), it attaches to Python's default loop, not uvicorn's. Jobs run in the wrong loop; async job coroutines may fail silently or use wrong connections.

**How to avoid:** Call `scheduler.start()` strictly inside the lifespan's startup section (between function start and `yield`). [VERIFIED: APScheduler 3.x docs]

**Warning signs:** Jobs never fire; `RuntimeError: This event loop is already running` in APScheduler logs; async jobs raising `RuntimeError: no running event loop`.

### Pitfall C: Double-semaphore / per-series semaphore fighting the LLM semaphore

**What goes wrong:** A developer introduces a second `asyncio.Semaphore(worker_max_concurrent_series)` at the worker level, thinking this caps concurrent series. But the `LLMClient._semaphore` (D-06) is already counting acquire/release calls. With both semaphores active, a series waiting on the per-series semaphore holds the per-series semaphore slot while every LLM call inside it competes for the global semaphore. Under load, `worker_max_concurrent_series` × `llm_max_concurrency` tasks may be waiting simultaneously, exceeding memory expectations and causing priority inversion.

**How to avoid:** Use `asyncio.Lock` per series (D-68) — this is a BINARY ownership primitive, not a bounded counter. Only one coroutine at a time works on a series; other series continue freely. The only global cap is `LLMClient._semaphore`. [VERIFIED: codebase + D-68 decision]

### Pitfall D: Webhook handler blocks on discovery/translation

**What goes wrong:** The webhook handler awaits `discover_sonarr_items()` or, worse, `translate_file()` before returning. Sonarr/Radarr have a short webhook timeout (usually 3–10 seconds). If discovery or translation takes longer, *arr marks the webhook delivery as failed and may disable the connection.

**How to avoid:** Webhook handler does minimum work: validate the payload shape, call `enqueue_job()` (one DB INSERT + one `asyncio.Queue.put_nowait()`), return `{"status": "accepted"}` with HTTP 200. All discovery and translation happens asynchronously in the worker loop.

### Pitfall E: StaticFiles mount shadowing API routes

**What goes wrong:** `app.mount("/", StaticFiles(...))` registered before `app.include_router(api_router, prefix="/api")` causes all requests — including API requests — to be handled by the static file server, which returns 404 for files that don't exist as static assets.

**How to avoid:** Always register all API routers BEFORE mounting static files. FastAPI matches routes in registration order; the static mount must be last. [VERIFIED: FastAPI docs]

### Pitfall F: New Job/JobLog models not imported in alembic/env.py

**What goes wrong:** Alembic autogenerate compares `Base.metadata` against the live DB. If `trezarr.jobs.models` is not imported before Alembic runs, the `Job` and `JobLog` tables are missing from `Base.metadata` and autogenerate will not include them in the migration.

**How to avoid:** Add `from trezarr.jobs import models as _job_models  # noqa: F401` in `alembic/env.py` alongside the existing `from trezarr.bible import models` import. This pattern is already established in the codebase. [VERIFIED: codebase inspection of alembic/env.py]

### Pitfall G: pydantic-settings precedence makes UI writes appear to silently fail

**What goes wrong:** The user saves a config value via the UI. The config-writer writes it to `/config/config.yaml`. But the same field is also set as a `TREZARR_*` environment variable (higher priority). On reload, the env var wins and the YAML value is invisible. The user sees their change revert with no error.

**How to avoid:** On `GET /api/settings`, return a map of which fields are currently "env-locked" (their effective value comes from an env var). The UI should display these fields as read-only with a note "set via environment variable". The config-writer should detect env-locked fields and warn (or refuse) rather than silently writing a value that will be ignored. [VERIFIED: pydantic-settings source priority order]

### Pitfall H: Docker COPY of frontend/dist fails at build time if `npm run build` was not run

**What goes wrong:** The multi-stage Dockerfile copies `frontend/dist/` from the Node stage. If the Node stage's `RUN npm run build` fails (missing dependency, TypeScript error), the build fails. In development, if the dist/ directory doesn't exist and the code tries to `StaticFiles(directory="...")` on a non-existent path, FastAPI raises on startup.

**How to avoid:** Guard the `StaticFiles` mount: `if os.path.exists(STATIC_DIR)` before mounting. In development (no built dist), the SPA is simply not served — the API works fine. Log a WARNING when STATIC_DIR is missing. [ASSUMED: defensive pattern]

### Pitfall I: Job log handler emit() called from non-event-loop thread

**What goes wrong:** Some logging calls inside `translate_file` may fire from background threads (aiosqlite uses threads internally; tenacity callbacks may fire from non-async contexts). The `JobLogHandler.emit()` method needs to schedule the DB write onto the event loop safely.

**How to avoid:** Use `asyncio.get_event_loop().call_soon_threadsafe(lambda: asyncio.ensure_future(...))` in `emit()`, or better, buffer log records into an `asyncio.Queue` that the event loop drains. An even simpler mvp: write log records to an in-memory list attached to the job, flush to DB when the job finishes. [ASSUMED: pattern synthesized from Python logging cookbook]

---

## Code Examples

### FastAPI complete lifespan skeleton
```python
# Source: FastAPI official docs + SQLAlchemy 2.0 async engine patterns [VERIFIED]
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio, os

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = TrezarrSettings()
    assert_media_roots_configured(settings)
    media_roots = build_media_roots(settings)
    probe_media_roots(media_roots)

    engine = build_engine(settings)
    try:
        await run_migrations_to_head(engine)   # runs 0001 + 0002
        session_factory = build_session_factory(engine)
        await _reconcile_in_progress(session_factory)

        scheduler = AsyncIOScheduler()
        scheduler.add_job(poll_and_enqueue, 'interval',
                          seconds=settings.poll_interval_seconds,
                          id='poll', replace_existing=True,
                          kwargs=dict(session_factory=session_factory, settings=settings))
        scheduler.start()

        worker_tasks = [
            asyncio.create_task(worker_loop(session_factory, settings))
            for _ in range(settings.worker_max_concurrent_series)
        ]
        app.state.session_factory = session_factory
        app.state.settings = settings
        yield
    finally:
        for t in worker_tasks:
            t.cancel()
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        scheduler.shutdown(wait=False)
        await engine.dispose()           # CR-01 fix at process scope

app = FastAPI(lifespan=lifespan)
app.include_router(api_router, prefix="/api")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
```

### Webhook route (enqueue-only pattern)
```python
# Source: D-66 decision + FastAPI route pattern [ASSUMED per D-66 contract]
from fastapi import APIRouter, Request
router = APIRouter()

@router.post("/webhook")
async def receive_webhook(request: Request):
    """Accept any webhook; trigger a targeted discovery scan asynchronously."""
    body = await request.json()
    event_type = body.get("eventType", "unknown")
    series_id = body.get("series", {}).get("id")   # Sonarr; Radarr uses "movie"
    # Trigger a scan task — do NOT await translate_file here
    asyncio.create_task(
        poll_and_enqueue(request.app.state.session_factory,
                         request.app.state.settings,
                         series_id_hint=series_id)
    )
    return {"status": "accepted", "eventType": event_type}
```

### Alembic migration 0002 header
```python
# Source: alembic/versions/0001_baseline_bible_schema.py pattern [VERIFIED: codebase]
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("job", ...)      # see job table shape above
    op.create_table("job_log", ...)

def downgrade() -> None:
    op.drop_table("job_log")
    op.drop_table("job")
```

### TrezarrSettings Phase-7 additions
```python
# Source: D-76 + config.py Phase-N grouping pattern [VERIFIED: codebase]
    # ── Phase 7: Service runtime (D-76) ────────────────────────────────────────
    web_host: str = "0.0.0.0"
    web_port: int = 6868
    poll_interval_seconds: int = 900           # 15 minutes
    enable_webhooks: bool = True               # D-77: toggle webhook receiver
    enable_watchfiles: bool = False            # D-65: default-off; deferred
    worker_max_concurrent_series: int = 2      # D-68: distinct series in parallel

    # ── Phase 7: Bazarr connection (D-76) ──────────────────────────────────────
    # Connection + webhook ONLY. Inventory reads are Phase 10 (INTG-02).
    bazarr_host: str = ""
    bazarr_port: int = 6767
    bazarr_api_key: SecretStr = SecretStr("")
    bazarr_enabled: bool = False
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI `@app.on_event("startup")` / `@app.on_event("shutdown")` | `@asynccontextmanager lifespan` parameter | FastAPI 0.95+ (stable) | Cleaner resource scoping; deprecation warning if using old events |
| APScheduler 3.x with BackgroundScheduler | AsyncIOScheduler for async apps | Established in 3.x | No thread pool needed; jobs run in the app's event loop |
| Docker COPY of requirements.txt + pip install | `uv sync --frozen` in Dockerfile | 2024/2025 | Faster, reproducible builds with lockfile |
| Serving React SPA from nginx in the same image | FastAPI `StaticFiles(html=True)` | Established pattern | Eliminates nginx process; single process model |
| Alembic autogenerate for all migrations | Hand-authored migrations for safety | Project convention (0001) | Avoids drift risk on critical schema |

**Deprecated/outdated:**
- FastAPI `@app.on_event`: deprecated in favor of lifespan; do not use for new code
- APScheduler `BackgroundScheduler` in an async app: works but spawns unnecessary threads; use `AsyncIOScheduler`
- `uvicorn.run(app)` with `reload=True` in production containers: reload mode forks subprocesses which conflict with in-process state (scheduler, engine); always `reload=False` in production

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FastAPI 0.136.x and uvicorn 0.48.x are aspirational CLAUDE.md versions not yet released; current is 0.128.x / 0.39.x | Standard Stack | Planner should pin to current released versions; if 0.136/0.48 release before execution, upgrade is straightforward (no API breaks expected in minor version range) |
| A2 | APScheduler `AsyncIOScheduler.start()` must be called inside an async context (after uvicorn's loop is running) | Pitfall B, Pattern 5 | If this is wrong and module-scope start works, it's a non-issue; getting it wrong causes scheduler to bind to wrong loop |
| A3 | Bazarr outgoing webhook JSON schema is undocumented; Phase 7 uses a scan-trigger-only approach (ignoring payload content) | Pattern 11 | If Bazarr's schema is well-defined and reliable, could parse it for faster targeting; but ignoring payload is always safe |
| A4 | `worker_max_concurrent_series = 2` is a reasonable default; planner may tune | TrezarrSettings pattern | Too low = slow backfill; too high = LLM semaphore contention; 2 is conservative and safe |
| A5 | DB-backed job queue + asyncio.Queue hybrid is the right queue model for D-69 | Pattern 2 | Pure asyncio.Queue would lose in-flight work on crash (violates AUTO-05); pure DB polling adds latency; hybrid is established pattern |
| A6 | watchfiles 1.2 (CLAUDE.md) maps to 1.1.1 (current PyPI latest); no 1.2.x released yet | Standard Stack | Pin `>=1.1,<1.3` covers both |
| A7 | The per-job log handler emit() threading concern can be solved with an in-memory buffer flushed at job end for mvp | Pitfall I, Pattern 8 | Full asyncio-safe handler is more correct but adds complexity; buffer approach is safe for single-process daemon |
| A8 | SPAStaticFiles with `html=True` handles all SPA routing fallback cases in FastAPI | Pattern 6 | Starlette `html=True` serves index.html for 404s within the mount; if edge cases exist (query strings), a custom SPAStaticFiles subclass is the fallback |

---

## Open Questions

1. **LSIO base image vs python:3.12-slim for PUID/PGID**
   - What we know: LSIO base (`ghcr.io/linuxserver/baseimage-alpine`) provides s6-overlay + PUID/PGID for free. The PUID/PGID mechanism (`id $user` → env vars → container UID change) is well-documented at docs.linuxserver.io. `apply_permissions` in the codebase already handles the in-process ownership fix.
   - What's unclear: The LSIO Python base image (`ghcr.io/linuxserver/baseimage-python`) may add Alpine-vs-Debian conflicts with some Python packages compiled for glibc. `python:3.12-slim` is Debian-based and has fewer compatibility issues with wheels.
   - Recommendation: Default to `python:3.12-slim` + a small s6-like entrypoint script for MVP (simpler, fewer unknowns). Upgrade to the full LSIO base for Phase 9 or a v1.1 hardening pass if PUID/PGID edge cases are reported.

2. **watchfiles optional wiring depth for MVP**
   - What we know: D-65/D-77 say `enable_watchfiles = False` default; poll + webhook satisfy AUTO-02.
   - What's unclear: Should Phase 7 ship the watchfiles code as scaffolded (settings field + import guard) but with no actual `watchfiles.awatch()` call, or as a fully-wired feature toggle?
   - Recommendation: Scaffold only — add the settings field, add a startup log "watchfiles disabled (enable_watchfiles=False)", no `awatch()` call. The poll + webhook path is tested; watchfiles can be wired in a follow-up PR.

3. **Hot-reload scope for settings changes (D-72)**
   - What we know: Re-instantiating `LLMClient(settings)` and `pyarr.SonarrAPI(...)` is cheap. The scheduler interval job can be rescheduled via APScheduler's `scheduler.reschedule_job()`.
   - What's unclear: Database URL changes (`bible_db_url`) require engine disposal and recreation — this is a restart-required case. The UI must clearly indicate which fields require a restart.
   - Recommendation: Hot-reload for: LLM endpoint/model/key, *arr connection settings, poll interval, semaphore limits. Restart-required for: `bible_db_url`, `web_host`, `web_port`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Frontend build (Vite) | ✓ | v25.2.1 | — |
| npm | Frontend package management | ✓ | 11.6.2 | — |
| Docker | Container build + testing | ✓ | 29.2.1 | — |
| Python 3.12 | Runtime | ✓ | 3.12.12 | — |
| uv | Package management | ✓ | 0.11.8 | pip |
| fastapi/uvicorn/apscheduler | Phase 7 service deps | ✗ (not yet in pyproject.toml) | need to add | n/a |
| watchfiles | Optional filesystem watcher | ✗ (not yet in pyproject.toml) | need to add | default-off |

**Missing dependencies with no fallback:**
- `fastapi`, `uvicorn[standard]`, `apscheduler`, `httpx` must be added to `pyproject.toml` as part of Wave 1.

**Missing dependencies with fallback:**
- `watchfiles` — not needed for MVP; poll + webhook cover AUTO-02 with `enable_watchfiles=False`.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing, asyncio_mode=auto) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -x -q --timeout=30` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SVC-01 | lifespan startup/shutdown without error | integration (in-process uvicorn) | `pytest tests/web/test_lifespan.py -x` | No — Wave 0 |
| SVC-01 | Engine disposed on shutdown (no CR-01) | unit | `pytest tests/web/test_lifespan.py::test_engine_disposed_on_shutdown -x` | No — Wave 0 |
| SVC-01 | `trezarr serve` CLI subcommand registered | unit | `pytest tests/test_cli.py::test_serve_subcommand_exists -x` | No — Wave 0 (add to test_cli.py) |
| SVC-02 | GET /api/settings returns masked secrets | unit | `pytest tests/web/test_settings_api.py::test_secrets_masked -x` | No — Wave 0 |
| SVC-02 | PUT /api/settings writes to config.yaml | unit | `pytest tests/web/test_settings_api.py::test_settings_write -x` | No — Wave 0 |
| SVC-02 | POST /api/test/sonarr returns ok/error | unit (mocked pyarr) | `pytest tests/web/test_connection_tests.py::test_sonarr_connection_ok -x` | No — Wave 0 |
| SVC-03 | GET /api/queue returns job rows | unit | `pytest tests/web/test_jobs_api.py::test_get_queue -x` | No — Wave 0 |
| SVC-03 | GET /api/jobs returns history | unit | `pytest tests/web/test_jobs_api.py::test_get_history -x` | No — Wave 0 |
| SVC-04 | POST /api/jobs/{id}/retry re-enqueues | unit | `pytest tests/web/test_jobs_api.py::test_retry_requeues -x` | No — Wave 0 |
| AUTO-02 | Webhook POST triggers enqueue | unit | `pytest tests/web/test_webhook.py::test_webhook_enqueues -x` | No — Wave 0 |
| AUTO-02 | Webhook handler returns 200 immediately | unit | `pytest tests/web/test_webhook.py::test_webhook_returns_200_fast -x` | No — Wave 0 |
| AUTO-05 | in_progress rows re-enqueued on startup reconcile | unit | `pytest tests/web/test_worker.py::test_reconcile_in_progress -x` | No — Wave 0 |
| AUTO-05 | Two episodes of same series run serially | unit | `pytest tests/web/test_worker.py::test_per_series_serialization -x` | No — Wave 0 |
| AUTO-05 | Two episodes of distinct series run concurrently | unit | `pytest tests/web/test_worker.py::test_distinct_series_concurrent -x` | No — Wave 0 |
| D-68 | Single LLMClient._semaphore not doubled | unit | `pytest tests/web/test_worker.py::test_no_second_semaphore -x` | No — Wave 0 |
| D-69 | Alembic 0002 migration runs cleanly | integration | `pytest tests/db/test_migrations.py::test_0002_migration -x` | No — Wave 0 |
| D-70 | SecretStr field never appears in GET /api/settings response | unit | `pytest tests/web/test_settings_api.py::test_secret_never_in_response -x` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q --timeout=30 -k "not integration"`
- **Per wave merge:** `uv run pytest tests/ -v --timeout=60`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/web/__init__.py` — new test package
- [ ] `tests/web/test_lifespan.py` — SVC-01, engine lifecycle
- [ ] `tests/web/test_settings_api.py` — SVC-02, secret masking, write-back
- [ ] `tests/web/test_connection_tests.py` — SVC-02, connection test endpoints
- [ ] `tests/web/test_jobs_api.py` — SVC-03, SVC-04, queue/history/retry
- [ ] `tests/web/test_webhook.py` — AUTO-02, webhook handler
- [ ] `tests/web/test_worker.py` — AUTO-05, D-68, per-series lock
- [ ] `tests/db/test_migrations.py` — D-69, Alembic 0002 migration

---

## Security Domain

`security_enforcement` is enabled and `security_asvs_level = 1`. Block on `high`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (D-78 single-user no-auth trusted-LAN) | n/a for v1; document as deferred |
| V3 Session Management | No | n/a |
| V4 Access Control | No | n/a |
| V5 Input Validation | Yes | Pydantic model validation on all request bodies; path parameters validated by FastAPI |
| V6 Cryptography | No | Secrets stored in SecretStr / env vars; no custom crypto |
| V7 Error Handling | Yes | Never echo API keys/secrets in error responses; structured error responses |
| V9 Communication | Low concern | Trusted-LAN single-user; no TLS requirement for v1; document for reverse proxy users |
| V12 File Handling | Yes | Path-traversal guard (assert_within_media_roots) already in place; must apply to any new write paths |
| V13 API | Yes | Request size limits; no DoS via unbounded log queries (paginate /api/jobs) |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leakage via /api/settings GET | Info Disclosure | SecretStr masking; never echo raw key value |
| API key leakage via /api/test/* error messages | Info Disclosure | Redact credentials from connection-test error strings before returning |
| SSRF via user-configured LLM/Sonarr/Radarr base URLs | Spoofing | Accepted by design (user brings own endpoint); document clearly; do not auto-forward subtitle content to third-party URLs |
| Path traversal via job source_path in worker | Tampering | `assert_within_media_roots()` gate before any write; already implemented in `cli.py` |
| Unbounded job_log growth causing disk exhaustion | Denial of Service | Add log retention limit (e.g. keep last 1000 lines per job; delete job_log rows older than N days) |
| Webhook endpoint DDoS (unauthenticated POST /webhook) | Denial of Service | Rate-limit; only trigger scan (cheap), never translate in handler |

### Security Notes

- **Secrets on the wire (HIGH risk):** The new `/api/settings` GET and `/api/test/*` endpoints are the first place where secret values could escape. The existing `SecretStr` discipline (D-11) must be extended to the HTTP surface by the config-writer (D-70). This is a hard requirement — exposing the LLM API key to the browser is a security breach.
- **No authentication (known gap):** D-78 intentionally defers auth. The ASVS Level 1 requirement for auth is waived for this phase. The README/docs must clearly state "bind to localhost or use a reverse proxy with auth in untrusted networks."
- **Webhook endpoint:** The `/webhook` endpoint is unauthenticated in v1 (consistent with Bazarr's posture). In a hostile network, an attacker could trigger repeated library scans (expensive but non-destructive). Add source-IP or API key validation as a D-78 follow-up.

---

## Sources

### Primary (HIGH confidence)
- `trezarr/cli.py` (codebase) — current CLI structure, `_run_pipeline_steps` body, CR-01 pattern, engine lifecycle
- `trezarr/db/engine.py`, `trezarr/db/session.py`, `trezarr/db/migration_runner.py` (codebase) — confirmed async engine lifecycle, session factory, Alembic runner
- `trezarr/bible/models.py` (codebase) — ProcessedFile.status enum `in_progress` confirmed; `Base` registration pattern
- `alembic/versions/0001_baseline_bible_schema.py`, `alembic/env.py` (codebase) — `down_revision = None`; migration chaining pattern; `render_as_batch=True`
- `trezarr/config.py` (codebase) — existing settings structure; Phase-N grouping convention; SecretStr fields; `settings_customise_sources`
- FastAPI lifespan documentation (https://fastapi.tiangolo.com/advanced/events/) — `@asynccontextmanager lifespan` pattern, resource management
- FastAPI StaticFiles documentation (https://fastapi.tiangolo.com/tutorial/static-files/) — `StaticFiles(html=True)` SPA fallback
- SQLAlchemy 2.0 async engine lifecycle (https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — `await engine.dispose()` before event loop close; single engine for process lifetime
- Alembic autogenerate docs — `down_revision` chaining, `op.create_table()` for new tables

### Secondary (MEDIUM confidence)
- APScheduler 3.x user guide (https://apscheduler.readthedocs.io/en/3.x/) — `AsyncIOScheduler` for asyncio apps; `start()`/`shutdown()` lifecycle
- Community patterns: APScheduler + FastAPI lifespan (multiple sources including https://www.nashruddinamin.com/blog/running-scheduled-jobs-in-fastapi)
- Sonarr webhook payload shape (community docs, Sonarr issue tracker — eventType, series.id, episodes array)
- LinuxServer.io PUID/PGID docs (https://docs.linuxserver.io/general/understanding-puid-and-pgid/) — env var mechanism; `-e PUID=1000 -e PGID=1000`
- Vite build output structure (https://vite.dev/guide/build) — default `dist/` output, `index.html` + `assets/`
- Python `contextvars` + `logging.Handler` for per-request log capture (https://docs.python.org/3/howto/logging-cookbook.html + structlog docs)
- uvicorn programmatic launch (https://uvicorn.dev/settings/) — `uvicorn.run()` with host/port/log_level

### Tertiary (LOW confidence / ASSUMED)
- Bazarr outgoing webhook JSON payload schema — no public documentation found; scan-trigger-only approach is defensive and safe
- DB-backed job queue + asyncio.Queue hybrid as the correct pattern for D-69 — synthesized from multiple sources (snappea, persist-queue, sqlitebgjobs); no single authoritative source

---

## Metadata

**Confidence breakdown:**
- Service runtime skeleton: HIGH — directly derived from existing codebase patterns + official FastAPI/SQLAlchemy docs
- Queue/worker model: MEDIUM — hybrid pattern is well-reasoned but not validated against a running Trezarr instance
- Alembic migration 0002: HIGH — authoring a new migration using the existing template is fully verified
- Docker + LSIO: MEDIUM — PUID/PGID pattern is verified; Python:3.12-slim vs LSIO base choice left as planner discretion
- React/Vite SPA: HIGH (functional-first dashboard is well-trodden territory)
- Bazarr webhook payload: LOW — no public schema; defensive approach documented

**Research date:** 2026-06-02
**Valid until:** 2026-07-02 (30 days) for stable portions; re-verify watchfiles/fastapi minor version if executing after 2026-07-01
