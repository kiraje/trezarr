# Phase 11: shadcn Foundation & Purple Theme — Research

**Researched:** 2026-06-03
**Domain:** shadcn/ui + jolly-ui installation on Tailwind v3.4 / React 19 / Vite 7 SPA
**Confidence:** HIGH — all findings consolidated from milestone research verified 2026-06-03 against npm registry, shadcn CLI source, and official docs. No additional web research needed for this phase (SUMMARY.md explicitly flags it as "standard patterns").

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Lock `--primary: 270 70% 60%` as the brand purple anchor. Exact per-token values are visually tuned at the D-09 gate — 270 70% 60% is the starting point, not frozen.
- **D-02:** All CSS variables are bare channel-triple `H S% L%` (e.g. `270 70% 60%`), never wrapped in `hsl()`. The `hsl(var(--x))` wrapper lives only in `tailwind.config.js`.
- **D-03:** `--ring` and `--sidebar-primary` track `--primary` (same purple). Suggested coherent anchors: `--background 270 24% 7%`, `--card 270 22% 11%`, `--muted 270 15% 16%`, `--border 270 18% 20%`, `--primary-foreground 0 0% 100%`, `--destructive 0 72% 51%`, `--radius 0.5rem`, sidebar tokens in the same purple-dark family.
- **D-04:** `--background` is a purple-tinted dark (not legacy blue-black `#0f1117`). Update `<body>`/`html` inline background in `frontend/index.html` to match the new `--background`.
- **D-05:** Legacy `bg-base`/`bg-surface`/`bg-stripe`/`text-primary`/`text-muted` stay blue-black as bridge tokens until all pages reskinned in Phase 15. The colliding keys — `border`, `accent`, `destructive` — are replaced wholesale in one commit.
- **D-06:** Bulk-install the full shadcn set + jolly-ui Table in one clean foundation commit. `init` MUST be pinned to `shadcn@2.10.0`; `add` may use `@latest`.
- **D-07:** Treat `src/components/ui/` as vendor code — never hand-edit. `legacy-peer-deps=true` in `.npmrc` BEFORE the first `add`; do NOT use `--force`.
- **D-08:** Do NOT set `base` in `vite.config.ts`. Keep `build.outDir = ../trezarr/web/static`, `emptyOutDir: true`. Add `@/` alias via `resolve.alias` + `@types/node`. Mirror alias in `tsconfig.json` (`baseUrl: "."`, `paths: { "@/*": ["src/*"] }`).
- **D-09:** Phase 11 ends with a human visual-UAT checkpoint. The `--auto` chain HOLDS at this gate.

### Claude's Discretion

- Exact non-anchor token values (secondary/accent/popover/input shades within the purple-dark family), the precise purple-tinted `--background` lightness, and `components.json` style/baseColor selections.

### Deferred Ideas (OUT OF SCOPE)

- jolly-ui Table beta stability evaluation → Phase 14
- Removing legacy bridge tokens from `tailwind.config.js` → Phase 15
- Sidebar shell / AppSidebar / route restructure → Phase 12
- Backend episodes enrichment → Phase 13
- New Series/Movies/SeriesDetail pages, nav badges → Phase 14
- Reskinning existing pages → Phase 15
- Docker rebuild + live smoke test → Phase 16

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | shadcn/ui + jolly-ui component foundation installed on Tailwind v3; `cn()` util, `@/` path alias, `components.json`, base primitives; SPA build stays green throughout migration | STACK.md §2 path alias setup; §5 jolly-ui install; §8 setup sequence; Pitfall 2-A (dual alias), 3-A (legacy-peer-deps) |
| UI-02 | A purple CSS-variable theme (dark mode default) replaces legacy custom hex tokens across every page | STACK.md §3 tailwind.config.js, §4 index.css; ARCHITECTURE.md §3 migration strategy; PITFALLS.md 1-A (channel-triple), 1-B (token collision), 1-C (darkMode class) |

</phase_requirements>

---

## Summary

Phase 11 is the prerequisite for the entire v1.1 milestone. It installs the shadcn/jolly-ui component layer on the existing Tailwind v3.4 / React 19 / Vite 7 SPA and establishes the purple HSL dark theme — all without changing any page content. The gate condition is a green `tsc -b && vite build` plus in-browser proof that `bg-primary/50` renders as half-opacity purple.

The existing codebase is minimal and clean: `tailwind.config.js` has 8 hex tokens, `index.css` has 3 `@tailwind` lines, `vite.config.ts` has no alias, `tsconfig.json` has no paths, `index.html` has an inline `background-color: #0f1117` and no `.dark` class on `<html>`. Everything in this phase is additive except for three wholesale replacements: `tailwind.config.js` (hex tokens out, CSS-var token map in with bridge), `src/index.css` (bare directives out, HSL `:root` block in), and `index.html` (add `class="dark"`, update inline background to purple).

The single most dangerous trap is the shadcn CLI version split: `npx shadcn@latest` is the 4.x line which emits Tailwind v4 config (`@tailwindcss/vite`, OKLCH variables) that breaks this project's PostCSS pipeline on first run. Every `init` must use `npx shadcn@2.10.0 init`.

**Primary recommendation:** Execute the 11-step sequence in STACK.md §8 verbatim, with D-01–D-09 locked decisions honored at every step. The purple HSL token values are tuned at the D-09 gate, not before.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CSS variable theme / dark mode | Browser (CSS) | Build (Tailwind) | CSS variables are client-side runtime; Tailwind maps them to utility classes at build time |
| `@/` path alias resolution | Build (Vite bundler) | TypeScript (tsc) | Vite resolves imports at bundle time; tsc needs the mirror for type-checking only |
| Component primitives (shadcn CLI) | Build (codegen) | Browser (React) | CLI writes vendor source files at install time; they render client-side |
| `.npmrc` peer-dep resolution | Build (npm) | — | Registry-side at install time; no runtime footprint |
| `legacy-peer-deps` decision | Build (npm) | — | Install-time only; does not affect runtime behaviour |

---

## Standard Stack

### New Runtime Dependencies (to add to `frontend/package.json`)

[VERIFIED: npm registry] — all versions live-queried 2026-06-03.

| Package | Version | Purpose | Notes |
|---------|---------|---------|-------|
| `class-variance-authority` | `^0.7.1` | CVA variant system used by all shadcn components | Stable 2+ years; all shadcn v2 components require it |
| `clsx` | `^2.1.1` | Conditional class string builder inside `cn()` | 239 B; no peer deps |
| `tailwind-merge` | `^3.6.0` | Deduplicates conflicting Tailwind strings inside `cn()` | v3.x supports Tailwind v3 and v4 |
| `tailwindcss-animate` | `^1.0.7` | Tailwind plugin registering accordion/dialog keyframe animations | Required for Accordion, Collapsible, Sheet; functionally complete for v3 |
| `react-aria-components` | `^1.18.0` | jolly-ui primitive layer (Table, Disclosure) | Peer dep `^19.0.0-rc.1` satisfies React 19.0 stable; cosmetic npm warning only |
| `sonner` | `^2.0.7` | Toast system wrapped by shadcn Sonner component | Peer deps explicitly cover `^19.0.0` |

### New Dev Dependencies

| Package | Version | Purpose | Notes |
|---------|---------|---------|-------|
| `@types/node` | `^22.x` | Enables `path.resolve(__dirname, ...)` in `vite.config.ts` | Required for the `@/` alias; add to `devDependencies` |

### Radix UI Primitives (installed per-component by shadcn CLI — do NOT pre-install)

These are pulled automatically. Listed for awareness only.

| Package | Pulled by component |
|---------|-------------------|
| `@radix-ui/react-slot` | button, badge, many others |
| `@radix-ui/react-accordion` | accordion |
| `@radix-ui/react-collapsible` | collapsible |
| `@radix-ui/react-dialog` | sheet |
| `@radix-ui/react-dropdown-menu` | dropdown-menu |
| `@radix-ui/react-separator` | sidebar |
| `@radix-ui/react-tabs` | tabs |
| `@radix-ui/react-tooltip` | tooltip |

All `@radix-ui/*` packages support React 19.0 since June 2024. [VERIFIED: radix-ui.com]

### What is NOT Needed (do not install)

| Package | Why |
|---------|-----|
| `tw-animate-css` | Tailwind v4 replacement; incompatible with v3 |
| `@tailwindcss/vite` | Tailwind v4 Vite plugin; incompatible with v3 PostCSS |
| Any `jolly-ui` npm package | jolly-ui has no npm package — copy-paste registry only |
| `vaul`, `cmdk`, `recharts`, `framer-motion` | Not in v1.1 scope |
| Individual `@react-aria/*` packages | Use bundled `react-aria-components`; individual packages conflict with RAC internals |

---

## Package Legitimacy Audit

Packages are from the milestone research verified 2026-06-03 against the npm registry live.

| Package | Registry | Confidence | Disposition |
|---------|----------|------------|-------------|
| `class-variance-authority` | npm | VERIFIED: npm registry (2026-06-03) | Approved |
| `clsx` | npm | VERIFIED: npm registry (2026-06-03) | Approved |
| `tailwind-merge` | npm | VERIFIED: npm registry (2026-06-03) | Approved |
| `tailwindcss-animate` | npm | VERIFIED: npm registry (2026-06-03) | Approved |
| `react-aria-components` | npm | VERIFIED: npm registry (2026-06-03) | Approved |
| `sonner` | npm | VERIFIED: npm registry (2026-06-03) | Approved |
| `@types/node` | npm | VERIFIED: npm registry (2026-06-03) | Approved |

**Packages removed due to slopcheck verdict:** none
**Packages flagged as suspicious:** none

*Note: slopcheck was not re-run in this session. Packages were verified as part of the original milestone research session on 2026-06-03 by live npm registry queries. Package install history in this project should confirm these are well-established packages (millions of weekly downloads each).*

---

## Architecture Patterns

### System Architecture Diagram

```
frontend/package.json
        │
        ▼ npm install (runtime deps)
  clsx + tailwind-merge + class-variance-authority
  tailwindcss-animate + react-aria-components + sonner
        │
        ▼ @types/node → devDependencies
  .npmrc (legacy-peer-deps=true)
        │
        ▼ npx shadcn@2.10.0 init
  components.json ──────────────────────► src/lib/utils.ts (cn())
        │
        ▼ npm install + tsconfig + vite.config.ts
  @/ alias ◄──── tsconfig.json paths ──── vite.config.ts resolve.alias
        │
        ▼ npx shadcn@2.10.0 add [bulk]
  src/components/ui/  (vendor — never hand-edit)
        │
        ▼ REGISTRY_URL=... npx shadcn@latest add table
  src/components/ui/table.tsx (jolly-ui React Aria Table)
        │
        ▼ File edits (manual)
  tailwind.config.js ── darkMode:["class"] + CSS-var token map + bridge tokens + animate plugin
  src/index.css      ── @layer base { :root { --primary: 270 70% 60%; ... } }
  frontend/index.html ─ <html class="dark"> + body background update
        │
        ▼ tsc -b && vite build
  GREEN build ──► ../trezarr/web/static/
        │
        ▼ browser visual UAT (D-09 gate — HOLDS auto chain)
  bg-primary/50 = half-opacity purple ✓
```

### Recommended Project Structure After Phase 11

```
frontend/
├── .npmrc                    # legacy-peer-deps=true  (NEW)
├── components.json           # shadcn project config  (NEW — written by CLI)
├── index.html                # class="dark" added; inline bg updated  (MODIFIED)
├── package.json              # 6 runtime + 1 dev dep added  (MODIFIED)
├── tailwind.config.js        # CSS-var token map + bridge + animate plugin  (REPLACED)
├── tsconfig.json             # baseUrl + paths added  (MODIFIED)
├── vite.config.ts            # resolve.alias + @types/node import added  (MODIFIED)
└── src/
    ├── index.css             # HSL :root block  (REPLACED)
    ├── lib/
    │   └── utils.ts          # cn() utility  (NEW — written by CLI)
    └── components/
        └── ui/               # vendor code — never hand-edit  (NEW — written by CLI)
            ├── sidebar.tsx
            ├── button.tsx
            ├── badge.tsx
            ├── card.tsx
            ├── tabs.tsx
            ├── accordion.tsx
            ├── collapsible.tsx
            ├── tooltip.tsx
            ├── skeleton.tsx
            ├── sonner.tsx
            ├── dropdown-menu.tsx
            └── table.tsx     # jolly-ui React Aria Table
```

---

## Ordered Command Sequence

This is the canonical execution order. Every step maps to a locked decision.

### Step 0 — Working directory

```bash
cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr/frontend
```

### Step 1 — Create `.npmrc` (D-07: MUST precede first `shadcn` invocation)

Create `frontend/.npmrc`:
```
legacy-peer-deps=true
```

This prevents `ERESOLVE` from `cmdk` and `react-day-picker` when shadcn components are added. Document in a comment why it exists so future maintainers understand. Do NOT use `--force` as a substitute.

### Step 2 — Install runtime dependencies

```bash
npm install \
  class-variance-authority@^0.7.1 \
  clsx@^2.1.1 \
  tailwind-merge@^3.6.0 \
  tailwindcss-animate@^1.0.7 \
  react-aria-components@^1.18.0 \
  sonner@^2.0.7
```

### Step 3 — Install `@types/node` dev dependency (D-08)

```bash
npm install -D @types/node
```

Required for `path.resolve(__dirname, ...)` in `vite.config.ts`. The current `vite.config.ts` does not import `path`; the alias step adds this import.

### Step 4 — Wire `@/` alias in `vite.config.ts` (D-08)

Replace the current `vite.config.ts` content:

```typescript
import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Build the SPA directly into trezarr/web/static so FastAPI can serve it
// via StaticFiles(html=True) mounted as the last route (Pattern 6).
// NOTE: Do NOT set `base` here — that would break FastAPI's absolute-path
// asset serving from the root mount. outDir and emptyOutDir are load-bearing.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "../trezarr/web/static",
    emptyOutDir: true,
  },
})
```

Key constraints: no `base` field, `outDir` unchanged. [VERIFIED: STACK.md §2; PITFALLS.md 5-A]

### Step 5 — Wire `@/` alias in `tsconfig.json` (D-08)

The current `tsconfig.json` has no `baseUrl` or `paths`. Add to `compilerOptions`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

IMPORTANT: Both `vite.config.ts` and `tsconfig.json` must be updated in the same commit. A partial alias setup causes one of: build fails but tsc passes, or IDE shows red underlines but build works. [VERIFIED: PITFALLS.md 2-A]

### Step 6 — Run shadcn init (pinned to 2.10.0 — D-06)

```bash
npx shadcn@2.10.0 init
```

Prompt answers:
- Style: **New York** (compact, dashboard-appropriate)
- Base color: **Zinc** (closest neutral dark; all tokens are overridden anyway)
- CSS variables: **yes**
- Global CSS file: `src/index.css`
- Tailwind config: `tailwind.config.js`
- Components path alias: `@/components`
- Utils path alias: `@/lib/utils`

This writes `components.json`, `src/lib/utils.ts` (the `cn()` function), and a `:root` CSS variable block in `src/index.css`. The generated `index.css` block and `tailwind.config.js` are immediately replaced in steps 7 and 8.

**CRITICAL — NEVER RUN:** `npx shadcn@latest init` (4.x emits Tailwind v4 config that breaks this project). [VERIFIED: STACK.md §2; ui.shadcn.com/docs/tailwind-v4]

### Step 7 — Replace `tailwind.config.js` with bridge+shadcn token map (D-02, D-05)

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        // ── BRIDGE TOKENS — keep until ALL pages reskinned in Phase 15 ──
        // These five keys do NOT collide with shadcn's namespace.
        // They preserve existing page classes (bg-base, text-primary, etc.)
        // until Phase 15 removes them. (D-05)
        "bg-base":      "#0f1117",
        "bg-surface":   "#1a1d27",
        "bg-stripe":    "#1e2130",
        "text-primary": "#e2e6f0",
        "text-muted":   "#6b7280",

        // ── SHADCN CSS-VARIABLE TOKENS ──
        // Values in :root are bare H S% L% channel triples (no hsl() wrapper).
        // The hsl() wrapper is applied here in tailwind.config.js only.
        // Writing hsl() inside the CSS variable silently breaks bg-primary/50. (D-02)
        border:     "hsl(var(--border))",
        input:      "hsl(var(--input))",
        ring:       "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT:    "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT:    "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT:    "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT:    "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT:    "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT:    "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT:    "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Sidebar tokens — required by shadcn sidebar.tsx CSS variable references
        sidebar: {
          DEFAULT:                "hsl(var(--sidebar-background))",
          foreground:             "hsl(var(--sidebar-foreground))",
          primary:                "hsl(var(--sidebar-primary))",
          "primary-foreground":   "hsl(var(--sidebar-primary-foreground))",
          accent:                 "hsl(var(--sidebar-accent))",
          "accent-foreground":    "hsl(var(--sidebar-accent-foreground))",
          border:                 "hsl(var(--sidebar-border))",
          ring:                   "hsl(var(--sidebar-ring))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to:   { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to:   { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up":   "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
```

Notes:
- `darkMode: ["class"]` is required. Without it, `.dark` selector does nothing and all shadcn CSS variables in `.dark {}` are never applied. [PITFALLS.md 1-C]
- The old `border`, `accent`, `destructive` keys from the legacy config are replaced wholesale by the shadcn CSS-var-backed entries. This is intentional and correct. (D-05)
- The `require("tailwindcss-animate")` call is CommonJS require inside an ESM-style config — this works in Vite's PostCSS/Tailwind processing context. If a module error occurs at build time, add `import tailwindcssAnimate from "tailwindcss-animate"` at the top and replace with `plugins: [tailwindcssAnimate]`.
- The accordion keyframes reference `--radix-accordion-content-height`, a CSS custom property injected at render time by the Radix Accordion component. This is correct. [VERIFIED: STACK.md §3]

### Step 8 — Replace `src/index.css` with purple HSL `:root` block (D-01, D-02, D-03, D-04)

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /*
     * Trezarr v1.1 — dark-only purple theme.
     * ALL values are bare H S% L% channel triples — NO hsl() wrapper.
     * The hsl() wrapper is applied exclusively in tailwind.config.js.
     * Writing hsl() here silently breaks opacity modifiers (bg-primary/50). (D-02)
     *
     * Purple anchor: --primary: 270 70% 60%  (D-01)
     * Exact values are visually tuned at the Phase 11 human-verify gate (D-09).
     * 270 70% 60% is the starting point, not a frozen final value.
     */

    --radius: 0.5rem;

    /* Core surfaces — purple-tinted dark (D-04) */
    --background:           270 24% 7%;      /* purple-dark root; replaces #0f1117 */
    --foreground:           270 10% 90%;

    --card:                 270 22% 11%;
    --card-foreground:      270 10% 90%;

    --popover:              270 22% 11%;
    --popover-foreground:   270 10% 90%;

    /* Primary — purple accent anchor (D-01, D-03) */
    --primary:              270 70% 60%;     /* ~purple-500; tune at D-09 gate */
    --primary-foreground:   0 0% 100%;

    /* Secondary — slightly lighter surface */
    --secondary:            270 15% 16%;
    --secondary-foreground: 270 10% 90%;

    /* Muted */
    --muted:                270 15% 16%;
    --muted-foreground:     270 8% 50%;

    /* Accent — hover highlight */
    --accent:               270 20% 20%;
    --accent-foreground:    270 10% 90%;

    /* Destructive */
    --destructive:          0 72% 51%;
    --destructive-foreground: 0 0% 100%;

    /* Border / input / ring (D-03: ring tracks primary) */
    --border:               270 18% 20%;
    --input:                270 18% 20%;
    --ring:                 270 70% 60%;     /* tracks --primary */

    /* Sidebar tokens — required by shadcn sidebar.tsx (D-03) */
    --sidebar-background:           270 22% 9%;
    --sidebar-foreground:           270 10% 90%;
    --sidebar-primary:              270 70% 60%;   /* tracks --primary */
    --sidebar-primary-foreground:   0 0% 100%;
    --sidebar-accent:               270 15% 14%;
    --sidebar-accent-foreground:    270 10% 90%;
    --sidebar-border:               270 18% 20%;
    --sidebar-ring:                 270 70% 60%;   /* tracks --primary */
  }

  /*
   * No .light block — Trezarr is dark-mode-first/only.
   * Dark mode is activated by class="dark" on <html> (index.html, step 9).
   * The :root values above ARE the dark theme.
   * (If light mode is ever added, move dark values to .dark and define
   *  light values in :root.)
   */

  * {
    @apply border-border;
  }

  body {
    @apply bg-background text-foreground;
  }
}
```

### Step 9 — Update `frontend/index.html` (D-04, D-09)

Two changes:
1. Add `class="dark"` to `<html>`: `<html lang="en" class="dark">`
2. Update the inline `background-color` to match the new purple-tinted `--background`. Since the CSS variable resolves to `hsl(270 24% 7%)` ≈ `#100d17`, update the inline style to `background-color: hsl(270, 24%, 7%)` (or the equivalent hex). This ensures the page root reads purple before the SPA hydrates.

The `color: #e2e6f0` inline style can remain or be updated to `hsl(270, 10%, 90%)` — either is correct during the bridge period.

### Step 10 — Bulk-install shadcn components (D-06)

```bash
npx shadcn@2.10.0 add sidebar button badge card tabs accordion collapsible tooltip skeleton sonner dropdown-menu
```

All components land in `src/components/ui/`. Treat as vendor code — never hand-edit. [D-07]

### Step 11 — Add jolly-ui Table via registry URL (D-06)

After `react-aria-components` is in `package.json`:

```bash
REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table
```

`shadcn@latest` (4.x) is safe for the `add` command — it copies component source files only and does not touch `tailwind.config.js` or re-run init. The 2.x pin is only required for `init`. [VERIFIED: STACK.md §5]

jolly-ui has no npm package. It is a copy-paste registry at `https://jollyui.dev/r`. [VERIFIED: jollyui.dev/docs/installation]

### Step 12 — Verify build

```bash
npm run build
# Expects: tsc -b && vite build both pass; ../trezarr/web/static/ populated
```

---

## Purple HSL Token Table

All tokens use bare `H S% L%` format (no `hsl()` wrapper) in `src/index.css`.
The `hsl(var(--x))` wrapper lives exclusively in `tailwind.config.js`.
Values below are the starting-point defaults anchored on D-01. **Tune at D-09 gate.**

| CSS Variable | Starting Value | Resolves to (approx) | Role |
|---|---|---|---|
| `--primary` | `270 70% 60%` | ~`#8b5cf6` purple-500 | Brand accent; buttons, rings, active states |
| `--primary-foreground` | `0 0% 100%` | white | Text on primary-colored backgrounds |
| `--ring` | `270 70% 60%` | same as `--primary` | Focus rings; tracks primary (D-03) |
| `--background` | `270 24% 7%` | ~`#100d17` | Page root — purple-tinted dark (D-04) |
| `--foreground` | `270 10% 90%` | ~`#e3e1e8` | Default text |
| `--card` | `270 22% 11%` | ~`#19151f` | Card/panel surfaces |
| `--card-foreground` | `270 10% 90%` | same as `--foreground` | Text on cards |
| `--popover` | `270 22% 11%` | same as `--card` | Popover/dropdown background |
| `--popover-foreground` | `270 10% 90%` | same as `--foreground` | Text in popovers |
| `--secondary` | `270 15% 16%` | ~`#231e2b` | Secondary surfaces |
| `--secondary-foreground` | `270 10% 90%` | same as `--foreground` | Text on secondary |
| `--muted` | `270 15% 16%` | same as `--secondary` | Muted surface |
| `--muted-foreground` | `270 8% 50%` | ~`#7d7887` | Muted/dimmed text |
| `--accent` | `270 20% 20%` | ~`#2c2537` | Hover highlight surface |
| `--accent-foreground` | `270 10% 90%` | same as `--foreground` | Text on accent |
| `--destructive` | `0 72% 51%` | ~`#e03131` | Error / delete actions |
| `--destructive-foreground` | `0 0% 100%` | white | Text on destructive |
| `--border` | `270 18% 20%` | ~`#2a2333` | Borders |
| `--input` | `270 18% 20%` | same as `--border` | Input borders |
| `--radius` | `0.5rem` | — | Border radius scale |
| `--sidebar-background` | `270 22% 9%` | ~`#140f1b` | Sidebar panel — slightly darker than page |
| `--sidebar-foreground` | `270 10% 90%` | same as `--foreground` | Sidebar text |
| `--sidebar-primary` | `270 70% 60%` | same as `--primary` | Active nav item (D-03) |
| `--sidebar-primary-foreground` | `0 0% 100%` | white | Text on active nav |
| `--sidebar-accent` | `270 15% 14%` | ~`#1c172a` | Sidebar hover state |
| `--sidebar-accent-foreground` | `270 10% 90%` | same as `--foreground` | Sidebar hover text |
| `--sidebar-border` | `270 18% 20%` | same as `--border` | Sidebar borders |
| `--sidebar-ring` | `270 70% 60%` | same as `--primary` | Sidebar focus rings (D-03) |

Note: `ARCHITECTURE.md` documents `271 71% 58%` as an alternative anchor. Both are within 1-2 degree/percent of each other. Choose one at the D-09 gate, then propagate to every token that tracks `--primary`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Conditional + merged class strings | Custom string concat | `cn()` via `clsx` + `tailwind-merge` | Tailwind utility deduplication requires tailwind-merge; hand-rolled concat produces invalid class strings with conflicting utilities |
| Component variant styling | if/else className strings | `cva()` from `class-variance-authority` | shadcn components already use CVA; mixing patterns makes component source diverge from CLI-generated baseline |
| Dark mode toggle | `prefers-color-scheme` media query | `class="dark"` on `<html>` + `darkMode: ["class"]` | Trezarr is dark-only; media-query approach fights the forced dark strategy and triggers unexpected light flashes |
| CSS variable declaration format | Manually convert hex to hsl() | Use bare `H S% L%` channel triples | `hsl()` inside the variable silently breaks opacity modifiers — this is the #1 runtime breakage with no compile error |
| shadcn component code | Writing custom primitives | `npx shadcn@2.10.0 add <component>` | CLI generates accessibility-correct, shadcn-compatible, CVA-based components; hand-written equivalents drift |

---

## Common Pitfalls

### Pitfall 1: HSL Channel-Triple Format (the #1 silent breakage)

**What goes wrong:** CSS variables written as `--primary: hsl(270 70% 60%)` instead of `--primary: 270 70% 60%`. The opacity modifier `bg-primary/50` resolves to `hsl(hsl(270 70% 60%) / 50%)` which browsers silently discard. The component renders at full opacity with no compile error.

**Why it happens:** Developers migrating from hex tokens naturally write full color values. The channel-triple format is a Tailwind v3 shadcn convention, not general CSS.

**How to avoid:** Never wrap CSS variable values in `hsl()`. Verify immediately after theme authoring: render a `<div className="bg-primary/50 w-8 h-8">` in the browser and confirm it appears at half opacity with purple showing through. This is the D-09 gate's opacity proof. [VERIFIED: PITFALLS.md 1-A; STACK.md §4]

**Warning signs:** Components at full opacity despite `/50` modifier; no console errors; DevTools shows invalid computed value.

---

### Pitfall 2: `shadcn@latest init` Breaks Tailwind v3 (the #1 operator error)

**What goes wrong:** Running `npx shadcn@latest init` (v4.x CLI) emits `@tailwindcss/vite` plugin config, OKLCH color variables, and `tw-animate-css` imports. This breaks the existing PostCSS pipeline on first run.

**Why it happens:** `shadcn@latest` is the v4 line as of mid-2026. The v3 line is `shadcn@2.x`.

**How to avoid:** Always use `npx shadcn@2.10.0 init`. The `add` command (individual components, jolly-ui via registry URL) can safely use `shadcn@latest` — it only copies source files. [VERIFIED: ui.shadcn.com/docs/tailwind-v4; STACK.md §2]

**Warning signs:** `tailwind.config.js` contains `@tailwindcss/vite` or OKLCH variables after init; build fails with PostCSS plugin errors.

---

### Pitfall 3: Token Namespace Collisions

**What goes wrong:** The existing `tailwind.config.js` has `border: "#2d3148"`, `accent: "#3b82f6"`, `destructive: "#ef4444"` as plain strings. shadcn uses the same keys as nested objects (`border: "hsl(var(--border))"`, `accent: { DEFAULT, foreground }`). A partial replacement leaves conflicting definitions.

**Why it happens:** Tailwind `extend` merges objects but the `border` key at top level is replaced by whichever entry comes last. The result is unpredictable.

**How to avoid:** Replace the entire `colors` block wholesale in one commit. The bridge period retains `bg-base`, `bg-surface`, `bg-stripe`, `text-primary`, `text-muted` (these do NOT collide with shadcn keys). The colliding keys (`border`, `accent`, `destructive`) are removed and replaced with the CSS-var-backed shadcn entries. (D-05) [VERIFIED: PITFALLS.md 1-B]

**Warning signs:** `border-border` class rendering a different color than `border-[#2d3148]` after init; TypeScript LSP showing `accent` type as both `string` and `{ DEFAULT, foreground }`.

---

### Pitfall 4: `darkMode: ["class"]` Missing or `.dark` Not Applied to `<html>`

**What goes wrong:** Two separate requirements must be met simultaneously: `darkMode: ["class"]` in `tailwind.config.js` AND `class="dark"` on `<html>` in `index.html`. Missing either one breaks dark mode.

- Missing `darkMode: ["class"]`: Tailwind does not generate `dark:` variant classes; `.dark` selector has no effect.
- Missing `class="dark"` on `<html>`: Generated `dark:` classes exist but are never triggered; all shadcn components render in light mode (white backgrounds on dark page).

**How to avoid:** Both changes in the same commit. The `darkMode: ["class"]` key goes in `tailwind.config.js`. The `class="dark"` attribute goes directly in `frontend/index.html` on the `<html>` element — this is the simplest approach for a dark-only app. Do NOT rely on `document.documentElement.classList.add("dark")` in JS; the inline attribute is immediate (no flash on load). [VERIFIED: PITFALLS.md 1-C; ARCHITECTURE.md §3 Step 5]

**Warning signs:** All shadcn components render white/light-colored; browser DevTools shows `:root` values active but `.dark` block inactive; build passes but visual inspection fails.

---

### Pitfall 5: `tailwindcss-animate` Missing from `plugins`

**What goes wrong:** shadcn components use `animate-in`, `animate-out`, `fade-in-0`, `zoom-in-95`, etc. Without `plugins: [require("tailwindcss-animate")]` in `tailwind.config.js`, these classes are undefined and purged from production builds. Dialog, Tooltip, Popover, Accordion, and Dropdown open/close with no animation (instant snap).

**Why it happens:** The plugin must be explicitly registered. Forgetting it has no compile error; it only manifests visually.

**How to avoid:** Add `tailwindcss-animate` to `plugins` in the same commit that adds the token block. After the build, verify: `grep -l "animate-in" dist/assets/*.css` — it must match. Do NOT use `tw-animate-css` (the Tailwind v4 equivalent). [VERIFIED: PITFALLS.md 1-D; STACK.md §3]

**Warning signs:** Accordion opens instantly with no slide; Tooltip appears with no fade; production build only (works in dev because Vite dev server may include more).

---

### Pitfall 6: `@/` Alias in Only One Config (partial setup)

**What goes wrong:** The `@/` alias requires both `resolve.alias` in `vite.config.ts` AND `paths` in `tsconfig.json`. A partial setup causes asymmetric failures: alias in Vite only → TypeScript IDE shows red underlines but build works; alias in tsconfig only → IDE works but `vite build` fails with `Cannot find module "@/lib/utils"`.

**How to avoid:** Update both files in the same commit. The current `tsconfig.json` uses `moduleResolution: bundler`, which delegates resolution to Vite — `paths` alone is not sufficient; `resolve.alias` in Vite is still required. [VERIFIED: PITFALLS.md 2-A; STACK.md §2]

**Warning signs:** `tsc -b` passes but `vite build` fails; or VSCode shows red underlines on `@/` imports while build succeeds.

---

### Pitfall 7: `legacy-peer-deps` Added AFTER the First `shadcn add` Call

**What goes wrong:** If `legacy-peer-deps=true` is not in `.npmrc` before the first `npx shadcn@2.10.0 add` call, npm's strict resolver throws `ERESOLVE unable to resolve dependency tree` for `cmdk` and `react-day-picker` (React 19 peer dep ranges).

**How to avoid:** Create `.npmrc` with `legacy-peer-deps=true` as the FIRST action before any npm or npx command. Do NOT use `--force` as a substitute — it can cause subtle runtime breakage. Document why this exists in a comment. [VERIFIED: PITFALLS.md 3-A; STACK.md §8]

**Warning signs:** `npm error ERESOLVE` on any `shadcn add` command; `react-aria-components` peer dep warnings (cosmetic — these are harmless on React 19 stable).

---

## Verification Approach

### Build Verification

```bash
# From frontend/ directory
npm run build
# Equivalent to: tsc -b && vite build
```

Success criterion: exits 0. Failure modes to watch:
- `Cannot find module "@/lib/utils"` → alias not wired in `vite.config.ts`
- TypeScript errors on shadcn component source → `skipLibCheck` should handle this; if not, check `tsconfig.json` includes `src/` only
- PostCSS errors → sign that `shadcn@latest init` was run instead of `shadcn@2.10.0 init`

### Animation Class Verification

After successful build:

```bash
grep -l "animate-in" dist/assets/*.css
```

Must match at least one file. If no match: `tailwindcss-animate` is not in `plugins` or classes are not referenced in any scanned source file.

### In-Browser Opacity Modifier Proof (D-09 gate)

Add a temporary element to any page (or the browser console):

```html
<div class="bg-primary/50 w-16 h-16 fixed top-4 right-4 rounded"></div>
```

Expected: a semi-transparent purple square. If it renders as full-opacity purple or is invisible: the CSS variable has an `hsl()` wrapper in `index.css` (Pitfall 1). This is the canonical proof the channel-triple format is correct.

### Dark Mode Activation Proof (D-09 gate)

Open DevTools → Elements → inspect `<html>`. Confirm:
- `class="dark"` attribute present
- In Computed Styles, `background-color` on `<body>` resolves to a dark purple (approximately `hsl(270, 24%, 7%)` ≈ `#100d17`)

---

## Validation Architecture

`workflow.nyquist_validation` is `true` in `.planning/config.json`. This section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Not applicable — Phase 11 is infrastructure only; no business logic introduced |
| Quick build check | `npm run build` (from `frontend/`) |
| Full verification | `tsc -b && vite build` + manual browser UAT per D-09 |

Phase 11 introduces no testable business logic. There are no unit tests to write. The validation gate is the build-green + browser-UAT combination required by D-09.

### Phase Requirements → Validation Map

| Req ID | Behavior | Validation Type | Observable Signal |
|--------|----------|-----------------|-------------------|
| UI-01 | shadcn/jolly-ui installed; `@/` alias works; `cn()` exists; `components.json` present; build stays green | Build gate | `npm run build` exits 0; `tsc -b` exits 0; `src/components/ui/` populated with all 11 components; `src/lib/utils.ts` present |
| UI-01 | Existing page content unchanged | Visual inspection | Open any existing page (`/queue`, `/settings`, `/bible`) in browser — content and layout must be identical to pre-Phase-11 |
| UI-02 | Purple CSS-variable theme active | Visual inspection | `<html class="dark">` in DevTools; body background resolves to dark purple (not `#0f1117` blue-black) |
| UI-02 | Channel-triple format correct (opacity modifiers work) | Browser UAT (D-09 gate) | `bg-primary/50` renders as half-opacity purple; DevTools computed value is a valid `color-mix()` or `rgb()` with 50% alpha |
| UI-02 | Purple Button renders | Browser UAT (D-09 gate) | A `<Button variant="default">` displays with purple background |
| UI-02 | No broken pages | Visual inspection | All existing pages load and render without white/unstyled content |

### Sampling Rate

- **Build gate:** `npm run build` after every file change (Steps 4–9 each warrant a build check before proceeding)
- **Phase gate:** Full suite green (`tsc -b && vite build` passing) + all D-09 browser UAT criteria met before closing Phase 11
- **D-09 gate:** Human visual review — the `--auto` chain holds until human confirmation

### Wave 0 Gaps

None — Phase 11 requires no test file creation. The validation is build + browser UAT.

---

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high` per `.planning/config.json`.

### Applicable ASVS Categories

| ASVS Category | Applies | Notes |
|---------------|---------|-------|
| V2 Authentication | No | No auth changes in this phase |
| V3 Session Management | No | No session changes |
| V4 Access Control | No | No access control changes |
| V5 Input Validation | No | No user input processed in this phase |
| V6 Cryptography | No | No cryptographic operations |

Phase 11 is purely frontend infrastructure (package installs, config file edits, CSS). No security-relevant surface area is introduced.

### Known Threat Patterns

None applicable to this phase. The one security-adjacent note: `legacy-peer-deps=true` in `.npmrc` is an intentional install-time setting to resolve React 19 peer dep conflicts — it does not weaken runtime security.

---

## Open Questions

1. **Purple HSL final values**
   - What we know: `270 70% 60%` is the locked starting anchor (D-01). ARCHITECTURE.md suggests `271 71% 58%` as an alternative.
   - What's unclear: The exact values for secondary, muted, accent, background lightness that look visually coherent as a complete purple-dark theme.
   - Resolution: This is a D-09 gate design decision, not a research blocker. The token table above provides reasonable starting values. Tune in-browser, commit the final values before closing Phase 11. This is explicitly listed as "Claude's Discretion" in CONTEXT.md.

---

## Environment Availability

Phase 11 is frontend-only infrastructure. No external services are required.

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| Node.js / npm | All npm commands | Assumed (project already builds) | `node --version` should show 18+ |
| `npx` | shadcn CLI invocations | Comes with npm | |
| Internet access (registry.npmjs.org) | npm install, npx shadcn@2.10.0 | Required for install commands | jolly-ui registry at jollyui.dev/r also requires outbound access |

**Missing dependencies with no fallback:** None — environment is known-working (project previously built).

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| `shadcn@latest init` (v4 line) | `shadcn@2.10.0 init` (v3 line) | v4 CLI changed to Tailwind v4 / OKLCH; v3 projects must pin to 2.x |
| Hex token extensions in `tailwind.config.js` | HSL CSS-variable token map | CSS variables enable opacity modifiers and theme switching |
| No `darkMode` key (default: `"media"`) | `darkMode: ["class"]` | Forced-dark apps must use class strategy |
| `tw-animate-css` (v4) | `tailwindcss-animate` (v3) | Different packages for the two Tailwind major lines |
| jolly-ui via npm install | `REGISTRY_URL=... npx shadcn@latest add` | jolly-ui has no npm package; copy-paste registry model |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `shadcn@2.10.0` is the current latest 2.x stable | Standard Stack | If 2.11.x exists, use that instead — functionally equivalent |
| A2 | All 11 shadcn components bulk-installed via one `add` command will write to `src/components/ui/` without conflict | Command Sequence Step 10 | If any component fails, run them individually to isolate |
| A3 | jolly-ui registry at `https://jollyui.dev/r` is reachable and the Table component is still present | Command Sequence Step 11 | If Table is unavailable, defer to Phase 14 per the deferred-ideas list |
| A4 | `require("tailwindcss-animate")` works in the ESM-style `export default` tailwind.config.js | tailwind.config.js Step 7 | If CommonJS/ESM conflict, switch to `import tailwindcssAnimate from "tailwindcss-animate"` at top + `plugins: [tailwindcssAnimate]` |

---

## Sources

### Primary (HIGH confidence)

- `.planning/research/STACK.md` — verified 2026-06-03 against npm registry live queries; shadcn CLI source at github.com/shadcn-ui/ui `packages/shadcn/src/utils/templates.ts`; exact setup sequence and HSL template
- `.planning/research/PITFALLS.md` — verified against shadcn official docs, GitHub issues, Trezarr codebase
- `.planning/research/ARCHITECTURE.md` — verified against Trezarr source; four migration seams; dark-mode wiring
- `.planning/research/SUMMARY.md` — consolidated v1.1 plan; Phase 1 Foundation deliverables
- `.planning/phases/11-shadcn-foundation-purple-theme/11-CONTEXT.md` — locked decisions D-01 through D-09
- `frontend/tailwind.config.js` — current baseline (8 hex tokens, no darkMode, no plugins)
- `frontend/src/index.css` — current baseline (3 bare `@tailwind` lines)
- `frontend/vite.config.ts` — current baseline (no alias, outDir set)
- `frontend/tsconfig.json` — current baseline (no baseUrl, no paths, strict mode)
- `frontend/package.json` — current baseline (no new deps yet)
- `frontend/index.html` — current baseline (`<html lang="en">`, inline hex background)

### Secondary (MEDIUM confidence)

- `ui.shadcn.com/docs/tailwind-v4` — v3/v4 CLI split; `shadcn@2.3.0` minimum for v3 projects
- `jollyui.dev/docs/installation` — registry URL; shadcn init prerequisite; no npm package

---

## Metadata

**Confidence breakdown:**
- Command sequence: HIGH — copied from verified STACK.md §8 with baseline deltas applied
- Token table: HIGH (format, structure) / MEDIUM (exact starting values — tuned at D-09)
- Pitfalls: HIGH — consolidated from PITFALLS.md which was verified against official sources
- Validation: HIGH — build gate is deterministic; browser UAT is straightforward

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (stable ecosystem; shadcn v2.x line is stable)
