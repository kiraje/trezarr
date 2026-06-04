# Phase 12: App Shell + Route Restructure - Research

**Researched:** 2026-06-03
**Domain:** React 19 SPA layout/routing — shadcn `Sidebar` shell + react-router-dom v6 layout routes
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (Sidebar interaction model):** shadcn `collapsible="icon"` (icon-rail, ~48px collapsed, nav stays visible). Default state **expanded**. Persistence via shadcn's built-in **cookie** (`sidebar_state`) — no custom store. Toggle affordances: draggable **`SidebarRail`** + **Cmd/Ctrl+B** (vendor defaults); a `SidebarTrigger` in the header is acceptable. Do NOT rely on a top-bar trigger (TopBar removed). Mobile/narrow widths: rely on shadcn's automatic **`Sheet`** behavior — not a primary target but must not break.
- **D-02 (Top bar & service status):** **Drop the 48px TopBar entirely.** Relocate the existing green "service running" status dot into a **`SidebarFooter`** row. In Phase 12 the dot keeps current semantics ("server is serving this page") — it is NOT the NAV-03 LIVE/*arr-connection badge (Phase 14). When collapsed, footer shows just the dot (label hidden).
- **D-03 (`/library` transition):** **Keep `/library` mounted on the existing `Library.tsx`** during the Phase 12–13 transition, but **remove it from the nav** (NAV_ITEMS exposes only the six locked items). `Library.tsx` itself is **untouched** this phase. (Deleting it + removing the route = Phase 14.)
- **D-04 (Route table):** Single layout route `<Route path="/" element={<AppShell/>}>` with children: `index → <Navigate to="/series" replace/>`, `series`, `series/:seriesId`, `movies`, `queue`, `history`, `jobs/:id/logs`, `settings`, `bible`, `bible/:seriesId`, plus the transitional `library` route (D-03). The existing `SPAStaticFiles` fallback already serves `index.html` for all extensionless deep links — **no backend change**.
- **D-05 (Active-state detection):** Derive active from react-router `useLocation` inside `app-sidebar.tsx` and pass to `SidebarMenuButton`'s `isActive` prop. Prefix match: `pathname === to || pathname.startsWith(to + "/")` so `/series/:id` keeps `/series` active and `/bible/:seriesId` keeps `/bible` active. Navigate with `onClick={() => navigate(to)}` (NOT `asChild` + `<a>`).
- **D-06 (Brand):** lucide **`Captions`** glyph + uppercase **"TREZARR"** pill in `SidebarHeader` (NAV-01), glyph tinted `--sidebar-primary` purple, no new image asset. When collapsed, show only the glyph (pill hidden). `Languages` is an approved alternate glyph if `Captions` reads poorly at 16–20px — finalize at UI verify gate.

### Claude's Discretion
- Exact stub-page content for `Series.tsx` / `SeriesDetail.tsx` / `Movies.tsx`: a single heading placeholder is sufficient (Success Criterion 4); a muted "Coming in Phase 14" subline is optional. Stubs must compile and render with no console errors.
- Exact `SidebarHeader` / `SidebarFooter` markup, spacing, and the precise pill styling (within the Phase-11 purple token system).
- Whether to also render a `SidebarTrigger` in the header in addition to the rail (D-01) — chosen ON for ergonomics, finalized at the UI gate.
- Final glyph choice between `Captions` and `Languages` (D-06).

### Deferred Ideas (OUT OF SCOPE)
- **NAV-03** nav-row **count badges** + the **LIVE** *arr-connection badge → Phase 14. (Phase 12's footer dot is the generic running indicator only.)
- **Deleting `Library.tsx`** and removing the transitional `/library` route → Phase 14 (after `Series.tsx` + `Movies.tsx` are real and tested).
- **Reskinning** existing pages onto shadcn primitives and removing legacy bridge tokens from `tailwind.config.js` → Phase 15.
- Backend `GET /api/library/series/{id}/episodes` enrichment → Phase 13.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NAV-01 | Full-height sidebar shell with brand (logo glyph + "TREZARR" pill); active section marked with a **left purple accent bar** | Shell composition (Pattern 1); the **load-bearing accent-bar gap** finding (Pitfall 1 / Code Example 2) — vendor `SidebarMenuButton` `data-[active=true]` is filled-bg only (verified `sidebar.tsx:523`); bar added via `className` on the hand-written `app-sidebar.tsx`. Brand header pattern (Code Example 4). |
| NAV-02 | Nav exposes Series / Movies / Queue / History / Bible / Settings; `/library` splits into `/series` + `/movies`; `/` → `/series` | Layout-route migration (Pattern 2 / Code Example 1); six-item NAV_ITEMS (Code Example 3); `/library` kept as transitional non-nav route (D-03); `SPAStaticFiles` confirms zero backend change for new deep links. |

**NAV-03 is Phase 14 — explicitly out of scope here.**
</phase_requirements>

## Summary

Phase 12 is a pure frontend chrome/routing swap: replace the legacy `AppShell` (48px TopBar + 192px flat `<nav>`, `children`-prop) with a shadcn `SidebarProvider` + hand-written `AppSidebar` + `<main><Outlet/></main>` layout, migrate `App.tsx` to a react-router-dom v6 layout-route table, split `/library` into `/series` + `/movies` + `/series/:seriesId`, redirect `/` → `/series`, and add three heading-only stub pages. No new content, no backend change, no new npm packages — every shadcn primitive was vendored in Phase 11 and verified present (`sidebar.tsx`, `sheet.tsx`, `separator.tsx`, `button.tsx`, `tooltip.tsx`, `skeleton.tsx`, `input.tsx`, `use-mobile.tsx`). The design is fully settled in CONTEXT.md (D-01..D-06), the approved 12-UI-SPEC.md, and ARCHITECTURE.md §2 — this research verifies implementation specifics and the two real risks the planner must encode.

The single load-bearing technical finding (verified in vendor source): the installed `SidebarMenuButton` implements `data-[active=true]` as a **filled background highlight only** (`sidebar.tsx:523` — `data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground`). It does **NOT** render the NAV-01-required left 2px purple accent bar. The bar must be composed onto each `SidebarMenuButton` via a `className` in the hand-written `app-sidebar.tsx` — never by editing the vendor file. The bar composes additively with the vendor's filled background, reproducing the legacy `border-l-2 border-accent bg-bg-stripe` look on the new mechanism.

The second finding de-risks the migration: a grep confirmed **no frontend test infrastructure exists at all** (no vitest/jest/@testing-library, no `test` script in `package.json`) and the only two non-trivial `AppShell` references are `App.tsx` and `AppShell.tsx` themselves. The `children → Outlet` swap (a flagged ARCHITECTURE.md §8 risk) therefore has zero test fallout. Validation is build-gate (`npm run build` = `tsc -b && vite build`) + browser/manual UAT only.

**Primary recommendation:** Implement exactly to 12-UI-SPEC.md §Interaction Contract and ARCHITECTURE.md §2 sketches. Add the accent bar via `className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"` on `SidebarMenuButton` in `app-sidebar.tsx`. Use the layout-route + `<Outlet/>` table from D-04. Preserve all Phase-11 build invariants (`tsc -b && vite build`, no `base` in vite.config, outDir `../trezarr/web/static`, strict TS). No `shadcn add`, no npm install, no backend edits.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Layout chrome (sidebar shell, main region) | Browser / Client (React SPA) | — | Pure client-rendered layout; `SidebarProvider` is whole-document client context. |
| Route table + redirects (`/` → `/series`, layout route) | Browser / Client (react-router-dom) | — | Client-side routing; BrowserRouter owns the route tree. |
| Deep-link refresh on extensionless paths (`/series`, `/movies`, `/series/:id`) | Frontend Server (FastAPI `SPAStaticFiles`) | Browser | Server returns `index.html` for extensionless non-`/api`/`/webhook` paths; client router then resolves the route. **Already handled — no change.** |
| Active-nav detection | Browser / Client (`useLocation` in `app-sidebar.tsx`) | — | Derived from current pathname; not a server concern. |
| Collapse state persistence (`sidebar_state` cookie) | Browser / Client (vendor `SidebarProvider`) | — | `document.cookie` written client-side by the vendor primitive; the cookie is read on next mount, not by the server. |
| Brand glyph + nav icons | Browser / Client (lucide-react) | — | Static client assets; no new image asset (D-06). |
| Service-status dot | Browser / Client (static green dot) | — | Phase-12 dot is a static "server is serving this page" indicator, NOT wired to *arr state (D-02). |

**Key correctness note:** Every capability in this phase lives in the Browser/Client tier. The one server touchpoint (`SPAStaticFiles` deep-link fallback) is pre-existing and requires zero edits. The planner should NOT create any backend task for Phase 12.

## Standard Stack

### Core (all PRE-INSTALLED — no install step this phase)
| Library | Version (installed) | Purpose | Why Standard |
|---------|--------------------|---------|--------------|
| react | ^19.0.0 | SPA runtime | Existing project baseline. `[VERIFIED: frontend/package.json]` |
| react-router-dom | ^6.30.1 | Client routing + layout routes + `<Outlet/>` | v6 layout-route pattern (`<Route element={<Layout/>}>` + nested `<Route>` + `<Outlet/>`) is the canonical replacement for the `children`-prop wrapper. `[VERIFIED: frontend/package.json]` `[CITED: reactrouter.com v6 layout routes]` |
| lucide-react | ^0.511.0 | Icon glyphs (brand + nav) | Already used by current AppShell; `Captions`, `Languages`, `Tv`, `Film`, `List`, `History`, `BookOpen`, `Settings`, `PanelLeft` all confirmed exported by the installed package. No version bump. `[VERIFIED: node_modules/lucide-react grep]` |
| shadcn `sidebar` (vendor) | n/a (copy-in, Phase-11 drop) | The shell primitives: `SidebarProvider`, `Sidebar`, `SidebarContent`, `SidebarHeader`, `SidebarFooter`, `SidebarMenu(Item\|Button)`, `SidebarRail`, `SidebarTrigger`, `SidebarGroup(Label)` | Single 23KB file at `src/components/ui/sidebar.tsx` exporting the full API surface. CSS-var-driven width; manages open/collapsed + cookie + Cmd/Ctrl+B internally. `[VERIFIED: src/components/ui/sidebar.tsx read in full]` |
| vite | ^7.0.0 | Build + dev server | Build is `tsc -b && vite build`; no `base`; outDir `../trezarr/web/static`. `[VERIFIED: frontend/package.json, vite.config.ts]` |
| typescript | ~5.7.2 | Type checking (strict) | `strict`, `noUnusedLocals`, `noUnusedParameters` all `true`; `@/*` alias wired. New files must import only what they use. `[VERIFIED: frontend/tsconfig.json]` |

### Supporting (vendor primitives consumed by the shell — all present)
| Library | Path | Purpose | When to Use |
|---------|------|---------|-------------|
| `sheet` | `ui/sheet.tsx` | Mobile auto-collapse drawer | Consumed internally by `Sidebar` when `useIsMobile()` true; you do not call it directly. |
| `tooltip` | `ui/tooltip.tsx` | Collapsed-rail label tooltips | Pass a `tooltip` prop string to `SidebarMenuButton` so labels show on hover when collapsed (vendor wires the `Tooltip`). |
| `separator` | `ui/separator.tsx` | Optional divider between header/nav/footer | Optional; `SidebarSeparator` wraps it. |
| `button` | `ui/button.tsx` | `SidebarTrigger` styling base | Used internally by `SidebarTrigger`; available to stubs. |
| `use-mobile` | `hooks/use-mobile.tsx` | Mobile breakpoint hook | Imported by `sidebar.tsx`; confirmed present (no missing-import build break). |
| `skeleton` | `ui/skeleton.tsx` | Loading skeleton | Imported by `sidebar.tsx`; confirmed present. |
| `input` | `ui/input.tsx` | `SidebarInput` base | Imported by `sidebar.tsx`; confirmed present. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `onClick={() => navigate(to)}` on `SidebarMenuButton` | `asChild` + `<NavLink>`/`<a>` | D-05 explicitly forbids `asChild`+`<a>`: it fights the Radix Slot model and NavLink can't cleanly set the `data-active` attribute the vendor relies on. Use `navigate(to)` + manual `isActive`. |
| Manual `useLocation` prefix-match for active state | react-router `NavLink` `isActive` | NavLink's `end` prop gives exact-match or full-prefix only; it cannot easily express "`/series` active on `/series/:id` AND `/bible` active on `/bible/:id`" while feeding a shadcn `data-` attribute. Manual prefix-match (D-05) is the prescribed pattern. |
| `collapsible="icon"` | `collapsible="offcanvas"` | D-01 locks `icon` — the rail stays visible at ~48px reclaiming width for Phase-14 dense tables. `offcanvas` would hide nav entirely on collapse. |

**Installation:**
```bash
# NONE. No npm install, no `shadcn add`. All primitives were vendored in Phase 11.
# Verify only:
cd frontend && ls src/components/ui/sidebar.tsx src/components/ui/sheet.tsx \
  src/components/ui/tooltip.tsx src/hooks/use-mobile.tsx
```

**Version verification:** Not applicable for new installs — this phase adds zero dependencies. Installed versions confirmed against `frontend/package.json`: react-router-dom ^6.30.1, lucide-react ^0.511.0, react ^19.0.0, vite ^7.0.0, typescript ~5.7.2. `[VERIFIED: frontend/package.json]`

## Package Legitimacy Audit

> **Not applicable — Phase 12 installs zero external packages.** No `npm install`, no `shadcn add`, no registry fetch. All shadcn primitives were vendored (copy-in) during Phase 11 and are committed to the repo; they are not npm dependencies. `lucide-react` and `react-router-dom` are pre-existing, already-vetted dependencies and are not added or version-bumped this phase.

No new packages → no slopcheck run required and no `checkpoint:human-verify` install gates for the planner to insert.

## Architecture Patterns

### System Architecture Diagram

```
                         Browser hard-refresh on /series/1
                                    │
                                    ▼
              FastAPI  SPAStaticFiles (trezarr/web/app.py)
              extensionless, not /api or /webhook?  ──► returns index.html (200)
                                    │                    [UNCHANGED this phase]
                                    ▼
                      React SPA boots → <BrowserRouter>
                                    │
                                    ▼
                  <Route path="/" element={<AppShell/>}>   ◄── layout route (D-04)
                                    │
                    ┌───────────────┴────────────────────┐
                    ▼                                     ▼
        <SidebarProvider>  (whole-doc context:    matched child route resolves
         open/collapsed + sidebar_state cookie     into <Outlet/>
         + Cmd/Ctrl+B)                                    │
            │                                             │
   ┌────────┴─────────┐                                   ▼
   ▼                  ▼                          one of:
<AppSidebar/>     <main bg-background p-6>       index → <Navigate to="/series"/>
(hand-written)        └── <Outlet/> ◄────────────series · series/:id · movies
   │                                             queue · history · jobs/:id/logs
   ├─ SidebarHeader: Captions glyph + TREZARR pill (D-06)   settings · bible · bible/:id
   ├─ SidebarContent → SidebarMenu                          library (transitional, D-03)
   │     └─ 6× SidebarMenuItem > SidebarMenuButton
   │          isActive = pathname===to || pathname.startsWith(to+"/")  (D-05)
   │          className="border-l-2 border-transparent
   │                     data-[active=true]:border-sidebar-primary"   ◄── ACCENT BAR
   │          onClick={() => navigate(to)}                            (vendor gap fix)
   ├─ SidebarFooter: green dot + "Running" label (D-02)
   └─ SidebarRail (drag to collapse)
```

A reader can trace the primary use case (deep-link to a section, see the right nav item highlighted with the purple bar, render the page in `<Outlet/>`) top-to-bottom by following the arrows. File-to-implementation mapping is in the Component Inventory of 12-UI-SPEC.md.

### Recommended Project Structure
```
frontend/src/
├── components/
│   ├── AppShell.tsx          # REPLACED: SidebarProvider + AppSidebar + main>Outlet
│   ├── app-sidebar.tsx       # NEW (hand-written): brand, 6 nav items, accent bar, footer
│   └── ui/sidebar.tsx        # VENDOR — never edit (accent bar goes on app-sidebar.tsx className)
├── pages/
│   ├── Series.tsx            # NEW STUB: heading placeholder
│   ├── SeriesDetail.tsx      # NEW STUB: heading placeholder (may echo :seriesId)
│   ├── Movies.tsx            # NEW STUB: heading placeholder
│   └── Library.tsx           # UNTOUCHED — kept reachable at /library (D-03)
└── App.tsx                   # MODIFIED: layout-route table; / → /series
```

### Pattern 1: SidebarProvider + Outlet shell (D-04, ARCHITECTURE.md §2)
**What:** `AppShell` becomes a thin layout host: `<SidebarProvider><AppSidebar/><main className="flex-1 overflow-auto bg-background p-6"><Outlet/></main></SidebarProvider>`. `SidebarProvider` is whole-document context — not per-route.
**When to use:** As the single layout route element wrapping all pages.
**Note on the wrapper div:** `SidebarProvider` renders a `flex min-h-svh w-full` wrapper; `Sidebar` renders a `fixed` overlay + a width-reserving spacer; `<main className="flex-1 ...">` is the flex sibling that fills remaining width. Do NOT wrap `<main>` in extra `flex` containers or hardcode `w-48` — the vendor manages width via `--sidebar-width`/`--sidebar-width-icon` CSS vars. `[CITED: src/components/ui/sidebar.tsx lines 136–266]`

### Pattern 2: react-router-dom v6 layout route (D-04)
**What:** Replace `<AppShell>{children}</AppShell>` wrapping `<Routes>` with a nested route tree: `<Route path="/" element={<AppShell/>}>` containing child `<Route>`s, where `AppShell` renders `<Outlet/>` for the matched child. Child paths are **relative** (no leading slash): `series`, not `/series`. The default uses `<Route index element={<Navigate to="/series" replace/>}/>`.
**When to use:** The whole `App.tsx` rewrite.
**Example:** See Code Example 1.

### Pattern 3: Active-state via useLocation prefix-match + isActive prop (D-05)
**What:** Inside `app-sidebar.tsx`, read `const { pathname } = useLocation()`; for each nav item compute `isActive = pathname === to || pathname.startsWith(to + "/")` and pass it to `SidebarMenuButton`'s `isActive` prop (vendor maps it to `data-active`). The `+ "/"` guard prevents `/series` matching `/seriesextra` and keeps `/series` active on `/series/1`.
**When to use:** Every nav item.

### Anti-Patterns to Avoid
- **Editing `src/components/ui/sidebar.tsx`** to add the accent bar: vendor file, never hand-edit (Wiring Invariant). The bar belongs on `app-sidebar.tsx` via `className`.
- **`asChild` + `<a>`/`<NavLink>` on `SidebarMenuButton`:** D-05 forbids it — fights the Radix Slot model and breaks `data-active`. Use `onClick={() => navigate(to)}`.
- **Hardcoding `w-48` / fixed pixel sidebar widths:** the vendor uses `--sidebar-width` (16rem) and `--sidebar-width-icon` (3rem); hardcoding breaks the collapse geometry.
- **Adding `base` to vite.config.ts:** breaks FastAPI's root-mount absolute-path asset serving (vite.config has an explicit comment forbidding it). Preserve as-is.
- **Adding `/library` to NAV_ITEMS:** D-03 keeps it reachable but NOT in the nav.
- **Wiring the footer dot to *arr connection state:** that is NAV-03 / Phase 14. Keep it the static green "server is serving" dot.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Collapse/expand state + persistence | Custom React state + localStorage + a custom toggle | Vendor `SidebarProvider` (manages `open`/`collapsed`, writes `sidebar_state` cookie, binds Cmd/Ctrl+B) | The primitive already does all of it (`sidebar.tsx:79–117`); `defaultOpen` defaults to `true` (D-01 expanded). `[VERIFIED: sidebar.tsx]` |
| Mobile drawer behavior | Custom media-query + slide-in panel | Vendor `Sidebar` auto-switches to `Sheet` when `useIsMobile()` is true | Built-in (`sidebar.tsx:199–221`); D-01 says rely on it. |
| Collapsed-rail tooltips | Custom hover tooltip | Pass `tooltip="Label"` to `SidebarMenuButton` (vendor renders `Tooltip`, hidden unless `state==="collapsed"`) | `sidebar.tsx:578–598`. |
| Keyboard shortcut | Custom `keydown` listener for Cmd/Ctrl+B | Vendor's built-in `SIDEBAR_KEYBOARD_SHORTCUT = "b"` | `sidebar.tsx:104–117`; D-01 keeps the default. |
| Active-route highlight | Re-implement route matching | `useLocation` + the prefix-match expression (D-05) | One-line expression; no library needed. |
| Layout/outlet plumbing | Manual context to pass children through | react-router `<Outlet/>` under a layout route | Canonical v6 pattern. |

**Key insight:** Phase 12 is almost entirely *composition* of already-installed primitives. The ONLY thing the vendor does not give you is the left purple accent bar (NAV-01) — and that is deliberately a one-line `className`, not a fork of the vendor file.

## Common Pitfalls

### Pitfall 1: Active accent bar silently missing (THE load-bearing risk for NAV-01)
**What goes wrong:** You set `isActive` correctly, the row gets a filled purple-tinted background, and you assume NAV-01 is satisfied. It is not — there is no left 2px purple bar, so the headline visual contract fails verification.
**Why it happens:** The vendor `sidebarMenuButtonVariants` (`sidebar.tsx:523`) implements `data-[active=true]` as **filled background + font-medium + accent-foreground only**:
`...data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground...` — **no `border-l`**. `[VERIFIED: src/components/ui/sidebar.tsx:523]`
**How to avoid:** Add the bar via `className` on each `SidebarMenuButton` in `app-sidebar.tsx`:
`className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"`.
The transparent default border reserves the 2px so there is no layout shift on activation; the active state lights it `--sidebar-primary` (purple). `cn()` merges this after the variant string so it composes additively with the filled background. The combined active look = purple left bar + subtle purple-tinted bg = the legacy `border-l-2 border-accent bg-bg-stripe` look on the new mechanism.
**Warning signs:** UAT step SC-2 ("active item shows a left 2px purple accent bar") fails; only a background tint is visible.

### Pitfall 2: Light-mode flash / wrong colors if `.dark` is dropped
**What goes wrong:** Sidebar renders white card backgrounds / black text.
**Why it happens:** shadcn uses `darkMode: ["class"]`; all `--sidebar-*` values are defined under the dark scope and require `class="dark"` on `<html>`.
**How to avoid:** Leave `frontend/index.html` `<html lang="en" class="dark">` intact (Phase-11 set it; **verified present**). Do not remove it. `[VERIFIED: frontend/index.html:2]`
**Warning signs:** Visible only in a browser, not in the headless build — must be checked at the UAT gate.

### Pitfall 3: Child route paths written with leading slash
**What goes wrong:** Nested routes under `<Route path="/">` 404 or mis-resolve.
**Why it happens:** In a v6 nested route tree, child `path` values are **relative** to the parent. Writing `path="/series"` (absolute) inside `path="/"` is invalid/ambiguous.
**How to avoid:** Use `path="series"`, `path="series/:seriesId"`, `path="movies"`, `path="queue"`, etc. The redirect uses `<Route index element={<Navigate to="/series" replace/>}/>` (the `to` target IS absolute — it's a navigation target, not a route path).
**Warning signs:** A route renders blank or the index redirect loops.

### Pitfall 4: `tsc -b` strict failures on stubs and the new sidebar
**What goes wrong:** Build fails on `noUnusedLocals`/`noUnusedParameters`.
**Why it happens:** `strict`, `noUnusedLocals`, `noUnusedParameters` are all `true`. Importing an icon you don't use, or a `SeriesDetail` that imports `useParams` but doesn't read it, fails the build.
**How to avoid:** Import only used icons; in `SeriesDetail.tsx` either read the `:seriesId` param (`const { seriesId } = useParams()`) or don't import `useParams`. Stubs must be self-contained and compile clean. `[VERIFIED: frontend/tsconfig.json]`
**Warning signs:** `tsc -b` errors `'X' is declared but its value is never read`.

### Pitfall 5: Re-introducing a `tsconfig.app.json` / project-reference split
**What goes wrong:** Adding files that assume a `tsconfig.app.json` + `tsconfig.node.json` references layout (as ARCHITECTURE.md §3 Step 1 generically describes) will not match this project.
**Why it happens:** This project uses a **single flat `frontend/tsconfig.json`** (`strict`, `@/*` alias, `include: ["src"]`) — there is no `tsconfig.app.json`. The `@/*` alias and strict flags are already present from Phase 11.
**How to avoid:** Do not create or modify tsconfig files this phase. The alias is already wired; no tsconfig change is needed. `[VERIFIED: frontend/tsconfig.json is the only tsconfig; tsconfig.app.json does not exist]`

## Code Examples

### Example 1: App.tsx — layout-route table (D-04)
```tsx
// frontend/src/App.tsx (target shape; child paths are RELATIVE — no leading slash)
// Source: ARCHITECTURE.md §2 "After (v1.1)"; D-04
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import Series from "./pages/Series";
import SeriesDetail from "./pages/SeriesDetail";
import Movies from "./pages/Movies";
import Queue from "./pages/Queue";
import History from "./pages/History";
import JobLogs from "./pages/JobLogs";
import Settings from "./pages/Settings";
import BibleList from "./pages/BibleList";
import BibleEditor from "./pages/BibleEditor";
import Library from "./pages/Library"; // transitional (D-03)

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<Navigate to="/series" replace />} />
          <Route path="series" element={<Series />} />
          <Route path="series/:seriesId" element={<SeriesDetail />} />
          <Route path="movies" element={<Movies />} />
          <Route path="queue" element={<Queue />} />
          <Route path="history" element={<History />} />
          <Route path="jobs/:id/logs" element={<JobLogs />} />
          <Route path="settings" element={<Settings />} />
          <Route path="bible" element={<BibleList />} />
          <Route path="bible/:seriesId" element={<BibleEditor />} />
          <Route path="library" element={<Library />} /> {/* transitional, not in nav (D-03) */}
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

### Example 2: AppShell.tsx — thin layout host (D-04, Pattern 1)
```tsx
// frontend/src/components/AppShell.tsx (REPLACED)
// Source: ARCHITECTURE.md §2 "AppShell.tsx — v1.1 shape"
import { Outlet } from "react-router-dom";
import { SidebarProvider } from "./ui/sidebar";
import { AppSidebar } from "./app-sidebar";

export default function AppShell() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="flex-1 overflow-auto bg-background p-6">
        <Outlet />
      </main>
    </SidebarProvider>
  );
}
```

### Example 3: app-sidebar.tsx — nav + accent bar + brand + footer (D-01/02/05/06, NAV-01/02)
```tsx
// frontend/src/components/app-sidebar.tsx (NEW, hand-written)
// Source: ARCHITECTURE.md §2 sketch + 12-UI-SPEC §Interaction Contract; accent bar is the
// Phase-12 load-bearing fix for the vendor gap at ui/sidebar.tsx:523.
import { useLocation, useNavigate } from "react-router-dom";
import { Captions, Tv, Film, List, History, BookOpen, Settings } from "lucide-react";
import {
  Sidebar, SidebarHeader, SidebarContent, SidebarFooter,
  SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarRail, SidebarTrigger,
} from "./ui/sidebar";

const NAV_ITEMS = [
  { to: "/series",   label: "Series",   icon: Tv },
  { to: "/movies",   label: "Movies",   icon: Film },
  { to: "/queue",    label: "Queue",    icon: List },
  { to: "/history",  label: "History",  icon: History },
  { to: "/bible",    label: "Bible",    icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function AppSidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-1">
          <Captions className="text-sidebar-primary" size={20} />
          {/* pill hidden when collapsed via group-data-[collapsible=icon]:hidden */}
          <span className="font-semibold uppercase tracking-wide text-sm
                           group-data-[collapsible=icon]:hidden">
            TREZARR
          </span>
          {/* Optional in-header trigger (D-01, discretion ON) */}
          <SidebarTrigger className="ml-auto group-data-[collapsible=icon]:hidden" />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarMenu>
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
            const isActive = pathname === to || pathname.startsWith(to + "/");
            return (
              <SidebarMenuItem key={to}>
                <SidebarMenuButton
                  isActive={isActive}
                  tooltip={label}                       // shows when collapsed
                  onClick={() => navigate(to)}          // NOT asChild + <a> (D-05)
                  // THE ACCENT BAR — vendor gives only a filled bg; add the 2px bar here:
                  className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter>
        <div className="flex items-center gap-2 px-2">
          <span className="h-2 w-2 rounded-full bg-[#22c55e]"
                aria-label="Service status: running" />
          <span className="text-sm text-muted-foreground
                           group-data-[collapsible=icon]:hidden">
            Running
          </span>
        </div>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
```
> Note: the `group-data-[collapsible=icon]:hidden` utility hides the label/pill when collapsed because the vendor `Sidebar` sets `data-collapsible="icon"` on the outer `group` wrapper (`sidebar.tsx:228`). This is the same mechanism the vendor uses for `SidebarGroupLabel`.

### Example 4: Stub page (Claude's discretion; Success Criterion 4)
```tsx
// frontend/src/pages/Series.tsx (NEW STUB) — Movies.tsx is identical with "Movies"
export default function Series() {
  return (
    <div>
      <h1 className="text-xl font-semibold">Series</h1>
      <p className="text-muted-foreground">Coming in Phase 14</p> {/* optional */}
    </div>
  );
}

// frontend/src/pages/SeriesDetail.tsx — may echo the param (read it to satisfy noUnusedLocals)
import { useParams } from "react-router-dom";
export default function SeriesDetail() {
  const { seriesId } = useParams();
  return (
    <div>
      <h1 className="text-xl font-semibold">Series Detail</h1>
      <p className="text-muted-foreground">Series #{seriesId} — coming in Phase 14</p>
    </div>
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `<AppShell>{children}</AppShell>` wrapping `<Routes>` | `<Route element={<AppShell/>}>` + `<Outlet/>` layout route | react-router v6 (stable since 2021); applied here in Phase 12 | The `children` prop is removed; pages render via `<Outlet/>`. No test fallout (no tests mount AppShell). |
| 48px TopBar + 192px flat `<nav>` | Full-height shadcn `SidebarProvider` shell | Phase 12 (this) | TopBar dropped (D-02); brand + status move into the sidebar. |
| Blue accent (`#3b82f6`), hardcoded hex active styling | Purple `--sidebar-primary` accent + CSS-var theme | Phase 11 (theme), Phase 12 (accent bar on new mechanism) | Active styling now data-attribute driven; bar added via className. |

**Deprecated/outdated:**
- The `children`-prop `AppShell` signature (`interface AppShellProps { children: ReactNode }`) — replaced by the no-prop `<Outlet/>` host.
- `/` → `/queue` redirect — replaced by `/` → `/series` (D-04, NAV-02).
- `NavLink`-based active class in the old AppShell — replaced by `useLocation` prefix-match feeding `isActive`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `cn()` (tailwind-merge) merges the appended `border-l-2 ...` className additively with the vendor variant string without clobbering the filled-bg classes (different properties → both survive). | Pitfall 1 / Code Example 3 | LOW — `border-*` and `bg-*`/`text-*`/`font-*` are distinct property groups; tailwind-merge does not drop across groups. If wrong, the bar simply won't show and the UAT gate catches it. |
| A2 | `group-data-[collapsible=icon]:hidden` on the brand pill / footer label / header trigger correctly hides them in the collapsed rail (the `data-collapsible="icon"` group attribute is on an ancestor of these hand-written children). | Code Example 3 | LOW — verified the vendor sets `data-collapsible` on the `group peer` wrapper (`sidebar.tsx:228`) that contains `SidebarHeader`/`Content`/`Footer`; same mechanism the vendor itself uses for `SidebarGroupLabel`. UAT step 5/6/2 confirms visually. |
| A3 | `tsc -b` against the single flat `tsconfig.json` (no project references / no `tsconfig.node.json`) is the established passing build and new files just need to satisfy it. | Pitfall 4/5 | LOW — Phase 11 shipped green with this exact layout; this phase adds no tsconfig change. |
| A4 | Glyph default `Captions` reads acceptably at 16–20px; `Languages` is the fallback. | D-06 / Brand | NONE for planning — explicitly Claude's discretion, finalized at UI gate. |

**Note:** All structural/behavioral claims are VERIFIED against vendor source or project files. The four entries above are the only non-verified items and all are LOW/NONE risk, resolved at the build or UAT gate.

## Open Questions

1. **Does the in-header `SidebarTrigger` duplicate the rail affordance confusingly?**
   - What we know: D-01 permits a header trigger; UI-SPEC records it as "ON for ergonomics."
   - What's unclear: whether two affordances (rail + header button) feel redundant.
   - Recommendation: Ship both per the recorded discretion; finalize at the UI verify gate. Not a blocker.

2. **Should the collapsed footer dot keep a tooltip ("Running")?**
   - What we know: D-02 says collapsed shows just the dot (label hidden).
   - What's unclear: whether a hover tooltip on the dot is desired when collapsed.
   - Recommendation: Optional; add `title="Service running"` (cheap, no new dep) — matches the existing AppShell which already had a `title`. Not a blocker.

## Environment Availability

> Phase 12 is a code-only frontend change with no new external dependencies. The only relevant tooling is the existing build chain.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| node / npm | `npm run build` (`tsc -b && vite build`) | ✓ (project already builds; Phase 11 shipped) | per project | — |
| react-router-dom | layout route + `<Outlet/>` | ✓ pre-installed | ^6.30.1 | — |
| lucide-react | brand + nav glyphs | ✓ pre-installed | ^0.511.0 | — |
| shadcn sidebar/sheet/tooltip/etc. | the shell | ✓ vendored Phase 11 (files verified present) | n/a (copy-in) | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | **NONE for frontend.** No vitest/jest/@testing-library installed; no `test` script in `frontend/package.json`. `[VERIFIED: package.json + grep src/]` |
| Config file | none |
| Quick run command | `cd frontend && npm run build` (this IS the automated gate — `tsc -b` strict + `vite build`) |
| Full suite command | `cd frontend && npm run build` (build is the only automated check) |

> **Verified:** the only two files matching test-ish substrings (`JobTable.tsx`, `BibleEditor.tsx`) contain no `describe`/`it`/`test`/vitest/@testing-library imports — they are source files with incidental substrings, NOT tests. There is genuinely no frontend test harness. Standing up vitest is explicitly out of scope (no requirement asks for it; the project shipped Phases 1–11 with build-gate + manual UAT). Validation for NAV-01/NAV-02 is therefore: automated build-gate for compile/strict correctness + browser/manual UAT for the visual + interaction contract.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NAV-02 | Project compiles after route restructure (strict TS, no unused) | build (proxy) | `cd frontend && npm run build` | ✅ build script |
| NAV-02 | `/` redirects to `/series` | manual UAT | visit `/`, observe redirect to `/series` | n/a (manual) |
| NAV-02 | Deep-link refresh works on all 6 nav routes + `/series/:id` | manual UAT | hard-refresh each of `/series`,`/movies`,`/queue`,`/history`,`/bible`,`/settings`,`/series/1` → correct page (SPA fallback) | n/a (manual) |
| NAV-02 | Nav exposes exactly the six items in order; `/library` NOT in nav but reachable | manual UAT | inspect sidebar; visit `/library` directly → Library page renders | n/a (manual) |
| NAV-01 | Full-height sidebar shell with brand (Captions glyph + "TREZARR" pill) | manual UAT | observe sidebar on every page | n/a (manual) |
| NAV-01 | **Active item shows a left 2px purple accent bar** (the headline check — vendor does NOT provide it) | manual UAT | navigate sections; confirm purple left bar on active item (not just a bg tint) | n/a (manual) |
| (SC-3) | Existing pages (Queue/History/Settings/BibleList/BibleEditor/JobLogs) functional inside the shell, no regressions | manual UAT | navigate each; verify functionality | n/a (manual) |
| (SC-4) | Stub pages `/series`,`/series/:id`,`/movies` render a heading with no console errors | manual UAT | visit each; check DevTools console clean | n/a (manual) |
| (D-01) | Cmd/Ctrl+B and `SidebarRail` collapse to 48px icon rail; accent bar still shows; `sidebar_state` cookie persists across reload | manual UAT | toggle; reload; confirm persisted state | n/a (manual) |
| (D-02) | Green "Running" dot in `SidebarFooter`; label hidden when collapsed | manual UAT | observe footer expanded + collapsed | n/a (manual) |

### Sampling Rate
- **Per task commit:** `cd frontend && npm run build` (must exit 0; `tsc -b` strict clean; `trezarr/web/static/` populated)
- **Per wave merge:** `cd frontend && npm run build`
- **Phase gate:** Build green + full browser UAT checklist above before `/gsd-verify-work`

### Wave 0 Gaps
- None. No test infrastructure is required or expected for this phase; introducing vitest is out of scope. The automated gate is the existing `npm run build`; behavioral/visual verification is the documented manual UAT checklist (mirrors 12-UI-SPEC §Phase-End Verification Contract).

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1` in config. Phase 12 is a client-side layout/routing change with no new data flows, no auth changes, no new inputs, no crypto, and no backend edits. Most ASVS categories are N/A; the relevant ones are inherited and unchanged.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth touched; *arr API-key auth lives in backend/settings, untouched. |
| V3 Session Management | no | No sessions; the only cookie is the vendor `sidebar_state` UI-preference cookie (non-sensitive, no auth value). |
| V4 Access Control | no | No new endpoints/routes on the server; client routes expose no new authorization surface. SPA routes are served identically by the existing `SPAStaticFiles` fallback. |
| V5 Input Validation | no | No new user inputs introduced (nav + stubs only). `:seriesId`/`:id` params are echoed at most into a stub heading; React escapes text by default (no `dangerouslySetInnerHTML`) → no XSS sink. |
| V6 Cryptography | no | No crypto. |
| V13 API/Web Service | no | No backend/API change; the `/series`,`/movies` deep links are served by the pre-existing static fallback. |

### Known Threat Patterns for React SPA route/shell change

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Reflected XSS via echoed route param (`:seriesId` in a stub heading) | Tampering | Render via JSX text interpolation (auto-escaped); never `dangerouslySetInnerHTML`. The stub example reads `seriesId` into a text node only — safe by default. |
| Open redirect via `/` → target | Spoofing | The redirect target is the hardcoded literal `/series` (`<Navigate to="/series" replace/>`) — not user-controlled. No risk. |
| Sensitive data in the `sidebar_state` cookie | Info disclosure | The vendor cookie stores only `true`/`false` (open/collapsed) with `path=/; max-age=7d` — no PII, no auth token. Acceptable as-is; do not store anything else in it. |

**Net:** No new security obligations for Phase 12. Maintain the React default-escaping posture (no raw HTML injection) and keep the redirect target a literal. `security_block_on: high` — there are no high findings in scope.

## Sources

### Primary (HIGH confidence)
- `frontend/src/components/ui/sidebar.tsx` (read in full) — vendor API surface, `--sidebar-width`/`--sidebar-width-icon`, `sidebar_state` cookie (lines 26–31, 79–117), Cmd/Ctrl+B shortcut, mobile `Sheet` switch (199–221), tooltip on collapsed (578–598), and the **accent-bar gap** at line 523 (`data-[active=true]:bg-sidebar-accent` filled-bg only, no `border-l`). HIGH.
- `frontend/package.json` — react-router-dom ^6.30.1, lucide-react ^0.511.0, react ^19.0.0, vite ^7.0.0, typescript ~5.7.2; build = `tsc -b && vite build`; NO vitest/jest/@testing-library, no `test` script. HIGH.
- `frontend/tsconfig.json` — single flat config; `strict`/`noUnusedLocals`/`noUnusedParameters` true; `@/*` alias wired. HIGH.
- `frontend/index.html` — `<html lang="en" class="dark">` present. HIGH.
- `frontend/vite.config.ts` — no `base`; outDir `../trezarr/web/static`; `@` alias to `./src`. HIGH.
- `frontend/src/components/AppShell.tsx` + `App.tsx` — current TopBar+nav+children shell and `/` → `/queue` route table to replace. HIGH.
- `node_modules/lucide-react` grep — `Captions`, `Languages`, `Tv`, `Film`, `List`, `History`, `BookOpen`, `Settings`, `PanelLeft` all exported. HIGH.
- `trezarr/web/app.py` — `SPAStaticFiles` returns `index.html` for extensionless non-`/api`/`/webhook` paths (lines 48–80) → new `/series`,`/series/:id`,`/movies` deep links covered with zero backend change. HIGH.
- `.planning/research/ARCHITECTURE.md` §2/§6/§8 — authoritative layout-route + `<Outlet/>` design, before/after route tables, `app-sidebar.tsx` sketch, `children→Outlet` risk (confirmed N/A). HIGH.
- `.planning/phases/12-app-shell-route-restructure/12-CONTEXT.md` + `12-UI-SPEC.md` — locked decisions D-01..D-06 and the approved interaction/visual contract incl. the verified accent-bar gap + className remedy. HIGH.
- `.planning/REQUIREMENTS.md` — NAV-01/02 (Phase 12), NAV-03 (Phase 14). HIGH.
- `.planning/config.json` — `nyquist_validation: true`, `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high`, `ui_phase: true`. HIGH.

### Secondary (MEDIUM confidence)
- react-router-dom v6 layout-route + `<Outlet/>` pattern (well-established RRv6 API; relative child paths; `<Route index>` redirect). MEDIUM (standard pattern; not re-fetched from docs this session — matches ARCHITECTURE.md §2 and current code usage).

### Tertiary (LOW confidence)
- None. (All findings cross-verified against vendor source or project files.)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions read from `package.json`; all primitives verified present on disk; zero new installs.
- Architecture: HIGH — design pre-settled in CONTEXT/UI-SPEC/ARCHITECTURE and the one novel mechanism (accent bar) verified against vendor line 523.
- Pitfalls: HIGH — accent-bar gap, `.dark` requirement, relative child paths, strict-TS, and the single-tsconfig layout all verified directly.
- Validation: HIGH — absence of any frontend test harness confirmed by grep + `package.json`; UAT checklist mirrors the approved UI-SPEC verification contract.

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (stable — vendored primitives are pinned copy-in files; no fast-moving external dependency)
