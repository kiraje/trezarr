# Phase 7: Web UI & Service Hardening - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** mvp (vertical slice — keep each capability to its success criterion; do not gold-plate)
**Discussion mode:** `--auto` (recommended defaults auto-selected; every decision below is a sensible default the planner/researcher may tune)

<domain>
## Phase Boundary

Phase 7 turns the proven **one-shot CLI** (`trezarr run --once`) into a **Dockerized, long-running, crash-safe service** with a **web UI** — the "*arr-citizen baseline" that makes unattended operation trustworthy. It adds **no new translation logic and no new format/source surface**; the entire three-pass + self-review pipeline from Phases 5–6 is reused verbatim as the work the new service orchestrates.

Concretely, Phase 7 delivers five capabilities, each mapped to a requirement:

1. **Dockerized long-running service (SVC-01).** A single Docker image runs `trezarr serve` (uvicorn + FastAPI) as a long-lived process with a `/config` volume (SQLite DB + `config.yaml` + quarantine + logs), deployable next to Sonarr/Radarr/Bazarr, dropping to PUID/PGID.

2. **Continuous monitoring (AUTO-02).** An in-process APScheduler interval **poll** is the source of truth; an inbound FastAPI **webhook** endpoint (Sonarr/Radarr Connect, Bazarr subtitle events) is the low-latency complement. Both *enqueue* work — they never translate in the request handler.

3. **Crash-safe resumption + per-series serialization (AUTO-05).** Processing resumes after a crash/restart without losing or duplicating work, with episodes of the same series processed serially (they share + mutate the Series Bible). This reuses the **existing `in_progress` ledger semantics** as the checkpoint.

4. **Web UI — configuration + connection tests (SVC-02).** A browser UI configures Sonarr/Radarr/**Bazarr** connections, the LLM endpoint, and path mappings, with per-connection **test** buttons, writing back to `/config/config.yaml`. Secrets are write-only (never echoed back).

5. **Web UI — Queue / History / logs + Retry (SVC-03, SVC-04).** The UI shows the in-flight **Queue**, the **History** (completed/failed with per-item reason), and **per-job logs**, and a failed/rejected item can be **retried** from the UI.

Requirements covered: **SVC-01, SVC-02, SVC-03, SVC-04, AUTO-02, AUTO-05.**

**In scope:**
- A new `trezarr serve` entry point: uvicorn + FastAPI app whose `lifespan` owns the scheduler, the webhook receiver, and the queue worker, and which serves the built SPA static assets — a single image, single port (6868).
- Refactor the existing `_run_pipeline_steps` "process one eligible item" body into a **reusable callable** the worker invokes (the CLI one-shot path is preserved, not deleted).
- **Bazarr connection config + connection test + inbound webhook receipt** (the connection surface only; *reading* Bazarr's subtitle inventory is INTG-02, **Phase 10**).
- A **job/queue/log persistence layer** — the first Alembic migration since the Phase-4 baseline — surfacing Queue, History, per-item failure reason, retry count, and per-job logs.
- A **config read/write service** (the UI edits `config.yaml`) with masked-secret round-tripping and connection-test endpoints.
- A **React 19 + Vite 7 SPA** (Bazarr parity; sets up the Phase-8 Bible editor) with Settings, Queue, History, and per-job Logs + Retry views, built to static assets FastAPI serves.
- A single **multi-stage Dockerfile** (node build stage → Python runtime), `/config` volume, PUID/PGID drop-privilege.
- New **Phase-7 `TrezarrSettings`** fields (web host/port, poll interval, webhook/watchfiles toggles, per-series concurrency, Bazarr connection) under a Phase-7 header mirroring D-50/D-60.

**Out of scope (deferred to owning phases / v2):**
- **Editable / lockable Series Bible UI** (view/correct/lock characters, address map, terms, register) → **Phase 8** (BIBLE-08/09). Phase 7's UI is config + queue/history/logs only.
- **Reading Bazarr's subtitle inventory, source-language selection, per-series source/register/model overrides** → **Phase 10** (INTG-02, SRC-01/02, SVC-05). Phase 7 only adds the Bazarr *connection* + webhook.
- **ASS/SSA + VTT formats** → **Phase 9** (FMT-02/03/04).
- **`watchfiles` filesystem watcher** — included as an **optional, default-off** toggle; poll + webhook satisfy AUTO-02 for the mvp. Lighting it up fully is a deferred-within-phase nice-to-have.
- **Notifications** (Discord/Telegram/ntfy, OBS-02), **confidence-flagging in the UI** (OBS-01), **multi-instance Sonarr/Radarr** (SCALE-01) → **v2**.
- **Retroactive re-translation** of earlier episodes → out of scope (forward-only, carried from Phase 6).
- **Web UI authentication / multi-user accounts** → not a v1 requirement; v1 targets a single-user, trusted-LAN deployment (Bazarr's default posture). Captured as a deferred consideration, not built.

</domain>

<decisions>
## Implementation Decisions

Continues the project decision ledger (Phase 1 D-01…D-11, Phase 2 D-12…D-20, Phase 3 D-21…D-30, Phase 4 D-31…D-39, Phase 5 D-40…D-50, Phase 6 D-51…D-60). **Phase 7 = D-61…D-78.** All numbered values are sensible defaults the planner/researcher may tune; all are overridable in planning.

> **Scale note for the planner.** This phase is unusually broad (service runtime + a schema migration + monitoring + Docker + a full SPA across five capability areas). It is a strong candidate for **wave-based slicing** — e.g. (W1) service runtime + reusable worker + job/queue persistence + crash-resume; (W2) monitoring (poll + webhook); (W3) config read/write + connection tests; (W4) the SPA + REST API; (W5) Docker packaging. The roadmap boundary is fixed (all six requirements land here), but the planner should not try to land it as one monolithic plan. Keep each capability to its success criterion (mvp mode).

### Capability A — Dockerized long-running service (SVC-01)

#### Process model (D-61)
- **D-61: One uvicorn process; FastAPI `lifespan` owns the daemon (APScheduler poll + webhook receiver + queue worker) AND serves the built Vite SPA static assets.** Single image, single port (default 6868, echoing Bazarr's 6767). This is the CLAUDE.md prescription ("run the daemon/scheduler in the same process via FastAPI lifespan"; "FastAPI static-file serving of the Vite `dist/` — no nginx, no second process"). **Rejected:** Celery/arq + Redis broker (CLAUDE.md "What NOT to Use" — forces users to run an extra service; massive overkill for a single-user daemon) and a separate scheduler process.

#### Entry point & worker reuse (D-62)
- **D-62: Add a `trezarr serve` CLI subcommand that starts uvicorn; preserve `trezarr run --once` unchanged.** The existing one-shot path stays (tests + manual single passes). Refactor the body of `_run_pipeline_steps` so the **"process one eligible item"** step becomes a single reusable async callable that BOTH the one-shot loop and the new queue worker invoke — no logic duplication. The console-script entry stays `trezarr`; add the `serve` subparser alongside `run`. **Rejected:** deleting/replacing the CLI (it's the cheapest test harness and a useful escape hatch).

#### Dependencies to add (D-63)
- **D-63: Add `fastapi` (~0.136), `uvicorn[standard]` (~0.48), `apscheduler` (~3.11), `httpx` (~0.28, for connection-test + webhook calls pyarr doesn't cover), and `watchfiles` (~1.2, feature-gated/default-off).** Frontend is a **separate `frontend/` package** built with Vite 7 / React 19, output `dist/` served by FastAPI `StaticFiles`. Pin to the CLAUDE.md "Recommended Stack" versions. Keep Pydantic v2 throughout (no v1 deps).

#### Docker packaging (D-64)
- **D-64: Single multi-stage Dockerfile — a Node stage builds the SPA, the Python runtime stage copies `dist/` and runs `trezarr serve`.** **Recommended base:** the LinuxServer.io pattern (`ghcr.io/linuxserver/baseimage-*` + s6-overlay) for free PUID/PGID drop-privilege and `/config` ownership fixup; `python:3.12-slim` + a small PUID/PGID entrypoint is the acceptable fallback. `/config` volume holds the SQLite DB, `config.yaml`, quarantine dir, and logs (the universal *arr convention; all our existing defaults already point at `/config/...`). Expose port 6868. **Non-negotiable:** the container drops to the host user so `.vi.srt` sidecars are written with correct ownership (INTG-04, already enforced in-process by `apply_permissions`).

### Capability B — Continuous monitoring (AUTO-02)

#### Hybrid trigger (D-65)
- **D-65: Hybrid — APScheduler interval poll is the source of truth; an inbound FastAPI webhook endpoint is the low-latency complement; `watchfiles` is optional/default-off.** CLAUDE.md is explicit: "poll as source of truth — webhooks are best-effort/lossy in this ecosystem and a missed event must not mean a permanently-untranslated episode." The webhook endpoint accepts Sonarr/Radarr **Connect** (On Import / On Download / On Upgrade) and **Bazarr** subtitle events; on receipt it triggers an **immediate discovery scan** rather than trusting the payload contents. Poll interval is configurable (default ~15 min). **Rejected:** pure polling (high latency) and pure webhooks (lossy).

#### Enqueue, never translate-in-handler (D-66)
- **D-66: Both poll and webhook run "discover → scan eligible → enqueue"; translation happens only in the worker.** The webhook handler enqueues and returns `200` immediately (never blocks on an LLM call). Queued state is persisted (D-69) so a crash between enqueue and execution is recoverable. **Dedup:** the idempotency ledger (AUTO-03) plus a queue-level "already queued/in-flight for this source_path" guard prevent a poll and a webhook from double-enqueuing the same item.

### Capability C — Crash-safe resumption + per-series serialization (AUTO-05)

#### The ledger is the checkpoint (D-67)
- **D-67: Crash-resume reuses the existing `in_progress` ledger semantics — no new mid-pass checkpoint machinery.** `engine.py` already records `status="in_progress"` *before* translating (Step 4), and `discover/gap.py` Case 4 already treats an `in_progress` ledger row as **crashed-run recovery** ("the next run picks it up"). On daemon startup, **reconcile**: any `in_progress` rows left by a prior (crashed) process are re-enqueued. Whole-file re-translation is idempotent (ENG-07 — temp+rename atomic write, content-hash skip), so re-running a crashed item from scratch never duplicates or corrupts output. **Checkpoint granularity = per-file, not per-pass** (a crash mid-three-pass simply re-runs the whole file). This is exactly why Phase 4 baked `in_progress` into the `processed_file.status` CHECK constraint.

#### Per-series serialization (D-68)
- **D-68: Serialize work per series via a per-series key (e.g. an `asyncio.Lock` per `series_id`, or a series-keyed single-flight worker); distinct series may run concurrently.** AUTO-05 requires per-series serialization: two episodes of the same series must not translate concurrently because they read + mutate the shared Series Bible (concurrent Pass-1 merges / Address-Map upserts would race). The **single `LLMClient._semaphore` (D-06) remains the only global in-flight LLM cap** — per-series serialization is an orthogonal *ordering* constraint, **not** a second `asyncio.Semaphore` (Pitfall 1 preserved; no double-capping). `worker_max_concurrent_series` (D-76) bounds how many distinct series run in parallel.

#### Job / queue / log persistence + the first post-baseline migration (D-69)
- **D-69: Add a dedicated `job` (+ `job_log`) persistence layer via a NEW Alembic migration — the first schema change since the Phase-4 baseline.** Queue (in-flight), History (done/failed + per-item reason), per-job logs, retry count, and timestamps need durable storage. **Recommended shape:** a `job` table keyed to `source_path` (referencing, not replacing, the `processed_file` idempotency ledger) carrying `status` (`queued|running|done|failed|quarantined`), `error_reason`, `attempts`, `enqueued_at`/`started_at`/`finished_at`, `series_id`, and trigger source (poll|webhook|manual-retry); plus a `job_log` table (or a JSON/text log column) so SVC-03 "per-job logs" is a DB query, not file-scraping. This **keeps the frozen D-20 ledger contract untouched** (idempotency stays in `processed_file`; queue/UI concerns live in `job`). The migration MUST follow the Phase-4 migration-runner discipline (`run_migrations_to_head` on startup; reversible). **Planner's discretion:** extend `processed_file` with the extra columns instead of a new table — acceptable, but only if the D-20 1:1 LedgerEntry↔column contract is not broken; the new-table option is preferred for exactly that reason.

### Capability D — Web UI: configuration + connection tests (SVC-02)

#### Config read/write + write-only secrets (D-70)
- **D-70: The UI edits `/config/config.yaml` through a config-writer service; SecretStr fields are write-only.** pydantic-settings is read-only at runtime, so add a settings service that (a) loads current effective settings for display, (b) accepts edits from the UI, and (c) writes them back to `config.yaml`. **Secrets (`llm_api_key`, `sonarr_api_key`, `radarr_api_key`, `bazarr_api_key`) are NEVER returned to the UI** — the API returns a masked sentinel / `is_set: true`; the UI only transmits a new secret when the user explicitly enters one (an unchanged field leaves the stored secret intact). **Env-var-sourced settings keep their existing precedence over YAML** (pydantic-settings order); the UI should surface which fields are env-locked so a save doesn't silently appear to fail. Clean YAML re-serialize is acceptable for mvp (comment-preservation is a nice-to-have, not required).

#### Connection-test endpoints (D-71)
- **D-71: `POST /api/test/{sonarr|radarr|bazarr|llm}` validate a candidate config and return ok/error with a redacted message.** *arr tests use a cheap `system/status` ping via pyarr; the LLM test uses a minimal models/health or trivial completion call against the configured endpoint. These let SVC-02's "with connection tests" work **before** saving. Never include the API key / host credentials verbatim in the response or logs (CLAUDE.md redaction rule).

#### Apply-on-save vs restart (D-72)
- **D-72: Prefer hot re-application of affected clients on save; otherwise clearly require a restart.** When connection/LLM/path settings change, re-instantiate the affected clients (and reschedule the poll job) in-process rather than forcing a container restart where cheap. If a setting genuinely needs a restart, the UI must say so explicitly. **Planner's discretion** on how much hot-reload to implement for mvp.

### Capability E — Web UI: Queue / History / logs + Retry (SVC-03, SVC-04)

#### SPA stack + API shape (D-73)
- **D-73: React 19 + Vite 7 SPA built to static assets FastAPI serves; the SPA consumes a REST API with client-side polling for live updates.** This matches CLAUDE.md (Bazarr parity; one container/one port) and sets up the Phase-8 Bible editor. Views: **Settings** (config + connection tests, D-70/D-71), **Queue** (in-flight), **History** (completed/failed with per-item reason), and a **per-job Logs** view with a **Retry** action. For live updates, **client-side polling** of `/api/queue` + `/api/jobs` is the mvp default; SSE/WebSocket is a deferrable nice-to-have. Keep the UI **functional-first** — this is "service hardening," not a visual-design phase — but it is a real SPA, not server-rendered. **Rejected for mvp consideration but allowed at planner discretion:** a lighter server-rendered (HTMX/Jinja) dashboard — only if the planner judges the SPA over-scoped; the SPA remains the recommended default because Phase 8 builds directly on it.

#### Retry = re-enqueue (D-74)
- **D-74: Retry (SVC-04) re-enqueues the item through the same worker path.** `POST /api/jobs/{id}/retry` resets the item's job (and, where appropriate, ledger) state and re-enqueues it, reusing the ENG-07 idempotent re-run. Retry **clears the prior quarantine artifact / failure reason** so the re-run starts clean. Per-series serialization (D-68) still governs a retried item. A retried item's trigger source is recorded as `manual-retry` (D-69) for History.

#### Per-job structured log capture (D-75)
- **D-75: Capture each job's `logging` output into a per-job sink (the `job_log` rows / column from D-69) so SVC-03 "per-job logs" shows which pass failed and why an item quarantined.** A rotating app-wide log file in `/config/logs` is the operator-level complement. **Planner's discretion** on the capture mechanism (a context-bound log handler, a `contextvars` job-id filter, etc.); the requirement is that the UI can render a specific job's log trail.

### Settings + staged rollout (D-76…D-78)

- **D-76: New Phase-7 `TrezarrSettings` fields under a Phase-7 comment header (mirroring the D-50/D-60 grouping).** At minimum: `web_host` (default `0.0.0.0`) / `web_port` (default `6868`); `poll_interval_seconds` (default ~900); `enable_webhooks: bool = True`; `enable_watchfiles: bool = False` (deferred-within-phase default); `worker_max_concurrent_series: int` (distinct series in parallel, e.g. default 2–4); and **Bazarr connection** fields `bazarr_host` / `bazarr_port` (default 6767) / `bazarr_api_key: SecretStr` / `bazarr_enabled: bool = False` (connection + webhook only — inventory reads are Phase 10). All overridable; defaults are Claude's discretion.
- **D-77: Independent toggles for staged rollout/tests** — the daemon, the poller, the webhook receiver, and the watcher must each be toggleable so the service can run headless/poll-only or be exercised in tests without a live UI or live *arr stack (mirrors the `enable_pass1_analysis` / `enable_self_review` precedent).
- **D-78: The service is single-user, no-auth, trusted-LAN by default for v1** (Bazarr's default posture). Web UI authentication is **not** built in Phase 7; it is recorded as a deferred consideration. Bind/port are configurable so a reverse proxy can front it.

### Claude's Discretion
Planner/researcher retain latitude on: the module layout for the web layer (`trezarr/web/` package vs `trezarr/api/` + `trezarr/service/`); whether the queue is a DB-polling worker, an `asyncio.Queue`, or an APScheduler-job-per-item; the exact `job` / `job_log` schema (or extending `processed_file` instead — D-69); the precise REST route names and response DTOs; SSE/WebSocket vs polling for live updates (D-73 defaults to polling); the per-series serialization primitive (per-`series_id` `asyncio.Lock` vs series-keyed single-flight — D-68); LSIO baseimage vs `python:3.12-slim` + entrypoint (D-64 recommends LSIO); how much settings hot-reload to implement (D-72); the per-job log-capture mechanism (D-75); the exact new setting names and numeric defaults (D-76); the SPA component structure and styling approach (functional-first, no design mandate); and whether `watchfiles` ships wired-but-off or merely scaffolded (D-65/D-77).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` §Service & Web UI — **SVC-01** (single Dockerized long-running service, `/config` volume), **SVC-02** (web UI config + connection tests), **SVC-03** (Queue / History / per-job logs), **SVC-04** (retry from UI); §Discovery & Automation — **AUTO-02** (continuous monitor: poll + webhook), **AUTO-05** (crash-safe resume); and the invariants this phase must not break — **AUTO-03** (idempotency / source-sub hash), **AUTO-04** (no self-reprocessing), **INTG-04** (PUID/PGID sidecar ownership)
- `.planning/ROADMAP.md` §"Phase 7: Web UI & Service Hardening" — goal + 4 success criteria (single container + `/config`; web UI config + tests; Queue/History/logs + retry; continuous monitor + crash-safe per-series serialized resume)

### Project-wide grounding (the prescriptions for THIS phase)
- `CLAUDE.md` §"Docker Packaging — Prescribed Conventions" — LSIO base + s6-overlay PUID/PGID, `/config` volume, media volumes at the same paths as *arr, single image / single port (6868), multi-stage node→python build, FastAPI serves the Vite `dist/`
- `CLAUDE.md` §"*arr Integration — Prescribed Approach" — hybrid webhook + poll (poll is the source of truth; webhooks are lossy); Bazarr `/api/*` + incoming webhook hook; X-Api-Key auth
- `CLAUDE.md` §"Technology Stack" / "Recommended Stack" / "Supporting Libraries" — FastAPI 0.136, Uvicorn 0.48, APScheduler 3.11 (in-process; NOT Celery/arq+Redis), watchfiles 1.2, httpx 0.28, React 19 / Vite 7; §"What NOT to Use" — no Redis broker, no nginx, no sync clients in the loop, never run container as root
- `.planning/PROJECT.md` §Constraints / Key Decisions — "Dockerized service + web UI" (— Pending, this phase closes it); "consistency is non-negotiable" (drives per-series serialization D-68)

### Prior-phase foundations this phase consumes & extends
- `.planning/phases/04-series-bible-store-schema/04-CONTEXT.md` — **D-31** (the 7-table baseline migration; Phase 7 adds the FIRST migration on top of it — D-69), **D-37/D-38** (`LedgerSQLA` async ledger + `run_migrations_to_head` startup discipline), the **`processed_file.status` `in_progress`** state pre-built for crash-resume (D-67)
- `.planning/phases/03-arr-integration-first-vertical-slice/03-CONTEXT.md` — **D-21** (the one-shot CLI Phase 7 explicitly supersedes with a daemon — see the `cli.py` "Phase 7" TODOs), **D-22/D-23/D-24/D-29** (pyarr discovery, path mapping, startup probe, PUID/PGID — all reused by the service), the `discover/gap.py` Case 4 in_progress recovery path
- `.planning/phases/05-three-pass-pronoun-engine/05-CONTEXT.md` + `.planning/phases/06-relationship-evolution-self-review/06-CONTEXT.md` — the pipeline (`translate_file` 3-pass + Pass-4 self-review) the worker orchestrates unchanged; **D-06** single `LLMClient._semaphore` (the only global concurrency cap — D-68 adds no second one); **D-50/D-60** settings-grouping pattern Phase 7 mirrors (D-76)

### Existing code to reuse / extend (do not reinvent)
- `trezarr/cli.py` — `main()` (add a `serve` subparser — D-62), `_run_pipeline_steps` (extract the per-item body into a reusable worker callable — D-62), the startup sequence (assert media roots → probe → build engine → migrate → ledger) the service `lifespan` reuses; note the in-file "Phase 7" TODOs (AsyncSonarr/AsyncRadarr + gather; replace one-shot with daemon)
- `trezarr/config.py` — `TrezarrSettings` (add the Phase-7 group under a Phase-7 header — D-76); the `settings_customise_sources` YAML+env precedence the config-writer must respect (D-70); `CONFIG_PATH` = `/config/config.yaml`
- `trezarr/bible/models.py` — `ProcessedFile` (the ledger; `status` already allows `in_progress` — D-67), `Base` (new `Job`/`JobLog` models register here — D-69); the D-32 `bible_event` audit pattern as a template for job provenance
- `trezarr/output/ledger_sqla.py` — `LedgerSQLA.check`/`record` (the worker's idempotency gate; `expire_on_commit=False` requirement — Pitfall 2); the frozen D-20 LedgerEntry↔column contract the new `job` table must NOT disturb
- `trezarr/db/migration_runner.py` + `alembic/versions/0001_baseline_bible_schema.py` — `run_migrations_to_head` (startup migration discipline the new migration plugs into — D-69); the baseline migration as the authoring template
- `trezarr/db/engine.py` / `trezarr/db/session.py` — `build_engine` / `build_session_factory` (`expire_on_commit=False`; PRAGMA-per-connection; the **CR-01 `await engine.dispose()`** lifecycle the long-running service must manage in `lifespan` shutdown, not per-run)
- `trezarr/translate/engine.py` — `translate_file` (the work unit; already records `in_progress` before translating — D-67) and its `eligible_item` + `session_factory` Bible-aware contract the worker must pass through
- `trezarr/discover/scan.py` + `trezarr/discover/gap.py` — `scan_for_eligible_items` (poll + webhook reuse it — D-65/D-66); `gap.py` Case 4 `in_progress` crashed-run recovery (the basis of D-67)
- `trezarr/arr/sonarr.py` / `trezarr/arr/radarr.py` — `discover_*_items` (poll/webhook reuse); pyarr `system/status` for the connection-test endpoints (D-71); the place to add a Bazarr client stub for the connection test (D-71/D-76)
- `trezarr/paths.py` — `assert_media_roots_configured` / `probe_media_roots` / `apply_permissions` (the service runs these at startup; INTG-04 sidecar ownership preserved)
- `trezarr/output/write.py` — `apply_permissions` / `PermissionApplyError` (sidecar PUID/PGID/umask; quarantine-on-chmod-failure — preserved unchanged)

### Research (risk & stack grounding)
- `.planning/research/STACK.md` — FastAPI + uvicorn + APScheduler + watchfiles + httpx + React/Vite versions and the single-process/single-port packaging rationale
- `.planning/research/ARCHITECTURE.md` — "API for knowledge, filesystem for action"; the daemon/poll/webhook hybrid; the service-as-*arr-citizen shape
- `.planning/research/PITFALLS.md` — re-check anything tagged concurrency / path-mapping / permissions / Docker / *arr-webhook; **specifically Pitfall 1** (single semaphore — D-68 adds none) and the path-mapping + PUID/PGID friction (the biggest deployment risk this phase exposes to real users)
- `.planning/research/FEATURES.md` / `.planning/research/SUMMARY.md` — the *arr-stack integration patterns and the Bazarr reference-product framing (Trezarr ↔ Bazarr/*arr one level up)

### External references
- LinuxServer.io PUID/PGID docs — https://docs.linuxserver.io/general/understanding-puid-and-pgid/ (the D-64 base-image mechanism)
- Bazarr — https://github.com/morpheus65535/bazarr (reference product: Python + web UI + Dockerized + *arr-connected + sidecar writer; the integration/UX posture Phase 7 mirrors)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`trezarr/cli.py` startup sequence + `_run_pipeline_steps`** — the entire discover→scan→translate→permission flow already exists and is battle-tested; Phase 7 wraps it in a long-running runtime and extracts the per-item body as the worker callable (D-62). The file even documents the Phase-7 work in its own TODOs (daemon replacement, AsyncSonarr/Radarr + gather).
- **`ProcessedFile.status == "in_progress"` + `engine.py` Step 4 + `gap.py` Case 4** — the crash-resume substrate is **already partially built**: translation records `in_progress` before it starts, and discovery already re-picks-up `in_progress` items. AUTO-05 is mostly "re-enqueue `in_progress` on startup + serialize per series," not new checkpoint machinery (D-67).
- **`LedgerSQLA` + `run_migrations_to_head` + the Alembic baseline** — the async persistence + startup-migration discipline is established; Phase 7's new `job`/`job_log` migration follows the exact same path (D-69).
- **`TrezarrSettings` + `config.yaml.example` + `settings_customise_sources`** — the full config surface (LLM, *arr, paths, permissions, Phase 2–6 knobs) already exists with env>YAML>default precedence and SecretStr masking; the UI config-writer reads/writes this same surface (D-70) and the example file documents every field.
- **`apply_permissions` / `assert_media_roots_configured` / `probe_media_roots`** — INTG-03/04 path-mapping + PUID/PGID + startup probe are done; the service just runs them at `lifespan` startup instead of per-CLI-invocation.

### Established Patterns
- **`/config`-volume defaults everywhere** (`bible_db_url`, `translate_quarantine_dir`, `translate_ledger_path`, `CONFIG_PATH`) — the Docker `/config` convention is already baked into defaults; SVC-01 packaging just mounts it.
- **SecretStr masking** (D-11) — `llm_api_key` / `sonarr_api_key` / `radarr_api_key` never appear in `repr`/`str`/`model_dump`; the config API (D-70) extends this to "never echo to the UI."
- **Single `asyncio.Semaphore` in `LLMClient`** (D-06, Pitfall 1) — preserved; per-series serialization (D-68) is an ordering lock, not a second semaphore.
- **CR-01 `await engine.dispose()` lifecycle** — the one-shot CLI disposes the engine per run inside `asyncio.run`; the long-running service must hold ONE engine for the process lifetime and dispose it in `lifespan` **shutdown** (a real change in lifecycle ownership the planner must get right).
- **Alembic-migration-on-startup + reversible migrations** (D-37) — the new `job` migration is authored and run the same way.

### Integration Points
- **`lifespan` startup** → assert media roots → probe → build engine (once) → `run_migrations_to_head` (incl. the new `job` migration) → reconcile `in_progress` → start scheduler + webhook + worker.
- **APScheduler job + `POST /webhook`** → `discover_*_items` → `scan_for_eligible_items` → enqueue (deduped) → `job` rows (D-65/D-66/D-69).
- **Queue worker** → per-series lock (D-68) → the reusable per-item callable (D-62) → `translate_file` (unchanged) → `apply_permissions` → ledger + `job` status update + per-job log (D-75).
- **REST API** (`/api/settings`, `/api/test/*`, `/api/queue`, `/api/jobs`, `/api/jobs/{id}/retry`, `/webhook`) ← React SPA (D-70/D-71/D-73/D-74); FastAPI also serves the SPA `dist/` (D-61).
- **`lifespan` shutdown** → stop scheduler/worker → `await engine.dispose()` (CR-01 at process scope).

</code_context>

<specifics>
## Specific Ideas

- **Phase 4 pre-built the runway for crash-resume — again.** Just as `relationship_event`/`valid_from_episode` were created empty for Phase 6, `processed_file.status='in_progress'` + the `gap.py` Case-4 recovery branch were built for *this* phase. AUTO-05 is an INSERT/reconcile + a per-series lock, not a new checkpointing engine (D-67/D-68).
- **The pipeline is frozen; Phase 7 only orchestrates it.** No change to `translate_file`, the three passes, reconciliation, or the validation gate. The risk surface is the *runtime* (async lifecycle, engine ownership, scheduling, queueing) and the *new surfaces* (HTTP API, SPA, Docker), not the translation logic.
- **Per-series serialization is a correctness guarantee, not a perf knob.** Two episodes of one series share the mutable Series Bible; concurrent Pass-1 merges would race the very consistency this product exists to protect. Serialize per series; parallelize across series; keep the one LLM semaphore global (D-68).
- **Secrets are write-only across the new API boundary.** The new HTTP surface is the first place a config secret could leak outward. The config + test endpoints must mask on read and only accept secrets on explicit write (D-70/D-71) — an extension of the existing SecretStr discipline to the wire.
- **Engine lifecycle ownership moves from per-run to per-process.** The CR-01 dispose pattern is correct for the CLI but must be re-homed into `lifespan` for the daemon — one engine for the process, disposed on shutdown. Getting this wrong reintroduces the "Event loop is closed" class of bugs at a new scope.
- **Bazarr appears here as a connection, not a consumer.** SVC-02 lists Bazarr among configurable connections, so its connection config + test + inbound webhook land in Phase 7; *reading* its subtitle inventory (INTG-02) is deliberately Phase 10. Keep that line sharp so the phase doesn't bleed into source-selection scope.

</specifics>

<deferred>
## Deferred Ideas

- **Editable / lockable Series Bible UI** (view/correct/lock characters, address map, terms, register) → **Phase 8** (BIBLE-08/09, the override valve). Phase 7's SPA is config + queue/history/logs; it does NOT edit the Bible.
- **Reading Bazarr's subtitle inventory, source-language selection, per-series source/register/model overrides** → **Phase 10** (INTG-02, SRC-01/02, SVC-05). Phase 7 adds only the Bazarr connection + webhook.
- **ASS/SSA + VTT formats** → **Phase 9** (FMT-02/03/04).
- **`watchfiles` filesystem watcher fully wired** → deferred-within-phase (default-off toggle; poll + webhook satisfy AUTO-02 for mvp). Promote to fully-on once validated against real Bazarr writes.
- **SSE / WebSocket live updates** for the Queue/History views → nice-to-have; mvp uses client-side polling (D-73).
- **Web UI authentication / multi-user accounts** → not a v1 requirement; single-user trusted-LAN default (D-78). Revisit if a reverse-proxy-less internet-exposed deployment becomes a goal.
- **Notifications on completion/failure** (Discord/Telegram/ntfy, OBS-02), **confidence-flagging low-certainty lines in the UI** (OBS-01), **multi-instance Sonarr/Radarr** (SCALE-01), **Bible/glossary import-export** (COMM-01) → **v2**.
- **AsyncSonarr/AsyncRadarr + `asyncio.gather` parallel discovery across large libraries** (the `cli.py` Phase-7 TODO) → a worthwhile perf upgrade but not required by any Phase-7 success criterion; planner may fold it in if cheap, else defer.
- **Settings hot-reload depth** (full live re-config vs restart-required) → D-72 leaves the mvp depth to the planner; deeper hot-reload can land later.

None of these block Phase 7. Discussion stayed within phase scope.

</deferred>

---

*Phase: 07-web-ui-service-hardening*
*Context gathered: 2026-06-02*
