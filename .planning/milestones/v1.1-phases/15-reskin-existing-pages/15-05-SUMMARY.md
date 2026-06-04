---
phase: 15-reskin-existing-pages
plan: "05"
subsystem: frontend
tags: [reskin, shadcn, tokens, bible-list]
dependency_graph:
  requires: []
  provides: [BibleList on shadcn tokens]
  affects: [frontend/src/pages/BibleList.tsx]
tech_stack:
  added: []
  patterns: [shadcn Skeleton, CSS-var tokens, hover:bg-accent/50 rows]
key_files:
  created: []
  modified:
    - frontend/src/pages/BibleList.tsx
decisions:
  - "Kept style={{ width: '%' }} for column widths — structural, not color hex; within plan scope"
metrics:
  duration: "~5 minutes"
  completed: "2026-06-03T19:53:51Z"
  tasks_completed: 1
  files_modified: 1
---

# Phase 15 Plan 05: BibleList Reskin Summary

**One-liner:** BibleList reskinned to shadcn tokens — Skeleton loading rows, amber-token error banner, hover:bg-accent/50 rows, zero legacy hex.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Reskin BibleList.tsx — full token swap, Skeleton loading, no stripes | 48d04da |

## What Was Built

BibleList.tsx was reskinned in-place. All token substitutions follow the 15-UI-SPEC.md authoritative map:

- **Heading:** `text-lg font-semibold text-text-primary` → `text-xl font-semibold text-foreground`
- **UnreachableBanner:** Removed `style={{ backgroundColor: "#451a03", color: "#fbbf24" }}`; replaced with `className="... bg-amber-900/30 border border-amber-800 text-amber-400"`
- **Loading state:** Hand-rolled `<div className="h-4 bg-bg-surface rounded w-48" />` shims replaced with `<Skeleton className="h-4 w-48" />` (and `w-8`, `w-16` variants per column)
- **Table headers (both loading + data tables):** `border-[#2d3148]` → `border-border`; `text-text-muted` → `text-muted-foreground`
- **Loading rows:** `border-[#2d3148]` → `border-border`
- **Data rows:** Zebra stripe (`idx % 2 === 1 ? "bg-bg-stripe" : ""`) removed entirely; `hover:bg-[#22263a]` → `hover:bg-accent/50`; `border-[#2d3148]` → `border-border`
- **Cell text:** `text-text-primary` → `text-foreground`; `text-text-muted` → `text-muted-foreground`; inner register `<span className="text-text-muted">` → `text-muted-foreground`
- **Empty state:** `text-text-primary` → `text-foreground`; `text-text-muted` → `text-muted-foreground`
- **Skeleton import added:** `import { Skeleton } from "../components/ui/skeleton"`

All data fetching, navigation, and state logic unchanged (RSK-02 / behavior invariant).

## Verification

```
cd frontend && npm run build
```

Exit 0. tsc strict clean. Vite build clean.

```
grep -En "#[0-9a-fA-F]{3,6}" frontend/src/pages/BibleList.tsx
```

Zero matches — no hex values remain.

## Deviations from Plan

None — plan executed exactly as written.

The `style={{ width: "15%" }}` and `style={{ width: "20%" }}` occurrences on table column headers are structural percentage widths (not hex colors) and were present in the original file. The plan's done criteria target hex strings (`bg-[#`, `text-[#`, `style={{ with hex values`); these width-only styles are out of scope and preserved unchanged.

## Known Stubs

None — BibleList renders live data from `getSeriesList()`. No placeholder content.

## Threat Flags

No new security-relevant surface introduced. All changes are pure className substitution. Series name/kind rendered as JSX text nodes (React auto-escapes, T-15-05-01 accepted).

## Self-Check: PASSED

- [x] `frontend/src/pages/BibleList.tsx` modified and committed at 48d04da
- [x] `git log --oneline` shows `48d04da feat(15-05): reskin BibleList onto shadcn tokens and Skeleton`
- [x] `npm run build` exits 0
- [x] Zero hex values in BibleList.tsx
