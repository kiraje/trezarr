---
phase: 07-web-ui-service-hardening
plan: "06"
subsystem: Docker packaging + deployment
tags: [docker, dockerfile, multi-stage, puid-pgid, entrypoint, gosu, docker-compose, config-yaml, svc-01, intg-04, d-64, d-76, d-78]
dependency_graph:
  requires:
    - 07-02 (trezarr serve CLI entry point, web_host/web_port settings, GET /api/health)
    - 07-05 (frontend/ SPA scaffold + Vite build → trezarr/web/static/)
  provides:
    - Dockerfile (multi-stage Node→Python; PUID/PGID; EXPOSE 6868; VOLUME /config)
    - entrypoint.sh (gosu-based privilege drop; creates user/group from PUID/PGID)
    - .dockerignore
    - docker-compose.example.yml
    - config.yaml.example (Phase-7 fields added)
  affects:
    - .planning/phases/07-web-ui-service-hardening/07-HUMAN-UAT.md (Wave 6 items appended)
tech_stack:
  added:
    - "Docker multi-stage build (Node 20-slim builder + Python 3.12-slim runtime)"
    - "gosu (apt-get) — clean privilege drop from root to PUID:PGID"
    - "curl (apt-get) — Docker HEALTHCHECK against GET /api/health"
    - "uv --frozen --no-dev --no-editable (production dependency install in image)"
  patterns:
    - "Stage 1: node:20-slim AS node-builder; npm ci --prefer-offline (lockfile); npm run build → /app/trezarr/web/static"
    - "Stage 2: python:3.12-slim; uv sync --frozen --no-dev --no-editable; COPY --from=node-builder static"
    - "entrypoint.sh: getent group/passwd checks before groupadd/useradd; chown /config; exec gosu PUID:PGID"
    - "HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -f http://localhost:6868/api/health"
    - "docker-compose.example.yml: ${TREZARR_*_API_KEY} env-var references for secrets (T-07-06-02)"
key_files:
  created:
    - Dockerfile
    - entrypoint.sh
    - .dockerignore
    - docker-compose.example.yml
  modified:
    - config.yaml.example (Phase-7 service runtime + Bazarr fields added; SECURITY note added)
    - .planning/phases/07-web-ui-service-hardening/07-HUMAN-UAT.md (Wave 6 items appended)
decisions:
  - "Use python:3.12-slim + gosu entrypoint (not LSIO base) — RESEARCH.md recommends this as the MVP approach; simpler than s6-overlay for a single-user service that doesn't need multi-process init"
  - "gosu installed via apt-get (same mechanism as official Postgres/Redis images) — T-07-06-SC confirms legitimacy"
  - "npm ci --prefer-offline in node-builder stage for reproducible SPA build from lockfile (T-07-06-04)"
  - "uv sync --frozen --no-dev --no-editable in Python runtime stage — frozen ensures deterministic image builds"
  - "HEALTHCHECK start-period=30s: lifespan runs DB migration + scheduler startup before first health probe"
  - "docker-compose.example.yml uses := syntax for optional keys and :? for required TREZARR_LLM_API_KEY (required = must be set by operator)"
  - "Docker daemon unavailable in autonomous run — docker build + PUID/PGID ownership UAT deferred to 07-HUMAN-UAT.md Wave 6 (tests 7-12)"
metrics:
  duration: "12 minutes"
  completed: "2026-06-02"
  tasks: 3
  files: 6
---

# Phase 7 Plan 6: Docker Packaging Summary

Multi-stage Dockerfile (Node 20-slim → Python 3.12-slim) with gosu PUID/PGID drop-privilege entrypoint, HEALTHCHECK, /config volume, and port 6868; plus docker-compose.example.yml and config.yaml.example Phase-7 additions — closes SVC-01.

## What Was Built

### Task 1: Dockerfile + entrypoint.sh + .dockerignore + docker-compose.example.yml

Created `Dockerfile` with two stages:

**Stage 1 — node-builder (Node 20-slim):**
- `WORKDIR /app`; copies `frontend/package.json` + `frontend/package-lock.json` first for layer-cache efficiency
- `npm ci --prefer-offline` installs from lockfile (T-07-06-04 reproducibility)
- `npm run build` compiles the Vite SPA; output goes to `/app/trezarr/web/static/` (vite.config.ts `outDir: ../trezarr/web/static`)

**Stage 2 — Python runtime (python:3.12-slim):**
- Installs `gosu` + `curl` via apt-get (privilege drop + HEALTHCHECK; T-07-06-SC)
- Installs `uv` via pip; copies `pyproject.toml` + `uv.lock`
- `uv sync --frozen --no-dev --no-editable` — deterministic production install
- Copies `trezarr/`, `alembic/`, `alembic.ini`
- `COPY --from=node-builder /app/trezarr/web/static ./trezarr/web/static` — SPA from builder
- `COPY entrypoint.sh /entrypoint.sh` + `chmod +x`
- `VOLUME ["/config"]`; `EXPOSE 6868`; `ENV TREZARR_CONFIG_PATH=/config/config.yaml`
- `HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -f http://localhost:6868/api/health || exit 1`
- `ENTRYPOINT ["/entrypoint.sh"]`; `CMD ["trezarr", "serve"]`

Created `entrypoint.sh`:
- Reads `PUID` (default 1000) and `PGID` (default 1000) env vars
- Uses `getent group $PGID` / `getent passwd $PUID` guards before `groupadd`/`useradd`
- `chown -R $PUID:$PGID /config` — ensures DB, config, quarantine, logs are writable
- `exec gosu $PUID:$PGID "$@"` — clean privilege drop replacing this script's PID (INTG-04)

Created `.dockerignore`:
- Excludes: `frontend/node_modules/`, `frontend/dist/`, `trezarr/web/static/` (rebuilt in node-builder), `.planning/`, `.claude/`, `.codegraph/`, `.gsd*`, `tests/`, `__pycache__/`, `*.pyc`, `.git/`, `.env`, build artifacts

Created `docker-compose.example.yml`:
- Service: image `trezarr:latest` (build: . commented alternative); port `6868:6868`
- Volumes: `./config:/config`, `/path/to/media:/media`
- Environment: `PUID=${PUID:-1000}`, `PGID=${PGID:-1000}`, `TREZARR_LLM_API_KEY=${...:?}` (required), optional `*_API_KEY` vars for Sonarr/Radarr/Bazarr
- `restart: unless-stopped`
- Detailed comment block: media path alignment requirement, security note, reverse-proxy guidance (D-78)

### Task 2: checkpoint:human-verify (auto-deferred)

Docker build + PUID/PGID ownership verification deferred — Docker daemon unavailable in autonomous run. 6 UAT items (tests 7-12) appended to `.planning/phases/07-web-ui-service-hardening/07-HUMAN-UAT.md` Wave 6 section:
- Test 7: docker build exits 0
- Test 8: `trezarr --help` shows "serve" subcommand
- Test 9: container starts; GET /api/health returns `{"status":"ok"}`
- Test 10: SPA loads at http://localhost:6868 in browser
- Test 11: /config files owned by host PUID:PGID (not root)
- Test 12: `docker compose -f docker-compose.example.yml config` validates syntax

### Task 3: Update config.yaml.example with Phase-7 fields

Added SECURITY note at top of `config.yaml.example` (T-07-06-02/T-07-06-05): directs operators to use `TREZARR_*_API_KEY` env vars instead of storing keys in the file.

Added Phase-7 service runtime section (D-76, D-77) with all 6 fields:
- `web_host: "0.0.0.0"` — bind address; comment explains localhost + reverse-proxy option (D-78)
- `web_port: 6868` — web UI and API port
- `poll_interval_seconds: 900` — 15-minute poll; source of truth alongside webhooks (D-65)
- `enable_webhooks: true` — inbound /webhook endpoint for Sonarr/Radarr/Bazarr triggers
- `enable_watchfiles: false` — default-off; poll + webhook cover MVP (D-65)
- `worker_max_concurrent_series: 2` — parallel series limit (D-68)

Added Phase-7 Bazarr connection section (D-76) with 4 fields:
- `bazarr_enabled: false`
- `bazarr_host: ""`
- `bazarr_port: 6767`
- `bazarr_api_key: ""` — with explicit env var guidance (T-07-06-05)

Verified YAML validity: `python -c "import yaml; yaml.safe_load(open('config.yaml.example'))"` — passes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Dockerfile + entrypoint.sh + .dockerignore + docker-compose.example.yml | 90bc933 | Dockerfile, entrypoint.sh, .dockerignore, docker-compose.example.yml |
| 2 | checkpoint:human-verify (auto-deferred) | — | 07-HUMAN-UAT.md (Wave 6 appended) |
| 3 | Update config.yaml.example with Phase-7 fields | ba9229d | config.yaml.example, 07-HUMAN-UAT.md |

## Verification Results

```
uv run pytest tests/ -q
# Result: 266 passed, 1 skipped, 4 xpassed, 1 warning in 7.14s
# No regressions from Dockerfile / config.yaml.example changes.
```

```
uv run python -c "import yaml; yaml.safe_load(open('config.yaml.example')); print('valid yaml')"
# Result: valid yaml
```

Static Dockerfile check (Docker daemon unavailable):
- All referenced files confirmed to exist: frontend/package.json, frontend/package-lock.json, pyproject.toml, uv.lock, trezarr/, alembic/, alembic.ini, entrypoint.sh
- `CMD ["trezarr", "serve"]` present at line 97
- `EXPOSE 6868` present
- `VOLUME ["/config"]` present
- `HEALTHCHECK` present
- `PUID`/`PGID` handled via entrypoint.sh

Docker build + runtime UAT deferred to 07-HUMAN-UAT.md Wave 6 (tests 7-12).

## Deviations from Plan

### Auto-fixed Issues

None.

### Auto-deferred (Task 2 checkpoint)

**Task 2: checkpoint:human-verify (Docker build + PUID/PGID ownership)**
- **Type:** auto-deferred (auto-mode run, Docker daemon not running)
- **Action:** Appended Wave 6 section with 6 UAT items (tests 7-12) to 07-HUMAN-UAT.md
- **Outcome:** Plan finalized; Docker smoke test and PUID/PGID ownership verification pending human review

## Known Stubs

None — all task-owned artifacts are complete. Docker runtime verification (build + PUID/PGID) is deferred to human UAT, not a code stub.

## Threat Flags

No new threat surface beyond the plan's threat model:
- T-07-06-01: Container always drops to PUID:PGID via gosu in entrypoint.sh; default 1000:1000 is never root — MITIGATED
- T-07-06-02: docker-compose.example.yml uses ${TREZARR_*_API_KEY} env var references, not literal keys — MITIGATED
- T-07-06-04: npm ci --prefer-offline uses lockfile; packages are RESEARCH.md-approved — MITIGATED
- T-07-06-05: SECURITY note in config.yaml.example; bazarr_api_key example shows empty string with env var guidance — MITIGATED
- T-07-06-SC: gosu installed via apt-get (same as official Postgres/Redis Docker images; github.com/tianon/gosu) — MITIGATED

## Self-Check: PASSED

- Dockerfile exists at project root: FOUND
- entrypoint.sh exists at project root: FOUND
- .dockerignore exists at project root: FOUND
- docker-compose.example.yml exists at project root: FOUND
- Dockerfile contains CMD ["trezarr", "serve"]: FOUND (line 97)
- Dockerfile contains EXPOSE 6868: FOUND
- Dockerfile contains VOLUME ["/config"]: FOUND
- Dockerfile contains HEALTHCHECK: FOUND
- Dockerfile contains PUID/PGID handling (entrypoint.sh reference): FOUND
- Dockerfile contains FROM python:3.12-slim: FOUND
- config.yaml.example YAML-valid: CONFIRMED (python yaml.safe_load passes)
- config.yaml.example contains web_host/web_port/poll_interval_seconds/enable_webhooks/enable_watchfiles/worker_max_concurrent_series: CONFIRMED
- config.yaml.example contains bazarr_enabled/bazarr_host/bazarr_port/bazarr_api_key: CONFIRMED
- config.yaml.example contains SECURITY note: CONFIRMED
- 07-HUMAN-UAT.md Wave 6 items appended: CONFIRMED (tests 7-12)
- pytest 266 passed, 1 skipped, 4 xpassed: CONFIRMED
- Commit 90bc933 (Task 1): FOUND
- Commit ba9229d (Task 3): FOUND
