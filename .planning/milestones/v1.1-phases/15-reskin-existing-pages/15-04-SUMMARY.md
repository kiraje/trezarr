---
phase: 15
plan: "04"
subsystem: frontend
tags: [reskin, shadcn, settings, sonner, skeleton]
dependency_graph:
  requires: [15-03]
  provides: [Settings.tsx on shadcn primitives, MaskedSecretInput shadcn, ConnectionTestButton shadcn, Sonner migration step 2]
  affects: [frontend/src/pages/Settings.tsx, frontend/src/components/MaskedSecretInput.tsx, frontend/src/components/ConnectionTestButton.tsx]
tech_stack:
  added: []
  patterns: [Card/CardContent sections, shadcn Input in form fields, Button variant=default for saves, Button variant=ghost size=icon for eye-toggle, Button variant=outline size=sm for test, Skeleton loading gate, toast.success/toast.error from sonner]
key_files:
  created: []
  modified:
    - frontend/src/components/MaskedSecretInput.tsx
    - frontend/src/components/ConnectionTestButton.tsx
    - frontend/src/pages/Settings.tsx
decisions:
  - "SectionHeading uses plain h2 with text-base font-semibold text-card-foreground (not CardTitle) — CardTitle pulled from design doc but the SectionCard already wraps in Card/CardContent; CardHeader/CardTitle would add unwanted padding"
  - "saveSection promoted to useCallback — was already a function; useCallback satisfies exhaustive-deps rule and matches Phase 14 patterns"
metrics:
  duration: "2 min"
  completed: "2026-06-04"
  tasks_completed: 2
  files_modified: 3
---

# Phase 15 Plan 04: Settings + MaskedSecretInput + ConnectionTestButton Reskin + Sonner Migration #2 Summary

Settings.tsx, MaskedSecretInput, and ConnectionTestButton reskinned onto shadcn Card/Input/Button primitives with Skeleton loading, Sonner toast (D-03 step 2), and zero legacy hex in all three files.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Reskin MaskedSecretInput + ConnectionTestButton | 5226309 | MaskedSecretInput.tsx, ConnectionTestButton.tsx |
| 2 | Reskin Settings.tsx — Card, Input, Button, Skeleton, Sonner | b7cf5d6 | Settings.tsx |

## What Was Built

### Task 1: MaskedSecretInput.tsx

- Raw `<input>` element replaced with shadcn `<Input>` component
- Eye-toggle raw `<button>` replaced with `<Button variant="ghost" size="icon">` (absolute-positioned inside input container)
- Labels: `text-xs text-[#6b7280]` → `text-xs text-muted-foreground`
- Masking logic (isSet/envLocked/showTyped), all props, and "set" chip are unchanged
- Zero hex strings remain

### Task 1: ConnectionTestButton.tsx

- Raw `<button>` → `<Button variant="outline" size="sm">` from shadcn
- Success ResultChip: `style={{backgroundColor:"#14291e", color:"#4ade80"}}` → `className="bg-emerald-900/50 text-emerald-400"`
- Error ResultChip: `style={{backgroundColor:"#2d1515", color:"#f87171"}}` → `className="bg-destructive/10 text-destructive"`
- All API call logic, status state machine, error message truncation unchanged
- Zero hex strings remain

### Task 2: Settings.tsx

- **SectionCard**: `<div className="bg-bg-surface border border-[#2d3148] rounded ...">` → `<Card><CardContent className="pt-6 flex flex-col gap-4">...</CardContent></Card>`
- **SectionHeading**: `text-lg text-[#e2e6f0]` h2 → `text-base font-semibold text-card-foreground` h2
- **TextField internal input**: raw input with hand-rolled classes → shadcn `<Input>`; label `text-xs text-muted-foreground`
- **Save buttons (7)**: all raw `<button>` with `bg-accent hover:bg-[#2563eb] focus:outline-[#3b82f6]` → `<Button variant="default" className="w-full">`
- **Page heading**: `text-lg text-[#e2e6f0]` → `text-xl text-foreground`
- **UnreachableBanner**: `style={{backgroundColor:"#451a03", color:"#fbbf24"}}` → `className="bg-amber-900/30 border border-amber-800 text-amber-400"`
- **RestartBanner**: `style={{color:"#fbbf24"}}` → `className="text-amber-400"`
- **Auto-translate checkbox**: `accent-[#3b82f6]` → `accent-primary`; label `text-sm text-foreground`; helper `text-xs text-muted-foreground`
- **Path Mappings section**: `text-[#6b7280]` → `text-muted-foreground`
- **Sonner migration**: `Toast`/`ToastState` imports removed; `useState<ToastState>` + `showToast` removed; all call sites replaced with `toast.success("Settings saved.")` / `toast.error("Failed to save settings. Check the server logs.")`; `<Toast>` JSX element removed
- **Skeleton loading**: `if (settings === null && !unreachable)` gate returns 3 × `Skeleton className="h-40 w-full"` (plus heading skeleton) instead of blank page

## Verification

```
cd frontend && npm run build
✓ 1756 modules transformed.
✓ built in 1.11s (exit 0)
```

Spot-check: zero legacy hex matches in all three files.
Toast references in Settings.tsx: zero.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unused CardHeader/CardTitle imports**
- **Found during:** Task 2 build
- **Issue:** Plan spec referenced CardHeader/CardTitle imports but SectionHeading uses a plain h2 (not CardTitle). tsc strict `noUnusedLocals` caught the unused imports.
- **Fix:** Import only `Card, CardContent` from the card module. SectionHeading remains a plain h2 with semantic class names.
- **Files modified:** frontend/src/pages/Settings.tsx
- **Commit:** b7cf5d6 (inline fix before commit)

## Known Stubs

None. All form fields are wired to real state and API calls. No placeholder data.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary changes. Settings form rendering is unchanged (React value binding, no innerHTML). Sonner toast messages are hardcoded strings only.

## Self-Check: PASSED

- [x] frontend/src/pages/Settings.tsx exists
- [x] frontend/src/components/MaskedSecretInput.tsx exists
- [x] frontend/src/components/ConnectionTestButton.tsx exists
- [x] Commit 5226309 exists (Task 1)
- [x] Commit b7cf5d6 exists (Task 2)
- [x] npm run build exits 0
- [x] Zero hex in all three files
- [x] Zero Toast/ToastState/showToast references in Settings.tsx
