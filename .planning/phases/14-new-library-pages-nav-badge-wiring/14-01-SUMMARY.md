---
phase: 14-new-library-pages-nav-badge-wiring
plan: "01"
subsystem: frontend/api-types
tags: [typescript, react, context, library-api, phase-13-types]
dependency_graph:
  requires: [phase-13]
  provides: [14-01-client-types, 14-01-LibraryContext]
  affects: [frontend/src/api/client.ts, frontend/src/contexts/LibraryContext.tsx, frontend/src/App.tsx]
tech_stack:
  added: []
  patterns: [React.createContext, React.useMemo, derived-helpers, deprecated-jsDoc]
key_files:
  created:
    - frontend/src/contexts/LibraryContext.tsx
  modified:
    - frontend/src/api/client.ts
    - frontend/src/pages/Library.tsx
    - frontend/src/App.tsx
decisions:
  - "getSeriesEpisodes() return type changed to SeriesEpisodesResponse; Library.tsx compat fixed by flattening seasons inline"
  - "LibraryProvider wraps BrowserRouter (outer) so sidebar can read context without being inside any specific route"
  - "Derived helpers exported from context file (not sidebar) for testability and future reuse"
metrics:
  duration: "2m 28s"
  completed: "2026-06-04"
  tasks: 2
  files: 4
---

# Phase 14 Plan 01: API Types + LibraryContext Foundation Summary

TypeScript Phase-13 API contract types added to client.ts and LibraryContext provider created, giving Series/Movies pages and the sidebar a shared data layer without duplicate fetches.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update client.ts — Phase-13 types + fetch wrappers | d8becea | frontend/src/api/client.ts, frontend/src/pages/Library.tsx |
| 2 | Create LibraryContext.tsx — shared GET /api/library state | 776426f | frontend/src/contexts/LibraryContext.tsx, frontend/src/App.tsx |

## What Was Built

**Task 1 — client.ts Phase-13 types:**
- Added `SeriesItem` (with `translated_count`, `total_count`) mirroring library.py shape exactly
- Added `MovieItem` (with `source_sub_found`, `translated_count`, `total_count`)
- Added `LibraryResponse` (new — `SeriesItem[]` + `MovieItem[]` + errors)
- Added `SubtitleEntry`, `EpisodeEnrichedRow`, `SeasonGroup`, `SeriesEpisodesResponse` envelope
- Added `TranslateRequest` interface
- Updated `getSeriesEpisodes()` return type from `EpisodeRow[]` → `SeriesEpisodesResponse`
- Marked old `LibrarySeriesItem`, `LibraryMovieItem`, `EpisodeRow` as `@deprecated` (Library.tsx still compiles)

**Task 2 — LibraryContext.tsx:**
- `LibraryProvider` wraps the entire app (above BrowserRouter) so any consumer can access data
- `useLibraryContext()` hook with null-guard throw for missing provider detection
- Four derived helpers: `getSeriesLiveBadge`, `getMoviesLiveBadge`, `getSeriesNeedsViCount`, `getMoviesNeedsViCount` (D-09 proxy count, D-10 LIVE derivation)
- `LibraryProvider` wired into `App.tsx` wrapping `<BrowserRouter>`

## Build Verification

```
cd frontend && npm run build
> tsc -b && vite build
✓ 1741 modules transformed.
✓ built in 1.06s
```

**Result: EXIT 0 — tsc strict + vite build green.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Library.tsx type break from getSeriesEpisodes return type change**
- **Found during:** Task 1 verification
- **Issue:** `getSeriesEpisodes()` return type changed to `SeriesEpisodesResponse` but Library.tsx assigns the result to `useState<EpisodeRow[] | null>` — TypeScript would fail
- **Fix:** Updated Library.tsx to flatten `envelope.seasons.flatMap(s => s.episodes.map(...))` into the `EpisodeRow[]` shape expected by the existing state — backward-compatible adapter in the legacy page
- **Files modified:** `frontend/src/pages/Library.tsx`
- **Commit:** d8becea

## Known Stubs

None. This plan creates type contracts and a context shell only. No data rendering that could produce stub values.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundaries introduced. LibraryContext is client-side only; data flows from existing GET /api/library fetch through context to sidebar.

## Self-Check

**Created files exist:**
- `frontend/src/contexts/LibraryContext.tsx` — YES (created in task 2)

**Commits exist:**
- d8becea — YES (feat(14-01): Phase-13 types)
- 776426f — YES (feat(14-01): LibraryContext)

**Build result:** EXIT 0 — confirmed above.

## Self-Check: PASSED
