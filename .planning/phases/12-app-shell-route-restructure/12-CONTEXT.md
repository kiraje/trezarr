# Phase 12: App Shell + Route Restructure - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the current `AppShell` (a 48px TopBar + a fixed 192px flat `<nav>`,
`children`-prop layout) with a shadcn **`SidebarProvider` + `AppSidebar` +
`<Outlet/>`** layout, and restructure the react-router route table so `/library`
splits into `/series` + `/movies` + `/series/:seriesId` and `/` redirects to
`/series`. Every existing page (Queue, History, Settings, Bible List, Bible
Editor, JobLogs) must keep rendering and navigating inside the new full-height
sidebar shell with **no regressions and no new page content**.

**In scope:**
- `frontend/src/components/AppShell.tsx` — REPLACED: thin layout that returns
  `<SidebarProvider><AppSidebar/><main><Outlet/></main></SidebarProvider>`
  (children-prop → Outlet).
- `frontend/src/components/app-sidebar.tsx` — NEW (hand-written): the
  Trezarr-specific sidebar (brand, 6 nav items, active-state, footer status).
- `frontend/src/App.tsx` — MODIFIED: layout-route pattern; `/` → `/series`;
  add `/series`, `/series/:seriesId`, `/movies` pointing at stub pages; keep
  `/queue`, `/history`, `/jobs/:id/logs`, `/settings`, `/bible`,
  `/bible/:seriesId`; keep `/library` mounted on the existing `Library.tsx`
  (see D-03).
- `frontend/src/pages/Series.tsx`, `SeriesDetail.tsx`, `Movies.tsx` — NEW STUBS:
  heading placeholder only, render without errors (Success Criterion 4).
- Uses the already-installed Phase-11 vendor primitives
  (`src/components/ui/sidebar.tsx`, `sheet.tsx`, `separator.tsx`, `button.tsx`).

**Out of scope (later phases — do NOT touch):**
- Backend `GET /api/library/series/{id}/episodes` enrichment → Phase 13
- Real Series/SeriesDetail/Movies page content (tables, season accordions,
  badges) → Phase 14
- NAV-03 right-side **count badge** + **LIVE** connection-aware badge → Phase 14
  (Phase 12's footer status dot is the existing generic "service running"
  indicator only — NOT wired to *arr connection state)
- Reskinning the existing pages onto shadcn primitives / removing bridge
  tokens → Phase 15
- Deleting `Library.tsx` and removing the `/library` route → Phase 14
- Docker rebuild + live smoke test → Phase 16

</domain>

<decisions>
## Implementation Decisions

### Sidebar Interaction Model
- **D-01:** The sidebar uses shadcn **`collapsible="icon"`** (icon-rail). It
  collapses to a ~48px icon-only rail (nav stays visible), reclaiming width for
  the Series-detail season accordions and dense tables that land in Phase 14.
  - Default state: **expanded**.
  - Persistence: shadcn's built-in **cookie** persistence (`sidebar_state`) — no
    custom store.
  - Toggle affordances: keep the shadcn defaults — the draggable **`SidebarRail`**
    plus the **Cmd/Ctrl+B** keyboard shortcut. A `SidebarTrigger` in the sidebar
    header is acceptable but the rail is the primary affordance (since the TopBar
    is being removed, do NOT rely on a top-bar trigger).
  - Mobile/narrow widths: rely on shadcn's automatic **`Sheet`** behavior
    (`sheet.tsx` already installed). Mobile is not a primary target (self-hosted
    desktop dashboard) but must not break.

### Top Bar & Service Status
- **D-02:** **Drop the 48px TopBar entirely.** The full-height sidebar owns the
  brand (NAV-01), so the separate top header is removed. Relocate the existing
  green **"service running" status dot** into a **`SidebarFooter`** row.
  - In Phase 12 this dot keeps its current semantics: a static green indicator
    meaning "the server is serving this page" — it is NOT the NAV-03 LIVE /
    *arr-connection-aware badge (that is Phase 14). Do not over-build it here.
  - When the sidebar is collapsed to the icon rail, the footer shows just the
    dot (label hidden), consistent with the icon-only collapsed state.

### Route Restructure & `/library` Transition
- **D-03:** **Keep `/library` mounted on the existing `Library.tsx`** during the
  Phase 12–13 transition, but **remove it from the nav** (`NAV_ITEMS` exposes
  only the six locked items). Rationale: Series/Movies are placeholder stubs
  until Phase 14 and `Library.tsx` is not deleted until Phase 14 — keeping the
  route reachable means the **live deployment never loses a working library
  view mid-milestone**. This does NOT violate NAV-02 (nav no longer exposes
  `/library`; the split is the user-visible contract; the legacy route is a
  transitional alias removed in Phase 14). `Library.tsx` itself is **untouched**
  this phase (no reskin, no edits).
- **D-04:** Route table per `research/ARCHITECTURE.md` §2 "After (v1.1)": a
  single layout route `<Route path="/" element={<AppShell/>}>` with children:
  `index → <Navigate to="/series" replace/>`, `series`, `series/:seriesId`,
  `movies`, `queue`, `history`, `jobs/:id/logs`, `settings`, `bible`,
  `bible/:seriesId`, plus the transitional `library` route (D-03). The existing
  `SPAStaticFiles` fallback already serves `index.html` for all extensionless
  deep links — **no backend change** (Success Criterion 1).
- **D-05:** Active-state detection per `research/ARCHITECTURE.md` §2: derive
  active from react-router `useLocation` inside `app-sidebar.tsx` and pass it to
  `SidebarMenuButton`'s `isActive` (which maps to `data-[active=true]` → the left
  2px purple accent bar via `--sidebar-primary`). Match nested routes:
  `pathname === to || pathname.startsWith(to + "/")` so `/series/:id` keeps
  `/series` active and `/bible/:seriesId` keeps `/bible` active. Use
  `onClick={() => navigate(to)}` (NOT `asChild` + `<a>`) to preserve
  client-side navigation without fighting the Radix slot model.

### Brand
- **D-06:** Brand = a **lucide glyph + uppercase "TREZARR" pill** in a
  `SidebarHeader` (NAV-01). Use the lucide **`Captions`** icon as the glyph
  (a subtitle-translator fit), tinted with `--sidebar-primary` purple; no new
  image/logo asset is introduced. When collapsed to the icon rail, show just the
  glyph (pill hidden). `Languages` is an acceptable alternate glyph if `Captions`
  reads poorly at 16–20px — finalize at the UI verify gate.

### Claude's Discretion
- Exact stub-page content for `Series.tsx` / `SeriesDetail.tsx` / `Movies.tsx`:
  a single heading placeholder is sufficient (Success Criterion 4); a muted
  "Coming in Phase 14" subline is optional. Stubs must compile and render with
  no console errors.
- Exact `SidebarHeader` / `SidebarFooter` markup, spacing, and the precise pill
  styling (within the Phase-11 purple token system).
- Whether to also render a `SidebarTrigger` in the header in addition to the
  rail (D-01) — chosen for best ergonomics, finalized at the UI gate.
- Final glyph choice between `Captions` and `Languages` (D-06).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 Research — locks the entire Phase-12 approach (read first)
- `.planning/research/ARCHITECTURE.md` §2 "App-Shell Architecture: SidebarProvider
  + React Router" — the authoritative design: layout-route + `<Outlet/>`, the
  exact before/after route tables, `AppShell.tsx` v1.1 shape, `app-sidebar.tsx`
  sketch (NAV_ITEMS, active-accent via `data-[active]`, `navigate(to)` over
  `asChild`), and the `SPAStaticFiles` "no backend change" conclusion.
- `.planning/research/ARCHITECTURE.md` §6 "Integration Points" — the New vs.
  Modified artifact table for the frontend (what this phase touches).
- `.planning/research/ARCHITECTURE.md` §8 "Risks" — `children`→`Outlet` test
  fallout (verified N/A here, see code_context), Tailwind v3 lock.
- `.planning/research/SUMMARY.md` — consolidated v1.1 plan + build order.

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — **NAV-01** (full-height sidebar shell; brand =
  logo glyph + "TREZARR" pill; left purple accent bar on active section),
  **NAV-02** (nav exposes Series/Movies/Queue/History/Bible/Settings; `/library`
  splits into `/series` + `/movies`; `/` → `/series`). **NAV-03 is Phase 14 —
  out of scope here.**
- `.planning/ROADMAP.md` §"Phase 12: App Shell + Route Restructure" — goal + the
  four success criteria (`/` redirect & deep-link refresh; sidebar brand + 6
  items + accent bar; existing pages functional inside the shell; stub pages
  render headings without errors).

### Phase-11 design contract (inherited tokens & labels)
- `.planning/phases/11-shadcn-foundation-purple-theme/11-UI-SPEC.md` — locked nav
  labels ("Series / Movies / Queue / History / Bible / Settings"), the
  `--sidebar-*` purple token table, and the "Phase 12 left purple accent bar on
  active nav item" color contract.
- `.planning/phases/11-shadcn-foundation-purple-theme/11-CONTEXT.md` — purple
  theme decisions, bridge-token policy (legacy hex tokens stay until Phase 15;
  do NOT remove them here).

### Existing code baseline (this phase replaces / modifies these)
- `frontend/src/components/AppShell.tsx` — current TopBar + fixed-nav,
  `children`-prop shell to REPLACE.
- `frontend/src/App.tsx` — current route table + `<AppShell>{children}</AppShell>`
  wrap to MODIFY (`/` currently → `/queue`).
- `frontend/src/components/ui/sidebar.tsx` — installed Phase-11 vendor primitive
  (`SidebarProvider`, `Sidebar`, `SidebarContent`, `SidebarMenu(Item|Button)`,
  `SidebarHeader`, `SidebarFooter`, `SidebarRail`, `SidebarTrigger`,
  `SidebarGroup(Label)`); **vendor code — never hand-edit**.
- `frontend/src/components/ui/sheet.tsx`, `separator.tsx`, `button.tsx` — installed
  vendor primitives available to the shell.
- `frontend/src/pages/Library.tsx` — kept reachable at `/library` (D-03);
  untouched this phase.
- `trezarr/web/app.py` — `SPAStaticFiles` fallback (no change needed; confirms
  deep-link routing for the new extensionless paths).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- All Phase-12 shadcn primitives are **already installed** (Phase 11 vendor
  drop): `sidebar.tsx` (23KB — full `SidebarProvider`/rail/trigger/footer API),
  `sheet.tsx` (mobile), `separator.tsx`, `button.tsx`. No `shadcn add` needed.
- `lucide-react` (^0.511.0) is present; the current AppShell already imports
  `Settings, List, History, BookOpen, Film` — add `Tv`/`Film`/`Captions`
  (or `Languages`) for the new nav + brand. No version bump.
- `react-router-dom` (^6.30.1) supports the layout-route + `<Outlet/>` pattern
  directly.

### Established Patterns
- FastAPI serves the Vite build from `trezarr/web/static` via
  `StaticFiles(html=True)` as the last route; the SPA deep-link fallback already
  returns `index.html` for extensionless paths not under `/api`/`/webhook`. The
  new `/series`, `/series/:id`, `/movies` paths are covered with **zero backend
  changes** (Success Criterion 1).
- TypeScript is `strict` + `noUnusedLocals`/`noUnusedParameters`; the build is
  `tsc -b && vite build`. New files (`app-sidebar.tsx`, stub pages) must satisfy
  strict mode and import only what they use.
- The current active-nav styling (left 2px accent border + striped bg) is exactly
  the visual contract the shadcn `data-[active]` + `--sidebar-primary` accent bar
  reproduces — the look carries over, the mechanism changes.

### Integration Points
- The single seam is the react-router **layout route**: `AppShell` moves from a
  `children`-prop wrapper to an `<Outlet/>` host nested under `<Route path="/">`.
- **Verified low-risk:** a `grep` for `AppShell` across `frontend/src/` returns
  only `App.tsx` and `AppShell.tsx` themselves — **no test file mounts
  `<AppShell>...</AppShell>`**, so the `children`→`Outlet` swap (a flagged risk
  in ARCHITECTURE.md §8) has **no test fallout** here.
- Bridge period: legacy hex tokens (`bg-base`, `bg-surface`, `bg-stripe`,
  `text-primary`, `text-muted`) remain valid; existing pages keep their current
  look inside the new shell. The new `<main>` uses `bg-background` (purple-tinted)
  so the app root reads purple while legacy panels sit on top — unchanged from
  Phase 11's bridge design.

</code_context>

<specifics>
## Specific Ideas

- Active-route matching must use prefix logic (`pathname === to ||
  pathname.startsWith(to + "/")`) so `/series` stays highlighted on
  `/series/:seriesId` and `/bible` on `/bible/:seriesId` — copy the
  `research/ARCHITECTURE.md` §2 `app-sidebar.tsx` sketch.
- Keep the green service dot's existing meaning in Phase 12 (server-is-serving),
  relocated to `SidebarFooter`; resist the urge to wire it to *arr connection
  state — that is NAV-03 / Phase 14.
- Brand glyph: prefer lucide `Captions`; fall back to `Languages` if it reads
  poorly small. Glyph tinted `--sidebar-primary`; "TREZARR" rendered as an
  uppercase pill.

</specifics>

<deferred>
## Deferred Ideas

- NAV-03 nav-row **count badges** (items needing a `vi` sub, auto-hidden at zero)
  and the **LIVE** *arr-connection badge — **Phase 14** (the footer status dot in
  Phase 12 is intentionally the generic running indicator, not this).
- Deleting `Library.tsx` and removing the transitional `/library` route —
  **Phase 14** (after `Series.tsx` + `Movies.tsx` are real and tested).
- Reskinning the existing pages onto shadcn primitives and removing the legacy
  bridge tokens from `tailwind.config.js` — **Phase 15**.

None outside the roadmapped phases — discussion stayed within phase scope.

</deferred>

---

*Phase: 12-app-shell-route-restructure*
*Context gathered: 2026-06-03*
