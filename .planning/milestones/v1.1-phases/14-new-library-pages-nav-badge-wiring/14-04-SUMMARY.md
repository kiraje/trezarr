---
phase: 14-new-library-pages-nav-badge-wiring
plan: "04"
subsystem: frontend
tags:
  - movies-list
  - library-page
  - search-filter-sort
  - nav-badge
  - progress-bar
dependency_graph:
  requires:
    - 14-01  # LibraryContext + client.ts types
    - 14-02  # sidebar badge wiring (reads LibraryContext setLibraryData provides)
    - 14-03  # Series.tsx sibling pattern reference
  provides:
    - real Movies list page at /movies
    - setLibraryData call populating LibraryContext for sidebar movies count + LIVE badges
  affects:
    - frontend/src/pages/Movies.tsx
tech_stack:
  added: []
  patterns:
    - plain HTML table (D-01, jolly-ui Table beta avoided)
    - debounced search (250ms, useRef + setTimeout, no library)
    - client-side filter + sort (same pattern as Series.tsx)
    - disabled Translate button with Tooltip (source_path absent from API)
key_files:
  created: []
  modified:
    - frontend/src/pages/Movies.tsx
decisions:
  - "Translate button always disabled with tooltip 'Source path unavailable' — MovieItem has no source_path field per API contract; documented inline per 14-UI-SPEC.md"
  - "Plain HTML table used over jolly-ui React Aria Table (D-01 — beta stability risk avoided)"
  - "handleTranslate included but only reachable if API adds source_path; button is disabled=true for all rows"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-04"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 1
---

# Phase 14 Plan 04: Movies List Page Summary

Real Movies list page (LIB-02, LIB-06, LIB-07, NAV-03) — dense table of Radarr movies with amber SOURCE badge, progress bar, disabled Translate button with tooltip, and debounced search/filter/sort wired to LibraryContext.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement Movies.tsx — full list page with table, Translate button, search/filter/sort | 34730a2 | frontend/src/pages/Movies.tsx |

## Verification

- `cd frontend && npm run build` — EXIT 0 (tsc -b strict clean + vite build clean)
- Build output: 471.15 kB JS, 43.41 kB CSS, 1751 modules transformed

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The disabled Translate button is intentional per spec (not a stub): the API does not expose `source_path` for movies. The `canTranslate` path renders the button correctly disabled. This is a documented API limitation, not unfinished work.

## Threat Flags

No new threat surface beyond what T-14-04-01 and T-14-04-02 in the plan's threat model cover:
- Movie title/year rendered as JSX text nodes — React auto-escapes (T-14-04-01 mitigated)
- Translate button always disabled; POST /api/translate not reachable from UI (T-14-04-02 accepted)

## Self-Check: PASSED

- [x] frontend/src/pages/Movies.tsx — FOUND (408 lines, full implementation)
- [x] commit 34730a2 — FOUND in git log
- [x] npm run build — EXIT 0
