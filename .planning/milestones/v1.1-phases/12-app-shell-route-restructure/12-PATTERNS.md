# Phase 12: App Shell + Route Restructure - Pattern Map

**Mapped:** 2026-06-03
**Files analyzed:** 6 (2 replaced/modified, 1 new component, 3 new stub pages)
**Analogs found:** 6 / 6 (every new/modified file has a direct in-codebase analog)

> Phase 12 is a pure-frontend composition phase. Every file has a strong existing
> analog in `frontend/src/` — there are **no "no analog" files** and no backend
> files. The single novel mechanism (the left 2px purple accent bar) is composed
> via `className` onto the vendor primitive; the legacy `AppShell.tsx` is the exact
> source for that bar's look.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `frontend/src/components/AppShell.tsx` (REPLACED) | layout shell | request-response (route render) | itself (current `AppShell.tsx`) + vendor `ui/sidebar.tsx` | exact (same file, role-preserving rewrite) |
| `frontend/src/components/app-sidebar.tsx` (NEW) | nav component | event-driven (click→navigate) + transform (pathname→isActive) | current `AppShell.tsx` `NavItem` + vendor `ui/sidebar.tsx` `SidebarMenuButton` | exact (role + data-flow) |
| `frontend/src/App.tsx` (MODIFIED) | route table / provider | request-response (route dispatch) | itself (current `App.tsx` `<Routes>`) | exact (same file, layout-route rewrite) |
| `frontend/src/pages/Series.tsx` (NEW STUB) | page | none (static render) | `frontend/src/pages/Queue.tsx` (heading block) | role-match (simplified) |
| `frontend/src/pages/Movies.tsx` (NEW STUB) | page | none (static render) | `frontend/src/pages/Queue.tsx` (heading block) | role-match (simplified) |
| `frontend/src/pages/SeriesDetail.tsx` (NEW STUB) | page (param) | transform (`:seriesId`→text) | `frontend/src/pages/JobLogs.tsx` (`useParams` pattern) | role-match (param read) |

---

## Pattern Assignments

### `frontend/src/components/AppShell.tsx` (REPLACED — layout shell)

**Analog:** the current `frontend/src/components/AppShell.tsx` itself (role preserved: it stays the single layout host) + vendor `frontend/src/components/ui/sidebar.tsx` for the new primitive composition.

**What to KEEP from the current file:**
- The file-header docstring convention (a JSDoc block citing the UI-SPEC and the active-nav contract) — every component/page in this codebase opens with one. Update it to cite `12-UI-SPEC.md §Interaction Contract`.
- The green status-dot literal `bg-[#22c55e]` and its `aria-label="Service status: running"` / `title="Service running"` — these move into `app-sidebar.tsx`'s `SidebarFooter`, NOT this file (see D-02 / app-sidebar assignment below).

**What to DELETE (the delta):**
- The `interface AppShellProps { children: ReactNode }` and the `children` prop — replaced by a no-prop `<Outlet/>` host.
- The entire `<header className="h-12 ...">` TopBar block (current lines 61-70) — TopBar dropped (D-02).
- The inline `<nav>` + `NavItem` markup (current lines 27-103) — moves into the new hand-written `app-sidebar.tsx`.
- The hardcoded `w-48` sidebar width — vendor manages width via `--sidebar-width` CSS vars (Wiring Invariant).

**Current shell structure being replaced** (`AppShell.tsx:58-112`):
```tsx
export default function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex flex-col min-h-screen bg-bg-base">
      <header className="h-12 bg-bg-surface ...">  {/* DROP: TopBar (D-02) */}
        <span ...>Trezarr</span>
        <div className="w-2 h-2 rounded-full bg-[#22c55e]" .../>  {/* RELOCATE to SidebarFooter */}
      </header>
      <div className="flex flex-1">
        <nav className="w-48 ..." aria-label="Primary navigation">...</nav>  {/* MOVE to app-sidebar.tsx */}
        <main className="flex-1 bg-bg-base px-8 py-6 overflow-auto">
          {children}  {/* REPLACE with <Outlet/> */}
        </main>
      </div>
    </div>
  );
}
```

**Target shape** (RESEARCH §Code Example 2; UI-SPEC §Interaction Contract 1):
```tsx
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
> Note the `<main>` background changes from the legacy `bg-bg-base px-8 py-6` to `bg-background p-6` (purple-tinted root; Wiring Invariant "`<main>` uses `bg-background`"). Do NOT wrap `<main>` in extra flex containers or set `w-48` — `SidebarProvider` already renders the `flex min-h-svh w-full` wrapper and `Sidebar` reserves width (vendor `sidebar.tsx:136-266`).

---

### `frontend/src/components/app-sidebar.tsx` (NEW — nav component)

**Primary analog:** the current `AppShell.tsx` `NavItem` function (`AppShell.tsx:27-56`) — it is the direct source for the active-state look, the lucide icon usage, and the left-2px-accent-border pattern.
**Secondary analog:** vendor `frontend/src/components/ui/sidebar.tsx` `SidebarMenuButton` API (`sidebar.tsx:544-601`) — the primitive this nav composes onto.

**Imports pattern** (copy lucide + react-router import style from current `AppShell.tsx:13-14` and `JobLogs.tsx:11`):
```tsx
import { useLocation, useNavigate } from "react-router-dom";
import { Captions, Tv, Film, List, History, BookOpen, Settings } from "lucide-react";
import {
  Sidebar, SidebarHeader, SidebarContent, SidebarFooter,
  SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarRail, SidebarTrigger,
} from "./ui/sidebar";
```
> Strict-TS guard (Pitfall 4): import ONLY these icons; every one is used by a nav row or the brand. `Settings`/`List`/`History`/`BookOpen`/`Film` were already imported by the old AppShell — `Captions`/`Tv` are the only additions. All confirmed exported by `lucide-react ^0.511.0`.

**THE ACCENT-BAR PATTERN — the load-bearing delta (NAV-01).** The current `NavItem` produced the active look with a hardcoded class string (`AppShell.tsx:43-50`):
```tsx
// CURRENT (legacy NavLink mechanism) — AppShell.tsx:43-50
className={({ isActive }) =>
  isActive
    ? "border-l-2 border-accent bg-bg-stripe text-[#e2e6f0] pl-[14px]"
    : "... border-l-2 border-transparent pl-[14px]"
}
```
The vendor `SidebarMenuButton` does NOT carry this bar. Verified at `sidebar.tsx:523`, its `data-[active=true]` is **filled background only**:
```
... data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground ...   // NO border-l
```
So reproduce the legacy `border-l-2 border-accent` look by adding a `className` on each `SidebarMenuButton` (the `cn()` merge at `sidebar.tsx:573` composes it additively after the variant string — distinct property groups, neither clobbers the other):
```tsx
className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"
```
The transparent default border reserves the 2px (no layout shift on activation) — directly mirroring the legacy `border-l-2 border-transparent` inactive state. `--sidebar-primary` (purple) replaces the legacy `border-accent` (blue). This is the single thing the planner must not let slip — it is the headline UAT check (SC-2).

**Active-route matching — transform pattern (D-05).** The old `NavLink` used react-router's built-in `isActive`. Replace with `useLocation` prefix-match so nested routes keep the parent active:
```tsx
const { pathname } = useLocation();
const navigate = useNavigate();
// per item:
const isActive = pathname === to || pathname.startsWith(to + "/");
```
Pass `isActive` to the vendor `SidebarMenuButton` `isActive` prop (`sidebar.tsx:548`, maps to `data-active`). Navigate via `onClick={() => navigate(to)}` (D-05 forbids `asChild` + `<a>` — fights the Radix Slot at `sidebar.tsx:564`).

**Core nav pattern** (RESEARCH §Code Example 3; the `NAV_ITEMS` table is locked in UI-SPEC §Interaction Contract 4):
```tsx
const NAV_ITEMS = [
  { to: "/series",   label: "Series",   icon: Tv },
  { to: "/movies",   label: "Movies",   icon: Film },
  { to: "/queue",    label: "Queue",    icon: List },
  { to: "/history",  label: "History",  icon: History },
  { to: "/bible",    label: "Bible",    icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;
// ...
<Sidebar collapsible="icon">
  ...
  <SidebarContent>
    <SidebarMenu>
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
        const isActive = pathname === to || pathname.startsWith(to + "/");
        return (
          <SidebarMenuItem key={to}>
            <SidebarMenuButton
              isActive={isActive}
              tooltip={label}                  // vendor shows it only when collapsed (sidebar.tsx:578-598)
              onClick={() => navigate(to)}
              className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"
            >
              <Icon size={16} />               {/* same 16px size as legacy NavItem icons */}
              <span>{label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  </SidebarContent>
  ...
  <SidebarRail />
</Sidebar>
```
> D-03: do NOT add `/library` to `NAV_ITEMS` — exactly these six items, this order. (The old AppShell listed Settings/Queue/Library/History/Bible; the order and membership change here.)

**Brand header pattern (D-06).** No legacy analog for the glyph+pill — the old TopBar had a plain `<span>Trezarr</span>` (`AppShell.tsx:63`). New brand uses lucide `Captions` tinted `text-sidebar-primary` + uppercase "TREZARR" pill, hidden when collapsed:
```tsx
<SidebarHeader>
  <div className="flex items-center gap-2 px-1">
    <Captions className="text-sidebar-primary" size={20} />
    <span className="font-semibold uppercase tracking-wide text-sm group-data-[collapsible=icon]:hidden">
      TREZARR
    </span>
    <SidebarTrigger className="ml-auto group-data-[collapsible=icon]:hidden" />  {/* discretion ON */}
  </div>
</SidebarHeader>
```

**Footer status row pattern (D-02) — copy the dot verbatim from legacy AppShell.** The green dot literal, aria-label, and title come straight from `AppShell.tsx:64-69`:
```tsx
<SidebarFooter>
  <div className="flex items-center gap-2 px-2">
    <span className="h-2 w-2 rounded-full bg-[#22c55e]"
          aria-label="Service status: running" title="Service running" />
    <span className="text-sm text-muted-foreground group-data-[collapsible=icon]:hidden">Running</span>
  </div>
</SidebarFooter>
```
> Keep its current static "server is serving" semantics — do NOT wire it to *arr state (that is NAV-03 / Phase 14). The `group-data-[collapsible=icon]:hidden` utility hides the label/pill in the icon rail (same mechanism the vendor uses for `SidebarGroupLabel`; the `data-collapsible` attr is set on the group wrapper at `sidebar.tsx:228`).

---

### `frontend/src/App.tsx` (MODIFIED — route table)

**Analog:** the current `App.tsx` `<Routes>` block itself (`App.tsx:25-43`).

**Current pattern (children-prop wrapper)** — `App.tsx:27-41`:
```tsx
<BrowserRouter>
  <AppShell>
    <Routes>
      <Route path="/" element={<Navigate to="/queue" replace />} />   {/* CHANGE target → /series */}
      <Route path="/settings" element={<Settings />} />
      <Route path="/queue" element={<Queue />} />
      ...
    </Routes>
  </AppShell>
</BrowserRouter>
```

**Delta to apply** (RESEARCH §Code Example 1; D-04):
1. Stop wrapping `<Routes>` in `<AppShell>`. Make `AppShell` the **layout-route element**: `<Route path="/" element={<AppShell />}>` with nested children rendering through `<Outlet/>`.
2. **Child paths become RELATIVE — drop the leading slash** (Pitfall 3): `path="series"`, NOT `path="/series"`. The index redirect's `to` target stays ABSOLUTE (`to="/series"`).
3. Change the default redirect target from `/queue` to `/series`: `<Route index element={<Navigate to="/series" replace />} />`.
4. Add new imports + routes: `Series` (`series`), `SeriesDetail` (`series/:seriesId`), `Movies` (`movies`).
5. Keep all existing pages, now as relative children: `queue`, `history`, `jobs/:id/logs`, `settings`, `bible`, `bible/:seriesId`.
6. Keep the transitional `library` route mounted on the existing `Library` import (D-03) — still imported, still routed, just no longer in the nav.

**Target shape:**
```tsx
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
> Update the file-header docstring's route list (`App.tsx:1-14`) to reflect `/` → `/series` and the new routes. No backend change needed — `SPAStaticFiles` already serves `index.html` for the new extensionless deep links.

---

### `frontend/src/pages/Series.tsx` and `frontend/src/pages/Movies.tsx` (NEW STUBS — page)

**Analog:** `frontend/src/pages/Queue.tsx` — specifically its top-level structure: file-header docstring, `export default function`, and the heading block (`Queue.tsx:55-62`):
```tsx
// Queue.tsx:55-62 — the heading-row pattern to simplify from
<div>
  <div className="flex items-center gap-3 mb-4">
    <h1 className="text-lg font-semibold text-[#e2e6f0]">Queue</h1>
    <span className="text-xs text-[#6b7280]">{jobs.length} items</span>
  </div>
  ...
</div>
```

**Delta:** strip all data fetching / state / polling (Queue's `useState`/`useEffect`/`getQueue`) — stubs render a heading only. Use `text-xl font-semibold` per UI-SPEC §Typography (Heading role 20px/600) and `text-muted-foreground` for the optional subline:
```tsx
export default function Series() {
  return (
    <div>
      <h1 className="text-xl font-semibold">Series</h1>
      <p className="text-muted-foreground">Coming in Phase 14</p> {/* optional (discretion) */}
    </div>
  );
}
```
> `Movies.tsx` is identical with "Movies". Strict-TS (Pitfall 4): import nothing — these stubs need no imports at all.

---

### `frontend/src/pages/SeriesDetail.tsx` (NEW STUB — page with param)

**Analog:** `frontend/src/pages/JobLogs.tsx` — the `useParams` read pattern (`JobLogs.tsx:10-21`):
```tsx
import { useParams } from "react-router-dom";   // JobLogs.tsx:11
// ...
const { id } = useParams<{ id: string }>();      // JobLogs.tsx:19
```

**Delta:** read `:seriesId` (route param name from `App.tsx` `series/:seriesId`), echo it into the heading. Reading the param satisfies `noUnusedLocals` (Pitfall 4) — if you import `useParams` you MUST read its result, or omit the import entirely:
```tsx
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
> XSS note (RESEARCH §Security): `seriesId` is rendered as a JSX text node (auto-escaped) — never `dangerouslySetInnerHTML`. Safe by default.

---

## Shared Patterns

### Active-nav left-2px accent bar (the phase's defining cross-cutting pattern)
**Legacy source:** `frontend/src/components/AppShell.tsx:43-50` (`border-l-2 border-accent bg-bg-stripe` / `border-l-2 border-transparent`).
**Vendor gap:** `frontend/src/components/ui/sidebar.tsx:523` — `data-[active=true]` is filled-bg only, no `border-l`.
**Apply to:** every `SidebarMenuButton` in `app-sidebar.tsx`.
```tsx
className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"
```
Never edit the vendor file — the bar is composed via `className` (merged additively by `cn()` at `sidebar.tsx:573`).

### File-header JSDoc docstring
**Source:** every existing component/page (`AppShell.tsx:1-11`, `App.tsx:1-14`, `Queue.tsx:1-11`, `JobLogs.tsx:1-9`).
**Apply to:** all new/replaced files. Open with a JSDoc block citing the controlling spec/decision (cite `12-UI-SPEC.md §Interaction Contract` and the relevant `D-0x`).

### Green service-status dot (verbatim carry-over)
**Source:** `frontend/src/components/AppShell.tsx:64-69` — `bg-[#22c55e]`, `aria-label="Service status: running"`, `title="Service running"`.
**Apply to:** `app-sidebar.tsx` `SidebarFooter` only. Keep static semantics; do NOT wire to *arr state (Phase 14).

### Strict-TS hygiene (`noUnusedLocals` / `noUnusedParameters`)
**Source:** `frontend/tsconfig.json` (single flat config; strict + both unused flags `true`).
**Apply to:** all new files. Import only used icons; in `SeriesDetail.tsx` read `seriesId` or omit `useParams`. Build gate: `cd frontend && npm run build` (= `tsc -b && vite build`). There is NO frontend test harness — build + browser UAT is the only validation.

### lucide icon sizing convention
**Source:** `AppShell.tsx:79-101` (`<Settings size={16} />` etc.) and `JobLogs.tsx:12` (`ChevronLeft`).
**Apply to:** nav rows use `size={16}` (matches legacy + vendor's forced `[&>svg]:size-4`); brand glyph uses `size={20}` (D-06, reads at 16-20px).

---

## No Analog Found

None. Every Phase-12 file has a direct in-codebase analog (the file itself for the two rewrites; `Queue.tsx`/`JobLogs.tsx` for the stubs; `AppShell.tsx`'s `NavItem` + vendor `sidebar.tsx` for `app-sidebar.tsx`). There are no backend files in scope. RESEARCH.md §Code Examples 1-4 are the vetted target shapes and align with these analogs.

---

## Metadata

**Analog search scope:** `frontend/src/components/`, `frontend/src/components/ui/`, `frontend/src/pages/`, `frontend/src/App.tsx`
**Files scanned (read):** `AppShell.tsx`, `App.tsx`, `Queue.tsx`, `JobLogs.tsx` (partial), `ui/sidebar.tsx` (targeted: lines 505-614 + export list)
**Vendor invariant:** `frontend/src/components/ui/sidebar.tsx` is vendor code — never hand-edit; accent bar goes on `app-sidebar.tsx` `className`.
**Pattern extraction date:** 2026-06-03
