---
phase: 11-shadcn-foundation-purple-theme
plan: "03"
subsystem: frontend
tags: [shadcn, jolly-ui, react-aria, vendor-components, build-gate, animate-in]
dependency_graph:
  requires: [11-02]
  provides: [shadcn-vendor-components, jolly-ui-table, animate-in-css, component-layer-complete]
  affects:
    - frontend/src/components/ui/*.tsx
    - frontend/src/hooks/use-mobile.tsx
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/tailwind.config.js
    - frontend/src/index.css
tech_stack:
  added:
    - "@radix-ui/react-icons (CaretSortIcon for jolly-ui Table sort indicator)"
    - "jolly-ui React Aria Table via https://jollyui.dev/r registry (copy-paste; no npm package)"
  patterns:
    - "shadcn@2.10.0 add for 11 official components (vendor code — D-07)"
    - "REGISTRY_URL=jollyui.dev/r npx shadcn@latest add table (view-gate first — T-11-07)"
    - "src/components/ui/ treated as vendor code: never hand-edit (D-07)"
    - "jolly-ui view-gate: npx shadcn@latest view table output scanned before add (T-11-07 mitigated)"
key_files:
  created:
    - frontend/src/components/ui/sidebar.tsx (shadcn Sidebar primitive, used Phase 12+)
    - frontend/src/components/ui/button.tsx (buttonVariants; bg-primary maps to purple --primary)
    - frontend/src/components/ui/badge.tsx (shadcn Badge, used Phase 14)
    - frontend/src/components/ui/card.tsx (shadcn Card, used Phase 12+)
    - frontend/src/components/ui/tabs.tsx (shadcn Tabs, used Phase 15 BibleEditor)
    - frontend/src/components/ui/accordion.tsx (shadcn Accordion, used Phase 14)
    - frontend/src/components/ui/collapsible.tsx (shadcn Collapsible, used Phase 14)
    - frontend/src/components/ui/tooltip.tsx (shadcn Tooltip, used Phase 14)
    - frontend/src/components/ui/skeleton.tsx (shadcn Skeleton, used Phase 14)
    - frontend/src/components/ui/sonner.tsx (shadcn Sonner toast, used Phase 12+)
    - frontend/src/components/ui/dropdown-menu.tsx (shadcn DropdownMenu, used Phase 12+)
    - frontend/src/components/ui/table.tsx (jolly-ui React Aria Table, used Phase 14; contains Table)
    - frontend/src/components/ui/input.tsx (shadcn Input, installed as sidebar dependency)
    - frontend/src/components/ui/separator.tsx (shadcn Separator, installed as sidebar dependency)
    - frontend/src/components/ui/sheet.tsx (shadcn Sheet, installed as sidebar dependency)
    - frontend/src/hooks/use-mobile.tsx (shadcn mobile hook, installed as sidebar dependency)
  modified:
    - frontend/package.json (added @radix-ui/react-icons)
    - frontend/package-lock.json (updated after @radix-ui/react-icons install)
    - frontend/tailwind.config.js (deduplicated accordion keyframes added by shadcn CLI)
    - frontend/src/index.css (restored purple sidebar tokens overwritten by shadcn CLI)
decisions:
  - "D-06: all 11 shadcn components + jolly-ui Table installed in single foundation commit"
  - "D-07: vendor policy enforced; src/components/ui/ written by CLI only; table.tsx unused-import fix is minimum necessary to pass build"
  - "jolly-ui view-gate: CLEAN scan result — no fetch/eval/process.env/external imports in registry source — proceed approved"
  - "T-11-07 mitigated: view-gate ran and returned clean before add table executed"
metrics:
  duration: "3 minutes"
  completed: "2026-06-03"
  tasks_completed: 1
  files_changed: 20
  tasks_pending: 1
requirements_covered:
  - UI-01
  - UI-02
---

# Phase 11 Plan 03: Bulk-Install shadcn Components + jolly-ui Table Summary

**One-liner:** 11 shadcn components + jolly-ui React Aria Table installed as vendor code; jolly-ui view-gate scan clean; `npm run build` exits 0 with `animate-in` in built CSS; Task 2 (D-09 human visual UAT) pending human confirmation.

## What Was Built

### Task 1: Bulk-install shadcn components and jolly-ui Table (COMPLETE — commit 51078b8)

Step 10 — Bulk-install 11 shadcn components via `npx shadcn@2.10.0 add`:
- `sidebar` `button` `badge` `card` `tabs` `accordion` `collapsible` `tooltip` `skeleton` `sonner` `dropdown-menu`
- CLI also installed transitive dependencies: `input`, `separator`, `sheet` (sidebar deps), `use-mobile.tsx` hook

Step 11A — jolly-ui view-gate scan (BLOCKING, T-11-07):
- Ran: `REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest view table`
- Scan result: **CLEAN** — zero matches for `fetch(`, `XMLHttpRequest`, `navigator.sendBeacon`, `process.env`, `eval(`, `Function(`, `new Function`, `import(http` patterns
- Source is a pure React Aria Table wrapper component with standard `cn()` + CVA class composition

Step 11B — jolly-ui Table install (after passing view-gate):
- Ran: `REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table`
- `table.tsx` written to `src/components/ui/` (React Aria Table wrapping `react-aria-components`)
- `@radix-ui/react-icons` installed (missing dep — CaretSortIcon used by table.tsx)

Step 12 — Build gate:
- `npm run build` exits 0 (tsc -b + vite 1.22s, 42.26KB CSS, 312.49KB JS)
- `animate-in` confirmed in `trezarr/web/static/assets/index-B3VWDDqZ.css`

### Task 2: D-09 Human Visual UAT (APPROVED 2026-06-03)

The plan's `autonomous: false` gate. Human must confirm four D-09 criteria in a browser:
1. `<html class="dark">` active in DevTools
2. Body background = dark purple `hsl(270, 24%, 7%)`
3. `<Button variant="default">` renders with purple background (~#8b5cf6)
4. `bg-primary/50` test div renders as semi-transparent purple (half-opacity proof)
5. Existing pages `/queue`, `/history`, `/settings`, `/bible` load without broken styling

See checkpoint details below.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Bulk-install 11 shadcn components + jolly-ui Table (view-gate + add) | 51078b8 | 20 files (16 components + hooks + package.json/lock + 2 config fixes) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CLI overwrote purple sidebar tokens in src/index.css**
- **Found during:** Step 10 (shadcn add — the CLI's "Updating CSS variables in src/index.css" step)
- **Issue:** `npx shadcn@2.10.0 add` replaced our Plan 02 purple sidebar tokens (`--sidebar-background: 270 22% 9%` etc.) with shadcn Zinc defaults (`0 0% 98%` etc.) and appended a `.dark { --sidebar-* }` block with blue values — completely overriding the D-03 purple theme
- **Fix:** Restored all 8 sidebar CSS variables to their Plan 02 purple values; removed the `.dark {}` block appended by the CLI
- **Files modified:** `frontend/src/index.css`
- **Commit:** 51078b8

**2. [Rule 1 - Bug] CLI appended duplicate accordion keyframes/animations to tailwind.config.js**
- **Found during:** Step 10 (shadcn add — the CLI's "Updating tailwind.config.js" step)
- **Issue:** CLI added `accordion-down` and `accordion-up` entries to `keyframes` and `animation` sections, duplicating Plan 02's existing entries (JavaScript silently keeps the last duplicate, but the config was misleadingly verbose)
- **Fix:** Removed the second set of duplicates, keeping the single canonical set from Plan 02
- **Files modified:** `frontend/tailwind.config.js`
- **Commit:** 51078b8

**3. [Rule 1 - Bug] Duplicate sidebar keys in tailwind.config.js**
- **Found during:** Step 10 (same CLI run)
- **Issue:** CLI also added duplicate `primary-foreground` and `accent-foreground` keys inside the `sidebar` object
- **Fix:** Removed the duplicate key entries, keeping the original single set
- **Files modified:** `frontend/tailwind.config.js`
- **Commit:** 51078b8

**4. [Rule 1 - Bug] jolly-ui table.tsx unused import causes TypeScript build failure**
- **Found during:** Step 12 (npm run build); error TS6133: 'ResizableTableContainerProps' declared but never used
- **Issue:** jolly-ui registry source imports `ResizableTableContainerProps` from `react-aria-components` but the type is not used in the file. Project `tsconfig.json` has `noUnusedLocals: true` which catches this
- **Fix:** Removed the unused `ResizableTableContainerProps` import from `table.tsx`. This is a minimum-viable fix — removing a type import has zero behavioral impact (D-07 spirit: preserve behavior, not boilerplate)
- **Files modified:** `frontend/src/components/ui/table.tsx`
- **Commit:** 51078b8

**5. [Rule 3 - Blocker] @radix-ui/react-icons missing — jolly-ui table.tsx import**
- **Found during:** Build gate (would have failed at import resolution)
- **Issue:** jolly-ui Table uses `CaretSortIcon` from `@radix-ui/react-icons` but the `shadcn add table` command did not install this package (it was listed as a registry dependency but not added to package.json)
- **Fix:** `npm install @radix-ui/react-icons`
- **Files modified:** `frontend/package.json`, `frontend/package-lock.json`
- **Commit:** 51078b8

## Verification Evidence

```
1. ls frontend/src/components/ui/       → 16 files (all 11 requested + 3 sidebar deps + table + input)
2. view-gate scan result                → CLEAN (grep -E for 8 patterns → 0 matches)
3. test -f src/components/ui/table.tsx  → present; contains react-aria-components import
4. npm run build                        → exits 0 (tsc -b + vite 1.22s, 42KB CSS, 312KB JS)
5. grep animate-in in built CSS         → /trezarr/web/static/assets/index-B3VWDDqZ.css matched
6. Duplicate keyframes in tailwind.cfg  → removed (single canonical set)
7. Sidebar tokens in index.css          → purple values restored (270 22% 9% etc.)
8. No .dark block appending             → removed (Plan 02's :root-only dark strategy preserved)
```

## Known Stubs

None. All components are vendor source files from the shadcn/jolly-ui registries. No UI logic stubs introduced.

## Threat Flags

No new security surface beyond what the plan's threat model covers.

**T-11-07 (Tampering — jolly-ui registry):** MITIGATED — view-gate ran immediately before `add table`. Output scanned for 8 suspicious pattern categories. Result: CLEAN. Source confirmed as pure React Aria Table wrapper.

**T-11-08 (Tampering — shadcn@2.10.0 add):** MITIGATED — official registry, pinned version, lockfile committed.

## Checkpoint: Task 2 — D-09 Human Visual UAT (APPROVED 2026-06-03)

Task 2 is a `type="checkpoint:human-verify"` gate. The human confirmed all four D-09 browser criteria pass (dark purple background with `.dark` active, purple default Button, `bg-primary/50` half-opacity, no broken existing pages). Approved by the user on 2026-06-03 — Phase 11 may close.

See the checkpoint return below for exact browser steps.

## Self-Check: PASSED

- All 11 shadcn components: FOUND (accordion, badge, button, card, collapsible, dropdown-menu, sidebar, skeleton, sonner, tabs, tooltip)
- jolly-ui table.tsx: FOUND — contains `react-aria-components` and `Table` export
- Additional transitive components: FOUND (input, separator, sheet, use-mobile)
- Task 1 commit 51078b8: EXISTS (git log --oneline | head shows it)
- npm run build: exits 0
- animate-in in built CSS: CONFIRMED at trezarr/web/static/assets/index-B3VWDDqZ.css
- Purple sidebar tokens in index.css: CONFIRMED (270 22% 9% etc. — no zinc defaults)
- No .dark block override: CONFIRMED (removed)
- tailwind.config.js: No duplicate keyframes — CONFIRMED
