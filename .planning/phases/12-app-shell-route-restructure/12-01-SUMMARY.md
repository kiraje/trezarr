---
phase: 12
plan: "01"
subsystem: frontend
tags: [app-shell, sidebar, routing, nav, react-router, shadcn]
dependency_graph:
  requires: [phase-11-shadcn-foundation]
  provides: [layout-route-shell, six-item-nav, series-movies-routes]
  affects: [App.tsx, AppShell.tsx, all-page-routes]
tech_stack:
  added: []
  patterns:
    - shadcn SidebarProvider + Sidebar composing layout-route shell
    - useLocation prefix-match active state (pathname === to || startsWith(to+"/"))
    - onClick navigate(to) (not asChild+anchor) for Radix Slot compatibility
    - border-l-2 border-transparent data-[active=true]:border-sidebar-primary accent-bar on SidebarMenuButton
key_files:
  created:
    - frontend/src/pages/Series.tsx
    - frontend/src/pages/Movies.tsx
    - frontend/src/pages/SeriesDetail.tsx
    - frontend/src/components/app-sidebar.tsx
  modified:
    - frontend/src/components/AppShell.tsx
    - frontend/src/App.tsx
decisions:
  - D-01 collapsible=icon + SidebarRail + SidebarTrigger in header (TopBar removed)
  - D-02 TopBar dropped; green status dot relocated to SidebarFooter (static semantics)
  - D-03 /library transitional route kept (Library.tsx untouched); absent from NAV_ITEMS
  - D-04 layout-route <Route path="/" element={<AppShell/>}> with relative child paths + <Outlet/>
  - D-05 useLocation prefix-match active state; navigate(to) not asChild+anchor
  - D-06 Captions glyph text-sidebar-primary + uppercase TREZARR pill in SidebarHeader
metrics:
  duration: "~2.5 min"
  completed: "2026-06-03"
  tasks_completed: 3
  files_created: 4
  files_modified: 2
---

# Phase 12 Plan 01: App Shell + Route Restructure Summary

**One-liner:** shadcn SidebarProvider+AppSidebar layout-route shell with six-item nav, left 2px purple accent bar via className, and react-router layout-route splitting /library into /series+/movies; / redirects to /series.

## What Was Built

Replaced the legacy `AppShell` (48px TopBar + fixed 192px flat nav, children-prop) with a shadcn `SidebarProvider` + hand-written `AppSidebar` + `<Outlet/>` layout, and restructured the react-router route table.

**Task 1 — Three stub pages (f0e22a3):**
- `Series.tsx`: zero-import heading placeholder (`text-xl font-semibold`)
- `Movies.tsx`: identical shape with Movies heading
- `SeriesDetail.tsx`: reads `:seriesId` via `useParams`, echoes as JSX text node (T-12-01 XSS mitigation: React auto-escape, no `dangerouslySetInnerHTML`)

**Task 2 — hand-written `app-sidebar.tsx` (6317bec):**
- `AppSidebar` named export composing vendor sidebar primitives
- NAV-01 accent bar: `className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"` on every `SidebarMenuButton` (vendor provides filled-bg only at sidebar.tsx:523)
- NAV-02: exactly six items in locked order (Series/Movies/Queue/History/Bible/Settings); `/library` absent from `NAV_ITEMS`
- D-05: `useLocation` prefix-match; `onClick navigate(to)`, `asChild` absent
- D-06: `Captions` glyph `text-sidebar-primary` + TREZARR pill hidden when collapsed
- D-02: green dot `bg-[#22c55e]` verbatim from legacy AppShell, static semantics, in SidebarFooter

**Task 3 — AppShell.tsx replaced + App.tsx rewired (bfd247f):**
- `AppShell` is now a no-prop layout host: `SidebarProvider > AppSidebar + main(Outlet)`
- `main` uses `bg-background p-6` (purple-tinted root per Wiring Invariant; was `bg-bg-base px-8 py-6`)
- `App.tsx`: layout-route pattern; `<Route path="/" element={<AppShell/>}>` with relative child paths; `Navigate to="/series"` (hardcoded literal, T-12-02 no open redirect); all eleven routes present; Library.tsx untouched

## Build Verification

```
cd frontend && npm run build
→ tsc -b (strict, noUnusedLocals, noUnusedParameters): CLEAN
→ vite build: 1740 modules, exit 0
→ trezarr/web/static/: index.html + assets/ POPULATED
```

Build: **GREEN**

## Deviations from Plan

None — plan executed exactly as written. All six decisions (D-01 through D-06) implemented per spec. Vendor file never edited. No new dependencies. No backend changes. `index.html class="dark"` and `vite.config.ts` (no base) unchanged.

## Known Stubs

The following stub pages are intentional and documented in the plan:

| Stub | File | Reason |
|------|------|--------|
| Series heading placeholder | `frontend/src/pages/Series.tsx` | Real content (table, season accordions) deferred to Phase 14 |
| Movies heading placeholder | `frontend/src/pages/Movies.tsx` | Real content deferred to Phase 14 |
| SeriesDetail heading + param echo | `frontend/src/pages/SeriesDetail.tsx` | Real content (episode table) deferred to Phase 14 |

These stubs satisfy NAV-02 (routes exist and render without errors) and are explicitly planned as Phase 14 work.

## Threat Flags

No new threat surface beyond what was modeled in the plan:

| Threat | File | Disposition |
|--------|------|-------------|
| T-12-01 reflected-XSS on :seriesId | SeriesDetail.tsx | Mitigated: JSX text node only, no dangerouslySetInnerHTML |
| T-12-02 open redirect | App.tsx Navigate | Mitigated: hardcoded literal `/series`, not user-controlled |
| T-12-03 sidebar_state cookie | vendor sidebar.tsx | Accepted: stores only true/false UI preference, no PII |

## Self-Check

### Created files exist:
- `frontend/src/pages/Series.tsx` — FOUND
- `frontend/src/pages/Movies.tsx` — FOUND
- `frontend/src/pages/SeriesDetail.tsx` — FOUND
- `frontend/src/components/app-sidebar.tsx` — FOUND
- `frontend/src/components/AppShell.tsx` — MODIFIED (FOUND)
- `frontend/src/App.tsx` — MODIFIED (FOUND)

### Commits exist:
- f0e22a3: feat(12-01): add three stub pages — FOUND
- 6317bec: feat(12-01): add hand-written AppSidebar — FOUND
- bfd247f: feat(12-01): replace AppShell (Outlet host) and rewire App.tsx — FOUND

## Self-Check: PASSED
