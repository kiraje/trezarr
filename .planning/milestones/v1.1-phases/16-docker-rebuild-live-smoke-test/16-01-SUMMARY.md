---
id: 16-01
phase: 16-docker-rebuild-live-smoke-test
status: complete
completed: 2026-06-04
requirement_ids: RSK-03
---

# Summary — 16-01: Docker Rebuild + Live Smoke Test

## What was done

- **Multi-stage image rebuilt** with `docker build --no-cache` (node:20 Vite build →
  python:3.12-slim runtime). Build EXIT 0; the built SPA (`index.html` + hashed assets)
  ships at `/app/trezarr/web/static`. `sonner` resolved from the lockfile; the deleted
  `Toast.tsx` caused no dangling imports.
- **Compose authored**: `docker-compose.yml` mirrors the live daemon (image `trezarr:local`
  / `build: .`, `/config` + `/data/media` binds, PUID 501 / PGID 20, `TREZARR_LLM_*` env
  with the API key interpolated from a gitignored `.env`). `docker-compose.example.yml`
  realigned to match; `.env.example` documents the required key.
- **Deployed on :6868** via `docker compose up -d` — container `trezarr` Up (healthy),
  `/api/health` → `{"status":"ok"}`, clean lifespan (alembic migrate + scheduler), no
  crash-loop. Server-side checks: `/series` + `/movies` → 200 text/html (SPA deep-link
  fallback for new routes), `/assets/<missing>` → honest 404, `/api/library` → 200.
- **Backlog nits fixed** before final image (commits 06efaa9 / ad98a68 / 04ad521):
  reciprocal-save double-toast, ConnectionTestButton resetKey, BibleEditor Fragment keys,
  FieldHistoryPanel close button, sidebar aria-keyshortcuts. Final image `trezarr:local`
  = `5270c77a1569`; redundant `trezarr:phase16-smoke` tag dropped; `trezarr:rollback`
  retained as the pre-v1.1 safe rollback.
- **Live smoke test passed** (operator-verified, 8/8 — `16-HUMAN-UAT.md`): all six nav
  routes render, season-grouped episode badges populate from live Bazarr, translate flow
  enqueues, Settings save round-trips, all five BibleEditor tabs behave identically, SPA
  deep-link fallback intact.

## Verification

`16-VERIFICATION.md` → **status: passed**. RSK-03 satisfied. Build green; operator smoke
test passed; deployed image matches committed source (HEAD).

## Notes / carry-forward

- Bazarr `seriesid[]` param confirmed honored by the live instance (subtitle badges
  populated) — the Phase-13 `TODO(phase-16)` is resolved in practice.
- No code changes in this plan beyond packaging (Dockerfile/compose) + the pre-image
  backlog fixes; all application behavior was delivered in phases 12–15.
