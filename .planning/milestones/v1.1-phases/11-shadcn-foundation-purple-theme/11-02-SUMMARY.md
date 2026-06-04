---
phase: 11-shadcn-foundation-purple-theme
plan: "02"
subsystem: frontend
tags: [tailwind, css-variables, dark-mode, purple-theme, shadcn, index-css, index-html]
dependency_graph:
  requires: [11-01]
  provides: [purple-hsl-theme, dark-mode-active, css-var-token-map, bridge-tokens-preserved]
  affects:
    - frontend/tailwind.config.js
    - frontend/src/index.css
    - frontend/index.html
tech_stack:
  added: []
  patterns:
    - "CSS variables as bare H S% L% channel triples — hsl() wrapper only in tailwind.config.js (D-02)"
    - "darkMode:[class] in tailwind.config.js + class=dark on <html> (Pitfall 4)"
    - "Bridge tokens preserved as literal hex alongside shadcn CSS-var token map (D-05)"
    - "tailwindcss-animate in plugins for accordion/tooltip/dialog animations (Pitfall 5)"
key_files:
  created: []
  modified:
    - frontend/tailwind.config.js (wholesale replacement: darkMode, container, bridge tokens, CSS-var map, sidebar, accordion keyframes, tailwindcss-animate)
    - frontend/src/index.css (wholesale replacement: 28 HSL CSS variables as bare channel triples, purple anchor --primary:270 70% 60%)
    - frontend/index.html (surgical: class=dark on html, background-color updated to purple hsl(270,24%,7%))
decisions:
  - "D-01: --primary:270 70% 60% locked purple anchor implemented in :root"
  - "D-02: all 28 CSS variables are bare H S% L% channel triples; hsl() wrapper exclusively in tailwind.config.js; proven by build green + zero hsl() in :root declarations"
  - "D-03: --ring, --sidebar-primary, --sidebar-ring all set to 270 70% 60% tracking --primary"
  - "D-04: --background:270 24% 7% purple-tinted dark (not #0f1117 blue-black); index.html body bg updated to match"
  - "D-05: bg-base/bg-surface/bg-stripe/text-primary/text-muted preserved as literal hex; border/accent/destructive replaced wholesale with hsl(var(--x)) shadcn entries"
metrics:
  duration: "2 minutes"
  completed: "2026-06-03"
  tasks_completed: 2
  files_changed: 3
requirements_covered:
  - UI-01
  - UI-02
---

# Phase 11 Plan 02: Purple HSL Theme + Dark Mode — tailwind.config.js / index.css / index.html Summary

**One-liner:** Purple dark-mode theme established — 28 bare HSL channel-triple CSS variables with `--primary:270 70% 60%`, darkMode:["class"] wired to `class="dark"` on `<html>`, bridge tokens preserved; `npm run build` exits 0.

## What Was Built

Plan 02 installs the purple HSL dark theme across the three config files that carry the visual layer:

1. **`frontend/tailwind.config.js`** (wholesale replacement):
   - `darkMode: ["class"]` at top level — activates `.dark` selector strategy
   - `container` block (center, 2rem padding, 2xl: 1400px)
   - 5 bridge tokens preserved as literal hex (`bg-base`, `bg-surface`, `bg-stripe`, `text-primary`, `text-muted`) alongside the new shadcn CSS-var-backed entries (D-05)
   - Colliding keys `border`, `accent`, `destructive` replaced wholesale with `hsl(var(--x))` entries
   - Full shadcn CSS-variable token map: border/input/ring/background/foreground/primary/secondary/destructive/muted/accent/popover/card/sidebar
   - Sidebar block with `--sidebar-background` mapping (not `--sidebar` — correct shadcn pattern)
   - Accordion keyframes (`accordion-down`, `accordion-up` with `--radix-accordion-content-height`)
   - `plugins: [require("tailwindcss-animate")]` — registers animation utilities

2. **`frontend/src/index.css`** (wholesale replacement):
   - Replaces OKLCH variables written by shadcn init with purple HSL channel triples
   - All 28 CSS variables as bare `H S% L%` format — zero `hsl()` wrappers in `:root` (D-02)
   - `--primary: 270 70% 60%` locked purple anchor (D-01)
   - `--background: 270 24% 7%` purple-tinted dark root (D-04)
   - `--ring`, `--sidebar-primary`, `--sidebar-ring` all track `--primary` at `270 70% 60%` (D-03)
   - Dark-only design: no `.dark {}` block — `:root` IS the dark theme

3. **`frontend/index.html`** (two surgical edits):
   - `<html lang="en" class="dark">` — activates `darkMode: ["class"]` selector
   - `background-color: hsl(270, 24%, 7%)` — eliminates flash of legacy `#0f1117` blue-black before SPA hydrates (D-04)

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Replace tailwind.config.js + src/index.css with purple HSL token system | b4d62e7 | frontend/tailwind.config.js, frontend/src/index.css |
| 2 | Update index.html (class=dark + purple background) and verify green build | 6a48ee4 | frontend/index.html |

## Deviations from Plan

None — plan executed exactly as written. All three files replaced/edited per RESEARCH.md Step 7/8/9 verbatim. The OKLCH variables written by shadcn@2.10.0 init (Plan 01) were the expected state to replace; this wholesale swap was the stated purpose of Plan 02.

## Verification Evidence

```
1. grep 'darkMode.*class' tailwind.config.js       → match (["class"])
2. grep '"bg-base"' tailwind.config.js             → match (#0f1117 literal hex)
3. --primary: 270 70% 60% in src/index.css         → line 31 (declaration), line 13 (comment)
4. hsl() in index.css :root variables              → 0 (only in comments, not declarations)
5. grep 'class="dark"' index.html                  → <html lang="en" class="dark">
6. grep 'hsl(270, 24%, 7%)' index.html             → background-color: hsl(270, 24%, 7%)
7. npm run build                                   → exits 0 (tsc -b + vite 1.13s, 16.32KB CSS, 312KB JS)
```

## Known Stubs

None. This plan modifies config/theme files only — no UI component stubs introduced.

## Threat Flags

No new security surface introduced. File edits only (no installs). Token collision (T-11-05) mitigated by wholesale replacement in one atomic commit. tailwindcss-animate present in plugins (T-11-06 mitigated).

## Self-Check: PASSED

- frontend/tailwind.config.js: EXISTS — darkMode:["class"] on line 3, tailwindcss-animate in plugins, bridge tokens present
- frontend/src/index.css: EXISTS — --primary:270 70% 60% on line 31, 0 hsl() wrappers in declarations
- frontend/index.html: EXISTS — class="dark" on html, hsl(270,24%,7%) in body background
- Task 1 commit b4d62e7: EXISTS
- Task 2 commit 6a48ee4: EXISTS
- npm run build: exits 0
