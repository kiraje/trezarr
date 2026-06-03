---
phase: 15-reskin-existing-pages
plan: "01"
subsystem: frontend
tags: [reskin, shadcn, badge, card, skeleton, button, tokens]
dependency_graph:
  requires: []
  provides:
    - StatusBadge on shadcn Badge with semantic color classes
    - LogViewer on bg-background/border-border/text-muted-foreground
    - JobLogs on shadcn Button/Card/Skeleton with loading/error/empty states
  affects:
    - frontend/src/pages/JobLogs.tsx
    - frontend/src/components/StatusBadge.tsx
    - frontend/src/components/LogViewer.tsx
tech_stack:
  added: []
  patterns:
    - shadcn Badge with className override for semantic status colors
    - shadcn Card/CardContent for summary strips
    - shadcn Skeleton for loading states
    - shadcn Button variant=ghost for breadcrumb and icon-only actions
    - div role=alert with bg-destructive/10 text-destructive for error states (alert.tsx not vendored)
key_files:
  created: []
  modified:
    - frontend/src/components/StatusBadge.tsx
    - frontend/src/components/LogViewer.tsx
    - frontend/src/pages/JobLogs.tsx
decisions:
  - StatusBadge status union extended with in_progress and translated per plan spec (new statuses present in live data)
  - LogViewer level colors (INFO green, ERROR red, WARNING orange) kept as hex — these are semantic log-level terminal colors, not UI theme tokens, and are absent from the legacy→shadcn token map
  - Error state uses div role=alert rather than Alert primitive — alert.tsx is not vendored in this project (UI-SPEC fallback rule applied)
  - Empty state paragraph added above LogViewer (not replacing LogViewer's own empty branch) so it shows even when LogViewer renders nothing
metrics:
  duration: "139 seconds"
  completed: "2026-06-03"
  tasks_completed: 3
  files_modified: 3
---

# Phase 15 Plan 01: JobLogs + StatusBadge + LogViewer Reskin Summary

StatusBadge, LogViewer, and JobLogs reskinned onto shadcn Badge/Card/Button/Skeleton primitives with zero legacy hex tokens remaining in any of the three files.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Reskin StatusBadge onto shadcn Badge variants | 24dedd2 | StatusBadge.tsx |
| 2 | Reskin LogViewer onto bg-background/border-border/text-muted-foreground | 8d0a980 | LogViewer.tsx |
| 3 | Reskin JobLogs heading/breadcrumb/Card/Skeleton/error/empty states | e08c16e | JobLogs.tsx |

## What Was Done

**Task 1 — StatusBadge.tsx:** Replaced the bespoke inline-style span (hex bg/text/dot per status) with shadcn `<Badge>` using the plan's specified variant/className mapping. Extended the `JobStatus` union to include `in_progress` and `translated` (present in live data per UI-SPEC). Unknown statuses get `variant="outline"` as safe default.

**Task 2 — LogViewer.tsx:** Replaced `bg-bg-base` with `bg-background border border-border rounded`; replaced `style={{color:"#6b7280"}}` on timestamp spans with `className="text-muted-foreground"`; replaced the raw `<button>` scroll-to-bottom element with `<Button variant="ghost" size="icon">` from shadcn; replaced `text-[#6b7280]` on the empty state div with `text-muted-foreground`. Level colors (LEVEL_COLORS record) were kept as hex — these are terminal-style semantic log level colors, not UI theme tokens, and are intentionally outside the Phase-15 token migration scope.

**Task 3 — JobLogs.tsx:** Applied all substitutions from the plan:
- Breadcrumb: raw button → `<Button variant="ghost" size="sm" className="text-primary">`
- Heading: `text-lg text-[#e2e6f0]` → `text-xl font-semibold text-foreground`
- Summary strip: `bg-bg-surface border-[#2d3148]` div → `<Card><CardContent>`; `text-[#6b7280]` → `text-muted-foreground`
- Loading: single "Loading…" div → three `<Skeleton>` rows (heading h-8, strip h-10, log area h-64)
- Error: `style={{backgroundColor:"#2d1515",color:"#f87171"}}` → `<div role="alert" className="bg-destructive/10 text-destructive">`
- Empty state: new `<p className="text-sm text-muted-foreground py-8 text-center">` above LogViewer

## Build Verification

| After Task | Command | Result |
|---|---|---|
| Task 1 | `cd frontend && npm run build` | EXIT 0 — tsc strict clean, vite built 477.76 kB |
| Task 2 | `cd frontend && npm run build` | EXIT 0 — tsc strict clean, vite built 477.62 kB |
| Task 3 | `cd frontend && npm run build` | EXIT 0 — tsc strict clean, vite built 478.63 kB |

Final hex grep across all three files:
```
grep -En "bg-\[#|text-\[#|bg-bg-|text-text-|style=\{\{.*#" StatusBadge.tsx LogViewer.tsx JobLogs.tsx
```
Result: 0 matches (one comment in JobLogs.tsx mentioning "bg-bg-surface" for documentation — not code)

## Deviations from Plan

### Auto-handled Design Decisions

**1. [Rule 2 - Missing] StatusBadge union extended with in_progress and translated**
- Found during: Task 1
- Issue: The plan's "queued | in_progress" and "done | translated" cases in the spec implied these status values exist in live data, but the original union only had queued/running/done/failed/quarantined
- Fix: Extended `JobStatus` to include `in_progress` and `translated` — both are valid API statuses from live data; existing call sites cast via `as JobStatus` so adding to the union is safe
- Files modified: StatusBadge.tsx

**2. [Design] LogViewer level colors kept as hex**
- Found during: Task 2
- Issue: LEVEL_COLORS record contains hex values for log levels (INFO green, ERROR red, etc.)
- Resolution: These are not UI theme tokens — they are terminal-style semantic log level indicators. They are absent from the 15-UI-SPEC.md legacy→shadcn token map. Kept intentionally.

## Known Stubs

None — all data flows are wired.

## Threat Flags

None — changes are className/primitive substitutions only. No new network endpoints, auth paths, or trust boundary changes. XSS protections (text nodes, no dangerouslySetInnerHTML) unchanged.

## Self-Check: PASSED

- [x] frontend/src/components/StatusBadge.tsx — exists, contains bg-emerald-600/80
- [x] frontend/src/components/LogViewer.tsx — exists, contains text-muted-foreground
- [x] frontend/src/pages/JobLogs.tsx — exists, contains text-xl font-semibold
- [x] Commits 24dedd2, 8d0a980, e08c16e — all present in git log
- [x] Zero hex tokens in modified files (code paths)
- [x] npm run build exits 0 after all three tasks
