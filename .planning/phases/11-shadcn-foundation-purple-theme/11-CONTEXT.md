# Phase 11: shadcn Foundation & Purple Theme - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Install the shadcn/ui + jolly-ui component infrastructure on the existing
**Tailwind v3.4** stack and replace the legacy hex token system with a purple,
dark-mode-default **HSL CSS-variable** theme — behind a bridge layer that keeps
every legacy class functional — verified by a green `npm run build` **with no
page content changes**.

**In scope:**
- `@/` path alias wired in **both** `frontend/vite.config.ts` and `frontend/tsconfig.json`
- `components.json`, `src/lib/utils.ts` (`cn()`), `.npmrc` (`legacy-peer-deps=true`)
- `npx shadcn@2.10.0 init` (the Tailwind-v3 CLI line)
- Purple HSL CSS-variable theme block in `src/index.css` (`:root`/`.dark`),
  `darkMode: ["class"]`, `class="dark"` on `<html>`, purple-tinted body background
- Bridge-period `tailwind.config.js` (legacy hex tokens preserved alongside the
  new shadcn token mapping); `tailwindcss-animate` plugin
- Bulk-install the shadcn component set + jolly-ui Table (vendor code under `src/components/ui/`)
- Green production build; in-browser visual confirmation of theme + one opacity modifier

**Out of scope (later phases — do NOT touch):**
- Sidebar shell / `AppSidebar` / route restructure → Phase 12
- Backend episodes enrichment → Phase 13
- New Series/Movies/SeriesDetail pages, nav badges → Phase 14
- Reskinning existing pages, removing bridge tokens → Phase 15
- Docker rebuild + live smoke test → Phase 16

</domain>

<decisions>
## Implementation Decisions

### Purple Identity (the flagged open question)
- **D-01:** Lock `--primary: 270 70% 60%` (STACK.md vivid violet) as the brand
  purple anchor. ARCHITECTURE.md's `271 71% 58%` is the documented alternative.
  The **exact** per-token HSL values are visually tuned in-browser at the
  Phase-11 human-verify gate (Decision D-09) — `270 70% 60%` is the starting point,
  not a frozen final value.
- **D-02:** All CSS variables are bare **channel-triple** `H S% L%` (e.g.
  `270 70% 60%`), never wrapped in `hsl()`. The `hsl(var(--x))` wrapper lives only
  in `tailwind.config.js`. (Pitfall #1 — `hsl()` in the variable silently breaks
  `bg-primary/50` opacity modifiers with no compile error.)
- **D-03:** `--ring` and `--sidebar-primary` track `--primary` (same purple).
  Suggested coherent anchors for the planner (tune at the gate):
  `--background 270 24% 7%`, `--card 270 22% 11%`, `--muted 270 15% 16%`,
  `--border 270 18% 20%`, `--primary-foreground 0 0% 100%`, `--destructive 0 72% 51%`,
  `--radius 0.5rem`, sidebar tokens in the same purple-dark family.

### Background Tint
- **D-04:** `--background` is a **purple-tinted dark** (not the legacy blue-black
  `#0f1117`), satisfying Success Criterion 2 ("dark purple background"). Update the
  `<body>`/`html` inline background in `frontend/index.html` to match the new
  `--background` so the app root reads purple.
- **D-05:** Legacy `bg-base`/`bg-surface`/`bg-stripe`/`text-primary`/`text-muted`
  **stay blue-black** as bridge tokens (existing pages keep their panels unchanged)
  until all pages are reskinned in Phase 15. The visible "dark purple background" is
  the app root showing through; legacy panels sit on top. (Pitfall #3 — these five
  bridge tokens do NOT collide with shadcn keys; keep them. The colliding keys —
  `border`, `accent`, `destructive` — are replaced wholesale in one commit.)

### Component Install Scope
- **D-06:** **Bulk-install** the full research-specified shadcn set in one clean
  foundation commit, plus jolly-ui Table via registry URL:
  ```
  npx shadcn@2.10.0 add sidebar button badge card tabs accordion collapsible \
      tooltip skeleton sonner dropdown-menu
  REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table
  ```
  Rationale: one vendor-code commit, no per-phase churn; downstream phases import
  ready primitives. `init` MUST be pinned to `2.10.0`; `add` may use `@latest`.
- **D-07:** Treat everything under `src/components/ui/` as **vendor code** — never
  hand-edit. `legacy-peer-deps=true` in `.npmrc` BEFORE the first `add` (prevents
  `ERESOLVE` from `cmdk`/`react-day-picker`); do **not** use `--force`.

### Build & Wiring Invariants
- **D-08:** Do **not** set `base` in `vite.config.ts` (would break the FastAPI
  static-serve path). Keep `build.outDir = ../trezarr/web/static`, `emptyOutDir: true`.
  Add the `@/` alias via `resolve.alias` + `@types/node` for `path`. Mirror the alias
  in `tsconfig.json` (`baseUrl: "."`, `paths: { "@/*": ["src/*"] }`). The build script
  stays `tsc -b && vite build`.

### Phase-End Verification
- **D-09:** Phase 11 ends with a **human visual-UAT checkpoint** (browser screenshot
  review): confirm (a) dark purple background with `.dark` active, (b) a
  `<Button variant="default">` renders purple, (c) `bg-primary/50` shows correct
  half-opacity purple (proves the channel-triple format). The `--auto` chain
  **HOLDS** at this gate — it does not auto-close with pending UAT.

### Claude's Discretion
- Exact non-anchor token values (secondary/accent/popover/input shades within the
  purple-dark family), the precise purple-tinted `--background` lightness, and
  `components.json` style/baseColor selections — chosen to look coherent, finalized
  at the D-09 gate.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 Research (locks the entire approach — read first)
- `.planning/research/SUMMARY.md` — consolidated v1.1 plan: stack, shadcn v2/v4 split, build order, the 7 pitfalls, Phase-1/Foundation deliverables
- `.planning/research/STACK.md` — exact package versions + peer-dep ranges, `shadcn@2.10.0` pin, HSL template, purple `270 70% 60%`, `cn()` source
- `.planning/research/ARCHITECTURE.md` — the four migration seams, artifact change table, dark-mode wiring, alt purple `271 71% 58%`
- `.planning/research/PITFALLS.md` — HSL channel-triple, `shadcn@latest` v3 break, token collisions, bridge tokens, dark-mode wiring, Vite `base`

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — **UI-01** (shadcn foundation on Tailwind v3, build stays green), **UI-02** (purple CSS-variable dark theme replaces legacy hex)
- `.planning/ROADMAP.md` §"Phase 11" — goal + four success criteria (green build / dark purple background / purple Button at `bg-primary/50` / no broken pages)

### Existing code baseline (this phase modifies these)
- `frontend/tailwind.config.js` — current plain-hex token block to bridge/replace
- `frontend/src/index.css` — currently bare `@tailwind` directives; CSS-variable block lands here
- `frontend/vite.config.ts` — add `@/` alias; keep `base` unset, keep `outDir`
- `frontend/tsconfig.json` — single flat config; add `baseUrl` + `paths`
- `frontend/package.json` — add 6 runtime + 1 dev (`@types/node`) deps; build = `tsc -b && vite build`
- `frontend/index.html` — `<html lang="en">` → add `class="dark"`; update inline body background to the new purple `--background`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `frontend/src/components/AppShell.tsx` and all existing pages render fine today;
  they must keep rendering unchanged this phase (bridge tokens carry them).
- Existing lucide-react (^0.511.0) and react-router-dom (^6.30.1) are unchanged —
  no version bumps in Phase 11.

### Established Patterns
- FastAPI serves the Vite build from `trezarr/web/static` as the last route
  (`StaticFiles(html=True)`); the SPA deep-link fallback already exists — Phase 11
  changes nothing in the backend. `outDir` and unset `base` are load-bearing.
- TypeScript is `strict` + `noUnusedLocals`/`noUnusedParameters`; vendor `ui/`
  files must satisfy strict mode (shadcn output does).

### Integration Points
- `@/` alias must resolve identically in Vite (runtime) and tsc (`tsc -b` typecheck)
  or the build splits — wire BOTH config files in the same commit.
- New shadcn `--background`/`--foreground` flow through `tailwind.config.js`
  `hsl(var(--…))` mappings; legacy semantic classes (`bg-base`, etc.) stay as raw
  hex side-by-side during the bridge period.

</code_context>

<specifics>
## Specific Ideas

- Verify the opacity modifier (`bg-primary/50`) renders as true half-opacity purple
  in the browser **immediately** after writing the theme — the canonical proof the
  channel-triple format is correct (Success Criterion 3).
- jolly-ui has no npm package; it is a copy-paste registry at `https://jollyui.dev/r`
  consumed via the shadcn CLI registry feature.

</specifics>

<deferred>
## Deferred Ideas

- jolly-ui **Table beta** stability evaluation (with shadcn plain `<Table>` fallback)
  is a **Phase 14** concern — the Table is installed here as vendor code but not
  exercised until the new library pages are built.
- Removing the legacy bridge tokens from `tailwind.config.js` is **Phase 15** (after
  every page is reskinned and `grep bg-[#`/`text-[#` is clean).

None outside the roadmapped phases — discussion stayed within phase scope.

</deferred>

---

*Phase: 11-shadcn-foundation-purple-theme*
*Context gathered: 2026-06-03*
