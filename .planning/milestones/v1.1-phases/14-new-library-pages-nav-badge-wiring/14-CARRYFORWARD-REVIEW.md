# Carry-forward review findings → Phase 14

Source: Phase 12 (App Shell) code review (`12-REVIEW.md`). These findings live in files Phase 14
reworks (app-sidebar.tsx, App.tsx, SeriesDetail.tsx), so they were intentionally NOT fixed in
Phase 12 to avoid fix-then-rework churn. **Fold them into Phase 14 planning/execution.**

- **WR-01 — Missing `SidebarGroup` wrapper** (`frontend/src/components/app-sidebar.tsx`):
  shadcn vendor expects `SidebarContent > SidebarGroup > SidebarMenu`. Without `SidebarGroup`
  the nav `<ul>` loses its `p-2` inset and renders flush to the panel walls + may break
  icon-mode padding transitions. Phase 14 wires sidebar badges here — add the wrapper then.

- **WR-03 — No catch-all/404 route** (`frontend/src/App.tsx`): unrecognized paths render the
  shell with a silently blank `<Outlet>`. Add `<Route path="*" element={<NotFound/>}/>` as the
  last child of the layout route (with a minimal `NotFound.tsx`). Phase 14 touches the route
  table for the real pages — add it there.

- **IN-01 — `useParams()` typing** (`frontend/src/pages/SeriesDetail.tsx`): currently
  `seriesId` is `string | undefined` and rendered unguarded. Phase 14 builds the real
  SeriesDetail with API calls keyed on `seriesId` — use `useParams<{ seriesId: string }>()`
  with an explicit guard before the fetch.

- **WR-02 — Keyboard-operable expand after collapse** (a11y, advisory): `SidebarTrigger` is
  hidden in icon mode and `SidebarRail` has `tabIndex={-1}`, so there is no keyboard-reachable
  expand affordance (Cmd/Ctrl+B still works). Optional: surface `aria-keyshortcuts` on
  `<Sidebar>` or keep the trigger visible. Low priority; address if convenient during reskin.
