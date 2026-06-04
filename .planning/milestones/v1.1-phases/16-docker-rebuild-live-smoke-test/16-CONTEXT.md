# Phase 16: Docker Rebuild + Live Smoke Test - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** auto (decisions auto-selected from locked research/requirements; no user prompts)

<domain>
## Phase Boundary

Rebuild the multi-stage Docker image from scratch (`--no-cache`: node Vite build →
`python:3.12-slim`), run the new dashboard on **:6868 against the live *arr stack**
(Sonarr/Radarr/Bazarr at 192.168.5.42), and verify the v1.1 UI works end-to-end —
all six nav routes, episode badges from live Bazarr, the translate→Queue flow,
Settings save, and the SPA deep-link fallback. This is the **v1.1 release gate**:
a build + live-smoke verification phase, not a feature-build phase.

**In scope (RSK-03):**
- Multi-stage `docker build --no-cache` (verify the existing Phase-7 Dockerfile
  still builds the new SPA → `trezarr/web/static/` → python image)
- Run the image on :6868; `/api/health` returns 200
- Live browser smoke test of the 4 ROADMAP success criteria
- Capture/triage any smoke failures (file follow-ups; do not silently pass)

**Out of scope:**
- Any new feature or page work (Phases 12–15 deliver those; this only verifies)
- Backend/frontend code changes beyond fixing a build break the rebuild surfaces
  (a genuine build/deploy fix is in scope; new functionality is not)
- The Dockerfile is expected to already work (Phase 7) — only touch it if the
  multi-stage build actually breaks on the new SPA

</domain>

<decisions>
## Implementation Decisions

### Build
- **D-01:** `docker build --no-cache` of the existing multi-stage Dockerfile
  (node stage runs `npm run build` → `../trezarr/web/static`; copied into
  `python:3.12-slim`). Confirm the build completes without error and the image
  starts on **:6868** with `/api/health` → 200. The build invariants from Phase 11
  (no Vite `base`, `outDir ../trezarr/web/static`, `tsc -b && vite build`) must hold
  through the container build.

### Smoke Test Scope (the 4 ROADMAP success criteria)
- **D-02:** Live browser checklist against the running container + live *arr:
  1. All six sidebar routes render the new shadcn dashboard with no blank pages /
     missing styles: `/series`, `/movies`, `/queue`, `/history`, `/bible`, `/settings`.
  2. A real Sonarr series' detail page shows season-grouped episodes with audio +
     subtitle-language badges populated from live Bazarr.
  3. Triggering a translation from the Series detail enqueues it and the Queue page
     shows the job.
  4. SPA deep-link fallback intact: a hard-refresh on `/series/42` serves
     `index.html` (not a 404). Plus `/` → `/series` redirect and a Settings save.

### Deployment Safety (live environment)
- **D-03:** The target is a **real, running deployment** (Dockerized daemon on
  :6868 wired to live Sonarr/Radarr/Bazarr + the deepseek LLM endpoint; media at
  /Volumes/Plex/... → /data/media). Before rebuilding, **tag/keep the current
  working image** (e.g. `:prev`) so a failed smoke test can roll back immediately;
  do NOT delete the prior image until smoke passes. Preserve the `/config` volume
  (DB + config.yaml) — never recreate it.

### Release Gate (human verify — --auto HOLDS)
- **D-04:** Phase 16 ends with a **human visual smoke-test UAT** — the milestone
  release gate. Like the Phase-11 D-09 gate, the `--auto`/`--chain` pipeline
  **HOLDS** here: do NOT auto-close the phase or the milestone with the smoke test
  pending. A human confirms the live :6868 dashboard before the phase (and v1.1)
  is marked complete.

### Failure Handling
- **D-05:** If the smoke test reveals a defect, **do not silently pass**. Triage:
  a build/deploy break is fixable in-phase; a feature defect traceable to Phases
  12–15 is recorded as a follow-up (gap/issue) against that phase. Roll back to the
  `:prev` image if the live service is left non-functional.

### Claude's Discretion
- Exact smoke-checklist ordering and which real series/episode to use for the badge
  + translate test; image tag naming; whether to script any of the health/route
  checks (`curl /api/health`, route fetches) vs purely manual browser verification.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 Research & inherited build
- `.planning/research/ARCHITECTURE.md` §7 Phase F (Docker rebuild + smoke test:
  node→python:3.12-slim, run on 6868 against live *arr, verify SPA/sidebar/series
  data/translate/deep-link).
- `.planning/phases/11-shadcn-foundation-purple-theme/11-CONTEXT.md` (D-08 build
  invariants: no Vite `base`, `outDir ../trezarr/web/static`, build script) and
  `12-CONTEXT.md` (SPA deep-link fallback served by the existing `SPAStaticFiles`).
- Phase 7 Docker packaging (the multi-stage Dockerfile + PUID/PGID + /config volume
  + port 6868) — `07-*` plans / `config.yaml.example`.

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — RSK-03 (multi-stage image rebuilt; new dashboard
  live-smoke-tested on :6868; SPA deep-link fallback intact).
- `.planning/ROADMAP.md` §"Phase 16" — goal + 4 success criteria (no-cache build +
  /api/health 200; all six routes render; live Series detail badges from Bazarr;
  translate enqueues→Queue + hard-refresh deep-link fallback).

### Live environment facts (memory)
- Live deployment is configured: Dockerized daemon :6868 ↔ real Sonarr/Radarr/Bazarr
  at 192.168.5.42 + deepseek endpoint; media /Volumes/Plex/... → /data/media. The
  deepseek endpoint needs `json_object` mode + raised timeout. Don't redo setup.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The multi-stage Dockerfile + `/config` volume + :6868 port already exist (Phase 7).
  This phase rebuilds and verifies — it should not need to author new Docker plumbing
  unless the new SPA breaks the node build stage.
- `/api/health` endpoint exists (Phase 7) for the liveness check.

### Established Patterns
- The Vite build writes to `trezarr/web/static`; FastAPI `StaticFiles(html=True)`
  serves it with the SPA fallback — the deep-link criterion rides on this.
- The live *arr stack + deepseek endpoint are already wired (memory); this is a
  verification pass, not a reconfiguration.

### Integration Points
- This phase exercises the FULL stack: Phase-12 shell, Phase-13 enriched endpoint
  (live Sonarr+Bazarr), Phase-14 pages/badges/translate, Phase-15 reskin — so it is
  also the de-facto integration test for the whole v1.1 milestone.

</code_context>

<specifics>
## Specific Ideas

- Tag the current working image before `--no-cache` rebuild (D-03) — the live
  service must be recoverable if smoke fails.
- The `--auto` chain HOLDS at the human smoke-UAT (D-04) — do not auto-complete the
  milestone with verification pending (matches the Phase-11 D-09 / yolo-hold rule).
- Use a real East-Asian series for the badge test so the audio + source-language
  badges (and the Phase-10 relational source selection) are exercised meaningfully.

</specifics>

<deferred>
## Deferred Ideas

- Automated E2E/browser test harness for the smoke checklist — out of scope for v1.1
  (the gate is a human UAT); could be a future hardening initiative.
- Any feature defect surfaced during smoke that traces to Phases 12–15 → a follow-up
  against that phase, not new scope here.

None outside the roadmapped phases — discussion stayed within phase scope.

</deferred>

---

*Phase: 16-docker-rebuild-live-smoke-test*
*Context gathered: 2026-06-04 (auto mode)*
