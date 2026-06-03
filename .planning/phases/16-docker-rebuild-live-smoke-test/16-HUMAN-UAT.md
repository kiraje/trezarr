---
status: partial
phase: 16-docker-rebuild-live-smoke-test
source: [16-VERIFICATION.md, 12-HUMAN-UAT.md, 13-HUMAN-UAT.md, 14-HUMAN-UAT.md, 15-HUMAN-UAT.md]
started: 2026-06-04
updated: 2026-06-04
---

## Current Test

[awaiting human smoke test — this is the v1.1 milestone's live acceptance gate. Run against the real *arr stack on :6868.]

> NOTE: The autonomous run rebuilt the production image (`trezarr:phase16-smoke`, `--no-cache`) and verified it BUILDS. Deploying it to :6868 (which replaces your running daemon), and all browser/live checks below, are intentionally left for you to perform and verify — the autonomous chain holds here per the human-verify gate.

## Tests

### 1. Production image builds (SC1a) — automated, see 16-VERIFICATION.md
expected: `docker build --no-cache` completes the full multi-stage build (node Vite → python:3.12-slim) without error.
result: [filled by autonomous run — see VERIFICATION]

### 2. Container starts + health (SC1b)
expected: Deploy the rebuilt image; it starts on :6868 and `GET /api/health` returns 200. (Suggested: `docker build -t <your-prod-tag> .` then restart your compose service, or retag `trezarr:phase16-smoke`.)
result: [pending]

### 3. All six nav routes render (SC2) — covers Phase 12/14/15 visual deferrals
expected: In the browser at :6868, navigate /series, /movies, /queue, /history, /bible, /settings. Each renders the new shadcn purple dashboard with no blank pages, no missing styles, no legacy hex colors. Sidebar shows the accent bar on the active route; count + LIVE badges appear where *arr is connected; Cmd/Ctrl+B collapses to the icon rail and persists across reload.
result: [pending]

### 4. Series detail with real Bazarr data (SC3) — covers Phase 13/14 deferrals
expected: Open a real Sonarr series (/series/:id). Episodes are grouped by season (latest auto-expanded); each episode shows the blue Audio badge + subtitle-language badges (amber=source, purple=VI, VI:HI when applicable). The real series TITLE shows in the heading (not "Series #5"). Confirm the live Bazarr inventory populates subtitles — i.e. the `seriesid[]` param form is honored by your Bazarr at 192.168.5.42 (Phase-13 carry-forward); if subtitles[] are empty for episodes that DO have subs in Bazarr, the param form needs flipping to plain `seriesid`. When Bazarr is unreachable, the subtitle column is suppressed (not empty badges) with the amber note.
result: [pending]

### 5. Translate flow (SC4a) — covers Phase 14 deferral
expected: Click Translate on an episode (and on a season header); the item enqueues and the view navigates to /queue where the job appears. The Translate button is absent for episodes with no file. A season-translate that fully fails does NOT navigate (shows an error).
result: [pending]

### 6. SPA deep-link fallback (SC4b)
expected: Hard-refresh (or type directly) `/series/42` in the address bar — it serves index.html and loads SeriesDetail (not a JSON 404). Same for /movies and /series. A missing asset (e.g. /assets/nope.js) still 404s honestly.
result: [pending]

### 7. Settings save round-trip
expected: Open /settings, change a value, save; the masked-secret + auto-enable-on-save behavior works; a Sonner toast confirms; reload shows the persisted value.
result: [pending]

### 8. BibleEditor behavior intact (Phase 15 deferral)
expected: Open the Bible Editor for a series; all five tabs (Characters, Address Map, Term Dictionary, Register, Overrides) load; lock/provenance badges render; field-history panels populate; PronounCombo works; attempting to lock an empty term is hard-blocked (D-87). Behavior identical to pre-reskin.
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
