# Phase 11: shadcn Foundation & Purple Theme — Pattern Map

**Mapped:** 2026-06-03
**Files analyzed:** 9 (6 modified + 3 net-new hand-written + 1 vendor tree)
**Analogs found:** 4 / 9 (5 files are net-new config with no codebase analog — RESEARCH.md is the source of truth for those)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `frontend/vite.config.ts` | build-config | transform | itself (current state documented below) | self-modification |
| `frontend/tsconfig.json` | build-config | transform | itself (current state documented below) | self-modification |
| `frontend/tailwind.config.js` | styling-tokens | transform | itself (current state documented below) | self-modification (wholesale replace) |
| `frontend/src/index.css` | styling-tokens | transform | itself (current state documented below) | self-modification (wholesale replace) |
| `frontend/index.html` | entrypoint | request-response | itself (current state documented below) | self-modification (two-line edit) |
| `frontend/package.json` | build-config | — | itself (current state documented below) | self-modification (dep additions) |
| `frontend/.npmrc` | build-config | — | none — net-new, no in-repo analog | no analog |
| `frontend/components.json` | build-config | — | none — net-new, CLI-generated | no analog |
| `frontend/src/lib/utils.ts` | utility | transform | none — net-new, CLI-generated | no analog |
| `frontend/src/components/ui/*` | vendor-primitive | — | none — vendor code, CLI-generated | vendor (do not hand-edit) |

---

## Current State Snapshots

Each modified file's **actual current content** is recorded here so the executor edits real
content, not assumptions. These were read directly from the working tree on 2026-06-03.

### `frontend/vite.config.ts` — current state (lines 1–12)

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build the SPA directly into trezarr/web/static so FastAPI can serve it
// via StaticFiles(html=True) mounted as the last route (Pattern 6).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../trezarr/web/static",
    emptyOutDir: true,
  },
});
```

**Observations:** No `path` import, no `resolve.alias`, no `base` field. The comment and the
`build` block are load-bearing and must survive the edit. `base` must remain absent.

---

### `frontend/tsconfig.json` — current state (lines 1–25)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",

    /* Strict mode */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
```

**Observations:** No `baseUrl`, no `paths`. All other options are load-bearing (strict mode,
`noUnusedLocals`, `noUnusedParameters` are enforced and shadcn vendor output must satisfy them
— which it does). `"include": ["src"]` must not change.

---

### `frontend/tailwind.config.js` — current state (lines 1–21)

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 07-UI-SPEC.md §Color — exact hex tokens
        "bg-base":      "#0f1117",
        "bg-surface":   "#1a1d27",
        "bg-stripe":    "#1e2130",
        border:         "#2d3148",      // COLLIDES with shadcn — replace wholesale
        "text-primary": "#e2e6f0",
        "text-muted":   "#6b7280",
        accent:         "#3b82f6",      // COLLIDES with shadcn — replace wholesale
        destructive:    "#ef4444",      // COLLIDES with shadcn — replace wholesale
      },
    },
  },
  plugins: [],
};
```

**Observations:** Eight hex tokens. Three collide with shadcn keys (`border`, `accent`,
`destructive`) and are replaced wholesale. Five bridge tokens (`bg-base`, `bg-surface`,
`bg-stripe`, `text-primary`, `text-muted`) survive into the new config unchanged. No
`darkMode` key, no `plugins`, no `container` block, no `borderRadius`, no `keyframes`.
This file is a **wholesale replacement** — do not attempt a partial merge.

---

### `frontend/src/index.css` — current state (lines 1–3)

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Observations:** Bare three-line file. No CSS variables, no `@layer base`, no `:root`
block. This file is a **wholesale replacement** — the new content prepends these three
directives and adds the `@layer base { :root { ... } }` block below them.

---

### `frontend/index.html` — current state (lines 1–24)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Trezarr</title>
    <style>
      html,
      body {
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
        margin: 0;
        padding: 0;
        background-color: #0f1117;
        color: #e2e6f0;
      }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Observations:** Two surgical edits required:
1. `<html lang="en">` → `<html lang="en" class="dark">`
2. `background-color: #0f1117` → `background-color: hsl(270, 24%, 7%)`

The `color: #e2e6f0` value may optionally be updated to `hsl(270, 10%, 90%)` but is
not required for the D-09 gate. Font stack, `<title>`, script tag, and all other
content are unchanged.

---

### `frontend/package.json` — current state (lines 1–27)

```json
{
  "name": "trezarr-ui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "lucide-react": "^0.511.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^6.30.1"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.4.1",
    "autoprefixer": "^10.4.21",
    "postcss": "^8.5.3",
    "tailwindcss": "^3.4.17",
    "typescript": "~5.7.2",
    "vite": "^7.0.0"
  }
}
```

**Observations:** `build` script is `tsc -b && vite build` — must not change. Six runtime
deps and one dev dep are added via `npm install` commands (Steps 2–3 in RESEARCH.md) — the
lock file is updated automatically. `lucide-react`, `react`, `react-dom`, `react-router-dom`
are unchanged.

---

## Pattern Assignments

### `frontend/vite.config.ts` (build-config, self-modification)

**No external analog.** The file is self-referential — add to existing content, preserve
load-bearing constraints. The full replacement is specified verbatim in RESEARCH.md Step 4.

**What changes:** Add `import path from "path"` at the top; add `resolve: { alias: { "@": path.resolve(__dirname, "./src") } }` block inside `defineConfig`.

**What must NOT change:** No `base` field added. `build.outDir` and `build.emptyOutDir`
stay exactly as-is. The existing comment about FastAPI StaticFiles is preserved.

**Exact replacement from RESEARCH.md Step 4:**

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

**Import style note:** `import path from "path"` uses `"path"` (Node built-in string),
not a relative path. `@types/node` in devDependencies provides the type. The existing
import of `defineConfig` and `react` stay on their own lines. Import order: `path` first,
then `defineConfig`, then `react`.

---

### `frontend/tsconfig.json` (build-config, self-modification)

**No external analog.** Add two keys to `compilerOptions`. Both `vite.config.ts` and
`tsconfig.json` must be updated in the same commit (Pitfall 6).

**What changes:** Add `"baseUrl": "."` and `"paths": { "@/*": ["./src/*"] }` at the end
of `compilerOptions`, before the closing `}`. All existing options are preserved verbatim
(especially `strict`, `noUnusedLocals`, `noUnusedParameters`).

**Exact final form from RESEARCH.md Step 5:**

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

Note: inline comments (`/* Bundler mode */`, `/* Strict mode */`) in the current file are
JSON-illegal in strict parsers but work in TypeScript's tsconfig parser — they may be
preserved or dropped; either is fine.

---

### `frontend/tailwind.config.js` (styling-tokens, wholesale replacement)

**No external analog.** No prior shadcn project exists in this repo. The source of truth
is RESEARCH.md Step 7 verbatim.

**Critical rules (all from RESEARCH.md):**
- `darkMode: ["class"]` is required at the top level (Pitfall 4 — without it, `.dark` selector does nothing).
- Bridge tokens (`bg-base`, `bg-surface`, `bg-stripe`, `text-primary`, `text-muted`) survive as literal hex strings — they do NOT use CSS variables.
- Colliding keys (`border`, `accent`, `destructive`) from the old config are removed and replaced with `hsl(var(--x))` entries.
- CSS variable values in the `hsl(var(--x))` strings are bare — the `hsl()` wrapper lives only here, never in `index.css` (D-02 / Pitfall 1).
- `plugins: [require("tailwindcss-animate")]` required for accordion/tooltip/dialog animation classes (Pitfall 5).
- ESM/CJS fallback: if `require("tailwindcss-animate")` throws a module error at build time, switch to `import tailwindcssAnimate from "tailwindcss-animate"` at top and `plugins: [tailwindcssAnimate]`.

**Exact replacement from RESEARCH.md Step 7:** See RESEARCH.md lines 343–441 (the full
`tailwind.config.js` block). Do not summarize — copy verbatim.

---

### `frontend/src/index.css` (styling-tokens, wholesale replacement)

**No external analog.** The source of truth is RESEARCH.md Step 8 verbatim.

**Critical rules:**
- Three `@tailwind` directives come FIRST, before `@layer base`.
- ALL CSS variable values are bare `H S% L%` channel triples — NO `hsl()` wrapper (D-02 / Pitfall 1). Violating this silently breaks `bg-primary/50` with no compile error.
- Purple anchor: `--primary: 270 70% 60%` (D-01). All tokens are starting values; tune at D-09 gate.
- No `.dark { }` block needed — Trezarr is dark-only; the `:root` block IS the dark theme, activated by `class="dark"` on `<html>`.
- `* { @apply border-border; }` and `body { @apply bg-background text-foreground; }` go inside `@layer base`.

**Exact replacement from RESEARCH.md Step 8:** See RESEARCH.md lines 450–532 (the full
`src/index.css` block). Do not summarize — copy verbatim.

---

### `frontend/index.html` (entrypoint, two surgical edits)

**No external analog needed.** Two targeted edits only.

**Edit 1 — line 2:** `<html lang="en">` → `<html lang="en" class="dark">`

**Edit 2 — line 15:** `background-color: #0f1117;` → `background-color: hsl(270, 24%, 7%);`

Everything else in the file is untouched. The font stack, `color: #e2e6f0`, `<title>`,
`<script>` tag, and `<div id="root">` are all preserved as-is.

**Why both edits are required together:** `darkMode: ["class"]` in tailwind.config.js only
applies dark-mode CSS variables when the `<html>` element has `class="dark"`. The inline
`background-color` update ensures the page root reads purple before the SPA hydrates
(prevents a flash of the old blue-black `#0f1117` background).

---

### `frontend/package.json` (build-config, dep additions via npm install)

**No hand-editing required.** Dependencies are added via the `npm install` commands in
RESEARCH.md Steps 2–3. The lock file updates automatically.

**Commands that modify this file (from RESEARCH.md Steps 2–3):**

```bash
npm install \
  class-variance-authority@^0.7.1 \
  clsx@^2.1.1 \
  tailwind-merge@^3.6.0 \
  tailwindcss-animate@^1.0.7 \
  react-aria-components@^1.18.0 \
  sonner@^2.0.7

npm install -D @types/node
```

**After install, `dependencies` gains:** `class-variance-authority`, `clsx`,
`tailwind-merge`, `tailwindcss-animate`, `react-aria-components`, `sonner`.
**After install, `devDependencies` gains:** `@types/node`.
**Unchanged:** `build` script (`tsc -b && vite build`), all existing deps, `"type": "module"`.

Radix UI primitives (`@radix-ui/*`) are NOT pre-installed — they are pulled automatically
by the shadcn CLI `add` commands.

---

### `frontend/.npmrc` (build-config, net-new)

**No in-repo analog exists.** This file does not exist yet in the repo.

**Source of truth:** RESEARCH.md Step 1.

**Complete file content:**

```
# legacy-peer-deps=true is required because cmdk and react-day-picker
# (pulled as transitive deps by some shadcn components) declare peer
# dependency ranges that exclude React 19.0 stable.
# Using --force is NOT a safe substitute — it can cause silent runtime breakage.
# See: Phase 11 RESEARCH.md Pitfall 7.
legacy-peer-deps=true
```

**Timing constraint (D-07 / Pitfall 7):** This file MUST be created before any `npm install`
or `npx shadcn` invocation. Creating it after the fact does not retroactively fix an
`ERESOLVE` failure.

---

### `frontend/components.json` (build-config, CLI-generated)

**No in-repo analog exists.** This file does not exist yet and is written by
`npx shadcn@2.10.0 init`.

**Source of truth:** RESEARCH.md Step 6 (init prompt answers).

**Expected content after init with prompt answers from RESEARCH.md Step 6:**

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

The `style: "new-york"` and `baseColor: "zinc"` reflect the init prompt answers. The
`cssVariables: true` is required — without it the CLI writes inline hex values instead
of CSS variable references in the component source files, which defeats the theme system.

**Do NOT hand-edit this file** after the CLI generates it.

---

### `frontend/src/lib/utils.ts` (utility, CLI-generated)

**No in-repo analog exists.** This file does not exist yet and is written by
`npx shadcn@2.10.0 init`.

**Source of truth:** RESEARCH.md §Standard Stack (`cn()` function) + STACK.md §cn() source.

**Expected content after init:**

```typescript
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

This is the canonical shadcn `cn()` pattern: `clsx` handles conditional/array inputs,
`tailwind-merge` deduplicates conflicting Tailwind utility strings (e.g., `bg-red-500`
overriding `bg-blue-500` correctly). Every shadcn component and all downstream Phase 12+
hand-written components import `cn` from `@/lib/utils`.

**Do NOT hand-edit this file** after the CLI generates it.

---

### `frontend/src/components/ui/*` (vendor-primitive, CLI-generated)

**No analog mapping needed. This is vendor code.**

These files are written entirely by two CLI commands (RESEARCH.md Steps 10–11):

```bash
# Step 10 — shadcn official components
npx shadcn@2.10.0 add sidebar button badge card tabs accordion collapsible \
    tooltip skeleton sonner dropdown-menu

# Step 11 — jolly-ui Table (React Aria)
REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table
```

**Vendor policy (D-07):** Never hand-edit any file under `src/components/ui/`. The CLI
is the only permitted writer. Hand edits diverge from the shadcn baseline and break
future CLI upgrades.

**Files that will appear after the CLI runs:**

| File | Source CLI | Used in Phase |
|------|-----------|---------------|
| `src/components/ui/sidebar.tsx` | shadcn@2.10.0 | Phase 12 |
| `src/components/ui/button.tsx` | shadcn@2.10.0 | Phase 11 UAT + Phase 12+ |
| `src/components/ui/badge.tsx` | shadcn@2.10.0 | Phase 14 |
| `src/components/ui/card.tsx` | shadcn@2.10.0 | Phase 12+ |
| `src/components/ui/tabs.tsx` | shadcn@2.10.0 | Phase 15 |
| `src/components/ui/accordion.tsx` | shadcn@2.10.0 | Phase 14 |
| `src/components/ui/collapsible.tsx` | shadcn@2.10.0 | Phase 14 |
| `src/components/ui/tooltip.tsx` | shadcn@2.10.0 | Phase 14 |
| `src/components/ui/skeleton.tsx` | shadcn@2.10.0 | Phase 14 |
| `src/components/ui/sonner.tsx` | shadcn@2.10.0 | Phase 12+ |
| `src/components/ui/dropdown-menu.tsx` | shadcn@2.10.0 | Phase 12+ |
| `src/components/ui/table.tsx` | jolly-ui via shadcn@latest | Phase 14 |

**jolly-ui table re-vet gate (blocking):** Before running Step 11, run
`REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest view table 2>/dev/null` and
scan for: `fetch(`, `XMLHttpRequest`, `navigator.sendBeacon`, `process.env`, `eval(`,
`Function(`, dynamic imports from external URLs. If any flag appears, halt and present
to developer for explicit approval. (From 11-UI-SPEC.md §Registry Safety.)

---

## Shared Patterns

### Channel-Triple CSS Variable Format (D-02)

**Applies to:** `frontend/src/index.css` exclusively (the only file that declares CSS variables).

**Rule:** CSS variable values are bare `H S% L%` triples. The `hsl()` wrapper lives
ONLY in `tailwind.config.js`. This is the single most important invariant in Phase 11 —
violation silently breaks `bg-primary/50` with no compile error.

```
CORRECT in index.css:    --primary: 270 70% 60%;
CORRECT in tailwind:     primary: { DEFAULT: "hsl(var(--primary))" }
WRONG in index.css:      --primary: hsl(270 70% 60%);   /* breaks opacity modifiers */
```

### `@/` Alias Must Be Wired in Both Configs (D-08 / Pitfall 6)

**Applies to:** `frontend/vite.config.ts` AND `frontend/tsconfig.json` — always updated
in the same commit.

```
vite.config.ts:  resolve: { alias: { "@": path.resolve(__dirname, "./src") } }
tsconfig.json:   "baseUrl": ".", "paths": { "@/*": ["./src/*"] }
```

Partial setup causes asymmetric failures (tsc red, vite green, or vice versa).

### `darkMode: ["class"]` + `class="dark"` Must Both Be Present (Pitfall 4)

**Applies to:** `frontend/tailwind.config.js` (top-level `darkMode` key) AND
`frontend/index.html` (`<html>` element). Always committed together.

```
tailwind.config.js:  darkMode: ["class"],
index.html:          <html lang="en" class="dark">
```

Missing either causes all shadcn components to render in light mode.

### `.npmrc` Before Any npm/npx Command (D-07 / Pitfall 7)

**Applies to:** `frontend/.npmrc` — must be created as Step 1, before `npm install`.

```
legacy-peer-deps=true
```

### Bridge Token Preservation (D-05)

**Applies to:** `frontend/tailwind.config.js` `extend.colors` block.

Five keys survive as literal hex strings alongside the new CSS-variable-backed shadcn tokens.
They do NOT collide with shadcn's key namespace:

```javascript
"bg-base":      "#0f1117",
"bg-surface":   "#1a1d27",
"bg-stripe":    "#1e2130",
"text-primary": "#e2e6f0",
"text-muted":   "#6b7280",
```

Do NOT convert these to CSS variables yet. They are removed only in Phase 15.

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `frontend/.npmrc` | build-config | Net-new file; no `.npmrc` exists anywhere in this repo |
| `frontend/components.json` | build-config | Net-new, CLI-generated; no prior shadcn project in repo |
| `frontend/src/lib/utils.ts` | utility | Net-new, CLI-generated; no `lib/` directory or `cn()` exists yet |
| `frontend/src/components/ui/*` | vendor-primitive | Net-new, CLI-generated vendor code; treated as external vendor |

For all four, **RESEARCH.md is the source of truth** — the exact-edit spec and command
sequence in Steps 1–11 provides complete, verified instructions that substitute for
in-repo analogs.

---

## Metadata

**Analog search scope:** `frontend/` root and `frontend/src/` tree
**Files scanned:** 25 (full frontend tree)
**Files with no prior state (net-new):** 4 — `.npmrc`, `components.json`, `src/lib/utils.ts`, `src/components/ui/*`
**Files with prior state (modified):** 6 — `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `src/index.css`, `index.html`, `package.json`
**Pattern extraction date:** 2026-06-03
**Source of truth for net-new files:** `.planning/phases/11-shadcn-foundation-purple-theme/11-RESEARCH.md`
