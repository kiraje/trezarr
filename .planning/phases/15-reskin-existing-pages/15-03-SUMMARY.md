---
phase: 15
plan: "03"
subsystem: frontend
tags: [reskin, shadcn, sonner, tokens, history, retry-button]
dependency_graph:
  requires: [15-02]
  provides: [reskinned History page, Sonner migration step 1]
  affects: [frontend/src/pages/History.tsx, frontend/src/components/RetryButton.tsx]
tech_stack:
  added: []
  patterns:
    - sonner toast() API replacing local Toast component (first call-site)
    - Button primitive variant=ghost size=sm for inline action buttons
    - hasLoaded gate for empty state display
key_files:
  modified:
    - frontend/src/pages/History.tsx
    - frontend/src/components/RetryButton.tsx
decisions:
  - "Inlined ToastPayload interface in RetryButton rather than importing from Toast.tsx (D-05 constraint: zero Toast/ToastState imports in reskinned files)"
  - "History.tsx owns empty-state render: gates HistoryTable with jobs.length===0 && hasLoaded && !unreachable check"
metrics:
  duration: "~2 min"
  completed: "2026-06-03"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 15 Plan 03: History + RetryButton Reskin + Sonner Migration #1 Summary

History.tsx and RetryButton.tsx reskinned onto shadcn CSS-variable tokens. Sonner toast migration begins here — History.tsx is the first call-site to drop the legacy Toast.tsx component in favor of `toast.success()` / `toast.error()` from sonner.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Reskin RetryButton.tsx — Button primitive with text-primary | 8866bd9 | frontend/src/components/RetryButton.tsx |
| 2 | Reskin History.tsx — heading, banner, empty state, Sonner migration | 3da4f42 | frontend/src/pages/History.tsx |

## Changes by File

### frontend/src/components/RetryButton.tsx

- Replaced raw `<button>` in idle state with `<Button variant="ghost" size="sm" className="text-primary">` — keeps RotateCw icon and aria-label unchanged
- Replaced confirming-state raw buttons with `<Button variant="ghost" size="sm">` + `text-primary` / `text-muted-foreground`
- Replaced pending-state hex `text-[#6b7280]` with `text-muted-foreground`
- Removed `import type { ToastState } from "./Toast"` — inlined local `ToastPayload` interface (`{ message: string; variant: "success" | "error" }`)
- Added `import { Button } from "./ui/button"`
- Removed all `focus:outline-[#...]`, `hover:text-[#...]`, `text-[#e2e6f0]`, `text-[#6b7280]` class strings

### frontend/src/pages/History.tsx

**Sonner migration (D-03 step 1):**
- Removed: `import Toast from "../components/Toast"`, `import type { ToastState } from "../components/Toast"`
- Added: `import { toast } from "sonner"`
- Removed: `const [toast, setToast] = useState<ToastState | null>(null)` declaration
- Updated `onToast` callback: `setToast({ ...t, id: Date.now() })` → `toast.success(t.message)` or `toast.error(t.message)` based on `t.variant`
- Removed: `<Toast toast={toast} onDismiss={() => setToast(null)} />` from JSX

**Token reskin:**
- Heading: `text-lg font-semibold text-[#e2e6f0]` → `text-xl font-semibold text-foreground`
- Count span: `text-xs text-[#6b7280]` → `text-xs text-muted-foreground`
- UnreachableBanner: removed `style={{ backgroundColor: "#451a03", color: "#fbbf24" }}` — replaced with `className="... bg-amber-900/30 border border-amber-800 text-amber-400"`

**Empty state:**
- Added `hasLoaded` boolean state (initial `false`), set to `true` after first successful `getJobs()` call
- When `jobs.length === 0 && hasLoaded && !unreachable`: renders `<div className="py-12 text-center"><p className="text-sm text-muted-foreground">No job history yet.</p></div>`
- Otherwise renders `<HistoryTable>` as before

## Verification

```
cd frontend && npm run build → EXIT 0 (tsc -b strict + vite build)
grep bg-[# History.tsx RetryButton.tsx → 0 matches
grep text-[# History.tsx RetryButton.tsx → 0 matches
grep Toast|ToastState History.tsx → 0 import matches (onToast prop reference only)
grep sonner History.tsx → import { toast } from "sonner" ✓
```

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] Inlined ToastPayload in RetryButton**
- **Found during:** Task 1
- **Issue:** D-05 requires zero `Toast/ToastState` imports in RestyButton.tsx after this plan; but the `onToast` prop type `Omit<ToastState, "id">` would still require the import.
- **Fix:** Defined a local `ToastPayload` interface (`{ message: string; variant: "success" | "error" }`) in RetryButton.tsx, structurally identical to `Omit<ToastState, "id">`. TypeScript structural typing ensures `JobTable.tsx`'s call sites remain compatible.
- **Files modified:** frontend/src/components/RetryButton.tsx
- **Commit:** 8866bd9

No other deviations.

## Known Stubs

None. Both files are fully wired: Sonner toast fires on actual retry success/failure; empty state gates on real `hasLoaded` + `jobs.length` checks.

## Threat Flags

None. No new network endpoints, auth paths, or file access patterns introduced. Threat register items T-15-03-01 and T-15-03-SC remain accepted as documented in the plan.

## Self-Check: PASSED

- [x] frontend/src/pages/History.tsx exists and was modified
- [x] frontend/src/components/RetryButton.tsx exists and was modified
- [x] Commit 8866bd9 exists (Task 1)
- [x] Commit 3da4f42 exists (Task 2)
- [x] Build exits 0
- [x] Zero legacy hex in both files
- [x] Zero Toast/ToastState imports in History.tsx
- [x] toast.success confirmed in History.tsx
