# Technology Stack — v1.1 UI v2 (shadcn + jolly-ui)

**Project:** Trezarr frontend — shadcn/ui + jolly-ui component foundation
**Researched:** 2026-06-03
**Scope:** Stack additions only for the UI v2 milestone. Python/FastAPI/SQLAlchemy/etc. are shipped v1 — not restated here.
**Overall confidence:** HIGH (npm registry versions live-verified 2026-06-03; shadcn CLI source read directly; Radix and React Aria peer deps confirmed)

---

## Summary

Adding shadcn/ui (Radix primitives) + jolly-ui (React Aria Components) to an existing React 19 / Tailwind v3.4 / Vite 7 project requires: (a) six runtime npm packages, (b) shadcn CLI pinned to `shadcn@2.x` (the Tailwind v3 line), (c) a `components.json` with explicit `tailwind.config` path, (d) a path alias (`@/`) wired through both `tsconfig.json` and `vite.config.ts`, (e) a rewritten `tailwind.config.js` with the CSS-variable color map + `tailwindcss-animate` plugin + accordion keyframes, and (f) a rewritten `src/index.css` with the shadcn HSL `:root`/`.dark` variable block.

jolly-ui is **not a package** — it is a shadcn-style copy-paste registry served at `https://jollyui.dev/r`. Components are added via the standard shadcn CLI (`REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add <component>`). The only extra runtime dep jolly-ui needs is `react-aria-components` (1.18.0 stable). It shares `components.json` with shadcn; both use the same `cn()` util and CSS-variable theme. The two primitive layers (Radix vs React Aria) do not conflict — they target different components.

**Key constraint:** Stay on `shadcn@2.x` (2.10.0 is the latest 2.x stable as of this writing) for `init`. The main branch / `shadcn@latest` (4.x) has switched to Tailwind v4 / OKLCH. Running `shadcn@latest init` on a Tailwind v3 project will emit v4 config that breaks the existing setup.

---

## 1. Dependency Table

All versions live-verified against the npm registry on 2026-06-03.

### Runtime additions (to `frontend/package.json` dependencies)

| Package | Version | Why needed | Notes |
|---------|---------|-----------|-------|
| `class-variance-authority` | `^0.7.1` | CVA — shadcn components use `cva()` to express slot/variant classes | Stable for 2 years; 0.7.x is the production line used by all shadcn v2 components |
| `clsx` | `^2.1.1` | Conditional class string helper; used inside `cn()` util | Tiny (239 B); no peer deps |
| `tailwind-merge` | `^3.6.0` | Deduplicates/merges conflicting Tailwind utility strings at runtime inside `cn()` | v3.x supports both Tailwind v3 and v4; no peer deps |
| `tailwindcss-animate` | `^1.0.7` | Tailwind plugin that registers shadcn's accordion/collapsible/dialog keyframe animations | Required for Accordion, Collapsible, and Sheet; last updated 3 years ago but functionally complete for Tailwind v3 |
| `react-aria-components` | `^1.18.0` | jolly-ui's primitive layer — replaces Radix for jolly-ui components (Table, Disclosure) | Peer deps: `react ^16.8 || ^17 || ^18 || ^19.0.0-rc.1` — covers React 19.0 (see React 19 notes) |
| `sonner` | `^2.0.7` | Toast/notification system; shadcn's Sonner component wraps this | Peer deps explicitly list `^18.0.0 || ^19.0.0 || ^19.0.0-rc` — React 19 clean |

### Dev additions (to `devDependencies`)

| Package | Version | Why needed | Notes |
|---------|---------|-----------|-------|
| `@types/node` | `^22.x` | Needed by `vite.config.ts` to call `path.resolve(__dirname, ...)` for the `@/` alias | Add if missing |

### Radix UI primitives (installed per-component by shadcn CLI — do NOT pre-install)

These are pulled automatically by `npx shadcn@2.x add <component>`. Listed here for awareness only. Versions are current as of 2026-06-03.

| Package | Current version | Pulled by |
|---------|----------------|-----------|
| `@radix-ui/react-slot` | 1.2.4 | Button, Badge, many others |
| `@radix-ui/react-accordion` | 1.2.12 | Accordion |
| `@radix-ui/react-collapsible` | 1.1.12 | Collapsible (sidebar sections) |
| `@radix-ui/react-dialog` | 1.1.15 | Dialog, Sheet |
| `@radix-ui/react-dropdown-menu` | 2.1.16 | DropdownMenu |
| `@radix-ui/react-label` | 2.1.8 | Form labels |
| `@radix-ui/react-separator` | 1.1.8 | Sidebar dividers |
| `@radix-ui/react-tabs` | 1.1.13 | Tabs (shadcn version) |
| `@radix-ui/react-tooltip` | 1.2.8 | Tooltip |

All `@radix-ui/*` packages declare peer React `^16.8 || ^17.0 || ^18.0 || ^19.0 || ^19.0.0-rc` — React 19.0 clean since June 2024.

### What is NOT needed

| Package | Why not needed |
|---------|---------------|
| `@radix-ui/react-icons` | lucide-react is already installed and preferred |
| `tw-animate-css` | That is the Tailwind v4 replacement for `tailwindcss-animate`; do not add on v3 |
| `@tailwindcss/vite` | That is the Tailwind v4 Vite plugin; incompatible with v3 |
| Any `jolly-ui` npm package | jolly-ui has no npm package — it is a copy-paste registry only |
| `cmdk` | Command palette; not in scope for v1.1 |
| `recharts` | Charts; not in scope for v1.1 |
| `vaul` | Drawer; not needed for v1.1 sidebar (shadcn sidebar is not vaul-based) |
| `framer-motion` | Not needed; shadcn v3 animations are Tailwind keyframes only |
| Individual `@react-aria/*` packages | Use the bundled `react-aria-components`; individual packages conflict with RAC's internal versions |

---

## 2. shadcn init — Tailwind v3 Path

### Critical version pin

The shadcn CLI has two major lines:

- **`shadcn@2.x`** (latest stable: `2.10.0`) — Tailwind v3, HSL CSS variables, `tailwind.config.js`-based, `tailwindcss-animate` plugin
- **`shadcn@4.x` / `shadcn@latest`** — Tailwind v4, OKLCH, `@tailwindcss/vite`, `tw-animate-css`

**Always invoke init as `npx shadcn@2.10.0 init`** for this project. The official shadcn docs state: "If you are using Tailwind v3, use `shadcn@2.3.0`" (that is a minimum; 2.10.0 is the current 2.x stable). Running `shadcn@latest init` emits v4 config.

### Init command for existing Vite project

```bash
cd frontend
npx shadcn@2.10.0 init
```

Prompt answers:
- Style: **New York** (more compact, better for a dashboard)
- Base color: **Zinc** (closest neutral dark — all tokens are overridden anyway)
- CSS variables: **yes**
- Global CSS file: `src/index.css`
- Tailwind config: `tailwind.config.js`
- Components path alias: `@/components`
- Utils path alias: `@/lib/utils`

This creates `components.json`, writes `src/lib/utils.ts`, updates `src/index.css` with a `:root` HSL block, and updates `tailwind.config.js`. After init, replace both files with the versions in Sections 3 and 4 (the init-generated versions are the base; our versions extend them with sidebar tokens and the custom purple theme).

### components.json (expected shape after init)

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.js",
    "css": "src/index.css",
    "baseColor": "zinc",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

Key fields:
- `"config": "tailwind.config.js"` — must be a non-empty string for shadcn 2.x (shadcn 4.x leaves this empty)
- `"rsc": false` — Vite SPA, not Next.js RSC
- `"iconLibrary": "lucide"` — lucide-react is already installed

### Path alias setup

**`tsconfig.json`** — add to `compilerOptions` (the current file has neither):

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

**`vite.config.ts`** — add `resolve.alias` (preserving existing `build.outDir`):

```typescript
import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

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

The `path.resolve(__dirname, ...)` call requires `@types/node` in devDependencies.

### cn() utility

Created at `src/lib/utils.ts` by `shadcn init`. Do not move it; `components.json` aliases.utils points here.

```typescript
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

---

## 3. tailwind.config.js — Full Replacement

Replace the entire current file (which uses raw hex tokens). The shadcn HSL CSS-variable color map supersedes the hex tokens. Retain the old named tokens (`bg-base`, `bg-surface`, etc.) temporarily if migration is phased; remove them once all components are ported.

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
        // shadcn CSS-variable tokens (Tailwind v3 HSL pattern — hsl() wrapper in JS, bare H S% L% in CSS)
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Sidebar tokens — required by shadcn/ui Sidebar component
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
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
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
```

Notes:
- `darkMode: ["class"]` — dark mode activated by `.dark` on `<html>`. Add `document.documentElement.classList.add("dark")` in `src/main.tsx` before `ReactDOM.createRoot(...)` since this app defaults to dark.
- The accordion keyframes reference `--radix-accordion-content-height`, a CSS custom property injected by the Radix Accordion component at render time. This is correct and intentional.
- `require("tailwindcss-animate")` is CommonJS require inside an ESM-style file (`export default`). This works in Vite's PostCSS/Tailwind processing context. If there is a module error, switch to: add `import tailwindcssAnimate from "tailwindcss-animate"` at top and use `plugins: [tailwindcssAnimate]`.
- The sidebar token block is needed because shadcn's `sidebar.tsx` references `bg-sidebar`, `text-sidebar-foreground`, etc.

---

## 4. src/index.css — Full Replacement (Purple Dark Theme)

Replace the current 3-line file. The values below map the existing hex design tokens (`#0f1117`, `#1a1d27`, `#3b82f6`) to shadcn HSL CSS variables, with `--primary` set to purple as specified in the milestone brief.

**Tailwind v3 HSL variable rule:** CSS variable values must be bare channel numbers (`H S% L%`), NOT wrapped in `hsl()`. The `hsl()` wrapper is applied only in `tailwind.config.js`. Example: `--background: 228 14% 8%` is correct; `--background: hsl(228 14% 8%)` is wrong for v3.

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Border radius scale */
    --radius: 0.5rem;

    /* Core surfaces — mapped from existing hex tokens */
    --background: 228 14% 8%;          /* #0f1117 (bg-base) */
    --foreground: 220 18% 88%;         /* #e2e6f0 (text-primary) */

    --card: 228 12% 13%;               /* #1a1d27 (bg-surface) */
    --card-foreground: 220 18% 88%;

    --popover: 228 12% 13%;
    --popover-foreground: 220 18% 88%;

    /* Primary — purple accent (replaces blue #3b82f6) */
    --primary: 270 70% 60%;            /* ~purple-500 */
    --primary-foreground: 0 0% 100%;

    /* Secondary — stripe surface */
    --secondary: 228 10% 18%;          /* #1e2130 (bg-stripe) */
    --secondary-foreground: 220 18% 88%;

    /* Muted */
    --muted: 228 10% 18%;
    --muted-foreground: 220 8% 43%;    /* #6b7280 (text-muted) */

    /* Accent — subtle hover highlight */
    --accent: 228 12% 20%;
    --accent-foreground: 220 18% 88%;

    /* Destructive */
    --destructive: 0 72% 60%;          /* #ef4444 */
    --destructive-foreground: 0 0% 100%;

    /* Border / input / ring */
    --border: 232 22% 23%;             /* #2d3148 */
    --input: 232 22% 23%;
    --ring: 270 70% 60%;               /* purple — matches primary */

    /* Sidebar tokens — required by shadcn/ui Sidebar component */
    --sidebar-background: 228 14% 8%;
    --sidebar-foreground: 220 18% 88%;
    --sidebar-primary: 270 70% 60%;
    --sidebar-primary-foreground: 0 0% 100%;
    --sidebar-accent: 228 12% 15%;
    --sidebar-accent-foreground: 220 18% 88%;
    --sidebar-border: 232 22% 23%;
    --sidebar-ring: 270 70% 60%;
  }

  /*
   * No .light block — this app is dark-mode-first/only.
   * dark mode is activated by `document.documentElement.classList.add("dark")` in main.tsx.
   * The :root values above ARE the dark theme.
   * If light mode support is added later, move dark values to .dark and define light values in :root.
   */

  * {
    @apply border-border;
  }

  body {
    @apply bg-background text-foreground;
  }
}
```

Token migration note: The current `tailwind.config.js` exposes `bg-base`, `bg-surface`, `bg-stripe`, `border`, `text-primary`, `text-muted`, `accent`, `destructive` as Tailwind utilities. Those map directly to the new tokens:

| Old utility | New utility |
|-------------|------------|
| `bg-base` | `bg-background` |
| `bg-surface` | `bg-card` |
| `bg-stripe` | `bg-secondary` |
| `border` color | `border-border` (via `@apply border-border` in base) |
| `text-primary` | `text-foreground` |
| `text-muted` | `text-muted-foreground` |
| `accent` (blue) | `bg-primary` (now purple) |
| `destructive` | `bg-destructive` |

Keep the old token definitions in `tailwind.config.js` during phase 1 to allow existing JSX to work until migrated, then remove them.

---

## 5. jolly-ui — Install Method and Coexistence

### What jolly-ui is NOT

jolly-ui is not an npm package. There is no `npm install jolly-ui`. It is a component registry served at `https://jollyui.dev/r`. Components are fetched and written to your project by the shadcn CLI's remote registry feature.

### Install method

```bash
# Method A: Using REGISTRY_URL env variable
REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add button

# Method B: Full URL
npx shadcn@latest add https://jollyui.dev/default/button
```

`shadcn@latest` (4.x) is fine for the `add` command — it only copies component source files, it does not touch `tailwind.config.js` or run `init`. The 2.x pin is only needed for `init`.

### Prerequisites

1. Complete `shadcn@2.10.0 init` first (jolly-ui docs: "Setup requires you doing the shadcn-ui set-up")
2. Have `react-aria-components` in `package.json` (installed in Section 2 setup)
3. The standard shadcn deps (`tailwindcss-animate`, `class-variance-authority`, `clsx`, `tailwind-merge`) are already present from Section 1

### Radix vs React Aria coexistence

No conflict. The two primitive layers target different components and manage independent DOM trees:
- Radix primitives: Dialog, DropdownMenu, Accordion, Tooltip, Tabs, Collapsible
- React Aria components: Table, Disclosure, some form primitives

They share the same CSS variable theme, `cn()` util, and `components.json`. Both write to `src/components/ui/`. No second `components.json` is needed.

### Tailwind v3 support confirmed

jolly-ui's installation page explicitly provides a `tailwind.config.js` config (not `@tailwindcss/vite`). The config structure matches the Tailwind v3 shadcn pattern. jolly-ui works on Tailwind v3.4. (HIGH confidence — documentation demonstrates v3 config directly.)

---

## 6. Component Source Map

| Component | Source | Install command | Notes |
|-----------|--------|----------------|-------|
| **Sidebar** | shadcn | `npx shadcn@2.10.0 add sidebar` | Installs `sidebar.tsx` (~600 lines, 25 sub-components) + `useSidebar` hook + `SidebarProvider`; requires the `sidebar.*` CSS variables and Tailwind color tokens from Sections 3-4 |
| **Button** | shadcn | `npx shadcn@2.10.0 add button` | Uses Radix `@radix-ui/react-slot`; apply CVA variants |
| **Badge** | shadcn | `npx shadcn@2.10.0 add badge` | Pure CSS, no Radix primitive; for audio/subtitle language badges |
| **Card** | shadcn | `npx shadcn@2.10.0 add card` | Pure CSS wrapper; for series/movie cards |
| **Table** | jolly-ui | `REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table` | React Aria Table — keyboard nav, row selection, sort announcements built in; superior to shadcn's plain `<table>` for the episode detail view. Beta status in jolly-ui. |
| **Tabs** | shadcn | `npx shadcn@2.10.0 add tabs` | Radix Tabs — already used in Bible Editor; keep consistent |
| **Accordion** | shadcn | `npx shadcn@2.10.0 add accordion` | Radix Accordion; uses `--radix-accordion-content-height` keyframes; for season-grouped episode view |
| **Collapsible** | shadcn | `npx shadcn@2.10.0 add collapsible` | Radix Collapsible; for individual season sections inside Accordion |
| **Tooltip** | shadcn | `npx shadcn@2.10.0 add tooltip` | Radix Tooltip; for sidebar nav item hover labels |
| **Skeleton** | shadcn | `npx shadcn@2.10.0 add skeleton` | Pure CSS pulse animation via `tailwindcss-animate` |
| **Sonner (Toast)** | shadcn | `npx shadcn@2.10.0 add sonner` | Wraps the `sonner` package; install `sonner` npm dep separately (Section 1) |
| **DropdownMenu** | shadcn | `npx shadcn@2.10.0 add dropdown-menu` | Radix DropdownMenu; for sidebar nav overflow menus |

Bulk shadcn install:

```bash
npx shadcn@2.10.0 add sidebar button badge card tabs accordion collapsible tooltip skeleton sonner dropdown-menu
```

Then add jolly-ui Table (after `react-aria-components` is installed):

```bash
REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table
```

---

## 7. React 19 Compatibility

### Radix UI

Full React 19 support shipped June 19, 2024 across all `@radix-ui/*` primitives. Peer dep range: `react: "^16.8 || ^17.0 || ^18.0 || ^19.0 || ^19.0.0-rc"`. No `--legacy-peer-deps` required. No breaking changes for consumers.

The one React 19 change affecting shadcn component source: `React.forwardRef` is deprecated (ref is now a plain prop). Shadcn components generated by `shadcn@2.x` still use `forwardRef` wrappers. These continue to work in React 19 — React 19 maintains full backward compatibility with `forwardRef`. You will see a deprecation warning in dev console if React DevTools is strict; suppress by updating the pattern per the shadcn v4 upgrade guide (`React.ComponentProps<...>` + direct ref prop). This is optional cleanup; it does not block runtime.

### react-aria-components

Version 1.18.0 (current stable). Peer dep range: `react: "^16.8.0 || ^17.0.0-rc.1 || ^18.0.0 || ^19.0.0-rc.1"`. This range, while showing `rc.1`, satisfies React 19.0 stable via semver (`^19.0.0-rc.1` matches anything `>=19.0.0-rc.1 <20.0.0`, which includes 19.0.0 stable). npm may display a peer dep warning due to the range literal, but the package functions correctly on React 19.0. Adobe has shipped React 19-specific fixes in recent releases (ref cleanup behavior, collection performance in transitions).

Do not use the nightly `3.0.0-nightly-*` builds — unstable API.

### sonner

sonner@2.0.7 peer deps: `react: "^18.0.0 || ^19.0.0 || ^19.0.0-rc"` — explicitly covers React 19.0 stable. No issues.

---

## 8. Setup Sequence (Ordered)

```bash
# 0. Working directory
cd /path/to/Trezarr/frontend

# 1. Install runtime deps
npm install \
  class-variance-authority@^0.7.1 \
  clsx@^2.1.1 \
  tailwind-merge@^3.6.0 \
  tailwindcss-animate@^1.0.7 \
  react-aria-components@^1.18.0 \
  sonner@^2.0.7

# 2. Install @types/node dev dep (for vite.config.ts path.resolve)
npm install -D @types/node

# 3. Edit tsconfig.json — add baseUrl and paths under compilerOptions (see Section 2)

# 4. Edit vite.config.ts — add resolve.alias block (see Section 2)

# 5. Run shadcn init on the Tailwind v3 line
npx shadcn@2.10.0 init
# Prompts: New York / Zinc / CSS variables: yes / src/index.css / tailwind.config.js / @/components / @/lib/utils

# 6. Replace tailwind.config.js with the full version from Section 3
#    (adds sidebar tokens and ensures module format is correct)

# 7. Replace src/index.css with the purple dark theme from Section 4
#    (the init-generated block uses zinc defaults; replace with Trezarr's purple tokens)

# 8. Add dark class to <html> in src/main.tsx (before ReactDOM.createRoot):
#    document.documentElement.classList.add("dark")

# 9. Add shadcn components (bulk)
npx shadcn@2.10.0 add sidebar button badge card tabs accordion collapsible tooltip skeleton sonner dropdown-menu

# 10. Add jolly-ui Table
REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table

# 11. Verify build
npm run build
# Expect: build completes, trezarr/web/static/ populated
```

---

## 9. What NOT to Add

| Package / Action | Reason |
|-----------------|--------|
| `tailwindcss@^4.x` | Breaks existing v3 config; locked out of scope |
| `@tailwindcss/vite` | Tailwind v4 Vite plugin — incompatible with v3 |
| `tw-animate-css` | Tailwind v4 animation replacement; use `tailwindcss-animate` on v3 |
| `npx shadcn@latest init` | 4.x emits v4 config; use `shadcn@2.10.0 init` |
| Any `jolly-ui` npm package | Does not exist; all jolly-ui is copy-paste via registry |
| `@radix-ui/react-icons` | Redundant; lucide-react is already present |
| `vaul` | Not used in this milestone's sidebar design |
| `cmdk` | Command palette not in v1.1 scope |
| `recharts` | Charts not in v1.1 scope |
| `framer-motion` | Not needed; shadcn v3 uses Tailwind keyframes only |
| Individual `@react-aria/*` packages | Use the bundled `react-aria-components`; individual packages conflict with RAC internal versions |
| A second `components.json` | jolly-ui shares the existing one |

---

## 10. FastAPI / Vite Integration Notes

The existing `vite.config.ts` builds to `../trezarr/web/static` with `emptyOutDir: true`, served by FastAPI's `SPAStaticFiles` mount. This setup is unaffected by the shadcn additions:
- The `@/` alias is a build-time TypeScript/Vite alias — resolves before bundling, zero runtime footprint in static output
- `npm run build` output structure does not change (Vite still produces `index.html` + hashed asset bundles)
- The FastAPI `StaticFiles` mount and SPA deep-link fallback do not need updates

---

## Sources

| Source | Confidence | What it verified |
|--------|-----------|-----------------|
| npm registry live queries (2026-06-03) | HIGH | Current versions: CVA 0.7.1, clsx 2.1.1, tailwind-merge 3.6.0, tailwindcss-animate 1.0.7, react-aria-components 1.18.0, sonner 2.0.7; all @radix-ui/* versions; peer dep ranges |
| `github.com/shadcn-ui/ui` — `packages/shadcn/src/utils/templates.ts` (raw, read directly 2026-06-03) | HIGH | Exact `TAILWIND_CONFIG_WITH_VARIABLES` template (HSL color map, accordion keyframes, borderRadius), `UTILS` (`cn()` function) — these are the v3 templates `shadcn init` writes |
| `ui.shadcn.com/docs/tailwind-v4` | HIGH | Confirms v3 projects still supported; v3 uses `tailwindcss-animate`, v4 uses `tw-animate-css`; "use `shadcn@2.3.0`" minimum for Tailwind v3 |
| `jollyui.dev/docs/installation` | HIGH | jolly-ui is copy-paste registry (not npm); uses `REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add`; requires shadcn init first; lists same npm deps as shadcn; Tailwind v3 config shown directly |
| `jollyui.dev/docs/components/table`, `jollyui.dev/docs` (component index) | MEDIUM | Table component exists (beta, uses React Aria); full component list confirmed |
| `radix-ui.com/primitives/docs/overview/releases` (fetched 2026-06-03) | HIGH | Full React 19 compatibility shipped June 2024; peer deps cover `^19.0` |
| `github.com/adobe/react-spectrum` issues #6445, #9267; npm dist tag | MEDIUM | react-aria-components 1.18.0 runs on React 19; peer dep range `^19.0.0-rc.1` satisfies 19.0 stable |
| Context7 `/shadcn-ui/ui` — sidebar component | HIGH | `npx shadcn@latest add sidebar`; sidebar CSS variable names (`--sidebar-background`, `--sidebar-primary`, etc.); `SidebarProvider` usage pattern |
