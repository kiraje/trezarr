# Phase 7: Web UI & Service Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 7-web-ui-service-hardening
**Discussion mode:** `--auto` (Claude auto-selected the recommended option for every gray area; no interactive prompts)
**Areas discussed:** Service process model, Continuous-monitoring trigger model, Crash-safety & per-series serialization, Job/queue/log persistence, Config read/write & secrets, Web UI scope & stack, Docker packaging

---

## Service process model (SVC-01)

| Option | Description | Selected |
|--------|-------------|----------|
| One uvicorn process; FastAPI `lifespan` owns scheduler + webhook + worker, serves the SPA | CLAUDE.md prescription — single image, single port (6868) | ✓ |
| Separate scheduler/worker process | More isolation, but two processes in one container | |
| Celery/arq + Redis broker | Forces an extra service; CLAUDE.md "What NOT to Use" | |

**Auto-selected:** One uvicorn process + FastAPI lifespan (D-61). `trezarr serve` subcommand added; `trezarr run --once` preserved; per-item body extracted as a reusable worker callable (D-62).
**Notes:** Directly endorsed by CLAUDE.md ("daemon in the same process via FastAPI lifespan"; "FastAPI serves the Vite dist/ — no nginx, no second process").

---

## Continuous-monitoring trigger model (AUTO-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: APScheduler poll (source of truth) + inbound webhook; watchfiles optional/off | Poll cannot miss; webhook adds latency; watcher deferred | ✓ |
| Pure polling | Simple but high-latency | |
| Pure webhooks | Low-latency but lossy in the *arr ecosystem | |

**Auto-selected:** Hybrid, poll = source of truth (D-65). Both poll and webhook *enqueue* only; translation runs in the worker; webhook returns 200 immediately (D-66).
**Notes:** CLAUDE.md is explicit that webhooks are best-effort/lossy and a missed event must not mean a permanently-untranslated episode.

---

## Crash-safety & per-series serialization (AUTO-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse `in_progress` ledger as the checkpoint; reconcile on startup; per-series lock | No new mid-pass machinery; whole-file idempotent re-run | ✓ |
| New per-pass checkpoint store | Finer granularity, much more complexity, unneeded | |
| No serialization (rely on idempotency alone) | Would race the shared Series Bible per series | |

**Auto-selected:** Ledger-as-checkpoint (D-67) + per-series `asyncio.Lock`/single-flight, parallel across series, single global LLM semaphore preserved (D-68).
**Notes:** Phase 4 pre-built `processed_file.status='in_progress'` and `gap.py` Case 4 already does crashed-run recovery — AUTO-05 is reconcile + serialize, not new checkpointing.

---

## Job/queue/log persistence

| Option | Description | Selected |
|--------|-------------|----------|
| New `job` (+ `job_log`) table via a new Alembic migration; ledger untouched | Keeps the frozen D-20 LedgerEntry contract intact; queue/UI concerns isolated | ✓ |
| Extend `processed_file` with queue/log columns | Fewer tables, but risks the D-20 1:1 contract | |
| Files in /config for logs | Not queryable for per-job UI | |

**Auto-selected:** Dedicated `job`/`job_log` + new migration (D-69) — the first schema change since the Phase-4 baseline; follows `run_migrations_to_head` discipline. Per-job logs stored as rows (D-75).
**Notes:** Planner may extend `processed_file` instead *only if* it doesn't break the D-20 contract; the new-table option is preferred for exactly that reason.

---

## Config read/write & secrets (SVC-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Config-writer to config.yaml; secrets write-only (masked on read); env precedence respected | Extends existing SecretStr discipline to the HTTP boundary | ✓ |
| Return secrets to the UI for editing | Leaks API keys across the new wire | |
| Env-only config (no UI write) | Fails SVC-02 "web UI configures connections" | |

**Auto-selected:** Config-writer + write-only secrets + connection-test endpoints (D-70/D-71); prefer hot re-apply of clients on save, else require restart explicitly (D-72).
**Notes:** First outward-facing surface where a secret could leak — masking on read is mandatory.

---

## Web UI scope & stack (SVC-03, SVC-04)

| Option | Description | Selected |
|--------|-------------|----------|
| React 19 + Vite 7 SPA served by FastAPI; REST + client-side polling | Bazarr parity; sets up Phase-8 Bible editor; functional-first | ✓ |
| Server-rendered (HTMX/Jinja) dashboard | Lighter, but diverges from CLAUDE.md and Phase-8 setup | |
| SSE/WebSocket live updates | Nice-to-have; deferred for mvp | |

**Auto-selected:** React/Vite SPA (D-73); Retry = re-enqueue through the worker (D-74); polling for live updates in mvp.
**Notes:** Functional-first — this is "service hardening," not a visual-design phase. Planner may choose a lighter approach if it judges the SPA over-scoped, but the SPA is the recommended default.

---

## Docker packaging (SVC-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Multi-stage (node build → python runtime); LSIO baseimage; /config volume; port 6868 | Free PUID/PGID + s6-overlay + /config fixup | ✓ |
| python:3.12-slim + custom PUID/PGID entrypoint | Acceptable fallback; more entrypoint code to own | |
| Run as root | Breaks shared *arr filesystem ownership (forbidden) | |

**Auto-selected:** Multi-stage single image, LSIO base recommended (D-64); deps added per CLAUDE.md versions (D-63).
**Notes:** Container must drop to host user so sidecars get correct ownership (INTG-04, already enforced in-process).

---

## Claude's Discretion

Web-layer module layout; queue mechanism (DB-polling worker vs `asyncio.Queue` vs APScheduler-job-per-item); exact `job`/`job_log` schema (or extend `processed_file`); REST route names + DTOs; SSE/WebSocket vs polling; per-series serialization primitive; LSIO vs slim base; settings hot-reload depth; per-job log-capture mechanism; exact new setting names + numeric defaults; SPA component structure/styling; whether `watchfiles` ships wired-but-off or scaffolded. (See CONTEXT.md §"Claude's Discretion" — D-61…D-78.)

## Deferred Ideas

- Editable/lockable Series Bible UI → Phase 8 (BIBLE-08/09)
- Bazarr inventory reads / source selection / per-series overrides → Phase 10 (INTG-02, SRC, SVC-05)
- ASS/SSA + VTT → Phase 9
- `watchfiles` fully wired; SSE/WebSocket live updates → deferred-within-phase
- Web UI auth / multi-user → not v1 (single-user trusted-LAN default)
- Notifications (OBS-02), confidence-flagging (OBS-01), multi-instance (SCALE-01), Bible import/export (COMM-01) → v2
- AsyncSonarr/AsyncRadarr + gather parallel discovery → optional perf upgrade, not required by any Phase-7 success criterion
