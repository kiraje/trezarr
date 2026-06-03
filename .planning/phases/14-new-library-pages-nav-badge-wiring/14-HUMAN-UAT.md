---
status: partial
phase: 14-new-library-pages-nav-badge-wiring
source: [14-VERIFICATION.md, 14-UI-REVIEW.md]
started: 2026-06-04
updated: 2026-06-04
---

## Current Test

[awaiting human testing — deferred to Phase 16 live smoke test against real *arr stack]

## Tests

### 1. Series list renders + navigation
expected: /series shows a dense table of all Sonarr series with a per-row "X/Y translated" progress bar; clicking (or Enter/Space on) a row navigates to /series/:id.
result: [pending]

### 2. Series detail season accordion
expected: Episodes grouped by season in a collapsible Accordion; the latest non-zero season is auto-expanded; Season 0 ordered last; the real series title shows in the heading.
result: [pending]

### 3. Episode badges
expected: Each episode row shows a blue Audio badge (Volume2 icon) and subtitle-language badges (CODE2 uppercase; amber=source, purple=VI; VI:HI when hi=true). When bazarr_available=false the entire subtitle column is suppressed and an amber "Bazarr unavailable" note shows.
result: [pending]

### 4. Translate flow (episode + season)
expected: Translate on an episode row or season header enqueues and navigates to Queue; the button is absent for episodes with no file; a season translate that fully fails does NOT navigate and shows an error.
result: [pending]

### 5. Movies list
expected: /movies shows all Radarr movies with amber SOURCE badge / status + progress bar; Translate button disabled-with-tooltip where source_path is unavailable.
result: [pending]

### 6. Search / filter / sort
expected: Both lists support 250ms-debounced title search, status filter (All / Needs VI / Translated / No files), and sort; results update correctly.
result: [pending]

### 7. Sidebar count + LIVE badges
expected: Series/Movies sidebar rows show a purple count badge of items needing VI (auto-hidden at zero) and an emerald LIVE badge when the backing *arr service is connected; both hide in icon-rail collapse.
result: [pending]

### 8. Loading / empty / error states
expected: Each page renders Skeleton loading, empty-after-filter, and *arr-down/error states with correct CTAs.
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
