---
phase: 15
plan: "02"
subsystem: frontend
tags: [reskin, shadcn, tokens, queue, job-table]
dependency_graph:
  requires: [15-01]
  provides: [reskinned-JobTable, reskinned-Queue]
  affects: [frontend/src/components/JobTable.tsx, frontend/src/pages/Queue.tsx]
tech_stack:
  added: []
  patterns: [shadcn-Button-ghost-icon, skeleton-loading-gate, amber-className-banner]
key_files:
  modified:
    - frontend/src/components/JobTable.tsx
    - frontend/src/pages/Queue.tsx
decisions:
  - "Keep plain HTML table (not jolly-ui Table) — matches Series.tsx D-01 precedent"
  - "hasLoaded boolean gates skeleton to first load only; re-polls are silent"
  - "QueueTable internal empty state retained; Queue page now has its own empty/loading states"
metrics:
  duration: "2m"
  completed: "2026-06-03"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 15 Plan 02: Queue + JobTable Reskin Summary

**One-liner:** JobTable reskinned to shadcn tokens (text-muted-foreground headers, hover:bg-accent/50 rows, Button ghost icon for logs); Queue page upgraded with text-xl heading, className-only amber banner, Skeleton-gated first load, and muted empty state.

---

## Tasks

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Reskin JobTable.tsx — token swap on table, headers, rows, log icon button | 015a162 | frontend/src/components/JobTable.tsx |
| 2 | Reskin Queue.tsx — heading, UnreachableBanner, loading/empty states | f58d13a | frontend/src/pages/Queue.tsx |

---

## Verification

- `cd frontend && npm run build` — exit 0 after Task 1 and Task 2
- `grep -En "bg-\[#|text-\[#|bg-bg-|text-text-"` on both files — zero matches
- `grep -En "style=\{\{.*#"` on both files — zero matches (only `style={{ width: ... }}` percentage values remain in column header widths, which are not hex)

---

## What Changed

### JobTable.tsx
- `text-[#6b7280]` → `text-muted-foreground` on all table headers, secondary text cells (timestamps, reason), lastUpdated paragraph, EmptyState text
- `text-[#e2e6f0]` → `text-foreground` on all primary data cells (series, episode, file path)
- `border-[#2d3148]` → `border-border` on header row and data rows
- `hover:bg-[#22263a]` → `hover:bg-accent/50` on data rows
- Zebra stripe `style={{ backgroundColor: idx % 2 === 1 ? "#1e2130" : undefined }}` removed entirely
- `idx` parameter removed from `.map()` callback (no longer needed — no unused vars)
- Log icon raw `<button>` → `<Button variant="ghost" size="icon">` in both QueueTable and HistoryTable
- `focus:outline-[#3b82f6]` removed (Button handles focus ring via CSS vars)
- `import { Button } from "./ui/button"` added

### Queue.tsx
- `text-lg font-semibold text-[#e2e6f0]` → `text-xl font-semibold text-foreground` on h1
- `text-xs text-[#6b7280]` → `text-xs text-muted-foreground` on count span
- `UnreachableBanner`: `style={{ backgroundColor: "#451a03", color: "#fbbf24" }}` replaced with `className="... bg-amber-900/30 border border-amber-800 text-amber-400"`
- `hasLoaded` boolean state added (initial: false); set to `true` after first successful `getQueue()` response
- Loading skeleton: shown when `jobs.length === 0 && !hasLoaded && !unreachable`
- Empty state: shown when `jobs.length === 0 && hasLoaded && !unreachable`
- Otherwise renders `<QueueTable>` as before
- `import { Skeleton } from "../components/ui/skeleton"` added

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes. All rendered data is JSX text (React auto-escapes). No new threat surface.

---

## Known Stubs

None — Queue and JobTable render live API data from `getQueue()`.

---

## Self-Check: PASSED

- frontend/src/components/JobTable.tsx — FOUND
- frontend/src/pages/Queue.tsx — FOUND
- Commit 015a162 (Task 1: JobTable reskin) — FOUND
- Commit f58d13a (Task 2: Queue.tsx reskin) — FOUND
