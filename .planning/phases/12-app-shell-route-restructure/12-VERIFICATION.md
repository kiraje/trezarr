---
phase: 12-app-shell-route-restructure
verified: 2026-06-04T00:00:00Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open the running UI and navigate to each of /series, /movies, /queue, /history, /bible, /settings. Confirm the left 2px purple accent bar renders on the active nav item (not just a background tint)."
    expected: "A visible 2px purple bar on the left edge of the active SidebarMenuButton across all six routes."
    why_human: "The accent bar is CSS (data-[active=true]:border-sidebar-primary); grep confirms the className string is present, but visual rendering requires a live browser to confirm the CSS variable resolves to purple and the 2px border-left is visible against the sidebar background."
  - test: "Confirm the full-height sidebar renders on every page. Press Cmd/Ctrl+B (or drag SidebarRail) to collapse to icon rail. Verify: labels and TREZARR pill disappear, icons remain, the active accent bar still shows on the active icon. Reload after collapse and confirm sidebar_state cookie preserves collapsed state."
    expected: "Sidebar collapses to ~48px icon rail, accent bar persists on active icon, state survives reload."
    why_human: "Collapse behavior and cookie persistence involve vendor SidebarProvider state machine and browser cookie mechanics — not verifiable by static grep."
  - test: "Hard-refresh on /series/1. Confirm the page loads correctly (SPA fallback serves index.html) and the SeriesDetail heading shows 'Series Detail' with the echoed seriesId '1'."
    expected: "Page loads, heading shows, seriesId echoed as plain text — no raw HTML in the heading."
    why_human: "SPA fallback behavior (SPAStaticFiles) requires a running server. While the static analysis confirms no dangerouslySetInnerHTML, the end-to-end render of the route param confirms the XSS mitigation works in practice."
  - test: "Navigate to /library directly. Confirm it renders the existing Library page inside the new sidebar shell with no console errors."
    expected: "Library page renders inside the new AppShell (sidebar visible), no JavaScript errors in DevTools."
    why_human: "D-03 transitional route correctness requires a live browser to confirm the old Library component renders without errors inside the new SidebarProvider shell."
---

# Phase 12: App Shell + Route Restructure Verification Report

**Phase Goal:** The current AppShell is replaced with a SidebarProvider + AppSidebar + Outlet layout, the route table is restructured with `/library` split into `/series` + `/movies` + `/series/:id` and `/` redirecting to `/series`, and all existing pages load correctly inside the new full-height sidebar shell.

**Verified:** 2026-06-04
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | NAV-01: full-height sidebar shell with Captions glyph + TREZARR pill; left 2px purple accent bar on active nav item | VERIFIED (static) / human needed (visual) | `app-sidebar.tsx:53` renders `<Captions className="text-sidebar-primary" size={20}/>` + `<span>TREZARR</span>`; `SidebarMenuButton` carries `className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"` at line 74. Visual rendering requires live browser. |
| 2 | NAV-02: nav exposes exactly 6 items (Series/Movies/Queue/History/Bible/Settings); /library splits into /series + /movies; / redirects to /series | VERIFIED | `NAV_ITEMS` const has exactly 6 entries in locked order; `/library` absent from `NAV_ITEMS` (comments only). `App.tsx:46` `<Route index element={<Navigate to="/series" replace />}/>`. Routes for `series`, `series/:seriesId`, `movies` all present. |
| 3 | D-01: sidebar collapsible=icon; SidebarRail present; sidebar_state cookie via vendor | VERIFIED (static) / human needed (behavior) | `app-sidebar.tsx:49` `<Sidebar collapsible="icon">`; `SidebarRail` imported and rendered at line 100. Cookie managed by vendor SidebarProvider (no custom code needed). Collapse/cookie behavior requires live browser. |
| 4 | D-02: 48px TopBar dropped; green status dot in SidebarFooter (static semantics) | VERIFIED | `AppShell.tsx` has no TopBar, no header element, no w-48; `app-sidebar.tsx:86-95` renders `bg-[#22c55e]` dot with `aria-label="Service status: running"` and `title="Service running"`. Running label hidden when collapsed via `group-data-[collapsible=icon]:hidden`. |
| 5 | D-03: /library transitional route mounted (Library.tsx untouched); absent from NAV_ITEMS | VERIFIED | `App.tsx:56` `<Route path="library" element={<Library />}/>` present. `NAV_ITEMS` in `app-sidebar.tsx` has zero `/library` entry. `git diff HEAD~3..HEAD -- frontend/src/pages/Library.tsx` returns empty (Library.tsx not touched). |
| 6 | D-04: single layout route (`<Route path="/" element={<AppShell/>}>`) with Outlet; child paths relative; index redirects /series | VERIFIED | `App.tsx:44-57`: layout route at path `/`, element `<AppShell/>`, all child `path=` values are relative (no leading slash), `<Navigate to="/series" replace/>` for index. `AppShell.tsx:29` `<Outlet/>` present. |
| 7 | D-05: active state via useLocation prefix-match; navigate(to) not asChild+anchor | VERIFIED | `app-sidebar.tsx:67`: `const isActive = pathname === to \|\| pathname.startsWith(to + "/")`. `onClick={() => navigate(to)}` at line 73. No `asChild` in non-comment code (grep confirms 0 matches in code lines). |
| 8 | D-06: Captions glyph tinted text-sidebar-primary + uppercase TREZARR pill in SidebarHeader; glyph only when collapsed | VERIFIED | `app-sidebar.tsx:53-58`: Captions glyph + TREZARR pill with `group-data-[collapsible=icon]:hidden` on pill span. No new image asset (icon from lucide-react). |

**Score:** 8/8 truths verified (static analysis); 4 items additionally need live browser confirmation.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/pages/Series.tsx` | Stub page, zero imports, heading "Series" | VERIFIED | Exists; zero imports; `<h1 className="text-xl font-semibold">Series</h1>`; default export. |
| `frontend/src/pages/Movies.tsx` | Stub page, zero imports, heading "Movies" | VERIFIED | Exists; zero imports; `<h1 className="text-xl font-semibold">Movies</h1>`; default export. |
| `frontend/src/pages/SeriesDetail.tsx` | Stub page, reads `:seriesId` via useParams; echoes as JSX text; no dangerouslySetInnerHTML | VERIFIED | Exists; imports `useParams`; destructures `seriesId`; renders `Series #{seriesId}` as JSX text node; `dangerouslySetInnerHTML` absent from code (appears only in JSDoc comment). |
| `frontend/src/components/app-sidebar.tsx` | AppSidebar: brand, 6 nav items, accent bar, footer status dot, SidebarRail | VERIFIED | Exists; `AppSidebar` named export; 6 `NAV_ITEMS` in correct order; accent bar className verbatim; `SidebarRail` rendered; green dot in `SidebarFooter`. |
| `frontend/src/components/AppShell.tsx` | Thin SidebarProvider + AppSidebar + Outlet; no children prop, no TopBar, no w-48 | VERIFIED | Exists; no `AppShellProps`, no `children`, no `w-48`, no `TopBar`; `<SidebarProvider>`, `<AppSidebar/>`, `<Outlet/>` all present; `main` className is `flex-1 overflow-auto bg-background p-6`. |
| `frontend/src/App.tsx` | Layout route table; Navigate to=/series; series + movies + series/:seriesId added; library kept | VERIFIED | Exists; layout route `<Route path="/" element={<AppShell/>}>`; index `<Navigate to="/series" replace/>`; all 11 expected routes present as relative paths; Library import and route intact. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app-sidebar.tsx` | `ui/sidebar.tsx` | `SidebarMenuButton` `isActive` prop → `data-[active=true]:border-sidebar-primary` | VERIFIED | `app-sidebar.tsx:74` contains verbatim className string `border-l-2 border-transparent data-[active=true]:border-sidebar-primary`. `isActive` prop passed. |
| `AppShell.tsx` | `react-router-dom Outlet` | layout-route element renders `<Outlet>` | VERIFIED | `AppShell.tsx:29` `<Outlet/>` present; imported from `react-router-dom` at line 20. |
| `App.tsx` | `AppShell.tsx` | layout route `element={<AppShell/>}` | VERIFIED | `App.tsx:44` `<Route path="/" element={<AppShell />}>`. |

---

### Data-Flow Trace (Level 4)

Not applicable — Phase 12 is a routing/shell phase. No dynamic data is fetched. All three stub pages are intentional placeholders (real content deferred to Phase 14). No API calls or state management introduced.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Frontend build exits 0 (tsc strict + vite build) | `cd frontend && npm run build` | `✓ 1740 modules transformed, built in 1.26s, exit 0` | PASS |
| `trezarr/web/static` populated | `ls trezarr/web/static/` | `assets/ index.html (880B)` | PASS |

---

### Probe Execution

No probes declared or conventional probe scripts found for this phase.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| NAV-01 | 12-01-PLAN.md | User sees a full-height sidebar shell with brand (logo glyph + "TREZARR" pill); active section marked with left purple accent bar | VERIFIED (static) + human needed (visual) | `app-sidebar.tsx` brand + accent bar className verified in code. Visual rendering requires live browser. |
| NAV-02 | 12-01-PLAN.md | Navigation exposes Series/Movies/Queue/History/Bible/Settings; /library splits into /series and /movies; / redirects to /series | VERIFIED | 6-item `NAV_ITEMS`, `/library` absent from nav, `Navigate to="/series"`, routes for series/movies/series/:seriesId all wired. |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/src/pages/Series.tsx` | — | Stub placeholder (intentional) | Info | Planned; Phase 14 will add real content. Not a blocker. |
| `frontend/src/pages/Movies.tsx` | — | Stub placeholder (intentional) | Info | Planned; Phase 14 will add real content. Not a blocker. |
| `frontend/src/pages/SeriesDetail.tsx` | — | Stub placeholder (intentional) | Info | Planned; Phase 14 will add real content. Not a blocker. |

No unreferenced TBD/FIXME/XXX debt markers found in any phase-12 modified file. The stub pages are documented in the SUMMARY and explicitly deferred to Phase 14 in the PLAN.

---

### Human Verification Required

#### 1. Active nav accent bar renders correctly

**Test:** Open the running UI (http://localhost:6868 or your *arr-stack deployment). Navigate to each of /series, /movies, /queue, /history, /bible, /settings.
**Expected:** Each active page shows a visible 2px purple bar on the left edge of the active SidebarMenuButton. The bar should be a distinct border, not just a background tint.
**Why human:** The accent bar relies on `data-[active=true]:border-sidebar-primary` resolving the `--sidebar-primary` CSS variable to a purple color under `.dark`. Static grep confirms the className string is present and `isActive` is wired, but rendering correctness requires a live browser.

#### 2. Sidebar collapse to icon rail (D-01)

**Test:** With the sidebar expanded, press Cmd+B (Mac) or Ctrl+B (Windows/Linux). Alternatively drag the SidebarRail.
**Expected:** Sidebar collapses to a ~48px icon rail — labels disappear, the TREZARR pill disappears, icons remain visible, and the purple accent bar still shows on the active icon. Reload the page; the sidebar should remain collapsed (sidebar_state cookie persistence).
**Why human:** Collapse behavior and cookie persistence are vendor SidebarProvider internals that cannot be verified by static analysis.

#### 3. SPA deep-link fallback for /series/:seriesId (D-04)

**Test:** Manually type `http://localhost:6868/series/1` into the browser address bar and press Enter (hard navigation, not client-side routing).
**Expected:** Page loads the SeriesDetail stub showing "Series Detail" heading and "Series #1 — coming in Phase 14". No blank page, no 404, no raw HTML in the heading.
**Why human:** SPA fallback behavior (SPAStaticFiles returning index.html) requires a running FastAPI server. The T-12-01 XSS mitigation (JSX auto-escape) is confirmed by static analysis but end-to-end rendering confirms the full path.

#### 4. /library transitional route renders inside new shell (D-03)

**Test:** Navigate directly to `http://localhost:6868/library`.
**Expected:** The existing Library page renders correctly inside the new SidebarProvider + AppSidebar shell (sidebar is visible, Library page content appears in the main area), with no JavaScript console errors.
**Why human:** Confirms the legacy Library component is compatible with the new SidebarProvider context; requires a live browser to check for runtime errors.

---

### Gaps Summary

No gaps. All eight must-have truths verified statically. The four human verification items above are browser-only checks (visual rendering, CSS variable resolution, SPA fallback, runtime compatibility); they cannot be disproved by static analysis and should not be classified as failures.

The three stub pages (Series, Movies, SeriesDetail) are intentional and documented — their real content is explicitly deferred to Phase 14.

---

_Verified: 2026-06-04_
_Verifier: Claude (gsd-verifier)_
