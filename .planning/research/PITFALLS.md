# Pitfalls: shadcn/ui + jolly-ui Migration onto Existing Tailwind-v3 / React-19 / Vite / FastAPI Stack

**Domain:** UI reskin of a shipped self-hosted subtitle-translation service  
**Milestone:** v1.1 — big-bang shadcn/jolly-ui dashboard  
**Researched:** 2026-06-03  
**Confidence:** HIGH for token/alias/dark-mode pitfalls (verified against shadcn docs, GitHub issues); MEDIUM for jolly-ui/react-aria specifics (limited public bug reports; library is actively maintained but smaller surface); HIGH for FastAPI/Docker pitfalls (codebase-verified); MEDIUM for backend episode-join pitfalls (Sonarr API field behavior confirmed via community reports, not official docs).

---

## Summary

These pitfalls are organized by the six topic areas in the research brief. Each entry: what breaks, warning signs, prevention strategy, owning phase.

---

## Part 1: Theme / Token Migration

### Pitfall 1-A: The HSL "channel triple" format — the #1 silent breakage

**What breaks:**  
shadcn/ui's Tailwind v3 integration defines CSS custom properties as bare HSL channel triples, not full color values:

```css
/* CORRECT for Tailwind v3 shadcn */
:root {
  --primary: 222.2 47.4% 11.2%;
  --background: 0 0% 100%;
}
```

The `hsl()` wrapper is applied at *usage* time in the Tailwind config:

```js
colors: {
  primary: {
    DEFAULT: "hsl(var(--primary))",
    foreground: "hsl(var(--primary-foreground))",
  },
}
```

If you write a full hex or `hsl(...)` value directly inside the CSS variable — which feels natural when migrating from the existing `#0f1117` hex tokens — Tailwind's opacity modifier (`bg-primary/50`) silently breaks. The class renders without opacity support and the modifier is quietly ignored rather than erroring. Components look fine at full opacity but modifiers produce `hsl(hsl(222 47% 11%) / 50%)` which browsers discard.

**Warning signs:**  
- Opacity modifiers like `bg-primary/30` or `text-foreground/70` render at full opacity  
- Working in Chromium DevTools shows the computed value is invalid but no console error  
- Only discovered when a component intentionally uses opacity variants (overlays, ghost buttons, disabled states)

**Prevention:**  
Keep all shadcn CSS variables as bare `H S% L%` triples. Convert existing hex tokens with a one-time script (many online converters; or use the shadcn theme generator at ui.shadcn.com). Do NOT write `--background: #0f1117` or `--background: hsl(222 47% 11%)` — strip the wrapper.

**Owning phase:** Foundation / theme setup phase (first phase of v1.1). Gate-check: after CSS variable authoring, verify one opacity modifier renders correctly in the browser before proceeding.

---

### Pitfall 1-B: Namespace collisions between existing custom tokens and shadcn tokens

**What breaks:**  
The current `tailwind.config.js` extends `colors` with keys that overlap shadcn's semantic namespace:

| Existing key | shadcn key | Collision |
|---|---|---|
| `border: "#2d3148"` | `border: "hsl(var(--border))"` | YES — `border-border` class semantics change |
| `accent: "#3b82f6"` | `accent: { DEFAULT: "hsl(var(--accent))" }` | YES — `bg-accent` now means shadcn's accent, not blue |
| `destructive: "#ef4444"` | `destructive: { DEFAULT: "hsl(var(--destructive))" }` | YES — existing red hex is replaced |
| `text-primary: "#e2e6f0"` | `foreground` (not `text-primary`) | No direct collision, but BibleEditor uses `text-text-primary` which Tailwind generates from the `text-primary` key |

When the shadcn color block is merged into `theme.extend.colors`, Tailwind's `extend` merges objects one level deep. The `accent` key becomes the shadcn object `{ DEFAULT, foreground }`, silently replacing the simple hex string. Every existing `bg-accent` class in ~13 components continues to compile — it now maps to `hsl(var(--accent))` which is shadcn's neutral/muted accent (purple in the target theme), not the blue `#3b82f6` that was there before. If the purple theme `--accent` is set correctly, the color will visually be correct, but the old semantic is gone.

The `border` key collision is more subtle: the existing config has `border: "#2d3148"` as a simple string. shadcn's canonical config also puts `border` at the top level: `border: "hsl(var(--border))"`. When merged, whichever object wins determines whether `border-border` (shadcn's utility class pattern for its border color) resolves correctly. With `extend`, the shadcn value replaces the hex. This is generally what you want, but any existing raw class like `border-[#2d3148]` still works while `border-border` is now the shadcn variable. Mixed usage creates dual sources of truth.

**Warning signs:**  
- Button hover states showing wrong shade (the old `#3b82f6` blue replaced by purple HSL accent)  
- `border-border` in shadcn components rendering as a different color than `border-[#2d3148]` in old components  
- TypeScript LSP showing `accent` has type `string` in one context and `{ DEFAULT, foreground }` in another

**Prevention:**  
1. Audit which existing keys collide (`border`, `accent`, `destructive`). Before merging, rename the old custom hex tokens to something non-colliding: `border-default` → `trezarr-border`, etc., or just delete them (since the migration replaces all pages).  
2. For a big-bang migration the cleaner approach: remove the entire old `theme.extend.colors` block in one commit when the migration starts, and replace it wholesale with the shadcn color block + the purple theme HSL variables. Old hex classes (`border-[#2d3148]`) still compile via arbitrary values; old semantic classes (`bg-accent`) now use the shadcn variable. The mix-match period is bounded to the migration sprint.  
3. The `text-primary` and `text-muted` keys (not in shadcn's namespace) survive collision-free but generate `text-text-primary` / `text-text-muted` classes — keep or rename based on whether you're migrating those tokens to `text-foreground` / `text-muted-foreground`.

**Owning phase:** Foundation / theme setup phase. The rename/delete decision must be made before any pages are migrated.

---

### Pitfall 1-C: Dark mode wiring — `darkMode: ["class"]` missing or wrong scope

**What breaks:**  
shadcn's dark mode mechanism requires `darkMode: ["class"]` in `tailwind.config.js`. The current config has no `darkMode` key (the default is `"media"` — OS preference). Without the class strategy, the `.dark` selector on `<html>` or `<body>` that shadcn components expect does nothing; all CSS variables in `.dark {}` are never applied.

Since the target design is dark-only, this pitfall manifests differently: if you hard-code `class="dark"` on `<html>` and don't add `darkMode: ["class"]`, Tailwind's `dark:` prefixed utilities (e.g. `dark:bg-muted`) in shadcn component source will be purged because the JIT sees no variant trigger.

**Warning signs:**  
- shadcn components render with light-mode background colors (white/near-white) despite the dark CSS variables being defined  
- `dark:` utility classes present in component source but absent from the compiled CSS bundle  
- Inspecting `:root` in DevTools shows the light-mode values; `.dark` block has no effect

**Prevention:**  
Add `darkMode: ["class"]` to `tailwind.config.js` as part of the foundation phase. In `main.tsx` or `App.tsx`, hard-code `document.documentElement.classList.add("dark")` at startup (since the app is dark-only). Do not rely on `prefers-color-scheme` — Trezarr is always dark.

**Owning phase:** Foundation / theme setup phase.

---

### Pitfall 1-D: `tailwindcss-animate` must be added to `plugins`; its classes will be purged without it

**What breaks:**  
shadcn components use animation classes like `animate-in`, `animate-out`, `fade-in-0`, `zoom-in-95`, etc. These are generated by the `tailwindcss-animate` plugin. Without the plugin in `tailwind.config.js`:

```js
plugins: [require("tailwindcss-animate")],
```

the classes are undefined, Tailwind's JIT does not know them, and they are silently absent from the production bundle. Components that use Dialog, Tooltip, Popover, DropdownMenu, or Command will have instant snap-open behavior instead of the configured transitions — no error, just broken animations.

**Warning signs:**  
- Dialog/Popover/Tooltip open/close with no animation in production build  
- Classes like `animate-in`, `data-[state=open]:fade-in-0` present in component source but absent from `dist/assets/*.css`  
- Works in dev (Vite dev server may include more) but breaks in `npm run build`

**Prevention:**  
Install `tailwindcss-animate` (`npm install tailwindcss-animate`) and add it to `plugins` in the same commit that installs shadcn. Do NOT use the Tailwind v4 equivalent (`tw-animate-css`) — this project is on Tailwind v3.4 and the v4 `@import` syntax does not apply.

**Owning phase:** Foundation / theme setup phase. Verify by running `npm run build` and grepping `dist/assets/*.css` for `animate-in`.

---

### Pitfall 1-E: Content glob misses leave shadcn component classes purged in production

**What breaks:**  
The current `tailwind.config.js` content glob is:
```js
content: ["./index.html", "./src/**/*.{ts,tsx}"]
```

After installing shadcn, components land in `src/components/ui/` — which is covered. BUT if the shadcn CLI generates any files outside `src/` (e.g. `lib/utils.ts`, `hooks/`, or a non-standard `components.json`-driven path), those paths need to be included. More commonly: if you add any component files in a non-standard location (e.g. the jolly-ui components at a different path), their classes will be purged.

The riskier version: if you decide to co-locate shadcn's generated `cn()` utility at `src/lib/utils.ts` (standard) it is covered; if placed elsewhere it is not.

**Warning signs:**  
- A component looks correct in `vite dev` but is visually broken after `npm run build`  
- Specific utility classes present in source but absent from the built CSS  
- Classes that appear only in dynamically-constructed strings (e.g. CVA variant maps) are silently purged

**Prevention:**  
Keep all generated files within `src/`. The standard shadcn layout (`src/components/ui/`, `src/lib/utils.ts`) is already covered by the glob. For CVA variant strings: never construct class names via string concatenation (`"bg-" + variant`) — write full class names in the variant config so PurgeCSS sees them as literals. After each build, spot-check `dist/assets/*.css` for key shadcn classes.

**Owning phase:** Foundation / theme setup phase. The glob is safe if the standard layout is used; add a build-verify step to the phase acceptance criteria.

---

## Part 2: Vite + Path Alias

### Pitfall 2-A: `@/` alias must be in BOTH `tsconfig.json` AND `vite.config.ts` — partial setup causes build-only failures

**What breaks:**  
shadcn generates imports like `import { cn } from "@/lib/utils"`. The `@/` alias requires two independent registrations:

1. `tsconfig.json` `compilerOptions.paths` — tells TypeScript's type checker where to resolve  
2. `vite.config.ts` `resolve.alias` — tells Vite's bundler where to resolve at build time

The current `tsconfig.json` has NO `paths` or `baseUrl`. The current `vite.config.ts` has NO `resolve.alias`. The shadcn CLI will attempt to set this up during `npx shadcn@latest init`, but only if it can detect the framework correctly.

**The trap:** TypeScript type-checking (`tsc -b` in the build script) can pass with `skipLibCheck: true` and bare module resolution even without the alias, because TypeScript in `moduleResolution: bundler` mode delegates resolution to the bundler. The build then fails at the Vite bundle step with `[vite] Cannot find module "@/lib/utils"`. Alternatively: alias is set in `tsconfig.json` only → TypeScript passes but `vite build` fails. Alias set in `vite.config.ts` only → Vite builds but TypeScript IDE errors appear everywhere (false red underlines, broken go-to-definition).

**Warning signs:**  
- `Cannot resolve module "@/..."` errors only appear on `npm run build`, not `vite dev`  
- VSCode shows red underlines for `@/` imports but the dev server works  
- `npx shadcn@latest init` completes but the first `npx shadcn@latest add button` fails to compile

**Prevention:**  
Add both simultaneously:

```ts
// vite.config.ts
import path from "path"
resolve: {
  alias: { "@": path.resolve(__dirname, "./src") }
}
```

```json
// tsconfig.json compilerOptions
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

Note: the current tsconfig uses `"moduleResolution": "bundler"` which does NOT automatically resolve `paths` entries at runtime — the Vite alias is still required for the bundler step. Both entries are mandatory.

**Owning phase:** Foundation / theme setup phase, first commit. This is a prerequisite for any component that imports from `@/lib/utils`.

---

## Part 3: React 19 Specifics

### Pitfall 3-A: `--legacy-peer-deps` required at install time; `cmdk` and `react-day-picker` are known offenders

**What breaks:**  
Radix UI (used by shadcn components) and several shadcn transitive deps have peer dependency declarations of `"react": "^16.8 || ^17.0 || ^18.0"` — not yet updated to `^19.0`. npm's strict resolver will `ERESOLVE` on install.

Confirmed problem packages as of mid-2026:
- `cmdk` < 1.0.4: the Command/search component; shadcn CLI installs `cmdk@1.0.0` which has React 19 type errors  
- `react-day-picker@8.x`: Calendar component peer dep conflict  
- Some `@radix-ui/react-*` individual packages still declare `^18.0` maximum

jolly-ui is built on `react-aria-components` (Adobe React Spectrum). React Aria has a known open issue (#9267) where peerDependencies are pinned to `^19.0.0-rc.1` rather than `^19.0.0`, causing npm warnings even with the stable React 19 release.

**Warning signs:**  
- `npm error ERESOLVE unable to resolve dependency tree` on `npx shadcn@latest add <component>`  
- React Aria peer dep warnings mentioning `^19.0.0-rc.1`  
- `cmdk` type errors on `CommandItem` children prop

**Prevention:**  
1. Install shadcn components with `--legacy-peer-deps` flag. Add this to the project's `.npmrc` (`legacy-peer-deps=true`) so it applies automatically to all subsequent `npx shadcn@latest add` calls during the migration sprint.  
2. Pin `cmdk` to `>=1.0.4` explicitly in `package.json` overrides or install it directly: `npm install cmdk@latest`.  
3. react-aria-components peer dep warnings are cosmetic if React 19 stable is installed — the library functions correctly; treat as noise.  
4. Do NOT use `--force` as a blanket solution — it can produce subtle runtime breakage; `--legacy-peer-deps` is the correct scalpel.

**Owning phase:** Foundation / theme setup phase. Document the `.npmrc` decision in the phase so future `npx shadcn@latest add` calls during subsequent phases don't surprise.

---

### Pitfall 3-B: `forwardRef` deprecation warnings and ref instability in React 19

**What breaks:**  
React 19 deprecates `forwardRef` — it still works but emits a console warning in development. shadcn's newer components (post-October 2024) have been updated to accept `ref` as a standard prop. Older versions of Radix primitives still use `forwardRef` internally and may emit warnings.

The more dangerous variant (React issue #31613): when a component uses `forwardRef`, the mere existence of the `ref` prop on the element — even when `undefined` — makes the component's props referentially unstable. This breaks `React.memo` or `useMemo`-gated children that depend on prop stability. In the BibleEditor's large address-map table, if rows are memoized and wrapped with a forwardRef component, every parent render forces a re-render of all rows.

jolly-ui's react-aria-components layer uses React Aria's own ref/composition model which is largely forwardRef-free, so jolly-ui components are less exposed to this than Radix-based components.

**Warning signs:**  
- `Warning: Component uses forwardRef ...` in the development console  
- BibleEditor table rows re-rendering on every keystroke even when data hasn't changed  
- Performance regression visible in React DevTools Profiler after adding shadcn wrappers

**Prevention:**  
1. Accept the forwardRef warnings as cosmetic during the migration sprint — they do not break functionality.  
2. For the BibleEditor's table rows: when wrapping with shadcn `TableRow`/`TableCell` primitives, ensure the parent does not pass unnecessary `ref` props. Use `React.memo` on the row component itself (not its shadcn wrapper).  
3. Prefer jolly-ui (react-aria) over Radix-based shadcn for interactive components inside the BibleEditor to reduce forwardRef exposure.

**Owning phase:** BibleEditor reskin phase. The forwardRef warning is cosmetic; the performance issue only matters for the 88KB BibleEditor with many address-map rows.

---

### Pitfall 3-C: react-aria-components `DatePicker`/`DateInput` ref passthrough bug

**What breaks:**  
There is a confirmed open issue (adobe/react-spectrum #7756) where refs are not correctly received by `DatePicker` and `DateInput` in react-aria-components when used with React 19. If jolly-ui's date-related components are adopted, programmatic focus or scrolling via refs will silently fail.

**Warning signs:**  
- `inputRef.current` is `null` after mounting a date input  
- Keyboard focus management broken in date fields

**Prevention:**  
Avoid `DatePicker`/`DateInput` from jolly-ui until the upstream issue is resolved (track adobe/react-spectrum #7756). For date display in the BibleEditor's `valid_from_episode` field, use a plain `<input type="text">` styled to match.

**Owning phase:** BibleEditor reskin phase. Low risk since Trezarr doesn't use date pickers today; note it as a constraint when adding new UI in future phases.

---

## Part 4: Big-Bang Migration Risk

### Pitfall 4-A: Half-migrated state ships broken — the big-bang paradox

**What breaks:**  
Big-bang means all pages are migrated before the release ships. The risk: the SPA must compile and the existing pages must remain navigable during the sprint. If page A has its theme tokens removed before its components are replaced, it will render with unstyled text. If page B is migrated to shadcn but shares a layout component that still uses the old tokens, the layout breaks.

The existing AppShell (sidebar) is shared across all pages. Migrating the shell first creates a period where the shell uses shadcn/CSS-var tokens but page content still uses the old hex classes. This is visually jarring but functionally safe — it does not break compilation.

**Warning signs:**  
- `vite build` fails mid-migration because a renamed token (`bg-accent`) is used somewhere that wasn't updated  
- Pages render with no background color (transparent) because a CSS variable isn't defined yet  
- Routing still works but navigation to a page shows an unstyled layout

**Prevention:**  
Migration order: foundation-first.  
1. Set up CSS variables + `darkMode: ["class"]` + animate plugin in one commit. At this point existing pages still work because their `bg-[#0f1117]` arbitrary values and `bg-bg-base` semantic classes still compile.  
2. Migrate AppShell/sidebar next (it's shared and small — 3.2KB). After this, all pages get the new shell but keep their old content styling. This is the acceptable "mixed" state.  
3. Migrate pages in order from simplest to most complex: Queue → History → JobLogs → BibleList → Settings → Library → Movies → Series → BibleEditor.  
4. Do NOT remove the old token definitions from `tailwind.config.js` until all pages are migrated. The old `bg-bg-surface`, `text-text-primary` etc. keys can coexist with the new shadcn keys for the duration of the sprint.  
5. Gate each page on `npm run build` passing before moving to the next. The BibleEditor is last — if it blocks, the rest of the app is already shippable.

**Owning phase:** All migration phases. The foundation phase owns establishing the safe "dual-token" coexistence period.

---

### Pitfall 4-B: BibleEditor 88KB reskin-in-place trap — the rebuild reflex

**What breaks:**  
BibleEditor.tsx is 88KB, contains four major sections (Characters, Address Map, Term Dictionary, Register/Overrides), uses ~122 occurrences of custom theme tokens, and has complex state management for locking, history panels, pronoun combos, and reciprocal suggestions. The temptation when migrating is to rebuild it from scratch using the new component system — this is the wrong approach.

Rebuilding risks:  
- Reintroducing bugs that took the previous harness-driven code review cycles to find (broken address-pair unlock path, history-endpoint serialization, `term_id` authority — all found in Phase 8 post-execution review)  
- Breaking the lock propagation semantics (`locked_fields` JSON, `human lock > prior value > new inference` invariant)  
- Losing the Phase-5/8 behavioral contracts that the existing 293-test suite covers

**Warning signs:**  
- PR description says "rewrote BibleEditor"  
- Lock badge behavior changes  
- `apply_human_edit_*` or `set_lock` tests start failing  
- History panel stops populating

**Prevention:**  
Reskin-in-place only: swap HTML primitives for shadcn equivalents, update className strings, keep all logic, state, and API calls identical. A mechanical substitution approach:  
- `<div className="bg-bg-surface ...">` → `<Card>` or `<div className="bg-card ...">` (same div, different class)  
- `<table>` → shadcn `<Table>` (just wraps a `<table>`, same children)  
- `<input>` → shadcn `<Input>` (same ref, same onChange, new className)  
- `<button>` → shadcn `<Button variant="ghost">` (same onClick, new styling)  

Never change: API call patterns, state shape, lock mechanics, the `FieldHistoryPanel` behavior, or any component that has a test covering its behavior. After reskin, run the existing test suite — it must stay green.

**Owning phase:** BibleEditor reskin phase (last or second-to-last page). Explicitly label it "reskin-in-place" in the phase spec.

---

### Pitfall 4-C: Visual regression with no automated test harness — the self-hosted single-user blind spot

**What breaks:**  
Trezarr has no visual regression test suite (Chromatic, Percy, Playwright screenshots). For a big-bang UI migration, visual regressions can only be caught manually. Self-hosted single-user context means there is no staging environment — the user IS the QA team.

**Warning signs:**  
- A color token change breaks a specific state (e.g., locked field badge contrast)  
- shadcn component behavior differs from the old div-based pattern in an edge case (e.g., Accordion closing behavior, Dialog focus trap)  
- Mobile/narrow-viewport layout breaks go unnoticed

**Prevention:**  
1. Create a manual checklist per page: cover all interactive states (locked/unlocked fields, empty states, error toasts, all four BibleEditor tabs, all job statuses).  
2. Use the existing smoke-test pattern (`.planning/v1.0-SMOKE-TEST.md`) — create a v1.1 smoke test covering the new sidebar nav, episode detail view, all badge states, Settings save.  
3. For the BibleEditor specifically: run the existing test suite after every section migrated (not just at the end). The tests cover behavioral contracts; visual correctness is manually checked.  
4. Validate in the actual Docker container (`docker run :6868`), not just `vite dev` — the production build can drop classes that dev serves fine (see Pitfall 1-D/1-E).

**Owning phase:** Final polish/Docker phase, but the checklist should be prepared during the foundation phase so each page phase can check off items as it goes.

---

## Part 5: FastAPI Static-Serving Interplay

### Pitfall 5-A: Vite `base` path must be `/` (or `./`) — mismatch breaks asset loading after Docker rebuild

**What breaks:**  
FastAPI mounts the SPA at `"/"` via `app.mount("/", SPAStaticFiles(...))`. Vite's default `base` is `"/"` which means all asset URLs in `index.html` are absolute paths like `/assets/index-Cx3k9.js`. This is correct when FastAPI serves from root.

The pitfall: if `base` is accidentally set to a sub-path (e.g. `"/trezarr/"`) in `vite.config.ts`, the built `index.html` references `/trezarr/assets/...` but FastAPI serves assets from `/assets/...`. Result: browser loads `index.html` but all JS/CSS 404s. The app is a blank page with network errors.

The current `vite.config.ts` has no explicit `base` setting (defaults to `"/"`). This is correct. The risk is accidental mutation during the migration when someone follows a tutorial that adds `base: "./"` (relative) thinking it's equivalent — relative base works for simple SPAs but breaks when FastAPI's `StaticFiles` uses the absolute path in its routing.

**Warning signs:**  
- Browser Network tab shows 404 for `/trezarr/assets/index-*.js` after `docker build`  
- `index.html` loads (200) but the app is blank  
- Works on `vite dev` (dev server ignores `base` for local files) but fails on `docker run`

**Prevention:**  
Do not add a `base` key to `vite.config.ts` unless deliberately serving from a sub-path. If `base` is needed, set it to `"/"` explicitly (same as default). The `outDir: "../trezarr/web/static"` path in the current config is correct and should not change — it deposits the build directly into the FastAPI static directory.

**Owning phase:** Foundation phase (when vite.config.ts is modified for the `@/` alias). Add a note: "do not set `base`."

---

### Pitfall 5-B: SPAStaticFiles `.dark` class and hashed asset names — no issues, but understand the interaction

**What works (and how):**  
The `SPAStaticFiles` implementation correctly serves `index.html` for all extensionless routes outside `/api/` and `/webhook/`. shadcn's dark mode adds `class="dark"` to `<html>` — this is a DOM operation, invisible to the server-side routing logic. No changes needed to `SPAStaticFiles` for dark mode support.

Hashed asset names (`assets/index-Cx3k9.js`) are served as real files (the `has_extension` check in `get_response` passes them through to the superclass handler, which resolves them from disk). After a rebuild, old hashed filenames no longer exist on disk but `index.html` references the new hashes — this is correct behavior. The browser loads the new `index.html` (no hash), which references new hashed assets.

**The one real risk:** if the Docker image is rebuilt but the *old* image is still running on the Synology NAS (stale container), the old `index.html` references old hashed asset filenames which no longer exist in the new image. This is NOT a code pitfall — it is an operational pitfall (see Pitfall 5-D).

**Owning phase:** N/A for code; Docker phase for ops.

---

### Pitfall 5-C: Routes registered before StaticFiles mount — already solved; don't regress it

**What breaks:**  
`app.py` already documents "Pitfall E: StaticFiles must be after routes" and implements it correctly — all API routers are registered before `app.mount("/", SPAStaticFiles(...))`. After adding new shadcn-related API endpoints in the episode enrichment phase (Bazarr data, audio language badges), those routers MUST also be registered before the mount.

**Warning signs:**  
- A new API endpoint returns `index.html` content instead of JSON  
- `curl /api/library/series/1/episodes` returns an HTML document  
- The browser's network tab shows the API call as `content-type: text/html`

**Prevention:**  
Every new router added during the v1.1 milestone must follow the existing pattern in `app.py`: import the router at the top of the create_app function body and call `app.include_router(...)` before the `if os.path.exists(_static_dir):` block. This is already the pattern; it needs enforcement via code review, not new code.

**Owning phase:** Backend episode-enrichment phase.

---

### Pitfall 5-D: Docker rebuild / Synology multi-machine image staleness

**What breaks:**  
The project memory records that the Synology-synced multi-machine repo can have the local `main` advancing mid-session. For v1.1, there is an additional hazard: the multi-stage Docker image bundles the built Vite SPA as a COPY layer. If the image is not rebuilt after frontend changes, the running container serves the old UI.

The Dockerfile's node-builder stage has good layer caching: `package.json`/`package-lock.json` are copied before `npm ci`, so dependency installs are cached. BUT if `package.json` changes (new shadcn deps), the cache is busted and a full `npm ci` runs. On a Synology NAS with an ARM64 Docker environment building `linux/amd64` images via emulation, this is slow. Developers may be tempted to skip the Docker rebuild and test only on `vite dev` — which is fine for UI logic but misses:  
- The Tailwind purge (classes present in dev but purged in production)  
- The `trezarr serve` lifespan startup (media root assertions, DB migrations)  
- The PUID/PGID drop and file ownership behavior

**Warning signs:**  
- UI changes deployed but the running container still shows the old design  
- `docker pull` of the image shows an old build date  
- Smoke test passes on `vite dev` but fails on `:6868`

**Prevention:**  
1. After the shadcn/package.json changes, run a full `docker build` early to catch any COPY/layer issues — don't defer the Docker build to the final phase.  
2. For rapid iteration during the migration sprint, use `vite dev` with the FastAPI backend running separately (`trezarr serve` with no SPA found — the app gracefully logs that and serves only the API). Do final validation in Docker.  
3. Before pushing a release build: `docker build --no-cache` to verify the full multi-stage build. Add a build timestamp `ARG BUILD_DATE` to bust the cache explicitly when needed.  
4. Given the Synology multi-machine setup: `git fetch && git merge-base --is-ancestor HEAD origin/main` before the Docker build to verify the local branch is current. Never force-push to main (per project memory).

**Owning phase:** Final Docker / smoke-test phase.

---

## Part 6: Backend Episodes-Endpoint Pitfalls

### Pitfall 6-A: Bazarr fail-soft — never 500 the page if Bazarr is down or disabled

**What breaks:**  
The new episode detail endpoint (`GET /api/library/series/{id}/episodes`) needs to be enriched with Bazarr subtitle inventory data for the subtitle-language badge column. The existing `BazarrClient.fetch_episode_inventory()` raises `BazarrError` on HTTP error or transport failure. If the enrichment code calls Bazarr and propagates the exception to the route handler, a Bazarr outage returns HTTP 502 to the browser — the entire Series episode view fails to load.

This violates the project's stated soft-dependency contract: "disabled/unreachable degrades to the filesystem glob (D-104)." The UI must display episodes with Trezarr-status data even when Bazarr is down; subtitle badges simply appear empty/absent.

The current `get_series_episodes` endpoint does NOT call Bazarr at all (it uses only Sonarr episode files + filesystem glob). The enrichment phase must add Bazarr without changing the HTTP-200 guarantee.

**Warning signs:**  
- Episodes page returns 502 when Bazarr's connection test in Settings shows "unreachable"  
- Browser shows a loading spinner forever when the user has Bazarr disabled in settings  
- Any `BazarrError` exception propagating past the `try/except` in the route handler

**Prevention:**  
Wrap every Bazarr call in the episode endpoint in a `try/except BazarrError` (and broad `Exception`) with a fallback to empty:

```python
bazarr_inventory: dict[int, BazarrInventoryItem] = {}
if settings.bazarr_enabled:
    try:
        items = await bazarr_client.fetch_episode_inventory(series_id)
        bazarr_inventory = {item.arr_id: item for item in items}
    except Exception:
        logger.warning("get_series_episodes: Bazarr unavailable, continuing without subtitle data")
        # bazarr_inventory stays {}
```

Each episode row then does `bazarr_data = bazarr_inventory.get(sonarr_episode_id)` — `None` if Bazarr was down. The row is returned with an empty `subtitles: []`. The badge column renders nothing. Route still returns HTTP 200 with full episode list.

**Owning phase:** Backend episode-enrichment phase.

---

### Pitfall 6-B: `sonarrEpisodeId` ↔ episode-file join — using the wrong ID

**What breaks:**  
Sonarr's data model has two distinct ID spaces:  
- `episodeFile.id` — the file record's own ID  
- `episode.id` — the logical episode record  
- `episode.episodeFileId` — foreign key from episode → file  
- `episodeFile.episodeIds[]` — which logical episodes this file covers (multi-episode files)  

Bazarr's `BazarrInventoryItem.arr_id` is the `sonarrEpisodeId` — the **logical episode ID**, not the file ID. If the enrichment code joins on `episodeFile.id` instead of `episode.id`, no Bazarr entries will match and all badges will be empty silently.

The current `fetch_episode_inventory` in `bazarr.py` already extracts `arr_id` from `sonarrEpisodeId` (`_parse_inventory_item` line: `arr_id = item.get("sonarrEpisodeId") or item.get("radarrId") or 0`). The join in the route must look up by this same ID.

But `client.episode_file.get(series_id=series_id)` returns episode *files*, not logical episodes. Episode files do not carry `sonarrEpisodeId` directly — they carry `episodeIds: [int]`. To join correctly, either:  
a. Call `client.episode.get(series_id=series_id)` to get logical episodes (with `episodeFileId`), build a map `fileId → episodeId`, then join.  
b. Use `episodeIds[0]` from the file record as an approximation (works for single-episode files; wrong for multi-episode packs).

**Warning signs:**  
- All Bazarr badges empty even when Bazarr is online and reports subtitle data  
- `bazarr_inventory` dict is non-empty but no episode row finds a match  
- Logging `arr_id=0` for all Bazarr items

**Prevention:**  
In the enrichment phase, design the join explicitly:  
1. Fetch logical episodes: `episodes = client.episode.get(series_id=series_id)` → build `file_id_to_episode_id: dict[int, int]`  
2. Fetch episode files: `ep_files = client.episode_file.get(series_id=series_id)`  
3. For each file: `episode_id = file_id_to_episode_id.get(ep_file["id"])` → look up in `bazarr_inventory`  
This is one extra Sonarr call per series page load. Cache it in-request (not across requests — no server-side state for this). Performance is acceptable: two pyarr calls plus one Bazarr call per page view.

**Owning phase:** Backend episode-enrichment phase.

---

### Pitfall 6-C: `audioLanguages` absent or `"und"` for un-analyzed files

**What breaks:**  
The new episode detail table shows an Audio badge (e.g., "KO" for Korean audio). This data comes from Sonarr's `episodeFile.mediaInfo.audioLanguages`. This field:  
- Is absent entirely if the episode file has never been analyzed by Sonarr (file imported but mediaInfo scan not yet run)  
- Returns `"und"` (undetermined) for files where Sonarr's analyzer couldn't detect the language  
- Is a single string (e.g. `"Japanese"`) or comma-separated string (e.g. `"Japanese / English"`) — not an array  
- Uses full language names (e.g. `"Japanese"`) not ISO codes in some Sonarr versions

If the code assumes `mediaInfo.audioLanguages` is always present and always an ISO code, it will crash on missing mediaInfo or display "und" / "Japanese" raw instead of a clean badge.

**Warning signs:**  
- `KeyError: 'audioLanguages'` or `AttributeError` on episodes without mediaInfo  
- Badge displays "und" or the full word "Japanese" instead of "JA"  
- TypeError when trying to split a `None` value

**Prevention:**  
```python
media_info = ep_file.get("mediaInfo") or {}
audio_languages_raw = media_info.get("audioLanguages") or ""
# audioLanguages is a string like "Japanese / English" or "und" or ""
audio_badges = []
if audio_languages_raw and audio_languages_raw != "und":
    for lang in audio_languages_raw.split("/"):
        lang = lang.strip()
        if lang:
            audio_badges.append(lang[:3].upper())  # truncate to badge width
```

Return `audio_languages: []` (empty list) when mediaInfo is absent or "und". The UI renders no badge rather than crashing. Map common full names to ISO codes in a small lookup table ({"Japanese": "JA", "Korean": "KO", "Chinese": "ZH", ...}) rather than raw-truncating.

**Owning phase:** Backend episode-enrichment phase.

---

### Pitfall 6-D: Performance — one Bazarr call per series, not per episode

**What breaks:**  
`BazarrClient.fetch_episode_inventory(sonarr_series_id)` fetches the entire series' subtitle inventory in one `GET /api/episodes?seriesid=N` request. If the enrichment code calls Bazarr once per episode file (inside the loop), a 24-episode series makes 24 Bazarr HTTP calls per page load. At 10s timeout each, this is a 240-second worst case before Bazarr failure is detected.

**Warning signs:**  
- Episodes page takes 10+ seconds to load  
- Logs show repeated `GET /api/episodes?seriesid=1` calls  
- Bazarr logs show a storm of identical requests per page view

**Prevention:**  
Call Bazarr ONCE per page request (outside the loop), then build the `sonarrEpisodeId → BazarrInventoryItem` lookup dict, and resolve each episode inside the loop via dict lookup. This is the pattern described in Pitfall 6-A above. The `fetch_episode_inventory` method already returns the full series at once — use it that way.

**Owning phase:** Backend episode-enrichment phase.

---

### Pitfall 6-E: Path-mapping and traversal guard on subtitle paths from Bazarr

**What breaks:**  
`BazarrInventoryItem.subtitles[].path` is a Bazarr-side filesystem path (Bazarr's container namespace). The existing `BazarrClient._parse_subtitle_entry` already applies `apply_path_mapping` when `path_mappings` are configured (D-105). But the episode endpoint needs to expose these paths to the frontend for display — and the frontend might offer a "use this subtitle as source" action in the future.

The risk: Bazarr-reported paths are user-controlled data (Bazarr configuration could be misconfigured to return paths outside the media roots). If the backend passes these paths to `translate_file` without the traversal guard, a path like `../../../config/config.yaml` (hypothetical) would be a security issue.

**Warning signs:**  
- Subtitle paths in the API response starting with `..` or `/config/`  
- A subtitle path not resolving under any configured media root

**Prevention:**  
In the episode enrichment endpoint, Bazarr subtitle paths are returned to the frontend for display only — they must NOT be passed directly to any execution path. If a future action "use Bazarr subtitle as source" is added, apply the same `assert_within_media_roots` guard that `post_translate` already uses (T-l8g-01 pattern in `library.py` line 251-263). For v1.1, the paths are display-only; document this constraint explicitly in the route docstring.

**Owning phase:** Backend episode-enrichment phase.

---

## Phase-Specific Warning Table

| Phase topic | Likely pitfall | Mitigation |
|---|---|---|
| Foundation: theme setup | HSL format wrong (1-A), token collision (1-B), missing `darkMode: ["class"]` (1-C), missing animate plugin (1-D), content glob (1-E) | All five must be in one verified commit before any component work starts |
| Foundation: Vite alias | `@/` in only one config location (2-A) | Add to both `vite.config.ts` AND `tsconfig.json` simultaneously |
| Foundation: npm install | `ERESOLVE` on React 19 peer deps, `cmdk` type errors (3-A) | `.npmrc` `legacy-peer-deps=true` before first `npx shadcn@latest init` |
| AppShell / sidebar migration | Starts the dual-token mixed period (4-A) | Do not remove old token defs from tailwind.config.js yet |
| Page migrations (Settings, Queue, etc.) | Visual regression with no automated harness (4-C) | Manual checklist per page; `npm run build` gate after each page |
| BibleEditor reskin | Rebuild reflex (4-B), forwardRef perf (3-B) | "Reskin-in-place only" label; run test suite after each section |
| Backend enrichment: episodes endpoint | Bazarr fail-soft (6-A), wrong ID join (6-B), audioLanguages absent (6-C), N+1 Bazarr calls (6-D), path traversal (6-E), new router before StaticFiles (5-C) | All six in one review checklist for the enrichment PR |
| Final Docker / smoke test | Stale image on Synology (5-D), purged animation classes (1-D), `vite dev` passing but `docker build` failing | `docker build --no-cache` on final phase; full smoke test at `:6868` |

---

## Sources

- shadcn/ui Tailwind v3 theming (HSL channel triple format, `darkMode: ["class"]`, `tailwindcss-animate` plugin): https://shadcn.usame.link/docs/theming — HIGH confidence (canonical v3 docs mirror)
- shadcn/ui React 19 compatibility guide: https://ui.shadcn.com/docs/react-19 — HIGH confidence (official)
- shadcn/ui changelog (October 2024 React 19, February 2026 Radix unification): https://ui.shadcn.com/docs/changelog — HIGH confidence (official)
- GitHub: `fix: command dependency cmdk React 19 support` (PR #6644): https://github.com/shadcn-ui/jolly-ui/pull/6644 — HIGH confidence (merged fix)
- GitHub: `border-border` class does not exist bug (#6066): https://github.com/shadcn-ui/ui/issues/6066 — HIGH confidence (confirmed behavior)
- GitHub: react-aria-components peer dep pinned to RC (#9267): https://github.com/adobe/react-spectrum/issues/9267 — MEDIUM confidence (open issue)
- GitHub: DatePicker/DateInput ref passthrough bug (#7756): https://github.com/adobe/react-spectrum/issues/7756 — MEDIUM confidence (open issue)
- GitHub: React 19 forwardRef props referential instability (#31613): https://github.com/facebook/react/issues/31613 — HIGH confidence (React core issue)
- Sonarr API mediaInfo.audioLanguages field (string, "und" for undetermined): Sonarr issue #5602 + Go package docs — MEDIUM confidence (community reports consistent)
- JollyUI: https://www.jollyui.dev/docs — MEDIUM confidence (official but limited peer-dep docs)
- Trezarr codebase: `trezarr/web/app.py`, `trezarr/arr/bazarr.py`, `trezarr/web/routes/library.py`, `frontend/tailwind.config.js`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `Dockerfile` — HIGH confidence (source of truth for existing patterns)
