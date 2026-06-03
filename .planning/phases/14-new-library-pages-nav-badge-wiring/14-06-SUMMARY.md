---
phase: 14-new-library-pages-nav-badge-wiring
plan: 06
subsystem: ui
tags: [react, vite, typescript, cleanup, routing]

# Dependency graph
requires:
  - phase: 14-new-library-pages-nav-badge-wiring/14-02
    provides: catch-all NotFound route that now handles /library
  - phase: 14-new-library-pages-nav-badge-wiring/14-03
    provides: Series.tsx replaces library series tab
  - phase: 14-new-library-pages-nav-badge-wiring/14-04
    provides: Movies.tsx replaces library movies tab
  - phase: 14-new-library-pages-nav-badge-wiring/14-05
    provides: SeriesDetail.tsx replaces library episode drilldown
provides:
  - Library.tsx deleted; no transitional page remains
  - /library route removed from App.tsx; catch-all NotFound now handles it
  - Deprecated EpisodeRow, LibrarySeriesItem, LibraryMovieItem interfaces removed from client.ts
  - D-11 fully resolved: zero references to old Library.tsx in the codebase
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-11 cleanup pattern: delete transitional file only after all replacement pages are functional and build is verified"

key-files:
  created: []
  modified:
    - frontend/src/App.tsx
    - frontend/src/api/client.ts
  deleted:
    - frontend/src/pages/Library.tsx

key-decisions:
  - "Retained LibraryContext/LibraryProvider and LibraryResponse (new Phase-13 shape) — only the @deprecated legacy types were removed"
  - "Grep verified that all remaining Library-named symbols are intentional (LibraryContext, LibraryResponse, getLibrary) — none are Library.tsx artifacts"

patterns-established:
  - "Wave 4 cleanup: always run build gate before deletion to confirm prior waves are clean, then run again after to confirm zero dangling refs"

requirements-completed: [LIB-01, LIB-02, LIB-03, LIB-05, NAV-03]

# Metrics
duration: 5min
completed: 2026-06-03
---

# Phase 14 Plan 06: Library.tsx Deletion + Route/Type Cleanup Summary

**D-11 completed: Library.tsx deleted, /library route removed, three @deprecated legacy types purged; build exits 0 with 1754 modules (1755 before deletion)**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-03T18:54:00Z
- **Completed:** 2026-06-03T18:59:44Z
- **Tasks:** 1
- **Files modified:** 2 modified, 1 deleted

## Accomplishments
- Deleted `frontend/src/pages/Library.tsx` (the transitional Phase-12 page, now fully replaced by Series/Movies/SeriesDetail)
- Removed `import Library` and `<Route path="library">` from App.tsx; /library now falls through to the catch-all NotFound route added in plan 02
- Removed three `@deprecated` legacy interfaces from client.ts: `LibrarySeriesItem`, `LibraryMovieItem`, `EpisodeRow`
- Build gate confirmed green both before (precondition) and after (post-deletion): `npm run build` exits 0

## Task Commits

Each task was committed atomically:

1. **Task 1: Delete Library.tsx, remove /library route + deprecated types** - `ff9bc24` (chore)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `frontend/src/pages/Library.tsx` - DELETED (transitional page, replaced by Series/Movies/SeriesDetail)
- `frontend/src/App.tsx` - Removed Library import, /library route; updated JSDoc route table
- `frontend/src/api/client.ts` - Removed @deprecated LibrarySeriesItem, LibraryMovieItem, EpisodeRow interfaces

## Decisions Made
- Retained `LibraryContext`, `LibraryProvider`, `LibraryResponse`, and `getLibrary()` — these are Phase-13 architecture (not the deprecated Library.tsx), intentionally kept for Series.tsx/Movies.tsx badge wiring
- Remaining `Library` symbol occurrences confirmed correct: `LibraryContext` (context provider), `LibraryResponse` (new response shape), `getLibrary()` (API wrapper) — all from plan 01 design

## Deviations from Plan

None — plan executed exactly as written. Precondition build check passed, all three edits applied cleanly, post-deletion build green on first pass.

## Issues Encountered

None.

## Known Stubs

None introduced by this plan. Pure deletion/cleanup.

## Threat Flags

None. No new network endpoints, auth paths, or trust-boundary surface introduced.

## Next Phase Readiness
- D-11 fully resolved. Phase 14 is complete: all six real nav routes (/series, /movies, /series/:id, /queue, /history, /settings) functional with badge wiring; /library returns NotFound.
- No blockers.

---
*Phase: 14-new-library-pages-nav-badge-wiring*
*Completed: 2026-06-03*
