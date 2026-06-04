---
phase: 14-new-library-pages-nav-badge-wiring
plan: "02"
subsystem: frontend/nav-badges-routing
tags: [typescript, react, sidebar, badges, routing, 404]
dependency_graph:
  requires: [14-01]
  provides: [14-02-SidebarGroup, 14-02-nav-badges, 14-02-NotFound, 14-02-404-route]
  affects:
    - frontend/src/components/app-sidebar.tsx
    - frontend/src/pages/NotFound.tsx
    - frontend/src/App.tsx
tech_stack:
  added: []
  patterns: [SidebarGroup-wrapper, LibraryContext-consumer, Tailwind-group-data-selector, catch-all-route]
key_files:
  created:
    - frontend/src/pages/NotFound.tsx
  modified:
    - frontend/src/components/app-sidebar.tsx
    - frontend/src/App.tsx
decisions:
  - "Badge slot uses a wrapping <span className='flex items-center gap-1'> for LIVE+count pair; avoids ml-auto collision on individual badges when both render simultaneously"
  - "count/isLive derived inline in map callback (not extra useState) — context values are already computed by derived helpers; no local state needed"
  - "NotFound.tsx uses JSX entity &apos; for apostrophe in copy to avoid raw apostrophe in JSX (tsc strict)"
metrics:
  duration: "~8m"
  completed: "2026-06-03"
  tasks: 2
  files: 3
---

# Phase 14 Plan 02: Sidebar Badges + SidebarGroup + 404 Route Summary

Sidebar Series/Movies rows wired to LibraryContext for count (purple) and LIVE (emerald) badges; SidebarGroup wrapper added for proper p-2 inset (WR-01); minimal NotFound.tsx page and catch-all Route added to App.tsx (WR-03). Build stayed green throughout.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add SidebarGroup wrapper + LIVE/count badges to app-sidebar.tsx | 26e7e4d | frontend/src/components/app-sidebar.tsx |
| 2 | Create NotFound.tsx and add catch-all route to App.tsx (WR-03) | f328b52 | frontend/src/pages/NotFound.tsx, frontend/src/App.tsx |

## What Was Built

**Task 1 — app-sidebar.tsx:**
- `SidebarGroup` imported and wrapping `SidebarMenu` inside `SidebarContent` (WR-01 fixed)
- `useLibraryContext`, `getSeriesLiveBadge`, `getMoviesLiveBadge`, `getSeriesNeedsViCount`, `getMoviesNeedsViCount` imported from `../contexts/LibraryContext`
- `Badge` imported from `./ui/badge`
- Per-item `isLive` and `count` derived inline from context data in the `NAV_ITEMS.map()` callback
- Badge slot rendered only for `/series` and `/movies` rows — other rows unaffected
- LIVE badge: `bg-emerald-600 text-white`; Count badge: `bg-[hsl(var(--primary))] text-primary-foreground`
- Both badges wrapped in `<span className="flex items-center gap-1">` for correct horizontal layout
- Both badges have `group-data-[collapsible=icon]:hidden` — hidden in icon rail mode (no room)
- Count badge auto-hides at zero (conditional `{count > 0 && ...}`)
- `<span className="flex-1">` on label text to push badge span to the right

**Task 2 — NotFound.tsx + App.tsx:**
- `frontend/src/pages/NotFound.tsx` created: heading "Page not found", muted body text, `<Button variant="outline">Go to Series</Button>` (navigates to hardcoded `/series` literal)
- `App.tsx`: `NotFound` imported; `<Route path="*" element={<NotFound />} />` added as last child of layout route
- App.tsx docstring updated to include the catch-all route entry

## Build Verification

```
cd frontend && npm run build
> tsc -b && vite build
✓ 1743 modules transformed.
✓ built in 1.30s
```

**Result: EXIT 0 — tsc strict + vite build green (both tasks).**

## Deviations from Plan

None — plan executed exactly as written. The inline `isLive`/`count` derivation in the map callback (rather than a named NavBadges sub-component) kept the badge logic under 20 lines as the plan specified.

## Known Stubs

None. This plan wires real data from LibraryContext — badges show real counts derived from `SeriesItem.translated_count / total_count` and real LIVE state derived from `errors[]`. The sidebar badges are `null`-safe (hidden when no library page has loaded).

## Threat Flags

None. NotFound.tsx renders only static copy (no URL reflection). Navigate target is hardcoded `/series`. No new network endpoints introduced.

## Self-Check

**Created files exist:**
- `frontend/src/pages/NotFound.tsx` — YES

**Modified files exist:**
- `frontend/src/components/app-sidebar.tsx` — YES
- `frontend/src/App.tsx` — YES

**Commits exist:**
- 26e7e4d — YES (Task 1)
- f328b52 — YES (Task 2)

**Build result:** EXIT 0 — confirmed above (both task-level builds).

## Self-Check: PASSED
