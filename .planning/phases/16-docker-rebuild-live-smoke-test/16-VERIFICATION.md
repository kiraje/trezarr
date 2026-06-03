---
status: human_needed
phase: 16-docker-rebuild-live-smoke-test
requirement_ids: [RSK-03]
verified: 2026-06-04
score: "2/2 automated must-haves verified; live smoke test pending human"
---

# Phase 16 Verification — Docker Rebuild + Live Smoke Test

## Automated (verified by the autonomous run)

### ✓ SC1a — Production image builds (multi-stage, --no-cache)
`docker build --no-cache -t trezarr:phase16-smoke .` completed with **EXIT 0**.
- Stage 1 (node:20-slim): `npm ci` (sonner v2.0.7 resolved from lockfile) + `npm run build` (tsc + vite) succeeded.
- Stage 2 (python:3.12-slim): uv sync + project install + SPA copy succeeded.
- Image: `trezarr:phase16-smoke`, 413MB.
- Built SPA present in image at `/app/trezarr/web/static/{index.html,assets/}`; `index.html` carries `class="dark"` (purple theme).
- The new frontend (Series/Movies/SeriesDetail pages, sidebar badges, Sonner, deleted Toast.tsx, reskinned pages) all compile into the production artifact.

### ✓ SC4b — SPA deep-link fallback is route-agnostic (static analysis)
`SPAStaticFiles` (trezarr/web/app.py:47-83) falls back to `index.html` for ANY extensionless path not under `/api` or `/webhook`, with `os.path.normpath` handling nested paths. The new routes `/series`, `/movies`, `/series/:id` are therefore covered with no code change; missing assets (`.js/.css/...`) still return honest 404s. Runtime confirmation is item 6 of the human smoke test.

## Human verification required (live smoke test — RSK-03)

This phase's remaining success criteria require the running container on :6868 against the real
*arr stack and a browser — they cannot be confirmed autonomously and (per the human-verify hold)
are intentionally left for the user. See `16-HUMAN-UAT.md` for the full 8-item checklist:

- SC1b — container starts on :6868, `/api/health` → 200
- SC2 — all six nav routes render the new dashboard (no blank pages / missing styles)
- SC3 — real Sonarr series detail shows season-grouped episodes with audio + Bazarr subtitle badges; confirms the live Bazarr `seriesid[]` param form (Phase-13 carry-forward)
- SC4a — translate flow enqueues + appears in Queue
- SC4b — deep-link hard-refresh on `/series/42` serves index.html (runtime confirmation)
- Settings save round-trip; BibleEditor 5-tab behavior intact (Phase-15 carry-forward)

## Status

**human_needed** — the milestone is code-complete and the production image builds; the v1.1
acceptance gate is the live smoke test, held for the user. Milestone lifecycle (audit →
complete → cleanup) is NOT run until the user confirms the smoke test passes.
