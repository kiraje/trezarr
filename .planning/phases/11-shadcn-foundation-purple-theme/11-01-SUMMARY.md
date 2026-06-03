---
phase: 11-shadcn-foundation-purple-theme
plan: "01"
subsystem: frontend
tags: [shadcn, tailwind, vite, typescript, alias, foundation]
dependency_graph:
  requires: []
  provides: [shadcn-foundation, cn-utility, path-alias, components-json]
  affects: [frontend/vite.config.ts, frontend/tsconfig.json, frontend/components.json, frontend/src/lib/utils.ts, frontend/tailwind.config.js, frontend/src/index.css]
tech_stack:
  added:
    - class-variance-authority@0.7.1
    - clsx@2.1.1
    - tailwind-merge@3.6.0
    - tailwindcss-animate@1.0.7
    - react-aria-components@1.18.0
    - sonner@2.0.7
    - "@types/node (dev)"
  patterns:
    - legacy-peer-deps=true in .npmrc before any npm/npx (D-07)
    - "@/ alias in both vite.config.ts resolve.alias AND tsconfig.json paths (D-08)"
    - shadcn@2.10.0 init pinned (never @latest — Pitfall 2)
    - cn() utility via clsx + tailwind-merge
key_files:
  created:
    - frontend/.npmrc
    - frontend/components.json
    - frontend/src/lib/utils.ts
    - frontend/src/lib/ (directory)
  modified:
    - frontend/package.json (6 runtime deps + @types/node)
    - frontend/package-lock.json
    - frontend/vite.config.ts (resolve.alias + @types/node import)
    - frontend/tsconfig.json (baseUrl + paths)
    - frontend/src/index.css (shadcn init wrote OKLCH :root block — replaced in Plan 02)
    - frontend/tailwind.config.js (shadcn init wrote CSS-var token map — replaced in Plan 02)
decisions:
  - "D-06: shadcn init pinned to 2.10.0 (never @latest); shadcn@latest (4.x) emits Tailwind v4 OKLCH config that breaks the v3 PostCSS pipeline"
  - "D-07: .npmrc legacy-peer-deps=true created as Step 1 before any npm/npx call; --force is not a safe substitute"
  - "D-08: @/ alias wired in both vite.config.ts (resolve.alias) AND tsconfig.json (paths); base field NOT set; outDir/emptyOutDir preserved"
  - "shadcn@2.10.0 init interactive prompt handled via --force + Enter key (selects New York, the default); --defaults flag errors on this project"
metrics:
  duration: "3 minutes"
  completed: "2026-06-03"
  tasks_completed: 2
  files_changed: 10
requirements_covered:
  - UI-01
---

# Phase 11 Plan 01: shadcn Foundation — .npmrc, Deps, @/ Alias, init Summary

**One-liner:** shadcn@2.10.0 foundation installed — 7 npm packages, @/ alias in both Vite + tsc, cn() utility, components.json; pre-theme build green.

## What Was Built

Plan 01 establishes the shadcn/ui prerequisite layer on the existing Tailwind v3.4 / React 19 / Vite 7 SPA. It:

1. Creates `frontend/.npmrc` with `legacy-peer-deps=true` (prevents ERESOLVE from cmdk/react-day-picker React 19 peer dep conflicts)
2. Installs 6 runtime deps (class-variance-authority, clsx, tailwind-merge, tailwindcss-animate, react-aria-components, sonner) and 1 dev dep (@types/node)
3. Wires the `@/` path alias in both `vite.config.ts` (resolve.alias) and `tsconfig.json` (baseUrl + paths) — both in one commit per D-08/Pitfall 6
4. Runs `npx shadcn@2.10.0 init --force` to produce `components.json` (new-york, zinc, cssVariables) and `src/lib/utils.ts` (cn() utility)
5. Confirms `npm run build` exits 0 — pre-theme baseline is green

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create .npmrc, install deps, wire @/ alias | 2bdc022 | .npmrc, package.json, vite.config.ts, tsconfig.json, package-lock.json |
| 2 | Run shadcn@2.10.0 init; verify pre-theme build green | acf20c8 | components.json, src/lib/utils.ts, tailwind.config.js, src/index.css |

## Deviations from Plan

### Handled Automatically

**1. [Rule 3 - Blocking] shadcn@2.10.0 init is interactive — cannot pass style via flag**
- **Found during:** Task 2
- **Issue:** `npx shadcn@2.10.0 init` has no `--style` flag; `--defaults` errors with "Validation failed: tailwind Required"; stdin piping with arrow-key simulation selected "Default" (wrong style)
- **Fix:** Created `components.json` and `src/lib/utils.ts` manually with the exact content from PATTERNS.md first, then ran `npx shadcn@2.10.0 init --force` with an Enter keystroke (auto-selects "New York (Recommended)" as the first/highlighted option). The CLI confirmed: "New York (Recommended)" selected, wrote components.json, updated tailwind.config.js + index.css, skipped utils.ts (file identical).
- **Files modified:** frontend/components.json, frontend/src/lib/utils.ts (pre-created manually)
- **Commit:** acf20c8

**2. [Note] shadcn init wrote OKLCH values to index.css and modified tailwind.config.js**
- These are shadcn@2.10.0 CLI outputs. The init generates OKLCH-format variables and a CSS-variable token map. Both files will be replaced wholesale in Plan 02 (the plan explicitly states this). Not treated as final output.

## Verification Evidence

```
1. grep -c "legacy-peer-deps=true" .npmrc  → 2 (comment + value lines)
2. All 6 runtime deps + @types/node in package.json  → PASS
3. vite.config.ts: path.resolve(__dirname, "./src")  → line 13
4. tsconfig.json: "@/*": ["./src/*"]  → line 21
5. components.json: style=new-york, baseColor=zinc, cssVariables=true  → PASS
6. src/lib/utils.ts: twMerge + clsx cn() function  → PASS
7. npm run build  → exits 0 (tsc -b + vite build, 1.07s, 312KB JS bundle)
```

## Known Stubs

None. This plan installs prerequisites only — no UI stubs introduced.

## Threat Flags

No new security surface introduced. Package installs completed from the RESEARCH.md Package Legitimacy Audit (all packages VERIFIED 2026-06-03 against npm registry).

## Self-Check: PASSED

- frontend/.npmrc: EXISTS
- frontend/components.json: EXISTS
- frontend/src/lib/utils.ts: EXISTS
- frontend/vite.config.ts: contains path.resolve
- frontend/tsconfig.json: contains @/*
- Task 1 commit 2bdc022: EXISTS
- Task 2 commit acf20c8: EXISTS
- npm run build: exits 0
