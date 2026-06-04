---
phase: 14-new-library-pages-nav-badge-wiring
plan: "03"
subsystem: ui
tags: [react, typescript, shadcn, library-page, series-list, context, progress-bar]

requires:
  - phase: 14-01
    provides: SeriesItem + LibraryResponse types in client.ts; useLibraryContext + setLibraryData from LibraryContext.tsx
provides:
  - Real Series list page: dense table, per-row progress bar, debounced search, filter/sort, row navigation to /series/:id
  - setLibraryData() call after fetch populates LibraryContext (sidebar count + LIVE badges)
affects: [app-sidebar.tsx NAV-03, 14-04 SeriesDetail, 14-06 Library.tsx deletion]

tech-stack:
  added: []
  patterns:
    - "useCallback-wrapped load() for stable Retry button and useEffect dep"
    - "250ms debounce via useRef<ReturnType<typeof setTimeout>> — no external library"
    - "Plain HTML table (no jolly-ui Table component) per D-01 for sort stability"
    - "Derived filter/sort computed inline before return, not in state"

key-files:
  created: []
  modified:
    - frontend/src/pages/Series.tsx

key-decisions:
  - "Plain HTML table used (not jolly-ui Table) per D-01 — avoids beta stability risk; sort implemented in component state"
  - "useCallback wraps load() so it can be stable dep in useEffect and accessible for Retry button"
  - "Year column retained in table rows (spec shows year sub-label in Title cell; implemented as separate Year column matching table header)"

patterns-established:
  - "setLibraryData(result) called immediately after successful getLibrary() fetch — consistent pattern for Movies.tsx"
  - "isSonarrDown derived from data !== null && series.length === 0 && errors.some(e => e.source === 'sonarr') — use same pattern for Radarr in Movies.tsx"

requirements-completed: [LIB-01, LIB-06, LIB-07, NAV-03]

duration: 4min
completed: 2026-06-03
---

# Phase 14 Plan 03: Series List Page Summary

**Real Series list page with dense HTML table, per-row translation progress bars (bg-muted/bg-primary), 250ms-debounced title search, status filter dropdown, two sort buttons (Title/Progress), and setLibraryData() context wiring for sidebar badge population**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-03T18:45:00Z
- **Completed:** 2026-06-03T18:49:10Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Replaced Series.tsx stub with full series list page implementing LIB-01, LIB-06, LIB-07, NAV-03
- Dense HTML table with Title, Year, Progress (bar + fraction), and Translated columns; row click navigates to /series/:id
- Per-row ProgressBar helper renders bg-muted/bg-primary h-1.5 rounded-full bar; em dash when total_count === 0
- setLibraryData(result) wired after successful fetch — sidebar LIVE + count badges update without second fetch
- All error/loading/empty states implemented: Skeleton loading, Retry on error, Sonarr unavailable, Clear filters

## Task Commits

1. **Task 1: Implement Series.tsx — full list page with table, progress bar, search/filter/sort** - `9ee23ca` (feat)

## Files Created/Modified

- `frontend/src/pages/Series.tsx` - Real series list page replacing stub; 234 lines net implementation

## Decisions Made

- Plain HTML `<table>` used (not jolly-ui Table component) per D-01: avoids React Aria beta stability risk; sort is simpler to implement in component state anyway
- `useCallback` wraps `load()` function so it can be a stable `useEffect` dependency and also referenced from the Retry button onClick without stale-closure risk
- Year column is a standalone column in the table header/body rather than a sub-label in the Title cell — matches the table header spec in 14-UI-SPEC.md §Series List Page

## Deviations from Plan

None — plan executed exactly as written.

## Build Verification

```
cd frontend && npm run build
> tsc -b && vite build
✓ 1751 modules transformed.
✓ built in 1.09s
```

**Result: EXIT 0 — tsc strict + vite build green.**

## Known Stubs

None. The page fetches real data from GET /api/library and renders all fields from the API response. No hardcoded placeholder values.

## Threat Flags

None. All series data (title, year) rendered as JSX text nodes — React auto-escapes. `navigate('/series/' + s.id)` uses a typed integer from SeriesItem.id — cannot produce off-origin redirect. Search query used only in `.toLowerCase().includes()`, never injected into DOM.

## Self-Check

**Files exist:**
- `frontend/src/pages/Series.tsx` — YES

**Commits exist:**
- `9ee23ca` — YES (feat(14-03): implement real Series list page)

**Build result:** EXIT 0 — confirmed above.

## Self-Check: PASSED
